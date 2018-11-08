-- Calculate and update the OCP CPU usage charge
UPDATE reporting_ocpusagelineitem_daily_summary SET pod_charge_cpu_cores=GREATEST(pod_usage_cpu_core_hours*'{cpu_rate}', pod_request_cpu_core_hours*'{cpu_rate}');
