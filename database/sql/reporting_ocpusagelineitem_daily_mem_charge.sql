-- Calculate and update the OCP Memory usage charge
UPDATE reporting_ocpusagelineitem_daily_summary SET pod_charge_memory_gigabyte_hours = '{mem_charge}' WHERE id = '{line_id}';
