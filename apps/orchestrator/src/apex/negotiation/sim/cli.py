"""Command line for the buyer-side simulation (D5-11).

    python -m apex.negotiation.sim run --marketplace-url http://localhost:8002 \
        [--llm-url http://localhost:8003] [--json report.json] [--buyers 3] [--query "nitrile gloves"]

Prints one block per buyer (chosen supplier, offer ladder, outcome), writes the JSON report when
``--json`` is given, and exits 1 when the marketplace is unreachable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from apex.negotiation.sim.market import MarketplaceUnavailable
from apex.negotiation.sim.models import (
    DEFAULT_SEARCH_QUERY,
    ChosenOffer,
    ScenarioConfig,
    ScenarioReport,
)
from apex.negotiation.sim.pipeline import run_scenario
from apex.negotiation.templates import format_price

__all__ = ["build_parser", "main", "render_report"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m apex.negotiation.sim",
        description="Buyer-side simulation over the mock marketplace (D5-11).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run the scenario and print the transcript")
    run.add_argument(
        "--marketplace-url",
        required=True,
        help="root URL of the mock marketplace, e.g. http://localhost:8002",
    )
    run.add_argument(
        "--llm-url", default=None, help="OpenAI-compatible LLM; templates when omitted"
    )
    run.add_argument("--json", dest="json_path", default=None, help="write the JSON report here")
    run.add_argument(
        "--buyers", type=int, default=3, help="how many buyer profiles to simulate (default 3)"
    )
    run.add_argument(
        "--query", default=DEFAULT_SEARCH_QUERY, help="marketplace search query for every buyer"
    )
    return parser


def render_report(report: ScenarioReport) -> str:
    """Readable text version of the report: one block per buyer."""
    lines: list[str] = [
        f"Mock marketplace simulation — {report.marketplace_url}",
        f"LLM: {report.llm_url or 'none (deterministic templates)'}",
        f"Offers found: {len(report.items)} | Suppliers: {len(report.sellers)}",
    ]
    for run in report.buyers:
        lines.append("")
        lines.append(f"Buyer: {run.name} ({run.buyer_id}) — outcome: {run.outcome}")
        chosen = run.chosen
        if chosen is not None:
            offer = ChosenOffer.model_validate(chosen)
            lines.append(
                f"  Chosen: {offer.item_id} — {offer.supplier_name or offer.supplier_id} "
                f"@ {format_price(offer.asking_price.amount_minor, offer.asking_price.currency)}/unit"
            )
        for step in run.steps:
            price = (
                f" ({format_price(step.price.amount_minor, step.price.currency)})"
                if step.price is not None
                else ""
            )
            lines.append(f"  [{step.kind}] {step.detail}{price}")
        if run.final_price is not None:
            lines.append(
                f"  Final price: "
                f"{format_price(run.final_price.amount_minor, run.final_price.currency)}/unit"
            )
        if run.transcript:
            lines.append("  Transcript:")
            for line in run.transcript:
                lines.append(f"    {line.role:>6}: {line.text}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = ScenarioConfig(
        marketplace_url=args.marketplace_url,
        llm_url=args.llm_url,
        search_query=args.query,
    )
    if not 1 <= args.buyers <= len(config.buyers):
        parser.error(f"--buyers must be between 1 and {len(config.buyers)}")
    config = config.model_copy(update={"buyers": config.buyers[: args.buyers]})

    try:
        report = asyncio.run(run_scenario(config))
    except MarketplaceUnavailable as exc:
        print(f"marketplace unreachable: {exc}", file=sys.stderr)
        return 1

    print(render_report(report))
    if args.json_path:
        path = Path(args.json_path)
        path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nJSON report written to {path}")
    return 0
