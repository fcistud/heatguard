"""Leaf-adjacent API contract models (WO-012).

This package may import ``heatguard.types`` and pydantic only — never
``heatguard.service`` or ``heatguard.api``.
"""

from .legal_contract import (
    LEGAL_CONTRACT_INVENTORY,
    HourAdvisoryPayload,
    LegalEnvelope,
    TimelineResponse,
    TimelineRow,
)

__all__ = [
    "LEGAL_CONTRACT_INVENTORY",
    "HourAdvisoryPayload",
    "LegalEnvelope",
    "TimelineResponse",
    "TimelineRow",
]
