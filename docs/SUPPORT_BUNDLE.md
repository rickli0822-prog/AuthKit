# AuthKit Support Bundle

AuthKit support bundles are the field handoff artifact for FDE engineers. They combine a diagnosis snapshot with recent repair audit records so the next support person can see what was checked, what was changed, and whether rollback is available.

## Recommended Commands

Fast field collection:

```powershell
authkit bundle --client codex --out .\authkit-support-bundle.json --fast
```

Deep collection when time allows:

```powershell
authkit bundle --client codex --out .\authkit-support-bundle.json
```

Include fewer audit records:

```powershell
authkit bundle --client codex --out .\authkit-support-bundle.json --audit-limit 5 --fast
```

Generate a redacted sample bundle without diagnosing the current machine:

```powershell
authkit bundle --sample --client codex --out .\authkit-support-bundle.sample.json
```

Validate a bundle before attaching it to a ticket:

```powershell
authkit bundle --validate .\authkit-support-bundle.json
```

Export recent repair audit records only:

```powershell
authkit audit --json --limit 20
```

`authkit audit` and `authkit audit --json` are redacted by default. Use `authkit audit --raw` or `authkit audit --json --raw` only for local troubleshooting when the output will not be attached to a support ticket.

## Bundle Shape

Top-level fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Bundle schema version. Current value is `1`. |
| `kind` | Always `authkit_support_bundle`. |
| `client` | Target AI client, such as `codex`, `claude`, or `gemini`. |
| `metadata` | Low-privacy generation context. |
| `privacy` | Redaction rules applied during export. |
| `diagnosis` | Redacted `DiagnosisReport` snapshot. |
| `repair_audit` | Redacted recent repair audit records, newest first. |

`metadata` intentionally contains only low-privacy fields:

| Field | Meaning |
| --- | --- |
| `bundle_id` | Random non-identifying ID for this exported bundle. |
| `generated_at_utc` | UTC export time. |
| `authkit_version` | AuthKit version. |
| `client` | Target client. |
| `locale` | Report locale used during diagnosis. |
| `audit_limit` | Maximum audit records included. |
| `audit_records_included` | Actual number of repair audit records included. |
| `fast` | Whether the bundle used the bounded fast diagnosis path. |
| `diagnosis_status` | Diagnosis status copied from the exported report. |
| `diagnosis_case` | Diagnosis case copied from the exported report. |
| `platform` | Python platform string. |
| `python_version` | Python runtime version. |

Do not add hostname, username, raw tokens, passwords, cookies, or OAuth secret values to bundle metadata.

Each `repair_audit` item also carries low-privacy record metadata:

| Field | Meaning |
| --- | --- |
| `schema_version` | Repair audit record schema version. Current value is `1`. |
| `authkit_version` | AuthKit version that wrote the audit record. |
| `platform` | Python platform string for the machine that wrote the record. |

These fields must remain non-identifying. Do not add hostname or username to repair audit records.

## Privacy Boundary

Bundle export redacts by default:

- Secret-like values such as access tokens, refresh tokens, API keys, authorization values, passwords, cookies, and generic secrets become `<redacted>`.
- URL credentials are removed, for example `http://user:pass@127.0.0.1:7890` becomes `http://<redacted>@127.0.0.1:7890`.
- Current user profile paths are normalized to `%USERPROFILE%`, `%APPDATA%`, or `%LOCALAPPDATA%`, using case-insensitive matching for Windows path variants.

Presence booleans such as `access_token_present` remain visible because they are diagnostic evidence, not secrets.

The same default redaction rules apply to `authkit audit` and `authkit audit --json`. Raw audit output requires the explicit `--raw` flag.

## Field Use

Use `--fast` when the customer machine has unstable network access, limited maintenance windows, or when the FDE needs a quick evidence handoff. Use the default deep path when reproducing a complex issue and time is available.

If a repair was applied, attach the bundle after the repair attempt so `repair_audit` includes the action, status, safety metadata, and rollback marker.

Bundle files are written through a same-directory temporary file, flushed and fsynced, then atomically replaced. If export is interrupted, the previous complete bundle is preserved instead of being replaced by partial JSON.

`authkit bundle --validate <file>` is read-only. It checks the top-level schema,
metadata privacy boundary, diagnosis shape, repair audit shape, URL credential
leaks, and forbidden identifying keys such as `hostname` or `username`.

Before rolling back a repair, run:

```powershell
authkit rollback --preview
```

This is read-only and shows the latest rollbackable repair target, changed keys, and safety metadata before `authkit rollback --apply` mutates the machine.
