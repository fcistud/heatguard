"""Policy retrieval/extraction facade.

Canonical module name for the GCC/ILO compliance auditor.
Implementation remains in ``policy_rag`` for backward compatibility.
"""
from __future__ import annotations

from .policy_rag import _build_index
from .policy_rag import list_demo_questions
from .policy_rag import policy_index_status
from .policy_rag import query_policy
from .policy_rag import retrieve

__all__ = [
    "_build_index",
    "list_demo_questions",
    "policy_index_status",
    "query_policy",
    "retrieve",
]
