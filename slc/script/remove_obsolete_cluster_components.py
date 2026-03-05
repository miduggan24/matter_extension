#!/usr/bin/env python3
"""
Remove cluster components from slc/component/matter-clusters when the
corresponding cluster no longer exists in third_party/matter_sdk/src/app/clusters.
Matches Confluence: "If a cluster is removed ... Manually remove the same
component from slc/component/matter-clusters" (automated).
Run after gen_cluster_components.py.
"""

import os
import pathlib

root = str(pathlib.Path(os.path.realpath(__file__)).parent.parent.parent)
os.chdir(root)

CLUSTER_DIR = pathlib.Path("third_party/matter_sdk/src/app/clusters")
COMPONENT_DIR = pathlib.Path("slc/component/matter-clusters")


def _valid_cluster_names():
    """Set of clusternames that have a corresponding dir in the SDK."""
    valid = set()
    if not CLUSTER_DIR.exists():
        return valid
    for subdir in os.listdir(CLUSTER_DIR):
        subdir_path = CLUSTER_DIR / subdir
        if not subdir_path.is_dir():
            continue
        component_name = subdir.replace("-", "_")
        clustername = component_name.replace("_server", "").replace("_client", "")
        valid.add(clustername)
        if "client" in component_name:
            valid.add(clustername + "_client")
    return valid


def main():
    if not COMPONENT_DIR.exists():
        print("Component dir not found:", COMPONENT_DIR)
        return 0
    valid = _valid_cluster_names()
    removed = []
    for f in os.listdir(COMPONENT_DIR):
        if not f.endswith(".slcc") or not f.startswith("matter_"):
            continue
        name = f[7:-5]  # strip "matter_" and ".slcc"
        if name not in valid:
            path = COMPONENT_DIR / f
            path.unlink()
            removed.append(f)
    if removed:
        print("Removed obsolete cluster components:", ", ".join(sorted(removed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
