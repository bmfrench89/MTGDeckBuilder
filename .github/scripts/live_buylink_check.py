"""Verify card_image.purchase_links' ManaPool and Card Kingdom URL schemes
against the live sites — the Phase 0 leftover the tracker parked as "best-effort
links shipped; verify on the live sites" (spec-interactive-analytics-ai.md).

Run from the repo root on a GitHub Actions runner (open egress). Per link:
  2xx/3xx  -> the scheme works (PASS)
  404      -> the scheme is WRONG (FAIL — the one-line fix lives in
              card_image.purchase_links)
  403/429/5xx or network error -> bot wall / rate limit (INCONCLUSIVE — retail
              sites often challenge datacenter IPs; not evidence either way, so
              it never fails the run, it just says so)

Two probe cards: a plain name and an apostrophe name, because the ManaPool slug
is the only generated path (apostrophes are stripped, spaces become dashes) —
if the slug rule is wrong, the apostrophe card is where it shows.
"""
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "scripts")
import card_image  # noqa: E402

# A browser-shaped UA: retail storefronts reject obvious scripts outright,
# which would turn every verdict into INCONCLUSIVE and tell us nothing.
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/126.0 Safari/537.36"),
      "Accept": "text/html,application/xhtml+xml"}

PROBES = ["Sol Ring", "Urza's Saga"]
CHECK = ("manapool", "cardkingdom")   # tcgplayer was verified in Phase 0 (#23)


def status_of(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return f"error: {e}"


def main():
    failures = 0
    inconclusive = 0
    for name in PROBES:
        links = card_image.purchase_links(name)
        for site in CHECK:
            url = links[site]
            code = status_of(url)
            if isinstance(code, int) and 200 <= code < 400:
                verdict = "PASS"
            elif code == 404:
                verdict = "FAIL (scheme wrong — fix card_image.purchase_links)"
                failures += 1
            else:
                verdict = f"INCONCLUSIVE (bot wall / {code})"
                inconclusive += 1
            print(f"{verdict:12s} {site:12s} {name:15s} {code}  {url}")

    print(f"\n{failures} failed, {inconclusive} inconclusive "
          f"(inconclusive never fails the run — a challenge page is not a 404)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
