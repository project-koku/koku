#!/bin/bash

set -e

pipenv run make
pipenv run make check-partitioned
