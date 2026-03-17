#!/usr/bin/env python3
"""
Sync include file_list entries under third_party/matter_sdk to match the SDK
directory contents. For each such include path, file_list is set to the
headers present on disk so removed/renamed headers are
dropped and new ones picked up without manual edits.
Run as part of the matter_sdk submodule update workflow (after submodule init).
"""

import pathlib
import yaml

root = pathlib.Path(__file__).resolve().parent.parent.parent
SDK_PREFIX = "third_party/matter_sdk"
COMPONENT_DIR = root / "slc" / "component"
HEADER_SUFFIXES = (".h", ".hpp", ".ipp")

def _norm_path(p):
    return str(p).replace("\\", "/")

def _discover_headers(dir_path):
    """Return sorted list of header paths in dir_path top-level and codegen/ if present."""
    if not dir_path.is_dir():
        return []
    names = sorted(
        f.name for f in dir_path.iterdir()
        if f.is_file() and f.suffix.lower() in HEADER_SUFFIXES
    )
    codegen_dir = dir_path / "codegen"
    if codegen_dir.is_dir():
        names.extend(
            "codegen/" + f.name for f in sorted(codegen_dir.iterdir())
            if f.is_file() and f.suffix.lower() in HEADER_SUFFIXES
        )
    return sorted(names)

def _file_list_equal(a, b):
    """Compare file_list"""
    def names(lst):
        return [e.get("path", e) if isinstance(e, dict) else e for e in lst]
    return names(a) == names(b)

def sync_slcc(slcc_path):
    """For include paths with file_list, set file_list to discovered headers. Return True if changed."""
    try:
        content = slcc_path.read_text(encoding="utf-8")
    except OSError:
        return False
    data = yaml.safe_load(content)
    if not data or "include" not in data:
        return False
    changed = False
    for inc in data["include"]:
        if not isinstance(inc, dict):
            continue
        path_val = inc.get("path")
        if not path_val or not _norm_path(path_val).startswith(SDK_PREFIX):
            continue
        full_dir = root / path_val
        if not full_dir.is_dir():
            continue
        discovered = _discover_headers(full_dir)
        new_list = [{"path": f} for f in discovered]
        current = inc.get("file_list")
        if current is None:
            continue
        if not _file_list_equal(new_list, current):
            inc["file_list"] = new_list
            changed = True
    if not changed:
        return False
    with open(slcc_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return True

def main():
    if not (root / SDK_PREFIX).exists():
        print("matter_sdk not found; skip syncing include file_lists")
        return 0
    changed_count = 0
    for slcc in sorted(COMPONENT_DIR.rglob("*.slcc")):
        if sync_slcc(slcc):
            changed_count += 1
            print("Synced:", slcc.relative_to(root))
    if changed_count:
        print("Synced SDK include file_lists in", changed_count, "component(s).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
