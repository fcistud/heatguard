"""Tests for policy corpus RAG retrieval."""
from __future__ import annotations

from heatguard.policy_rag import (
    DEMO_QUESTIONS,
    list_demo_questions,
    query_policy,
    retrieve,
)


def test_demo_questions_non_empty():
    assert len(list_demo_questions()) >= 3


def test_uae_query_hits_uae_doc():
    hits = retrieve("When does the UAE midday work ban start in summer?", top_k=3)
    assert hits
    ids = {h.doc_id for h in hits}
    assert "uae_midday_ban" in ids or "gcc_ban_summary" in ids


def test_qatar_query_hits_qatar_or_summary():
    hits = retrieve("Qatar WBGT cutoff outdoor work", top_k=3)
    assert hits
    ids = {h.doc_id for h in hits}
    assert "qatar_wbgt_rule" in ids or "gcc_ban_summary" in ids


def test_ilo_query_hits_wrs_doc():
    hits = retrieve("Water Rest Shade kidney injury reduction", top_k=3)
    assert hits
    ids = {h.doc_id for h in hits}
    assert "ilo_wrs_excerpt" in ids


def test_query_policy_returns_cited_answer():
    ans = query_policy(DEMO_QUESTIONS[0], top_k=2)
    d = ans.to_dict()
    assert d["question"] == DEMO_QUESTIONS[0]
    assert d["sources"]
    assert "policy corpus" in d["answer"].lower()
    assert all("excerpt" in s and "title" in s for s in d["sources"])
