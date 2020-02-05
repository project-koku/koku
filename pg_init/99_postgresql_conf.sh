#! /usr/bin/env bash

echo "Updating ${PGDATA}/postgresql.conf..."
cat >>${PGDATA}/postgresql.conf <<EOF

# ==============================================
# -----------------------------
# PostgreSQL configuration file additions
# These additions are to allow for local statement statistics
# These configuration options were taken from PostgreSQL 10.6
# -----------------------------

shared_preload_libraries = 'pg_stat_statements'		# (change requires restart)

pg_stat_statements.max = 5000          # max number of statements to track
pg_stat_statements.track = top         # top = statements issued by clients; all = top + statements in functions; none = disable stats
pg_stat_statements.track_utility = off # on = track statements other than SELECT INSERT UPDATE DELETE; off = no tracking
pg_stat_statements.save = off          # on = save stats between restarts; off = do not save

log_min_error_statement = error	# values in order of decreasing detail:
					#   debug5
					#   debug4
					#   debug3
					#   debug2
					#   debug1
					#   info
					#   notice
					#   warning
					#   error
					#   log
					#   fatal
					#   panic (effectively off)

log_min_duration_statement = 5000	# -1 is disabled, 0 logs all statements
					# and their durations, > 0 logs only
					# statements running at least this number
					# of milliseconds

track_functions = pl			# none, pl, all

track_activity_query_size = 4096   # max statement length in pg_stat_activity

EOF

psql -U postgres -c "create extension if not exists pg_stat_statements;" 2>/dev/null

