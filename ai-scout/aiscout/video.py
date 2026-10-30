"""Download match videos and pull frames out of them."""
import json
import subprocess
import sys
from pathlib import Path
from . import CACHE

VIDEOS = CACHE / "videos"
# the yt-dlp installed in this project's .venv (kept current with pip; YouTube breaks old versions)
YTDLP = str(Path(sys.executable).with_name("yt-dlp"))


def download(yt_id):
    """Download a YouTube video (<=1080p, mp4, no audio) once; return its path.
    1080p matters: bumper numbers are unreadable at 720p from the overhead camera."""
    VIDEOS.mkdir(parents=True, exist_ok=True)
    out = VIDEOS / f"{yt_id}.mp4"
    if out.exists():
        return out
    subprocess.run([
        YTDLP, "-q", "--no-warnings", "--no-playlist",
        "-f", "bv*[height<=1080][ext=mp4][vcodec^=avc1]/bv*[height<=1080][ext=mp4]/b[height<=1080]",
        "-o", str(out),
        f"https://www.youtube.com/watch?v={yt_id}",
    ], check=True)
    return out


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def frame_at(path, t, out, width=640, crop=None):
    """Save one frame at time t (seconds) as a JPEG. crop = (x0, y0, x1, y1) as fractions of the frame."""
    vf = f"scale={width}:-2"
    if crop:
        x0, y0, x1, y1 = crop
        vf = f"crop=iw*{x1 - x0:.4f}:ih*{y1 - y0:.4f}:iw*{x0:.4f}:ih*{y0:.4f}," + vf
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path),
                    "-frames:v", "1", "-vf", vf, "-q:v", "3", str(out)], check=True)
    return Path(out)


def frames(path, times, outdir, width=640, crop=None):
    """Save a frame at each time; return [(t, path)] for the ones that worked."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    got = []
    for t in times:
        f = outdir / f"f{int(t * 10):05d}.jpg"
        if not f.exists():
            try:
                frame_at(path, t, f, width, crop)
            except subprocess.CalledProcessError:
                continue
        if f.exists() and f.stat().st_size:
            got.append((t, f))
    return got
