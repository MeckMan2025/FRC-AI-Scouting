"""CLI: python -m aiscout --event 2026wasno --matches 1-10 [--teams 1678,2910]"""
import argparse
import time
from . import tba
from .backends.base import UsageLimit
from .backends import make
from .config import game as load_game, load
from .export import write
from .pipeline import process


def parse_range(s):
    if not s:
        return None, None
    a, _, b = s.partition("-")
    return int(a), int(b or a)


def main():
    p = argparse.ArgumentParser(prog="aiscout")
    p.add_argument("--event", required=True, help="TBA event key, e.g. 2026wasno")
    p.add_argument("--matches", help="qual match range, e.g. 1-10 or 7")
    p.add_argument("--teams", help="only scout these teams, e.g. 1678,2910")
    p.add_argument("--rescout", action="store_true", help="ignore saved results and ask the model again")
    a = p.parse_args()
    start, end = parse_range(a.matches)
    teams = [t.strip() for t in a.teams.split(",")] if a.teams else None
    game = load_game(int(a.event[:4]))
    backend = make(load())
    ms = tba.select(a.event, start, end, teams)
    print(f"{len(ms)} matches selected")
    entries = []
    for m in ms:
        print(tba.label(m))
        try:
            entries += process(m, game, backend, teams, a.rescout)
        except UsageLimit as ex:
            print(f"  usage limit reached ({ex}); stopping. Run again later; finished matches are saved.")
            break
        except Exception as ex:   # keep going; one bad video shouldn't stop the batch
            print(f"  skipped: {ex}")
    if entries:
        f = write(entries, f"{a.event}-{time.strftime('%Y%m%d-%H%M')}")
        print(f"Wrote {len(entries)} entries to {f}")


if __name__ == "__main__":
    main()
