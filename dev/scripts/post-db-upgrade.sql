#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#

-- ================================================
--   THIS SCRIPT WAS WRITTEN TO BE RUN USING psql
-- ================================================
-- The script should be invoked like:
--     psql <connection options> -f <path-to>/scripts/post-db-upgrade.sql --variable=TARGET_DB=<database_name>
--  Ex:
--     psql -h localhost -d postgres -U postgres -p 15432 -f ./scripts/post-db-upgrade.sql --VARIABLE=TARGET_DB=postgres

-- This script will run a VACUUM ANALYZE command on the koku database
-- Following that, the script will run a REINDEX on all of the database tables

-- This script should be run after a major version database upgrade.
-- There may be changes in how is stores or caclulates statsitics as well as how
-- indexes are stored or ordered.

\echo
\echo =========================================================
\echo Connecting to the target database :"TARGET_DB"
\c :TARGET_DB

\echo
\echo =========================================================
\echo Running vacuum/analyze on :"TARGET_DB" ...
VACUUM ( ANALYZE, VERBOSE )
;

\echo
\echo =========================================================
\echo Running reindex :"TARGET_DB" ...
REINDEX ( VERBOSE ) DATABASE :TARGET_DB;
