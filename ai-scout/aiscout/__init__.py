"""AI Scout: turns FRC match videos into entries for the frc-scouting app."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
OUT = ROOT / "out"
VERSION = "0.1"
