-- Synthetic invalid identity object: schema_version does not match code.
CREATE TABLE users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    kdf_params TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('supervisor', 'ohs_officer', 'compliance_officer', 'inspector')),
    sites TEXT NOT NULL,
    token_version INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO schema_meta(key, value) VALUES ('schema_version', '99');
