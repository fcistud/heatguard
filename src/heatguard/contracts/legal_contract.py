"""Pydantic models for the frozen legal contract (WO-012).

Field names match ``legal_precedence.operational_payload()`` and
``legal_precedence.legal_status()``. Authoritative prose:
``docs/SCOPE_GUARDRAIL.md`` section 8.

Models use ``extra='allow'`` so additive keys do not fail validation; omitting
a required legal field does. Attached to routes via OpenAPI ``responses``
only — never ``response_model``, which would re-serialize payloads.
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True, slots=True)
class LegalContractInventory:
    """Single field inventory reused by schema, runtime, and omit tests.

    Mirrors ``docs/SCOPE_GUARDRAIL.md`` section 8 plus ``scientific_live``
    and the legal envelope keys emitted by ``legal_status()``.
    """

    hour_fields: tuple[str, ...]
    legal_fields: tuple[str, ...]
    timeline_lanes: tuple[str, ...]


LEGAL_CONTRACT_INVENTORY = LegalContractInventory(
    hour_fields=(
        "scientific_advisory",
        "effective_advisory",
        "advisory",
        "legal",
        "live",
        "scientific_live",
    ),
    legal_fields=(
        "banned",
        "description",
        "precedence_applied",
        "scientific_vs_legal_conflict",
    ),
    timeline_lanes=(
        "veteran",
        "newcomer",
        "veteran_effective",
        "newcomer_effective",
    ),
)


class LegalEnvelope(BaseModel):
    """``legal`` object from ``legal_precedence.legal_status()``."""

    model_config = ConfigDict(extra="allow")

    banned: bool
    description: str
    precedence_applied: bool
    scientific_vs_legal_conflict: bool


class HourAdvisoryPayload(BaseModel):
    """Advisory-bearing hour / decide payload from ``operational_payload()``."""

    model_config = ConfigDict(extra="allow")

    scientific_advisory: dict[str, object]
    effective_advisory: dict[str, object]
    advisory: dict[str, object]
    legal: LegalEnvelope
    live: list[str]
    scientific_live: list[str]


class TimelineRow(BaseModel):
    """One hour row with scientific and operational lanes."""

    model_config = ConfigDict(extra="allow")

    veteran: dict[str, object]
    newcomer: dict[str, object]
    veteran_effective: dict[str, object]
    newcomer_effective: dict[str, object]
    legal: LegalEnvelope


class TimelineResponse(BaseModel):
    """Timeline wrapper; the row component is the contract, not this envelope."""

    model_config = ConfigDict(extra="allow")

    rows: list[TimelineRow]
