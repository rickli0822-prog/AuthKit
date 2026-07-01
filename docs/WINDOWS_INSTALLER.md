# AuthKit Windows Installer

AuthKit can be shipped as a Python package for developers and as Windows
artifacts for field users who need a direct GUI entry point.

## Build

Run the non-mutating release gate first:

```powershell
python scripts\release_smoke.py
```

Then build Windows artifacts:

```powershell
python scripts\build_windows_installer.py
```

The script produces:

- `dist\windows\AuthKit\AuthKit.exe` for the GUI.
- `dist\windows\AuthKitCLI\AuthKitCLI.exe` for the CLI.
- `dist\windows\AuthKit-<version>-windows-portable.zip` for portable handoff.
- `dist\windows\AuthKit_Setup_<version>.exe` when Inno Setup's `ISCC.exe` is installed.

If Inno Setup is not installed, the script still writes
`build\windows-installer\AuthKit.iss`. Install Inno Setup 6 and rerun the
script to create the setup executable.

## Safety Boundary

The installer only installs AuthKit files and shortcuts. It must not run repair
actions during install. Proxy, DNS, Winsock, firewall, and CA changes remain
explicit GUI or CLI actions and continue to write repair audit records.

## Release Gate

Before attaching installer artifacts to a public GitHub release, verify:

```powershell
python scripts\release_smoke.py
python scripts\build_windows_installer.py --check-only
python scripts\build_windows_installer.py
```

When `ISCC.exe` is unavailable on the build machine, publish the portable zip
and the source/wheel release first, then build the setup executable from a
machine with Inno Setup installed.
