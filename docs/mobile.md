# Running the deckbuilder on your phone

The app installs to your home screen and opens full-screen. There is no APK to sideload —
**the installed web app is the app**, and the reasons why are at the bottom.

## Hosted deploy (if one exists)

If the app is hosted (see `docs/plan-pythonanywhere-deploy.md`), skip the LAN setup
entirely: open the hosted URL on the phone and install it from there (step 4 below).
The PC never needs to be on. Everything below covers the **local/LAN mode**, which
still works for offline development.

## Quick start (local/LAN mode)

1. **On the PC**, start the server so your network can reach it:

   ```bash
   webapp\run.bat
   ```

   (`run.bat` / `run.sh` set `MTG_HOST=0.0.0.0`, which is what lets other devices in.
   Running `python webapp/app.py` on its own binds to localhost only, and your phone
   will not be able to connect.)

2. It prints the address, e.g. `on your phone : http://192.168.1.42:5000`. The same
   address is on the **Mobile** tab in the app, with a copy button.

3. **On the phone**, open that address in the browser — same Wi-Fi as the PC.

4. **Install it:**
   - **Android / Chrome** — ⋮ → *Add to Home screen* → *Install*
   - **iPhone / Safari** — Share → *Add to Home Screen* (must be Safari; Chrome on iOS
     can't install web apps)

Long-press the installed icon for shortcuts straight to Collection, Build Next and Wishlist.

## What works away from the PC (local/LAN mode)

| | Works? |
|---|---|
| Dashboards, card panel, optimize, edit, collection | ✅ while the PC is on and serving |
| Card images | ✅ always — they come from Scryfall's CDN, not your PC |
| PC asleep / different network | ❌ shows a "can't reach the deckbuilder" page |

(On a hosted deploy none of this applies — the server is always on.)

The service worker (`webapp/static/sw.js`) caches only the **static shell** (CSS, JS,
icons). Deck and collection pages are always fetched live and are **never** served from
cache: your decks change every time you optimize, and a cached copy would confidently show
you the wrong 100 cards. An honest error beats stale data.

## Reaching it from outside your home

A tunnel gives you a temporary public HTTPS URL:

```bash
cloudflared tunnel --url http://localhost:5000
```

⚠️ That exposes your collection **and your purchase prices** to anyone with the link.
Keep it short-lived, and don't leave it running.

## Why there's no APK

Three ways to make an installable Android package, and none of them beat the PWA:

1. **WebView wrapper (Capacitor/Cordova).** Produces a real `.apk`, but it's a browser
   pointed at `http://192.168.x.x:5000`. The PC still has to be on and on the same Wi-Fi —
   functionally identical to the installed PWA, plus a build toolchain in the repo.
2. **TWA via Bubblewrap** (the sanctioned way to ship a PWA as an APK) requires **HTTPS on
   a public domain** with Digital Asset Links verification. A LAN HTTP address can't satisfy
   it, so you'd have to host the app — and your collection — publicly first.
3. **Python on Android (Chaquopy/BeeWare).** Genuinely standalone, but it means porting
   Flask and the whole `scripts/` toolkit onto the phone and keeping the collection CSV
   there — at which point it can't see the data on your PC anyway.

The PWA gives you the same home-screen icon and full-screen launch as option 1, with none
of the cost. With a hosted HTTPS deploy, option 2 (TWA) becomes technically possible —
but the installed PWA already delivers the same UX, so it remains an explicit non-goal.

## Regenerating the icons

`webapp/static/icon-192.png` and `icon-512.png` are generated from the same geometry as
`icon.svg` by a dependency-free rasteriser (Android launchers want PNG; an SVG-only
manifest often falls back to a generic globe):

```bash
python3 scripts/make_icons.py
```

Re-run it after editing `icon.svg`.
