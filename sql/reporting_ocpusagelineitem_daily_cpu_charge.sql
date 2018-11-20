-- Calculate and update the OCP CPU usage charge
UPDATE reporting_ocpusagelineitem_daily_summary SET pod_charge_cpu_cores = '{cpu_charge}' WHERE id = '{line_id}';