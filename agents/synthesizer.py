"""
Synthesizer Agent — generates grounded LLM response from real collected data.
"""
from __future__ import annotations
from typing import AsyncIterator
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import core
from .decomposer import Intent


async def synthesize(
    repo_info: dict,
    intent: Intent,
    dir_map: dict[str, list[str]],
    file_contents: dict[str, str],
    readme: str,
    chat_history: list[dict] | None = None,
) -> AsyncIterator[str]:
    """Streams grounded LLM tokens."""
    prompt = _build_prompt(repo_info, intent, dir_map, file_contents, readme)

    if chat_history:
        messages = [m.copy() for m in chat_history]
        # Append current question with fresh context as a new user message
        messages.append({
            "role": "user",
            "content": (
                f"[Contexto coletado sobre {repo_info['full_name']}]\n"
                f"{prompt}\n\n"
                f"[Pergunta]\n{intent.query}"
            ),
        })
    else:
        messages = [{"role": "user", "content": prompt}]

    async for token in core.stream_llm(messages):
        yield token


def _build_prompt(
    repo_info: dict,
    intent: Intent,
    dir_map: dict[str, list[str]],
    file_contents: dict[str, str],
    readme: str,
) -> str:
    full_name = repo_info["full_name"]

    # ── Directory listing ──────────────────────────────────────────────────────
    dir_lines: list[str] = []
    for dir_path, files in dir_map.items():
        dir_lines.append(f"\n📁 {dir_path}/")
        for f in files[:50]:
            depth = f.count("/")
            name = f.rstrip("/").split("/")[-1] + ("/" if f.endswith("/") else "")
            dir_lines.append("  " * depth + name)
    dir_section = "\n".join(dir_lines) or "(sem dados)"

    # ── File contents ──────────────────────────────────────────────────────────
    files_section = ""
    if file_contents:
        parts = [f"\n### `{path}`\n```\n{content}\n```"
                 for path, content in file_contents.items()]
        files_section = "\n".join(parts)

    # ── Full analysis prompt ───────────────────────────────────────────────────
    if intent.intent_type == "full_analysis":
        return f"""Você é um engenheiro de software sênior. Analise o repositório **{full_name}** em português, baseando-se EXCLUSIVAMENTE nos dados reais abaixo.

## Metadados
- Descrição: {repo_info.get('description') or 'N/A'}
- Linguagem: {repo_info.get('language') or 'N/A'}
- Estrelas: {repo_info.get('stargazers_count', 0):,}
- Tópicos: {', '.join(repo_info.get('topics', [])) or 'nenhum'}

## Estrutura real do repositório
```
{dir_section}
```

## Conteúdo de arquivos-chave
{files_section or '(nenhum arquivo lido)'}

## README (prévia)
{readme[:5000] or 'Não disponível'}

## Produza uma análise estruturada com:
1. **Resumo** – objetivo e proposta de valor
2. **Arquitetura** – organização real dos módulos (baseada nos dados acima)
3. **Funcionalidades** – o que o repositório oferece
4. **Stack** – linguagens, frameworks, dependências
5. **Pontos fortes / a melhorar** – tabela comparativa
6. **Conclusão** – veredicto e recomendações

⚠️ Use APENAS as informações dos dados acima. Não invente arquivos, funções ou funcionalidades.
Use Markdown com tabelas onde adequado."""

    # ── Specific question / list_files / architecture ──────────────────────────
    return f"""Você é um assistente técnico especialista no repositório **{full_name}**.

## Dados reais coletados

### Estrutura de diretórios relevantes
```
{dir_section}
```

### Conteúdo dos arquivos relevantes
{files_section or '(nenhum arquivo lido para esta consulta)'}

### README (prévia)
{readme[:3000] or 'Não disponível'}

## Pergunta
{intent.query}

⚠️ Responda de forma direta e proporcional à pergunta:
- Se perguntarem uma **quantidade/contagem** → responda só com o número e uma linha de contexto. Não liste itens.
- Se perguntarem uma **lista** → liste os itens.
- Se perguntarem algo **específico** → responda só o que foi pedido, sem expandir.
Baseie-se EXCLUSIVAMENTE nos dados acima. Se a informação não estiver disponível, diga "não encontrei essa informação nos dados coletados".
Use Markdown onde adequado."""
