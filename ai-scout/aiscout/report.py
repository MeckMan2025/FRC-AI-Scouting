"""Accuracy report: the AI's raw calls (before official overrides) vs TBA's official results.

python -m aiscout.report 2026wasno
"""
import json
import sys
from collections import Counter
from . import CACHE, tba
from .official import _dig


def main(event):
    tower = Counter()   # (field, outcome) -> n
    balls, found, conf, usage = [], Counter(), Counter(), []
    rows = []
    for f in sorted((CACHE / "matches").glob(f"{event}_*/result.json")):
        res = json.loads(f.read_text())
        m = tba.match(f.parent.name)
        sb = m.get("score_breakdown") or {}
        usage.append(res["usage"])
        slot = {t: (a, st) for t, a, st in tba.robots(m)}
        by_alliance = {"R": [], "B": []}
        for r in res["robots"]:
            a, st = slot[r["team"]]
            side = sb.get("red" if a == "R" else "blue") or {}
            found[r["found"]] += 1
            for sec, c in r["confidence"].items():
                conf[(sec, c)] += 1
            by_alliance[a].append(r.get("balls_scored_estimate"))
            off_auto = side.get(f"autoTowerRobot{st}") not in (None, "None")
            ai_auto = r["auto"]["hang"] is True
            off_end = side.get(f"endGameTowerRobot{st}", "None")
            off_climbed = off_end != "None"
            ai_climbed = r["end"]["climb"] == "ok"
            tower[("auto hang", "agree" if ai_auto == off_auto else ("missed" if off_auto else "false alarm"))] += 1
            tower[("end climb", "agree" if ai_climbed == off_climbed else ("missed" if off_climbed else "false alarm"))] += 1
            if off_climbed and ai_climbed:
                tower[("rung", "agree" if str(r["end"]["rung"]) == off_end[-1] else "wrong")] += 1
            if off_auto or off_climbed or ai_auto or ai_climbed:
                rows.append(f"  {m['key']} {r['team']}: auto hang AI={ai_auto} official={off_auto}; "
                            f"climb AI={r['end']['climb']}/{r['end']['rung']} official={off_end}")
        for a, color in (("R", "red"), ("B", "blue")):
            est = by_alliance[a]
            if len(est) == 3 and None not in est:
                balls.append((m["key"], color, sum(est), _dig(sb.get(color) or {}, "hubScore.totalCount")))

    n = len(usage)
    print(f"{event}: {n} matches, {sum(found.values())} robots, found in video: {found[True]}/{sum(found.values())}\n")
    print("Tower calls vs official (the AI's own call, before override):")
    for (field, outcome), k in sorted(tower.items()):
        print(f"  {field:10} {outcome:12} {k}")
    print("\nRobots where either side reported a hang/climb:")
    print("\n".join(rows) or "  none")
    print("\nAlliance balls, AI estimate vs official:")
    for key, color, est, off in balls:
        print(f"  {key} {color:4} AI {est:4}  official {off}")
    if balls:
        err = [abs(e - o) / o for _, _, e, o in balls if o]
        print(f"  mean error {100 * sum(err) / len(err):.0f}%")
    print("\nConfidence given:")
    for sec in ("auto", "tele", "end", "extra"):
        print(f"  {sec:6} " + "  ".join(f"{c}={conf[(sec, c)]}" for c in ("high", "medium", "low")))
    if n:
        tin = sum(u["in"] for u in usage) / n
        tout = sum(u["out"] for u in usage) / n
        usd = sum(u.get("api_equiv_usd") or 0 for u in usage) / n
        secs = sum(u.get("seconds") or 0 for u in usage) / n
        print(f"\nPer match: ~{tin / 1000:.0f}k tokens in, ~{tout / 1000:.0f}k out, {secs:.0f}s model time, "
              f"API-equivalent ${usd:.2f} (billed to Max, not charged)")


if __name__ == "__main__":
    main(sys.argv[1])
