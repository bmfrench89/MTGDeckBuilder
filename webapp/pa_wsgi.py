#!/usr/bin/env python3
"""WSGI entry point for a hosted deployment (PythonAnywhere, or any WSGI host).

Nothing about the app changes to run hosted. ``webapp/app.py`` keeps ``app.run()``
behind ``if __name__ == "__main__":`` and resolves every path relative to the repo
root, so importing it here starts no server, needs no environment variables, and
needs no secret key (the app uses no signed sessions).

This module is **self-locating**: it puts its own directory on ``sys.path``, so it
works from any checkout path with no edits. On PythonAnywhere, replace the contents
of the auto-generated ``/var/www/<username>_pythonanywhere_com_wsgi.py`` with::

    import sys
    sys.path.insert(0, "/home/<username>/MTGDeckBuilder/webapp")
    from pa_wsgi import application   # noqa: F401

That file — which lives outside the repo — is the only place your username appears.

**Do not add a "Static files" mapping for /static/ on the host.** ``/static/tokens.css``
is a Flask route (see ``app.py``) serving ``scripts/assets/tokens.css``, the design
tokens shared with the generated dashboards. A directory mapping would shadow that
route and 404 the shared scales on every page. ``tests/test_deploy.py`` guards this.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from app import app as application       # noqa: E402  (sys.path prepared above)
