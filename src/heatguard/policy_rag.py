"""Policy-gap RAG — retrieve GCC heat-work regulations and ILO guidance.

Uses TF-IDF retrieval over the committed ``data/policy/`` corpus (no external
LLM API). Answers are **extractive** summaries of the top matching excerpts
with explicit source citations — suitable for demo and audit.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np
import importlib
try:
    sklearn_text = importlib.import_module("sklearn.feature_extraction.text")
    TfidfVectorizer = getattr(sklearn_text, "TfidfVectorizer")
    sklearn_metrics = importlib.import_module("sklearn.metrics.pairwise")
    cosine_similarity = getattr(sklearn_metrics, "cosine_similarity")
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

from .datasets import load_policy_corpus

DEMO_QUESTIONS: tuple[str, ...] = (
    "When does the UAE midday ban start, and does it cover May heat?",
    "How is Qatar's WBGT rule different from other GCC states?",
    "What evidence supports Water-Rest-Shade for outdoor workers?",
    "What are the limits of calendar-based midday bans in the Gulf?",
)


@dataclass(frozen=True, slots=True)
class PolicyChunk:
    doc_id: str
    title: str
    path: str
    text: str
    chunk_index: int


@dataclass(frozen=True, slots=True)
class PolicyHit:
    doc_id: str
    title: str
    path: str
    excerpt: str
    score: float
    chunk_index: int


@dataclass(frozen=True, slots=True)
class PolicyAnswer:
    question: str
    answer: str
    sources: list[PolicyHit]
    method: str = "tfidf-retrieval"
    degraded: bool = False
    degraded_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "method": self.method,
            "sources": [asdict(s) for s in self.sources],
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
        }


def _normalise(text: str) -> str:
    text = re.sub(r"[#*`_\[\]]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _chunk_document(doc_id: str, title: str, path: str, text: str) -> list[PolicyChunk]:
    """Split markdown into paragraph-scale chunks for retrieval."""
    raw_parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[PolicyChunk] = []
    buf: list[str] = []
    buf_len = 0
    idx = 0

    def flush() -> None:
        nonlocal idx, buf, buf_len
        if not buf:
            return
        body = "\n\n".join(buf)
        chunks.append(PolicyChunk(doc_id, title, path, body, idx))
        idx += 1
        buf, buf_len = [], 0

    for part in raw_parts:
        if buf_len + len(part) > 900 and buf:
            flush()
        buf.append(part)
        buf_len += len(part)
    flush()
    return chunks


@dataclass
class _Index:
    chunks: list[PolicyChunk]
    vectorizer: TfidfVectorizer
    matrix: np.ndarray


@lru_cache(maxsize=1)
def _build_index() -> _Index:
    corpus = load_policy_corpus()
    chunks: list[PolicyChunk] = []
    for doc in corpus:
        chunks.extend(_chunk_document(doc["id"], doc["title"], doc["path"], doc["text"]))
    if not chunks:
        raise FileNotFoundError("Policy corpus empty — add markdown files under data/policy/")

    texts = [_normalise(c.text) for c in chunks]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform(texts)
    return _Index(chunks=chunks, vectorizer=vectorizer, matrix=matrix)


def retrieve(question: str, top_k: int = 3) -> list[PolicyHit]:
    """Return the top ``top_k`` policy excerpts for a natural-language question."""
    from .observability.tracing import ATTR_ROWS, set_attrs, span

    with span("policy.retrieve") as sp:
        available, reason = policy_index_status()
        if not available:
            _report_policy_unavailable(reason or "unavailable")
            set_attrs(sp, **{ATTR_ROWS: 0})
            return []

        idx = _build_index()
        k = max(1, min(top_k, len(idx.chunks)))
        q = idx.vectorizer.transform([_normalise(question)])
        scores = cosine_similarity(q, idx.matrix).ravel()
        order = np.argsort(scores)[::-1][:k]
        hits: list[PolicyHit] = []
        for i in order:
            score = float(scores[i])
            if score <= 0.0:
                continue
            c = idx.chunks[int(i)]
            excerpt = c.text if len(c.text) <= 480 else c.text[:477] + "…"
            hits.append(
                PolicyHit(
                    doc_id=c.doc_id,
                    title=c.title,
                    path=c.path,
                    excerpt=excerpt,
                    score=round(score, 4),
                    chunk_index=c.chunk_index,
                )
            )
        set_attrs(sp, **{ATTR_ROWS: len(hits)})
        return hits


def policy_index_status() -> tuple[bool, str | None]:
    """Return ``(available, reason)`` for the policy index."""
    if not _HAS_SKLEARN:
        return False, "sklearn missing"
    try:
        idx = _build_index()
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    if not idx.chunks:
        return False, "empty corpus"
    return True, None


def _report_policy_unavailable(reason: str) -> None:
    from .observability import degradation as deg
    from .observability.metrics import observe_degraded_condition

    deg.report_degraded(
        deg.POLICY_INDEX_UNAVAILABLE,
        detail=reason,
        once_key=f"policy.index_unavailable:{reason}",
        log_event=deg.POLICY_INDEX_UNAVAILABLE_EVENT,
        log_fields={"reason": reason},
        increment_metric=lambda: observe_degraded_condition(
            reason_code=deg.POLICY_INDEX_UNAVAILABLE
        ),
    )


def _synthesize(question: str, hits: list[PolicyHit], *, degraded: bool = False) -> str:
    if degraded:
        return (
            "Policy index unavailable — HeatGuard cannot retrieve regulatory excerpts "
            "in this process (missing scikit-learn or empty corpus). "
            "Deterministic WBGT scheduling remains available."
        )
    if not hits:
        return (
            "No matching excerpts in the committed policy corpus. "
            "Try a question about GCC midday bans, Qatar WBGT, or ILO Water-Rest-Shade."
        )
    lines = [
        "Retrieved from the HeatGuard policy corpus (curated GCC regulations + ILO WRS summary):",
        "",
    ]
    for n, h in enumerate(hits, 1):
        lines.append(f"{n}. {h.title} — {h.excerpt}")
    lines.extend([
        "",
        f"Question: {question}",
        "",
        "HeatGuard compares these fixed rules against live WBGT scheduling — see the timeline "
        "for hours where adaptive protection applies but the calendar ban does not.",
    ])
    return "\n".join(lines)


def query_policy(question: str, top_k: int = 3) -> PolicyAnswer:
    """Answer a policy question via retrieval + cited extractive synthesis."""
    from .observability import POLICY_QUERY, get_logger

    available, reason = policy_index_status()
    if not available:
        _report_policy_unavailable(reason or "unavailable")
        get_logger(__name__).info(POLICY_QUERY, top_k=top_k, hit_count=0, degraded=True)
        return PolicyAnswer(
            question=question,
            answer=_synthesize(question, [], degraded=True),
            sources=[],
            method="unavailable",
            degraded=True,
            degraded_reason=reason,
        )

    hits = retrieve(question, top_k=top_k)
    get_logger(__name__).info(
        POLICY_QUERY,
        top_k=top_k,
        hit_count=len(hits),
    )
    return PolicyAnswer(
        question=question,
        answer=_synthesize(question, hits),
        sources=hits,
    )


def list_demo_questions() -> list[str]:
    return list(DEMO_QUESTIONS)
