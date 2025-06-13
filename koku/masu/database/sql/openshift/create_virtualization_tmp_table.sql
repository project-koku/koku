CREATE TABLE IF NOT EXISTS {{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}} (
  vm_name TEXT,
  node TEXT,
  pvc_name TEXT,
  cpu_request FLOAT,
  mem_request FLOAT
);

CREATE INDEX IF NOT EXISTS idx_tmp_virt_vm_name_{{uuid | sqlsafe}}
ON {{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}} (vm_name);
CREATE INDEX IF NOT EXISTS idx_tmp_virt_pvc_name_{{uuid | sqlsafe}}
ON {{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}} (pvc_name);
CREATE INDEX IF NOT EXISTS idx_tmp_virt_node_{{uuid | sqlsafe}}
ON {{schema | sqlsafe}}.tmp_virt_{{uuid | sqlsafe}} (node);
