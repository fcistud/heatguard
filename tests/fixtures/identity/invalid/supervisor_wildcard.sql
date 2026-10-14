-- Synthetic invalid identity object: supervisor with wildcard site scope.
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

INSERT INTO schema_meta(key, value) VALUES ('schema_version', '1');

INSERT INTO users (
    username, password_hash, salt, kdf_params, role, sites,
    token_version, active, created_at_utc, updated_at_utc
) VALUES (
    'syn.supervisor.wildcard',
    '$argon2id$v=19$m=8,t=1,p=1$UkVEQUNUX1RFU1RfU0FMVA$UkVEQUNUX1RFU1RfSEFTSA',
    'REDACT_TEST_SALT',
    '{"m":8,"p":1,"t":1}',
    'supervisor',
    '["*"]',
    1, 1, '2024-01-01T00:00:00Z', '2024-01-01T00:00:00Z'
);
