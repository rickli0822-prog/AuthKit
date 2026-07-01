# Contributing to AuthKit

AuthKit is a Windows-first diagnostic and repair utility for AI client login
problems. The project values field evidence, privacy-safe reports, and small
auditable fixes over broad generic networking features.

## What To Contribute First

Good first contributions usually fall into one of these areas:

- Improve diagnosis accuracy for Codex, Claude Code, Gemini, Cursor, or VS Code.
- Add privacy-safe field samples under `docs/field_samples/`.
- Improve support bundle validation, redaction, or documentation.
- Improve Windows GUI clarity without changing diagnosis or repair behavior.
- Add tests for edge cases found by real FDE field usage.

Avoid broad rewrites or passive "network toolbox" features unless they directly
support the login diagnosis and repair workflow.

## Development Setup

Requirements:

- Windows 10/11.
- Python 3.10 or newer.
- PowerShell.

```powershell
git clone https://github.com/rickli0822-prog/AuthKit.git
cd AuthKit
python -m pip install -e ".[dev]"
python -m pytest -q
```

For release-gate checks:

```powershell
python -m pip install pyinstaller
python scripts\release_smoke.py
```

For Windows installer artifacts:

```powershell
python scripts\build_windows_installer.py
```

The setup executable requires Inno Setup 6. Without `ISCC.exe`, the script still
builds the PyInstaller GUI/CLI artifacts and portable zip.

## Issue Reports

Use the issue templates whenever possible. A useful report includes:

- Target client: Codex, Claude Code, Gemini, Cursor, or VS Code.
- AuthKit version and whether you used the installer, portable zip, or source.
- Windows version.
- What failed: login, token exchange, OAuth callback, proxy, CA, firewall, DNS,
  or another step.
- A redacted support bundle when possible:

```powershell
authkit bundle --client codex --out .\authkit-support-bundle.json --fast
```

Do not paste raw tokens, cookies, authorization headers, emails, hostnames, or
customer-identifying paths. Support bundle export redacts common secrets by
default, but you should still review it before posting.

## Pull Requests

Before opening a PR:

1. Keep the change focused.
2. Add or update tests for changed behavior.
3. Preserve repair audit, rollback, and privacy boundaries.
4. Update docs when user-facing behavior changes.
5. Run the relevant checks:

```powershell
python -m pytest -q
python scripts\foundation_audit.py
```

Run the full release smoke when touching packaging, entry points, support
bundles, repair audit, GUI startup, i18n resources, or installer logic:

```powershell
python scripts\release_smoke.py
```

## Safety Rules

- Diagnostic commands should be read-only by default.
- System-changing repair commands must require explicit user action.
- Repair actions must write audit records when they mutate state.
- Rollback must rely on AuthKit audit snapshots, not guessed system state.
- Credential checks may report presence and metadata, never secret values.
- Support bundles must preserve the low-privacy metadata boundary documented in
  `docs/SUPPORT_BUNDLE.md`.

## Code Style

- Keep identifiers and commands in English.
- User-facing strings should be locale-aware where the surrounding code already
  supports i18n.
- Prefer small, testable functions over one-off procedural branches.
- Use existing modules first: `authkit.clients`, `authkit.repair`,
  `authkit.platform`, `authkit.core`, and `authkit.ui`.

## License

By contributing, you agree that your contribution will be licensed under the MIT
License used by this repository.
