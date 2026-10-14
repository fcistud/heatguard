# Invalid identity-object fixtures (WO-020)

Synthetic, non-production artefacts used to prove
`scripts/validate_identity_object.py` fails on each invariant class.
**No real credentials.** Usernames are `syn.*` prefixes; hashes and
salts are dummy argon2id strings.

| File | Violation |
|---|---|
| `forbidden_column.sql` | `users.age` (worker personal data) |
| `volatile_column.sql` | `users.failed_login_count` (volatile auth state) |
| `altered_role_check.sql` | role CHECK includes extra `admin` |
| `supervisor_wildcard.sql` | supervisor with `sites = ["*"]` |
| `schema_version_mismatch.sql` | `schema_version = 99` |
| `multi_violation.sql` | forbidden + volatile + supervisor wildcard + version 99 |

Over-ceiling objects are not committed (they are ≥ 8 MiB). Build one with:

```bash
uv run python tests/fixtures/identity/invalid/generate.py --dest /tmp/identity-invalid
```

`generate.py` also materializes the SQL files above into small `.db`
files for a local deliberate-break drill. Never upload those files.
