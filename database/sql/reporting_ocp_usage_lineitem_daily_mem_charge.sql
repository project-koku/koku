-- Calculate and update the OCP Memory usage charge
UPDATE reporting_ocpusagelineitem_daily_summary SET pod_charge_memory_gigabytes=GREATEST(pod_usage_memory_gigabytes*'{mem_rate}', pod_request_memory_gigabytes*'{mem_rate}');
