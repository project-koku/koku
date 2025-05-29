CREATE TABLE IF NOT EXISTS {{schema | sqlsafe}}.{{temp_table | sqlsafe}} (
  vm_name TEXT,
  node TEXT,
  pvc_name TEXT,
  cpu_request FLOAT,
  mem_request FLOAT
);
