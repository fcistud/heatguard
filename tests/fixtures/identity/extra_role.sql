-- Identity fixture whose role CHECK lists an extra value (WO-016).
CREATE TABLE users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    kdf_params TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('supervisor', 'ohs_officer', 'compliance_officer', 'inspector', 'admin')),
    sites TEXT NOT NULL,
    token_version INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
