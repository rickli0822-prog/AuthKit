# AuthKit v0.4.0

AuthKit v0.4.0 is the first public Windows release for diagnosing AI client
login failures.

Use it when Codex, Claude Code, Gemini, Cursor, or VS Code AI login fails on a
Windows machine and you need local evidence instead of guesswork.

## Download

- [AuthKit_Setup_0.4.0.exe](https://github.com/rickli0822-prog/AuthKit/releases/download/v0.4.0/AuthKit_Setup_0.4.0.exe) - recommended installer for field users.
- [AuthKit-0.4.0-windows-portable.zip](https://github.com/rickli0822-prog/AuthKit/releases/download/v0.4.0/AuthKit-0.4.0-windows-portable.zip) - portable GUI and CLI build.

## What This Release Solves

- Checks AI client installation and local login evidence.
- Detects proxy mismatch between environment variables and Windows system proxy.
- Checks OAuth callback and localhost readiness.
- Tests AI endpoint reachability with bounded network diagnostics.
- Generates redacted support bundles for field handoff.
- Records repair audit entries for explicit repair actions.
- Supports rollback preview and rollback for supported audited repairs.

Full diagnostic coverage currently targets Codex, Claude Code, and Gemini.
Cursor and VS Code are included as partial clients where local login evidence is
available.

## Safety Boundary

- The installer only installs AuthKit files and shortcuts.
- AuthKit does not upload support bundles automatically.
- AuthKit does not print access tokens, refresh tokens, cookies, passwords, or API keys.
- Repairs are explicit actions and write local audit records.
- System-level repairs are not silently executed during install.

## Quick Commands

```powershell
authkit gui
authkit check --client codex
authkit scan
authkit bundle --client codex --out .\authkit-support-bundle.json --fast
authkit bundle --validate .\authkit-support-bundle.json
```

## Validation

This release was validated with:

- `python scripts\release_smoke.py`
- `python scripts\build_windows_installer.py --require-inno`
- GitHub Actions CI on Python 3.10, 3.11, and 3.12
- Installed wheel entry point checks for `authkit`, `authkit-gui`, and `authkit-shortcut`
- Installed GUI smoke check
- Support bundle sample generation and validation

Latest CI: https://github.com/rickli0822-prog/AuthKit/actions

## SHA256

- `AuthKit_Setup_0.4.0.exe`: `7636711011CEF7324D85776BC2952C8DA9D824682C14139D468BAF3702C90B60`
- `AuthKit-0.4.0-windows-portable.zip`: `E0907D06B733DC076CD3790B1690BDED1AB12F19D19A7882CDBFBF8E8863946E`

## Feedback Wanted

The most useful feedback is a sanitized field support bundle from a real login
failure:

```powershell
authkit bundle --client codex --out .\authkit-support-bundle.json --fast
```

Open an issue and attach the redacted bundle only. Do not paste raw tokens,
cookies, OAuth codes, proxy passwords, or customer-identifying screenshots.
