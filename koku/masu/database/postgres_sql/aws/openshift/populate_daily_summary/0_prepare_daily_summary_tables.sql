CREATE TABLE IF NOT EXISTS {{schema | sqlsafe}}.managed_aws_openshift_daily_temp
(
    row_uuid VARCHAR,
    resource_id VARCHAR,
    product_code VARCHAR,
    usage_start TIMESTAMP,
    usage_account_id VARCHAR,
    availability_zone VARCHAR,
    product_family VARCHAR,
    instance_type VARCHAR,
    region VARCHAR,
    unit VARCHAR,
    tags TEXT,
    aws_cost_category TEXT,
    data_transfer_direction VARCHAR,
    usage_amount FLOAT,
    currency_code VARCHAR,
    unblended_cost FLOAT,
    blended_cost FLOAT,
    savingsplan_effective_cost FLOAT,
    calculated_amortized_cost FLOAT,
    resource_id_matched BOOLEAN,
    matched_tag VARCHAR,
    source VARCHAR,
    ocp_source VARCHAR,
    year VARCHAR,
    month VARCHAR,
    day VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_aws_daily_temp_source_year_month ON {{schema | sqlsafe}}.managed_aws_openshift_daily_temp (source, ocp_source, year, month);
CREATE INDEX IF NOT EXISTS idx_aws_daily_temp_day ON {{schema | sqlsafe}}.managed_aws_openshift_daily_temp (day);

CREATE TABLE IF NOT EXISTS {{schema | sqlsafe}}.managed_reporting_ocpawscostlineitem_project_daily_summary_temp
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
    product_code VARCHAR,
    product_family VARCHAR,
    instance_type VARCHAR,
    usage_account_id VARCHAR,
    availability_zone VARCHAR,
    region VARCHAR,
    unit VARCHAR,
    usage_amount FLOAT,
    currency_code VARCHAR,
    unblended_cost FLOAT,
    markup_cost FLOAT,
    blended_cost FLOAT,
    markup_cost_blended FLOAT,
    savingsplan_effective_cost FLOAT,
    markup_cost_savingsplan FLOAT,
    calculated_amortized_cost FLOAT,
    markup_cost_amortized FLOAT,
    pod_cost FLOAT,
    project_markup_cost FLOAT,
    pod_effective_usage_cpu_core_hours FLOAT,
    pod_effective_usage_memory_gigabyte_hours FLOAT,
    node_capacity_cpu_core_hours FLOAT,
    node_capacity_memory_gigabyte_hours FLOAT,
    pod_labels TEXT,
    volume_labels TEXT,
    tags TEXT,
    aws_cost_category TEXT,
    cost_category_id INTEGER,
    project_rank INTEGER,
    data_source_rank INTEGER,
    resource_id_matched BOOLEAN,
    matched_tag VARCHAR,
    source VARCHAR,
    ocp_source VARCHAR,
    year VARCHAR,
    month VARCHAR,
    day VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_aws_summary_temp_source_year_month ON {{schema | sqlsafe}}.managed_reporting_ocpawscostlineitem_project_daily_summary_temp (source, ocp_source, year, month);
CREATE INDEX IF NOT EXISTS idx_aws_summary_temp_day ON {{schema | sqlsafe}}.managed_reporting_ocpawscostlineitem_project_daily_summary_temp (day);

CREATE TABLE IF NOT EXISTS {{schema | sqlsafe}}.managed_reporting_ocpawscostlineitem_project_daily_summary
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
    product_code VARCHAR,
    product_family VARCHAR,
    instance_type VARCHAR,
    usage_account_id VARCHAR,
    account_alias_id INTEGER,
    availability_zone VARCHAR,
    region VARCHAR,
    unit VARCHAR,
    usage_amount FLOAT,
    data_transfer_direction VARCHAR,
    currency_code VARCHAR,
    unblended_cost FLOAT,
    markup_cost FLOAT,
    blended_cost FLOAT,
    markup_cost_blended FLOAT,
    savingsplan_effective_cost FLOAT,
    markup_cost_savingsplan FLOAT,
    calculated_amortized_cost FLOAT,
    markup_cost_amortized FLOAT,
    pod_cost FLOAT,
    project_markup_cost FLOAT,
    pod_labels TEXT,
    tags TEXT,
    aws_cost_category TEXT,
    cost_category_id INTEGER,
    project_rank INTEGER,
    data_source_rank INTEGER,
    resource_id_matched BOOLEAN,
    matched_tag VARCHAR,
    source VARCHAR,
    ocp_source VARCHAR,
    year VARCHAR,
    month VARCHAR,
    day VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_aws_summary_source_year_month ON {{schema | sqlsafe}}.managed_reporting_ocpawscostlineitem_project_daily_summary (source, ocp_source, year, month);
CREATE INDEX IF NOT EXISTS idx_aws_summary_day ON {{schema | sqlsafe}}.managed_reporting_ocpawscostlineitem_project_daily_summary (day);
CREATE INDEX IF NOT EXISTS idx_aws_summary_usage_start ON {{schema | sqlsafe}}.managed_reporting_ocpawscostlineitem_project_daily_summary (usage_start);

CREATE TABLE IF NOT EXISTS {{schema | sqlsafe}}.managed_aws_openshift_disk_capacities_temp
(
    resource_id VARCHAR,
    capacity INTEGER,
    usage_start TIMESTAMP,
    ocp_source VARCHAR,
    year VARCHAR,
    month VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_aws_disk_cap_source_year_month ON {{schema | sqlsafe}}.managed_aws_openshift_disk_capacities_temp (ocp_source, year, month);
