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
import csv
import html
import json
import os
import re
import sys
from collections import Counter

import mtglib
import deck_stats
import card_image
import deck_conflicts
import power
import deck_fit
import similar_commanders as simc

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
    "rakdos": {  # Rakdos punisher — blood & ember
        "void": "#120A0C", "panel": "#1e1214", "accent": "#E23B3B",
        "accent2": "#E8843A", "warn": "#E8B84B", "text": "#f0e6e6",
        "muted": "#a3888a", "gold": "#E8843A",
        "display": "'Oswald', sans-serif", "head": "'Rajdhani', sans-serif",
        "mono": "'JetBrains Mono', monospace",
        "fonts_link": ("https://fonts.googleapis.com/css2?"
                       "family=Oswald:wght@500;600;700&"
                       "family=Rajdhani:wght@500;600;700&"
                       "family=JetBrains+Mono&display=swap"),
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


# Card images come from Scryfall's /cards/named API, which is rate-limited to
# ~10 req/s. Firing ~80 <img> loads at once gets the later ones 429'd (blank).
# This loads them from a throttled queue (~9/s) with a one-time retry, so they
# all appear. Images use data-src; this script assigns src on a timer.
IMG_LOADER = """<script>
(function(){
  var q=[].slice.call(document.querySelectorAll('img[data-src]'));
  var t=setInterval(function(){
    var img=q.shift();
    if(!img){clearInterval(t);return;}
    img.onerror=function(){var s=img.getAttribute('data-src');img.onerror=null;
      setTimeout(function(){img.src=s;},1500);};
    img.src=img.getAttribute('data-src');
  },110);
})();
</script>"""


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


# --------------------------------------------------------------------------- #
# Optional companion files (auto-detected next to the deck: <stem>.notes.md,
# <stem>.buylist.csv, <stem>.attrs.csv)
# --------------------------------------------------------------------------- #
def load_deck_sections(path):
    """Group the deck by the `# --- Label ---` headers in the deck file itself,
    so each build sections its own way ("Spiders", "Ramp", ...)."""
    sections, cur = [], None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            s = raw.strip()
            if not s:
                continue
            if s.startswith("#"):
                m = re.search(r"---\s*(.*?)\s*---", s)
                if m:
                    label = re.sub(r"\s*\(\d+\)\s*$", "", m.group(1)).strip()
                    cur = (label, [])
                    sections.append(cur)
                continue
            m = re.match(r"^(\d+)\s*[xX]?\s+(.*\S)$", s)
            qty, name = (int(m.group(1)), m.group(2).strip()) if m else (1, s)
            if cur is None:
                cur = ("Cards", [])
                sections.append(cur)
            cur[1].append((qty, name))
    return sections


def load_notes(path):
    return open(path, encoding="utf-8").read() if path and os.path.exists(path) else None


def load_buylist(path):
    if not (path and os.path.exists(path)):
        return None
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({
                "card": (r.get("Card") or "").strip(),
                "price": _to_float_price(r.get("Price")),
                "tier": (r.get("Tier") or "").strip(),
                "replaces": (r.get("Replaces") or "").strip(),
                "reason": (r.get("Reason") or "").strip(),
            })
    return [r for r in rows if r["card"]]


def load_attrs(path):
    """Optional name -> {type, mv} map to power the MV spread without the full CSV."""
    if not (path and os.path.exists(path)):
        return None
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("Name") or r.get("Card") or "").strip()
            if not name:
                continue
            mv = _to_float_price(r.get("MV"))
            out[mtglib._norm(name)] = {
                "type": (r.get("Type") or "").strip(),
                "mv": mv,
                "colors": (r.get("Colors") or "").strip(),
            }
    return out


def _to_float_price(s):
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _default_notes_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "reference", "card_notes.csv")


def load_card_notes(path=None):
    """name(normalized) -> {"why": str, "alts": [names]}. The curated, editable
    knowledge base behind the click-a-card panel. First row per name wins."""
    path = path or _default_notes_path()
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("Name") or r.get("Card") or "").strip()
            if not name:
                continue
            k = mtglib._norm(name)
            if k in out:
                continue
            alts = [a.strip() for a in re.split(r"[;|]", r.get("Alternatives") or "")
                    if a.strip()]
            out[k] = {"why": (r.get("Why") or "").strip(), "alts": alts}
    return out


_ROLE_LABEL = {
    "ramp": "Ramp / mana acceleration", "draw": "Card advantage",
    "removal": "Targeted removal", "wipe": "Board wipe", "counter": "Counterspell",
    "land": "Land", "creature": "Creature", "spell": "Instant / sorcery",
    "artifact": "Artifact", "enchantment": "Enchantment",
    "planeswalker": "Planeswalker", "other": "Deck card",
}


def build_card_details(sections, enriched, idx, notes, rep=None, ctx=None,
                       refs=None, staples=None, size="normal"):
    """Per-card payload for the click-to-enlarge panel: enlarged image, a grounded
    generic 'why it works' blurb, a deck-specific fit score + how-it-fits line, and
    alternatives / stronger options tagged owned/buy."""
    en = {mtglib._norm(c.name): c for c in enriched}
    in_deck = set(en.keys())
    details = {}
    for _, cards in sections:
        for _q, name in cards:
            k = mtglib._norm(name)
            if k in details:
                continue
            c = en.get(k)
            sid = c.scryfall_id if (c and c.scryfall_id) else ""
            full = (card_image.image_url(sid, size) if sid
                    else card_image.image_url_by_name(name, size))
            roles = mtglib.classify(c) if c else set()
            role = " · ".join(_ROLE_LABEL.get(r, r.title()) for r in sorted(roles))
            note = notes.get(k)

            fit = None
            if c is not None and rep is not None and ctx is not None and refs is not None:
                try:
                    fit = deck_fit.assess_card(c, rep, ctx, refs)
                except Exception:
                    fit = None

            curated = note["alts"] if note else []
            if c is not None and ctx is not None and refs is not None:
                try:
                    alt_src = deck_fit.better_alternatives(
                        c, ctx, idx, refs, curated, in_deck, staples or {})
                except Exception:
                    alt_src = [{"n": a, "owned": mtglib.lookup(idx, a) is not None,
                                "upgrade": False, "why": ""} for a in curated]
            else:
                alt_src = [{"n": a, "owned": mtglib.lookup(idx, a) is not None,
                            "upgrade": False, "why": ""} for a in curated]

            alts = []
            for a in alt_src:
                ref = mtglib.lookup(idx, a["n"])
                asid = ref.scryfall_id if (ref and ref.scryfall_id) else ""
                aimg = (card_image.image_url(asid, "small") if asid
                        else card_image.image_url_by_name(a["n"], "small"))
                alts.append({"n": a["n"], "img": aimg, "owned": a["owned"],
                             "upgrade": a.get("upgrade", False), "why": a.get("why", "")})

            details[k] = {"name": name, "full": full, "role": role,
                          "why": note["why"] if note else "", "fit": fit, "alts": alts}
    return details


def apply_attrs(enriched, attrs):
    """Overlay type/MV/colors from an attrs map onto enriched deck cards."""
    if not attrs:
        return 0
    n = 0
    for c in enriched:
        a = attrs.get(mtglib._norm(c.name))
        if not a:
            continue
        n += 1
        if a["type"]:
            c.types = [a["type"]]
        if a["mv"] is not None:
            c.mana_value = a["mv"]
        if a["colors"]:
            c.identity = mtglib._parse_colorish(a["colors"])
    return n


# --------------------------------------------------------------------------- #
# Section renderers
# --------------------------------------------------------------------------- #
def notes_html(text):
    def bold(s):
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(s))
    out, inlist = [], False
    for raw in text.splitlines():
        s = raw.rstrip()
        if not s.strip():
            if inlist:
                out.append("</ul>"); inlist = False
            continue
        if s.startswith("## ") or s.startswith("# "):
            if inlist:
                out.append("</ul>"); inlist = False
            out.append(f"<h3>{bold(s.lstrip('# '))}</h3>")
        elif s.lstrip().startswith(("- ", "* ")):
            if not inlist:
                out.append("<ul class='notes'>"); inlist = True
            out.append(f"<li>{bold(s.lstrip()[2:])}</li>")
        else:
            if inlist:
                out.append("</ul>"); inlist = False
            out.append(f"<p>{bold(s)}</p>")
    if inlist:
        out.append("</ul>")
    return "".join(out)


def _share_badge(k, shared):
    """A ⇄ badge for cards used in more than one deck."""
    if not shared or k not in shared:
        return ""
    v = shared[k]
    cls = "sb" if v["covered"] else "sb need"
    others = [d for d in v["decks"]]
    title = ("also in: " + ", ".join(others) +
             ("" if v["covered"] else f" — own {v['owned']}, need more"))
    return f"<span class='{cls}' title='{esc(title)}'>⇄{len(v['decks'])}</span>"


def sections_html(sections, enriched, shared=None, images=True, size="small"):
    mv = {mtglib._norm(c.name): c.mana_value for c in enriched}
    pr = {mtglib._norm(c.name): c.price for c in enriched}
    sid = {mtglib._norm(c.name): c.scryfall_id for c in enriched if c.scryfall_id}
    out = []
    if images:
        out.append("<p class='muted imgnote'>Card images load live from Scryfall "
                   "when opened in a browser. <b>Click any card</b> to enlarge it and "
                   "see why it's here plus alternatives. <span class='sb'>⇄</span> marks "
                   "a card shared with another deck (<span class='sb need'>⇄</span> = "
                   "you'd need more copies).</p>")
    for label, cards in sections:
        n = sum(q for q, _ in cards)
        out.append(f"<h3>{esc(label)} <span class='count'>{n}</span></h3>")
        if images:
            out.append("<div class='cardgrid'>")
            for q, name in cards:
                k = mtglib._norm(name)
                m = mv.get(k)
                mvb = (f"<span class='mv'>{m:g}</span>" if m is not None else "")
                p = pr.get(k)
                price = f"<span class='pr'>${p:,.2f}</span>" if p else ""
                qty = f"<span class='qty'>{q}×</span>" if q > 1 else ""
                cid = sid.get(k)
                url = (card_image.image_url(cid, size) if cid
                       else card_image.image_url_by_name(name, size))
                out.append(
                    f"<figure class='mc' data-key='{esc(k)}' tabindex='0' "
                    f"role='button' aria-label='{esc(name)} — details'>"
                    f"<img loading='lazy' data-src='{esc(url)}' "
                    f"alt='{esc(name)}'>{qty}{_share_badge(k, shared)}"
                    f"<figcaption>{mvb}{esc(name)}{price}</figcaption></figure>")
            out.append("</div>")
        else:
            out.append("<ul class='cards'>")
            for q, name in cards:
                k = mtglib._norm(name)
                m = mv.get(k)
                mvb = (f"<span class='mv'>{m:g}</span>" if m is not None
                       else "<span class='mv dim'>·</span>")
                p = pr.get(k)
                price = f"<span class='pr'>${p:,.2f}</span>" if p else ""
                qty = f"{q}× " if q > 1 else ""
                out.append(f"<li>{mvb}{qty}{esc(name)}"
                           f"{_share_badge(k, shared)}{price}</li>")
            out.append("</ul>")
    return "".join(out)


def shared_html(shared):
    if shared is None:
        return ""
    if not shared:
        return ("<div class='ok'>No cards in this deck are used in any other deck — "
                "it's fully self-contained.</div>")
    items = sorted(shared.items(), key=lambda kv: (kv[1]["covered"], kv[0]))
    short = [1 for _, v in items if not v["covered"]]
    rows = []
    for _, v in items:
        others = [d for d in v["decks"]]
        mark = ("<span class='ok'>✓ own enough</span>" if v["covered"]
                else "<span class='need'>⚠ need more copies</span>")
        rows.append(
            f"<tr><td class='bc'>{esc(v['name'])}</td>"
            f"<td>{mark}</td>"
            f"<td class='br'>own {v['owned']} · in {len(v['decks'])} decks: "
            f"{esc(', '.join(others))}</td></tr>")
    note = (f"<div class='muted'>{len(shared)} card(s) here are shared with your other "
            "decks. <b>✓</b> = you own enough copies to sleeve them all at once; "
            f"<b class='need'>⚠</b> = {sum(short)} card(s) would need extra copies "
            "(they're on your <code>wishlist.md</code>). Nothing's blocked — this is "
            "just so you can see the overlap.</div>")
    return (note + "<div class='tablewrap'><table class='data'><thead><tr>"
            "<th>Card</th><th>Status</th><th>Shared with</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def curve_note(enriched):
    nonland = [c for c in enriched if not c.is_land]
    known = [c for c in nonland if c.mana_value is not None]
    if not nonland:
        return ""
    if len(known) < len(nonland):
        miss = len(nonland) - len(known)
        return (f"<p class='muted'>Curve covers {len(known)} of {len(nonland)} "
                f"nonland cards. {miss} still need mana-value data — add them to "
                "<code>&lt;deck&gt;.attrs.csv</code> or load the attribute CSV.</p>")
    return f"<p class='muted'>Curve covers all {len(known)} nonland cards.</p>"


def buylist_html(rows):
    if not rows:
        return ""
    thresholds = [5, 10, 20, 50]
    btns = "".join(
        f"<button type='button' class='thbtn' data-max='{v}'>&le;${v}</button>"
        for v in thresholds)
    body = []
    for r in rows:
        p = r["price"]
        dp = p if p is not None else 999999
        pstr = f"${p:,.2f}" if p is not None else "—"
        repl = (f"<span class='repl'>replace:</span> {esc(r['replaces'])}"
                if r["replaces"] else "<span class='muted'>new add</span>")
        tier = f"<span class='tier'>{esc(r['tier'])}</span>" if r["tier"] else ""
        body.append(
            f"<tr class='buyrow' data-price='{dp:.2f}'>"
            f"<td class='bc'>{esc(r['card'])} {tier}</td>"
            f"<td class='bp'>{pstr}</td>"
            f"<td>{repl}</td>"
            f"<td class='br'>{esc(r['reason'])}</td></tr>")
    total = sum(r["price"] for r in rows if r["price"] is not None)
    return f"""
<div class="buytoggle">
  <span class="muted">Price filter:</span>
  {btns}
  <button type="button" class="thbtn active" data-max="999999">All</button>
  <span class="buysum" id="buysum"></span>
</div>
<div class="tablewrap"><table class="data buytable">
<thead><tr><th>Buy</th><th>~Price</th><th>Swap</th><th>Why</th></tr></thead>
<tbody id="buybody">{''.join(body)}</tbody></table></div>
<p class='muted' data-total='{total:.2f}'>Prices are rough estimates (no live
price source reachable) — sanity-check before buying.</p>
<script>
(function(){{
  var body=document.getElementById('buybody');
  var sum=document.getElementById('buysum');
  var btns=document.querySelectorAll('.thbtn');
  function apply(max){{
    var rows=body.querySelectorAll('.buyrow'), shown=0, tot=0;
    rows.forEach(function(r){{
      var p=parseFloat(r.getAttribute('data-price'));
      var vis=p<=max;
      r.style.display=vis?'':'none';
      if(vis){{shown++; if(p<900000) tot+=p;}}
    }});
    sum.textContent=shown+' cards · ~$'+tot.toFixed(2);
  }}
  btns.forEach(function(b){{
    b.addEventListener('click',function(){{
      btns.forEach(function(x){{x.classList.remove('active');}});
      b.classList.add('active');
      apply(parseFloat(b.getAttribute('data-max')));
    }});
  }});
  apply(999999);
}})();
</script>"""


def power_html(a):
    reasons = "".join(f"<li>{esc(r)}</li>" for r in a["bracket_reasons"])
    bars = []
    for c in a["components"]:
        if c["score"] is None:
            bars.append(f"<tr><td>{esc(c['name'])}</td><td class='muted' "
                        f"colspan='2'>{esc(c['detail'])}</td></tr>")
            continue
        pct = 100 * c["score"] / c["weight"] if c["weight"] else 0
        bars.append(
            f"<tr><td>{esc(c['name'])}</td>"
            f"<td class='pwrbar'><span style='width:{pct:.0f}%'></span></td>"
            f"<td class='pwrnum'>{c['score']:g}/{c['weight']} "
            f"<span class='muted'>· {esc(c['detail'])}</span></td></tr>")
    return (
        f"<div class='bracketline'><span class='bnum'>Bracket {a['bracket']}</span>"
        f"<span class='bname'>{esc(a['bracket_name'])}</span>"
        f"<span class='pscore'>{a['power']}<span class='muted'>/100 · "
        f"{esc(a['tier'])}</span></span></div>"
        f"<ul class='notes'>{reasons}</ul>"
        "<table class='data pwrtable'><tbody>" + "".join(bars) + "</tbody></table>"
        "<p class='muted'>Bracket follows WotC's Commander Bracket system; the "
        "0-100 score is a countable-signal estimate — a guide, not a verdict.</p>")


SIM_LABEL = {"drop-in": "DROP-IN", "tighter": "TIGHTER", "partial": "PARTIAL",
             "reskin": "RESKIN", "unknown": "?"}


def similar_html(similar):
    if not similar:
        return ("<p class='muted'>No archetype-tagged alternates found. Tag the deck "
                "with <code># Archetype:</code> and add candidates to "
                "<code>data/reference/commanders.csv</code>.</p>")
    rows = []
    for r in similar:
        own = ("<span class='sb'>OWNED</span>" if r["owned"]
               else "<span class='muted'>buy</span>")
        pct = (f" · <span class='good'>~{r['compat_pct']}% stay in color</span>"
               if r["compat_pct"] is not None else "")
        rel = r["relation"]
        cls = "good" if rel == "drop-in" else "warn" if rel == "reskin" else ""
        rows.append(
            f"<tr><td><b>{esc(r['name'])}</b> <span class='mv'>[{esc(r['colors'])}]</span> {own}</td>"
            f"<td class='{cls}'>{SIM_LABEL.get(rel, rel)}</td>"
            f"<td class='br'>{esc(r['why'])}{pct}<br><span class='muted'>"
            f"shares {esc(', '.join(r['shared']))} · {esc(r['notes'])}</span></td></tr>")
    return ("<p class='muted'>Other commanders that play this deck's game. "
            "<b class='good'>DROP-IN</b> = your 99 stay legal · <b>TIGHTER/PARTIAL</b> = "
            "trim or rebuild some colors (colorless cards always carry) · "
            "<b class='warn'>RESKIN</b> = same idea, new shell. "
            "<span class='sb'>OWNED</span> = already on your shelf.</p>"
            "<div class='tablewrap'><table class='data'><thead><tr><th>Commander</th>"
            "<th>Fit</th><th>Why / what changes</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def card_modal_css(t):
    return f"""
.mc {{ cursor:pointer; }}
.mc:focus {{ outline:2px solid var(--accent); outline-offset:2px; }}
.mc:hover img {{ filter:brightness(1.08); }}
.cm-overlay {{ position:fixed; inset:0; background:rgba(0,0,0,.8);
  display:flex; align-items:center; justify-content:center; padding:20px; z-index:60;
  -webkit-backdrop-filter:blur(2px); backdrop-filter:blur(2px); }}
.cm-overlay[hidden] {{ display:none; }}
.cm-box {{ background:var(--panel); border:1px solid rgba(255,255,255,.12);
  border-radius:16px; max-width:760px; width:100%; max-height:92vh; overflow:auto;
  position:relative; padding:24px; }}
.cm-close {{ position:absolute; top:8px; right:14px; background:none; border:none;
  color:var(--muted); font-size:2rem; line-height:1; cursor:pointer; }}
.cm-close:hover {{ color:var(--text); }}
.cm-grid {{ display:grid; grid-template-columns:280px 1fr; gap:24px; }}
.cm-img {{ width:100%; border-radius:4.75% / 3.5%; display:block; aspect-ratio:5/7;
  object-fit:cover; background:rgba(255,255,255,.05); }}
.cm-info h3 {{ font-family:{t['display']}; color:var(--accent); margin:0 0 6px;
  font-size:1.6rem; }}
.cm-role {{ color:var(--gold); font-family:{t['mono']}; font-size:.74rem;
  text-transform:uppercase; letter-spacing:1px; margin-bottom:12px; }}
.cm-fit {{ margin:0 0 14px; }}
.cm-fithead {{ display:flex; align-items:baseline; justify-content:space-between;
  gap:10px; margin-bottom:5px; }}
.cm-fitband {{ font-family:{t['head']}; font-weight:700; text-transform:uppercase;
  letter-spacing:1px; font-size:.82rem; color:var(--accent2); }}
.cm-fitscore {{ font-family:{t['display']}; font-size:1.5rem; color:var(--accent); }}
.cm-fitscore small {{ color:var(--muted); font-size:.8rem; }}
.cm-meter {{ height:9px; border-radius:6px; background:rgba(255,255,255,.09);
  overflow:hidden; }}
.cm-meter span {{ display:block; height:100%; border-radius:6px;
  background:linear-gradient(90deg,var(--accent2),var(--accent)); }}
.cm-fitctx {{ line-height:1.55; margin:10px 0 0; }}
.cm-reasons {{ margin-top:8px; }}
.cm-reasons summary {{ color:var(--muted); cursor:pointer; font-size:.8rem;
  font-family:{t['mono']}; }}
.cm-reasons ul {{ list-style:none; padding:0; margin:8px 0 0; font-family:{t['mono']};
  font-size:.76rem; }}
.cm-reasons li {{ display:flex; justify-content:space-between; gap:12px; padding:3px 0;
  border-bottom:1px solid rgba(255,255,255,.06); }}
.cm-reasons li b {{ color:var(--text); font-weight:600; white-space:nowrap; }}
.cm-reasons li span {{ color:var(--muted); text-align:right; }}
.cm-reasons li em {{ color:var(--accent); font-style:normal; white-space:nowrap; }}
.cm-whyhead, .cm-altwrap h4 {{ color:var(--muted); text-transform:uppercase;
  font-size:.72rem; letter-spacing:1.5px; margin:16px 0 7px; }}
.cm-why {{ line-height:1.6; margin:0; }}
.cm-altwrap h4 {{ color:var(--muted); text-transform:uppercase; font-size:.72rem;
  letter-spacing:1.5px; margin:20px 0 9px; }}
.cm-alts {{ display:grid; grid-template-columns:repeat(3,1fr); gap:11px; }}
.cm-alt {{ margin:0; }}
.cm-alt img {{ width:100%; border-radius:5% / 3.6%; display:block; aspect-ratio:5/7;
  object-fit:cover; background:rgba(255,255,255,.05); }}
.cm-alt figcaption {{ font-family:{t['mono']}; font-size:.64rem; color:var(--muted);
  margin-top:3px; line-height:1.3; }}
.cm-alt .own {{ color:var(--accent2); font-weight:700; }}
.cm-alt .buy {{ color:var(--warn); font-weight:700; }}
.cm-alt .up {{ display:inline-block; background:var(--accent); color:#000;
  font-weight:700; font-size:.58rem; padding:0 4px; border-radius:6px;
  margin-left:4px; text-transform:uppercase; letter-spacing:.5px; }}
.cm-alt .altwhy {{ display:block; color:var(--muted); font-size:.6rem; margin-top:1px; }}
@media (max-width:560px) {{ .cm-grid {{ grid-template-columns:1fr; }}
  .cm-img {{ max-width:210px; margin:0 auto; }}
  .cm-alts {{ grid-template-columns:repeat(3,1fr); }} }}
"""


def card_modal_block(details):
    payload = (json.dumps(details, ensure_ascii=True)
               .replace("<", "\\u003c").replace(">", "\\u003e")
               .replace("&", "\\u0026"))
    return """
<div id="cardmodal" class="cm-overlay" hidden>
  <div class="cm-box" role="dialog" aria-modal="true" aria-label="Card details">
    <button class="cm-close" type="button" aria-label="Close">&times;</button>
    <div class="cm-grid">
      <img id="cm-img" class="cm-img" alt="">
      <div class="cm-info">
        <h3 id="cm-name"></h3>
        <div id="cm-role" class="cm-role"></div>
        <div id="cm-fit" class="cm-fit" hidden>
          <div class="cm-fithead"><span id="cm-fitband" class="cm-fitband"></span>
            <span id="cm-fitscore" class="cm-fitscore"></span></div>
          <div class="cm-meter"><span id="cm-meterbar"></span></div>
          <p id="cm-fitctx" class="cm-fitctx"></p>
          <details class="cm-reasons"><summary>How this score breaks down</summary>
            <ul id="cm-reasons"></ul></details>
        </div>
        <div id="cm-whyhead" class="cm-whyhead" hidden>Why the card is good</div>
        <p id="cm-why" class="cm-why"></p>
        <div id="cm-altwrap" class="cm-altwrap" hidden>
          <h4 id="cm-althead">Alternatives that could slot here</h4>
          <div id="cm-alts" class="cm-alts"></div>
        </div>
      </div>
    </div>
  </div>
</div>
<script>
(function(){
  var DATA=__PAYLOAD__;
  var ov=document.getElementById('cardmodal');
  var img=document.getElementById('cm-img'), nm=document.getElementById('cm-name');
  var rl=document.getElementById('cm-role'), wy=document.getElementById('cm-why');
  var wh=document.getElementById('cm-whyhead');
  var aw=document.getElementById('cm-altwrap'), al=document.getElementById('cm-alts');
  var ah=document.getElementById('cm-althead');
  var fit=document.getElementById('cm-fit'), fb=document.getElementById('cm-fitband');
  var fs=document.getElementById('cm-fitscore'), mb=document.getElementById('cm-meterbar');
  var fc=document.getElementById('cm-fitctx'), fr=document.getElementById('cm-reasons');
  function open(key){
    var d=DATA[key]; if(!d) return;
    nm.textContent=d.name;
    rl.textContent=d.role||''; rl.style.display=d.role?'':'none';
    // fit score
    if(d.fit){
      fb.textContent=d.fit.band;
      fs.innerHTML=d.fit.score+'<small>/100 fit</small>';
      mb.style.width=Math.max(3,d.fit.score)+'%';
      fc.textContent=d.fit.context||'';
      fr.innerHTML='';
      (d.fit.reasons||[]).forEach(function(r){
        var li=document.createElement('li');
        var b=document.createElement('b'); b.textContent=r.label;
        var em=document.createElement('em'); em.textContent=r.pts+'/'+r.max;
        var sp=document.createElement('span'); sp.textContent=r.detail;
        li.appendChild(b); li.appendChild(sp); li.appendChild(em); fr.appendChild(li);
      });
      fit.hidden=false;
    } else { fit.hidden=true; }
    // generic why
    if(d.why){ wy.textContent=d.why; wy.className='cm-why'; wh.hidden=false; }
    else { wy.textContent=''; wh.hidden=true; }
    img.removeAttribute('src'); img.alt=d.name; img.src=d.full;
    al.innerHTML='';
    if(d.alts&&d.alts.length){
      var anyUp=d.alts.some(function(a){return a.upgrade;});
      ah.textContent=anyUp?'Stronger options for this slot':'Alternatives that could slot here';
      d.alts.forEach(function(a){
        var fig=document.createElement('figure'); fig.className='cm-alt';
        var im=document.createElement('img'); im.alt=a.n; im.loading='lazy'; im.src=a.img;
        var cap=document.createElement('figcaption');
        cap.textContent=a.n+' ';
        var tag=document.createElement('span');
        tag.className=a.owned?'own':'buy'; tag.textContent=a.owned?'✓ owned':'buy';
        cap.appendChild(tag);
        if(a.upgrade){ var up=document.createElement('span'); up.className='up';
          up.textContent='upgrade'; cap.appendChild(up); }
        if(a.why){ var w=document.createElement('span'); w.className='altwhy';
          w.textContent=a.why; cap.appendChild(w); }
        fig.appendChild(im); fig.appendChild(cap); al.appendChild(fig);
      });
      aw.hidden=false;
    } else { aw.hidden=true; }
    ov.hidden=false; document.body.style.overflow='hidden';
  }
  function close(){ ov.hidden=true; document.body.style.overflow=''; }
  document.querySelectorAll('figure.mc[data-key]').forEach(function(f){
    f.addEventListener('click',function(){ open(f.getAttribute('data-key')); });
    f.addEventListener('keydown',function(e){
      if(e.key==='Enter'||e.key===' '){ e.preventDefault(); open(f.getAttribute('data-key')); }
    });
  });
  ov.addEventListener('click',function(e){ if(e.target===ov) close(); });
  document.querySelector('#cardmodal .cm-close').addEventListener('click',close);
  document.addEventListener('keydown',function(e){ if(e.key==='Escape'&&!ov.hidden) close(); });
})();
</script>
""".replace("__PAYLOAD__", payload)


def render_dashboard(title, commander, subtitle, rep, enriched, theme,
                     sections, notes=None, buylist=None, shared=None,
                     assessment=None, similar=None, details=None):
    t = THEMES.get(theme, THEMES["default"])
    modal_css = card_modal_css(t)
    modal_block = card_modal_block(details or {})
    fonts = (f"<link rel='preconnect' href='https://fonts.googleapis.com'>"
             f"<link href='{t['fonts_link']}' rel='stylesheet'>"
             if t["fonts_link"] else "")
    cats = rep["categories"]
    tiles = [stat_tile("Total", rep["total_cards"], "incl. commander"),
             stat_tile("Lands", rep["lands"],
                       deck_stats._flag("lands", rep["lands"]).strip("()"))]
    if rep.get("deck_value") is not None:
        tiles.append(stat_tile("Value", f"${rep['deck_value']:,.0f}", "market est"))
    if assessment:
        tiles.append(stat_tile("Bracket", assessment["bracket"],
                               assessment["bracket_name"]))
        tiles.append(stat_tile("Power", f"{assessment['power']}",
                               f"/100 · {assessment['tier']}"))
    tiles += [stat_tile("Ramp", cats.get("ramp", 0)),
              stat_tile("Removal", cats.get("removal", 0)),
              stat_tile("Draw", cats.get("draw", 0))]
    tiles = "".join(tiles)

    power_sec = (f"<section><h2>Power &amp; Bracket</h2>{power_html(assessment)}"
                 "</section>" if assessment else "")

    notes_sec = (f"<section><h2>Game Plan &amp; Player Notes</h2>"
                 f"{notes_html(notes)}</section>" if notes else "")
    pip_sec = (f"<section><h2>Color / Pip Demand</h2>{pip_table(rep)}</section>"
               if rep.get("pip_demand") else "")
    buy_sec = (f"<section><h2>Buy &amp; Replace</h2>{buylist_html(buylist)}</section>"
               if buylist else "")
    sim_sec = (f"<section><h2>Commanders That Also Fit This Shell</h2>"
               f"{similar_html(similar)}</section>" if similar is not None else "")
    shared_sec = (f"<section><h2>Shared Across Decks</h2>{shared_html(shared)}"
                  "</section>" if shared is not None else "")
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
.mv.dim {{ color:var(--muted); }}
.pr {{ color:var(--muted); font-size:.72rem; margin-left:6px; }}
ul.notes {{ margin:6px 0 10px; padding-left:20px; }}
ul.notes li {{ margin:3px 0; }}
section p {{ margin:8px 0; }}
code {{ font-family:{t['mono']}; background:rgba(255,255,255,.06);
  padding:1px 5px; border-radius:5px; font-size:.85em; }}
.tablewrap {{ overflow-x:auto; }}
.buytoggle {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px;
  margin-bottom:14px; }}
.thbtn {{ background:transparent; color:var(--text); cursor:pointer;
  border:1px solid rgba(255,255,255,.18); border-radius:20px;
  padding:5px 13px; font-family:{t['mono']}; font-size:.8rem; }}
.thbtn:hover {{ border-color:var(--accent); }}
.thbtn.active {{ background:var(--accent); color:#000; border-color:var(--accent);
  font-weight:700; }}
.buysum {{ color:var(--muted); font-family:{t['mono']}; font-size:.8rem;
  margin-left:auto; }}
.buytable td.bc {{ color:var(--text); }}
.buytable td.bp {{ color:var(--accent2); white-space:nowrap; }}
.buytable td.br {{ color:var(--muted); font-size:.82rem; }}
.repl {{ color:var(--warn); }}
.tier {{ color:var(--muted); font-size:.68rem; border:1px solid rgba(255,255,255,.15);
  border-radius:8px; padding:0 6px; margin-left:6px; }}
.bracketline {{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;
  margin-bottom:8px; }}
.bnum {{ font-family:{t['display']}; font-size:1.9rem; color:var(--accent2); }}
.bname {{ color:var(--gold); font-family:{t['head']}; text-transform:uppercase;
  letter-spacing:1.5px; font-size:.85rem; }}
.pscore {{ margin-left:auto; font-family:{t['display']}; font-size:1.9rem;
  color:var(--accent); }}
.pwrtable td {{ border:none; padding:3px 8px 3px 0; vertical-align:middle; }}
.pwrtable td:first-child {{ width:150px; color:var(--muted); }}
.pwrbar {{ width:40%; }}
.pwrbar span {{ display:block; height:9px; border-radius:5px;
  background:linear-gradient(90deg,var(--accent2),var(--accent)); }}
.pwrnum {{ font-size:.78rem; white-space:nowrap; }}
.imgnote {{ font-size:.75rem; margin:0 0 10px; }}
.cardgrid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(104px,1fr));
  gap:10px; margin:6px 0 14px; }}
.mc {{ margin:0; position:relative; }}
.mc img {{ width:100%; aspect-ratio:5/7; object-fit:cover; display:block;
  border-radius:5% / 3.6%; background:rgba(255,255,255,.05); }}
.mc .qty {{ position:absolute; top:4px; right:4px; background:var(--accent);
  color:#000; font-family:{t['mono']}; font-size:.64rem; font-weight:700;
  padding:0 5px; border-radius:8px; }}
.sb {{ display:inline-block; font-family:{t['mono']}; font-size:.62rem;
  font-weight:700; padding:0 5px; border-radius:8px; background:var(--accent2);
  color:#000; }}
.mc .sb {{ position:absolute; top:4px; left:4px; }}
.sb.need {{ background:var(--warn); color:#000; }}
.need {{ color:var(--warn); font-weight:700; }}
.mc figcaption {{ font-family:{t['mono']}; font-size:.64rem; color:var(--muted);
  margin-top:3px; line-height:1.25; }}
.mc figcaption .mv {{ min-width:0; margin-right:3px; }}
.mc figcaption .pr {{ display:block; margin:0; }}
footer {{ color:var(--muted); font-size:.8rem; margin-top:30px;
  text-align:center; }}
@media (max-width:560px) {{ ul.cards {{ columns:1; }} header h1 {{ font-size:2rem; }}
  .buysum {{ margin-left:0; width:100%; }} }}
{modal_css}
</style></head><body><div class="wrap">
<header>
  <h1>{esc(title)}</h1>
  <div class="sub">{esc(subtitle)}</div>
  {f'<div class="cmd">Commander: {esc(commander)}</div>' if commander else ''}
</header>
<div class="tiles">{tiles}</div>
{power_sec}
{notes_sec}
<section><h2>Mana Curve (MV Spread)</h2>{curve_svg(rep['curve'], t)}{curve_note(enriched)}</section>
{pip_sec}
<section><h2>Ownership</h2>{ownership_block(rep)}</section>
{shared_sec}
{sim_sec}
{buy_sec}
<section><h2>Decklist by Section</h2>{sections_html(sections, enriched, shared)}</section>
<footer>Generated by the MTG Commander Deckbuilder. Category counts &amp; any
prices are heuristic/estimates — verify uncertain cards.</footer>
</div>{modal_block}{IMG_LOADER}</body></html>"""


def render_visual(title, deck, idx, theme, size="normal"):
    t = THEMES.get(theme, THEMES["default"])
    tiles = []
    for d in deck:
        ref = mtglib.lookup(idx, d.name)
        if ref and ref.scryfall_id:            # exact printing via CDN (best)
            url = card_image.image_url(ref.scryfall_id, size)
        else:                                   # reliable: Scryfall image-by-name
            url = card_image.image_url_by_name(d.name, size)
        qty = f"<span class='qty'>{d.quantity}x</span>" if d.quantity > 1 else ""
        tiles.append(
            f"<figure><img loading='lazy' data-src='{esc(url)}' alt='{esc(d.name)}'>"
            f"{qty}<figcaption>{esc(d.name)}</figcaption></figure>")
    warn = ""
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
figure {{ margin:0; position:relative; }}
figure img {{ width:100%; aspect-ratio:5/7; object-fit:cover;
  border-radius:4.75% / 3.5%; display:block; background:{t['panel']}; }}
.qty {{ position:absolute; top:6px; right:6px; background:{t['accent']};
  color:#000; font-family:{t['mono']}; font-size:.72rem; font-weight:700;
  padding:1px 6px; border-radius:10px; }}
figcaption {{ font-family:{t['mono']}; font-size:.72rem; color:{t['muted']};
  margin-top:5px; text-align:center; }}
.warn {{ color:{t['warn']}; }}
</style></head><body><div class="wrap">
<h1>{esc(title)}</h1>
<div class="banner"><b>Heads up:</b> card images load <b>live from Scryfall by
name</b> when you open this file. They will <b>not</b> appear in the chat preview
(external images are blocked there) — open it in a real browser with internet
(Chrome / Safari / Edge). A blank card usually means a name Scryfall's fuzzy
search couldn't match.</div>
{warn}
<div class="grid">{''.join(tiles)}</div>
</div>{IMG_LOADER}</body></html>"""


def generate(deck_path, collection_path, title="Commander Deck", commander="",
             subtitle="Commander (EDH) deck dashboard", theme="default",
             decks_dir=None, size="normal", want_visual=False):
    """Load a deck + collection and return rendered HTML. Shared by the CLI and
    the web app. Returns {'dashboard': str, 'visual': str|None, 'assessment': dict|None,
    'report': dict}."""
    with open(deck_path, encoding="utf-8") as f:
        deck = mtglib.parse_deck(f.read())
    coll = mtglib.load_collection(collection_path)

    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path
    idx = mtglib.index_by_name(coll)
    enriched, missing = deck_stats.analyze(deck, idx)
    attrs = load_attrs(f"{stem}.attrs.csv")
    apply_attrs(enriched, attrs)
    rep = deck_stats.build_report(deck, enriched, missing, idx)

    sections = load_deck_sections(deck_path)
    notes = load_notes(f"{stem}.notes.md")
    buylist = load_buylist(f"{stem}.buylist.csv")

    shared = None
    dd = decks_dir if decks_dir is not None else os.path.dirname(deck_path)
    if dd:
        try:
            shared = deck_conflicts.shared_for_deck(deck_path, idx, dd)
        except Exception:
            shared = None
    try:
        assessment = power.assess(enriched, rep, power.load_refs())
    except Exception:
        assessment = None
    try:
        _, _, similar = simc.find(deck_path, idx, simc.load_commanders(), attrs)
    except Exception:
        similar = None

    try:
        refs = power.load_refs()
        ctx = deck_fit.deck_context(deck_path, enriched, commander)
        staples = deck_fit.load_role_staples()
        details = build_card_details(sections, enriched, idx, load_card_notes(),
                                     rep=rep, ctx=ctx, refs=refs, staples=staples)
    except Exception:
        details = None

    dashboard = render_dashboard(title, commander, subtitle, rep, enriched, theme,
                                 sections, notes, buylist, shared, assessment,
                                 similar, details)
    visual = render_visual(title, deck, idx, theme, size) if want_visual else None
    return {"dashboard": dashboard, "visual": visual,
            "assessment": assessment, "report": rep}


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
    ap.add_argument("--notes", help="player notes markdown (default: <deck>.notes.md)")
    ap.add_argument("--buylist", help="buy/replace CSV (default: <deck>.buylist.csv)")
    ap.add_argument("--attrs", help="type/MV CSV (default: <deck>.attrs.csv)")
    ap.add_argument("--decks-dir", help="folder of sibling decks for the cross-deck "
                    "conflict check (default: the deck's folder); '' to disable")
    args = ap.parse_args()

    decks_dir = args.decks_dir if args.decks_dir is not None else os.path.dirname(args.deck)
    try:
        res = generate(args.deck, args.collection, args.title, args.commander,
                       args.subtitle, args.theme, decks_dir, args.size, args.visual)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(res["dashboard"])
    print(f"wrote dashboard: {args.out}")

    if args.visual and res["visual"]:
        vpath = (args.out[:-5] if args.out.endswith(".html") else args.out) + "-visual.html"
        with open(vpath, "w", encoding="utf-8") as f:
            f.write(res["visual"])
        print(f"wrote visual gallery: {vpath}  (open in a real browser)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
