#
# Copyright 2026 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Mapping of operator commit SHAs to human readable version strings.

The koku-metrics-operator (upstream) and costmanagement-metrics-operator (downstream)
send a git commit SHA as the `version` field in their manifest payloads. This module
maps those commits to release versions.

Update this after every operator release:
https://github.com/project-koku/koku-metrics-operator/releases
"""
from packaging.version import Version

OPERATOR_RELEASES = [
    # (version, downstream_commit, upstream_commit)
    ("4.3.1", "ec11d7bddaa8ea3a980236b364780fed0cd2cb0f", "ec6bc48a434b78e21681233585fcb0f3b2dba223"),
    ("4.3.0", "078c8d706ff3bc4198d2364c6fad1e3f7074cbe8", "c78ce96835e6dd4430e9f75cc23e914af2b3706b"),
    ("4.2.0", "d0bc2c257b15ad2f6d73b4e77badbd9706d1a694", "d973ee0dcaa457040a619340c1e781a6e7be547f"),
    ("4.1.0", "c7361974c47522d07a4810fdada6be4f39ecd75d", "0f4d67606199148fd2ea04392d00a32d1387be84"),
    ("4.0.0", "e53f9db7c6e7f995b6aa6100a580dae74162ac3c", "0dbe2ce263a19e05935023c46d20692213fdef90"),
    ("3.3.2", "8e957a5b174639642809df0317b39593532d6fb7", "1dd2f05c51daa7487ea53b1f3f4894316b1759e1"),
    ("3.3.1", "6b4d72a4a629527c1de086b416faf6d226fe587a", "b0731873d0c54aa1d016b8b3463b29c23c9e852c"),
    ("3.3.0", "8c10aa090b2be3d2aea7553ce2cb62e78844ce6f", "1650a9fa9f353efee534dde6030ece40e6a9a1ee"),
    ("3.2.1", "212f944b3b1d7cfbf6e48a63c4ed74bfe942bbe1", "631434d278be57cfedaa5ad0000cb3a3dfb69a76"),
    ("3.2.0", "9d463e92ba69d82513d8ec53edc5242658623840", "06f3ed1c48b889f64ecec09e55f0bd7c2f09fe54"),
    ("3.1.0", "e3ab976307639acff6cc86e25f90f242c45d7210", "b3525a536a402d5bed9b5bbd739fb6a89c8e92e0"),
    ("3.0.1", "b5a2c05255069215eb564dcc5c4ec6ca4b33325d", "8737fb075bdbd63c02e82e6f89056380e9c1e6b6"),
    ("3.0.0", "47ddcdbbdf3e445536ea3fa8346df0dac3adc3ed", "3a6df53f18e574286a1666e1d26586dc729f0568"),
    ("2.0.0", "5806b175a7b31e6ee112c798fa4222cc652b40a6", "26502d500672019af5c11319b558dec873409e38"),
    ("1.2.0", "e3450f6e3422b6c39c582028ec4ce19b8d09d57d", "2acd43ccec2d6fe6ec292aece951b3cf0b869071"),
    ("1.1.9", "61099eb07331b140cf66104bc1056c3f3211c94e", "ebe8dab6aebfeacf9a3428d66cc8be7da682c2ad"),
    ("1.1.8", "6d38c76be52e5981eaf19377a559dc681f1be405", "ccc78b4fd4b63a6cb1516574d5e38a9b1078ea16"),
    ("1.1.7", "0159d5e55ce6a5a18f989e6f04146f47983ebdf3", "2003f0ea23efc49b7ba1337a16b1c90c6899824b"),
    ("1.1.6", "2a702a3aac89f724a08b08650b77a0bd33f5b5e5", "45cc7a72ced124a267acf0976d90504f134e1076"),
    ("1.1.5", "f8d1f7c5d8685f758ecc36a14aca3b6b86614613", "2c52da1481d0c90099e130f6989416cdd3cd7b5a"),
    ("1.1.4", "77ec351f8d332796dc522e5623f1200c2fab4042", "12b9463a9501f8e9acecbfa4f7e7ae7509d559fa"),
    ("1.1.3", "084bca2e1c48caab18c237453c17ceef61747fe2", "3430d17b8ad52ee912fc816da6ed31378fd28367"),
    ("1.1.0", "6f10d07e3af3ea4f073d4ffda9019d8855f52e7f", None),
    ("1.0.0", "fd764dcd7e9b993025f3e05f7cd674bb32fad3be", None),
    # upstream-only older releases
    ("1.1.2", None, "02f315aa5a7f0bf5adecd3668b0a769799b54be8"),
    ("1.1.1", None, "7c413e966e2ec0a709f5a25cbf5a487c646306d1"),
    ("0.9.8", None, "f73a992e7b2fc19028b31c7fb87963ae19bba251"),
    ("0.9.7", None, "d37e6d6fd90d65b0d6794347f5fe00a472ce9d33"),
    ("0.9.6", None, "1019682a6aa1eeb7533724b07d98cfb54dbe0e94"),
    ("0.9.5", None, "513e7dffddb6ecc090b9e8f20a2fba2fe8ec6053"),
    ("0.9.4", None, "eaef8ea323b3531fa9513970078a55758afea665"),
    ("0.9.2", None, "4f1cc5580da20a11e6dfba50d04d8ae50f2e5fa5"),
    ("0.9.1", None, "0419bb957f5cdfade31e26c0f03b755528ec0d7f"),
    ("0.9.0", None, "bfdc1e54e104c2a6c8bf830ab135cf56a97f41d2"),
]

OPERATOR_VERSIONS: dict[str, str] = {}
for _ver, _ds_commit, _us_commit in OPERATOR_RELEASES:
    if _ds_commit:
        OPERATOR_VERSIONS[_ds_commit] = f"costmanagement-metrics-operator:{_ver}"
    if _us_commit:
        OPERATOR_VERSIONS[_us_commit] = f"koku-metrics-operator:v{_ver}"

LATEST_OPERATOR_VERSION: str = max(
    (v.split(":")[-1].lstrip("v") for v in OPERATOR_VERSIONS.values()),
    key=Version,
)
