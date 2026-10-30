# FRC AI Scouting

AI Scout watches posted FRC match videos and fills in scouting entries for our team's scouting app
([frc-scouting](https://meckman2025.github.io/frc-scouting/FRC-Scouting.html)). It's mainly for **pre-event recon**:
scouting other teams' earlier matches before we get to an event.

For each match it:
1. Looks the match up on [The Blue Alliance](https://www.thebluealliance.com) (teams, stations, video, official results).
2. Downloads the video (1080p, so bumper numbers are readable) and finds when the match starts from the on-screen timer.
3. Crops the field out of ~70 frames (more during auto and endgame) and asks an AI to scout every robot.
4. Overwrites climbs and auto hangs with **official results**, and splits each alliance's official ball count between its
   robots by the share the AI saw each one shoot.
5. Writes a `.json` file you load into the scouting app with **Sync & Settings → Import files…**. Entries are signed
   "AI Scout" and carry a confidence level (low / medium / high) per section.

## Start it

Double-click **`Start AI Scout.command`** (macOS). It sets itself up the first time and opens
http://localhost:8765. Keep its Terminal window open while it scouts.

On the page: add your Blue Alliance read key (free at thebluealliance.com/account), pick an event, a qual range and
(optionally) teams, then **Start scouting**. When matches turn green, **Download import file**.

Needs: macOS with Python 3, `ffmpeg` (`brew install ffmpeg`), and an AI engine:

| Engine | Setup | Notes |
|---|---|---|
| **Claude** (default) | [Claude Code](https://claude.com/claude-code) logged in with a Claude subscription | ~2.5 min and ~100k input tokens per match. Runs on the subscription login, not an API key; pauses and resumes on usage limits. |
| **Local (Ollama)** | Install [Ollama](https://ollama.com/download), then `ollama pull qwen3-vl:4b` | Free and offline after setup, but much slower and less accurate. Works in steps so it fits on an 8 GB Mac. |

Command line instead of the page:

```
cd ai-scout
.venv/bin/python -m aiscout --event 2026wasno --matches 1-10 --teams 2522,2910
.venv/bin/python -m aiscout.report 2026wasno     # AI calls vs official results, and usage per match
```

## How good is it?

First test, 5 quals at PNW Glacier Peak 2026 (30 robots):
- Found 29 of 30 robots in the video.
- Climbs and auto hangs from video are unreliable (caught 1 of 5 climbs), which is why official results replace them.
- Raw ball counts ran ~57% low, hence the split of the official totals.
- Most sections come back low or medium confidence; the notes say why (robots hidden behind hubs, far-side numbers
  unreadable, teleop sampled every 4 s).

Treat it as a head start for recon, not a replacement for watching key matches. Every entry links to its video.

## Layout

```
Start AI Scout.command   double-click launcher
ai-scout/
  server.py              local web page + job queue worker
  web/index.html         the page
  games/2026.json        everything season-specific: rules summary, form options, timing, TBA field mapping
  aiscout/               pipeline: tba, video, scout, official, export, queue, report
  aiscout/backends/      claude_code.py (headless Claude Code), ollama.py (local model)
app-patch/ai-entries.patch   changes to the scouting app: AI badge, confidence, "Include AI entries" toggle,
                             ball split in match detail, CSV columns (apply in frc-scouting, then run build.py)
AI-Scout-Plan.txt        the original design plan
```

**New season:** copy `games/2026.json` to `games/2027.json` and update the rules summary, form options, timing and
the TBA `score_breakdown` field names. The scouting app's form needs the same changes.
