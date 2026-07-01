from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import platform

from authkit import __version__
from authkit.clients import installed_clients
from authkit.core.diagnose import run_diagnosis
from authkit.models import DiagnosisReport, FailureCase, HealthStatus, LayerResult


def scan_installed_clients(*, locale: str = "zh", fast: bool = True, max_workers: int = 4) -> list[DiagnosisReport]:
    clients = installed_clients()
    if not clients:
        return []
    workers = max(1, min(max_workers, len(clients)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            client: executor.submit(run_diagnosis, client=client, locale=locale, fast=fast)
            for client in clients
        }
        reports: list[DiagnosisReport] = []
        for client in clients:
            try:
                reports.append(futures[client].result())
            except Exception as exc:  # noqa: BLE001 - one broken client must not break the whole scan
                reports.append(_scan_error_report(client, exc, locale=locale))
        return reports


def _scan_error_report(client: str, exc: Exception, *, locale: str) -> DiagnosisReport:
    if locale == "en":
        root_cause = f"{client} scan failed before diagnosis completed."
        summary = f"Scan failed: {exc}"
        browser_explanation = "This is an AuthKit scan isolation error; other installed clients were still checked."
    else:
        root_cause = f"{client} 扫描在完成诊断前失败。"
        summary = f"扫描失败: {exc}"
        browser_explanation = "这是 AuthKit 扫描隔离错误；其他已安装客户端仍会继续检查。"
    return DiagnosisReport(
        tool_version=__version__,
        platform=platform.platform(),
        client=client,
        status=HealthStatus.WARNING,
        case=FailureCase.UNKNOWN,
        root_cause=root_cause,
        confidence="low",
        browser_explanation=browser_explanation,
        layers=[
            LayerResult(
                name="scan_error",
                ok=False,
                summary=summary,
                details={"error": str(exc), "type": type(exc).__name__},
            )
        ],
        notes=[summary],
    )
