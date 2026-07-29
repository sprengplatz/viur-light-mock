"""Store-backed query execution in overlay mode.

The seam is ``Query._run_single_filter_query``, which every execution path goes
through (``run()`` for the single and the multi-query case, and ``iter()``).
Patching the *method* rather than the transport function is deliberate: it hands
us ``self``, so viur's own ``_resort_result`` does the sorting, and viur's
``_entryMatchesQuery`` does the matching. Nothing about filter or sort semantics
is restated here.

Tests drive ``db.Query`` directly instead of ``skel.all()``. That is the honest
level for this package: it exercises the real query-building code (filter
parsing, operator normalisation, QueryDefinition) without needing project
skeletons, which only an application test suite has.
"""
import pytest

from viur.light_mock.overlay import install_db_overlay


def _seed(db, state, kind, id_, **values):
    entity = db.Entity(db.Key(kind, id_))
    entity.update(values)
    state.store[entity.key] = entity
    return entity


def test_query_returns_seeded_entities_of_its_kind_only(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    wanted = _seed(db, state, "thing", 1, x=1)
    _seed(db, state, "other", 1, x=1)

    assert db.Query("thing").run() == [wanted]


def test_query_on_an_empty_store_returns_an_empty_list(monkeypatch):
    import viur.core.db as db
    install_db_overlay(monkeypatch)

    assert db.Query("thing").run() == []


def test_equality_filter_selects_matching_entities(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    wanted = _seed(db, state, "thing", 1, colour="red")
    _seed(db, state, "thing", 2, colour="blue")

    assert db.Query("thing").filter("colour =", "red").run() == [wanted]


def test_range_filters_combine_as_and(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    _seed(db, state, "thing", 1, n=5)
    wanted = _seed(db, state, "thing", 2, n=15)
    _seed(db, state, "thing", 3, n=25)

    result = db.Query("thing").filter("n >", 10).filter("n <=", 20).run()

    assert result == [wanted]


def test_filter_on_a_multi_valued_property_matches_any_element(monkeypatch):
    """``_entryMatchesQuery`` gives list properties any()-semantics, the same as
    the Datastore's multi-valued index."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    # Three values, not two: the flattened view collects repeated paths into a
    # list, and going from "second value" to "third value" is a separate step.
    wanted = _seed(db, state, "thing", 1, tags=["a", "b", "c"])
    _seed(db, state, "thing", 2, tags=["d"])

    assert db.Query("thing").filter("tags =", "b").run() == [wanted]
    assert db.Query("thing").filter("tags =", "c").run() == [wanted]


def test_key_filter_uses_the_entity_key(monkeypatch):
    """``__key__`` is not a dict item on the entity — it lives on ``.key`` — so
    the flattened view has to supply it."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    wanted = _seed(db, state, "thing", 1, x=1)
    _seed(db, state, "thing", 2, x=1)

    result = db.Query("thing").filter(f"{db.KEY_SPECIAL_PROPERTY} =", wanted.key)

    assert result.run() == [wanted]


def test_in_filter_matches_any_of_the_listed_values(monkeypatch):
    """``IN`` is a native single-query operator in viur-core 3.9 — it is not split
    into a multi-query — and ``_entryMatchesQuery`` implements it, so the union
    comes for free."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    red = _seed(db, state, "thing", 1, colour="red")
    blue = _seed(db, state, "thing", 2, colour="blue")
    _seed(db, state, "thing", 3, colour="green")

    result = db.Query("thing").filter("colour IN", ["red", "blue"]).run()

    assert len(result) == 2
    assert red in result and blue in result


def test_not_equal_filter_excludes_the_value(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    _seed(db, state, "thing", 1, colour="red")
    kept = _seed(db, state, "thing", 2, colour="blue")

    assert db.Query("thing").filter("colour !=", "red").run() == [kept]


def test_multi_query_results_are_merged_and_deduplicated_by_viur(monkeypatch):
    """A list-valued external filter on a key bone makes viur build a real
    multi-query (``bones/key.py``): one QueryDefinition per key, no custom merge,
    so ``_merge_multi_query_results`` unions and de-duplicates above our seam.

    The point of this test is what it does *not* find: the same entity is matched
    by both sub-queries, yet appears once. Nothing in the overlay de-duplicates —
    if it did, this would be testing our code instead of viur's.
    """
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    first = _seed(db, state, "thing", 1, n=1)
    second = _seed(db, state, "thing", 2, n=2)

    query = db.Query("thing")
    # Shaped exactly like bones/key.py builds it: a QueryDefinition per value.
    query.queries = [
        db.QueryDefinition("thing", {"n >=": 1}, []),   # matches both
        db.QueryDefinition("thing", {"n =": 2}, []),    # matches the second again
    ]
    result = query.run()

    assert len(result) == 2, "the overlapping hit must appear once, not twice"
    assert first in result and second in result


def test_relation_parent_jump_stays_in_the_store(monkeypatch):
    """``_fixKind`` (query.py) jumps from a ``viur-relations`` hit to its parent
    entity, the shape a relational filter produces. It uses the ``get`` that
    ``query.py`` bound with a module-level from-import — which still resolves to
    the in-memory client, because the overlay replaced the *client* rather than
    the ``db`` functions. No extra seam needed; pinning that here so a change of
    approach would show up."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    parent = _seed(db, state, "thing", 1, n=1)
    relation = db.Entity(db.Key("viur-relations", 1, parent=parent.key))
    relation["src"] = parent
    state.store[relation.key] = relation

    # What RelationalBone.buildDBFilter does: rewrite the query onto viur-relations
    # while origKind stays the kind the caller asked for.
    query = db.Query("thing")
    query.kind = "viur-relations"
    query.queries = db.QueryDefinition("viur-relations", {}, [])

    assert query.run() == [parent]


def test_order_sorts_ascending_and_descending(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    low = _seed(db, state, "thing", 1, n=1)
    high = _seed(db, state, "thing", 2, n=9)
    mid = _seed(db, state, "thing", 3, n=5)

    ascending = db.Query("thing").order(("n", db.SortOrder.Ascending)).run()
    descending = db.Query("thing").order(("n", db.SortOrder.Descending)).run()

    assert ascending == [low, mid, high]
    assert descending == [high, mid, low]


def test_order_is_applied_level_by_level(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    a_late = _seed(db, state, "thing", 1, group="a", n=2)
    b_early = _seed(db, state, "thing", 2, group="b", n=1)
    a_early = _seed(db, state, "thing", 3, group="a", n=1)

    result = db.Query("thing").order(
        ("group", db.SortOrder.Ascending), ("n", db.SortOrder.Ascending)
    ).run()

    assert result == [a_early, a_late, b_early]


def test_an_entity_missing_the_sort_field_still_appears(monkeypatch):
    """viur's ``_resort_result`` substitutes a placeholder for a missing field
    rather than dropping the entity. Worth pinning: the real Datastore *omits*
    entities that have no value for the sort property, so this is one place where
    running viur's sorter is not the same as running the Datastore's index."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    with_field = _seed(db, state, "thing", 1, n=1)
    without_field = _seed(db, state, "thing", 2, other=1)

    result = db.Query("thing").order(("n", db.SortOrder.Ascending)).run()

    assert len(result) == 2
    assert with_field in result and without_field in result


def test_distinct_keeps_the_first_entity_per_value(monkeypatch):
    """``distinctOn`` groups the result. Which entity survives per group follows
    the sort order, so the two have to be applied in that sequence."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    first_a = _seed(db, state, "thing", 1, group="a", n=1)
    _seed(db, state, "thing", 2, group="a", n=2)
    first_b = _seed(db, state, "thing", 3, group="b", n=3)

    result = (
        db.Query("thing")
        .order(("n", db.SortOrder.Ascending))
        .distinctOn(["group"])
        .run()
    )

    assert result == [first_a, first_b]


def test_distinct_on_several_fields_groups_by_the_combination(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    a1 = _seed(db, state, "thing", 1, group="a", kind_="x", n=1)
    _seed(db, state, "thing", 2, group="a", kind_="x", n=2)
    a2 = _seed(db, state, "thing", 3, group="a", kind_="y", n=3)

    result = (
        db.Query("thing")
        .order(("n", db.SortOrder.Ascending))
        .distinctOn(["group", "kind_"])
        .run()
    )

    assert result == [a1, a2]


def test_distinct_applies_before_the_limit(monkeypatch):
    """Otherwise a limit of 2 over three rows in two groups would return one row."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    first_a = _seed(db, state, "thing", 1, group="a", n=1)
    _seed(db, state, "thing", 2, group="a", n=2)
    first_b = _seed(db, state, "thing", 3, group="b", n=3)

    result = (
        db.Query("thing")
        .order(("n", db.SortOrder.Ascending))
        .distinctOn(["group"])
        .run(limit=2)
    )

    assert result == [first_a, first_b]


def test_distinct_rejects_a_sort_order_that_the_datastore_would_reject(monkeypatch):
    """Google's rule, verbatim: "If ordering is specified, the set of properties
    specified in the `distinct on` clause must appear before any non-`distinct on`
    properties in the sort orders."

    The fake must not be more permissive than the service here — otherwise a query
    the Datastore rejects would pass in tests.
    """
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    _seed(db, state, "thing", 1, group="a", n=1)

    query = (
        db.Query("thing")
        .order(("n", db.SortOrder.Ascending), ("group", db.SortOrder.Ascending))
        .distinctOn(["group"])
    )

    with pytest.raises(ValueError, match="distinct"):
        query.run()


def test_distinct_accepts_a_sort_order_that_leads_with_it(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    first_a = _seed(db, state, "thing", 1, group="a", n=1)
    _seed(db, state, "thing", 2, group="a", n=2)
    first_b = _seed(db, state, "thing", 3, group="b", n=3)

    result = (
        db.Query("thing")
        .order(("group", db.SortOrder.Ascending), ("n", db.SortOrder.Ascending))
        .distinctOn(["group"])
        .run()
    )

    assert result == [first_a, first_b]


def test_limit_truncates_the_result(monkeypatch):
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    for i in range(5):
        _seed(db, state, "thing", i, n=i)

    assert len(db.Query("thing").run(limit=2)) == 2


def test_a_query_without_an_explicit_limit_uses_the_configured_default(monkeypatch):
    """``run()`` falls back to ``QueryDefinition.limit``, which
    ``conf.db.query_default_limit`` seeds at 30. Application code calling a bare
    ``.fetch()`` therefore never sees more than 30 rows — a fake that ignored the
    limit would hide that."""
    import viur.core.db as db
    from viur.core.config import conf
    state = install_db_overlay(monkeypatch)
    for i in range(conf.db.query_default_limit + 5):
        _seed(db, state, "thing", i, n=i)

    assert len(db.Query("thing").run()) == conf.db.query_default_limit


def test_relational_key_filter_navigates_into_a_denormalised_entity(monkeypatch):
    """Relational bones store a list of ``{"dest": <entity>, "rel": …}`` dicts,
    and viur filters them as ``bone.dest.__key__``. Flat ``entry.get(field)``
    would never see that, so the flattened view is dotted."""
    import viur.core.db as db
    state = install_db_overlay(monkeypatch)
    target = db.Key("project", 7)
    wanted = _seed(
        db, state, "thing", 1,
        project=[{"dest": db.Entity(target), "rel": None}],
    )
    _seed(
        db, state, "thing", 2,
        project=[{"dest": db.Entity(db.Key("project", 8)), "rel": None}],
    )

    result = db.Query("thing").filter(
        f"project.dest.{db.KEY_SPECIAL_PROPERTY} =", target
    )

    assert result.run() == [wanted]
