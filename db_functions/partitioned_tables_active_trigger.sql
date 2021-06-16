--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--

DROP TRIGGER IF EXISTS tr_attach_date_range_partition ON partitioned_tables;
CREATE TRIGGER tr_attach_date_range_partition
 AFTER UPDATE OF active
    ON partitioned_tables
   FOR EACH ROW EXECUTE FUNCTION public.trfn_attach_date_range_partition();
