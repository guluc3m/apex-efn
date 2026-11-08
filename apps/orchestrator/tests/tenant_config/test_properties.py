"""Property tests: deep-merge is associative and idempotent (ADR-400 §2)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from apex.tenant_config.resolver import deep_merge, flatten

leaf = st.one_of(st.none(), st.booleans(), st.integers(-1000, 1000), st.text(max_size=8))
keys = st.sampled_from(["a", "b", "c"])


def _tree(depth: int = 2) -> st.SearchStrategy[dict]:
    if depth == 0:
        return st.dictionaries(keys, leaf, max_size=3)
    return st.dictionaries(keys, st.one_of(leaf, _tree(depth - 1)), max_size=3)


@settings(max_examples=200, deadline=None)
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
