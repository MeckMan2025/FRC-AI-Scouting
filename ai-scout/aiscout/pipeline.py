"""Shared by the CLI and the web server: scout a match (or reuse its saved result) and build app entries."""
import json
from . import CACHE, tba
from .export import entry
from .official import apply
from .scout import scout_match


def saved_result(m, want):
    """The saved result for a match if it covers every wanted team."""
    f = CACHE / "matches" / m["key"] / "result.json"
    if not f.exists():
        return None
    res = json.loads(f.read_text())
    return res if set(want) <= {r["team"] for r in res["robots"]} else None


def wanted(m, teams):
    return [r[0] for r in tba.robots(m) if not teams or r[0] in teams]


def process(m, game, backend, teams=None, rescout=False, log=print):
    """Scout one match if needed; returns its app entries (official results applied)."""
    want = wanted(m, teams)
    res = None if rescout else saved_result(m, want)
    if res:
        log("  using saved result")
    else:
        res = scout_match(m, game, backend, set(teams) if teams else None, log)
    return entries_for(m, res, game, backend.name, want)


def entries_for(m, res, game, backend_name, want):
    robots = json.loads(json.dumps(res["robots"]))   # copy: the saved result stays the AI's raw calls
    apply(m, robots, game)                         # needs all robots (ball split is per alliance)
    return [entry(m, r, res, backend_name) for r in robots if r["team"] in want]
