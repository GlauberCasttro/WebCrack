# Project Instructions

## Tech Stack
- Python Flask app with a vanilla HTML/CSS/JS frontend.
- Groq `AsyncGroq` streams LLM tokens.
- GitHub API access uses `requests` with retry support.
- Frontend Markdown rendering uses `marked.js` from CDN.
- Runtime config comes from `.env` via `python-dotenv`.

## Build & Run
- Create env: `python3 -m venv .venv`
- Activate env: `source .venv/bin/activate`
- Install deps: `pip install -r requirements.txt`
- Dev server: `./run.sh` or `python3 app.py`
- Syntax check: `python3 -m py_compile core.py app.py agents/*.py`

## Environment
- `GROQ_API_KEY` is required for analysis and chat.
- `GITHUB_TOKEN` is optional, but helps avoid low public GitHub API rate limits.
- Never commit `.env` or generated files under `analises/`.

## Project Structure
- `app.py` - Flask routes, SSE response helpers, saved-analysis endpoints.
- `core.py` - GitHub API helpers, Groq streaming, config, env validation, analysis persistence.
- `agents/` - deterministic pipeline stages plus final LLM synthesis.
- `templates/index.html` - complete frontend UI and browser-side SSE handling.
- `test_pipeline.py` - manual async pipeline smoke script.
- `run.sh` - activates `.venv` and starts the Flask app.

## Pipeline
- `decomposer.py` converts user intent into an `Intent` using heuristics.
- `explorer.py` expands relevant GitHub directories.
- `planner.py` selects a small set of files to read.
- `fetcher.py` fetches file previews in parallel.
- `synthesizer.py` builds grounded prompts and streams Groq tokens.
- `pipeline.py` orchestrates stages and emits SSE events: `status`, `token`, `error`, `done`.

## Code Style
- Use small module-level helpers for focused behavior.
- Keep GitHub/API logic UI-agnostic in `core.py`.
- Keep orchestration in `agents/pipeline.py`; individual agents should stay narrow.
- Prefer async generators for streaming paths.
- Use `core.UserFacingError` for expected user-actionable failures.
- Expected failures should become SSE `{ "type": "error", "data": "..." }` events.

## Frontend Conventions
- The frontend is currently single-file vanilla JS in `templates/index.html`.
- Use the existing state variables: `repos`, `selectedRepo`, `streaming`, `sessions`, `currentKey`.
- SSE payloads are JSON objects sent as `data: ...`.
- Render streamed Markdown through `marked.parse`.

## Testing
- There is no formal test runner configured.
- Use `python3 -m py_compile core.py app.py agents/*.py` before handing off Python changes.
- Use `test_pipeline.py` only as a manual smoke test; it calls live GitHub/Groq services.

## Git Conventions
- Recent commits use short imperative/feature-style messages, e.g. `feat: ...`.
- Keep generated analyses out of commits; `analises/` is ignored.
