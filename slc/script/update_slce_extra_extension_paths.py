#!/usr/bin/env python3
"""
Update the "# matter_extension paths" block in packages/matter/matter.slce.extra
with paths collected from matter_extension code (excluding third_party).
Confluence: "If new files are added/removed in the matter_extension code,
manually edit ... matter.slce.extra" (automated).
"""

import os
import sys
from pathlib import Path
from typing import List

DEFAULT_ROOTS = [
    "slc",
    "provision",
    "docs",
    "tools",
    "jenkins_integration",
    "silabs_utils",
    "src",
]
EXCLUDE_DIRS = {"third_party", ".git", "__pycache__", "out", "build"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".class")
SLCE_EXTRA = Path("packages/matter/matter.slce.extra")
MARKER = "# matter_extension paths"


def collect_paths(
    root: Path,
    include_dirs: bool,
    exclude_dirs: set,
) -> List[Path]:
    results: List[Path] = []
    root = root.resolve()
    cwd = Path.cwd().resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs and not d.startswith(".")]
        current = Path(dirpath)
        if include_dirs and current.name not in exclude_dirs and not current.name.startswith("."):
            try:
                results.append(current.relative_to(cwd))
            except ValueError:
                pass
        for name in filenames:
            if name.startswith(".") or name.endswith(EXCLUDE_SUFFIXES):
                continue
            p = current / name
            try:
                results.append(p.relative_to(cwd))
            except ValueError:
                pass
    results.sort()
    return results


def main() -> int:
    root_path = Path(__file__).resolve().parent.parent.parent
    os.chdir(root_path)

    all_paths: List[Path] = []
    for root_str in DEFAULT_ROOTS:
        r = Path(root_str)
        if not r.exists() or not r.is_dir():
            continue
        paths = collect_paths(r, include_dirs=False, exclude_dirs=EXCLUDE_DIRS)
        all_paths.extend(paths)

    seen = set()
    unique = []
    for p in all_paths:
        key = str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)

    target = SLCE_EXTRA
    if not target.exists():
        print(f"Error: {target} not found", file=sys.stderr)
        return 1

    text = target.read_text(encoding="utf-8").splitlines()
    new_lines = [f"  - {p}" for p in unique]

    try:
        idx = next(i for i, line in enumerate(text) if line.strip() == MARKER)
    except StopIteration:
        idx = None

    def is_top_level_key(line: str) -> bool:
        ls = line.lstrip()
        if not ls or ls.startswith("#"):
            return False
        return ls.split()[0].endswith(":") and not line.strip().startswith("-")

    if idx is not None:
        end = idx + 1
        while end < len(text) and not is_top_level_key(text[end]):
            end += 1
        updated = text[: idx + 1] + new_lines + text[end:]
    else:
        try:
            gidx = next(i for i, line in enumerate(text) if line.strip() == "git_extra_files:")
        except StopIteration:
            print("Error: git_extra_files: not found, cannot insert block", file=sys.stderr)
            return 2
        block = [f"  {MARKER}"] + new_lines + [""]
        updated = text[:gidx] + block + text[gidx:]

    target.write_text("\n".join(updated) + "\n", encoding="utf-8")
    print(f"Updated {len(unique)} paths under {MARKER} in {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
