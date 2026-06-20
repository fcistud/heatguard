"""Load demo sites from ``data/locales.json`` into ``Site`` objects."""
from __future__ import annotations

import json
from functools import lru_cache

from ._paths import data_file
from .types import Site


@lru_cache(maxsize=1)
def load_sites() -> dict[str, Site]:
    raw = json.loads(data_file("locales.json").read_text())
    return {key: Site(**val) for key, val in raw.items()}


def get_site(key: str) -> Site:
    sites = load_sites()
    if key not in sites:
        raise KeyError(f"Unknown site '{key}'. Known: {', '.join(sorted(sites))}")
    return sites[key]
