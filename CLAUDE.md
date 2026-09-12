# Ruflo — Claude Code Configuration

## Rules

- Do what has been asked; nothing more, nothing less
- NEVER create files unless absolutely necessary — prefer editing existing files
- NEVER create documentation files unless explicitly requested
- NEVER save working files or tests to root — use `/src`, `/tests`, `/docs`, `/config`, `/scripts`
- ALWAYS read a file before editing it
- NEVER commit secrets, credentials, or .env files
- NEVER add a `Co-Authored-By` trailer to user commits unless this project's `.claude/settings.json` has `attribution.commit` set (#2078). The Claude Code Bash tool may suggest one in its default commit-message template — ignore it. `Co-Authored-By` is semantic authorship attribution under git/GitHub convention; the tool is the facilitator, not a co-author.
- Keep files under 500 lines
- Validate input at system boundaries

## Agent Comms (SendMessage-First Coordination)

Named agents coordinate via `SendMessage`, not polling or shared state.

```
Lead (you) ←→ architect ←→ developer ←→ tester ←→ reviewer
              (named agents message each other directly)
```

### Spawning a Coordinated Team

```javascript
// ALL agents in ONE message, each knows WHO to message next.
// Subagentes JÁ rodam em background — não existe parâmetro `run_in_background`.
Agent({ description: "Research codebase", name: "researcher", subagent_type: "researcher",
  prompt: "Research the codebase. SendMessage findings to 'architect'." })
Agent({ description: "Design solution", name: "architect", subagent_type: "system-architect",
  prompt: "Wait for 'researcher'. Design solution. SendMessage to 'coder'." })
Agent({ description: "Implement", name: "coder", subagent_type: "coder",
  prompt: "Wait for 'architect'. Implement it. SendMessage to 'tester'." })
Agent({ description: "Write tests", name: "tester", subagent_type: "tester",
  prompt: "Wait for 'coder'. Write tests. SendMessage results to 'reviewer'." })
Agent({ description: "Review", name: "reviewer", subagent_type: "reviewer",
  prompt: "Wait for 'tester'. Review code quality and security." })

// Kick off the pipeline
SendMessage({ to: "researcher", message: "[task context]" })
```

> Este é o `Agent` **nativo do Claude Code** — ele executa de verdade.
> Não confundir com `agent_spawn` do ruflo, que só registra.

### Patterns

| Pattern | Flow | Use When |
|---------|------|----------|
| **Pipeline** | A → B → C → D | Sequential dependencies (feature dev) |
| **Fan-out** | Lead → A, B, C → Lead | Independent parallel work (research) |
| **Supervisor** | Lead ↔ workers | Ongoing coordination (complex refactor) |

### Rules

- ALWAYS name agents — `name: "role"` makes them addressable
- ALWAYS include comms instructions in prompts — who to message, what to send
- Spawn ALL agents in ONE message (subagentes já rodam em background por padrão)
- After spawning: STOP, tell user what's running, wait for results
- NEVER poll status — agents message back or complete automatically

## Swarm & Routing

> **O swarm do ruflo NÃO executa agentes.** Verificado no código-fonte
> (`@claude-flow/cli/dist/src/mcp-tools/agent-tools.js`, ~L270-320): `agent_spawn`
> grava o id num JSON, adiciona um nó no grafo e retorna — nenhuma chamada de LLM,
> nenhum processo. `swarm_status` devolve `"running"` com `taskCount: 0`.
> A própria resposta da tool diz para executar por fora.
>
> **Quem executa é o `Agent` nativo do Claude Code.** Use `swarm_init`/`agent_spawn`
> apenas se quiser o registro de custo/estado por cima — nunca como executor.

### Config (só afeta o registro, não a execução)
- **Topology**: hierarchical-mesh
- **Max Agents**: 15
- **Memory**: hybrid

### Agent Routing

| Task | Agents | Topology |
|------|--------|----------|
| Bug Fix | researcher, coder, tester | hierarchical |
| Feature | architect, coder, tester, reviewer | hierarchical |
| Refactor | architect, coder, reviewer | hierarchical |
| Performance | perf-engineer, coder | hierarchical |
| Security | security-architect, auditor | hierarchical |

### When to Swarm
- **YES**: 3+ files, new features, cross-module refactoring, API changes, security, performance
- **NO**: single file edits, 1-2 line fixes, docs updates, config changes, questions

### 3-Tier Model Routing

| Tier | Handler | Use Cases |
|------|---------|-----------|
| 1 | ~~Codemod determinístico~~ | **Indisponível** — ver nota |
| 2 | Haiku | Simple tasks, low complexity |
| 3 | Sonnet/Opus | Architecture, security, complex reasoning |

> **Tier 1 não funciona aqui, por dois motivos independentes:**
> 1. `hooks_codemod` só transforma `javascript|typescript|jsx|tsx` — este projeto é Python.
> 2. Está quebrado mesmo em JS: `engine.js` importa `typescript` em runtime, mas o
>    `@claude-flow/cli` declara esse pacote em `devDependencies`, que o npm não instala
>    em install global. Erro: `Cannot find package 'typescript'`.
>
> Para transformações mecânicas em Python, use `Edit`/`sed` diretamente.

## Memory & Learning

> **A busca semântica só funciona em inglês.** O embedding é `all-MiniLM-L6-v2`,
> modelo monolíngue, fixado no código (`config.model ?? 'all-MiniLM-L6-v2'`) sem
> chave de config nem env var que o sobrescreva no caminho usado pela memória.
>
> Medido: em português os scores colapsam (0.69 / 0.68 / 0.67 — margem 0.02) e a
> entrada correta some do top-3; em inglês separam (0.69 / 0.61 / 0.52 — margem 0.17)
> e acertam em 1º. **Grave em inglês o que precisar ser encontrado depois.**
>
> `memory_delete` é soft-delete: some da busca, mas a linha permanece no SQLite.

### Before Any Task
```bash
npx @claude-flow/cli@latest memory search --query "[task keywords]" --namespace patterns
npx @claude-flow/cli@latest hooks route --task "[task description]"
```

### After Success
```bash
npx @claude-flow/cli@latest memory store --namespace patterns --key "[name]" --value "[what worked]"
npx @claude-flow/cli@latest hooks post-task --task-id "[id]" --success true --store-results true
```

### MCP Tools (use `ToolSearch("keyword")` to discover)

| Category | Key Tools |
|----------|-----------|
| **Memory** | `memory_store`, `memory_search`, `memory_search_unified` |
| **Bridge** | `memory_import_claude`, `memory_bridge_status` |
| **Swarm** | `swarm_init`, `swarm_status`, `swarm_health` |
| **Agents** | `agent_spawn`, `agent_list`, `agent_status` |
| **Hooks** | `hooks_route`, `hooks_post-task`, `hooks_worker-dispatch` |
| **Security** | `aidefence_scan`, `aidefence_is_safe`, `aidefence_has_pii` — **só detecta inglês** (ver nota) |
| **Hive-Mind** | `hive-mind_init`, `hive-mind_consensus`, `hive-mind_spawn` |

### Background Workers

| Worker | When |
|--------|------|
| `audit` | After security changes |
| `optimize` | After performance work |
| `testgaps` | After adding features |
| `map` | Every 5+ file changes |
| `document` | After API changes |

```bash
npx @claude-flow/cli@latest hooks worker dispatch --trigger audit
```

## Ruflo — o que realmente funciona (medido em 2026-09-09)

| Capacidade | Estado | Observação |
|---|---|---|
| `memory_store` / `memory_search` | ✅ funciona | **só em inglês** — ver nota em Memory |
| `aidefence_*` (prompt injection, PII) | ⚠️ parcial | regex **só em inglês**; PT passa como `safe:true` |
| `analyze_diff` / `analyze_file-risk` | ✅ funciona | agnóstico de linguagem |
| `hooks_route` | ⚠️ fraco | cai em `keyword-fallback`; `patternsLearned: 0` |
| `swarm_*` / `agent_spawn` | ⚠️ só registro | **não executa** — ver Swarm & Routing |
| `hooks_codemod` | ❌ quebrado | falta `typescript`; e é JS-only |

**Regra prática:** use o ruflo para *memória* e *scan de conteúdo não confiável*.
Para executar trabalho, use o `Agent` nativo. Para transformar código, use `Edit`.

Dois stores distintos, não confundir:
- `.claude-flow/data/auto-memory-store.json` — hooks de auto-memory (JSON)
- `.swarm/memory.db` — tools MCP `memory_*` (SQLite + HNSW)

## Agents

**Core**: `coder`, `reviewer`, `tester`, `planner`, `researcher`
**Architecture**: `system-architect`, `backend-dev`, `mobile-dev`
**Security**: `security-architect`, `security-auditor`
**Performance**: `performance-engineer`, `perf-analyzer`
**Coordination**: `hierarchical-coordinator`, `mesh-coordinator`, `adaptive-coordinator`
**GitHub**: `pr-manager`, `code-review-swarm`, `issue-tracker`, `release-manager`

Any string works as a custom agent type.

## Build & Test

Projeto Python puro — não há `package.json`, `npm run build` nem `npm test`.

- ALWAYS run tests after code changes
- O ambiente virtual é `.venv`; o app sobe via `./run.sh`

```bash
source .venv/bin/activate
python3 test_pipeline.py        # teste de fumaça do pipeline (faz chamada real de rede)
./run.sh                        # sobe o Flask em app.py
```

> `test_pipeline.py` hoje é um script de fumaça, não uma suíte — ele imprime
> eventos em vez de asseverar. Não trate "rodou sem erro" como "passou".

## CLI Quick Reference

```bash
npx @claude-flow/cli@latest init --wizard           # Setup
npx @claude-flow/cli@latest swarm init --v3-mode     # Start swarm
npx @claude-flow/cli@latest memory search --query "" # Vector search
npx @claude-flow/cli@latest hooks route --task ""    # Route to agent
npx @claude-flow/cli@latest doctor --fix             # Diagnostics
npx @claude-flow/cli@latest security scan            # Security scan
npx @claude-flow/cli@latest performance benchmark    # Benchmarks
```

26 commands, 140+ subcommands. Use `--help` on any command for details.

## Setup

```bash
claude mcp add claude-flow -- npx -y ruflo@latest mcp start
npx ruflo@latest doctor --fix
```

> The background `daemon` is optional. It runs interval workers that each spawn
> a headless `claude` session, so it consumes tokens continuously. Start it only
> if you want those sweeps: `npx ruflo@latest daemon start` (self-stops after 12h
> by default; `--ttl 0` to disable, `daemon status --all` to audit running daemons).

**Agent tool** handles execution (agents, files, code, git). **MCP tools** handle coordination (swarm, memory, hooks). **CLI** is the same via Bash.
