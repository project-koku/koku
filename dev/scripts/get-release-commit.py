#!/usr/bin/env python
# Get the latest commit hash before midnight UTC.
# Smoke tests run at midnight UTC.
# We want to release the commit that ran in yesterday's test.
#
# Show the long and short (seven character) hash. The long hash is needed
# for app-interface, the short hash is useful for checking the container image.
import shutil
import subprocess
from datetime import datetime


def _run(command: list[str]) -> str:
    return subprocess.check_output(command, text=True)


def main() -> None:
    git = shutil.which("git")

    # Get the upstream of the main branch
    cmd = [git, "for-each-ref", "--format", "%(upstream:short)", "refs/heads/main"]
    upstream_name = _run(cmd).split("/", 1)[0]

    # Fetch changes from the remote
    _run([git, "fetch", upstream_name])

    # Get commit before 00:00:00 UTC
    today = datetime.today().strftime("%Y-%m-%d")
    cmd = [
        git,
        "log",
        f"--before={today} 00:00:00-0000",
        "--format=%H",
        "--no-merges",
        f"{upstream_name}/main",
        "--max-count=1",
    ]
    out = _run(cmd)

    print(f"The latest safe to release commit is {out.strip()} ({out[:7]})")


if __name__ == "__main__":
    main()
