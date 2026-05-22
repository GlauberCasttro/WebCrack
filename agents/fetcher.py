"""
Fetcher Agent — reads file contents from GitHub in parallel.
"""
from __future__ import annotations
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import core

CHARS_PER_FILE = 500   # previne erro de tokens no Groq


async def fetch_files(
    repo_full_name: str,
    file_paths: list[str],
) -> dict[str, str]:
    """Returns {path: content_preview} for all readable files."""
    if not file_paths:
        return {}

    loop = asyncio.get_event_loop()

    async def _read(path: str) -> tuple[str, str]:
        content = await loop.run_in_executor(
            None, core.get_file_content, repo_full_name, path
        )
        return path, content[:CHARS_PER_FILE]

    results = await asyncio.gather(*[_read(p) for p in file_paths], return_exceptions=True)
    return {
        path: content
        for r in results
        if not isinstance(r, Exception)
        for path, content in [r]
        if content.strip()
    }
