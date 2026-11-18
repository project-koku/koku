#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Helpers for Django parallel test workers.

Kept in a minimal module so multiprocessing spawn does not import Django models
before the app registry is ready.
"""


def init_worker(
    counter,
    initial_settings=None,
    serialized_contents=None,
    process_setup=None,
    process_setup_args=None,
    debug_mode=None,
    used_aliases=None,
):
    """Initialize a parallel worker with DB routing and an isolated Masu data dir."""
    from django.test.runner import _init_worker as django_init_worker
    from django.test.runner import _worker_id

    from masu.config import configure_worker_data_dir

    django_init_worker(
        counter,
        initial_settings,
        serialized_contents,
        process_setup,
        process_setup_args,
        debug_mode,
        used_aliases,
    )
    configure_worker_data_dir(_worker_id)
