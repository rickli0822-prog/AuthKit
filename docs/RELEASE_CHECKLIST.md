# AuthKit Release Checklist

AuthKit is a field utility for FDE engineers, so a release is not ready only
because unit tests pass. The installed package must also expose the same user
entry points and runtime assets that the source tree uses.

## Required Smoke Gate

Run this before handing a build to field users:

```powershell
python scripts\release_smoke.py
```

The smoke gate verifies:

- Python source compilation for `src` and `scripts`.
- Full pytest regression suite.
- Foundation readiness wiring through `scripts/foundation_audit.py`.
- Wheel build through `pip wheel`.
- Installation into a temporary virtual environment.
- Installed console scripts: `authkit`, `authkit-gui`, and `authkit-shortcut`.
- Runtime package assets: i18n JSON files and the GUI `.ico` icon.
- Importability of the package-level shortcut module.
- Basic installed CLI startup through `authkit --help`.
- Installed support-bundle sample generation and validation through
  `authkit bundle --sample` and `authkit bundle --validate`.
- Installed shortcut planning through `authkit-shortcut --dry-run`, without
  creating real desktop or Start Menu `.lnk` files.
- Installed GUI startup through `authkit-gui --smoke`, verifying that the Tk
  window can be created and packaged GUI icons are available.
- Windows installer tool readiness through
  `python scripts\build_windows_installer.py --check-only`.
- Non-mutating low-risk repair drill through `scripts/field_repair_drill.py`,
  covering repair execution, audit JSONL write, support bundle export, and
  support bundle validation.
- Sanitized field sample regression through
  `scripts/field_sample_regression.py`, validating `docs/field_samples/*.json`
  and their expected diagnosis/repair outcomes.

If a full pytest run has already been captured in the same release job, the
install/package checks can be run without repeating tests:

```powershell
python scripts\release_smoke.py --skip-tests
```

Do not use `--skip-tests` for a manual field handoff unless there is a nearby
record of the full test run.

The GitHub Actions release-smoke job sets `AUTHKIT_SKIP_GUI_SMOKE=1` because
hosted Windows runners are not a reliable interactive desktop environment.
Manual release handoff must not set this variable; local release verification
should keep `authkit-gui --smoke` enabled.

## Manual Checks Still Needed

The smoke gate is intentionally non-mutating. It does not create desktop
shortcuts, write to the user's real repair audit location, flush DNS, reset
Winsock, or change proxy settings.

The field repair drill writes only to a temporary `LOCALAPPDATA` directory and
patches the DNS command runner in-process, so it validates the AuthKit repair
handoff path without changing the real machine DNS cache.

Before a public handoff, still verify:

- GUI opens in the target Windows environment.
- The first-screen layout has no clipping at the target display scaling.
- `authkit bundle --client codex --out .\authkit-support-bundle.json --fast`
  writes a redacted support bundle.
- Any repair command intended for the handoff has been reviewed for risk,
  admin requirement, rollback support, and audit output.
- Windows release artifacts build with
  `python scripts\build_windows_installer.py`; this creates a portable zip and
  creates `AuthKit_Setup_<version>.exe` when Inno Setup is installed.
