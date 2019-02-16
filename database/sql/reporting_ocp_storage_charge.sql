-- Calculate and update the OCP Storage usage charge
UPDATE reporting_ocpstoragelineitem_daily_summary SET persistentvolumeclaim_charge_gb_month = '{storage_charge}' WHERE id = '{line_id}';
