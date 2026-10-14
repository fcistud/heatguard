"""Identity store schema — Confidential.

Operator-managed principals only. This package holds **no worker personal
data** (no age, weight, height, comorbidity, worker_id, or crew_id).
"""

from .schema import (
    FORBIDDEN_IDENTITY_COLUMNS,
    IDENTITY_SIZE_CEILING_BYTES,
    SCHEMA_VERSION,
    VOLATILE_STATE_COLUMNS,
    IdentityDuplicateError,
    IdentityError,
    IdentityRoleError,
    IdentitySchemaError,
    IdentitySitesError,
    assert_schema_compatible,
    canonicalize_sites,
    initialize,
    insert_user,
    load_seed_document,
    parse_sites,
    read_schema_version,
    seed_users,
    write_seeded_database,
)

__all__ = [
    "FORBIDDEN_IDENTITY_COLUMNS",
    "IDENTITY_SIZE_CEILING_BYTES",
    "SCHEMA_VERSION",
    "VOLATILE_STATE_COLUMNS",
    "IdentityDuplicateError",
    "IdentityError",
    "IdentityRoleError",
    "IdentitySchemaError",
    "IdentitySitesError",
    "assert_schema_compatible",
    "canonicalize_sites",
    "initialize",
    "insert_user",
    "load_seed_document",
    "parse_sites",
    "read_schema_version",
    "seed_users",
    "write_seeded_database",
]
