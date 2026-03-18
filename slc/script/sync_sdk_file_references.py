#!/usr/bin/env python3
"""
When the matter_sdk submodule is updated, some files may be deleted, renamed, or
moved. This script finds component files that still point at those old paths
and fixes them. Remove the reference if the file was deleted, or update it to the
new path if it was renamed or moved.
"""

import os
import pathlib
import re
import subprocess
import yaml

root = pathlib.Path(__file__).resolve().parent.parent.parent
SDK_PREFIX = "third_party/matter_sdk"
SDK_DIR = root / SDK_PREFIX
COMPONENT_DIR = root / "slc" / "component"

def _norm(p):
    """Normalize path separators to forward slashes for consistent comparison."""
    return str(p).replace("\\", "/")

def collect_refs():
    """
    Scan all component files and find every reference to a path under matter_sdk.
    For each one we get which file it's in, the full path, whether it's a source
    or include, the line number, and how the path is written in the file (for include
    file_list entries this is just the filename relative to that include dir).
    """
    path_line_re = re.compile(r"^\s*-\s*path:\s*(.+)$")
    for slcc_path in sorted(COMPONENT_DIR.rglob("*.slcc")):
        try:
            content = slcc_path.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = content.splitlines(keepends=True)
        try:
            data = yaml.safe_load(content)
        except Exception:
            continue
        if not data:
            continue

        # Collect source entries that point into the SDK
        for src in data.get("source") or []:
            if not isinstance(src, dict):
                continue
            path_val = src.get("path")
            if not path_val or not _norm(path_val).startswith(SDK_PREFIX):
                continue
            full_path = _norm(path_val)
            for li, line in enumerate(lines):
                m = path_line_re.match(line.rstrip("\n\r"))
                if m and _norm(m.group(1).strip()) == full_path:
                    yield (slcc_path, full_path, "source", li, path_val)
                    break

        # Collect include blocks: match each file_list path to its include dir and line
        current_include_path = None
        include_block_indent = None
        in_file_list = False
        file_list_indent = None
        for li, line in enumerate(lines):
            stripped = line.strip()
            leading = line[: len(line) - len(line.lstrip())]
            if not in_file_list and stripped.startswith("- path:") and "file_list" not in stripped:
                m = path_line_re.match(line.rstrip("\n\r"))
                if m:
                    p = m.group(1).strip()
                    if _norm(p).startswith(SDK_PREFIX):
                        current_include_path = _norm(p).rstrip("/")
                        include_block_indent = leading
                    else:
                        current_include_path = None
                        include_block_indent = None
                continue
            if current_include_path and "file_list:" in line:
                in_file_list = True
                file_list_indent = leading
                continue
            if in_file_list and current_include_path:
                m = path_line_re.match(line.rstrip("\n\r"))
                if m:
                    # Deeper indent = real file_list entry; same indent = next include block
                    if include_block_indent is not None and len(leading) > len(include_block_indent):
                        fl_path = m.group(1).strip()
                        full_path = current_include_path + "/" + fl_path.lstrip("/")
                        yield (slcc_path, full_path, "include", li, fl_path)
                    else:
                        # This line starts the next include block, so switch context
                        in_file_list = False
                        p = m.group(1).strip()
                        if _norm(p).startswith(SDK_PREFIX):
                            current_include_path = _norm(p).rstrip("/")
                            include_block_indent = leading
                        else:
                            current_include_path = None
                            include_block_indent = None
                else:
                    if stripped and (len(leading) <= len(file_list_indent or "")):
                        in_file_list = False
            elif current_include_path and stripped.startswith("- path:") and "file_list" not in stripped:
                in_file_list = False


def _git_show_rename(sdk_dir, commit, rel_path):
    """
    Look at the given commit in the SDK repo. If it renamed rel_path to something
    else, return that new path (relative to repo root). Otherwise return None.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(sdk_dir), "show", "--name-status", "--format=", commit],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if out.returncode != 0:
        return None
    rel_norm = _norm(rel_path)
    for line in out.stdout.strip().split("\n"):
        line = line.strip()
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0].startswith("R"):
            old_p, new_p = _norm(parts[1].strip()), _norm(parts[2].strip())
            if old_p == rel_norm:
                return new_p
    return None


def git_follow(sdk_dir, rel_path):
    """
    Ask git what happened to this path in the SDK repo. Returns:
    - ("D", None) if the file was deleted
    - ("R", new_path) if it was renamed or moved (new_path is where it went)
    - (None, None) if we can't find any history for it

    When git only says "deleted", we look at that same commit for a rename line
    so we can get the new path.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(sdk_dir), "log", "-1", "--follow", "--name-status", "--", rel_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None, None
    if out.returncode != 0 or not out.stdout.strip():
        return None, None

    # Parse the commit hash from the log output
    commit = None
    for line in out.stdout.strip().split("\n"):
        line = line.strip()
        if line.startswith("commit "):
            commit = line.split()[1]
            break

    for line in reversed(out.stdout.strip().split("\n")):
        line = line.strip()
        if not line or line.startswith("commit") or line.startswith("Author") or line.startswith("Date"):
            continue
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0].startswith("R"):
            return "R", parts[2].strip()
        if len(parts) >= 1 and parts[0] == "D":
            if commit:
                new_rel = _git_show_rename(sdk_dir, commit, rel_path)
                if new_rel:
                    return "R", new_rel
            return "D", None
    return None, None

def rel_path(full_path):
    """Strip the matter_sdk prefix so we have a path relative to the SDK repo root."""
    p = _norm(full_path)
    if p.startswith(SDK_PREFIX + "/"):
        return p[len(SDK_PREFIX) + 1 :]
    return p

def dir_of(full_path):
    """Return the directory part of the path (still including the SDK prefix)."""
    p = _norm(full_path)
    if "/" in p:
        return p.rsplit("/", 1)[0]
    return ""

def same_dir(old_full, new_full):
    """True if both paths live in the same directory (so we can do a simple replace)."""
    old_dir = dir_of(old_full)
    new_dir = dir_of(new_full)
    return old_dir == new_dir

def plan_actions():
    """
    Find every broken SDK reference and decide what to do: remove the line, replace
    the path in place (same-dir rename), or move the entry to another include block
    (file moved to a different dir). Yields one (action, slcc_path, line_idx, ...) per fix.
    """
    if not SDK_DIR.is_dir() or not (SDK_DIR / ".git").exists():
        return
    actions_remove = []
    actions_replace = []  # same-dir rename: (slcc, line_idx, new_filename)
    actions_move = []     # different dir: (slcc, line_idx, new_include_dir, new_filename)
    refs = list(collect_refs())
    for slcc_path, full_path, kind, line_idx, display_path in refs:
        abs_path = root / full_path
        if abs_path.exists():
            continue
        rp = rel_path(full_path)
        status, new_rel = git_follow(SDK_DIR, rp)
        if status == "D":
            actions_remove.append((slcc_path, line_idx, display_path))
            continue
        if status == "R" and new_rel:
            new_full = SDK_PREFIX + "/" + new_rel
            if same_dir(full_path, new_full):
                new_display = new_rel.split("/")[-1]
                actions_replace.append((slcc_path, line_idx, display_path, new_display))
            else:
                new_dir = dir_of(new_full)
                new_display = new_rel.split("/")[-1]
                actions_move.append((slcc_path, line_idx, display_path, new_dir, new_display))

    # Avoid duplicate actions for the same line, then yield
    seen = set()
    for a in actions_remove:
        k = (a[0], a[1])
        if k not in seen:
            seen.add(k)
            yield ("remove", a[0], a[1], None, None)
    for a in actions_replace:
        k = (a[0], a[1])
        if k not in seen:
            seen.add(k)
            yield ("replace", a[0], a[1], a[3], None)  # new_display
    for a in actions_move:
        k = (a[0], a[1])
        if k not in seen:
            seen.add(k)
            yield ("move", a[0], a[1], a[3], a[4])  # new_dir, new_display

def apply_actions(actions):
    """
    Apply the planned fixes: edit each .slcc file, removing or updating the
    relevant lines. We group by file and process line numbers from bottom to top
    so we don't mess up indices.
    """
    # Group edits by file
    by_slcc = {}
    for action, slcc_path, line_idx, v1, v2 in actions:
        slcc_path = pathlib.Path(slcc_path)
        if slcc_path not in by_slcc:
            by_slcc[slcc_path] = []
        by_slcc[slcc_path].append((action, line_idx, v1, v2))

    for slcc_path, list_ in by_slcc.items():
        lines = slcc_path.read_text(encoding="utf-8").splitlines(keepends=True)
        # Process from bottom to top so line numbers stay valid
        list_.sort(key=lambda x: -x[1])
        for action, line_idx, v1, v2 in list_:
            if action == "remove":
                if 0 <= line_idx < len(lines):
                    lines.pop(line_idx)
            elif action == "replace":
                if 0 <= line_idx < len(lines) and v1:
                    line = lines[line_idx]
                    # Keep the existing indent and "path: ", only change the path value
                    m = re.match(r"^(\s*-\s*path:\s*)(.+)$", line.rstrip("\n\r"))
                    if m:
                        lines[line_idx] = m.group(1) + v1 + "\n"
            elif action == "move":
                if 0 <= line_idx < len(lines) and v1 and v2:
                    lines.pop(line_idx)
                    # Find the include block for the new dir, then add the filename to its file_list
                    in_block = False
                    block_indent = None
                    insert_after = None
                    for i, ln in enumerate(lines):
                        if re.search(r"path:\s*" + re.escape(v1) + r"\s*$", ln.strip()):
                            in_block = True
                            continue
                        if in_block and "file_list:" in ln:
                            continue
                        if in_block and re.match(r"^\s+-\s+path:", ln):
                            if block_indent is None:
                                block_indent = ln[: len(ln) - len(ln.lstrip())]
                            insert_after = i
                        elif in_block and ln.strip() and block_indent is not None and not ln.startswith(block_indent):
                            break
                    if insert_after is not None and block_indent is not None:
                        new_line = block_indent + "- path: " + v2 + "\n"
                        lines.insert(insert_after + 1, new_line)
        slcc_path.write_text("".join(lines), encoding="utf-8")


def main():
    if not SDK_DIR.exists():
        print("matter_sdk not found; skip syncing file references")
        return 0
    if not (SDK_DIR / ".git").exists():
        print("matter_sdk is not a git repo; skip syncing file references")
        return 0
    actions = list(plan_actions())
    if not actions:
        print("No SDK file reference updates needed.")
        return 0
    apply_actions(actions)
    print(f"Updated {len(actions)} SDK file reference(s) in component(s).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
