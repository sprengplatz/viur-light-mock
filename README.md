# viur-light-mock

Pytest helpers and `viur.core.*` stand-ins for testing ViUR packages without
App Engine.

[![Tests](https://github.com/sprengplatz/viur-light-mock/actions/workflows/test.yml/badge.svg)](https://github.com/sprengplatz/viur-light-mock/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## What it does

`viur-light-mock` is a pytest plugin that injects lightweight stand-ins for the
`viur.core.*` modules into `sys.modules` *before* your tests are collected.
That lets a package import `from viur.core import db, utils, errors, …` in
production code while the tests run hermetically — no Google App Engine
stack, no Datastore connection, fast cold-start.

The plugin auto-discovers via the `pytest11` entry-point. No `conftest.py`
boilerplate, no `pytest_plugins =` line — install the package and the
fixtures and mocks are there.

## Requirements

- Python ≥ 3.12
- pytest ≥ 8

## Install

The PyPI distribution name is `spltz-viur-light-mock` (the
experimental `spltz-` prefix marks it pre-1.0). The Python import
path stays `viur.light_mock` — namespace package, no rename in user
code.

```bash
pip install spltz-viur-light-mock
```

For a ViUR-based package that wants to use it:

```toml
[project.optional-dependencies]
test = ["pytest", "pytest-cov", "spltz-viur-light-mock>=0.1"]
```

## Usage

Just write tests as if `viur.core` were real:

```python
# tests/test_my_module.py
def test_something(db_state, freeze_time, make_query):
    from viur.core.db import Entity, Key
    from my_package import MyAdapter

    existing = Entity(Key("order_revision", 1))
    existing["revision_index"] = 7
    make_query(single=existing)

    MyAdapter().do_something()

    assert any(p["revision_index"] == 8 for p in db_state.put_calls)
```

The fixtures used here (`db_state`, `freeze_time`, `make_query`) are
auto-discovered from the plugin — you don't need to import them or wire
them up in a `conftest.py`.

## What's mocked

| Module                          | Stand-in surface                                                                |
| ------------------------------- | ------------------------------------------------------------------------------- |
| `viur.core`                     | Identity decorators `exposed`, `force_post`, `skey`; `conf` attr               |
| `viur.core.db`                  | `Key`, `Entity`, `Query`, `SortOrder`, `Get`, `Put`, `Delete`, `AllocateIDs`    |
| `viur.core.utils`               | `utcNow()` — freezable                                                          |
| `viur.core.errors`              | `Unauthorized`, `Forbidden`, `BadRequest`, `NotFound`                           |
| `viur.core.current`             | `user`, `request` slots with `.get/.set`                                        |
| `viur.core.skeleton`            | `Skeleton`, `SkeletonInstance`, `DatabaseAdapter`                               |
| `viur.core.tasks`               | `PeriodicTask` decorator (no-op, but tags the wrapped function)                 |
| `viur.core.render.json.default` | `CustomJsonEncoder` aliased to stdlib `json.JSONEncoder`                        |
| `viur.core.bones.base`          | `ReadFromClientError`, `ReadFromClientErrorSeverity`                            |

## Fixtures

| Fixture                       | Purpose                                                                |
| ----------------------------- | ---------------------------------------------------------------------- |
| `db_state`                    | Handle on the in-memory datastore (`store`, `put_calls`, `delete_calls`, …) |
| `freeze_time`                 | Pin `utils.utcNow()` to a controllable value                           |
| `make_query`                  | Pre-populate the next `db.Query(...)` with single/many results         |
| `patched_user`                | Set `current.user.get()` to a fake user dict                           |
| `_viur_light_mock_reset_state`   | Autouse — resets the fake datastore singleton between tests            |

## Overlay mode (real viur-core installed)

The stand-ins above are for packages that have **no** viur-core installed. An
*application* test suite is the opposite case: real viur-core is present and
production code runs on the full framework (prototypes, bones, compute,
skeletons). There you don't want to fake the framework — you only want to keep
the Datastore off the network so tests run in CI. That's overlay mode: it
monkeypatches just the external seams (`db` reads/writes, the request context)
onto the in-memory `db_state`, leaving real bone serialization, compute bones
and tree logic running.

```python
from viur.light_mock import install_db_overlay, set_request

def test_writes_go_to_memory(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)     # patches db.get/put/delete/…
    set_request(monkeypatch, kwargs={"parententry": "root"})

    MyModule().add(...)                          # real viur-core code path

    assert state.put_calls                       # observed the write in-memory
```

The pytest plugin **auto-detects** which mode applies: when a real `viur.core`
is importable it leaves it untouched (so `install_db_overlay` patches the
genuine modules); only when viur-core is absent does it inject the stand-ins.
No configuration needed — the same package serves both.

What overlay mode replaces is the **datastore client** itself
(`viur.core.db.transport.__client__`, plus the separate binding `viur.core.db.utils`
holds). viur's own `get`/`put`/`delete`/`allocate_ids`/`run_in_transaction` then
run for real against an in-memory store, so their contracts — batch shapes,
return values, error cases — are viur's, not restated here and unable to drift
from it. Requires **viur-core 3.8+**; on 3.7 the datastore lives in the compiled
`viur-datastore` package, which exposes no client to replace, and
`install_db_overlay` says so rather than patching nothing.

Queries are served from the store too, one layer up: `Query._run_single_filter_query`
is replaced so that viur's own `_entryMatchesQuery` does the matching and its
`_resort_result` the sorting. Filters, ordering, limit, `distinctOn`, cursors and
`count` all work; `iter()` pages properly rather than stopping after its first
batch. Entities are matched against a dotted view of themselves, with `__key__`
injected at every level, so relational filters like `project.dest.__key__ =` hit.

Deliberately *not* reproduced:

- `transaction()` has no rollback — writes land immediately, and reads inside a
  transaction do not see the pre-transaction state.
- Cursors are offsets, not opaque index positions. Insert or delete between two
  fetches and the window shifts differently than it would against the service.
- A grouped query returns whole entities; a real projection query returns only the
  projected properties.
- An entity that lacks the sort field still appears, because that is what
  `_resort_result` does. The Datastore would omit it for want of an index entry.
- No index simulation, so nothing raises "needs index".
- `DbState.get_result` pins only the single-key `get`.

Because the mode follows the environment, a test suite can only exercise one of
them per run — see [Development](#development) for how this package tests both.

## Public API

If you need to drive the mocks from your own `conftest.py` (for example to
add a project-specific stand-in), import directly:

```python
from viur.light_mock import (
    install_viur_core_mocks,       # inject the fake viur.core.* hierarchy
    install_db_overlay, set_request,  # overlay mode against a real viur-core
    FakeKey, FakeEntity, FakeQuery, FakeSortOrder, DbState,
)
```

## Why not just use `unittest.mock`?

You can — but the fake `viur.core` modules here are *real Python modules*
in `sys.modules`, so `from viur.core import db` resolves naturally without
patching every test, and `isinstance` checks against `db.Entity` etc. work
out of the box.

## Development

The suite is split by mode, because the mode follows the environment: the plugin
injects the stand-ins only when no real viur-core is importable. So `tests/`
(stand-ins) needs an environment *without* viur-core, and `tests_overlay/`
(overlay against the real framework) needs one *with* it. Installing both at once
would put the whole environment in overlay mode and leave `tests/` without the
stand-ins it exists to exercise.

Run them in sequence, installing viur-core in between:

```bash
git clone https://github.com/sprengplatz/viur-light-mock
cd viur-light-mock

# Run via `coverage run` so the plugin import itself is instrumented.
# pytest-cov would start measuring after the entry-point plugin loads,
# leaving viur.light_mock.plugin partially uncovered.

pip install -e ".[dev]"
coverage run -m pytest tests                  # stand-in mode

pip install -e ".[dev,overlay]"
coverage run -a -m pytest tests_overlay       # overlay mode; -a appends

coverage report --fail-under=100              # gate over both runs
```

`tests_overlay/conftest.py` keeps that environment offline: viur-core calls
`google.auth.default()` at import time, so it is stubbed with anonymous
credentials and a throwaway project id, and `DATASTORE_EMULATOR_HOST` points at a
dead port. No credentials, real or fake, are needed or stored.

## License

MIT — see [LICENSE](LICENSE).
