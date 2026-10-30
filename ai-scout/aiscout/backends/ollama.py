"""Backend for a local vision model served by Ollama (https://ollama.com).

A small model on an 8 GB Mac can't take 30+ large images at once, so long jobs run in steps:
  1. describe each robot from the first images (the starting close-ups),
  2. take notes on a few frames at a time, carrying the robot descriptions forward,
  3. fill in the JSON schema from the notes alone (no images).
Short jobs (e.g. the start finder's 2 probe sheets) go in one call.
"""
import base64
import io
import json
import time
import urllib.error
import urllib.request
from PIL import Image
from .base import Backend

HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen3-vl:4b"


def _post(path, body, timeout=1800):
    req = urllib.request.Request(HOST + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.URLError as ex:
        if isinstance(ex, urllib.error.HTTPError):
            raise RuntimeError(f"Ollama error: {ex.read().decode(errors='replace')[:300]}")
        raise RuntimeError("Ollama isn't running. Open the Ollama app (or run `ollama serve`) and try again.")


def installed_models():
    """Names of models Ollama has downloaded, or None if Ollama isn't reachable."""
    try:
        with urllib.request.urlopen(HOST + "/api/tags", timeout=3) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _b64(path, max_side):
    """JPEG bytes, shrunk so the longest side is max_side (keeps image tokens and memory down)."""
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


class Ollama(Backend):
    name = "ollama"

    def __init__(self, model=None, images_per_call=4, max_side=1024, num_ctx=16384):
        self.model = model or DEFAULT_MODEL
        self.images_per_call, self.max_side, self.num_ctx = images_per_call, max_side, num_ctx
        self.usage = {}

    def _chat(self, prompt, images=(), schema=None):
        body = {"model": self.model, "stream": False, "keep_alive": "10m",
                "options": {"num_ctx": self.num_ctx, "temperature": 0.2},
                "messages": [{"role": "user", "content": prompt,
                              **({"images": [_b64(p, self.max_side) for p in images]} if images else {})}]}
        if schema:
            body["format"] = schema
        d = _post("/api/chat", body)
        self.usage["in"] = self.usage.get("in", 0) + d.get("prompt_eval_count", 0)
        self.usage["out"] = self.usage.get("out", 0) + d.get("eval_count", 0)
        self.usage["calls"] = self.usage.get("calls", 0) + 1
        return d["message"]["content"]

    def ask(self, prompt, images, schema, workdir):
        t0 = time.time()
        self.usage = {}
        images = list(images)
        if len(images) <= self.images_per_call:
            text = self._chat(prompt + "\n\nThe images are attached in the order listed.", images, schema)
        else:
            text = self._stepwise(prompt, images, schema)
        data = json.loads(text)
        self.usage.update(api_equiv_usd=0, seconds=round(time.time() - t0, 1), model=self.model)
        return data, dict(self.usage)

    def _stepwise(self, prompt, images, schema):
        n = self.images_per_call
        first, rest = images[:2], images[2:]   # scout.py puts the two starting close-ups first
        looks = self._chat(
            f"{prompt}\n\nSTEP 1 of several. Attached: {', '.join(p.name for p in first)} (starting close-ups). "
            "Do NOT fill in the form yet. For each requested team, write one line: where it starts, its bumper "
            "color, and what it looks like (shape, colors, mechanisms) so it can be recognized later. "
            "Say so if you can't find a team.", first)
        notes = []
        for i in range(0, len(rest), n):
            chunk = rest[i:i + n]
            notes.append(f"[{', '.join(p.name for p in chunk)}]\n" + self._chat(
                f"{prompt}\n\nSTEP {2 + i // n}. Robot descriptions from the start of the match:\n{looks}\n\n"
                f"Attached: {', '.join(p.name for p in chunk)}. Do NOT fill in the form yet. In short bullet "
                "points, say what each requested robot does in these frames (use the time labels): driving, "
                "collecting, shooting and roughly how many balls, defense, getting stuck, climbing, fouls. "
                "Skip robots you can't see.", chunk))
        return self._chat(
            f"{prompt}\n\nFINAL STEP. You already looked at every image; your notes are below. Fill in the form "
            f"for every requested team using only these notes. Use low confidence where the notes are thin.\n\n"
            f"Robot descriptions:\n{looks}\n\nNotes in time order:\n" + "\n\n".join(notes), schema=schema)
