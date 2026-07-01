# AuthKit Foundation Readiness

AuthKit's foundation is considered field-ready when the repository can prove
these local utility contracts without mutating the user's real machine state.

## Verified Surfaces

| Surface | Evidence |
| --- | --- |
| CLI entry point | `authkit --help` inside a wheel-installed temporary venv |
| GUI entry point | `authkit-gui --smoke` creates and destroys a Tk window |
| Desktop entry planning | `authkit-shortcut --dry-run` resolves target, icon, and `.lnk` paths |
| Runtime package data | release smoke verifies i18n JSON and packaged GUI icons |
| Repair audit write path | `scripts/field_repair_drill.py` exercises `flush-dns-cache` through `apply_direct_repair()` |
| Support bundle export | `authkit bundle --sample --out <file>` writes a redacted sample bundle |
| Support bundle validation | `authkit bundle --validate <file>` checks schema and privacy boundaries |
| Field sample regression | `scripts/field_sample_regression.py` validates sanitized samples under `docs/field_samples/` |
| Installed wheel | `python scripts\release_smoke.py` builds and installs a wheel into a temporary venv |
| Windows release packaging | `python scripts\build_windows_installer.py --check-only` verifies packaging tools without mutating user settings |

## Required Gates

```powershell
python scripts\foundation_audit.py
python scripts\release_smoke.py
python scripts\build_windows_installer.py
```

`foundation_audit.py` checks that the repository still contains the required
gate files, sample directory, and release smoke command hooks. `release_smoke.py`
performs the heavier executable verification, while `build_windows_installer.py`
creates Windows release artifacts.

## Boundary

This readiness gate proves the software foundation: package entry points,
installed GUI startup, support handoff, repair auditability, and regression
fixtures. It does not claim broad real-world coverage until FDE-provided
sanitized support bundles are added under `docs/field_samples/`.
