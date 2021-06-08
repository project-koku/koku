#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Obtain project environment."""
import environ

ROOT_DIR = environ.Path(__file__) - 3

ENVIRONMENT = environ.Env()

# .env file, should load only in development environment
READ_DOT_ENV_FILE = ENVIRONMENT.bool("DJANGO_READ_DOT_ENV_FILE", default=False)

if READ_DOT_ENV_FILE:
    # Operating System Environment variables have precedence over variables
    # defined in the .env file, that is to say variables from the .env files
    # will only be used if not defined as environment variables.
    ENV_FILE = str(ROOT_DIR.path(".env"))
    print(f"Loading : {ENV_FILE}")
    ENVIRONMENT.read_env(ENV_FILE)
    print("The .env file has been loaded.")
