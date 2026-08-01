"""Assert installed package versions satisfy pyproject pinning policy."""
from __future__ import annotations

from importlib.metadata import version

from packaging.specifiers import SpecifierSet


def _v(name: str) -> str:
    return version(name)


def test_numpy_exact_pin():
    assert _v("numpy") == "1.26.4"


def test_api_stack_within_declared_ranges():
    assert SpecifierSet(">=0.141.0,<0.142.0").contains(_v("fastapi"))
    assert SpecifierSet(">=0.52.0,<0.53.0").contains(_v("uvicorn"))
    assert SpecifierSet(">=1.3.0,<1.4.0").contains(_v("starlette"))


def test_science_pins():
    assert _v("pythermalcomfort") == "4.0.1"
    assert _v("thermofeel") == "2.2.0"
