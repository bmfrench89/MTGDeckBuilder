#!/usr/bin/env python3
"""Generate the PWA's PNG app icons from the same geometry as static/icon.svg.

Android launchers want PNGs; an SVG-only manifest often falls back to a generic globe
when you "Add to Home Screen". Rather than add an imaging dependency to a stdlib-only
toolkit, this rasterises the icon's geometry directly (it's lines, an octagon and a
circle) and writes PNGs with `zlib` + `struct`.

4x supersampling gives clean edges. Rerun after changing icon.svg:

  python3 scripts/make_icons.py
"""
import math
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "webapp", "static")
BG = (0x0b, 0x0d, 0x13)
ACCENT = (0x5B, 0xE0, 0xD4)
DOT = (0xE2, 0x3B, 0x4E)
SS = 4                      # supersampling factor


def _blend(dst, i, rgb, a):
    """Alpha-composite a colour onto the RGB buffer at pixel index i."""
    if a <= 0:
        return
    a = min(1.0, a)
    for c in range(3):
        dst[i * 3 + c] = int(dst[i * 3 + c] * (1 - a) + rgb[c] * a)


def _seg_dist(px, py, x1, y1, x2, y2):
    """Distance from a point to a line segment — used to draw round-capped strokes."""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def render(size):
    """Draw the icon at `size` px (supersampled), return an RGB bytearray."""
    n = size * SS
    scale = n / 512.0
    buf = bytearray()
    for _ in range(n * n):
        buf += bytes(BG)

    cx = cy = 256.0
    spokes = [(256, 70), (256, 442), (70, 256), (442, 256),
              (124, 124), (388, 124), (124, 388), (388, 388)]
    oct_out = [(256, 132), (360, 152), (380, 256), (360, 360),
               (256, 380), (152, 360), (132, 256), (152, 152)]
    oct_in = [(256, 180), (322, 196), (336, 256), (322, 316),
              (256, 332), (190, 316), (176, 256), (190, 196)]

    def ring(pts):
        return [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]

    strokes = ([((cx, cy), p, 0.9) for p in spokes]
               + [(a, b, 0.5) for a, b in ring(oct_out)]
               + [(a, b, 0.7) for a, b in ring(oct_in)])
    half = 5.0 * scale                      # stroke-width 10 in the SVG
    radius = 96.0 * scale                   # the background's rounded corners

    for y in range(n):
        for x in range(n):
            i = y * n + x
            px, py = (x + 0.5) / scale, (y + 0.5) / scale
            # rounded-rect mask: knock the corners out to transparent-looking bg
            gx, gy = x + 0.5, y + 0.5
            for ox, oy in ((radius, radius), (n - radius, radius),
                           (radius, n - radius), (n - radius, n - radius)):
                if ((gx < radius) == (ox == radius)) and ((gy < radius) == (oy == radius)):
                    if math.hypot(gx - ox, gy - oy) > radius:
                        buf[i * 3:i * 3 + 3] = bytes((0, 0, 0))
                    break
            best = 0.0
            for a, b, op in strokes:
                d = _seg_dist(px, py, a[0], a[1], b[0], b[1]) * scale
                if d <= half:
                    best = max(best, op)
            if best:
                _blend(buf, i, ACCENT, best)
            if math.hypot(px - cx, py - cy) <= 30.0:
                _blend(buf, i, DOT, 1.0)
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


def main():
    os.makedirs(OUT, exist_ok=True)
    for size in (192, 512):
        rgb = render(size)
        path = os.path.join(OUT, f"icon-{size}.png")
        n = write_png(path, rgb, size)
        print(f"wrote {os.path.relpath(path)} ({size}x{size}, {n:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
