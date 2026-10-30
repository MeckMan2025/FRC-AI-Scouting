"""Local web page for AI Scout: pick an event, matches and teams, then watch it work.

Run:  .venv/bin/python server.py      then open http://localhost:8765
"""
import json
import time
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from aiscout import CACHE, ROOT, tba, queue
from aiscout.backends.ollama import installed_models, DEFAULT_MODEL
from aiscout.config import load, save

PORT = 8765
worker = queue.Worker()


def event_info(key):
    ms = sorted(tba.matches(key), key=tba.sort_key)
    quals = [m for m in ms if m["comp_level"] == "qm"]
    teams = sorted({int(r[0]) for m in quals for r in tba.robots(m)})
    return {"key": key, "quals": len(quals), "withVideo": sum(1 for m in quals if tba.youtube_id(m)),
            "teams": teams, "lastQual": max((m["match_number"] for m in quals), default=0)}


def preview(q):
    ms = tba.select(q["event"], q.get("start"), q.get("end"), q.get("teams"))
    teams = set(q.get("teams") or [])
    robots = sum(len([r for r in tba.robots(m) if not teams or r[0] in teams]) for m in ms)
    return {"matches": [tba.label(m) for m in ms], "noVideo": [tba.label(m) for m in ms if not tba.youtube_id(m)],
            "robots": robots}


def result(key):
    f = CACHE / "matches" / key / "result.json"
    return json.loads(f.read_text()) if f.exists() else None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body, code=200, ctype="application/json", headers=None):
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def handle_any(self, method):
        u = urlparse(self.path)
        parts = [p for p in u.path.split("/") if p]
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if method == "GET" and not parts:
                return self.send((ROOT / "web" / "index.html").read_bytes(), ctype="text/html; charset=utf-8")
            if parts[:1] != ["api"]:
                return self.send({"error": "not found"}, 404)
            r = parts[1:]
            if r == ["config"]:
                cfg = load()
                if method == "POST":
                    cfg.update({k: v for k, v in self.body().items() if k in ("tba_key", "model", "backend", "ollama_model")})
                    save(cfg)
                return self.send({"hasKey": bool(cfg.get("tba_key")), "model": cfg.get("model") or "",
                                  "backend": cfg.get("backend") or "claude-code", "ollamaModel": cfg.get("ollama_model") or ""})
            if r == ["ollama"]:
                return self.send({"models": installed_models(), "recommended": DEFAULT_MODEL})
            if r == ["events"]:
                evs = sorted(tba.events(int(q.get("year", time.strftime("%Y")))), key=lambda e: (e["start_date"], e["name"]))
                return self.send([{"key": e["key"], "name": e["name"], "date": e["start_date"]} for e in evs])
            if len(r) == 2 and r[0] == "event":
                return self.send(event_info(r[1]))
            if r == ["preview"]:
                return self.send(preview(self.body()))
            if r == ["jobs"] and method == "POST":
                b = self.body()
                jid = queue.create(b["event"], b.get("start"), b.get("end"), b.get("teams"), b.get("rescout", False))
                return self.send({"id": jid})
            if r == ["jobs"]:
                return self.send({"jobs": queue.jobs(), "log": worker.log_lines[-40:]})
            if r == ["jobs", "clear"] and method == "POST":
                return self.send({"cleared": queue.clear_finished()})
            if len(r) == 3 and r[0] == "jobs" and r[2] == "cancel":
                queue.cancel(int(r[1]))
                return self.send({"ok": True})
            if len(r) == 3 and r[0] == "jobs" and r[2] == "download":
                f, n = queue.export(int(r[1]))
                return self.send(f.read_bytes(), headers={"Content-Disposition": f'attachment; filename="{f.name}"'})
            if len(r) == 2 and r[0] == "result":
                return self.send(result(r[1]) or {"error": "no result"})
            if len(r) == 3 and r[0] == "image":   # /api/image/<match_key>/<file>.jpg
                f = CACHE / "matches" / r[1] / Path(r[2]).name
                return self.send(f.read_bytes(), ctype="image/jpeg") if f.suffix == ".jpg" and f.exists() else self.send({}, 404)
            return self.send({"error": "not found"}, 404)
        except Exception as ex:
            return self.send({"error": str(ex)}, 500)

    def do_GET(self):
        self.handle_any("GET")

    def do_POST(self):
        self.handle_any("POST")


if __name__ == "__main__":
    worker.start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"AI Scout running at http://localhost:{PORT}  (Ctrl+C to stop)")
    webbrowser.open(f"http://localhost:{PORT}")
    srv.serve_forever()
