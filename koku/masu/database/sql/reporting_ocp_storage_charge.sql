-- Calculate and update the OCP Storage usage charge
UPDATE {{schema | sqlsafe}}.reporting_ocpusagelineitem_daily_summary SET persistentvolumeclaim_charge_gb_month = charge FROM {{temp_table | sqlsafe}} WHERE id = {{temp_table | sqlsafe}}.lineid;
