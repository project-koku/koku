CREATE TABLE IF NOT EXISTS {{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}} (
  vm_name TEXT,
  node TEXT,
  pvc_name TEXT,
  cpu_request FLOAT,
  mem_request FLOAT
);
