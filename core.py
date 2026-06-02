"""
core.py — GitHub fetching + Groq LLM logic (UI-agnostic)
"""
import asyncio
import base64
import logging
import os
from datetime import datetime
from typing import AsyncIterator, Optional

import requests
from requests.adapters import HTTPAdapter, Retry
from dotenv import load_dotenv
from groq import AsyncGroq

load_dotenv()

log = logging.getLogger(__name__)


class UserFacingError(RuntimeError):
    """Error that can be shown directly in the UI without a traceback."""


CONFIG = {
    "model": "llama-3.3-70b-versatile", # modelo oficial Groq mais robusto
    "temperature": 0.3,
    "max_tokens": 2048,           # limitado para evitar erro 413 do Groq
    "top_p": 1,
    "readme_preview_chars": 2000, # menos caracteres para economizar tokens
    "search_results": 5,
    "http_timeout": 15,
    "http_retries": 3,
    "output_dir": "analises",
}

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


# ── HTTP session ──────────────────────────────────────────────────────────────

def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=CONFIG["http_retries"],
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session


_http = _build_session()
_groq = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


# ── GitHub helpers ────────────────────────────────────────────────────────────

def _parse_repo_slug(query: str) -> Optional[str]:
    """If query looks like a GitHub URL or owner/repo slug, return 'owner/repo'. Else None."""
    import re
    query = query.strip().rstrip("/")
    # https://github.com/owner/repo  or  github.com/owner/repo
    m = re.match(r"(?:https?://)?github\.com/([^/\s]+/[^/\s]+)", query)
    if m:
        return m.group(1)
    # plain owner/repo  (no spaces, exactly one slash, no dots in path)
    if re.match(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$", query):
        return query
    return None


def get_repo_by_slug(full_name: str) -> Optional[dict]:
    data = _get_json(f"https://api.github.com/repos/{full_name}")
    return data if isinstance(data, dict) and "full_name" in data else None


def search_repositories(query: str) -> list[dict]:
    slug = _parse_repo_slug(query)
    if slug:
        repo = get_repo_by_slug(slug)
        return [repo] if repo else []

    url = (
        "https://api.github.com/search/repositories"
        f"?q={requests.utils.quote(query)}&sort=stars&order=desc"
        f"&per_page={CONFIG['search_results']}"
    )
    try:
        r = _http.get(url, headers=_gh_headers(), timeout=CONFIG["http_timeout"])
        r.raise_for_status()
        return r.json().get("items", [])
    except requests.RequestException as exc:
        log.error("search_repositories: %s", exc)
        return []


def _get_json(url: str) -> Optional[dict | list]:
    try:
        r = _http.get(url, headers=_gh_headers(), timeout=CONFIG["http_timeout"])
        if r.status_code == 200:
            return r.json()
    except requests.RequestException as exc:
        log.debug("_get_json %s: %s", url, exc)
    return None


def get_repo_contents(full_name: str, path: str = "") -> list[dict]:
    data = _get_json(f"https://api.github.com/repos/{full_name}/contents/{path}")
    return data if isinstance(data, list) else []


def get_file_content(full_name: str, file_path: str) -> str:
    data = _get_json(f"https://api.github.com/repos/{full_name}/contents/{file_path}")
    if isinstance(data, dict) and data.get("encoding") == "base64":
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
        except Exception:
            pass
    return ""


def find_readme(full_name: str) -> str:
    for name in ("README.md", "readme.md", "Readme.md", "README.rst", "README.txt"):
        content = get_file_content(full_name, name)
        if content:
            return content
    return ""


# Subpastas que costumam conter código relevante (skills, src, lib, etc.)
_INTERESTING_DIRS = {"src", "lib", "packages", "apps", "agents", "skills",
                     "tools", "plugins", "modules", "core", "components"}


def get_file_tree(full_name: str, max_files: int = 120) -> list[str]:
    """Builds a file tree by exploring root + one level of interesting subdirs."""
    paths: list[str] = []
    root_items = get_repo_contents(full_name, "")

    dirs_to_explore: list[str] = []
    for item in root_items:
        if item.get("type") == "file":
            paths.append(item["path"])
        elif item.get("type") == "dir":
            paths.append(item["path"] + "/")
            if item["name"].lower() in _INTERESTING_DIRS:
                dirs_to_explore.append(item["path"])

    # Explore one level deeper in interesting dirs
    for d in dirs_to_explore:
        if len(paths) >= max_files:
            break
        sub = get_repo_contents(full_name, d)
        for item in sub:
            if len(paths) >= max_files:
                break
            if item.get("type") == "file":
                paths.append(item["path"])
            elif item.get("type") == "dir":
                paths.append(item["path"] + "/")
                # One more level for skill-like dirs
                if item["name"].lower() in _INTERESTING_DIRS:
                    sub2 = get_repo_contents(full_name, item["path"])
                    for i2 in sub2:
                        if len(paths) >= max_files:
                            break
                        paths.append(i2["path"] + ("/" if i2.get("type") == "dir" else ""))

    return paths[:max_files]


# ── LLM streaming (async) ─────────────────────────────────────────────────────

def _llm_params(**overrides) -> dict:
    return {
        "model": CONFIG["model"],
        "temperature": CONFIG["temperature"],
        "max_completion_tokens": CONFIG["max_tokens"],
        "top_p": CONFIG["top_p"],
        **overrides,
    }


def _inject_loop_bypass(messages: list[dict]) -> list[dict]:
    """Appends Groq's bypass tag to the last user message."""
    msgs = [m.copy() for m in messages]
    for i in reversed(range(len(msgs))):
        if msgs[i]["role"] == "user":
            if "[ignoring loop detection]" not in msgs[i]["content"]:
                msgs[i]["content"] += "\n[ignoring loop detection]"
            break
    return msgs


async def _raw_stream(messages: list[dict], **overrides) -> AsyncIterator[str]:
    """Inner generator — calls Groq and yields tokens."""
    if _groq is None:
        raise UserFacingError(
            "GROQ_API_KEY não configurada. Adicione a chave ao arquivo .env e reinicie o servidor."
        )

    completion = await _groq.chat.completions.create(
        messages=messages,
        stream=True,
        **_llm_params(**overrides),
    )
    async for chunk in completion:
        token = chunk.choices[0].delta.content or ""
        if token:
            yield token


async def stream_llm(messages: list[dict], **overrides) -> AsyncIterator[str]:
    """
    Yields text tokens from Groq.
    If the model flags looping content, automatically retries once
    with the `[ignoring loop detection]` bypass tag injected.
    """
    try:
        async for token in _raw_stream(messages, **overrides):
            yield token
    except Exception as exc:
        err = str(exc).lower()
        if "looping" in err or "loop detection" in err:
            log.warning("Groq loop detection triggered — retrying with bypass tag.")
            async for token in _raw_stream(_inject_loop_bypass(messages), **overrides):
                yield token
        elif "expired_api_key" in err or "invalid api key" in err:
            raise UserFacingError(
                "GROQ_API_KEY inválida ou expirada. Gere uma nova chave no console da Groq "
                "e atualize o arquivo .env, depois reinicie o servidor."
            ) from exc
        elif _groq is None:
            raise UserFacingError(
                "GROQ_API_KEY não configurada. Adicione a chave ao arquivo .env e reinicie o servidor."
            ) from exc
        else:
            raise


# ── Analysis ─────────────────────────────────────────────────────────────────

def build_analysis_prompt(repo_info: dict, readme_preview: str, file_list: list[str]) -> str:
    full_name = repo_info["full_name"]
    # Format file tree with indentation for dirs
    tree_lines = []
    for p in file_list:
        depth = p.count("/") - (1 if p.endswith("/") else 0)
        indent = "  " * depth
        name = p.rstrip("/").split("/")[-1] + ("/" if p.endswith("/") else "")
        tree_lines.append(f"{indent}{name}")
    file_tree = "\n".join(tree_lines) or "(nenhum arquivo encontrado)"

    return f"""Você é um engenheiro de software sênior. Analise o repositório GitHub abaixo em **português**, de forma estruturada e técnica.

## Repositório
- **Nome:** {full_name}
- **Descrição:** {repo_info.get('description') or 'Não informada'}
- **Linguagem:** {repo_info.get('language') or 'desconhecida'}
- **Estrelas:** {repo_info.get('stargazers_count', 0):,}
- **Tópicos:** {', '.join(repo_info.get('topics', [])) or 'nenhum'}

## Árvore de arquivos (até 120 entradas)
```
{file_tree}
```

## README (prévia — até {CONFIG['readme_preview_chars']} chars)
{readme_preview or 'Não disponível'}

## Estruture a análise com:
1. **Resumo** – objetivo e proposta de valor
2. **Arquitetura** – organização real dos módulos (baseada na árvore acima, sem inventar)
3. **Funcionalidades** – o que faz de relevante
4. **Stack** – linguagens, frameworks, dependências
5. **Pontos fortes / a melhorar** – tabela comparativa
6. **Conclusão** – veredicto e recomendações

⚠️ IMPORTANTE: Use APENAS informações presentes na árvore de arquivos e no README acima. Não invente arquivos, pastas, skills ou funcionalidades que não aparecem nesses dados.
Use Markdown com tabelas onde adequado.
"""


def build_chat_system(repo_info: dict, analysis: str) -> str:
    return (
        f"Você é um assistente técnico especialista em repositórios GitHub. "
        f"Acabou de analisar **{repo_info['full_name']}**.\n\n"
        f"Análise inicial:\n{analysis}"
    )


def save_analysis(repo_info: dict, analysis_text: str) -> str:
    """Saves analysis to Markdown. Returns the file path."""
    os.makedirs(CONFIG["output_dir"], exist_ok=True)
    clean_name = repo_info["full_name"].replace("/", "-").replace(" ", "_")
    filepath = os.path.join(CONFIG["output_dir"], f"{clean_name}.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = "\n".join([
        f"# Análise: {repo_info['full_name']}",
        f"**Data:** {timestamp}  ",
        f"**URL:** {repo_info.get('html_url', 'N/A')}  ",
        f"**Estrelas:** {repo_info.get('stargazers_count', 0):,}  ",
        f"**Linguagem:** {repo_info.get('language', '?')}  ",
        "", "---", "",
    ])
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(header)
        fh.write(analysis_text)
    return filepath


async def fetch_repo_context(repo_info: dict) -> tuple[str, list[str]]:
    """Runs blocking GitHub calls in a thread pool to not block the event loop."""
    loop = asyncio.get_event_loop()
    full_name = repo_info["full_name"]
    file_list, readme = await asyncio.gather(
        loop.run_in_executor(None, get_file_tree, full_name),
        loop.run_in_executor(None, find_readme, full_name),
    )
    readme_preview = readme[: CONFIG["readme_preview_chars"]]
    return readme_preview, file_list


def validate_env() -> tuple[bool, str]:
    """Returns (ok, warning_message)."""
    if not GROQ_API_KEY:
        return False, "GROQ_API_KEY não configurado no .env"
    if GROQ_API_KEY == "your_groq_api_key_here":
        return False, "GROQ_API_KEY ainda está com o valor de exemplo no .env"
    warn = "" if GITHUB_TOKEN else "GITHUB_TOKEN ausente — limite de 60 req/h na API pública"
    return True, warn
