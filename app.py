"""
app.py — Deep GitHub Analyzer  (Flask web server)
HTML servido de templates/index.html
Streaming via Server-Sent Events.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import webbrowser

from flask import Flask, Response, jsonify, request, send_from_directory

import core
from agents import pipeline

app = Flask(__name__)
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


# ── SSE helpers ───────────────────────────────────────────────────────────────

def _run_stream(coro_factory, q: queue.Queue):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(coro_factory(q))
    except core.UserFacingError as exc:
        q.put({"type": "error", "data": str(exc)})
    except Exception as exc:
        q.put({"type": "error", "data": f"Erro inesperado no servidor: {exc}"})
    finally:
        q.put(None)
        loop.close()


def _sse_response(q: queue.Queue) -> Response:
    def generate():
        while True:
            event = q.get()
            if event is None:
                yield "data: [DONE]\n\n"
                break
            # Format as JSON string
            yield f"data: {json.dumps(event)}\n\n"

    return Response(
        generate(),
        content_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(TEMPLATES_DIR, "index.html")


@app.route("/env")
def env_check():
    ok, warn = core.validate_env()
    return jsonify({"ok": ok, "warn": warn})


@app.route("/search", methods=["POST"])
def search():
    data = request.get_json()
    repos = core.search_repositories(data.get("query", ""))
    slim = [
        {
            "full_name": r["full_name"],
            "stargazers_count": r.get("stargazers_count", 0),
            "description": (r.get("description") or "")[:120],
            "language": r.get("language", ""),
            "html_url": r.get("html_url", ""),
            "topics": r.get("topics", []),
        }
        for r in repos
    ]
    return jsonify(slim)


@app.route("/analyze", methods=["POST"])
def analyze():
    repo = request.get_json()
    q: queue.Queue[dict | None] = queue.Queue()

    async def _coro(q):
        full = ""
        has_error = False
        async for event in pipeline.run_analysis(repo, query="__analysis__", chat_history=None):
            q.put(event)
            if event["type"] == "token":
                full += event["data"]
            elif event["type"] == "error":
                has_error = True
        # Assíncrono concluído, salva em disco
        if full and not has_error:
            threading.Thread(
                target=lambda: core.save_analysis(repo, full), daemon=True
            ).start()

    threading.Thread(target=_run_stream, args=(_coro, q), daemon=True).start()
    return _sse_response(q)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    messages = data["messages"]
    q: queue.Queue[dict | None] = queue.Queue()

    async def _coro(q):
        async for token in core.stream_llm(messages, max_completion_tokens=4096):
            q.put({"type": "token", "data": token})

    threading.Thread(target=_run_stream, args=(_coro, q), daemon=True).start()
    return _sse_response(q)


ANALYSES_DIR = os.path.join(os.path.dirname(__file__), "analises")


@app.route("/analyses")
def list_analyses():
    """List all saved analysis files, newest first."""
    if not os.path.exists(ANALYSES_DIR):
        return jsonify([])
    items = []
    for fname in os.listdir(ANALYSES_DIR):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(ANALYSES_DIR, fname)
        try:
            mtime = os.path.getmtime(path)
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            items.append({"filename": fname, "name": fname[:-3], "content": content, "mtime": mtime})
        except OSError:
            pass
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify(items)


@app.route("/analyses/<path:name>", methods=["DELETE"])
def delete_analysis(name):
    """Delete a saved analysis file."""
    path = os.path.join(ANALYSES_DIR, name + ".md")
    if os.path.exists(path):
        os.remove(path)
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 404


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    url = "http://127.0.0.1:5000"
    print(f"\n🚀  Abrindo Deep GitHub Analyzer em {url}\n")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(debug=False, threaded=True, port=5000)
