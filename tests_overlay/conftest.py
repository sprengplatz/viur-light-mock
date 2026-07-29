"""Bootstrap for the overlay test root — runs BEFORE the first viur import.

The overlay is the one feature of this package that cannot be tested against
our own fakes: it patches seams *on a real viur-core*, and its whole design
leans on viur's own ``QueryDefinition``, ``_entryMatchesQuery`` and
``_resort_result``. None of those exist on the stand-ins in
:mod:`viur.light_mock.modules`.

Real viur-core cannot be imported in a bare environment, though — two hurdles,
both hit at *import* time, which is why this file does its work at module level
and not in a fixture:

1. ``viur/core/config.py`` calls ``google.auth.default()`` on import. Without
   Application Default Credentials that raises. We hand it anonymous
   credentials and a throwaway project id. A credentials-shaped JSON file would
   have worked too, but shipping one in a public repo is the wrong direction
   even when its contents are fake.
2. ``viur/core/db/transport.py`` builds a ``datastore.Client()`` on import.
   With the stub above it constructs offline; ``DATASTORE_EMULATOR_HOST`` then
   points it at a dead port, so anything that *did* escape fails with a
   connection error instead of reaching Google. That covers the window before
   ``install_db_overlay`` has armed its own lockout.

Why a separate test root at all: ``install_viur_core_mocks()`` writes the fakes
into ``sys.modules`` permanently, with no restore. Once any test in a process
installs them, real viur-core is unreachable for the rest of that process. So
the two kinds of test cannot share a pytest run — see the README for the two
commands CI uses.
"""
import os

os.environ.setdefault("DATASTORE_EMULATOR_HOST", "localhost:1")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "light-mock-test")

import google.auth  # noqa: E402
from google.auth.credentials import AnonymousCredentials  # noqa: E402

google.auth.default = lambda *args, **kwargs: (
    AnonymousCredentials(),
    os.environ["GOOGLE_CLOUD_PROJECT"],
)

