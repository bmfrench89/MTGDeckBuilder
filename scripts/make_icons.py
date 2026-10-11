#!/usr/bin/env python3
"""Generate the PWA's PNG app icons from the same geometry as static/icon.svg.

Android launchers want PNGs; an SVG-only manifest often falls back to a generic globe
when you "Add to Home Screen". Rather than add an imaging dependency to a stdlib-only
toolkit, this rasterises the icon's geometry directly and writes PNGs with `zlib` +
`struct`.

The geometry is three nested diamonds (the Arcane Ledger mark), so the
rasteriser is one comparison per pixel. 4x supersampling gives clean edges.
Rerun after changing icon.svg:

  python3 scripts/make_icons.py
"""
import argparse
import math
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "webapp", "static")
BG = (0x0F, 0x11, 0x15)      # Arcane Ledger ink
AMBER = (0xF2, 0xB5, 0x44)   # the one accent
SS = 4                      # supersampling factor

# The mark: nested diamonds |x-256| + |y-256| <= r, alternating amber / ink /
# amber — the same three paths as static/icon.svg. Everything sits inside the
# central 80% circle, so the maskable variant survives any launcher's crop.
DIAMONDS = ((160.0, AMBER), (80.0, BG), (30.0, AMBER))


def render(size):
    """Draw the icon at `size` px (supersampled), return an RGB bytearray."""
    n = size * SS
    scale = n / 512.0
    radius = 96.0 * scale                   # the background's rounded corners
    buf = bytearray(n * n * 3)
    for y in range(n):
        py = (y + 0.5) / scale
        gy = y + 0.5
        for x in range(n):
            px = (x + 0.5) / scale
            gx = x + 0.5
            rgb = BG
            # rounded-rect mask: corners outside the radius go black
            cx = radius if gx < radius else (n - radius if gx > n - radius else None)
            cy = radius if gy < radius else (n - radius if gy > n - radius else None)
            if cx is not None and cy is not None and math.hypot(gx - cx, gy - cy) > radius:
                rgb = (0, 0, 0)
            else:
                d = abs(px - 256.0) + abs(py - 256.0)
                for r, colour in DIAMONDS:
                    if d <= r:
                        rgb = colour
            i = (y * n + x) * 3
            buf[i], buf[i + 1], buf[i + 2] = rgb
    return _downsample(buf, n, size)


def _downsample(buf, n, size):
    out = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            r = g = b = 0
            for sy in range(SS):
                for sx in range(SS):
                    i = ((y * SS + sy) * n + (x * SS + sx)) * 3
                    r += buf[i]; g += buf[i + 1]; b += buf[i + 2]
            k = (y * size + x) * 3
            t = SS * SS
            out[k], out[k + 1], out[k + 2] = r // t, g // t, b // t
    return out


def write_png(path, rgb, size):
    """Minimal PNG writer — stdlib only."""
    raw = b"".join(b"\x00" + bytes(rgb[y * size * 3:(y + 1) * size * 3])
                   for y in range(size))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def main(argv=None):
    # A real parser, so `--help` (which every script in this repo takes) prints help
    # instead of silently overwriting the tracked icons — it did, twice, during the
    # 2026-10-11 audit (R16).
    ap = argparse.ArgumentParser(
        description="Regenerate webapp/static/icon-192.png and icon-512.png from "
                    "the geometry of static/icon.svg (overwrites both files).")
    ap.add_argument("--out", default=OUT, help="output directory (default: %(default)s)")
    args = ap.parse_args(argv)
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    for size in (192, 512):
        rgb = render(size)
        path = os.path.join(out_dir, f"icon-{size}.png")
        n = write_png(path, rgb, size)
        print(f"wrote {os.path.relpath(path)} ({size}x{size}, {n:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
