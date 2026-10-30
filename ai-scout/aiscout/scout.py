"""Scout one match: video -> frames -> contact sheets -> model -> per-robot results."""
import json
import statistics
from . import CACHE, tba, video
from .frames import sheets

CONF = {"type": "string", "enum": ["low", "medium", "high"]}


def _n(t):
    """JSON-schema type that also allows null."""
    return {"anyOf": [t, {"type": "null"}]}


def _enum(vals):
    return _n({"enum": vals})


def robot_schema(game):
    e = game["enums"]
    yn = _n({"type": "boolean"})
    acc = _enum(e["acc"])
    pt = {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2}
    obj = lambda props: {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    return obj({
        "team": {"type": "string"},
        "found": {"type": "boolean", "description": "false if you could not pick this robot out in the video"},
        "robotType": {"enum": e["robotType"]},
        "auto": obj({"start": _enum(e["auto.start"]), "preload": yn, "path": {"type": "array", "items": pt, "maxItems": 8},
                     "collected": yn, "cycles": {"type": "integer"}, "acc": acc, "scored": yn, "hang": yn, "down": yn,
                     "notes": {"type": "string"}}),
        "tele": obj({"collected": yn, "acc": acc, "scored": yn, "beached": yn,
                     "beachWhere": {"type": "array", "items": {"enum": e["tele.beachWhere"]}},
                     "recovered": yn, "defense": yn,
                     "defZones": {"type": "array", "items": {"enum": e["tele.defZones"]}}, "notes": {"type": "string"}}),
        "end": obj({"cycles": {"type": "integer"}, "acc": acc, "climb": _enum(e["end.climb"]), "rung": _enum(e["end.rung"]),
                    "notes": {"type": "string"}}),
        "extra": obj({"penalties": {"type": "integer"}, "penKinds": {"type": "array", "items": {"enum": e["extra.penKinds"]}},
                      "penNotes": {"type": "string"}, "breakdown": yn, "comeback": yn, "stop": _enum(e["extra.stop"]),
                      "brkNotes": {"type": "string"}, "problems": {"type": "array", "items": {"enum": e["extra.problems"]}},
                      "probNotes": {"type": "string"}, "driver": _enum(["1", "2", "3", "4", "5"]),
                      "strategy": {"type": "string"}, "overall": {"type": "string"}}),
        "confidence": obj({"auto": CONF, "tele": CONF, "end": CONF, "extra": CONF}),
        "balls_scored_estimate": {"type": "integer", "description": "rough number of balls this robot scored all match"},
    })


def match_schema(game):
    return {"type": "object", "additionalProperties": False, "required": ["robots", "video_notes"],
            "properties": {"robots": {"type": "array", "items": robot_schema(game)},
                           "video_notes": {"type": "string", "description": "camera angle, visibility problems, anything that limited scouting"}}}


FRAC = {"type": "number", "minimum": 0, "maximum": 1}
ALIGN_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["tiles", "field_box"], "properties": {
  "field_box": {"type": "object", "additionalProperties": False, "required": ["x0", "y0", "x1", "y1"],
                "description": "box around the whole playing field (carpet inside the walls) in a single tile, as fractions of the tile's width/height (0,0 = top-left)",
                "properties": {"x0": FRAC, "y0": FRAC, "x1": FRAC, "y1": FRAC}},
  "tiles": {
    "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["label", "phase", "timer"],
                               "properties": {"label": {"type": "string"},
                                              "phase": {"enum": ["before", "auto", "teleop", "after", "unknown"]},
                                              "timer": {"anyOf": [{"type": "integer"}, {"type": "null"}],
                                                        "description": "match timer shown on screen, in seconds"}}}}}}


def find_start(vid, workdir, game, backend, log):
    """(video time when auto starts, field crop box) read from probe frames."""
    f = workdir / "start.json"
    if f.exists():
        d = json.loads(f.read_text())
        if "box" in d:
            return d["start"], d["box"]
    t = game["timing"]
    dur = video.duration(vid)
    times = [x * 3.0 for x in range(int(min(dur, 90) // 3))]
    fr = video.frames(vid, times, workdir / "probe", width=400)
    sh = sheets(fr, workdir, "probe", cols=5, rows=4, label=lambda s: f"{s:.0f}s")
    prompt = ("These are frames from an FRC match video, each labeled with its time in the video. "
              "For EVERY tile, report its label, the match phase, and the match timer shown on the "
              f"broadcast overlay in seconds (auto counts down from {t['auto_s']}, teleop counts down from "
              f"{t['teleop_s']}; convert m:ss to seconds). Use null if no timer is readable. "
              "Also give field_box: a box around the whole playing field (all carpet inside the field walls, "
              "both alliance zones; leave out the crowd and the score overlay) within ONE tile, as fractions.")
    data, usage = backend.ask(prompt, [p for p, _ in sh], ALIGN_SCHEMA, workdir)
    log(f"  start-finder usage: {usage}")
    est = []
    for tile in data["tiles"]:
        try:
            at = float(tile["label"].rstrip("s"))
        except ValueError:
            continue
        if tile["timer"] is None:
            continue
        if tile["phase"] == "auto":
            est.append(at - (t["auto_s"] - tile["timer"]))
        elif tile["phase"] == "teleop":
            est.append(at - (t["auto_s"] + t["transition_s"] + t["teleop_s"] - tile["timer"]))
    start = max(0.0, statistics.median(est)) if est else 5.0
    b = data["field_box"]
    pad = 0.02   # a little margin so robots at the walls aren't cut off
    box = [max(0, b["x0"] - pad), max(0, b["y0"] - pad), min(1, b["x1"] + pad), min(1, b["y1"] + pad)]
    if box[2] - box[0] < 0.3 or box[3] - box[1] < 0.2:
        box = [0, 0, 1, 1]  # implausible box: use the whole frame
    f.write_text(json.dumps({"start": start, "box": box, "estimates": est, "guessed": not est}))
    return start, box


def frame_plan(start, game, dur):
    """[(video_time, label)] with more frames in auto and endgame."""
    t, fr = game["timing"], game["frames"]
    tele0 = t["auto_s"] + t["transition_s"]
    end0 = tele0 + t["teleop_s"] - t["endgame_s"]
    stop = tele0 + t["teleop_s"]
    plan = []

    def span(a, b, fps, tag):
        x = a
        while x < b:
            plan.append((start + x, tag, x))
            x += 1 / fps
    span(0, t["auto_s"], fr["auto_fps"], "AUTO")
    span(tele0, end0, fr["teleop_fps"], "TELE")
    span(end0, stop + 2, fr["endgame_fps"], "END")
    return [(v, f"{tag} +{int(x)}s") for v, tag, x in plan if v < dur - 0.5]


def build_prompt(game, m, want):
    rows = "\n".join(f"- Team {team}: {'RED' if a == 'R' else 'BLUE'} alliance, driver station {st}"
                     for team, a, st in tba.robots(m) if team in want)
    others = ", ".join(f"{team} ({'red' if a == 'R' else 'blue'})" for team, a, _ in tba.robots(m) if team not in want)
    lf = game["look_for"]
    return f"""Scout FRC {game['year']} ({game['name']}) match {tba.label(m)} at event {m['event_key']}.

Game rules (short):
{chr(10).join('- ' + r for r in game['rules_summary'])}

Scout these robots (find them by the team number on their bumpers and their bumper color):
{rows}
{('Other robots in the match (do not report them): ' + others) if others else ''}

Images:
- id_red.jpg / id_blue.jpg: full-resolution close-ups of the red (left) and blue (right) halves of the field at the start
  of auto, while robots sit at their starting spots. Read bumper numbers here first, and note each robot's look
  (shape, colors, mechanisms) so you can follow it later when its number isn't readable.
- sheet_*.jpg: the field, cropped from the overhead camera, 2 frames per image in time order. Each frame is labeled with
  the phase and seconds since the match started (AUTO +0s = start of auto). Red alliance is on the LEFT.
Open EVERY image file before answering. Follow each robot from frame to frame by its look and position.

For each robot, fill in:
AUTO: {lf['auto']}
TELEOP: {lf['tele']}
ENDGAME: {lf['end']}
EXTRA: {lf['extra']}

Auto path points use the app's field map. {game['field_map']['description']}

Rules for answers:
- Use null when you truly cannot tell; otherwise give your best guess and lower the confidence.
- confidence per section: high = clearly seen, medium = mostly seen, low = guessed from little evidence.
- Put the reasoning for uncertain calls in that section's notes, starting with "AI:".
- cycles are counts of collect->score trips. acc is the closest of 0/25/50/75/100 percent of shots that went in.
- driver is 1-5 (1 = poor, 5 = great). penalties is the number of fouls you saw this robot commit.
- If you cannot pick a robot out at all, set found=false and leave its fields null/empty.
Return one entry per requested team, with team as the plain number string."""


def scout_match(m, game, backend, teams=None, log=print):
    """Returns {'robots': [...], 'video_notes', 'usage': [...], 'start': s} or raises."""
    yt = tba.youtube_id(m)
    if not yt:
        raise LookupError("no video on TBA for this match")
    # Always scout all 6: splitting an alliance's official ball total needs every robot's
    # estimate, and the images cost the same either way. `teams` only filters the export.
    want = [r[0] for r in tba.robots(m)]
    workdir = CACHE / "matches" / m["key"]
    workdir.mkdir(parents=True, exist_ok=True)
    log(f"  video {yt}")
    vid = video.download(yt)
    start, box = find_start(vid, workdir, game, backend, log)
    log(f"  match starts at {start:.1f}s in the video; field box {box}")
    fg = game["frames"]
    x0, y0, x1, y1 = box
    mid = (x0 + x1) / 2
    ids = []
    for name, half in (("id_red", (x0, y0, mid + 0.03, y1)), ("id_blue", (mid - 0.03, y0, x1, y1))):
        ids.append(video.frame_at(vid, start + 0.5, workdir / f"{name}.jpg", fg["id_width"], half))
    plan = frame_plan(start, game, video.duration(vid))
    fr = video.frames(vid, [v for v, _ in plan], workdir / "frames", width=fg["frame_width"], crop=box)
    labels = dict(plan)
    sh = sheets(fr, workdir, "sheet", fg["sheet_cols"], fg["sheet_rows"], label=lambda v: labels[v])
    log(f"  {len(fr)} frames on {len(sh)} sheets + 2 close-ups; asking {backend.name}")
    data, usage = backend.ask(build_prompt(game, m, want), ids + [p for p, _ in sh], match_schema(game), workdir)
    log(f"  usage: {usage}")
    data["robots"] = [r for r in data["robots"] if r["team"] in want]
    data.update(usage=usage, start=start, video=yt, backend=backend.name)
    (workdir / "result.json").write_text(json.dumps(data, indent=1))
    return data
