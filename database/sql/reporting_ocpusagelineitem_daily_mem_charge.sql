-- Calculate and update the OCP Memory usage charge
UPDATE reporting_ocpusagelineitem_daily_summary SET pod_charge_memory_gigabytes = '{mem_charge}' WHERE id = '{line_id}';