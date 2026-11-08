"""Property tests: deep-merge is associative and idempotent (ADR-400 §2)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from apex.tenant_config.resolver import deep_merge, flatten

leaf = st.one_of(st.none(), st.booleans(), st.integers(-1000, 1000), st.text(max_size=8))

# Layers are validated against one config schema, so a given path is either always a leaf (a scalar, or
# ``null`` meaning unset) or always an object, never both. The properties below are stated for such
# shape-consistent layers (ADR-400 section 2). Across shapes a ``null`` replaces a whole subtree and the
# merge is not associative; ``test_null_over_object_is_a_replacement_not_associative`` pins that down.
_OBJECT_KEYS = {"a": {"x": leaf, "y": leaf}, "b": {"x": leaf}}
_LEAF_KEYS = ("c", "d")


def _tree() -> st.SearchStrategy[dict]:
    objects = {
        key: st.dictionaries(st.sampled_from(sorted(children)), leaf, max_size=2)
        for key, children in _OBJECT_KEYS.items()
    }
    pairs = {**objects, **dict.fromkeys(_LEAF_KEYS, leaf)}
    return st.fixed_dictionaries({}, optional=pairs)


def test_null_over_object_is_a_replacement_not_associative() -> None:
    a, b, c = {"a": {"b": None}}, {"a": None}, {"a": {"a": None}}
    assert deep_merge(a, deep_merge(b, c)) != deep_merge(deep_merge(a, b), c)


@settings(max_examples=1000, deadline=None)
@given(_tree(), _tree(), _tree())
def test_deep_merge_is_associative(a: dict, b: dict, c: dict) -> None:
    assert deep_merge(a, deep_merge(b, c)) == deep_merge(deep_merge(a, b), c)


@settings(max_examples=200, deadline=None)
@given(_tree())
def test_deep_merge_is_idempotent(a: dict) -> None:
    assert deep_merge(a, a) == a


@settings(max_examples=200, deadline=None)
@given(_tree(), _tree())
def test_later_layer_wins_on_every_flat_leaf_it_defines(a: dict, b: dict) -> None:
    merged = flatten(deep_merge(a, b))
    for path, value in flatten(b).items():
        if value == {}:  # an empty object in a patch merges nothing (ADR-400 §2)
            continue
        assert merged[path] == value
