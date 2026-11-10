"""ADR-300: ``apex.domain`` engines take ``now`` and config as inputs. No clock, no unseeded randomness."""

from __future__ import annotations

import ast
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[2] / "src" / "apex" / "domain"
BANNED_CALLS = {"now", "utcnow", "today", "time", "time_ns", "monotonic", "perf_counter"}
BANNED_MODULES = {"random", "secrets", "uuid"}


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [a.name for a in node.names]
            )
            found += [f"imports {n}" for n in names if n.split(".")[0] in BANNED_MODULES]
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in BANNED_CALLS
        ):
            found.append(f"calls .{node.func.attr}() at line {node.lineno}")
    return [f"{path.relative_to(DOMAIN)}: {v}" for v in found]


def test_domain_reads_no_clock_or_randomness() -> None:
    assert [v for p in sorted(DOMAIN.rglob("*.py")) for v in _violations(p)] == []


def test_the_check_catches_a_clock_read(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("import random\nfrom datetime import datetime\nx = datetime.now()\n")
    global DOMAIN
    saved, DOMAIN = DOMAIN, tmp_path
    try:
        assert len(_violations(bad)) == 2
    finally:
        DOMAIN = saved
