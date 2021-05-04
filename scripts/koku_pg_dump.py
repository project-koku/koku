#!/usr/bin/env python3
import io
import os
import subprocess
import sys


if len(sys.argv) < 3:
    print(f"Usage {os.path.basename(sys.argv[0])} db_url", file=sys.stderr)
    sys.exit(1)


insert = []
ins_sep = "VALUES "
val_sep = f",{os.linesep}"


with open(sys.argv[2], "wt") as out:
    cmd = f"pg_dump -d {sys.argv[1]} --no-owner --schema=template0 --inserts"
    proc = subprocess.Popen(cmd.split(" "), stdout=subprocess.PIPE)
    for line in io.TextIOWrapper(proc.stdout, encoding="utf-8"):
        line = line.rstrip().replace("template0.", "")
        eol = os.linesep * 2 if line.endswith(";") else None

        if line.startswith("INSERT"):
            if "partitioned_tables" in line:
                line = line.replace("'template0'", "current_schema")

            if not insert:
                insert.append(line[:-1])
            else:
                insert.append(line.split(ins_sep)[1][:-1])

            continue
        elif insert:
            print(f"{val_sep.join(insert)};{os.linesep}", file=out)
            insert = []

        if (
            (len(line) == 0)
            or line.startswith("SET")
            or line.startswith("CREATE SCHEMA")
            or line.startswith("--")
            or line.startswith("SELECT pg_catalog.set_config")
        ):
            continue

        print(line, file=out, end=eol)
