"""
Explorer Agent — fetches real directory contents for target paths via GitHub API.
"""
from __future__ import annotations
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import core


async def explore(
    repo_full_name: str,
    target_paths: list[str],
    base_tree: list[str],
    max_items: int = 200,
) -> dict[str, list[str]]:
    """
    Returns {path: [file/dir paths inside]}.
    Explores target_paths two levels deep via GitHub API.
    Falls back to base_tree if no target_paths.
    """
    if not target_paths:
        return {"root": base_tree}

    loop = asyncio.get_event_loop()
    results: dict[str, list[str]] = {}

    async def _fetch_dir(path: str) -> list[str]:
        clean = path.rstrip("/")
        items = await loop.run_in_executor(
            None, core.get_repo_contents, repo_full_name, clean
        )
        collected: list[str] = []
        subdirs: list[str] = []
        for item in items:
            if item.get("type") == "file":
                collected.append(item["path"])
            elif item.get("type") == "dir":
                collected.append(item["path"] + "/")
                subdirs.append(item["path"])

        # One more level
        for sub in subdirs[:6]:
            if len(collected) >= max_items:
                break
            sub_items = await loop.run_in_executor(
                None, core.get_repo_contents, repo_full_name, sub
            )
            for si in sub_items:
                if len(collected) >= max_items:
                    break
                suffix = "/" if si.get("type") == "dir" else ""
                collected.append(si["path"] + suffix)

        return collected

    # Explore all target paths in parallel (max 6)
    tasks = [_fetch_dir(p) for p in target_paths[:6]]
    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    for path, result in zip(target_paths[:6], results_list):
        if isinstance(result, Exception):
            results[path.rstrip("/")] = []
        else:
            results[path.rstrip("/")] = result

    return results
