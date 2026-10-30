import json
from . import ROOT

CONFIG = ROOT / "config.json"


def load():
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else {}


def save(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2))


def game(year):
    return json.loads((ROOT / "games" / f"{year}.json").read_text())
