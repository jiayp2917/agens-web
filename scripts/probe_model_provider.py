"""Run one safe local capability probe for the configured evaluation provider."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from agens_novel.evaluation.ledger import EvaluationLedger, PriceCard
from agens_novel.evaluation.manifest import write_inventory_manifest, write_manifest
from agens_novel.evaluation.model_config import EvaluationModelConfig
from agens_novel.evaluation.provider_probe import probe_provider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--price-card", type=Path)
    parser.add_argument("--max-total-calls", type=int, default=800)
    parser.add_argument("--max-narrator-calls", type=int, default=650)
    parser.add_argument("--max-elapsed-seconds", type=float, default=1800.0)
    args = parser.parse_args()

    config = EvaluationModelConfig.from_environment()
    write_manifest(config, mode="provider-probe")
    price_card = _load_price_card(args.price_card)
    ledger = EvaluationLedger(
        provider=config.provider,
        model=config.model,
        price_card=price_card,
        max_total_calls=args.max_total_calls,
        max_narrator_calls=args.max_narrator_calls,
        max_elapsed_seconds=args.max_elapsed_seconds,
    )
    report = asyncio.run(probe_provider(config, ledger=ledger))
    write_inventory_manifest()
    probes = report["probes"]
    contract_names = {"world_opening", "narrator", "judge"}
    contracts_ok = all(
        bool(probe["strict"])
        for probe in probes
        if str(probe["name"]) in contract_names
    )
    output = {
        "provider": report["provider"],
        "model": report["model"],
        "recommended_transport": report["recommended_transport"],
        "probe_count": len(probes),
        "strict_count": sum(bool(probe["strict"]) for probe in probes),
        "contracts_ok": contracts_ok,
        "call_count": report["ledger"]["call_count"],
        "estimated_cost_known": report["ledger"]["estimated_cost"] is not None,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if contracts_ok else 2


def _load_price_card(path: Path | None) -> PriceCard | None:
    if path is None:
        return None
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("price card must be a JSON object")
    return PriceCard(
        effective_date=str(value.get("effective_date") or ""),
        currency=str(value.get("currency") or ""),
        input_per_million=_number_or_none(value.get("input_per_million")),
        output_per_million=_number_or_none(value.get("output_per_million")),
        cached_input_per_million=_number_or_none(value.get("cached_input_per_million")),
    )


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if number < 0:
        raise ValueError("price card rates must be non-negative")
    return number


if __name__ == "__main__":
    raise SystemExit(main())
