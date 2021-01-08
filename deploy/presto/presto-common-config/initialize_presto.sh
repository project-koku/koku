#!/bin/bash
set -ex

cp -v -L -r -f /trino-etc/* /opt/trino/trino-server/etc/

if [[ "${LOCAL}" == 'TRUE' ]]; then
    echo 'Launching Trino.'
    /trino-common/entrypoint.sh /opt/trino/trino-server/bin/launcher run
fi
