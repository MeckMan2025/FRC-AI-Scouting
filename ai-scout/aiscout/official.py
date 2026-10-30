"""Apply TBA's official per-robot results on top of the AI's calls (official wins)."""


def apply(m, robots, game):
    """Mutates each robot dict: overrides mapped fields, records the AI's original call, adds flags."""
    sb = m.get("score_breakdown")
    if not sb:
        return
    spec = game["tba_overrides"]["fields"]
    from .tba import robots as slots
    where = {team: (a, st) for team, a, st in slots(m)}
    for r in robots:
        if r["team"] not in where:
            continue
        a, st = where[r["team"]]
        side = sb.get("red" if a == "R" else "blue") or {}
        r.setdefault("official", {})
        r.setdefault("flags", [])
        for f in spec:
            raw = side.get(f["breakdown"].replace("{n}", st))
            if raw is None:
                continue
            for target, value in f["map"].get(str(raw), {}).items():
                sec, k = target.split(".")
                ai = r[sec].get(k)
                if isinstance(value, dict):     # {keep: [...], else: x}
                    value = ai if ai in value["keep"] else value["else"]
                if str(ai) != str(value):
                    r["official"][target] = {"ai": ai, "tba": value}
                    if ai is not None:
                        r["flags"].append(f"{target}: AI said {ai}, official {value}")
                r[sec][k] = value
    split_balls(m, robots, game)


def _dig(d, path):
    for k in path.split("."):
        d = d.get(k) if isinstance(d, dict) else None
    return d


def split_balls(m, robots, game):
    """Split each alliance's official ball total between its robots, in proportion to the AI's
    estimates. The AI undercounts a lot (a ball stream is hard to count from 1 frame every few
    seconds), but it sees who shoots more, so its shares are more useful than its raw counts."""
    sb = m.get("score_breakdown") or {}
    path = game.get("tba_alliance_totals", {}).get("balls")
    if not path:
        return
    from .tba import robots as slots
    for color, a in (("red", "R"), ("blue", "B")):
        official = _dig(sb.get(color) or {}, path)
        teams = [t for t, al, _ in slots(m) if al == a]
        mine = [r for r in robots if r["team"] in teams]
        if official is None or len(mine) < 3:
            continue    # need the whole alliance
        est = [max(0, r.get("balls_scored_estimate") or 0) for r in mine]
        total = sum(est)
        for r, e in zip(mine, est):
            share = e / total if total else None
            r["balls"] = {"est": e, "allianceOfficial": official, "share": round(share, 3) if share is not None else None,
                          "count": round(official * share) if share is not None else None}
            if not total and official:
                r.setdefault("flags", []).append(f"alliance scored {official} balls but the AI saw no shots; can't split")
