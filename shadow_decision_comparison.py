"""Pure comparison engine for old-versus-new shadow decisions.

The module compares two immutable ``CycleDecision`` objects created from the
same market-cycle snapshot. It does not import the trading runtime, read or
write state, register routes, replace callables, or place orders.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from shadow_decision_models import CandidateDecision, CycleDecision, Side


VERSION = "shadow-decision-comparison-2026-08-03-v1"


class DivergenceType(str, Enum):
    PARITY = "parity"
    ALLOWANCE = "allowance"
    SELECTION = "selection"
    TERMINAL_REASON = "terminal_reason"
    SCORE = "score"
    SIZE = "size"
    CANDIDATE_MISSING = "candidate_missing"


@dataclass(frozen=True, slots=True)
class CandidateComparison:
    symbol: str
    side: Side
    current_present: bool
    shadow_present: bool
    current_allowed: bool | None
    shadow_allowed: bool | None
    current_selected: bool
    shadow_selected: bool
    current_terminal_reason: str
    shadow_terminal_reason: str
    current_final_score: float | None
    shadow_final_score: float | None
    current_size_multiplier: float | None
    shadow_size_multiplier: float | None
    divergences: tuple[DivergenceType, ...]


@dataclass(frozen=True, slots=True)
class CycleComparison:
    cycle_id: str
    input_fingerprint: str
    current_authority: str
    shadow_authority: str
    parity: bool
    current_selected_symbols: tuple[str, ...]
    shadow_selected_symbols: tuple[str, ...]
    selected_only_by_current: tuple[str, ...]
    selected_only_by_shadow: tuple[str, ...]
    candidate_comparisons: tuple[CandidateComparison, ...]
    divergence_counts: tuple[tuple[str, int], ...]
    authority: str = "comparison_only"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_key(candidate: CandidateDecision) -> tuple[str, str]:
    return (candidate.signal.symbol.upper(), candidate.signal.side.value)


def _input_payload(decision: CycleDecision) -> dict[str, Any]:
    signals = sorted(
        (
            {
                "symbol": candidate.signal.symbol.upper(),
                "side": candidate.signal.side.value,
                "score": candidate.signal.score,
                "rank_score": candidate.signal.rank_score,
                "price": candidate.signal.price,
                "sector": candidate.signal.sector,
                "strategy_bucket": candidate.signal.strategy_bucket,
                "confirmations": list(candidate.signal.confirmations),
            }
            for candidate in decision.candidates
        ),
        key=lambda row: (row["symbol"], row["side"]),
    )
    positions = sorted(
        (
            {
                "symbol": position.symbol.upper(),
                "side": position.side.value,
                "quantity": position.quantity,
                "market_value_fraction": position.market_value_fraction,
                "unrealized_return_fraction": position.unrealized_return_fraction,
                "sector": position.sector,
                "strategy_bucket": position.strategy_bucket,
            }
            for position in decision.positions
        ),
        key=lambda row: (row["symbol"], row["side"]),
    )
    return {
        "cycle_id": decision.cycle_id,
        "market": asdict(decision.market),
        "risk": asdict(decision.risk),
        "positions": positions,
        "signals": signals,
    }


def input_fingerprint(decision: CycleDecision) -> str:
    payload = json.dumps(
        _input_payload(decision),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _candidate_comparison(
    key: tuple[str, str],
    current: CandidateDecision | None,
    shadow: CandidateDecision | None,
    current_selected: set[str],
    shadow_selected: set[str],
    *,
    score_tolerance: float,
    size_tolerance: float,
) -> CandidateComparison:
    symbol, side_text = key
    divergences: list[DivergenceType] = []
    if current is None or shadow is None:
        divergences.append(DivergenceType.CANDIDATE_MISSING)
    else:
        if current.allowed != shadow.allowed:
            divergences.append(DivergenceType.ALLOWANCE)
        if current.terminal_reason != shadow.terminal_reason:
            divergences.append(DivergenceType.TERMINAL_REASON)
        if abs(current.final_score - shadow.final_score) > score_tolerance:
            divergences.append(DivergenceType.SCORE)
        if (
            abs(current.final_size_multiplier - shadow.final_size_multiplier)
            > size_tolerance
        ):
            divergences.append(DivergenceType.SIZE)

    current_is_selected = symbol in current_selected
    shadow_is_selected = symbol in shadow_selected
    if current_is_selected != shadow_is_selected:
        divergences.append(DivergenceType.SELECTION)
    if not divergences:
        divergences.append(DivergenceType.PARITY)

    return CandidateComparison(
        symbol=symbol,
        side=Side(side_text),
        current_present=current is not None,
        shadow_present=shadow is not None,
        current_allowed=None if current is None else current.allowed,
        shadow_allowed=None if shadow is None else shadow.allowed,
        current_selected=current_is_selected,
        shadow_selected=shadow_is_selected,
        current_terminal_reason="" if current is None else current.terminal_reason,
        shadow_terminal_reason="" if shadow is None else shadow.terminal_reason,
        current_final_score=None if current is None else current.final_score,
        shadow_final_score=None if shadow is None else shadow.final_score,
        current_size_multiplier=(
            None if current is None else current.final_size_multiplier
        ),
        shadow_size_multiplier=(
            None if shadow is None else shadow.final_size_multiplier
        ),
        divergences=tuple(divergences),
    )


def compare_cycles(
    current: CycleDecision,
    shadow: CycleDecision,
    *,
    score_tolerance: float = 1e-12,
    size_tolerance: float = 1e-12,
) -> CycleComparison:
    """Compare two decisions created from exactly the same input snapshot."""
    if current.cycle_id != shadow.cycle_id:
        raise ValueError(
            f"cycle mismatch: current={current.cycle_id!r}, shadow={shadow.cycle_id!r}"
        )
    current_fingerprint = input_fingerprint(current)
    shadow_fingerprint = input_fingerprint(shadow)
    if current_fingerprint != shadow_fingerprint:
        raise ValueError("input snapshot mismatch")

    current_map = {_candidate_key(candidate): candidate for candidate in current.candidates}
    shadow_map = {_candidate_key(candidate): candidate for candidate in shadow.candidates}
    keys = sorted(set(current_map) | set(shadow_map))

    current_selected = {symbol.upper() for symbol in current.selected_symbols}
    shadow_selected = {symbol.upper() for symbol in shadow.selected_symbols}
    comparisons = tuple(
        _candidate_comparison(
            key,
            current_map.get(key),
            shadow_map.get(key),
            current_selected,
            shadow_selected,
            score_tolerance=score_tolerance,
            size_tolerance=size_tolerance,
        )
        for key in keys
    )

    counts: dict[str, int] = {}
    for comparison in comparisons:
        for divergence in comparison.divergences:
            counts[divergence.value] = counts.get(divergence.value, 0) + 1

    parity = all(
        comparison.divergences == (DivergenceType.PARITY,)
        for comparison in comparisons
    )
    return CycleComparison(
        cycle_id=current.cycle_id,
        input_fingerprint=current_fingerprint,
        current_authority=current.authority,
        shadow_authority=shadow.authority,
        parity=parity,
        current_selected_symbols=tuple(sorted(current_selected)),
        shadow_selected_symbols=tuple(sorted(shadow_selected)),
        selected_only_by_current=tuple(sorted(current_selected - shadow_selected)),
        selected_only_by_shadow=tuple(sorted(shadow_selected - current_selected)),
        candidate_comparisons=comparisons,
        divergence_counts=tuple(sorted(counts.items())),
    )
