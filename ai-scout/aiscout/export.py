"""Turn scout results into entries the frc-scouting app can import."""
import json
import time
from . import OUT, VERSION, tba

SCOUTER = "AI Scout"


def entry(m, robot, result, backend_name):
    """One app match entry (same shape as blankMatch() in FRC-Scouting.html)."""
    team, alliance, station = next(r for r in tba.robots(m) if r[0] == robot["team"])
    e = {
        "kind": "match", "v": 1, "id": f"ai-{m['key']}-frc{team}", "ts": int(time.time() * 1000),
        "scouter": SCOUTER, "event": m["event_key"], "match": str(m["match_number"]), "team": team,
        "alliance": alliance, "station": station, "robotType": robot.get("robotType") or "",
        "auto": dict(robot["auto"]), "tele": dict(robot["tele"], defDots=[]),
        "end": dict(robot["end"]), "extra": dict(robot["extra"]),
    }
    e["auto"]["path"] = [[int(x), int(y)] for x, y in e["auto"]["path"]]
    for k in ("cycles",):
        e["auto"][k] = max(0, e["auto"][k] or 0)
        e["end"][k] = max(0, e["end"][k] or 0)
    e["extra"]["penalties"] = max(0, e["extra"]["penalties"] or 0)
    # the app's parseVal() turns numeric button values into numbers
    for sec, k in (("auto", "acc"), ("tele", "acc"), ("end", "acc"), ("end", "rung"), ("extra", "driver")):
        if e[sec].get(k) is not None:
            e[sec][k] = int(e[sec][k])
    e["ai"] = {
        "version": VERSION, "backend": backend_name, "model": result["usage"].get("model"),
        "video": result.get("video"), "found": robot["found"], "confidence": robot["confidence"],
        "balls": (robot.get("balls") or {}).get("count"), "ballsShare": (robot.get("balls") or {}).get("share"),
        "allianceBalls": (robot.get("balls") or {}).get("allianceOfficial"), "ballsEst": robot.get("balls_scored_estimate"), "videoNotes": result.get("video_notes", ""),
        "official": robot.get("official", {}), "flags": robot.get("flags", []),
    }
    return e


def write(entries, name):
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{name}.json"
    f.write_text(json.dumps({"app": "frc-scouting", "v": 1, "exported": int(time.time() * 1000),
                             "matches": entries, "pits": [], "pre": []}, indent=1))
    return f
