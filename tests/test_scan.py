from authkit.core import scan


def test_scan_installed_clients_uses_fast_mode(monkeypatch):
    monkeypatch.setattr(scan, "installed_clients", lambda: ["codex", "claude"])
    calls = []

    def fake_run_diagnosis(*, client, locale, fast):
        calls.append((client, locale, fast))
        return type("Report", (), {"client": client})()

    monkeypatch.setattr(scan, "run_diagnosis", fake_run_diagnosis)

    reports = scan.scan_installed_clients(locale="en", fast=True, max_workers=2)

    assert [report.client for report in reports] == ["codex", "claude"]
    assert calls == [("codex", "en", True), ("claude", "en", True)]


def test_scan_installed_clients_empty(monkeypatch):
    monkeypatch.setattr(scan, "installed_clients", lambda: [])

    assert scan.scan_installed_clients() == []


def test_scan_installed_clients_isolates_client_failures(monkeypatch):
    monkeypatch.setattr(scan, "installed_clients", lambda: ["codex", "claude"])

    def fake_run_diagnosis(*, client, locale, fast):
        if client == "codex":
            raise RuntimeError("boom")
        return type("Report", (), {"client": client})()

    monkeypatch.setattr(scan, "run_diagnosis", fake_run_diagnosis)

    reports = scan.scan_installed_clients(locale="en", fast=True, max_workers=2)

    assert [report.client for report in reports] == ["codex", "claude"]
    assert reports[0].status.value == "warning"
    assert reports[0].layers[0].name == "scan_error"
    assert reports[0].layers[0].details["error"] == "boom"
