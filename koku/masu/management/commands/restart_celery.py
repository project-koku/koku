#
# Copyright 2023 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
# pragma: no cover
"""Command to start celery worker with autoreload."""
import os
import shlex
import signal
import subprocess

import psutil
from django.core.management.base import BaseCommand
from django.utils import autoreload


def get_pid(name):
    return [proc.pid for proc in psutil.process_iter() if name in proc.name()]


def restart_celery():
    for pid in get_pid("celery"):
        os.kill(pid, signal.SIGTERM)
    cmd =  [
        "celery"
        "-A", "koku", "worker",
        "--without-gossip",
        "-P", "solo",
        "-l", "info",
        "-Q", "celery,download,hcs,ocp,priority,summary,cost_model,refresh,subs_extraction,subs_transmission",
    ]
    subprocess.run(cmd)


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Starting celery worker with autoreload...")
        autoreload.run_with_reloader(restart_celery)
