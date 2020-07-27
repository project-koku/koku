/*
Copyright 2020 Red Hat, Inc.
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.
You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

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
VACUUM ( ANALYZE, VERBOSE );

\echo
\echo =========================================================
\echo Running reindex :"TARGET_DB" ...
REINDEX ( VERBOSE ) DATABASE :TARGET_DB ;
