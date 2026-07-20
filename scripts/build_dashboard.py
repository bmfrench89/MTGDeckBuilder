#!/usr/bin/env python3
"""Generate a self-contained HTML dashboard (and optional visual card gallery)
for a Commander deck.

The dashboard is a single HTML file with inline CSS and an inline SVG mana curve
— it renders anywhere, including the chat preview. The visual gallery hotlinks
Scryfall card images and therefore ONLY renders in a real browser (warn the
player — see tooling-and-data.md).

Usage:
  python3 build_dashboard.py --deck data/decks/d.txt --collection coll.csv \
      --title "Y'shtola, Night's Blessed" --commander "Y'shtola, Night's Blessed" \
      --theme yshtola --out yshtola-dashboard.html
  # add --visual to also emit <out>-visual.html with card images (needs CSV IDs)

Themes: yshtola (Esper), cloud (Naya/Mako), default (neutral dark). Any theme
name not listed falls back to default.
"""
import argparse
import html
import sys
from collections import Counter

import mtglib
import deck_stats
import card_image

THEMES = {
    "default": {
        "void": "#0d1117", "panel": "#161b22", "accent": "#58a6ff",
        "accent2": "#3fb950", "warn": "#d29922", "text": "#e6edf3",
        "muted": "#8b949e", "gold": "#d9b26a",
        "display": "'Georgia', serif", "head": "'Trebuchet MS', sans-serif",
        "mono": "'Consolas', monospace", "fonts_link": "",
    },
    "yshtola": {  # dark FFXIV Esper aesthetic
        "void": "#0B0E1A", "panel": "#141a2e", "accent": "#5BE0D4",
        "accent2": "#8aa0d8", "warn": "#C2415C", "text": "#e8ecf5",
        "muted": "#8792ad", "gold": "#D9B26A",
        "display": "'Cormorant Garamond', serif",
        "head": "'Barlow Condensed', sans-serif",
        "mono": "'IBM Plex Mono', monospace",
        "fonts_link": ("https://fonts.googleapis.com/css2?"
                       "family=Cormorant+Garamond:wght@500;600;700&"
                       "family=Barlow+Condensed:wght@500;600&"
                       "family=IBM+Plex+Mono&display=swap"),
    },
    "spider": {  # 5-color web / Spider-Verse aesthetic
        "void": "#0A0A12", "panel": "#15121f", "accent": "#E23B4E",
        "accent2": "#3AA0FF", "warn": "#E8B84B", "text": "#eef0f7",
        "muted": "#8a86a0", "gold": "#E23B4E",
        "display": "'Oswald', sans-serif", "head": "'Rajdhani', sans-serif",
        "mono": "'JetBrains Mono', monospace",
        "fonts_link": ("https://fonts.googleapis.com/css2?"
                       "family=Oswald:wght@500;600;700&"
                       "family=Rajdhani:wght@500;600;700&"
                       "family=JetBrains+Mono&display=swap"),
    },
    "cloud": {  # Mako Naya aesthetic
        "void": "#0E1214", "panel": "#171e20", "accent": "#39E0B0",
        "accent2": "#E8B84B", "warn": "#E86A3A", "text": "#eaf2ef",
        "muted": "#8aa39b", "gold": "#E8B84B",
        "display": "'Oswald', sans-serif", "head": "'Rajdhani', sans-serif",
        "mono": "'JetBrains Mono', monospace",
        "fonts_link": ("https://fonts.googleapis.com/css2?"
                       "family=Oswald:wght@500;600;700&"
                       "family=Rajdhani:wght@500;600;700&"
                       "family=JetBrains+Mono&display=swap"),
    },
}

COLOR_HEX = {"W": "#f4efd6", "U": "#3b7fd4", "B": "#7a5b8c",
             "R": "#d3492f", "G": "#3f9d5a"}
COLOR_NAME = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


def esc(s):
    return html.escape(str(s))


def curve_svg(curve, t):
    if not curve:
        return "<p class='muted'>Mana curve unavailable (load the CSV for MV data).</p>"
    bars = [(f"{b}+" if b == 7 else str(b), curve.get(str(b), 0)) for b in range(8)]
    maxv = max((v for _, v in bars), default=1) or 1
    w, h, pad, bw = 520, 200, 28, 52
    parts = [f"<svg viewBox='0 0 {w} {h}' width='100%' role='img' "
             "aria-label='Mana curve'>"]
    for i, (label, v) in enumerate(bars):
        bh = int((h - 2 * pad) * (v / maxv))
        x = pad + i * (bw + 8)
        y = h - pad - bh
        parts.append(
            f"<rect x='{x}' y='{y}' width='{bw}' height='{bh}' rx='4' "
            f"fill='{t['accent']}' opacity='0.85'></rect>")
        parts.append(
            f"<text x='{x + bw/2:.0f}' y='{y - 6}' fill='{t['text']}' "
            f"font-size='13' text-anchor='middle'>{v}</text>")
        parts.append(
            f"<text x='{x + bw/2:.0f}' y='{h - pad + 16}' fill='{t['muted']}' "
            f"font-size='12' text-anchor='middle'>{label}</text>")
    parts.append("</svg>")
    return "".join(parts)


def stat_tile(label, value, note=""):
    note_html = f"<div class='tile-note'>{esc(note)}</div>" if note else ""
    return (f"<div class='tile'><div class='tile-val'>{esc(value)}</div>"
            f"<div class='tile-label'>{esc(label)}</div>{note_html}</div>")


def pip_table(rep):
    if not rep["pip_demand"]:
        return ("<p class='muted'>Pip demand unavailable "
                "(load the CSV for mana costs).</p>")
    src = rep["color_sources"] or {}
    rows = []
    for c in "WUBRG":
        dem = rep["pip_demand"].get(c, 0)
        if not dem and not src.get(c):
            continue
        dbl = (rep["double_pips"] or {}).get(c, 0)
        s = src.get(c, 0)
        warn = " class='warn'" if (dem and s and s < dem * 0.4) else ""
        rows.append(
            f"<tr{warn}><td><span class='pip' style='background:{COLOR_HEX[c]}'>"
            f"</span>{COLOR_NAME[c]}</td><td>{dem:g}</td><td>{dbl}</td>"
            f"<td>{s if src else '—'}</td></tr>")
    src_hdr = "Sources" if src else "Sources (need CSV)"
    return ("<table class='data'><thead><tr><th>Color</th><th>Pip demand</th>"
            f"<th>Double-pip cards</th><th>{src_hdr}</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def ownership_block(rep):
    prob = rep["quantity_problems"]
    if not prob:
        return ("<div class='ok'>✅ Every card in this list is owned in "
                "sufficient quantity.</div>")
    items = "".join(
        f"<li><b>{esc(n)}</b> — deck wants {w}, you own {o}</li>"
        for n, w, o in prob)
    return (f"<div class='warnbox'><b>Buy-list candidates "
            f"({len(prob)}):</b><ul>{items}</ul></div>")


def card_rows(enriched):
    order = ["Land", "Creature", "Planeswalker", "Artifact", "Enchantment",
             "Instant", "Sorcery", "Battle", "Unknown"]
    groups = {}
    for c in enriched:
        pt = c.primary_type if c.types else "Unknown"
        groups.setdefault(pt, []).append(c)
    out = []
    for pt in order:
        if pt not in groups:
            continue
        cards = sorted(groups[pt], key=lambda x: (x.mana_value or 0, x.name))
        n = sum(c.quantity for c in cards)
        out.append(f"<h3>{esc(pt)} <span class='count'>{n}</span></h3><ul class='cards'>")
        for c in cards:
            mv = f"<span class='mv'>{c.mana_value:g}</span>" if c.mana_value is not None else ""
            qty = f"{c.quantity}× " if c.quantity > 1 else ""
            out.append(f"<li>{mv}{qty}{esc(c.name)}</li>")
        out.append("</ul>")
    return "".join(out)


def render_dashboard(title, commander, subtitle, rep, enriched, theme):
    t = THEMES.get(theme, THEMES["default"])
    fonts = (f"<link rel='preconnect' href='https://fonts.googleapis.com'>"
             f"<link href='{t['fonts_link']}' rel='stylesheet'>"
             if t["fonts_link"] else "")
    cats = rep["categories"]
    tiles = "".join([
        stat_tile("Total", rep["total_cards"], "incl. commander"),
        stat_tile("Lands", rep["lands"], deck_stats._flag("lands", rep["lands"]).strip("()")),
        stat_tile("Ramp", cats.get("ramp", 0)),
        stat_tile("Draw", cats.get("draw", 0)),
        stat_tile("Removal", cats.get("removal", 0)),
        stat_tile("Wipes", cats.get("wipe", 0)),
    ])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>{fonts}
<style>
:root {{
  --void:{t['void']}; --panel:{t['panel']}; --accent:{t['accent']};
  --accent2:{t['accent2']}; --warn:{t['warn']}; --text:{t['text']};
  --muted:{t['muted']}; --gold:{t['gold']};
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--void); color:var(--text);
  font-family:{t['head']}; line-height:1.5; }}
.wrap {{ max-width:960px; margin:0 auto; padding:32px 20px 64px; }}
header h1 {{ font-family:{t['display']}; font-size:2.6rem; margin:0 0 4px;
  color:var(--accent); letter-spacing:.5px; }}
header .sub {{ color:var(--muted); font-size:1.05rem; }}
header .cmd {{ color:var(--gold); font-family:{t['mono']}; font-size:.95rem;
  margin-top:6px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:12px; margin:28px 0; }}
.tile {{ background:var(--panel); border:1px solid rgba(255,255,255,.06);
  border-radius:12px; padding:16px; text-align:center; }}
.tile-val {{ font-family:{t['display']}; font-size:2rem; color:var(--accent2);
  line-height:1; }}
.tile-label {{ color:var(--muted); text-transform:uppercase; font-size:.72rem;
  letter-spacing:1.5px; margin-top:6px; }}
.tile-note {{ color:var(--muted); font-size:.68rem; margin-top:4px; }}
section {{ background:var(--panel); border:1px solid rgba(255,255,255,.06);
  border-radius:14px; padding:20px 22px; margin:18px 0; }}
section h2 {{ font-family:{t['display']}; margin:0 0 12px; color:var(--accent);
  font-size:1.4rem; }}
table.data {{ width:100%; border-collapse:collapse; font-family:{t['mono']};
  font-size:.9rem; }}
table.data th, table.data td {{ text-align:left; padding:7px 10px;
  border-bottom:1px solid rgba(255,255,255,.07); }}
table.data th {{ color:var(--muted); font-weight:600; }}
tr.warn td {{ color:var(--warn); }}
.pip {{ display:inline-block; width:12px; height:12px; border-radius:50%;
  margin-right:8px; vertical-align:middle;
  box-shadow:0 0 0 1px rgba(0,0,0,.4) inset; }}
.ok {{ color:var(--accent2); font-weight:600; }}
.warnbox {{ color:var(--warn); }}
.warnbox ul {{ margin:8px 0 0; padding-left:18px; }}
.muted {{ color:var(--muted); }}
h3 {{ font-family:{t['head']}; color:var(--gold); margin:18px 0 6px;
  border-bottom:1px solid rgba(255,255,255,.08); padding-bottom:4px; }}
h3 .count {{ color:var(--muted); font-size:.85rem; float:right; }}
ul.cards {{ list-style:none; padding:0; margin:0; columns:2; column-gap:24px;
  font-family:{t['mono']}; font-size:.85rem; }}
ul.cards li {{ break-inside:avoid; padding:2px 0; }}
.mv {{ display:inline-block; min-width:20px; color:var(--accent);
  font-size:.75rem; }}
footer {{ color:var(--muted); font-size:.8rem; margin-top:30px;
  text-align:center; }}
@media (max-width:560px) {{ ul.cards {{ columns:1; }} header h1 {{ font-size:2rem; }} }}
</style></head><body><div class="wrap">
<header>
  <h1>{esc(title)}</h1>
  <div class="sub">{esc(subtitle)}</div>
  {f'<div class="cmd">Commander: {esc(commander)}</div>' if commander else ''}
</header>
<div class="tiles">{tiles}</div>
<section><h2>Mana Curve</h2>{curve_svg(rep['curve'], t)}</section>
<section><h2>Color / Pip Demand</h2>{pip_table(rep)}</section>
<section><h2>Ownership</h2>{ownership_block(rep)}</section>
<section><h2>Decklist</h2>{card_rows(enriched)}</section>
<footer>Generated by the MTG Commander Deckbuilder. Category counts are
heuristic — verify uncertain cards. Prices, if any, are estimates.</footer>
</div></body></html>"""


def render_visual(title, deck, idx, theme, size="normal"):
    t = THEMES.get(theme, THEMES["default"])
    tiles = []
    missing = 0
    for d in deck:
        ref = mtglib.lookup(idx, d.name)
        if ref and ref.scryfall_id:
            url = card_image.image_url(ref.scryfall_id, size)
            tiles.append(
                f"<figure><img loading='lazy' src='{esc(url)}' "
                f"alt='{esc(d.name)}'><figcaption>{esc(d.name)}</figcaption></figure>")
        else:
            missing += 1
            tiles.append(
                f"<figure class='noimg'><div class='ph'>{esc(d.name)}</div>"
                f"<figcaption>no Scryfall ID</figcaption></figure>")
    warn = ("" if not missing else
            f"<p class='warn'>{missing} card(s) had no Scryfall ID "
            "(need the CSV export).</p>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} — Visual</title>
<style>
body {{ margin:0; background:{t['void']}; color:{t['text']};
  font-family:{t['head']}; }}
.wrap {{ max-width:1200px; margin:0 auto; padding:28px 18px 60px; }}
h1 {{ font-family:{t['display']}; color:{t['accent']}; }}
.banner {{ background:{t['warn']}22; border:1px solid {t['warn']};
  color:{t['text']}; padding:12px 16px; border-radius:10px; margin:12px 0 24px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr));
  gap:16px; }}
figure {{ margin:0; }}
figure img {{ width:100%; border-radius:4.75% / 3.5%; display:block; }}
figcaption {{ font-family:{t['mono']}; font-size:.72rem; color:{t['muted']};
  margin-top:5px; text-align:center; }}
.noimg .ph {{ aspect-ratio:5/7; background:{t['panel']}; border-radius:8px;
  display:flex; align-items:center; justify-content:center; padding:10px;
  text-align:center; font-family:{t['mono']}; font-size:.8rem; }}
.warn {{ color:{t['warn']}; }}
</style></head><body><div class="wrap">
<h1>{esc(title)}</h1>
<div class="banner"><b>Heads up:</b> this gallery hotlinks Scryfall card images.
It will <b>not</b> render in the chat preview — open it in a real browser
(Chrome / Safari / Edge).</div>
{warn}
<div class="grid">{''.join(tiles)}</div>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Build a deck dashboard.")
    ap.add_argument("--deck", required=True)
    ap.add_argument("--collection", required=True)
    ap.add_argument("--title", default="Commander Deck")
    ap.add_argument("--commander", default="")
    ap.add_argument("--subtitle", default="Commander (EDH) deck dashboard")
    ap.add_argument("--theme", default="default",
                    help="yshtola | cloud | default")
    ap.add_argument("--out", default="dashboard.html")
    ap.add_argument("--visual", action="store_true",
                    help="also write <out>-visual.html with card images")
    ap.add_argument("--size", default="normal", help="image size for --visual")
    args = ap.parse_args()

    try:
        with open(args.deck, encoding="utf-8") as f:
            deck = mtglib.parse_deck(f.read())
        with open(args.collection, encoding="utf-8") as f:
            coll = mtglib.parse_collection(f.read())
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    idx = mtglib.index_by_name(coll)
    enriched, missing = deck_stats.analyze(deck, idx)
    rep = deck_stats.build_report(deck, enriched, missing, idx)

    html_doc = render_dashboard(args.title, args.commander, args.subtitle,
                                rep, enriched, args.theme)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"wrote dashboard: {args.out}")

    if args.visual:
        vpath = (args.out[:-5] if args.out.endswith(".html") else args.out) + "-visual.html"
        with open(vpath, "w", encoding="utf-8") as f:
            f.write(render_visual(args.title, deck, idx, args.theme, args.size))
        print(f"wrote visual gallery: {vpath}  (open in a real browser)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
