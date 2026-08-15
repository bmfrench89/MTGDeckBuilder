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
import combo_detector
import manabase
import deckcore

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


# Card images: resolve every card NAME (from each <img alt>) to its Scryfall CDN
# image in batches via POST /cards/collection (<=75 ids/request). A ~100-card page
# is ~2 requests to the un-rate-limited CDN instead of 100 hits on the 2/s
# /cards/named endpoint — so images don't get 429'd and drop out. Cards the batch
# can't resolve fall back to their data-src (the by-name URL), gently throttled.
# Same approach as the web app's cardgrid.js.
_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_asset_cache = {}


def _asset(name):
    """Read a dashboard asset (scripts/assets/) once and cache it. The dashboard stays a
    single self-contained HTML file — these are inlined at render time, not linked."""
    if name not in _asset_cache:
        with open(os.path.join(_ASSETS, name), encoding="utf-8") as f:
            _asset_cache[name] = f.read()
    return _asset_cache[name]


IMG_LOADER = _asset("card_images.html")


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
    # Say which basis the numbers rest on: enriched lands report what they actually
    # tap for, un-enriched (or unowned) ones fall back to color identity.
    if src and (rep.get("color_sources_basis") or {}).get("identity_lands"):
        src_hdr += " (identity approx.)"
    return ("<div class='tablewrap'><table class='data'><thead><tr>"
            "<th>Color</th><th>Pip demand</th>"
            f"<th>Double-pip cards</th><th>{src_hdr}</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


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
# Companion-file loaders, the card-notes knowledge base, the attrs overlay and
# role labels now live in `deckcore` (the shared analysis hub) so this renderer
# isn't imported just to reach them. Imported here for unqualified use below.
# --------------------------------------------------------------------------- #
from deckcore import (load_deck_sections, load_notes, load_buylist, load_attrs,  # noqa: E402
                      load_card_notes, apply_attrs, _to_float_price, _ROLE_LABEL)


# Only NARROW categories, where "same EDHREC category" ≈ "same job" and any peer is a
# fair swap (other mana rocks, other utility lands, other stax enchantments…). Broad
# categories (Creatures / Instants / Sorceries) would surface on-theme-but-not-functional
# cards, so alternatives there come from curated notes + role_staples instead.
_EDHREC_NARROW = {"Mana Artifacts", "Utility Artifacts", "Enchantments",
                  "Utility Lands", "Planeswalkers"}


def _edhrec_alts(commander, idx):
    """name(normalized) -> {peers: [names], label: str}: same-slot EDHREC options for
    generic categories. Cached + graceful; {} when EDHREC is unreachable or the commander
    is unknown, so alternatives fall back to curated notes + role staples."""
    if not commander:
        return {}
    try:
        import edhrec
        rec = edhrec.recommendations(commander, idx)
    except Exception:
        return {}
    if rec.get("error"):
        return {}
    out = {}
    for sec in rec.get("sections", []):
        if sec.get("header") not in _EDHREC_NARROW:
            continue
        names = [c["name"] for c in sec.get("cards", [])]
        for n in names:
            k = mtglib._norm(n)
            out.setdefault(k, {"peers": [p for p in names if mtglib._norm(p) != k],
                               "label": "a popular pick for this slot on EDHREC"})
    return out


def build_card_details(sections, enriched, idx, notes, rep=None, ctx=None,
                       refs=None, staples=None, size="normal", edhrec_alts=None,
                       fetch=None):
    """Per-card payload for the click-to-enlarge panel: enlarged image, a grounded
    generic 'why it works' blurb, a deck-specific fit score + how-it-fits line, and
    alternatives / stronger options tagged owned/buy."""
    en = {mtglib._norm(c.name): c for c in enriched}
    # Per-fetcher census rows (manabase.fetch_census), keyed for the panel note:
    # "5 legal targets in this deck" belongs on the card that does the searching.
    fetch_rows = {mtglib._norm(r["name"]): r
                  for r in ((fetch or {}).get("rows") or [])}
    in_deck = set(en.keys())
    section_of = {}
    for label, cards in sections:
        for _q, name in cards:
            section_of.setdefault(mtglib._norm(name), label)
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
            role_parts = [_ROLE_LABEL.get(r, r.title()) for r in sorted(roles)]
            role_parts += deckcore.load_power_tags().get(k, [])
            role = " · ".join(role_parts)
            note = notes.get(k)
            section = section_of.get(k, "")
            known_type = "/".join(c.types) if (c and c.types) else ""
            known_mv = (f"{c.mana_value:g}" if (c and c.mana_value is not None) else "")

            fit = None
            if c is not None and rep is not None and ctx is not None and refs is not None:
                try:
                    fit = deck_fit.assess_card(c, rep, ctx, refs, section)
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

            # broaden with EDHREC same-category peers so every listed card has options
            ea = (edhrec_alts or {}).get(k)
            if len(alt_src) < 4 and ea:
                have = {mtglib._norm(a["n"]) for a in alt_src}
                for peer in ea["peers"]:
                    if len(alt_src) >= 4:
                        break
                    pk = mtglib._norm(peer)
                    if pk in have or pk in in_deck:
                        continue
                    have.add(pk)
                    alt_src.append({"n": peer,
                                    "owned": mtglib.lookup(idx, peer) is not None,
                                    "upgrade": False, "why": ea["label"]})

            alts = []
            for a in alt_src:
                ref = mtglib.lookup(idx, a["n"])
                asid = ref.scryfall_id if (ref and ref.scryfall_id) else ""
                aimg = (card_image.image_url(asid, "small") if asid
                        else card_image.image_url_by_name(a["n"], "small"))
                alts.append({"n": a["n"], "img": aimg, "owned": a["owned"],
                             "upgrade": a.get("upgrade", False), "why": a.get("why", "")})

            details[k] = {"name": name, "full": full, "role": role,
                          "section": section, "type": known_type, "mv": known_mv,
                          "why": note["why"] if note else "", "fit": fit, "alts": alts}
            fr = fetch_rows.get(k)
            if fr:
                details[k]["fetch"] = {"targets": fr["targets"],
                                       "state": fr["state"]}
    return details


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


def _buy_badge(k, missing_keys):
    """A $ badge for a card in the list that you don't own yet — the deck can carry an
    aspirational pick, this just makes it obvious which ones you'd have to buy."""
    if k not in missing_keys:
        return ""
    return ("<span class='bb' title='You don&#39;t own this yet — buy it to sleeve "
            "this list'>BUY</span>")


def _new_badge(k, changes):
    """A NEW badge for a card the optimizer added in the last couple of weeks, so a
    refreshed deck shows what actually changed instead of making you diff 100 cards."""
    c = (changes or {}).get(k)
    if not c:
        return ""
    ago = c["days_ago"]
    when = "today" if ago == 0 else ("yesterday" if ago == 1 else f"{ago} days ago")
    why = f" — replaced {c['replaced']}" if c.get("replaced") else ""
    return (f"<span class='nb' title='Added {when} ({c['added']}){esc(why)}'>NEW</span>")


def sections_html(sections, enriched, shared=None, images=True, size="small",
                  missing=None, changes=None):
    missing_keys = {mtglib._norm(getattr(c, "name", c)) for c in (missing or [])}
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
                    f"alt='{esc(name)}'>{qty}{_share_badge(k, shared)}{_buy_badge(k, missing_keys)}"
                    f"{_new_badge(k, changes)}"
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
                           f"{_share_badge(k, shared)}{_new_badge(k, changes)}{price}</li>")
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
            + "".join(rows) + "</tbody></table></div>")


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
        src_tag = {"combo": " <span class='tier'>from Combo Watch</span>",
                   "decklist": " <span class='tier'>in decklist</span>"}.get(r.get("source"), "")
        repl = ((f"<span class='repl'>replace:</span> "
                 f"<a class='cardlink' data-card=\"{esc(r['replaces'])}\" "
                 f"data-key='{esc(mtglib._norm(r['replaces']))}'>"
                 f"{esc(r['replaces'])}</a>")
                if r["replaces"] else "<span class='muted'>new add</span>") + src_tag
        tier = f"<span class='tier'>{esc(r['tier'])}</span>" if r["tier"] else ""
        body.append(
            f"<tr class='buyrow' data-price='{dp:.2f}'>"
            # Panel-clickable, including cards NOT in the deck (combo pieces, buy
            # targets): the inlined panel carries details only for deck cards, but the
            # click path falls back to a live Scryfall lookup, so a plain-text row was
            # a dead end for exactly the cards a Buy tab is about.
            f"<td class='bc'><a class='cardlink' data-card=\"{esc(r['card'])}\" "
            f"data-key='{esc(mtglib._norm(r['card']))}'>{esc(r['card'])}</a> {tier}</td>"
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


def cuts_html(cuts):
    """The Cuts panel — advisory, and it says so twice.

    Ranked by the same value the optimizer uses, so the two never disagree about what
    a card is worth. Protected cards are rendered greyed and labelled rather than
    filtered out: the player asked "what do I cut", and silently dropping their own
    protected picks would answer a different question."""
    if not cuts or not cuts.get("rows"):
        return ""
    rows = []
    for r in cuts["rows"]:
        cls = " class='muted'" if r["protected"] else ""
        role = r.get("role") or "—"
        state = f" <span class='muted'>({r['role_state']})</span>" if r.get("role_state") else ""
        rows.append(
            f"<tr{cls}><td><a class='cardlink' data-card=\"{esc(r['name'])}\" "
            f"data-key='{esc(mtglib._norm(r['name']))}'>{esc(r['name'])}</a></td>"
            f"<td>{r['value']}</td><td>{esc(role)}{state}</td>"
            f"<td>{esc(r['why'])}</td></tr>")
    note = ""
    if cuts.get("no_field"):
        note = ("<p class='muted'>No EDHREC field data reachable — this ranking is "
                "fit-only, so treat it as a much weaker signal than usual.</p>")
    return ("<div class='tablewrap'><table class='data'><thead><tr>"
            "<th>Card</th><th>Value</th><th>Role</th><th>Why it ranks low</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
            + note + f"<p class='muted'>{esc(cuts.get('advisory', ''))}</p>")


def bracket_form(stem, editable, a):
    """The player's bracket setting — editable surface only.

    A generated (CLI) dashboard is a snapshot with nowhere to POST, so it gets
    nothing; the app's saved-deck page gets a select that writes the deck's
    `# Bracket:` header. Auto is a real option, not the absence of one: clearing
    the setting returns the deck to the detected verdict."""
    if not editable or not a:
        return ""
    cur = a.get("bracket_declared")
    opts = ["<option value='auto'%s>Auto (detected)</option>"
            % ("" if cur else " selected")]
    for n in (1, 2, 3, 4, 5):
        opts.append("<option value='%d'%s>%d — %s</option>"
                    % (n, " selected" if cur == n else "", n,
                       esc(power.BRACKET_NAMES.get(n, ""))))
    return (f"<form class='bracketform' method='post' "
            f"action='/deck/{esc(stem)}/bracket'>"
            f"<label for='bset'>Your bracket</label>"
            f"<select id='bset' name='bracket'>{''.join(opts)}</select>"
            f"<button type='submit'>Save</button>"
            f"<span class='muted'>Records intent — brackets 1 and 5 are defined by "
            f"it. The detected bracket stays visible either way.</span></form>")


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
    # The player's `# Bracket:` setting headlines when present; the DETECTED verdict
    # is printed beside it whenever they disagree. Both, always — the header records
    # intent (brackets 1 and 5 are defined by intent, not contents), it does not
    # silence the card evidence.
    eff = a.get("bracket_effective", a["bracket"])
    eff_name = a.get("bracket_effective_name", a["bracket_name"])
    declared_tag = ("<span class='muted'>your setting</span>"
                    if a.get("bracket_declared") else "")
    mismatch = (f"<p class='muted'>Detected <b>Bracket {a['bracket_detected']}</b> "
                f"({esc(a.get('bracket_detected_name', ''))}) from the card signals "
                f"below — your setting is what this deck reports.</p>"
                if a.get("bracket_mismatch") else "")
    return (
        f"<div class='bracketline'><span class='bnum'>Bracket {eff}</span>"
        f"<span class='bname'>{esc(eff_name)}</span>{declared_tag}"
        f"<span class='pscore'>{a['power']}<span class='muted'>/100 · "
        f"{esc(a['tier'])}</span></span></div>"
        + mismatch +
        f"<ul class='notes'>{reasons}</ul>"
        "<div class='tablewrap'><table class='data pwrtable'><tbody>" + "".join(bars) + "</tbody></table></div>"
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
            f"<tr><td><a class='cardlink' data-key='{esc(mtglib._norm(r['name']))}' "
            f"tabindex='0' role='button'>{esc(r['name'])}</a> "
            f"<span class='mv'>[{esc(r['colors'])}]</span> {own}</td>"
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


def add_commander_details(details, similar, idx, size="normal"):
    """Make the 'Commanders That Also Fit' names open the same bottom-sheet card
    panel: give each alternate commander a payload (image + a why blurb) keyed by
    its normalized name, matching the .cardlink in similar_html. Skips names
    already present (e.g. a commander that is also a deck card). Returns details."""
    if details is None:
        details = {}
    if not similar:
        return details
    for r in similar:
        k = mtglib._norm(r["name"])
        if k in details:
            continue
        ref = mtglib.lookup(idx, r["name"])
        sid = ref.scryfall_id if (ref and ref.scryfall_id) else ""
        full = (card_image.image_url(sid, size) if sid
                else card_image.image_url_by_name(r["name"], size))
        why = " ".join(p for p in (r.get("why"), r.get("notes")) if p).strip()
        details[k] = {"name": r["name"], "full": full, "why": why or None}
    return details


def explain_html(explain, *keys):
    """Collapsible "what this means" notes, rendered from the ENGINE's own text.

    The wording is data (`manabase.analyze()["explain"]`, `goldfish`'s `definitions`),
    never prose hardcoded here — so the CLI, the dashboard and --json cannot drift
    into three different explanations of the same number. Uses <details>, so it costs
    no JS and prints expanded."""
    parts = []
    for k in keys:
        e = (explain or {}).get(k)
        if not e:
            continue
        parts.append(
            f"<details class='explain'><summary>{esc(e['what'])}</summary>"
            f"<p>{esc(e['why'])}</p><p class='muted'>{esc(e['healthy'])}</p></details>")
    return "".join(parts)


def mana_health(mana, rep):
    """The standing Mana-health advisory (spec-mana-intelligence Phase D).

    Computed at render time from the SAME memoized analysis the page already
    holds, so every manual edit re-evaluates it on the reload the card panel
    already performs — idempotent, always current, no state carried between
    requests, and never a trigger for the optimizer. Returns a list of short
    finding strings (possibly empty); the renderer shows the top two.

    Fires on: a fetcher with ZERO targets (census state 'none'), and on a
    below-floor land count combined with any post-restriction LOW colour —
    each a fact the player can act on, not a vibe."""
    if not mana:
        return []
    findings = []
    for r in ((mana.get("fetch") or {}).get("rows") or []):
        if r["state"] == "none":
            findings.append(f"{r['name']} has 0 fetch targets")
    lands = (rep or {}).get("lands") or 0
    lo_floor = deckcore.LAND_RANGE[0]
    low = [c["color"] for c in (mana.get("colors") or []) if c["status"] == "low"]
    if lands and lands < lo_floor and low:
        findings.append(f"{lands} lands (template floor {lo_floor}) and "
                        f"{'/'.join(low)} under Karsten targets")
    return findings


def manabase_html(mana):
    """Consistency & Manabase section from manabase.analyze(). Reuses existing
    dashboard classes (stat tiles / data table / notes) — no new CSS."""
    if mana is None:
        return ""
    if not mana.get("have_colors"):
        return ("<p class='muted'>Colored-source analysis needs card colors + mana costs — "
                "enrich the collection (Card DB) or add a deck <code>.attrs.csv</code> with a "
                "Cost column. Then you get opening-hand odds, per-color source adequacy vs "
                "Karsten's targets, and which cards are risky to cast on curve.</p>")
    out = []
    ex = mana.get("explain") or {}
    lo = mana.get("land_odds")
    if lo:
        out.append("<div class='tiles'>"
                   + stat_tile("Keepable hand", f"{lo['keepable']*100:.0f}%", "2–5 lands")
                   + stat_tile("3+ lands", f"{lo['ge3_open']*100:.0f}%", "opening 7")
                   + stat_tile("4th land by T4", f"{lo['ge4_by_t4']*100:.0f}%", "on the play")
                   + "</div>")
        out.append(explain_html(ex, "keepable", "ge3_open", "ge4_by_t4"))
    rows = []
    for c in mana["colors"]:
        dbl = f" · P(2 by T3) {c['p_two_t3']*100:.0f}%" if c["double_pips"] else ""
        flag = ("<span class='warnbox'>⚠ under target</span>" if c["status"] == "low"
                else "<span class='ok'>✓</span>")
        restr = (f" <span class='muted'>(+{c['restricted']} restricted)</span>"
                 if c.get("restricted") else "")
        rows.append(f"<tr class='{'warn' if c['status']=='low' else ''}'><td>{c['color']}</td>"
                    f"<td>{c['sources']}{restr}</td><td>~{c['karsten_target']}</td>"
                    f"<td>{c['demand']}{' · dbl ' + str(c['double_pips']) if c['double_pips'] else ''}</td>"
                    f"<td>{c['p_open']*100:.0f}%{dbl}</td><td>{flag}</td></tr>")
    out.append("<div class='tablewrap'><table class='data'><thead><tr><th>Color</th>"
               "<th>Sources</th><th>Karsten</th><th>Pip demand</th><th>P(&ge;1 opener)</th>"
               "<th></th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")
    out.append(explain_html(ex, "sources"))
    if mana["risky"]:
        items = "".join(f"<li><b>{esc(r['name'])}</b> (MV {r['mv']:g}, {r['pips']}×{r['color']}) — "
                        f"{r['p']*100:.0f}% to have the color on curve</li>" for r in mana["risky"])
        out.append(f"<h3>Risky to cast on curve <span class='count'>{mana['risky_total']}</span></h3>"
                   f"<ul class='notes'>{items}</ul>")
        out.append(explain_html(ex, "risky"))
    basis = mana.get("basis") or {}
    if basis.get("restricted_lands"):
        out.append(explain_html(ex, "restricted"))
    if basis.get("restriction_unknown_lands"):
        out.append(f"<p class='muted'>~ {basis['restriction_unknown_lands']} land(s) "
                   "enriched before the restriction vocabulary — restriction status "
                   "unknown, counted as unrestricted. Re-enrich to verify.</p>")

    # Fetch census (spec-mana-intelligence Phase C). One renderer serves the app
    # deck page AND the CLI dashboard; the census either renders its rows or says
    # exactly why it can't — never a confident zero on pre-vocabulary data.
    fetch = mana.get("fetch") or {}
    if fetch.get("unknown") == "pre-vocabulary":
        out.append("<h3>Fetch census</h3><p class='muted'>Unavailable — this "
                   "collection's enrichment predates the fetch vocabulary. "
                   "Re-enrich (Card DB) to see what each fetcher can find here.</p>")
    elif fetch.get("rows"):
        frows = []
        for r in fetch["rows"]:
            chip = {"none": "<span class='warnbox'>⚠ no targets</span>",
                    "thin": "<span class='warnbox'>thin</span>"}.get(
                        r["state"], "<span class='ok'>✓</span>")
            names = esc(", ".join(r["target_names"]))
            more = r["targets"] - len(r["target_names"])
            if more > 0:
                names += f", +{more} more"
            spec = esc(", ".join(t[len("fetch:"):] for t in r["spec"]))
            frows.append(
                f"<tr class='{'warn' if r['state'] != 'ok' else ''}'>"
                f"<td><span class='cardlink' data-card='{esc(r['name'])}' "
                f"data-key='{esc(r['name'])}'>{esc(r['name'])}</span></td>"
                f"<td>{spec}</td><td>{r['targets']}</td>"
                f"<td class='muted'>{names}</td><td>{chip}</td></tr>")
        out.append(f"<h3>Fetch census <span class='count'>{fetch['total_fetchers']}</span></h3>"
                   "<div class='tablewrap'><table class='data'><thead><tr>"
                   "<th>Fetcher</th><th>Finds</th><th>Targets</th><th>In this deck</th>"
                   "<th></th></tr></thead><tbody>" + "".join(frows)
                   + "</tbody></table></div>")
        if fetch.get("unknown") == "no-subtype-data":
            out.append("<p class='muted'>~ counts may be low: some land(s) here "
                       "have no type data.</p>")
        out.append(explain_html(ex, "fetch"))

    # The "these are unconditional" caveat used to be a footer under everything. It is
    # a property of the probabilities themselves, so it now sits with them as one more
    # explainer — a caveat read after the numbers is a caveat that arrived too late.
    out.append(explain_html(ex, "unconditional"))
    return "".join(out)


def clock_html(sim):
    """The goldfish CLOCK — how fast this deck presents lethal, uncontested.

    Since WotC's Oct-2025 rework the brackets are defined by expected game length, so
    this is the one analytic that speaks the bracket system's own units. It is
    rendered as EVIDENCE beside power.py's card-count bracket, never as a
    reclassification — and every caveat the engine ships (combat-only, understated for
    drain decks, no data) is printed with it, because a confident wrong number is
    worse than an absent one."""
    clk = (sim or {}).get("clock")
    if not clk:
        return ""
    d = (sim.get("definitions") or {})
    out = []
    if clk.get("median_first_kill") is not None:
        out.append("<div class='tiles'>")
        out.append(stat_tile("Presents lethal", f"T{clk['median_first_kill']:g}",
                             d.get("first_kill", "")))
        if clk.get("median_table_kill") is not None:
            out.append(stat_tile("Whole table", f"T{clk['median_table_kill']:g}",
                                 d.get("table_kill", "")))
        by = clk.get("p_first_kill_by") or {}
        if "6" in by:
            out.append(stat_tile("Lethal by T6", f"{by['6']*100:.0f}%",
                                 d.get("first_kill", "")))
        out.append("</div>")
        if clk.get("bracket_hint"):
            out.append(f"<p class='muted'>Clock consistent with the <b>Bracket "
                       f"{clk['bracket_hint']}</b> expectation. "
                       f"{esc(d.get('clock_bracket', ''))}</p>")
    if clk.get("note"):
        out.append(f"<p class='warn'>{esc(clk['note'])}</p>")
    if not out:
        return ""
    return ("<h3>Clock <span class='count'>uncontested</span></h3>" + "".join(out))


def goldfish_html(sim):
    """Goldfish Monte Carlo section from `goldfish.sim_for_deck()`. Same classes as
    manabase_html (stat tiles / data table / notes) — no new CSS.

    Every tile carries its own definition, because "screw" and "flood" are judgement
    calls the engine ships as data, and the footer says out loud that these are
    SIMULATED frequencies sitting next to exact hypergeometrics. The two sections are
    meant to disagree; a reader who doesn't know why would trust the wrong one."""
    if not sim:
        return ""
    if not sim.get("have_data"):
        return f"<p class='muted'>{esc(sim.get('note') or 'Simulation unavailable.')}</p>"
    d = sim.get("definitions") or {}
    p = sim.get("p_cast_by") or {}
    out = ["<div class='tiles'>"]
    for turn in ("4", "6"):
        if turn in p:
            out.append(stat_tile(f"Commander by T{turn}", f"{p[turn]*100:.0f}%",
                                 d.get("p_cast_by", "")))
    out.append(stat_tile("Keepable opener", f"{sim['keepable_first7']*100:.0f}%",
                         d.get("keepable_first7", "")))
    if sim.get("screw") is not None:
        out.append(stat_tile("Screwed", f"{sim['screw']*100:.0f}%", d.get("screw", "")))
    out.append(stat_tile("Flooded", f"{sim['flood']*100:.0f}%", d.get("flood", "")))
    out.append("</div>")
    # The sim already ships its definitions as data; render them in the same
    # collapsible shape the manabase explainers use so the whole tab reads one way.
    out.append(explain_html(
        {k: {"what": d.get(k, ""), "why": "", "healthy": ""}
         for k in ("p_cast_by", "keepable_first7", "screw", "flood")
         if d.get(k)},
        "p_cast_by", "keepable_first7", "screw", "flood"))
    out.append(clock_html(sim))

    lands = sim.get("mean_lands_by_turn") or {}
    if lands:
        out.append("<p class='muted'>" + esc(d.get("mean_lands_by_turn", "")) + " "
                   + " · ".join(f"T{t} <b>{v}</b>" for t, v in list(lands.items())[:8])
                   + "</p>")

    worst = [c for c in (sim.get("cards") or [])
             if c["cast_rate"] < 1.0 or (c["delta"] or 0) > 0][:10]
    if worst:
        rows = []
        for c in worst:
            when = ("<span class='warn'>never cast</span>" if c["mean_first_cast"] is None
                    else f"T{c['mean_first_cast']:g}")
            delta = "—" if c["delta"] is None else f"{c['delta']:+g}"
            rows.append(f"<tr><td><a class='cardlink' data-card=\"{esc(c['name'])}\" "
                        f"data-key='{esc(mtglib._norm(c['name']))}'>{esc(c['name'])}</a></td>"
                        f"<td>{c['mv']:g}</td><td>{c['cast_rate']*100:.0f}%</td>"
                        f"<td>{when}</td><td>{delta}</td></tr>")
        out.append("<h3>Worst-sequenced cards <span class='count'>"
                   f"{len(worst)}</span></h3>"
                   f"<p class='muted'>{esc(d.get('cards', ''))}</p>"
                   "<div class='tablewrap'><table class='data'><thead><tr><th>Card</th>"
                   "<th>MV</th><th>Cast rate</th><th>Mean first cast</th>"
                   "<th>vs curve</th></tr></thead><tbody>"
                   + "".join(rows) + "</tbody></table></div>")

    notes = "".join(f"<li>{esc(a)}</li>" for a in (sim.get("assumptions") or []))
    out.append("<h3>Assumptions</h3><ul class='notes muted'>" + notes + "</ul>")
    return "".join(out)


def combos_html(combos):
    """Render the Combo Watch section from combo_detector output:
    {'complete':[...], 'near':[...]}. `None` (detector failed) renders nothing."""
    if combos is None:
        return ""
    comp, near = combos.get("complete", []), combos.get("near", [])
    if not comp and not near:
        return ("<div class='ok'>No known infinite / two-card combos detected in "
                "this deck, complete or one-away. <span class='muted'>(Checked "
                "against <code>data/reference/combos.csv</code> — a curated list, "
                "not exhaustive.)</span></div>")
    out = []
    if comp:
        out.append("<h3>Complete combos in this deck <span class='count'>"
                   f"{len(comp)}</span></h3><ul class='notes'>")
        for c in comp:
            flag = (" <span class='need'>EARLY 2-CARD → BRACKET 4</span>"
                    if c["early"] else "")
            out.append(f"<li><b>{esc(c['name'])}</b> → {esc(c['result'])}{flag}"
                       f"<br><span class='muted'>{esc(c['notes'])}</span></li>")
        out.append("</ul>")
    if near:
        out.append("<h3>One piece away <span class='count'>"
                   f"{len(near)}</span></h3><ul class='notes'>")
        for c in near:
            owned = c.get("missing_owned")
            tag = ("<span class='ok'>you own it</span>" if owned
                   else "<span class='muted'>not owned</span>")
            out.append(f"<li>add <b>{esc(c['missing'])}</b> ({tag}) → "
                       f"<b>{esc(c['name'])}</b>: {esc(c['result'])}</li>")
        out.append("</ul>")
    if comp:
        out.append("<p class='muted'>A complete <b>early two-card</b> combo is the "
                   "WotC red flag that puts a deck in Bracket 4 — verify the "
                   "interaction and read the pod before playing it.</p>")
    return "".join(out)


def card_modal_css(t):
    """Card-panel CSS (scripts/assets/card_panel.css) with the theme's fonts substituted."""
    return (_asset("card_panel.css")
            .replace("__DISPLAY__", t["display"])
            .replace("__HEAD__", t["head"])
            .replace("__MONO__", t["mono"]))


def card_modal_block(details, editable=False, stem=""):
    payload = (json.dumps(details, ensure_ascii=True)
               .replace("<", "\\u003c").replace(">", "\\u003e")
               .replace("&", "\\u0026"))
    return _asset("card_panel.html").replace("__PAYLOAD__", payload).replace("__EDITABLE__", "true" if editable else "false").replace("__STEM__", json.dumps(stem))


def add_card_block(stem, editable):
    """The add-a-card picker — editable surface only.

    A CLI-rendered dashboard is a file on disk with no server behind it, so offering an
    Add button there would be a dead control. Remove/Replace already follow this rule.
    """
    if not editable:
        return ""
    return _asset("add_card.html").replace("__STEM__", json.dumps(stem))


def add_card_css(t):
    return (_asset("add_card.css")
            .replace("__HEAD__", t["head"])
            .replace("__MONO__", t["mono"]))


def tabs_block(groups):
    """CSS-only subtabs over the dashboard's sections. Returns (css, html).

    Why radios and not JS: a dashboard has to stay ONE self-contained file that works
    from disk with no network, so the tab state lives in `:checked` and the panels are
    plain siblings. If anything about the page breaks, the failure mode is "everything
    visible", never "content lost".

    Inactive panels are hidden, NOT omitted — both surfaces' card-panel hooks
    (`data-card=` in the app, `figure.mc[data-key]` in generated files) need their
    targets present in the DOM, and a printed copy restores every panel.

    `groups` is [(key, label, html)]; empty groups are dropped so a deck with no buylist
    doesn't get an empty Buy tab.
    """
    live = [(k, lab, html) for k, lab, html in groups if html and html.strip()]
    if not live:
        return "", ""
    css, inputs, nav, panels = [], [], [], []
    for i, (k, lab, html) in enumerate(live):
        css.append(f"#tab-{k}:checked ~ .tabpanel[data-tab='{k}'] {{ display:block; }}")
        css.append(f"#tab-{k}:checked ~ .tabs label[for='tab-{k}'] {{ background:var(--accent); "
                   "color:#000; border-color:var(--accent); font-weight:700; }")
        # the radio stays in the tab order (native arrow-key radiogroup nav); the focus
        # ring is drawn on its label, since the input itself is visually clipped away.
        css.append(f"#tab-{k}:focus-visible ~ .tabs label[for='tab-{k}'] "
                   "{ outline:2px solid var(--accent2); outline-offset:2px; }")
        inputs.append(f"<input type='radio' name='decktabs' id='tab-{k}' class='tabinput'"
                      f"{' checked' if i == 0 else ''}>")
        nav.append(f"<label for='tab-{k}'>{esc(lab)}</label>")
        panels.append(f"<div class='tabpanel' data-tab='{k}'>{html}</div>")
    html = ("".join(inputs)
            + "<nav class='tabs' aria-label='Deck sections'>" + "".join(nav) + "</nav>"
            + "".join(panels))
    return "\n".join(css), html


TABS_JS = """<script>
(function(){
  var key='mtgtab:'+location.pathname;
  function pick(k){var el=k&&document.getElementById('tab-'+k);
    if(el){el.checked=true;return true;} return false;}
  var h=(location.hash||'').replace(/^#tab-/,'');
  if(!pick(h)){try{pick(localStorage.getItem(key));}catch(e){}}
  Array.prototype.forEach.call(document.querySelectorAll('.tabinput'),function(i){
    i.addEventListener('change',function(){
      var k=i.id.replace(/^tab-/,'');
      try{localStorage.setItem(key,k);}catch(e){}
      if(history.replaceState){history.replaceState(null,'','#tab-'+k);}
    });
  });
})();
</script>"""


def deadweight_html(rows, has_field=True):
    """"Pulling the least weight" — cards nothing in the deck is asking for.

    Deliberately NOT a cut list: the optimizer owns cuts and has its own guardrails.
    This just stops a 100-card list hiding its passengers. `None` means the fit engine
    couldn't run; an empty list is a real, and good, answer."""
    if rows is None:
        return ""
    note = ("" if has_field else
            "<p class='muted'>No EDHREC field data was reachable, so this is a "
            "fit-only read — judged on colors, roles, curve and theme alone.</p>")
    if not rows:
        return ("<div class='ok'>Nothing stands out — every card here either fills a "
                "role, ties to the theme, or brings real power.</div>" + note)
    med = rows[0].get("median")
    body = "".join(
        f"<tr><td>{esc(r['name'])}</td><td>{r['score']}</td>"
        f"<td>{esc(r['band'])}</td><td class='br'>{esc(r['why'])}</td></tr>"
        for r in rows)
    return (note +
            "<p class='muted'>Ranked <em>against the rest of this deck</em>"
            + (f" (its median fit is {med})" if med is not None else "") +
            ": these score below the middle <em>and</em> show no theme tie or staple "
            "pull. Not an instruction to cut — a prompt to check whether each one is "
            "doing a job the numbers can't see.</p>"
            "<div class='tablewrap'><table class='data'><thead><tr><th>Card</th>"
            "<th>Fit</th><th>Band</th><th>Why it stands out</th></tr></thead>"
            f"<tbody>{body}</tbody></table></div>")


def render_dashboard(title, commander, subtitle, rep, enriched, theme,
                     sections, notes=None, buylist=None, shared=None,
                     assessment=None, similar=None, details=None, combos=None, mana=None,
                     editable=False, stem="", missing=None, changes=None,
                     dead=None, cuts=None, has_field=True, sim=None):
    t = THEMES.get(theme, THEMES["default"])
    modal_css = card_modal_css(t)
    modal_block = card_modal_block(details or {}, editable=editable, stem=stem)
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
        tiles.append(stat_tile(
            "Bracket", assessment.get("bracket_effective", assessment["bracket"]),
            (assessment.get("bracket_effective_name", assessment["bracket_name"])
             + (f" · your setting (detected {assessment['bracket_detected']})"
                if assessment.get("bracket_mismatch") else ""))))
        tiles.append(stat_tile("Power", f"{assessment['power']}",
                               f"/100 · {assessment['tier']}"))
    tiles += [stat_tile("Ramp", cats.get("ramp", 0)),
              stat_tile("Removal", cats.get("removal", 0)),
              stat_tile("Draw", cats.get("draw", 0))]
    tiles = "".join(tiles)

    power_sec = (f"<section><h2>Power &amp; Bracket</h2>{power_html(assessment)}"
                 f"{bracket_form(stem, editable, assessment)}"
                 "</section>" if assessment else "")
    combo_sec = (f"<section><h2>Combo Watch</h2>{combos_html(combos)}</section>"
                 if combos is not None else "")
    cuts_sec = (f"<section><h2>If You Must Cut</h2>{cuts_html(cuts)}</section>"
                if cuts and cuts.get("rows") else "")
    dead_sec = (f"<section><h2>Pulling the Least Weight</h2>"
                f"{deadweight_html(dead, has_field)}</section>"
                if dead is not None else "")

    notes_sec = (f"<section><h2>Game Plan &amp; Player Notes</h2>"
                 f"{notes_html(notes)}</section>" if notes else "")
    pip_sec = (f"<section><h2>Color / Pip Demand</h2>{pip_table(rep)}</section>"
               if rep.get("pip_demand") else "")
    mana_sec = (f"<section><h2>Consistency &amp; Manabase</h2>{manabase_html(mana)}</section>"
                if mana is not None else "")
    # Sequenced play sits right under the exact closed forms, on purpose: the two
    # engines answer different questions and are meant to disagree.
    goldfish_block = goldfish_html(sim)
    mana_sec += (f"<section><h2>Goldfish Simulation</h2>{goldfish_block}</section>"
                 if goldfish_block else "")
    buy_sec = (f"<section><h2>Buy &amp; Replace</h2>{buylist_html(buylist)}</section>"
               if buylist else "")
    sim_sec = (f"<section><h2>Commanders That Also Fit This Shell</h2>"
               f"{similar_html(similar)}</section>" if similar is not None else "")
    shared_sec = (f"<section><h2>Shared Across Decks</h2>{shared_html(shared)}"
                  "</section>" if shared is not None else "")

    deck_sec = (f"<section><h2>Decklist by Section</h2>"
                f"{add_card_block(stem, editable)}"
                f"{sections_html(sections, enriched, shared, missing=missing, changes=changes)}"
                f"</section>")
    own_sec = f"<section><h2>Ownership</h2>{ownership_block(rep)}</section>"
    curve_sec = (f"<section><h2>Mana Curve (MV Spread)</h2>{curve_svg(rep['curve'], t)}"
                 f"{curve_note(enriched)}</section>")

    # The Mana-health advisory: text-only chip in the tab label (tabs_block
    # escapes label markup) + a one-line warn strip above the tiles. Advisory,
    # never an action — the optimizer is not involved and manual edits stand.
    health = mana_health(mana, rep)
    mana_label = "⚠ Mana" if health else "Mana"
    health_strip = ""
    if health:
        shown = " · ".join(esc(h) for h in health[:2])
        more = f" · +{len(health) - 2} more" if len(health) > 2 else ""
        health_strip = (f"<div class='banner warn'><b>⚠ Mana health:</b> {shown}{more}"
                        " — see the Mana tab.</div>")

    # Grouping is presentation only — every section's generator is untouched, and the
    # order inside each tab matches the old top-to-bottom page order.
    tab_css, tabs = tabs_block([
        ("deck",  "Deck",  deck_sec + own_sec),
        ("mana",  mana_label,  curve_sec + pip_sec + mana_sec),
        ("power", "Power", power_sec + combo_sec + dead_sec + cuts_sec),
        ("buy",   "Buy",   buy_sec),
        ("plan",  "Plan",  notes_sec),
        ("more",  "More",  sim_sec + shared_sec),
    ])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>{fonts}
<style>
/* shared design tokens (scripts/assets/tokens.css) — inlined so this file stays
   self-contained; identical to what the web app serves at /static/tokens.css */
{_asset('tokens.css')}
:root {{
  --void:{t['void']}; --panel:{t['panel']}; --accent:{t['accent']};
  --accent2:{t['accent2']}; --warn:{t['warn']}; --text:{t['text']};
  --muted:{t['muted']}; --gold:{t['gold']};
  --font-display:{t['display']}; --font-body:{t['head']}; --font-mono:{t['mono']};
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--void); color:var(--text);
  font-family:{t['head']}; line-height:1.5; }}
.wrap {{ max-width:960px; margin:0 auto; padding:var(--sp-6) var(--sp-5) var(--sp-8); }}
header h1 {{ font-family:{t['display']}; font-size:var(--fs-3xl); margin:0 0 var(--sp-1);
  color:var(--accent); letter-spacing:.5px; }}
header .sub {{ color:var(--muted); font-size:var(--fs-md); }}
header .cmd {{ color:var(--gold); font-family:{t['mono']}; font-size:var(--fs-sm);
  margin-top:6px; }}
.printbtn {{ margin-top:var(--sp-3); cursor:pointer; background:transparent;
  color:var(--accent); border:1px solid rgba(255,255,255,.25);
  border-radius:var(--r-pill); padding:var(--sp-2) var(--sp-4);
  font-family:{t['mono']}; font-size:var(--fs-xs); min-height:44px; }}
.printbtn:hover {{ border-color:var(--accent); }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:var(--sp-3); margin:var(--sp-6) 0; }}
.tile {{ background:var(--panel); border:1px solid rgba(255,255,255,.06);
  border-radius:var(--r-md); padding:var(--sp-4); text-align:center; }}
.tile-val {{ font-family:{t['display']}; font-size:var(--fs-2xl); color:var(--accent2);
  line-height:1; }}
.tile-label {{ color:var(--muted); text-transform:uppercase; font-size:var(--fs-2xs);
  letter-spacing:1.5px; margin-top:6px; }}
.tile-note {{ color:var(--muted); font-size:var(--fs-2xs); margin-top:4px; }}
section {{ background:var(--panel); border:1px solid rgba(255,255,255,.06);
  border-radius:var(--r-lg); padding:var(--sp-5); margin:var(--sp-4) 0; }}
section h2 {{ font-family:{t['display']}; margin:0 0 var(--sp-3); color:var(--accent);
  font-size:var(--fs-xl); }}
table.data {{ width:100%; border-collapse:collapse; font-family:{t['mono']};
  font-size:var(--fs-sm); }}
table.data th, table.data td {{ text-align:left; padding:var(--sp-2) var(--sp-3);
  border-bottom:1px solid rgba(255,255,255,.07); }}
table.data th {{ color:var(--muted); font-weight:600; }}
tr.warn td {{ color:var(--warn); }}
.cardlink {{ color:var(--accent); cursor:pointer; text-decoration:none;
  border-bottom:1px dotted rgba(255,255,255,.35); }}
.cardlink:hover {{ color:var(--accent2); border-bottom-color:var(--accent2); }}
.cardlink:focus {{ outline:2px solid var(--accent); outline-offset:2px; border-radius:2px; }}
.pip {{ display:inline-block; width:12px; height:12px; border-radius:50%;
  margin-right:8px; vertical-align:middle;
  box-shadow:0 0 0 1px rgba(0,0,0,.4) inset; }}
.ok {{ color:var(--accent2); font-weight:600; }}
.warnbox {{ color:var(--warn); }}
.warnbox ul {{ margin:var(--sp-2) 0 0; padding-left:18px; }}
.banner.warn {{ background:color-mix(in srgb, var(--warn) 12%, transparent);
  border:1px solid var(--warn); border-radius:var(--r-md);
  padding:var(--sp-2) var(--sp-4); margin:0 0 var(--sp-4); font-size:var(--fs-sm); }}
.muted {{ color:var(--muted); }}
h3 {{ font-family:{t['head']}; color:var(--gold); margin:var(--sp-4) 0 var(--sp-2);
  border-bottom:1px solid rgba(255,255,255,.08); padding-bottom:4px; }}
h3 .count {{ color:var(--muted); font-size:var(--fs-xs); float:right; }}
ul.cards {{ list-style:none; padding:0; margin:0; columns:2; column-gap:var(--sp-5);
  font-family:{t['mono']}; font-size:var(--fs-xs); }}
ul.cards li {{ break-inside:avoid; padding:var(--sp-1) 0; }}
.mv {{ display:inline-block; min-width:20px; color:var(--accent);
  font-size:var(--fs-xs); }}
.mv.dim {{ color:var(--muted); }}
.pr {{ color:var(--muted); font-size:var(--fs-2xs); margin-left:6px; }}
ul.notes {{ margin:var(--sp-2) 0 var(--sp-3); padding-left:20px; }}
ul.notes li {{ margin:var(--sp-1) 0; }}
section p {{ margin:var(--sp-2) 0; }}
code {{ font-family:{t['mono']}; background:rgba(255,255,255,.06);
  padding:2px var(--sp-2); border-radius:5px; font-size:var(--fs-xs); }}
.tablewrap {{ overflow-x:auto; max-width:100%; border-radius:var(--r-md); }}
.buytoggle {{ display:flex; flex-wrap:wrap; align-items:center; gap:var(--sp-2);
  margin-bottom:14px; }}
.thbtn {{ background:transparent; color:var(--text); cursor:pointer;
  border:1px solid rgba(255,255,255,.18); border-radius:var(--r-pill);
  padding:var(--sp-1) var(--sp-3); font-family:{t['mono']}; font-size:var(--fs-xs); }}
.thbtn:hover {{ border-color:var(--accent); }}
.thbtn.active {{ background:var(--accent); color:#000; border-color:var(--accent);
  font-weight:700; }}
.buysum {{ color:var(--muted); font-family:{t['mono']}; font-size:var(--fs-xs);
  margin-left:auto; }}
.buytable td.bc {{ color:var(--text); }}
.buytable td.bp {{ color:var(--accent2); white-space:nowrap; }}
.buytable td.br {{ color:var(--muted); font-size:var(--fs-xs); }}
.repl {{ color:var(--warn); }}
.tier {{ color:var(--muted); font-size:var(--fs-2xs); border:1px solid rgba(255,255,255,.15);
  border-radius:var(--r-sm); padding:0 var(--sp-2); margin-left:6px; }}
.bracketline {{ display:flex; align-items:baseline; gap:var(--sp-3); flex-wrap:wrap;
  margin-bottom:8px; }}
.bnum {{ font-family:{t['display']}; font-size:var(--fs-2xl); color:var(--accent2); }}
.explain {{ margin:var(--sp-2) 0; font-size:var(--fs-sm); }}
.explain > summary {{ cursor:pointer; color:var(--muted); }}
.explain > p {{ margin:var(--sp-1) 0 0; }}
.bracketform {{ display:flex; align-items:center; gap:var(--sp-2); flex-wrap:wrap;
  margin-top:var(--sp-3); font-size:var(--fs-sm); }}
.bracketform select, .bracketform button {{ font:inherit; padding:var(--sp-1) var(--sp-2);
  border-radius:var(--r-sm); border:1px solid rgba(255,255,255,.18);
  background:rgba(255,255,255,.06); color:inherit; }}
.bname {{ color:var(--gold); font-family:{t['head']}; text-transform:uppercase;
  letter-spacing:1.5px; font-size:var(--fs-xs); }}
.pscore {{ margin-left:auto; font-family:{t['display']}; font-size:var(--fs-2xl);
  color:var(--accent); }}
.pwrtable td {{ border:none; padding:var(--sp-1) var(--sp-2) var(--sp-1) 0; vertical-align:middle; }}
.pwrtable td:first-child {{ width:150px; color:var(--muted); }}
.pwrbar {{ width:40%; }}
.pwrbar span {{ display:block; height:9px; border-radius:5px;
  background:linear-gradient(90deg,var(--accent2),var(--accent)); }}
.pwrnum {{ font-size:var(--fs-xs); white-space:nowrap; }}
.imgnote {{ font-size:var(--fs-xs); margin:0 0 var(--sp-3); }}
.cardgrid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(104px,1fr));
  gap:var(--sp-3); margin:var(--sp-2) 0 var(--sp-3); }}
.mc {{ margin:0; position:relative; }}
.mc img {{ width:100%; aspect-ratio:5/7; object-fit:cover; display:block;
  border-radius:5% / 3.6%; background:rgba(255,255,255,.05); }}
.mc .qty {{ position:absolute; top:4px; right:4px; background:var(--accent);
  color:#000; font-family:{t['mono']}; font-size:var(--fs-2xs); font-weight:700;
  padding:0 var(--sp-2); border-radius:var(--r-sm); }}
.sb {{ display:inline-block; font-family:{t['mono']}; font-size:var(--fs-2xs);
  font-weight:700; padding:0 var(--sp-2); border-radius:var(--r-sm); background:var(--accent2);
  color:#000; }}
.mc .sb {{ position:absolute; top:4px; left:4px; }}
.sb.need {{ background:var(--warn); color:#000; }}
.bb {{ display:inline-block; font-family:{t['mono']}; font-size:var(--fs-2xs);
  font-weight:700; letter-spacing:.5px; padding:0 var(--sp-1); border-radius:var(--r-sm);
  background:var(--accent2); color:#000; }}
.mc .bb {{ position:absolute; bottom:22px; left:4px; }}
.nb {{ display:inline-block; font-family:{t['mono']}; font-size:var(--fs-2xs);
  font-weight:700; letter-spacing:.5px; padding:0 var(--sp-1);
  border-radius:var(--r-sm); background:var(--gold); color:#000; }}
.mc .nb {{ position:absolute; top:22px; right:4px; }}
.need {{ color:var(--warn); font-weight:700; }}
.mc figcaption {{ font-family:{t['mono']}; font-size:var(--fs-2xs); color:var(--muted);
  margin-top:3px; line-height:1.25; }}
.mc figcaption .mv {{ min-width:0; margin-right:3px; }}
.mc figcaption .pr {{ display:block; margin:0; }}
footer {{ color:var(--muted); font-size:var(--fs-xs); margin-top:30px;
  text-align:center; }}
@media (max-width:560px) {{ ul.cards {{ columns:1; }} header h1 {{ font-size:var(--fs-2xl); }}
  .buysum {{ margin-left:0; width:100%; }} }}
/* --- subtabs: state lives in :checked, so the file needs no JS to work --- */
.tabinput {{ position:absolute; width:1px; height:1px; overflow:hidden;
  clip:rect(0 0 0 0); clip-path:inset(50%); white-space:nowrap; }}
.tabs {{ display:flex; gap:var(--sp-2); overflow-x:auto; -webkit-overflow-scrolling:touch;
  position:sticky; top:0; z-index:5; padding:var(--sp-3) 0;
  background:var(--void); border-bottom:1px solid rgba(255,255,255,.08);
  scrollbar-width:none; }}
.tabs::-webkit-scrollbar {{ display:none; }}
.tabs label {{ flex:none; cursor:pointer; user-select:none; white-space:nowrap;
  min-height:44px; display:inline-flex; align-items:center;
  padding:var(--sp-2) var(--sp-4); border:1px solid rgba(255,255,255,.18);
  border-radius:var(--r-pill); color:var(--text); font-family:{t['mono']};
  font-size:var(--fs-xs); letter-spacing:.5px; }}
.tabs label:hover {{ border-color:var(--accent); }}
.tabpanel {{ display:none; }}
.tabpanel > section:first-child {{ margin-top:var(--sp-4); }}
{tab_css}
{add_card_css(t) if editable else ''}
{modal_css}
/* ---------------------------------------------------------------------------
   PRINT — this block IS the PDF export.

   The repo generates no PDF of its own on purpose: `scripts/` is stdlib-only, and
   card images are browser hotlinks that a server-side renderer could not fetch
   (docs/card-images.md). So "save as PDF" is the browser's own print dialog, and
   how good that PDF is comes down to what is written here. Both surfaces render
   through generate(), so this lands on CLI dashboards and the web app at once.

   It is emitted AFTER add_card.css and card_panel.css deliberately. @media adds no
   specificity, so a print rule sitting above those files loses to any later rule of
   equal weight — the old block was above both and its `.ac {{ display:none }}`
   worked only because add_card.css happens never to set `display`. Ordering it last
   is what makes the rules below authoritative instead of lucky.

   Two rules of thumb: force ink-on-paper (#000 text, #fff ground, #444 for text
   that is genuinely secondary, #ccc/#999 hairlines), and reach for
   print-color-adjust:exact ONLY where the colour IS the data and would otherwise be
   dropped — the length of a bar, a mana swatch — never for decoration.
   --------------------------------------------------------------------------- */
@media print {{
  /* No `size:` — the dialog's Letter/A4 choice should win. */
  @page {{ margin:12mm; }}

  /* tokens.css tunes its hairlines for dark surfaces (white at 7% alpha) and they
     vanish on paper; the elevation shadows are just noise in ink. Redefining the
     tokens fixes every consumer at once, the inlined card panel included. */
  :root {{ --line:#ccc; --line-strong:#999; --el-1:none; --el-2:none; --el-3:none; }}

  /* The core bug this block exists to fix: browsers DROP background colours when
     printing but KEEP text colour, so every dark theme printed near-white on white.
     `overflow` is reset because opening a card panel sets it inline on the body
     element. NOTE: never write that element's opening tag literally anywhere in this
     file above the real one — webapp/app.py splices its singleton-violation banner in
     at the first regex match for it, so a literal in a comment silently swallows the
     ILLEGAL alarm into a CSS comment where nobody can see it. */
  body {{ background:#fff !important; color:#000 !important;
    overflow:visible !important; orphans:3; widows:3; }}
  /* A hair of side padding rather than none: Chrome lets the dialog's "Margins:
     None" override @page, and this keeps text off the paper edge when it does. */
  .wrap {{ max-width:none; margin:0; padding:0 var(--sp-1); }}

  /* --- interactive chrome: every control here posts somewhere, and paper has
     nowhere to post to. The card panel is the load-bearing one — it is emitted on
     BOTH surfaces and is only `hidden` by attribute, so printing with a card open
     would otherwise drop a position:fixed sheet over the report (Chrome paints it
     on page 1, Firefox repeats it on every page). --- */
  .tabs, .ac, #ac, .bracketform, .buytoggle, .thbtn, .printbtn,
  #cardmodal, .cm-overlay {{ display:none !important; }}

  /* --- structure: one tab per page turns the report into chapters, and every
     panel already leads with a self-describing <h2>, so losing the tab bar costs
     nothing. `.tabpanel:first-of-type` would match NOTHING here (the tiles div is
     the first child of .wrap), which is why this is the adjacent-sibling form. --- */
  .tabpanel {{ display:block !important; }}
  .tabpanel + .tabpanel {{ break-before:page; }}

  /* Never blanket-avoid a break on `section`: the decklist alone runs to several
     pages, and forcing avoid on it makes the browser either ignore the rule or push
     an unbreakable box onto a fresh page and overflow it anyway. Headings are the
     right granularity — keep each one with the content it introduces. */
  section {{ background:none; border:0; border-radius:0; padding:0;
    margin:0 0 var(--sp-5); break-inside:auto; }}
  section + section {{ border-top:1px solid #ccc; padding-top:var(--sp-4); }}
  section > h2, h3 {{ break-after:avoid; break-inside:avoid; }}
  .tile, .tiles, .mc, .banner.warn, ul.notes li, details.explain,
  .warnbox {{ break-inside:avoid; }}

  /* overflow:auto SCROLLS on screen but CLIPS on paper, and the printable width is
     far narrower than the 960px column — so the widest tables would silently lose
     their right-hand columns. Let them use the full page and wrap instead. */
  .tablewrap {{ overflow:visible !important; max-width:none; border-radius:0; }}
  table.data {{ font-size:var(--fs-xs); break-inside:auto; }}
  table.data thead {{ display:table-header-group; }}
  table.data tr {{ break-inside:avoid; }}
  table.data th, table.data td {{ border-bottom:1px solid #ccc;
    overflow-wrap:anywhere; }}
  table.data th {{ color:#000; border-bottom:1px solid #999; }}
  ul.cards {{ columns:1; }}

  /* --- ink. Anything below is a theme colour picked to sit on a dark ground; on
     white it runs from low-contrast to invisible (the cloud/yshtola accents are
     about 1.7:1 on paper). --- */
  header h1, header .cmd, section h2, h3, .tile-val, .cardlink, .ok, .warnbox,
  .bnum, .bname, .pscore, .mv, .need, .repl, .buysum, .buytable td.bc,
  .buytable td.bp, .pwrtable td:first-child, .mc figcaption,
  .explain > summary {{ color:#000; }}
  header .cmd, .ok, .need, .repl, .buysum {{ font-weight:700; }}
  header .sub, .tile-label, .tile-note, .muted, h3 .count, .mv.dim, .pr,
  .buytable td.br, .tier, .imgnote, footer {{ color:#444; }}
  .tile {{ background:none; border:1px solid #ccc; }}
  .cardlink {{ border-bottom:none; text-decoration:none; }}
  code {{ background:none; border:1px solid #ccc; }}
  .banner.warn {{ background:none; border:1px solid #000; }}
  footer {{ border-top:1px solid #ccc; padding-top:var(--sp-2); }}
  /* The pip table's under-supported rows are flagged by colour ALONE, so on paper
     the warning simply disappears. Weight plus a rule restates it in ink. */
  tr.warn td {{ color:#000; font-weight:700; }}
  tr.warn td:first-child {{ border-left:3px solid #000; }}
  /* Focus rings follow the accent and would print around whatever the reader last
     clicked. */
  *:focus, *:focus-visible {{ outline:none !important; }}

  /* --- the two places colour genuinely IS the data --- */
  /* A power bar's meaning is its length, and a background is exactly what print
     drops. The track outline gives the eye a 100% reference to read it against. */
  .pwrbar {{ outline:1px solid #bbb; outline-offset:-1px; }}
  .pwrbar span {{ background:#444 !important; background-image:none !important;
    -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  /* Mana swatches keep their colour, but white mana is #f4efd6 — invisible on
     paper without a ring around it. */
  .pip {{ -webkit-print-color-adjust:exact; print-color-adjust:exact;
    box-shadow:none !important; border:1px solid #666; }}

  /* SVG fill is content paint rather than a background, so it is NOT dropped — the
     curve's value labels are drawn in the theme's near-white --text and print
     invisible. A presentation attribute has specificity 0, so these win outright. */
  svg text {{ fill:#000 !important; }}
  svg rect {{ fill:#bbb !important; opacity:1 !important; stroke:#333;
    stroke-width:1; }}

  /* A card whose image could not be fetched has its `src` REMOVED by the loader, on
     purpose, so the name reads cleanly instead of a broken icon. On screen that
     leaves a tidy placeholder; on paper `aspect-ratio:5/7` would reserve full card
     height for every one, so an offline print of a downloaded report becomes pages
     of blank frames. Collapsing them turns it into a dense list of names instead —
     which is what the figcaption was already there to provide.

     Note this matches EVERY image until the loader has run (they ship carrying
     `data-src`, not `src`), which is exactly the offline case this is for. That
     makes the second rule mandatory rather than defensive: the badges are absolutely
     positioned against the figure, so collapsing the image alone drops them straight
     onto the card name — measured as captions printing "6 ⇄2n Titan" instead of
     "6 Sun Titan". Returning them to flow puts them on their own line above it. */
  .mc img:not([src]) {{ display:none; }}
  .mc:has(img:not([src])) .qty, .mc:has(img:not([src])) .sb,
  .mc:has(img:not([src])) .bb, .mc:has(img:not([src])) .nb {{
    position:static; display:inline-block; margin:0 var(--sp-1) 0 0; }}

  /* The Buy tab's price filter hides rows with an INLINE display:none, so a report
     printed after filtering would silently omit buys with no visible filter to
     explain the gap. A paper report should never lose rows — restore them all, and
     the hidden .buytoggle above takes the now-meaningless control with it. */
  .buyrow {{ display:table-row !important; }}

  /* An explainer collapsed on screen must still print: the caveat is part of the
     number, and paper has no way to open a <details>. The old `.explain > p`
     rule could never do this — a closed <details> hides its children through the
     UA's ::details-content box, not through the child's own `display`, so every
     explainer printed as a bare summary line and the engine's text was lost.
     `.explain > p` stays as a harmless fallback for pre-::details-content engines. */
  details.explain::details-content {{ content-visibility:visible !important;
    block-size:auto !important; }}
  .explain > p {{ display:block !important; }}
}}
</style></head><body><div class="wrap">
<header>
  <h1>{esc(title)}</h1>
  <div class="sub">{esc(subtitle)}</div>
  {f'<div class="cmd">Commander: {esc(commander)}</div>' if commander else ''}
  <!-- Emitted on BOTH surfaces, unlike every other control here: window.print()
       needs no server, so it is the one button that still works in a downloaded
       file. It hides itself in print (see .printbtn in the @media print block). -->
  <button type="button" class="printbtn" onclick="window.print()"
    title="Opens your browser's print dialog — choose &quot;Save as PDF&quot; there to get a PDF">
    &#128424; Print / Save as PDF</button>
</header>
{health_strip}
<div class="tiles">{tiles}</div>
{tabs}
<footer>Generated by the MTG Commander Deckbuilder. Category counts &amp; any
prices are heuristic/estimates — verify uncertain cards.</footer>
</div>{modal_block}{IMG_LOADER}{TABS_JS}</body></html>"""


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
/* Same ink-on-paper rule as the dashboard's print block, in miniature: this is a
   second, self-contained document with its own theme colours and no CSS variables,
   so the overrides have to be literal. The caption is the card NAME — on a sheet
   whose images may not have loaded it is the only thing identifying the card, so it
   prints as primary text, not as the muted grey it is on screen. */
@media print {{
  @page {{ margin:12mm; }}
  body {{ background:#fff !important; color:#000 !important; }}
  .wrap {{ max-width:none; padding:0; }}
  h1 {{ color:#000; }}
  .banner {{ background:none !important; border:1px solid #999; color:#000; }}
  figure {{ break-inside:avoid; }}
  figure img {{ background:none !important; border:1px solid #ccc; }}
  /* The loader strips `src` when a fetch fails; without this every miss reserves a
     full card of blank paper. The qty chip is absolutely positioned against the
     figure, so it has to rejoin the flow or it lands on the caption. */
  figure img:not([src]) {{ display:none; }}
  figure:has(img:not([src])) .qty {{ position:static; display:inline-block;
    margin:0 6px 0 0; }}
  figcaption {{ color:#000; }}
  .qty {{ background:none !important; color:#000; border:1px solid #666; }}
}}
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


_SIM_UNSET = object()   # "not passed" — distinct from an explicit sim=None


def generate(deck_path, collection_path, title="Commander Deck", commander="",
             subtitle="Commander (EDH) deck dashboard", theme="default",
             decks_dir=None, size="normal", want_visual=False, editable=False,
             sim=_SIM_UNSET):
    """Load a deck + collection and return rendered HTML. Shared by the CLI and
    the web app. Returns {'dashboard': str, 'visual': str|None, 'assessment': dict|None,
    'report': dict}.

    `sim` is the goldfish Monte Carlo report: omit it and this self-computes through
    the shared disk cache (`goldfish.sim_for_deck`); pass `sim=None` to leave the
    section out entirely. Because the webapp re-renders this on EVERY page view, the
    cache is what keeps a page load at one file read instead of one simulation."""
    # One pass through the shared analysis hub (load + enrich + report + power +
    # manabase + combos) — the same pipeline the assess packet + auto-builder use.
    a = deckcore.analyze_deck(deck_path, collection_path)
    coll, idx, deck = a["coll"], a["idx"], a["deck"]
    enriched, missing, rep = a["enriched"], a["missing"], a["report"]
    assessment, mana, combos, attrs = a["assessment"], a["mana"], a["combos"], a["attrs"]
    stem = deck_path[:-4] if deck_path.endswith(".txt") else deck_path

    # Fold Commander Spellbook's one-aways into the same combos dict combos.csv
    # feeds, deduped by piece-set — one Combo Watch, one Buy view, two sources.
    # Cached + graceful: unreachable CSB just means combos.csv stands alone.
    try:
        import spellbook
        have = {frozenset(mtglib.name_keys(p) for p in c.get("pieces", []))
                for c in (combos or {}).get("near", []) + (combos or {}).get("complete", [])}
        extra = [n for n in spellbook.near_for_deck(deck_path, idx)
                 if frozenset(mtglib.name_keys(p) for p in n["name"].split(" + ")) not in have]
        if extra:
            combos = dict(combos or {}, near=list((combos or {}).get("near", [])) + extra)
    except Exception:
        pass

    # Sequenced play, next to the exact closed forms in the Mana tab. Imported here
    # (not at module scope) so the spoke keeps its engine list flat, and guarded
    # because a failed simulation must cost the page a section, never the render.
    if sim is _SIM_UNSET:
        try:
            import goldfish
            sim = goldfish.sim_for_deck(deck_path, collection_path)
        except Exception:
            sim = None

    sections = load_deck_sections(deck_path)
    notes = load_notes(f"{stem}.notes.md")
    # The Buy view is fed by EVERY engine that knows about a gap — curated buylist,
    # one-away combos (unowned piece), and the decklist's own BUY-badged cards —
    # merged in the hub with provenance. A combo the deck is one card away from
    # completing IS a buy signal; it used to die inside the Combo Watch section.
    buylist = deckcore.buy_signals(load_buylist(f"{stem}.buylist.csv"),
                                   combos, missing, idx)
    changes = deckcore.load_changes(f"{stem}.changes.csv")

    shared = None
    dd = decks_dir if decks_dir is not None else os.path.dirname(deck_path)
    if dd:
        try:
            shared = deck_conflicts.shared_for_deck(deck_path, idx, dd)
        except Exception:
            shared = None
    try:
        _, _, similar = simc.find(deck_path, idx, simc.load_commanders(), attrs)
    except Exception:
        similar = None

    # Pre-bind: the try below can fail BEFORE assigning these, and both are read again
    # outside it (dead-weight pass, has_field). Leaving them unbound turned a degraded
    # page into an UnboundLocalError crash — the one failure mode this repo forbids.
    refs = ctx = None
    try:
        refs = power.load_refs()
        ctx = deck_fit.deck_context(deck_path, enriched, commander,
                                    field=deck_fit.load_field(commander, idx),
                                    synergy=deck_fit.load_synergy(commander, idx))
        staples = deck_fit.load_role_staples()
        details = build_card_details(sections, enriched, idx, load_card_notes(),
                                     rep=rep, ctx=ctx, refs=refs, staples=staples,
                                     edhrec_alts=_edhrec_alts(commander, idx),
                                     fetch=(mana or {}).get("fetch"))
    except Exception:
        details = None
    if similar:
        try:
            details = add_commander_details(details, similar, idx)
        except Exception:
            pass

    # which cards are pinned, and to which deck — the panel shows and toggles
    try:
        pins = deckcore.load_pins()
        if details:
            for k, d in details.items():
                d["pinned"] = pins.get(k)
    except Exception:
        pass

    # merge shared-across-decks status into the panel payload (drives the edit view's badge)
    if details and shared:
        try:
            for v in shared.values():
                d = details.get(mtglib._norm(v["name"]))
                if d is not None:
                    d["shared"] = {"covered": v["covered"], "owned": v["owned"],
                                   "count": len(v["decks"])}
        except Exception:
            pass

    # "Pulling the least weight" — reuses the ctx/refs already built above, so it costs
    # one extra pass over the list and no extra IO. None = the fit engine couldn't run.
    dead = None
    try:
        prot, notes_text = set(), (notes or "").lower()
        prot |= {mtglib._norm(commander)} if commander else set()
        prot |= {mtglib._norm(c.name) for c in enriched
                 if c.name.lower() in notes_text}
        section_of = {mtglib._norm(n): label for label, cards in sections
                      for _q, n in cards}
        dead = deck_fit.dead_weight(enriched, rep, ctx, refs, protected=prot,
                                    section_of=section_of)
    except Exception:
        dead = None

    # "What do I cut" — the most-asked deckbuilding question, answered with the
    # optimizer's OWN value scorer (deck_fit.card_value) so the two surfaces can never
    # disagree about what a card is worth. Advisory and read-only; protected cards are
    # shown flagged rather than hidden.
    cuts = None
    try:
        # ctx already carries the archetype-aware template (deck_context computes it
        # once) — no spoke-imports-spoke reach into optimize needed since Phase 12.
        ranges = (ctx or {}).get("role_ranges") or deckcore.role_ranges(
            (ctx or {}).get("archetype"))
        cuts = deck_fit.cut_ranking(
            enriched, rep, ctx, refs, (ctx or {}).get("field") or {},
            protected=prot, ranges=ranges,
            cats=dict(rep.get("categories") or {}), limit=10)
    except Exception:
        cuts = None

    url_stem = os.path.splitext(os.path.basename(deck_path))[0]
    dashboard = render_dashboard(title, commander, subtitle, rep, enriched, theme,
                                 sections, notes, buylist, shared, assessment,
                                 similar, details, combos, mana,
                                 editable=editable, stem=url_stem, missing=missing,
                                 changes=changes, dead=dead, cuts=cuts,
                                 has_field=bool((ctx or {}).get("field")), sim=sim)
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
