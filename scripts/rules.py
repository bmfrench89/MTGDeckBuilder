#!/usr/bin/env python3
"""Magic's Comprehensive Rules, on tap — ask the CR instead of recalling it.

The skill already *instructs* answering rules questions "from the Comprehensive
Rules — never from memory" (`references/coaching.md`). This is the tool behind
that instruction: it downloads WotC's official CR text file once, caches it,
parses it into rules / sections / chapters / glossary, and answers three kinds of
question — look a rule up by number, search the text, or define a glossary term.

The point is NOT the ranking. The point is that a cited rule number comes from
retrieved text. Search is a shortlist; read the rule before you cite it.

Design decisions worth knowing before you edit:

- **The CR is never committed.** It is ~1 MB of copyrighted WotC text that revs
  5-6× a year; committing it would be redistribution plus a recurring megabyte
  diff. It lives in `data/cache/rules/`, which is gitignored like every other
  cache.
- **Manual refresh only.** `--refresh` re-downloads. Otherwise any cached copy is
  used and honestly labeled `fetched <date>` from its mtime. No TTL, no
  `meta.json`, no surprise 60-second fetch in the middle of a query.
- **Zero repo imports** — a first for the engine ring. Every other engine imports
  `mtglib`; rule text has no card names in it, so there is nothing to normalize.
- **Nothing here raises.** Every failure path returns the standard `{'error': …}`
  payload carrying the manual-download instructions, exactly like `edhrec.py`
  and `spellbook.py`, so a caller prints a note instead of crashing.

Reachability: the player's PC reaches magic.wizards.com; the hosted server and
CI/sandboxes do not (see the network matrix in `docs/codemap.md`). That is why
this is a player's-PC feature and why there is no `/api/rules` route.

Usage:
  python3 rules.py 903.1                      # look up a rule (children included)
  python3 rules.py "commander tax"            # glossary, else full-text search
  python3 rules.py --search "deathtouch trample" --limit 5
  python3 rules.py --gloss "Deathtouch"
  python3 rules.py 601.2a --json
  python3 rules.py --refresh                  # re-download, then report the parse
  python3 rules.py 903.1 --file MagicCompRules.txt   # a copy you downloaded yourself
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

LANDING = "https://magic.wizards.com/en/rules"
CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "cache",
                 "rules"))
CACHE_FILE = "MagicCompRules.txt"
_HEADERS = {"User-Agent": "MTGDeckBuilder/1.0 (personal collection tool)",
            "Accept": "text/html,text/plain,*/*"}

# Printed on every degraded path. A blocked network is not a dead end — the player
# can download the file by hand and point --file at it.
MANUAL_NOTE = (
    "Download the Comprehensive Rules txt from " + LANDING +
    " and pass it with --file <path> (or drop it at " +
    os.path.join("data", "cache", "rules", CACHE_FILE) + ").")

# The official file's structure. Rules are one per line: "100.1. text" or "100.1a text".
_RE_RULE = re.compile(r"^(\d{3})\.(\d+)([a-z])?\.?(?:\s|$)")
_RE_SECTION = re.compile(r"^(\d{3})\.\s+(.*)$")
_RE_CHAPTER = re.compile(r"^([1-9])\.\s+(.*)$")
_RE_EFFECTIVE = re.compile(r"effective as of\s+(.+?)\.\s*$", re.I)
_RE_TXT_URL = re.compile(r"https?://[^\"'\s]*MagicComp[Rr]ules[^\"'\s]*\.txt")
# "See rule 702.2" / "see rules 601.2a and 601.2b" inside a glossary definition.
_RE_SEE_RULE = re.compile(r"\brules?\s+(\d{3}(?:\.\d+[a-z]?)?)", re.I)

# Parsed CRs, keyed by (abspath, mtime). Repeated queries in one process (the CLI
# runs several, the skill more) parse the ~1 MB file exactly once.
_MEMO = {}


# ── fetch / cache / load ─────────────────────────────────────────────────────

def _error(msg):
    """The standard degraded payload: an error string plus empty containers, so
    every query function below can run against it without a guard."""
    return {"error": msg + " " + MANUAL_NOTE, "effective": "", "chapters": {},
            "sections": {}, "rules": {}, "children": {}, "glossary": {},
            "source": "", "fetched": ""}


def _decode(raw):
    """WotC has shipped the CR as UTF-8-with-BOM and as Windows-1252 over the years.
    Try both, then fall back to lossy UTF-8 — a mangled em-dash beats no rules."""
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _find_txt_url(html):
    """The .txt link on the rules landing page (the filename carries a date, so it
    can't be hardcoded). Returns None if the page layout changed — the caller then
    degrades to the manual-download note rather than guessing a URL."""
    m = _RE_TXT_URL.search(html or "")
    return m.group(0) if m else None


def cache_path(cache_dir=None):
    return os.path.join(cache_dir or CACHE_DIR, CACHE_FILE)


def fetch_cr(cache_dir=None, url=None, timeout=60):
    """Download the CR text file into the cache and return its path.

    Writes to `<file>.part` and `os.replace`s it into position (the `carddb.py`
    idiom), so an interrupted download can never leave a truncated file that
    parses to half the rules. Raises on failure; `load_cr` is what catches."""
    cache_dir = cache_dir or CACHE_DIR
    if not url:
        req = urllib.request.Request(LANDING, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            url = _find_txt_url(_decode(r.read()))
        if not url:
            raise ValueError("no MagicCompRules .txt link found on " + LANDING)
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    os.makedirs(cache_dir, exist_ok=True)
    dest = cache_path(cache_dir)
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, dest)
    return dest


def load_cr(path=None, cache_dir=None, fetch=True, url=None, refresh=False):
    """The parsed Comprehensive Rules, or an error payload. Never raises.

    Precedence:
      1. an explicit `path` (`--file`) — used as-is, never refreshed;
      2. the cached copy, labeled `fetched <date>` from its mtime;
      3. one live fetch (first run ever, or `refresh=True`);
      4. the error payload with the manual-download note.

    There is deliberately no TTL: a rules file six months old still answers 903.1
    correctly, and a silent 60-second download in the middle of a question is a
    worse failure than a slightly stale rule. `--refresh` is the whole refresh
    policy."""
    cache_dir = cache_dir or CACHE_DIR
    target = os.path.abspath(path) if path else cache_path(cache_dir)

    if path and not os.path.exists(target):
        return _error("no such rules file: %s." % target)

    if not path and (refresh or not os.path.exists(target)):
        try:
            target = os.path.abspath(fetch_cr(cache_dir, url))
        except Exception as e:                     # network, 404, layout change
            if not os.path.exists(target):
                return _error("could not download the Comprehensive Rules (%s)." % e)
            # A refresh that failed still has yesterday's file — use it, labeled.

    try:
        mtime = os.path.getmtime(target)
    except OSError as e:
        return _error("could not read %s (%s)." % (target, e))

    key = (target, mtime)
    if key in _MEMO:
        return _MEMO[key]

    try:
        with open(target, "rb") as f:
            text = _decode(f.read())
    except OSError as e:
        return _error("could not read %s (%s)." % (target, e))

    cr = parse_cr(text)
    cr["source"] = target
    cr["fetched"] = "fetched " + time.strftime("%Y-%m-%d", time.localtime(mtime))
    _MEMO[key] = cr
    return cr


# ── parser ───────────────────────────────────────────────────────────────────

def _slice_body(lines):
    """(body_start, body_end, gloss_start, gloss_end) over the official layout.

    The file repeats its own headings: the Contents listing near the top names every
    chapter and section AND ends with the words "Glossary" and "Credits". Slicing on
    the FIRST "Glossary" therefore cuts the body away entirely and yields zero rules.
    So: the Contents listing is closed by the first "Credits"; the body runs to the
    LAST "Glossary"; the glossary runs to the LAST "Credits"."""
    first_credits = last_gloss = last_credits = -1
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s == "Credits":
            if first_credits < 0:
                first_credits = i
            last_credits = i
        elif s == "Glossary":
            last_gloss = i
    body_start = first_credits + 1 if first_credits >= 0 else 0
    body_end = last_gloss if last_gloss > body_start else len(lines)
    gloss_start = last_gloss + 1 if last_gloss > body_start else len(lines)
    gloss_end = last_credits if last_credits > gloss_start else len(lines)
    return body_start, body_end, gloss_start, gloss_end


def _parse_glossary(lines):
    """Blank-line-separated blocks: first line is the term, the rest is the
    definition. Later duplicates lose to the first (the file doesn't have any, but
    first-writer-wins is the repo's convention for curated-beats-derived)."""
    gloss, block = {}, []
    for ln in list(lines) + [""]:
        if ln.strip():
            block.append(ln.strip())
            continue
        if block:
            term = block[0]
            if term not in gloss:
                gloss[term] = " ".join(block[1:]).strip()
        block = []
    return gloss


def parse_cr(text):
    """Parse the official CR text file into
    `{'effective', 'chapters', 'sections', 'rules', 'children', 'glossary'}`.

    Everything is kept in **document order** (dicts preserve insertion order), which
    is what lets `search` break score ties by "earlier = more fundamental".

    `children` maps both levels: section '601' → its rules, rule '601.2' → its
    lettered subrules. `Example:` lines and any other unrecognized non-blank line
    attach to the rule currently open — a format change degrades to a concatenated
    rule, never a crash. A parse that finds no rules at all sets an explicit error
    instead of returning a convincingly empty result."""
    lines = (text or "").splitlines()
    effective = ""
    for ln in lines[:60]:
        m = _RE_EFFECTIVE.search(ln.strip())
        if m:
            effective = m.group(1).strip()
            break

    b0, b1, g0, g1 = _slice_body(lines)
    chapters, sections, rules, children = {}, {}, {}, {}
    current = None

    for ln in lines[b0:b1]:
        s = ln.rstrip()
        if not s.strip():
            continue
        m = _RE_RULE.match(s)
        if m:
            sec, num, letter = m.group(1), m.group(2), m.group(3) or ""
            ref = "%s.%s%s" % (sec, num, letter)
            body = s[m.end():].strip()
            rules[ref] = body
            parent = "%s.%s" % (sec, num) if letter else sec
            children.setdefault(parent, [])
            if ref not in children[parent]:
                children[parent].append(ref)
            current = ref
            continue
        m = _RE_SECTION.match(s)
        if m:
            sections[m.group(1)] = m.group(2).strip()
            children.setdefault(m.group(1), [])
            current = None
            continue
        m = _RE_CHAPTER.match(s)
        if m:
            chapters[m.group(1)] = m.group(2).strip()
            current = None
            continue
        if current:                        # Example: … and wrapped continuations
            rules[current] = (rules[current] + "\n" + s.strip()).strip()

    cr = {"effective": effective, "chapters": chapters, "sections": sections,
          "rules": rules, "children": children,
          "glossary": _parse_glossary(lines[g0:g1]),
          "source": "", "fetched": "", "error": None}
    if not rules:
        cr["error"] = ("parsed 0 rules — this file does not look like the "
                       "Comprehensive Rules text export. " + MANUAL_NOTE)
    return cr


# ── query surface ────────────────────────────────────────────────────────────

def normalize_ref(ref):
    """'601.2A.' / 'rule 601.2A' / ' 601.2a ' → '601.2a'. Lowercases the subrule
    letter and drops the trailing period the CR prints on whole-number rules."""
    r = str(ref or "").strip().lower()
    r = re.sub(r"^rules?\s+", "", r)
    return r.rstrip(".").strip()


def is_ref(text):
    """Does this look like a rule reference rather than a phrase? Drives the CLI's
    positional auto-detect ('903.1' → lookup, 'commander tax' → glossary/search)."""
    r = normalize_ref(text)
    return bool(re.fullmatch(r"\d{3}(\.\d+[a-z]?)?", r) or re.fullmatch(r"[1-9]", r))


def lookup(cr, ref):
    """A rule, a section, or a chapter, with its context. `None` on a miss.

    An error payload passes straight through — the caller sees the degrade note
    rather than an indistinguishable "no such rule"."""
    if cr.get("error"):
        return {"error": cr["error"]}
    r = normalize_ref(ref)
    if r in cr["rules"]:
        sec = r.split(".")[0]
        kids = [(k, cr["rules"].get(k, "")) for k in cr["children"].get(r, [])]
        return {"kind": "rule", "ref": r, "text": cr["rules"][r], "children": kids,
                "section": sec, "section_title": cr["sections"].get(sec, ""),
                "chapter": sec[0], "chapter_title": cr["chapters"].get(sec[0], "")}
    if r in cr["sections"]:
        return {"kind": "section", "ref": r, "title": cr["sections"][r],
                "rule_numbers": list(cr["children"].get(r, [])),
                "chapter": r[0], "chapter_title": cr["chapters"].get(r[0], "")}
    if r in cr["chapters"]:
        return {"kind": "chapter", "ref": r, "title": cr["chapters"][r],
                "section_numbers": [s for s in cr["sections"] if s[0] == r]}
    return None


def _terms(query):
    """Distinct query words, in order. Each becomes a **word-start** pattern: `\\bgame`
    matches "games" (bag-of-words with no stemmer needs the recall) but `\\bon` does
    not match "propose" (plain substring matching scored that as a hit)."""
    words = dict.fromkeys(re.findall(r"[a-z0-9']+", (query or "").lower()))
    return [(w, re.compile(r"\b" + re.escape(w))) for w in words if w]


def search(cr, query, limit=8):
    """Bag-of-words search over the rule text. Returns
    `[{'ref', 'score', 'snippet', 'text'}]`, best first.

    Scoring, deliberately simple: **+2** per distinct query term present, **+5** if
    every term is present, **+10** if the exact phrase appears. Ties break by
    document order, so the more fundamental rule wins. Snippet is ±120 characters
    around the first hit.

    This is a shortlist, not an answer. The retrieved rule text is the answer —
    read it before citing it. An error payload yields `[]`; nothing raises."""
    if cr.get("error"):
        return []
    terms = _terms(query)
    phrase = re.sub(r"\s+", " ", (query or "").strip().lower())
    if not terms:
        return []
    hits = []
    for order, (ref, text) in enumerate(cr["rules"].items()):
        hay = (ref + " " + text).lower()
        found = [m.start() for _w, pat in terms for m in [pat.search(hay)] if m]
        if not found:
            continue
        score = 2 * len(found)
        if len(found) == len(terms):
            score += 5
        if phrase and len(phrase) > 2 and phrase in hay:
            score += 10
        at = max(0, min(found) - len(ref) - 1)
        lo, hi = max(0, at - 120), min(len(text), at + 120)
        snippet = ("…" if lo else "") + text[lo:hi].strip() + ("…" if hi < len(text) else "")
        hits.append({"ref": ref, "score": score, "snippet": snippet, "text": text,
                     "_order": order})
    hits.sort(key=lambda h: (-h["score"], h["_order"]))
    for h in hits:
        h.pop("_order", None)
    return hits[:limit]


def glossary_lookup(cr, term):
    """A glossary entry: exact match (case-insensitive), then prefix, then
    substring. Returns `{'term', 'definition', 'see_rules'}` or None; `see_rules`
    are the rule numbers the definition itself points at, so the caller can go read
    the real rule instead of stopping at the gloss."""
    if cr.get("error"):
        return None
    q = re.sub(r"\s+", " ", (term or "").strip().lower())
    if not q:
        return None
    gloss = cr["glossary"]
    hit = None
    for k in gloss:
        if k.lower() == q:
            hit = k
            break
    if hit is None:
        for k in gloss:
            if k.lower().startswith(q):
                hit = k
                break
    if hit is None:
        for k in gloss:
            if q in k.lower():
                hit = k
                break
    if hit is None:
        return None
    definition = gloss[hit]
    seen = list(dict.fromkeys(_RE_SEE_RULE.findall(definition)))
    return {"term": hit, "definition": definition, "see_rules": seen}


# ── CLI ──────────────────────────────────────────────────────────────────────

def _print_rule(hit, out):
    if hit["kind"] == "rule":
        ctx = " · ".join(x for x in ["%s. %s" % (hit["chapter"], hit["chapter_title"])
                                     if hit["chapter_title"] else "",
                                     "%s. %s" % (hit["section"], hit["section_title"])
                                     if hit["section_title"] else ""] if x)
        if ctx:
            out(ctx)
        # Example: lines live inside the rule text — indent them so a subrule's
        # example doesn't read as a new top-level paragraph.
        out("%s %s" % (hit["ref"], hit["text"].replace("\n", "\n    ")))
        for num, text in hit["children"]:
            out("  %s %s" % (num, text.replace("\n", "\n      ")))
    elif hit["kind"] == "section":
        out("%s. %s" % (hit["ref"], hit["title"]))
        if hit["chapter_title"]:
            out("  in chapter %s. %s" % (hit["chapter"], hit["chapter_title"]))
        out("  rules: " + (", ".join(hit["rule_numbers"]) or "(none)"))
    else:
        out("%s. %s" % (hit["ref"], hit["title"]))
        out("  sections: " + (", ".join(hit["section_numbers"]) or "(none)"))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Look up Magic's Comprehensive Rules: a rule by number, a "
                    "full-text search, or a glossary term. Downloads the official "
                    "text file once into data/cache/rules/ (never committed) and "
                    "re-downloads only with --refresh.")
    ap.add_argument("query", nargs="*",
                    help="a rule reference (903.1, 601.2a) → look it up; anything "
                         "else → glossary, then full-text search.")
    ap.add_argument("--search", action="store_true", help="force full-text search.")
    ap.add_argument("--gloss", action="store_true", help="force a glossary lookup.")
    ap.add_argument("--json", action="store_true", help="machine-readable output.")
    ap.add_argument("--file", help="use this Comprehensive Rules txt (no download).")
    ap.add_argument("--url", help="download from this .txt URL instead of scraping "
                                  "the rules landing page.")
    ap.add_argument("--refresh", action="store_true", help="re-download the CR first.")
    ap.add_argument("--limit", type=int, default=8, help="search results (default 8).")
    args = ap.parse_args(argv)

    # The CR is full of em-dashes and curly quotes and the player's machine is
    # Windows, whose console is often cp1252. Never let an encode error eat an answer.
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    query = " ".join(args.query).strip()
    if not query and not args.refresh:
        print("error: give a rule reference, a glossary term, or a search phrase "
              "(or --refresh to just re-download).", file=sys.stderr)
        return 2
    if args.search and args.gloss:
        print("error: --search and --gloss are exclusive.", file=sys.stderr)
        return 2

    cr = load_cr(path=args.file, url=args.url, refresh=args.refresh)
    if cr.get("error"):
        if args.json:
            print(json.dumps({"error": cr["error"]}, indent=2))
        print(cr["error"], file=sys.stderr)
        return 1

    label = "%s rules · %s%s" % (len(cr["rules"]),
                                 ("effective " + cr["effective"] + " · ") if cr["effective"] else "",
                                 cr["fetched"])
    if not query:                              # --refresh with nothing to ask
        if args.json:
            print(json.dumps({"rules": len(cr["rules"]), "glossary": len(cr["glossary"]),
                              "effective": cr["effective"], "fetched": cr["fetched"],
                              "source": cr["source"]}, indent=2))
        else:
            print(label)
            print("glossary entries: %s" % len(cr["glossary"]))
            print("source: %s" % cr["source"])
        return 0

    if args.gloss:
        result, kind = glossary_lookup(cr, query), "glossary"
    elif args.search:
        result, kind = search(cr, query, args.limit), "search"
    elif is_ref(query):
        result, kind = lookup(cr, query), "rule"
    else:
        result = glossary_lookup(cr, query)
        kind = "glossary"
        if not result:
            result, kind = search(cr, query, args.limit), "search"

    if args.json:
        print(json.dumps({"query": query, "kind": kind, "result": result,
                          "effective": cr["effective"], "fetched": cr["fetched"]},
                         indent=2))
        return 0 if result else 1

    if not result:
        print("no match for %r in %s." % (query, label), file=sys.stderr)
        return 1

    print(label)
    print("")
    if kind == "rule":
        _print_rule(result, print)
    elif kind == "glossary":
        print(result["term"])
        print("  " + result["definition"])
        if result["see_rules"]:
            print("  see: " + ", ".join(result["see_rules"]) +
                  "   (read the rule — the glossary is a summary)")
    else:
        for h in result:
            print("%s  [%s]" % (h["ref"], h["score"]))
            print("  " + h["snippet"])
        print("")
        print("These are candidates, not an answer — look the winner up by number "
              "and read it before citing it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
