"""
Planner Agent — decides which files to read given the intent and directory map.
Pure heuristics, no LLM call.
"""
from __future__ import annotations
from .decomposer import Intent

MAX_FILES = 8

_ENTRY_POINTS = ("index.", "main.", "app.", "__init__", "server.", "cli.")
_DEP_FILES    = ("package.json", "requirements.txt", "pyproject.toml",
                 "go.mod", "Cargo.toml", "Gemfile", "setup.py")


def plan(intent: Intent, dir_map: dict[str, list[str]]) -> list[str]:
    """Return list of file paths to actually read (content fetch)."""
    all_files = _all_files(dir_map)

    if intent.intent_type == "list_files":
        return []   # Don't need content, just the listing

    selected: list[str] = []

    # 1. Always include key files (package.json etc.)
    for kf in intent.key_files:
        if kf in all_files and kf not in selected:
            selected.append(kf)

    if intent.intent_type == "dependencies":
        dep = [f for f in all_files
               if any(f == n or f.endswith("/" + n) for n in _DEP_FILES)]
        return (selected + [f for f in dep if f not in selected])[:MAX_FILES]

    # 2. Entry-point files
    for f in all_files:
        if len(selected) >= MAX_FILES:
            break
        if f in selected:
            continue
        name = f.split("/")[-1].lower()
        if any(name.startswith(ep) for ep in _ENTRY_POINTS):
            selected.append(f)

    # 3. Fill remaining slots sampling broadly
    for f in all_files:
        if len(selected) >= MAX_FILES:
            break
        if f not in selected:
            selected.append(f)

    return selected[:MAX_FILES]


def _all_files(dir_map: dict[str, list[str]]) -> list[str]:
    seen: set[str] = set()
    files: list[str] = []
    for items in dir_map.values():
        for p in items:
            if not p.endswith("/") and p not in seen:
                seen.add(p)
                files.append(p)
    return files
