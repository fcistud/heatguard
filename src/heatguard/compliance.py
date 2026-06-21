"""Tamper-evident protection record — worker-protective first, compliance shield second.

An append-only, SHA-256 hash-chained record of every WBGT reading, work-rest
call, drink prompt, water-availability attestation, and STOP. Any later edit or
deletion breaks the chain, so the export is cryptographically verifiable proof
that conditions were monitored and breaks/water were provided.

It is **dual-purpose**: it gives the *worker* an immutable record that they were
protected (their own heat-safety history, usable in a health or grievance claim),
and the *employer* a defence against heat-safety fines (e.g. AED 5,000/worker in
the UAE) and liability.

**Privacy by design** (see ``ComplianceLog.summary()['privacy']``): the log records
site CONDITIONS and protective ACTIONS, not individual surveillance — no location
trail, no biometrics, no continuous worker tracking. The only identifier is a
worker/crew id the operator controls and can pseudonymise.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass

from .types import Advisory

_GENESIS = "0" * 64


def _json_default(o):
    # Coerce stray numpy scalars (from the PHS/WBGT libs) to native types so the
    # hash chain is stable and the export is valid JSON.
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


def _canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def _hash(body: dict) -> str:
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LogRecord:
    seq: int
    timestamp: str       # ISO8601
    kind: str            # "advisory" | "wbgt_reading" | "break_called" | "drink_prompt" | "water_check" | "stop"
    payload: dict
    prev_hash: str
    record_hash: str

    def _body(self) -> dict:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "kind": self.kind,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
        }


class ComplianceLog:
    def __init__(self, site_name: str) -> None:
        self.site_name = site_name
        self.records: list[LogRecord] = []

    @property
    def head_hash(self) -> str:
        return self.records[-1].record_hash if self.records else _GENESIS

    def _add(self, timestamp_iso: str, kind: str, payload: dict) -> LogRecord:
        seq = len(self.records)
        body = {"seq": seq, "timestamp": timestamp_iso, "kind": kind, "payload": payload, "prev_hash": self.head_hash}
        rec = LogRecord(seq, timestamp_iso, kind, payload, self.head_hash, _hash(body))
        self.records.append(rec)
        return rec

    def append(self, advisory: Advisory, water_available: bool = True) -> LogRecord:
        """Log a full advisory plus the supervisor's water-availability attestation."""
        payload = advisory.to_dict()
        payload["water_available"] = bool(water_available)
        return self._add(advisory.timestamp.isoformat(), "advisory", payload)

    def append_event(self, timestamp_iso: str, kind: str, payload: dict) -> LogRecord:
        return self._add(timestamp_iso, kind, dict(payload))

    def verify_chain(self) -> bool:
        """Recompute every hash and linkage; False on any tampering."""
        prev = _GENESIS
        for i, rec in enumerate(self.records):
            if rec.seq != i or rec.prev_hash != prev:
                return False
            if _hash(rec._body()) != rec.record_hash:
                return False
            prev = rec.record_hash
        return True

    # ---- export -------------------------------------------------------------
    def export_jsonl(self) -> str:
        """One verifiable record per line (includes hashes)."""
        return "\n".join(_canonical(asdict(r)) for r in self.records)

    def export_csv(self) -> str:
        """Flat human-readable audit table (advisory rows)."""
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([
            "seq", "timestamp", "kind", "signal", "wbgt_c", "wbgt_source",
            "work_min", "rest_min", "cups_per_h", "water_available", "record_hash",
        ])
        for r in self.records:
            p = r.payload
            cyc = p.get("cycle", {})
            hyd = p.get("hydration", {})
            w.writerow([
                r.seq, r.timestamp, r.kind, p.get("signal", ""),
                p.get("wbgt_c", ""), p.get("wbgt_source", ""),
                cyc.get("work_min_per_hour", ""), cyc.get("rest_min_per_hour", ""),
                hyd.get("cups_250ml_per_h", ""), p.get("water_available", ""),
                r.record_hash,
            ])
        return buf.getvalue()

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for r in self.records:
            sig = r.payload.get("signal")
            if sig:
                counts[sig] = counts.get(sig, 0) + 1
        return {
            "site": self.site_name,
            "records": len(self.records),
            "head_hash": self.head_hash,
            "verified": self.verify_chain(),
            "signal_counts": counts,
            "purpose": "Worker-protection record + employer compliance evidence",
            "privacy": {
                "records": "site WBGT readings, called work-rest cycles, drink prompts, water availability — conditions and protective actions",
                "does_not_record": "no individual location trail, no biometrics, no continuous worker tracking",
                "identifier": "a worker/crew id the operator controls (pseudonymisable)",
            },
        }
