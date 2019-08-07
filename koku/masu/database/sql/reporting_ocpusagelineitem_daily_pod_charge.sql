-- Calculate and update the OCP CPU and memory charge
UPDATE {schema}.reporting_ocpusagelineitem_daily_summary
    SET pod_charge_cpu_core_hours = cpu_temp.charge,
        pod_charge_memory_gigabyte_hours = mem_temp.charge
FROM {cpu_temp} AS cpu_temp
LEFT JOIN {mem_temp} AS mem_temp
    ON cpu_temp.lineid = mem_temp.lineid
WHERE id = mem_temp.lineid
