"""Backend that runs headless Claude Code on the user's claude.ai (Max) login."""
import json
import os
import re
import subprocess
import time
from .base import Backend, UsageLimit

SYSTEM = ("You are an expert FRC match scout. You look at contact sheets of match video frames "
          "(use the Read tool to open each image file you are given) and report what you see as JSON. "
          "Be honest about uncertainty.")

# Unset so `claude` uses the claude.ai login instead of an API key, and doesn't
# think it's running inside another Claude Code session.
STRIP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT",
             "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_MESSAGING_SOCKET",
             "CLAUDE_CODE_MESSAGING_TOKEN")


def _resume_at(text):
    """Best guess at when a usage limit resets, from the error text."""
    m = re.search(r"\|(\d{10})", text)
    if m:
        return int(m.group(1))
    return time.time() + 30 * 60   # unknown: check again in 30 min


class ClaudeCode(Backend):
    name = "claude-code"

    def __init__(self, model=None, timeout=900):
        self.model, self.timeout = model, timeout

    def ask(self, prompt, images, schema, workdir):
        files = "\n".join(f"- {p.name}" for p in images)
        # every extra turn resends all images read so far, so open them all in one turn
        how = ("Open ALL of these image files in ONE turn, as parallel Read calls in a single message, "
               "then answer. Do not read them one at a time.")
        cmd = ["claude", "-p", f"{prompt}\n\nImage files (in the current folder):\n{files}\n\n{how}",
               "--output-format", "json", "--json-schema", json.dumps(schema),
               "--tools", "Read", "--allowedTools", "Read", "--permission-mode", "dontAsk",
               "--system-prompt", SYSTEM, "--strict-mcp-config", "--disable-slash-commands",
               "--setting-sources", "", "--no-session-persistence"]
        if self.model:
            cmd += ["--model", self.model]
        env = {k: v for k, v in os.environ.items() if k not in STRIP_ENV}
        r = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True, timeout=self.timeout)
        out = r.stdout
        try:
            d = json.loads(out[out.index("{"):])
        except ValueError:
            msg = (out + r.stderr).strip()
            if "limit" in msg.lower():
                raise UsageLimit(msg[:300], _resume_at(msg))
            raise RuntimeError(f"claude returned no JSON: {msg[:500]}")
        text = str(d.get("result", ""))
        if d.get("is_error"):
            if "limit" in text.lower() or d.get("api_error_status") == 429:
                raise UsageLimit(text[:300], _resume_at(text))
            raise RuntimeError(f"claude error: {text[:500]}")
        data = d.get("structured_output")
        if data is None:
            data = json.loads(text)
        u = d.get("usage", {})
        usage = {"in": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0),
                 "out": u.get("output_tokens", 0), "api_equiv_usd": d.get("total_cost_usd"),
                 "seconds": d.get("duration_ms", 0) / 1000, "model": next(iter(d.get("modelUsage", {})), None)}
        return data, usage
