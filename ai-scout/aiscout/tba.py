"""The Blue Alliance API v3: events, teams, matches, videos, score breakdowns."""
import json
import time
import urllib.request
from . import CACHE
from .config import load

BASE = "https://www.thebluealliance.com/api/v3"


def get(path, max_age=600):
    """GET a TBA path, cached on disk for max_age seconds."""
    key = load().get("tba_key")
    if not key:
        raise RuntimeError("No TBA key: add tba_key to ai-scout/config.json")
    f = CACHE / "tba" / (path.strip("/").replace("/", "__") + ".json")
    if f.exists() and time.time() - f.stat().st_mtime < max_age:
        return json.loads(f.read_text())
    req = urllib.request.Request(BASE + path, headers={"X-TBA-Auth-Key": key, "User-Agent": "frc-ai-scout"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data))
    return data


def events(year):
    return get(f"/events/{year}/simple", max_age=86400)


def event_teams(event):
    return get(f"/event/{event}/teams/simple", max_age=3600)


def matches(event):
    return get(f"/event/{event}/matches")


def match(key):
    return get(f"/match/{key}")


ORDER = {"qm": 0, "ef": 1, "qf": 2, "sf": 3, "f": 4}


def sort_key(m):
    return (ORDER.get(m["comp_level"], 9), m["set_number"], m["match_number"])


def label(m):
    """Short label like qm12 or sf3m1."""
    if m["comp_level"] == "qm":
        return f"qm{m['match_number']}"
    return f"{m['comp_level']}{m['set_number']}m{m['match_number']}"


def robots(m):
    """[(team_number, 'R'|'B', station)] for a match."""
    out = []
    for color, a in (("red", "R"), ("blue", "B")):
        for i, tk in enumerate(m["alliances"][color]["team_keys"], 1):
            out.append((tk[3:], a, str(i)))
    return out


def youtube_id(m):
    for v in m.get("videos") or []:
        if v.get("type") == "youtube" and v.get("key"):
            return v["key"].split("?")[0]
    return None


def select(event, start=None, end=None, teams=None, playoffs=False):
    """Matches of an event filtered by qual-number range and/or team list."""
    teams = {str(t) for t in teams} if teams else None
    out = []
    for m in sorted(matches(event), key=sort_key):
        if m["comp_level"] == "qm":
            n = m["match_number"]
            if (start and n < start) or (end and n > end):
                continue
        elif not playoffs:
            continue
        if teams and not teams & {r[0] for r in robots(m)}:
            continue
        out.append(m)
    return out
