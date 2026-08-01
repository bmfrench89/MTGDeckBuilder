"""The PWA — what makes "Add to Home Screen" produce an app rather than a bookmark."""
import json
import os
import re
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "webapp", "static")


def _manifest():
    with open(os.path.join(STATIC, "manifest.webmanifest"), encoding="utf-8") as f:
        return json.load(f)


def test_manifest_is_installable():
    m = _manifest()
    assert m["display"] == "standalone"
    assert m["start_url"] and m["scope"]
    assert m["name"] and m["short_name"]


def test_manifest_ships_real_png_icons():
    """Android launchers want PNG; an SVG-only manifest often falls back to a globe."""
    m = _manifest()
    pngs = [i for i in m["icons"] if i["type"] == "image/png"]
    assert {i["sizes"] for i in pngs} >= {"192x192", "512x512"}
    assert any(i.get("purpose") == "maskable" for i in pngs)


def test_icons_exist_and_match_their_declared_size():
    for size in (192, 512):
        p = os.path.join(STATIC, f"icon-{size}.png")
        data = open(p, "rb").read()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{p} is not a PNG"
        w, h = struct.unpack(">II", data[16:24])
        assert (w, h) == (size, size), f"{p} is {w}x{h}, manifest claims {size}x{size}"


def test_service_worker_never_caches_deck_or_collection_pages():
    """The core design rule. Decks change on every optimize — serving a cached list would
    confidently show the wrong 100 cards, which is worse than an error."""
    sw = open(os.path.join(STATIC, "sw.js"), encoding="utf-8").read()
    shell = re.search(r"const SHELL = \[(.*?)\];", sw, re.S).group(1)
    for path in re.findall(r"'([^']+)'", shell):
        assert path.startswith("/static/"), f"{path} must not be pre-cached"
    assert "network only" in sw.lower() or "fetch(e.request).catch" in sw


def test_service_worker_is_served_from_the_root():
    """A worker can only control pages at or below its own path — at /static/sw.js it
    could never manage the app."""
    app_py = open(os.path.join(ROOT, "webapp", "app.py"), encoding="utf-8").read()
    assert '@app.route("/sw.js")' in app_py


def test_icon_generator_is_reproducible_and_dependency_free():
    src = open(os.path.join(ROOT, "scripts", "make_icons.py"), encoding="utf-8").read()
    for banned in ("import PIL", "from PIL", "cairosvg", "import numpy"):
        assert banned not in src, f"icon generator must stay stdlib-only ({banned})"
