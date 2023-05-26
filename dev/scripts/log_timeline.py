#! /usr/bin/env python3
import argparse
import ast
import csv
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
from pytz import UTC


random.seed(time.time())
logging.basicConfig(stream=sys.stderr, format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO)
LOG = logging.getLogger(os.path.basename(sys.argv[0]))
LOG_LINE_META = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{1,4})[: \]].([A-Z]+).(\S+).(.+)")
LOG_LINE_SCRUB = re.compile("\x1b\\[.+?m")


class StdoutWriter:
    STDOUT_ESC = "\033["
    STDOUT_COLORS = {
        "none": f"{STDOUT_ESC}0m",
        "black": f"{STDOUT_ESC}0;30m",
        "red": f"{STDOUT_ESC}0;31m",
        "green": f"{STDOUT_ESC}0;32m",
        "brown": f"{STDOUT_ESC}0;33m",
        "blue": f"{STDOUT_ESC}0;34m",
        "purple": f"{STDOUT_ESC}0;35m",
        "cyan": f"{STDOUT_ESC}0;36m",
        "yellow": f"{STDOUT_ESC}1;33m",
        "white": f"{STDOUT_ESC}1;37m",
        "gray": f"{STDOUT_ESC}1;30m",
        "ltred": f"{STDOUT_ESC}1;31m",
        "ltgreen": f"{STDOUT_ESC}1;32m",
        "ltblue": f"{STDOUT_ESC}1;34m",
        "ltpurple": f"{STDOUT_ESC}1;35m",
        "ltcyan": f"{STDOUT_ESC}1;36m",
        None: None,
    }
    STDOUT_COLORS["orange"] = STDOUT_COLORS["brown"]
    STDOUT_COLORS_LIST = [k for k in STDOUT_COLORS if k]

    def __init__(self, ofile, fieldnames):
        self._file = ofile
        self.fieldnames = fieldnames
        self._format = " ".join(f"{{{fn}}}" for fn in fieldnames)
        self._break = None
        self.log_color_map = {}
        self.id_fields = ("log_name", "log_line")
        # self.id_fields = ("log_ts", "log_name", "log_line")

    def stdout_format(self, data, color=None):
        if color:
            msg = f"{self.STDOUT_COLORS[color]}{data}{self.STDOUT_COLORS['none']}"

        return msg

    def writeheader(self):
        pass

    def writerow(self, data):
        # LOG.debug(f"""BREAK {self._break} || U_BOUND {data["_u_bound"]}""")
        if self._break is None:
            self._break = data["_u_bound"]
        elif self._break != data["_u_bound"]:
            self._break = data["_u_bound"]
            print("=" * 80)

        if not data:
            data = dict.fromkeys(self.fieldnames, "")
        # LOG.debug(data)
        # LOG.debug(self.fieldnames)
        log_name = data["log_name"]
        if log_name not in self.log_color_map:
            self.log_color_map[log_name] = self.STDOUT_COLORS_LIST[random.randrange(0, len(self.STDOUT_COLORS_LIST))]
        for key in self.id_fields:
            data[key] = self.stdout_format(data.get(key, ""), color=self.log_color_map[log_name])
        for key in self.fieldnames:
            if key not in self.id_fields and key != "log_ts":
                data[key] = self.stdout_format(data.get(key, ""), color=data.get("_color"))
        print(self._format.format(**data))

    def writerows(self, iterable):
        for data in iterable:
            self.writerow(data)


class Process:
    def __init__(self, db_url, logs, clean=False, dump=None, window="15 seconds", dump_debug=False):
        self.__db_url = db_url
        self.clean = clean
        self.logs = logs
        self.dump = dump
        self.window = window
        self.dump_debug = dump_debug

    def connect(self, db_url):
        LOG.info("Connecting to DB")
        self.conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        return self.conn

    def execute(self, sql, params=None):
        cur = self.conn.cursor()
        try:
            mogsql = cur.mogrify(sql, params).decode("utf-8")
        except Exception:
            LOG.error(f"SQL: {sql} PARAMS: {params}")
            raise
        LOG.debug(f"EXECUTING SQL Statement: {mogsql}")
        cur.execute(mogsql)
        return cur

    def table_exists(self, table_name):
        sql = """SELECT to_regclass(format('"public".%%I', %s))::oid as table_oid;"""
        cur = self.execute(sql, ("_log_timeline",))
        rec = cur.fetchone()
        exists = rec and rec["table_oid"] is not None and rec["table_oid"] > 0
        LOG.debug(f"Table {table_name} {'exists' if exists else 'does not exist'}")
        return exists

    def create_table(self):
        LOG.debug("Dropping existing table if it exists")
        sql = """
drop table if exists public._log_timeline
;
"""
        self.execute(sql)

        LOG.info("creating table")
        sql = """
create table public._log_timeline (
    log_ts timestamptz not null,
    log_name text not null,
    log_line bigint not null,
    log_level text not null,
    log_ident text,
    log_message jsonb,
    primary key (log_name, log_line)
)
;
"""
        self.execute(sql)

        LOG.info("creating table indexes")
        sql = """
create index log_timeline_ix1 on public._log_timeline (log_ts)
;
"""
        self.execute(sql)

        sql = """
create index log_timeline_ix2 on public._log_timeline (log_level)
;
"""
        self.execute(sql)

        self.conn.commit()

    def init_table(self):
        if self.clean or not self.table_exists("_log_timeline"):
            self.clean = False
            self.create_table()

    def parse_ts(self, ts):
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=UTC)

    def parse_json_or_eval(self, txt):
        if not isinstance(txt, str) or not txt:
            return None
        try:
            return json.loads(txt)
        except Exception:
            return ast.literal_eval(txt)

    def parse_log_message(self, msg):
        if msg[0] == "{":
            try:
                lmsg = self.parse_json_or_eval(msg)
            except Exception:
                lmsg = {"message": msg, "PARSE_FAIL": True}
        else:
            lmsg = {"message": msg}

        return lmsg

    def parse_level(self, level, message):
        umsg = str(message.get("message", "")).upper()
        if "ERROR" in umsg:
            level = "ERROR"
        elif "WARNING" in umsg:
            level = "WARNING"

        return level

    def readlog(self, logfile):
        log_name = os.path.splitext(os.path.basename(logfile.name))[0].split("_")[0]
        in_log = False
        ts = level = ident = None
        lmsg = None
        for line_num, log_line in enumerate(logfile):
            log_line = LOG_LINE_SCRUB.sub("", log_line).strip()
            if not log_line:
                continue

            if log_line[0] == "[":
                meta = LOG_LINE_META.match(log_line)
                if meta:
                    if in_log:
                        yield (
                            {
                                "log_name": log_name,
                                "log_line": line_num,
                                "log_ts": self.parse_ts(ts),
                                "log_level": level,
                                "log_ident": ident,
                                "log_message": json.dumps(lmsg),
                            }
                        )
                        ts = level = ident = None
                        lmsg = None

                    in_log = True
                    # LOG.debug(log_line)
                    # LOG.debug(meta.groups())
                    ts, level, ident, lmsg = meta.groups()
                    lmsg = self.parse_log_message(lmsg)
                    level = self.parse_level(level, lmsg)
                else:
                    in_log = False
            else:
                if in_log:
                    lmsg["message"] = f"{lmsg['message']}{os.linesep}{log_line}"

        if in_log and lmsg:
            yield (
                {
                    "log_name": log_name,
                    "log_line": line_num + 1,
                    "log_ts": self.parse_ts(ts),
                    "log_level": level,
                    "log_ident": ident,
                    "log_message": json.dumps(lmsg),
                }
            )

    def insert_log_line(self, log_data):
        # LOG.debug(log_data)
        sql = """
insert into public._log_timeline(log_name, log_line, log_ts, log_level, log_ident, log_message)
values (%(log_name)s, %(log_line)s, %(log_ts)s, %(log_level)s, %(log_ident)s, %(log_message)s)
;
"""
        if log_data["log_ident"] and not log_data["log_message"]:
            log_data["log_message"], log_data["log_ident"] = log_data["log_ident"], None
        self.execute(sql, log_data)

    def handle_log(self, log_file_name):
        LOG.info(f"Processing log file {log_file_name}")
        with open(log_file_name) as logfile:
            for rec in self.readlog(logfile):
                self.insert_log_line(rec)
        self.conn.commit()

    def open_dump_file(self):
        # LOG.critical(f"DUMP = {self.dump}")
        if self.dump:
            return open(self.dump[0], "w")
        return sys.stdout

    def get_error_log_ts_start_end(self):
        sql = """
select log_ts - %(window)s::interval as start_time,
       log_ts + %(window)s::interval as end_time
  from public._log_timeline
 where log_level = %(level)s
;
"""
        LOG.info("Getting windowed error ranges")
        starts = []
        ends = []
        res = None
        with self.execute(sql, {"window": self.window, "level": "ERROR"}) as cur:
            res = cur.fetchall()

        if res:
            LOG.info("Collpsing error ranges")
            for rec in res:
                if not starts:
                    starts.append(rec["start_time"])
                    ends.append(rec["end_time"])
                elif ends[-1] > rec["start_time"] and ends[-1] < rec["end_time"]:
                    ends[-1] = rec["end_time"]
                elif ends[-1] >= rec["end_time"]:
                    continue
                else:
                    starts.append(rec["start_time"])
                    ends.append(rec["end_time"])
            return starts, ends
        else:
            return [datetime(1900, 1, 1).replace(tzinfo=UTC)], [datetime(1900, 1, 2).replace(tzinfo=UTC)]

    def get_error_window_cte_stmt(self):
        start_times, end_times = self.get_error_log_ts_start_end()
        sql = """
with _window as (
select tstzrange(_win._start, _win._end, '[]') as "err_range"
  from unnest(%(start_times)s::timestamptz[], %(end_times)s::timestamptz[]) as _win(_start, _end)
)
"""
        params = {"start_times": start_times, "end_times": end_times}
        return sql, params

    def get_db_data_debug_stmt(self):
        sql = """
select case when w.err_range is null
                 then %(no_color)s
            else case when log_level = %(error_level)s
                           then %(error_color)s
                      else %(window_color)s
                 end::text
            end::text as _color,
       null::text as _u_bound,
       log_ts,
       log_name,
       log_line,
       log_level,
       log_ident,
       log_message
  from public._log_timeline lt
  left
  join _window w
    on w.err_range @> lt.log_ts
 order
    by lt.log_ts
;
"""
        params = {"no_color": "none", "error_color": "red", "window_color": "ltgreen", "error_level": "ERROR"}
        return sql, params

    def get_db_data_stmt(self):
        sql = """
select case when log_level = %(error_level)s
                 then %(error_color)s
            else %(window_color)s
       end::text as _color,
       upper(w.err_range) as _u_bound,
       log_ts,
       log_name,
       log_level,
       log_ident,
       log_message
  from public._log_timeline lt
  join _window w
    on w.err_range @> lt.log_ts
 order
    by lt.log_ts
;
"""
        params = {"error_color": "red", "window_color": "ltgreen", "error_level": "ERROR"}
        return sql, params

    def get_db_data(self, debug):
        LOG.info("Getting log data")
        sql = []
        params = {}
        _sql, _params = self.get_error_window_cte_stmt()
        sql.append(_sql)
        params.update(_params)
        get_stmt = self.get_db_data_debug_stmt if debug else self.get_db_data_stmt
        _sql, _params = get_stmt()
        sql.append(_sql)
        params.update(_params)

        return self.execute(os.linesep.join(sql), params)

    def dump_db(self, dumpfile):
        LOG.info("Dumping log timeline")
        cur = self.get_db_data(self.dump_debug)
        fields = [d[0] for d in cur.description if d[0][0] != "_"]
        if dumpfile == sys.stdout:
            LOG.info("Writing to stdout")
            writer = StdoutWriter(dumpfile, fields)
        else:
            LOG.info(f"Writing to {os.path.basename(dumpfile.name)}")
            writer = csv.DictWriter(dumpfile, fields, quoting=csv.QUOTE_MINIMAL)

        writer.writeheader()
        writer.writerows(cur)

    def process(self):
        with self.connect(self.__db_url):
            self.init_table()

            for log in self.logs:
                self.handle_log(log)

            if self.dump is not None:
                df = self.open_dump_file()
                try:
                    self.dump_db(df)
                finally:
                    df.flush()
                    df.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-url",
        type=str,
        metavar="DBURL",
        required=True,
        help="DB connect url (table will be created in public schema",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        dest="clean",
        required=False,
        default=False,
        help="Drop and recreate the database table",
    )
    parser.add_argument(
        "--dump-debug",
        action="store_true",
        dest="dump_debug",
        required=False,
        default=False,
        help="Dump original log file name and line",
    )
    parser.add_argument(
        "--debug", action="store_true", dest="debug", required=False, default=False, help="Set logging level to DEBUG"
    )
    parser.add_argument(
        "--dump",
        dest="dump",
        type=str,
        metavar="DUMPFILE",
        nargs="*",
        help="Dump logs as timeline. Write to file name if given.",
    )
    parser.add_argument(
        "--window",
        dest="window",
        type=str,
        required=False,
        default="5 seconds",
        help="Interval on either side of an error as '<value> <unit>'. Ex: '10 seconds'",
    )
    parser.add_argument("logs", nargs="*", metavar="LOGS", help="Log files to consume")

    args = parser.parse_args()
    if args.debug:
        LOG.setLevel(logging.DEBUG)

    Process(
        args.db_url,
        args.logs,
        clean=args.clean,
        dump=args.dump,
        window=args.window,
        dump_debug=args.dump_debug,
    ).process()
