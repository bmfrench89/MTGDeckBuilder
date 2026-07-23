# Card Images — how retrieval works (and how not to break it)

Card-image loading has broken **the same way several times** (the deck dashboard,
the auto-build view, the collection grid). The cause is always the same, and so is
the fix. Read this before touching any code that shows card images.

## The one rule

> **Showing MANY card images? Resolve them in BATCHES via `POST /cards/collection`
> (→ CDN URLs). Never fire N per-card requests at `/cards/named`.**

The Scryfall **image CDN is not rate-limited**; the Scryfall **API card endpoints
are** (~2 requests/sec). Firing ~100 `<img>` loads at the by-name endpoint gets the
later ones **429'd**, so they show blank / the `alt` text (the card name) instead of
the picture. That is the bug, every time.

## The two image sources

| Source | URL shape | Rate-limited? | Needs |
|---|---|---|---|
| **CDN** (what you want in bulk) | `https://cards.scryfall.io/<size>/<face>/<a>/<b>/<id>.jpg` | **No** | the card's Scryfall **id**, or an `image_uris` object from a card |
| **API by-name** (fine for ONE) | `https://api.scryfall.com/cards/named?fuzzy=<name>&format=image` | **Yes (~2/s)** | just the card **name** |

`scripts/card_image.py` builds both: `image_url(sid, size)` (CDN) and
`image_url_by_name(name, size)` (API). CDN needs an id; by-name needs only a name
but is the rate-limited path.

## Why the batch endpoint is the answer

`POST https://api.scryfall.com/cards/collection` takes **up to 75 identifiers** per
request and returns full card objects (each with `image_uris`). Identifiers can be
`{name}`, `{id}`, or `{set, collector_number}`. So a **100-card page = ~2 requests**
that return CDN image URLs for everything — instead of 100 hits on the 2/s endpoint.
It works **with or without enrichment** (it resolves names → CDN), so images no
longer depend on the collection having Scryfall ids.

Minimal shape (see the real implementations below):
```js
// read the card NAME from each <img alt> (or a data-* attr), then:
fetch('https://api.scryfall.com/cards/collection', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ identifiers: names.slice(0,75).map(n => ({ name: n })) })
})
  .then(r => r.json())
  .then(j => j.data.forEach(card => {
    const iu = card.image_uris || (card.card_faces && card.card_faces[0].image_uris);
    if (iu) setImgSrc(card.name, iu.normal);          // CDN — not rate-limited
  }));
// anything in j.not_found → fall back to its by-name URL (one request each, throttled)
```

## Where each pattern lives (keep these consistent)

| File | What it does |
|---|---|
| `webapp/static/cardgrid.js` | Batch resolver for the **auto-build view** (`build_deck.html`). |
| `webapp/static/collection.js` | Batch resolver **+ IntersectionObserver** (lazy) for the **Collection grid** (~1,800 cards — only load what scrolls into view). |
| `scripts/build_dashboard.py` → `IMG_LOADER` | Batch resolver for the **deck dashboard + visual gallery** (self-contained HTML; the script is inlined). |
| `scripts/card_image.py` | The URL builders (`image_url` = CDN, `image_url_by_name` = API). |
| `webapp/static/cardpanel.js` | The card **panel** opens ONE card → a single `/cards/named` fetch is fine; it also uses the returned `image_uris` for the CDN image. |

All of these read the card **name** off `<img alt>` (or `data-card`) and batch-resolve.

## Rules for adding a NEW image display

1. **Many images → batch resolver.** Copy `cardgrid.js`. Do **not** write `<img src="…/cards/named…">` × N, and do not loop per-card `fetch`es.
2. **One image (a modal/panel) → a single by-name fetch is fine.** No batching needed.
3. **Every `<img>` must carry the exact card NAME** (`alt="Sol Ring"` or `data-card`) so a batch resolver can find it and map the response back.
4. **Big grid → `loading="lazy"`**, and for very large grids (the collection) gate loading with an **IntersectionObserver** so off-screen cards don't fetch.
5. Prefer setting `img.src` to the **CDN** URL (`image_uris.normal`), never leave it pointed at the by-name endpoint in bulk.

## Gotchas

- **Adventure / double-faced names.** A deck lists the front-face name ("Murderous
  Rider") but Scryfall's exact name is "Murderous Rider // Swift End", so
  `/cards/collection {name}` misses it → it falls back to the fuzzy by-name path.
  That's fine (one request); just don't be surprised by a 1-card fallback.
- **Server-side is firewalled.** Scryfall is **blocked from the Python build/sandbox
  env** (403 at the proxy), but reachable from the **user's browser**. So image
  loading is **always client-side JS** — never fetch images server-side in the scripts.
- **Chat/preview pane won't render external images.** Card galleries only display in
  a real browser (Chrome/Edge/Safari). Self-contained dashboards render anywhere; the
  images inside them still need a real browser.
- **Headless test viewport (0×0).** With `loading="lazy"`, nothing paints in a 0×0
  browser, so `naturalWidth` reads 0 even when everything is wired correctly. To
  verify, check that `img.src` got set to a `cards.scryfall.io` URL, or eager-load one
  probe image and check its `naturalWidth`.

## History (why this doc exists)

Same bug, three times — each fixed by moving to the batch resolver:
- Dashboard decklist images 429'd and dropped out → hardened loader, then **batch** (PR #27).
- Auto-build "Build this deck" view → batch resolver from the start (`cardgrid.js`).
- Collection grid (~1,800 cards) → batch + IntersectionObserver (`collection.js`).

If you're about to add another card-image surface: use the batch resolver. See also
[codemap.md](codemap.md) and the skill's `references/tooling-and-data.md`.
