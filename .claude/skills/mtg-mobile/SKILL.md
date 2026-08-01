---
name: mtg-mobile
description: >-
  Launch the MTG Deckbuilder web app so a phone or tablet can use it, install it to
  the home screen, and fix the usual connection problems. Use when the user wants to
  run the deckbuilder on their phone, view decks on mobile, install it as an app, get
  an APK, share it with someone on their network, or when the phone says it can't
  reach the server. Triggers on: "on my phone", "mobile", "android", "iphone", "APK",
  "install the app", "add to home screen", "can't connect from my phone", "LAN",
  "tunnel", "PWA".
---

# Running the deckbuilder on a phone

The app is a Flask server on the player's PC. A phone reaches it over the local
network and installs it as a **PWA** — a home-screen icon that opens full-screen.
Full reference: `docs/mobile.md`.

## The one thing that goes wrong

`python webapp/app.py` binds to **localhost only**, so the phone cannot connect. The
launchers set `MTG_HOST=0.0.0.0`, which is what allows other devices in:

```bash
webapp\run.bat        # Windows
./webapp/run.sh       # macOS / Linux
```

If the user is stuck, check that **first** — before anything about Wi-Fi or firewalls.

## Walking them through it

1. Start the server with a launcher (above). It prints
   `on your phone : http://192.168.x.x:5000`.
2. Point them at the **Mobile tab** in the app (`/mobile`) — it shows the same address
   with a copy button plus the install steps, so they don't have to read the terminal.
3. Phone, same Wi-Fi, open that address.
4. Install: **Android/Chrome** ⋮ → *Add to Home screen* → *Install*.
   **iPhone** must use **Safari** → Share → *Add to Home Screen* (Chrome on iOS cannot
   install web apps — a common dead end).

## Diagnosing "it won't connect"

Work down this list; the cause is almost always #1 or #2.

1. **Server bound to localhost** — did they use `run.bat` / `run.sh`? Check the startup
   output actually shows an `on your phone` line. No line = no LAN binding.
2. **Different networks** — phone on cellular, or on a guest/5GHz-isolated SSID. Many
   routers block client-to-client traffic on guest networks.
3. **Windows Firewall** prompting on first run and being dismissed. Re-run and allow
   Python on *private* networks.
4. **PC asleep.** The app reads the collection live from that machine; if it sleeps, the
   phone gets the offline page.
5. **Wrong IP** — `lan_ip()` picks the interface with a default route, which can be a VPN
   or a virtual adapter. Have them compare against `ipconfig` / `ip addr`.

## What it can and can't do offline

`webapp/static/sw.js` caches **only the static shell** (CSS/JS/icons). Deck and
collection pages always hit the network and are never served stale — decks change on
every optimize, so a cached list would show the wrong 100 cards. Offline the user gets
an explicit "can't reach the deckbuilder" page. Card images always work: they come from
Scryfall's CDN, not the PC.

**Do not add offline caching of deck/collection pages.** It looks like a feature and is
actively harmful here.

## If they ask for an APK

Say plainly that there isn't a useful one, and why (detail in `docs/mobile.md`):

- A **WebView wrapper** (Capacitor/Cordova) builds a real `.apk`, but it's a browser
  pointed at the same LAN address — identical to the installed PWA, plus a build system.
- A **TWA** (the sanctioned PWA→APK path) needs **HTTPS on a public domain** with Digital
  Asset Links. A LAN HTTP address can't satisfy it, and hosting publicly would expose the
  collection and purchase prices.
- **Python on Android** is genuinely standalone but means porting Flask and `scripts/`
  onto the phone — and then it can't reach the data on the PC.

The PWA already gives the home-screen icon and full-screen launch. Offer to build a
wrapper only if the user insists after hearing that, and be clear it's a bookmark.

## Away from home

```bash
cloudflared tunnel --url http://localhost:5000
```

Gives a temporary public HTTPS URL. **Warn every time**: it exposes the collection and
purchase prices to anyone with the link. Short-lived only.

## Icons

PNGs are generated from `icon.svg`'s geometry by a dependency-free rasteriser (Android
wants PNG; SVG-only manifests often fall back to a generic globe):

```bash
python3 scripts/make_icons.py
```
