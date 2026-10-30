"""Turn frames into labeled contact sheets so one image covers several moments."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def _font(size):
    for f in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def sheets(frames, outdir, prefix, cols=3, rows=2, label=lambda t: f"{t:.0f}s"):
    """frames: [(t, path)]. Writes prefix_01.jpg... ; returns [(path, [labels])]."""
    outdir = Path(outdir)
    per = cols * rows
    out = []
    for n, i in enumerate(range(0, len(frames), per), 1):
        chunk = frames[i:i + per]
        imgs = [Image.open(p).convert("RGB") for _, p in chunk]
        w, h = imgs[0].size
        sheet = Image.new("RGB", (w * cols, h * rows), "black")
        draw = ImageDraw.Draw(sheet)
        font = _font(max(16, w // 22))
        labels = []
        for k, ((t, _), im) in enumerate(zip(chunk, imgs)):
            x, y = (k % cols) * w, (k // cols) * h
            sheet.paste(im.resize((w, h)), (x, y))
            text = label(t)
            labels.append(text)
            box = draw.textbbox((x + 6, y + 6), text, font=font)
            draw.rectangle((box[0] - 4, box[1] - 3, box[2] + 4, box[3] + 3), fill="black")
            draw.text((x + 6, y + 6), text, fill="yellow", font=font)
        f = outdir / f"{prefix}_{n:02d}.jpg"
        sheet.save(f, quality=82)
        out.append((f, labels))
    return out
