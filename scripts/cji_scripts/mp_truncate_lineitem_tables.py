#! /usr/bin/env python3
#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
#
# This prgram is designed for multi-process task processing.
# The tables to be truncated will be processed as all lineitem tables first
# followed by the lineitem_daily tables.
# This way, all of the tables can be operated upon atomically. Each worker will
# process one table at a time, signallying when they are ready for a new table.
# When there are no more tables to process, workers will be marked as done.
# When all workers are done, the main process will end.
#
import json
import logging
import os
import sys
import time
from multiprocessing import get_context
from multiprocessing import Process
from multiprocessing.queues import Queue as MPQueue
from queue import Empty

import psycopg2
from lite.config import CONFIGURATOR
from lite.env import ENVIRONMENT
from psycopg2.extras import RealDictCursor


logging.basicConfig(
    format="%(processName)s (%(process)d) :: %(asctime)s: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=getattr(logging, ENVIRONMENT.get_value("KOKU_LOG_LEVEL", default="INFO")),
)
LOG = logging.getLogger("super_truncate_limeitem")


READY_ACTION = "*READY*"
TASK_ACTION = "*TASK*"
STOP_ACTION = "*STOP*"


class WrkrQueue(MPQueue):
    """Interface for the worker process"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, ctx=get_context(), **kwargs)

    def get(self, *args, **kwargs):
        msg = super().get(*args, **kwargs)
        return json.loads(msg)

    def put(self, action, data=None, blocking=False, timeout=None):
        msg = {"action": action, "data": data}
        super().put(json.dumps(msg), blocking, timeout)


class Worker:
    """Interface for the main process"""

    def __init__(self, target, name, ident=None):
        self.ident = "" if ident is None else ident
        LOG.debug("Creating Queue")
        self.__squeue = WrkrQueue()  # Send-to-Worker Queue
        self.__rqueue = WrkrQueue()  # Receive-from-Worker Queue
        LOG.debug("Creating worker process")
        self.__worker = Process(
            target=process_truncate, name=f"trunc_worker {self.ident}", args=(self.__squeue, self.__rqueue, self.ident)
        )
        self.done = 0

    def start(self):
        if not self.done:
            LOG.info(f"Starting worker process {self.ident}")
            self.__worker.daemon = True
            self.__worker.start()

    def stop(self):
        if not self.done:
            LOG.info(f"Stopping worker process {self.ident}")
            self.put(STOP_ACTION)
            self.__worker.join()
            LOG.debug("worker process completed join()")
            self.done = 1

    def get(self):
        """Always reads from rqueue"""
        if not self.done:
            LOG.debug("Getting message")
            try:
                msg = self.__rqueue.get(False)
            except Empty:
                msg = {"action": None}
            LOG.debug("got message", msg)
            return msg
        return {"action": None}

    def put(self, action, data=None, blocking=False, timeout=None):
        """Always writes to squeue"""
        if not self.done:
            LOG.debug("Putting message", action, data)
            self.__squeue.put(action, data, blocking, timeout)

    def is_ready(self):
        if not self.done:
            return self.get()["action"] == READY_ACTION
        return False


def connect():
    """Establish a database connection"""
    engine = "postgresql"
    app = os.path.basename(sys.argv[0])

    user = CONFIGURATOR.get_database_user()
    passwd = CONFIGURATOR.get_database_password()
    host = CONFIGURATOR.get_database_host()
    port = CONFIGURATOR.get_database_port()
    db = CONFIGURATOR.get_database_name()

    url = f"{engine}://{user}:{passwd}@{host}:{port}/{db}?sslmode=prefer&application_name={app}"
    LOG.info(f"Connecting to {db} at {host}:{port} as {user}")

    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def _execute(conn, sql, params=None):
    """Execute and log SQL"""
    cur = conn.cursor()
    stmt = cur.mogrify(sql, params).decode("utf-8")
    LOG.debug(f"SQL: {stmt}")
    cur.execute(stmt)
    return cur


def get_target_tables(conn):
    """Get the target tables in order of truncation for atomic processing"""
    sql = """
select table_schema,
       table_name
  from information_schema.tables
 where table_name ~ 'lineitem$'
    or table_name ~ 'lineitem_daily$'
 order
    by table_name,
       table_schema
;
"""
    return _execute(conn, sql).fetchall()


def truncate_table(conn, trunc_info, worker_id):
    """Format and submit the table truncate SQL"""
    sql = f"truncate table {trunc_info['table_schema']}.{trunc_info['table_name']} ;"
    LOG.info(f"WORKER {worker_id}: Truncating table {trunc_info['table_schema']}.{trunc_info['table_name']}")
    _execute(conn, sql)
    _execute(conn, "commit ;")


def process_truncate(task_queue, comm_queue, worker_id):
    """Worker process. Read messages from task queue for processing.
    Signal readiness by writing to communication queue"""
    LOG.info(f"worker {worker_id} started")
    # Establish a connection for this worker process
    with connect() as conn:
        # Listen until told to stop.
        while True:
            # Notify main process that worker is ready
            comm_queue.put(READY_ACTION)
            # Wait for task message
            msg = task_queue.get(True)
            LOG.debug(f"WORKER {worker_id}: Got message: {msg}")
            # If we get a STOP_ACTION message, terminate the loop
            if msg["action"] == STOP_ACTION:
                LOG.info(f"WORKER {worker_id} stopping")
                break
            elif msg["action"] == TASK_ACTION:
                # Process the table given in the TASK_ACTION
                truncate_table(conn, msg["data"], worker_id)


def task_handler(num_workers=1):
    """Main process. Create workers, check for readiness, pass tasks to workers.
    Once all worders have been marked "done", then exit."""
    LOG.info("Truncate handler started")
    workers = []
    tasks = None

    # Get target tables to truncate
    with connect() as conn:
        tasks = [{"action": TASK_ACTION, "data": rec} for rec in get_target_tables(conn)]

    # Create workers
    for wnum in range(num_workers):
        worker = Worker(process_truncate, f"worker {wnum}", ident=wnum)
        worker.start()
        workers.append(worker)

    done_workers = 0
    # Process until all workers are marked as "done"
    while done_workers < num_workers:
        # Poll available workers
        for worker in workers:
            # If worker is "ready", then we can submit a task to that worker
            if tasks:
                if worker.is_ready():
                    LOG.debug(f"Worker {worker.ident} is ready")
                    worker.put(**tasks.pop(0))
            else:
                # If there are no more tasks, tell worker to stop
                # This will mark the worker as "done"
                worker.stop()
            done_workers += worker.done
        # Rebuild workers so we don't have to re-check "done" workers
        workers = [w for w in workers if not w.done]
        time.sleep(0.1)


if __name__ == "__main__":
    num_workers = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("NUM_TRUNC_WORKERS", 2)) or 2
    task_handler(num_workers)
