"""
Pipeline — orchestrates the 5 agents and yields Server-Sent Events (SSE).
"""
from __future__ import annotations
import json
import logging
from typing import AsyncIterator

from . import decomposer
from . import explorer
from . import planner
from . import fetcher
from . import synthesizer
import core

log = logging.getLogger(__name__)


def _sse_event(event_type: str, data: str) -> dict:
    """Return an event dict to be queued."""
    return {"type": event_type, "data": data}


async def run_analysis(
    repo_info: dict,
    query: str = "__analysis__",
    chat_history: list[dict] | None = None,
) -> AsyncIterator[dict]:
    """
    Runs the multi-agent pipeline and yields SSE chunks.
    Event types:
      - 'status': progress messages for UI (e.g., "🧠 Entendendo intenção...")
      - 'token': LLM text chunks
      - 'error': error message
      - 'done': pipeline finished
    """
    full_name = repo_info["full_name"]
    
    try:
        # 1. Base Context
        yield _sse_event("status", "📚 Lendo README e raiz do repositório...")
        readme, base_tree = await core.fetch_repo_context(repo_info)
        
        # 2. Decomposer
        yield _sse_event("status", "🧠 Analisando sua intenção...")
        intent = decomposer.decompose(query, repo_info, base_tree)
        log.info(f"Intent: {intent}")
        
        # 3. Explorer
        yield _sse_event("status", f"🔍 Mapeando diretórios relevantes ({len(intent.target_paths)})...")
        dir_map = await explorer.explore(full_name, intent.target_paths, base_tree)
        
        # 4. Planner
        file_contents = {}
        if intent.needs_file_content:
            yield _sse_event("status", "📋 Selecionando arquivos para leitura...")
            files_to_read = planner.plan(intent, dir_map)
            
            # 5. Fetcher
            if files_to_read:
                yield _sse_event("status", f"📂 Lendo conteúdo de {len(files_to_read)} arquivos...")
                file_contents = await fetcher.fetch_files(full_name, files_to_read)
        
        # 6. Synthesizer
        yield _sse_event("status", "✍️ Gerando resposta...")
        # Tell UI to clear status and prepare for markdown
        yield _sse_event("status", "") 
        
        async for token in synthesizer.synthesize(
            repo_info, intent, dir_map, file_contents, readme, chat_history
        ):
            yield _sse_event("token", token)
            
        yield _sse_event("done", "")
        
    except core.UserFacingError as e:
        log.warning("Pipeline stopped: %s", e)
        yield _sse_event("error", str(e))
    except Exception as e:
        log.exception("Pipeline errored")
        yield _sse_event("error", "Erro inesperado na análise. Veja o log do servidor para detalhes.")
