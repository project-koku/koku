-- Calculate and update the OCP Storage usage charge
UPDATE {schema}.reporting_ocpstoragelineitem_daily_summary SET persistentvolumeclaim_charge_gb_month = charge FROM {temp_table} WHERE id = {temp_table}.lineid;
