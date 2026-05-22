"""
Decomposer Agent — understands user intent from query + repo metadata.
Uses heuristics; no LLM call needed.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

# ── Intent patterns ───────────────────────────────────────────────────────────
_SKILL    = re.compile(r"sk+il+|plugin|tool|compet|capabilit", re.I)
_LISTING  = re.compile(r"list|mostr|todos|tudo|all|arquiv|file", re.I)
_ARCH     = re.compile(r"arquitetura|estrutura|architecture|structure|organiz|módulo|module", re.I)
_DEPS     = re.compile(r"depend|library|bibliote|package|requisit|import", re.I)
_SECURITY = re.compile(r"segur|secur|vulnerab|auth|permission|acesso", re.I)

INTERESTING_DIRS = {
    "src", "lib", "packages", "apps", "agents", "skills",
    "tools", "plugins", "modules", "core", "components",
    "services", "api", "routes", "controllers", "models",
}

KEY_FILE_NAMES = [
    "package.json", "pyproject.toml", "requirements.txt", "go.mod",
    "Cargo.toml", "Gemfile", "setup.py", "tsconfig.json",
    "Makefile", "Dockerfile", "docker-compose.yml",
]


@dataclass
class Intent:
    query: str
    intent_type: str        # full_analysis | list_files | architecture | dependencies | specific
    target_paths: list[str] = field(default_factory=list)
    needs_file_content: bool = True
    key_files: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


def decompose(query: str, repo_info: dict, file_tree: list[str]) -> Intent:
    """Return structured Intent based on heuristics."""
    # Initial analysis request (no user query)
    if not query or query == "__analysis__":
        return Intent(
            query=query,
            intent_type="full_analysis",
            target_paths=_find_interesting_dirs(file_tree),
            needs_file_content=True,
            key_files=_find_key_files(file_tree),
        )

    q = query

    if _SKILL.search(q):
        skill_dirs = [p for p in file_tree
                      if p.endswith("/") and any(kw in p.lower() for kw in ("skill", "plugin", "tool", "agent"))]
        return Intent(
            query=q,
            intent_type="list_files",
            target_paths=skill_dirs or _find_interesting_dirs(file_tree),
            needs_file_content=False,
            keywords=["skill", "plugin", "tool"],
        )

    if _LISTING.search(q):
        return Intent(
            query=q,
            intent_type="list_files",
            target_paths=_find_interesting_dirs(file_tree),
            needs_file_content=False,
        )

    if _ARCH.search(q):
        return Intent(
            query=q,
            intent_type="architecture",
            target_paths=_find_interesting_dirs(file_tree),
            needs_file_content=True,
            key_files=_find_key_files(file_tree),
        )

    if _DEPS.search(q):
        dep_files = [f for f in file_tree
                     if any(f == n or f.endswith("/" + n) for n in KEY_FILE_NAMES[:5])]
        return Intent(
            query=q,
            intent_type="dependencies",
            needs_file_content=True,
            key_files=dep_files[:6],
        )

    # Generic specific question
    return Intent(
        query=q,
        intent_type="specific",
        target_paths=_find_interesting_dirs(file_tree),
        needs_file_content=True,
        key_files=_find_key_files(file_tree),
    )


def _find_interesting_dirs(file_tree: list[str]) -> list[str]:
    return [
        p for p in file_tree
        if p.endswith("/") and p.rstrip("/").split("/")[-1].lower() in INTERESTING_DIRS
    ]


def _find_key_files(file_tree: list[str]) -> list[str]:
    result = []
    for name in KEY_FILE_NAMES:
        matches = [p for p in file_tree if p == name or p.endswith("/" + name)]
        result.extend(matches[:1])
    return result[:8]
