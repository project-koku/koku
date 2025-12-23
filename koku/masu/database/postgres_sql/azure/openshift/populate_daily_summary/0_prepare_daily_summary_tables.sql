CREATE TABLE IF NOT EXISTS "{{schema}}".managed_azure_openshift_daily_temp
(
    row_uuid VARCHAR,
    usage_start TIMESTAMP,
    resource_id VARCHAR,
    service_name VARCHAR,
    data_transfer_direction VARCHAR,
    instance_type VARCHAR,
    subscription_guid VARCHAR,
    subscription_name VARCHAR,
    resource_location VARCHAR,
    unit_of_measure VARCHAR,
    usage_quantity FLOAT,
    currency VARCHAR,
    pretax_cost FLOAT,
    date TIMESTAMP,
    metername VARCHAR,
    complete_resource_id VARCHAR,
    tags TEXT,
    resource_id_matched BOOLEAN,
    matched_tag VARCHAR,
    source VARCHAR,
    ocp_source VARCHAR,
    year VARCHAR,
    month VARCHAR,
    day VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_azure_daily_temp_source_year_month ON "{{schema}}".managed_azure_openshift_daily_temp (source, ocp_source, year, month);
CREATE INDEX IF NOT EXISTS idx_azure_daily_temp_day ON "{{schema}}".managed_azure_openshift_daily_temp (day);

CREATE TABLE IF NOT EXISTS "{{schema}}".managed_azure_openshift_disk_capacities_temp
(
    resource_id VARCHAR,
    capacity INTEGER,
    usage_start TIMESTAMP,
    ocp_source VARCHAR,
    year VARCHAR,
    month VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_azure_disk_cap_source_year_month ON "{{schema}}".managed_azure_openshift_disk_capacities_temp (ocp_source, year, month);

CREATE TABLE IF NOT EXISTS "{{schema}}".managed_reporting_ocpazurecostlineitem_project_daily_summary_temp
(
    row_uuid VARCHAR,
    cluster_id VARCHAR,
    cluster_alias VARCHAR,
    data_source VARCHAR,
    namespace VARCHAR,
    node VARCHAR,
    persistentvolumeclaim VARCHAR,
    persistentvolume VARCHAR,
    storageclass VARCHAR,
    resource_id VARCHAR,
    usage_start TIMESTAMP,
    usage_end TIMESTAMP,
    service_name VARCHAR,
    data_transfer_direction VARCHAR,
    instance_type VARCHAR,
    subscription_guid VARCHAR,
    subscription_name VARCHAR,
    resource_location VARCHAR,
    unit_of_measure VARCHAR,
    usage_quantity FLOAT,
    currency VARCHAR,
    pretax_cost FLOAT,
    markup_cost FLOAT,
    pod_cost FLOAT,
    project_markup_cost FLOAT,
    pod_effective_usage_cpu_core_hours FLOAT,
    pod_effective_usage_memory_gigabyte_hours FLOAT,
    node_capacity_cpu_core_hours FLOAT,
    node_capacity_memory_gigabyte_hours FLOAT,
    pod_labels TEXT,
    volume_labels TEXT,
    tags TEXT,
    project_rank INTEGER,
    data_source_rank INTEGER,
    matched_tag VARCHAR,
    resource_id_matched BOOLEAN,
    cost_category_id INTEGER,
    source VARCHAR,
    ocp_source VARCHAR,
    year VARCHAR,
    month VARCHAR,
    day VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_azure_summary_temp_source_year_month ON "{{schema}}".managed_reporting_ocpazurecostlineitem_project_daily_summary_temp (source, ocp_source, year, month);
CREATE INDEX IF NOT EXISTS idx_azure_summary_temp_day ON "{{schema}}".managed_reporting_ocpazurecostlineitem_project_daily_summary_temp (day);

CREATE TABLE IF NOT EXISTS "{{schema}}".managed_reporting_ocpazurecostlineitem_project_daily_summary
(
    row_uuid VARCHAR,
    cluster_id VARCHAR,
    cluster_alias VARCHAR,
    data_source VARCHAR,
    namespace VARCHAR,
    node VARCHAR,
    persistentvolumeclaim VARCHAR,
    persistentvolume VARCHAR,
    storageclass VARCHAR,
    resource_id VARCHAR,
    usage_start TIMESTAMP,
    usage_end TIMESTAMP,
    service_name VARCHAR,
    data_transfer_direction VARCHAR,
    instance_type VARCHAR,
    subscription_guid VARCHAR,
    subscription_name VARCHAR,
    resource_location VARCHAR,
    unit_of_measure VARCHAR,
    usage_quantity FLOAT,
    currency VARCHAR,
    pretax_cost FLOAT,
    markup_cost FLOAT,
    pod_cost FLOAT,
    project_markup_cost FLOAT,
    pod_effective_usage_cpu_core_hours FLOAT,
    pod_effective_usage_memory_gigabyte_hours FLOAT,
    node_capacity_cpu_core_hours FLOAT,
    node_capacity_memory_gigabyte_hours FLOAT,
    pod_labels TEXT,
    volume_labels TEXT,
    tags TEXT,
    project_rank INTEGER,
    data_source_rank INTEGER,
    matched_tag VARCHAR,
    resource_id_matched BOOLEAN,
    cost_category_id INTEGER,
    source VARCHAR,
    ocp_source VARCHAR,
    year VARCHAR,
    month VARCHAR,
    day VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_azure_summary_source_year_month ON "{{schema}}".managed_reporting_ocpazurecostlineitem_project_daily_summary (source, ocp_source, year, month);
CREATE INDEX IF NOT EXISTS idx_azure_summary_day ON "{{schema}}".managed_reporting_ocpazurecostlineitem_project_daily_summary (day);
CREATE INDEX IF NOT EXISTS idx_azure_summary_usage_start ON "{{schema}}".managed_reporting_ocpazurecostlineitem_project_daily_summary (usage_start);
