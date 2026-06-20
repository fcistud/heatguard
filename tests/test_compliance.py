from __future__ import annotations

from dataclasses import replace

from heatguard.compliance import ComplianceLog
from heatguard.scheduler import schedule
from heatguard.types import MetabolicCategory as MC

from conftest import weather


def _log(riyadh, veteran, n=8):
    log = ComplianceLog("Site A")
    for h in range(6, 6 + n):
        av = schedule(weather(h, 30 + h, 30, sw=h * 80, direct=h * 60), riyadh, veteran, MC.HEAVY)
        log.append(av, water_available=True)
    return log


def test_chain_verifies(riyadh, veteran):
    log = _log(riyadh, veteran)
    assert len(log.records) == 8
    assert log.verify_chain() is True


def test_tamper_breaks_chain(riyadh, veteran):
    log = _log(riyadh, veteran)
    bad = log.records[3]
    log.records[3] = replace(bad, payload={**bad.payload, "wbgt_c": 1.0})
    assert log.verify_chain() is False


def test_deletion_breaks_chain(riyadh, veteran):
    log = _log(riyadh, veteran)
    del log.records[4]
    assert log.verify_chain() is False


def test_genesis_linkage(riyadh, veteran):
    log = _log(riyadh, veteran, n=1)
    assert log.records[0].prev_hash == "0" * 64


def test_exports(riyadh, veteran):
    log = _log(riyadh, veteran)
    jsonl = log.export_jsonl()
    assert len(jsonl.splitlines()) == 8
    csv = log.export_csv()
    assert "record_hash" in csv.splitlines()[0]
    assert log.summary()["verified"] is True
