#!/usr/bin/env python3
"""Print-exact proxy sheets: 63mm x 88mm cards, nine to a page, cut and play.

The one genuinely print-geometry-shaped artifact in this project. A dashboard's
print layout can reflow and stay correct; a proxy is WRONG if it is not the size
of a Magic card, so this page is specified in millimetres end to end and the
browser's print dialog is the (only) renderer — same reasoning as the deck
report's PDF story: `scripts/` is stdlib-only and card images are browser
hotlinks (docs/card-images.md), so the browser is the only place the images and
the paper geometry meet.

Physical contract:
  * Every cell is exactly 63mm x 88mm (a real card, sleeve-checked).
  * Nine cells per sheet, 3x3, no gaps — shared edges mean single scissor cuts.
  * A 3x3 sheet is 189mm x 264mm, which fits BOTH Letter (203.9 x 267.4mm
    printable at 6mm margins) and A4 (198 x 285mm) — so @page sets margin only
    and lets the dialog pick the paper.
  * `print-color-adjust:exact` on the cells: the art IS the content, and the
    print dialog's "Background graphics" checkbox must not be able to blank it.
  * The ONE setting that can break the size is the dialog's "Scale" — the page
    tells the player to print at 100%.

Images resolve by exact printing (set code + collector number, from the
ManaPool/Sorted export) when the collection knows one, else by name. Both are
Scryfall hotlinks that the player's browser fetches at print time.

Usage:
  python3 proxy_sheet.py --deck data/decks/<stem>.txt --collection <coll> --out proxies.html
  python3 proxy_sheet.py --deck ... --collection ... --missing      # only unowned copies
  python3 proxy_sheet.py --cards "Smaug, Wicked Worm" --cards "Sol Ring" --collection <coll>
  python3 proxy_sheet.py --list arrivals.txt --collection <coll>    # '<qty> <name>' lines

Playtest proxies for tuning decks before buying — not for sanctioned play.
The footer on every sheet says so.
"""
import argparse
import html
import os
import sys

import card_image
import mtglib

CELLS_PER_SHEET = 9


def esc(s):
    return html.escape(str(s), quote=True)


def _cells(entries, coll_idx, size):
    """entries: [(qty, name)] -> one cell dict per physical copy.

    Exact printing wins (the proxy then matches the sleeve it stands in for);
    the by-name API is the fallback for cards the collection has no printing
    of — which is exactly the --missing case, where there is nothing to match.
    The set/num ride along as data attributes for the page's batch loader; the
    url is the per-image fallback when the batch cannot resolve a card.
    """
    cells = []
    for qty, name in entries:
        ref = mtglib.lookup(coll_idx, name) if coll_idx else None
        set_code = num = ""
        if ref is not None and ref.set_code and ref.collector_number:
            set_code, num = ref.set_code, ref.collector_number
            url = card_image.image_url_by_set(set_code, num, size)
        elif ref is not None and ref.scryfall_id:
            url = card_image.image_url(ref.scryfall_id, size)
        else:
            url = card_image.image_url_by_name(name, size)
        for _ in range(max(1, int(qty))):
            cells.append({"name": name, "url": url, "set": set_code, "num": num})
    return cells


def _deck_entries(deck_path, coll_idx, missing_only):
    entries = []
    with open(deck_path, encoding="utf-8") as f:
        deck = mtglib.parse_deck(f.read())
    for d in deck:
        qty = d.quantity
        if missing_only:
            ref = mtglib.lookup(coll_idx, d.name) if coll_idx else None
            owned = ref.quantity if ref else 0
            qty = max(0, d.quantity - owned)
        if qty:
            entries.append((qty, d.name))
    return entries


def _buylist_entries(deck_path):
    """One proxy per buylist row — the playtest-before-you-buy sheet.

    Decks here are built from owned cards only (optimizer rule, 2026-08-11), so
    a deck's own cards never need proxying; the cards worth printing are the
    ones on `<stem>.buylist.csv` that the player is DECIDING whether to buy.
    Sleeve the proxy over the card its `Replaces` column names, play a few
    games, then spend the money or don't."""
    import csv as _csv
    path = os.path.splitext(deck_path)[0] + ".buylist.csv"
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in _csv.DictReader(f):
            name = (row.get("Card") or "").strip()
            if name:
                entries.append((1, name))
    return entries


def generate_html(cells, title="Proxy Sheet", size="large"):
    """The whole page from cell dicts. Shared verbatim by the CLI and the app."""
    sheets = []
    for i in range(0, len(cells), CELLS_PER_SHEET):
        chunk = cells[i:i + CELLS_PER_SHEET]
        figs = "".join(
            f"<figure class='px'><span class='px-name'>{esc(c['name'])}</span>"
            f"<img loading='lazy' data-src='{esc(c['url'])}' alt='{esc(c['name'])}'"
            f" data-set='{esc(c['set'])}' data-num='{esc(c['num'])}'>"
            f"</figure>" for c in chunk)
        sheets.append(f"<section class='sheet'>{figs}</section>")

    n = len(cells)
    pages = (n + CELLS_PER_SHEET - 1) // CELLS_PER_SHEET
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} — Proxies</title>
<style>
/* Screen: a dark preview around the sheets. Print: nothing but the sheets. */
body {{ margin:0; background:#14171c; color:#e8ecf2;
  font-family:system-ui, sans-serif; }}
.bar {{ padding:14px 18px; display:flex; gap:14px; align-items:center;
  flex-wrap:wrap; }}
.bar h1 {{ font-size:1.1rem; margin:0; }}
.bar .note {{ color:#9aa4b2; font-size:.85rem; max-width:52ch; }}
.bar button {{ cursor:pointer; font:inherit; padding:8px 16px;
  border-radius:999px; border:1px solid #4a5568; background:transparent;
  color:#7dd3c0; min-height:44px; }}
.sheet {{ display:grid; grid-template-columns:repeat(3, 63mm);
  width:189mm; margin:16px auto; background:#fff; }}
.px {{ width:63mm; height:88mm; margin:0; position:relative;
  outline:0.25mm solid #b8b8b8; overflow:hidden; background:#fff; }}
/* The name paints FIRST, under the image: if a hotlink fails at the printer,
   the cell still says which card it was standing in for. */
.px-name {{ position:absolute; inset:0; display:flex; align-items:center;
  justify-content:center; text-align:center; padding:4mm; color:#222;
  font-size:.8rem; }}
.px img {{ position:absolute; inset:0; width:63mm; height:88mm;
  object-fit:cover; display:block; }}
.px img:not([src]) {{ display:none; }}
@media print {{
  /* margin only, no size: 189x264mm fits Letter AND A4 at 6mm — the dialog
     keeps the paper choice. Scale must stay 100%; the bar says so on screen. */
  @page {{ margin:6mm; }}
  body {{ background:#fff !important; }}
  .bar {{ display:none; }}
  .sheet {{ margin:0 auto; break-after:page; }}
  .sheet:last-child {{ break-after:auto; }}
  .px, .px img {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
}}
</style></head><body>
<div class="bar">
  <h1>{esc(title)}</h1>
  <button type="button" onclick="window.print()"
    title="Print at 100% scale — &quot;Fit to page&quot; would shrink the cards off-size">&#128424; Print at 100%</button>
  <span class="note">{n} card{'' if n == 1 else 's'} on {pages} sheet{'' if pages == 1 else 's'} —
  63&times;88&nbsp;mm each, nine per page. Set printer scale to <b>100%</b> (not
  &ldquo;fit&rdquo;), keep &ldquo;Background graphics&rdquo; on, and cut along the grey
  lines. Images load live from Scryfall, so print from a browser with internet.
  Playtest proxies &mdash; not for sanctioned play.</span>
</div>
{''.join(sheets)}
{_proxy_loader(size)}
</body></html>"""


def _proxy_loader(size):
    """A proxy-specific image loader, not the dashboard's shared one — on purpose.

    The shared loader (assets/card_images.html) batch-resolves by NAME and reads
    `image_uris.normal`: right for a dashboard thumbnail, wrong twice over for a
    proxy, which wants the player's EXACT PRINTING at print resolution. Same
    architecture though, and the same hard-won rate rules: /cards/collection in
    75-identifier batches with one retry, and a 700ms stagger on the per-image
    fallback (400ms was over Scryfall's limit and printed a page of 429 glyphs).
    """
    want = size if size in ("small", "normal", "large", "png") else "large"
    return """<script>
(function(){
  var SIZE=%s;
  var imgs=[].slice.call(document.querySelectorAll('img[data-src]'));
  if(!imgs.length) return;
  function keyOf(i){var s=i.getAttribute('data-set'),n=i.getAttribute('data-num');
    return (s&&n)?('sn:'+s.toLowerCase()+':'+n.toLowerCase()):('nm:'+(i.getAttribute('alt')||'').toLowerCase());}
  var byKey={};
  imgs.forEach(function(i){var k=keyOf(i);(byKey[k]=byKey[k]||[]).push(i);});
  var keys=Object.keys(byKey);
  function ident(k){
    if(k.slice(0,3)==='sn:'){var p=k.slice(3).split(':');return {set:p[0], collector_number:p[1]};}
    return {name:(byKey[k][0].getAttribute('alt')||'')};
  }
  function art(c){var iu=c.image_uris||(c.card_faces&&c.card_faces[0]&&c.card_faces[0].image_uris);
    return iu&&(iu[SIZE]||iu.large||iu.normal);}
  function chunk(a,n){var r=[];for(var i=0;i<a.length;i+=n)r.push(a.slice(i,i+n));return r;}
  var batches=chunk(keys,75), pending=batches.length;
  function apply(c){
    var url=art(c); if(!url) return;
    var sn=c.set&&c.collector_number?('sn:'+c.set.toLowerCase()+':'+String(c.collector_number).toLowerCase()):null;
    var nm='nm:'+(c.name||'').toLowerCase();
    [sn,nm].forEach(function(k){ if(k&&byKey[k]) byKey[k].forEach(function(i){ if(!i.getAttribute('src')) i.src=url; }); });
  }
  function runBatch(batch, attempt){
    fetch('https://api.scryfall.com/cards/collection',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({identifiers:batch.map(ident)})})
      .then(function(r){return r.ok?r.json():null;}).then(function(j){
        if(j&&j.data) j.data.forEach(apply);
        if(!j&&attempt<1){ setTimeout(function(){ runBatch(batch,attempt+1); },1500); return; }
        if(--pending===0) fallback();
      }).catch(function(){
        if(attempt<1){ setTimeout(function(){ runBatch(batch,attempt+1); },1500); return; }
        if(--pending===0) fallback();
      });
  }
  batches.forEach(function(b){ runBatch(b,0); });
  function fallback(){
    var rest=imgs.filter(function(i){ return !i.getAttribute('src'); });
    if(!rest.length) return;
    var q=rest.slice(), timer=setInterval(function(){
      var i=q.shift(); if(!i){clearInterval(timer);return;}
      if(!i.getAttribute('src')){
        i.onerror=function(){ this.onerror=null; this.removeAttribute('src'); };
        i.src=i.getAttribute('data-src');
      }
    },700);
  }
})();
</script>""" % _json_str(want)


def _json_str(s):
    import json
    return json.dumps(s)


def build(deck=None, collection=None, cards=None, list_file=None,
          missing=False, buylist=False, size="large", title=None):
    """Resolve inputs to (cells, title). The one entry point both surfaces use."""
    coll_idx = None
    if collection:
        coll_idx = mtglib.index_by_name(mtglib.load_collection(collection))
    if deck:
        stem = os.path.splitext(os.path.basename(deck))[0]
        if buylist:
            entries = _buylist_entries(deck)
            ttl = title or f"{stem} — buylist playtest proxies"
        else:
            entries = _deck_entries(deck, coll_idx, missing)
            ttl = title or (f"{stem} — missing cards" if missing else stem)
    else:
        entries = []
        if list_file:
            with open(list_file, encoding="utf-8") as f:
                for d in mtglib._parse_namelist(f.read()):
                    entries.append((d.quantity, d.name))
        for name in cards or []:
            entries.append((1, name))
        ttl = title or "Proxy Sheet"
    return _cells(entries, coll_idx, size), ttl


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deck", help="deck file to proxy")
    ap.add_argument("--collection", help="collection CSV/snapshot (for exact printings and --missing)")
    ap.add_argument("--cards", action="append", default=[],
                    help="a single card name (repeatable)")
    ap.add_argument("--list", dest="list_file",
                    help="file of '<qty> <name>' lines to proxy")
    ap.add_argument("--missing", action="store_true",
                    help="deck mode: only copies the collection does NOT cover")
    ap.add_argument("--buylist", action="store_true",
                    help="deck mode: proxy the deck's .buylist.csv instead — "
                         "playtest the upgrades before buying them")
    ap.add_argument("--size", default="large",
                    choices=sorted(card_image.SIZES),
                    help="Scryfall image size (large ≈ 271dpi at 63mm; png ≈ 300dpi)")
    ap.add_argument("--title", help="page title override")
    ap.add_argument("--out", help="write HTML here (default: stdout)")
    a = ap.parse_args()
    if not a.deck and not a.cards and not a.list_file:
        ap.error("nothing to proxy: pass --deck, --cards or --list")
    if a.missing and not (a.deck and a.collection):
        ap.error("--missing needs --deck and --collection")

    cells, title = build(deck=a.deck, collection=a.collection, cards=a.cards,
                         list_file=a.list_file, missing=a.missing,
                         buylist=a.buylist, size=a.size, title=a.title)
    page = generate_html(cells, title=title, size=a.size)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(page)
        pages = (len(cells) + CELLS_PER_SHEET - 1) // CELLS_PER_SHEET
        print(f"{a.out}: {len(cells)} proxies on {pages} sheet(s). "
              f"Print at 100% scale from a browser with internet.")
    else:
        sys.stdout.write(page)


if __name__ == "__main__":
    main()
