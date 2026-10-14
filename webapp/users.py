"""Named members beside the owner — docs/spec-second-login.md.

The owner keeps signing in with MTG_PASSWORD (nothing to migrate). A MEMBER signs in
with a name and their own password and gets the owner's powers minus the People page
(and, unless the owner allows it, replacing the whole collection). Every edit a member
or the owner makes is labelled with who made it, once this file exists.

The store is `data/private/users.json`: on the server, mode 0600, gitignored, and never
in `sync_server.sh`'s explicit path list. Passwords are Werkzeug scrypt hashes — the web
app already has Werkzeug through Flask, so scripts/ stays stdlib-only.

    {"owner": {"display": "Ben"},
     "members_can_upload": false,
     "members": {"sam": {"name": "sam", "display": "Sam", "role": "member",
                         "hash": "scrypt:…", "ver": 1, "disabled": false}}}

With no file, the app is exactly the single-password app it was: no names, no `By`
labels, no activity log. That back-compat is a spec requirement, not an accident.

**Once the app runs on its collection database** (docs/spec-target-architecture.md
Phase 1b, 2026-10-14) the same store lives there instead: `store.people_load` /
`people_save` hold the very dict below, and the first read takes users.json in once
and renames it `users.json.moved-to-db`. The app says where through `database`;
everything else in this module is the same code on either side.
"""
import json
import os
import re
import tempfile
import threading
import time

from werkzeug.security import check_password_hash, generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "private", "users.json")

# The app sets this to a function returning its collection database's path while it
# runs on one, else None. Asked on every call, so it follows the app's own switch.
database = None

LOCK_FAILS = 10                  # failures per name …
LOCK_WINDOW = 15 * 60            # … within this many seconds locks that name out
_fails = {}                      # name key -> [timestamps]; in memory, one worker
_lock = threading.Lock()

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9 _.-]{0,31}$")
OWNER_KEY = "owner"


def key_of(name):
    """The lookup key for a sign-in name: trimmed, case-folded, inner spaces kept."""
    return re.sub(r"\s+", " ", (name or "").strip()).casefold()


def valid_name(name):
    k = key_of(name)
    return bool(_NAME_RE.match(k)) and k != OWNER_KEY


def _db():
    return database() if database else None


def exists():
    if _db():
        return load() is not None
    return os.path.exists(PATH)


def load():
    """The store, or None when there is none (single-password mode)."""
    db = _db()
    if db:
        import store                       # scripts/ is on the path wherever the app runs
        return store.people_load(db, import_from=PATH)
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("owner", {})
    data.setdefault("members", {})
    data.setdefault("members_can_upload", False)
    return data


def save(data):
    """Atomic, owner-only (0600) write; creates data/private/ on first use. In
    database mode: one transaction in the database, which is kept 0600 too."""
    db = _db()
    if db:
        import store
        store.people_save(db, data)
        return
    d = os.path.dirname(PATH)
    os.makedirs(d, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=".users-", suffix=".tmp", dir=d)
    try:
        os.fchmod(fd, 0o600)
    except (OSError, AttributeError):
        pass
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(tmp, PATH)


def _store():
    return load() or {"owner": {}, "members": {}, "members_can_upload": False}


def owner_display(data=None):
    data = data if data is not None else load()
    return ((data or {}).get("owner") or {}).get("display") or "owner"


def set_owner_display(display):
    data = _store()
    data["owner"]["display"] = (display or "").strip()[:40] or "owner"
    save(data)


def member(name, data=None):
    data = data if data is not None else load()
    return ((data or {}).get("members") or {}).get(key_of(name))


def members(data=None):
    data = data if data is not None else load()
    return sorted(((data or {}).get("members") or {}).values(), key=lambda m: m["name"])


def add_member(name, password, display=None):
    """Create a member. Returns an error sentence, or None on success."""
    if not valid_name(name):
        return ("Names are 1-32 letters, digits, spaces, dots, dashes or underscores, "
                "and can't be “owner”.")
    if len(password or "") < 8:
        return "Choose a password of at least 8 characters."
    data = _store()
    k = key_of(name)
    if k in data["members"] or k == key_of(owner_display(data)):
        return f"There is already someone called {name}."
    data["members"][k] = {"name": k, "display": (display or name).strip()[:40],
                          "role": "member", "hash": generate_password_hash(password),
                          "ver": 1, "disabled": False}
    save(data)
    return None


def _update(name, fn):
    data = _store()
    m = data["members"].get(key_of(name))
    if not m:
        return False
    fn(m)
    save(data)
    return True


def reset_password(name, password):
    if len(password or "") < 8:
        return False
    # A new password also signs every old session out.
    return _update(name, lambda m: m.update(hash=generate_password_hash(password),
                                            ver=int(m.get("ver", 1)) + 1))


def sign_out_everywhere(name):
    """Bump the member's version: their old cookies fail on the next request, the
    owner's sessions (and other members') are untouched."""
    return _update(name, lambda m: m.update(ver=int(m.get("ver", 1)) + 1))


def set_disabled(name, disabled):
    return _update(name, lambda m: m.update(disabled=bool(disabled),
                                            ver=int(m.get("ver", 1)) + (1 if disabled else 0)))


def set_members_can_upload(allowed):
    data = _store()
    data["members_can_upload"] = bool(allowed)
    save(data)


def remove(name):
    data = _store()
    if data["members"].pop(key_of(name), None) is None:
        return False
    save(data)
    return True


# ---- sign-in -----------------------------------------------------------------
def locked(name, now=None):
    now = time.time() if now is None else now
    with _lock:
        recent = [t for t in _fails.get(key_of(name), []) if now - t < LOCK_WINDOW]
        _fails[key_of(name)] = recent
        return len(recent) >= LOCK_FAILS


def note_failure(name, now=None):
    with _lock:
        _fails.setdefault(key_of(name), []).append(time.time() if now is None else now)


def clear_failures(name):
    with _lock:
        _fails.pop(key_of(name), None)


def check_member(name, password):
    """The member record when `name` + `password` sign in, else None. A disabled
    member never signs in."""
    m = member(name)
    if not m or m.get("disabled") or not m.get("hash"):
        return None
    return m if check_password_hash(m["hash"], password or "") else None
