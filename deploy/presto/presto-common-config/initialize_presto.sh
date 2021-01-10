#!/bin/bash
set -ex

cp -v -L -r -f /presto-etc/* /opt/presto/presto-server/etc/

if [[ "${LOCAL}" == 'TRUE' ]]; then
    echo 'Launching Presto.'
    /presto-common/entrypoint.sh /opt/presto/presto-server/bin/launcher run
fi
