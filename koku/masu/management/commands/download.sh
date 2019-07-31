#!/bin/bash
docker exec -it koku_listener bash -c 'python koku/manage.py api'
