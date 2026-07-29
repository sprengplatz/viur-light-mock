# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-07-29

### Added

- **Store-backed queries in overlay mode.** After seeding, `db.Query(...)` /
  `skel.all()` returns matching entities from the in-memory store instead of
  reaching for the datastore. Filters, ordering and the limit are all viur's own
  work: the seam is the method `Query._run_single_filter_query`, which hands over
  `self`, so matching runs through viur's `_entryMatchesQuery` and sorting through
  its `_resort_result`. Operator semantics (`=`, `<`, `<=`, `>`, `>=`, `IN`,
  `NOT_IN`, `!=`, any()-semantics on multi-valued properties, OR groups) are
  therefore not reimplemented and cannot drift.

  Entities are matched against a dotted view of themselves, the way the Datastore
  indexes nested entity properties — with `__key__` injected at every level, so
  `__key__ =` and relational filters such as `project.dest.__key__ =` work.

  One thing to know: an entity that lacks the sort field still appears in the
  result, because that is what `_resort_result` does — the real Datastore would
  omit it for want of an index entry.

- **Grouping via `distinctOn`**, applied after the sort and before the limit, so
  which member of a group survives follows the ordering. The sort-order
  constraint the service imposes is enforced (`distinct on` properties must not be
  ordered after non-`distinct on` ones), because the client library does not check
  it locally and a rejected query would otherwise pass in tests. Grouping on a
  multi-valued property raises rather than inventing a grouping key for it.

- **Cursors and `count`.** Cursors are offsets into the result: `startCursor`
  resumes, `endCursor` bounds, and `currentCursor` is handed back until the window
  is exhausted — which is what lets `iter()` walk past its first 100-entity batch
  instead of stopping there and looking complete. `Query.count()`, `db.count` and
  the deprecated `db.Count` all count from the store, applying filters only, the
  way `transport.count` builds its aggregation: orders and `distinct` do not reach
  it, so a grouped query counts rows rather than groups.

### Changed

- **Overlay mode replaces the datastore client** instead of monkeypatching
  individual `db` functions. `install_db_overlay` swaps
  `viur.core.db.transport.__client__` — plus the separate binding
  `viur.core.db.utils` holds via its module-level `from`-import — for an
  in-memory client. viur's own `get`/`put`/`delete`/`allocate_ids`/
  `run_in_transaction` then execute for real against the store, so their
  contracts are viur's and cannot drift away from it.

  Everything below follows from that. Each was a place where the hand-written
  stand-ins disagreed with production, in one direction or the other:

  - `db.run_in_transaction` is intercepted now. Only the deprecated
    `RunInTransaction` alias used to be, and `Skeleton.write` calls the lowercase
    name — so every write test opened a real transaction against whatever project
    the ambient credentials resolved to.
  - `db.allocate_ids` raises `TypeError` for a non-`str` kind, as production does.
    It used to accept a `Key`, turning a call that fails live into a green test.
  - `db.AllocateIDs` returns a single `Key`, not a list.
  - `db.put` and `db.delete` accept the list form (`put_multi`/`delete_multi`).
  - `db.put` raises `ValueError` for a keyless entity instead of inventing a key.
  - Batch `db.get([...])` **omits misses instead of padding with `None`**,
    reversing the 0.2.0 behaviour noted below: `get_multi` reports misses only
    when the caller passes a `missing` list, and viur passes none. Be aware that
    this makes viur's own `if not all(db.get([...]))` guard in `RelationalBone`
    unable to detect a missing key — the padding used to mask that.
- Overlay mode **fails loudly on queries** rather than letting them reach the
  network. There is no real client left to escape to, and the in-memory one has
  no query support on purpose, so an unimplemented query path raises instead of
  quietly returning results from a live datastore.
- `DbState.get_result` pins only the single-key `get`. A pinned scalar cannot
  sensibly travel through viur's batch branch, which sorts its result.

### Removed

- Overlay mode requires **viur-core 3.8+**. On 3.7 the datastore ships as the
  compiled `viur-datastore`, which exposes no client to replace;
  `install_db_overlay` raises `RuntimeError` explaining that instead of patching
  nothing and looking like it worked.

### Notes for contributors

- The test suite is split by mode, because the plugin picks its mode from whether
  a real `viur.core` is importable — so one environment can only exercise one
  mode. `tests/` runs without viur-core, `tests_overlay/` with it, in sequence;
  see the README's Development section.
- Two behaviours are deliberately not reproduced by the in-memory client:
  `transaction()` has no rollback (writes land immediately), and reads inside a
  transaction do not see the pre-transaction state.

## [0.2.0] - 2026-07-07

### Added

- **Overlay mode** for test suites that run against a *real* installed
  viur-core. `install_db_overlay(monkeypatch)` monkeypatches only the
  external Datastore seams (`db.get`/`put`/`delete`/`allocate_ids` and
  their capitalized aliases, plus `RunInTransaction`) onto the in-memory
  `db_state`, leaving real bone serialization, compute bones and tree
  logic running. `set_request(monkeypatch, **attrs)` swaps
  `current.request` for a throwaway namespace. Both are undone after the
  test. New public exports: `install_db_overlay`, `set_request`.
- Batch `db.get([...])` support in overlay mode: a sequence of keys
  returns a list aligned to the input (`None` for misses), as relation
  (RefSkel) denormalization expects.

### Changed

- PyPI distribution name is now **`spltz-viur-light-mock`** (the
  experimental `spltz-` prefix marks the package pre-1.0). The
  Python import path stays `viur.light_mock` — namespace package,
  no rename in user code. Consumers should update their
  `pyproject.toml`:

      test = ["pytest", "pytest-cov", "spltz-viur-light-mock>=0.1"]

### Fixed

- The pytest plugin no longer installs the fake `viur.core.*` hierarchy
  when a real viur-core is importable. Previously the stand-ins were
  injected unconditionally on plugin load, clobbering a real framework
  before overlay mode could patch it. The plugin now auto-detects which
  mode applies (`importlib.util.find_spec`) and leaves a real viur-core
  untouched.

## [0.1.0] - 2026-05-20

### Added

- Initial release, extracted from the `viur-revision` test harness.
- Pytest plugin (`pytest11` entry-point `viur_light_mock`) that auto-loads
  before test collection.
- `install_viur_core_mocks()` for explicit setup outside of pytest.
- Fake modules: `viur.core.db`, `viur.core.utils`, `viur.core.errors`,
  `viur.core.current`, `viur.core.skeleton`, `viur.core.tasks`,
  `viur.core.render.json.default`.
- Identity decorators for `viur.core.exposed`, `viur.core.force_post`,
  `viur.core.skey`.
- Data types: `FakeKey`, `FakeEntity`, `FakeQuery`, `FakeSortOrder`, `DbState`.
- Pytest fixtures: `db_state`, `freeze_time`, `make_query`, `patched_user`,
  plus an autouse state reset.

[Unreleased]: https://github.com/sprengplatz/viur-light-mock/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/sprengplatz/viur-light-mock/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/sprengplatz/viur-light-mock/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/sprengplatz/viur-light-mock/releases/tag/v0.1.0
