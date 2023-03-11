--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--

DROP TRIGGER IF EXISTS tr_manage_date_range_partition ON partitioned_tables;
CREATE TRIGGER tr_manage_date_range_partition
 AFTER INSERT
    OR DELETE
    OR UPDATE OF partition_parameters
    ON partitioned_tables
   FOR EACH ROW EXECUTE FUNCTION public . trfn_manage_date_range_partition()
;
