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

DROP TRIGGER IF EXISTS tr_attach_date_range_partition ON partitioned_tables;
CREATE TRIGGER tr_attach_date_range_partition
 AFTER UPDATE OF active
    ON partitioned_tables
   FOR EACH ROW EXECUTE FUNCTION public.trfn_attach_date_range_partition();
