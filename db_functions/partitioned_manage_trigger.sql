--
-- Copyright 2021 Red Hat Inc.
-- SPDX-License-Identifier: Apache-2.0
--

DROP TRIGGER IF EXISTS tr_partition_manager ON partitioned_tables;
CREATE TRIGGER tr_partition_manager
 AFTER INSERT
    OR DELETE
    OR UPDATE
    ON partitioned_tables
   FOR EACH ROW EXECUTE FUNCTION public . trfn_partition_manager()
;
