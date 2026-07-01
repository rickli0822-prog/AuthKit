# Field Sample Regression

Field samples are sanitized AuthKit support bundles used to keep diagnosis,
repair audit, and handoff contracts stable across releases.

## Run

```powershell
python scripts\field_sample_regression.py
```

The runner scans `docs/field_samples/*.json`, validates every file with the
support bundle validator, then checks each sample's `metadata.expected` block.

## Sample Contract

Each sample must be a redacted support bundle and must include:

- `privacy.redaction_applied: true`
- no `hostname` or `username`
- no URL credentials
- `metadata.expected.client`
- `metadata.expected.diagnosis_status`
- `metadata.expected.diagnosis_case`
- optional `metadata.expected.repair_fix_id`

Do not place raw customer bundles in this directory. Redact first, then add only
the minimum expected fields needed to protect the behavior being covered.
