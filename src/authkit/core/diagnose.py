from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import platform
from typing import Callable

from authkit import __version__
from authkit.clients import FULL_DIAGNOSTIC_CLIENTS
from authkit.checks.client import check_client
from authkit.models import (
    DiagnosisReport,
    FailureCase,
    FixAction,
    HealthStatus,
    LayerResult,
    OfficialGuidance,
    ProxyEndpoint,
)
from authkit.checks.login import check_login_status
from authkit.checks.network import (
    CALLBACK_PORTS,
    analyze_callback_ports,
    http_probe,
    probe_chatgpt_api,
    probe_oauth_token,
    summarize_port,
    tcp_probe,
)
from authkit.checks.network_profile import collect_network_profile
from authkit.platform.proxy import (
    format_env_snapshot,
    primary_env_proxy,
    read_env_proxy,
    read_system_proxy,
)


DEFAULT_NO_PROXY = "127.0.0.1,localhost,::1"
ProgressCallback = Callable[[dict[str, str]], None]


def _emit_progress(progress: ProgressCallback | None, name: str, state: str, summary: str) -> None:
    if progress:
        progress({"name": name, "state": state, "summary": summary})


def _progress_text(locale: str, key: str, **kwargs: object) -> str:
    texts = {
        "zh": {
            "system_proxy_running": "正在读取 Windows 系统代理并测试代理端口...",
            "env_proxy_running": "正在读取用户/进程环境变量代理并测试端口...",
            "oauth_running": "正在探测 {client} OAuth/API 端点连通性...",
            "network_profile_running": "正在识别当前出口 IP、地理信息、风险与网络质量评分...",
            "callback_running": "正在检查本地 OAuth 回调端口 1455/1457...",
            "login_running": "正在检查 {client} 本地登录凭据...",
            "online_session_running": "正在汇总在线模式：公网出口、服务端点与本地登录凭据闭环...",
            "client_running": "正在检查 {client} 本地安装、配置、版本与凭据信息...",
            "finalize_running": "正在汇总根因、置信度与官方修复路径...",
            "finalize_done": "已完成根因分析与修复建议生成。",
        },
        "en": {
            "system_proxy_running": "Reading Windows system proxy and testing the proxy port...",
            "env_proxy_running": "Reading user/process proxy environment variables and testing ports...",
            "oauth_running": "Probing {client} OAuth/API endpoint connectivity...",
            "network_profile_running": "Checking current exit IP, geo, risk, and network quality score...",
            "callback_running": "Checking local OAuth callback ports 1455/1457...",
            "login_running": "Checking local {client} sign-in credentials...",
            "online_session_running": "Summarizing online mode: exit network, service endpoints, and local credentials...",
            "client_running": "Checking local {client} install, settings, version, and credentials...",
            "finalize_running": "Summarizing root cause, confidence, and official recovery path...",
            "finalize_done": "Root cause analysis and fix guidance are complete.",
        },
    }
    template = texts.get(locale, texts["zh"]).get(key, key)
    return template.format(**kwargs)


def run_diagnosis(
    client: str = "codex",
    *,
    locale: str = "zh",
    fast: bool = False,
    progress: ProgressCallback | None = None,
) -> DiagnosisReport:
    _emit_progress(progress, "system_proxy", "running", _progress_text(locale, "system_proxy_running"))
    system = read_system_proxy()
    env = read_env_proxy("user")
    process_env = read_env_proxy("process")
    system_endpoint: ProxyEndpoint = system["endpoint"]  # type: ignore[assignment]
    env_endpoint = primary_env_proxy(env)
    process_endpoint = primary_env_proxy(process_env)

    layers: list[LayerResult] = []
    fixes: list[FixAction] = []
    notes: list[str] = []

    tcp_timeout = 0.6 if fast else 1.5
    http_timeout = 3.0 if fast else 12.0
    port_timeout = 3 if fast else 8

    system_alive = system_endpoint.is_set and tcp_probe(system_endpoint.host, system_endpoint.port, timeout=tcp_timeout)
    env_alive = env_endpoint.is_set and tcp_probe(env_endpoint.host, env_endpoint.port, timeout=tcp_timeout)
    process_alive = process_endpoint.is_set and tcp_probe(process_endpoint.host, process_endpoint.port, timeout=tcp_timeout)

    system_layer = LayerResult(
        name="system_proxy",
        ok=not system_endpoint.is_set or system_alive,
        summary=(
            _text(locale, "system_proxy", url=system_endpoint.url or _text(locale, "not_enabled"))
            + (_text(locale, "port_reachable") if system_alive else _text(locale, "port_unreachable_or_unset"))
        ),
        details={
            "enabled": system["enabled"],
            "server": system["server"],
            "endpoint": system_endpoint.to_dict(),
            "override": system["override"],
            "bypass_localhost": system["bypass_localhost"],
            "port_alive": system_alive,
        },
    )
    layers.append(system_layer)
    _emit_progress(progress, system_layer.name, "done", system_layer.summary)

    _emit_progress(progress, "env_proxy", "running", _progress_text(locale, "env_proxy_running"))
    env_layer = LayerResult(
        name="env_proxy",
        ok=not env_endpoint.is_set or env_alive,
        summary=(
            _text(locale, "user_env_proxy", url=env_endpoint.url or _text(locale, "not_set"))
            + (_text(locale, "port_reachable") if env_alive else _text(locale, "port_unreachable_or_unset"))
        ),
        details={
            "user_env": format_env_snapshot(env),
            "process_env": format_env_snapshot(process_env),
            "primary_endpoint": env_endpoint.to_dict(),
            "port_alive": env_alive,
            "process_port_alive": process_alive,
        },
    )
    layers.append(env_layer)
    _emit_progress(progress, env_layer.name, "done", env_layer.summary)

    _emit_progress(progress, "oauth_endpoints", "running", _progress_text(locale, "oauth_running", client=client))
    endpoint_probes = _run_endpoint_probes(
        client=client,
        env_endpoint=env_endpoint,
        system_endpoint=system_endpoint,
        timeout=http_timeout,
    )
    oauth_via_env = endpoint_probes["oauth_via_env"]
    oauth_via_system = endpoint_probes["oauth_via_system"]
    oauth_direct = endpoint_probes["oauth_direct"]
    api_via_env = endpoint_probes["api_via_env"]
    api_via_system = endpoint_probes["api_via_system"]

    oauth_layer = LayerResult(
        name="oauth_endpoints",
        ok=oauth_via_env["ok"] or oauth_via_system["ok"] or oauth_direct["ok"],
        summary=_text(locale, _endpoint_summary_key(client)),
        details={
            "auth_via_env": oauth_via_env,
            "auth_via_system": oauth_via_system,
            "auth_direct": oauth_direct,
            "api_via_env": api_via_env,
            "api_via_system": api_via_system,
        },
    )
    layers.append(oauth_layer)
    _emit_progress(progress, oauth_layer.name, "done", oauth_layer.summary)

    _emit_progress(progress, "network_profile", "running", _progress_text(locale, "network_profile_running"))
    network_profile = collect_network_profile(
        client=client,
        env_endpoint=env_endpoint,
        system_endpoint=system_endpoint,
        endpoint_probes=endpoint_probes,
        timeout=1.6 if fast else 2.5,
    )
    network_layer = LayerResult(
        name="network_profile",
        ok=network_profile["score"] >= 60,
        summary=_text(
            locale,
            "network_profile_summary",
            score=network_profile["score"],
            quality=_text(locale, f"network_quality_{network_profile['quality']}"),
            ip=network_profile.get("public_ip") or _text(locale, "unknown_value"),
        ),
        details=network_profile,
    )
    layers.append(network_layer)
    _emit_progress(progress, network_layer.name, "done", network_layer.summary)

    _emit_progress(progress, "callback_ports", "running", _progress_text(locale, "callback_running"))
    callback_layers = []
    if fast:
        for port in CALLBACK_PORTS:
            callback_layers.append(_summarize_port_fast(port, locale=locale, timeout=tcp_timeout))
        callback_conflict = False
        callback_summary = _text(locale, "callback_fast_summary") + " | " + " | ".join(
            str(layer["summary"]) for layer in callback_layers
        )
    else:
        for port in CALLBACK_PORTS:
            callback_layers.append(summarize_port(port, locale=locale, timeout=port_timeout))
        callback_conflict, callback_summary = analyze_callback_ports(callback_layers, locale=locale)

    callback_layer = LayerResult(
        name="callback_ports",
        ok=not callback_conflict,
        summary=callback_summary,
        details={"ports": callback_layers, "conflict_detected": callback_conflict},
    )
    layers.append(callback_layer)
    _emit_progress(progress, callback_layer.name, "done", callback_layer.summary)

    _emit_progress(progress, "login_status", "running", _progress_text(locale, "login_running", client=client))
    login = check_login_status(client, locale=locale)
    login_layer = LayerResult(
        name="login_status",
        ok=login.logged_in or client not in FULL_DIAGNOSTIC_CLIENTS,
        summary=login.summary,
        details=login.to_dict(),
    )
    layers.append(login_layer)
    _emit_progress(progress, login_layer.name, "done", login_layer.summary)

    _emit_progress(progress, "online_session", "running", _progress_text(locale, "online_session_running"))
    online_session = _evaluate_online_session(
        client=client,
        login=login,
        endpoint_probes=endpoint_probes,
        network_profile=network_profile,
        locale=locale,
    )
    online_layer = LayerResult(
        name="online_session",
        ok=bool(online_session["ok"]),
        summary=str(online_session["summary"]),
        details=online_session,
    )
    layers.append(online_layer)
    _emit_progress(progress, online_layer.name, "done", online_layer.summary)

    _emit_progress(progress, "client_specific", "running", _progress_text(locale, "client_running", client=client))
    client_info = check_client(client, fast=fast)
    client_layer = LayerResult(
        name="client_specific",
        ok=True,
        summary=_text(locale, "client_specific", client=client),
        details=client_info,
    )
    layers.append(client_layer)
    _emit_progress(progress, client_layer.name, "done", client_layer.summary)

    _emit_progress(progress, "finalize", "running", _progress_text(locale, "finalize_running"))
    case, root_cause, confidence, browser_explanation = _classify(
        system=system,
        system_endpoint=system_endpoint,
        env_endpoint=env_endpoint,
        system_alive=system_alive,
        env_alive=env_alive,
        oauth_via_env=oauth_via_env,
        oauth_via_system=oauth_via_system,
        callback_conflict=callback_conflict,
        locale=locale,
    )

    fixes.extend(
        _build_fixes(
            case=case,
            system_endpoint=system_endpoint,
            env_endpoint=env_endpoint,
            system_alive=system_alive,
            env_alive=env_alive,
            system=system,
            network_profile=network_profile,
            client_info=client_info,
            client=client,
            logged_in=login.logged_in,
            locale=locale,
        )
    )
    official_guidance = _build_official_guidance(client=client, case=case, logged_in=login.logged_in, locale=locale)

    if system_endpoint.is_set and env_endpoint.is_set and system_endpoint.port != env_endpoint.port:
        notes.append(_text(locale, "note_proxy_mismatch"))
    if not system.get("bypass_localhost"):
        notes.append(_text(locale, "note_localhost"))
    if client == "codex" and not login.logged_in and case == FailureCase.NONE:
        notes.append(_text(locale, "note_login_missing_healthy"))
    elif client == "codex" and not login.logged_in:
        notes.append(_text(locale, "note_login_missing"))
    elif client in {"claude", "gemini"} and not login.logged_in:
        notes.append(_text(locale, "note_client_login_missing", client=client))

    status = HealthStatus.HEALTHY if case == FailureCase.NONE else HealthStatus.UNHEALTHY
    _emit_progress(progress, "finalize", "done", _progress_text(locale, "finalize_done"))
    return DiagnosisReport(
        tool_version=__version__,
        platform=f"{platform.system()} {platform.release()}",
        client=client,
        status=status,
        case=case,
        root_cause=root_cause,
        confidence=confidence,
        browser_explanation=browser_explanation,
        layers=layers,
        fixes=fixes,
        notes=notes,
        official_guidance=official_guidance,
    )


def _classify(
    *,
    system: dict[str, object],
    system_endpoint: ProxyEndpoint,
    env_endpoint: ProxyEndpoint,
    system_alive: bool,
    env_alive: bool,
    oauth_via_env: dict[str, object],
    oauth_via_system: dict[str, object],
    callback_conflict: bool,
    locale: str = "zh",
) -> tuple[FailureCase, str, str, str]:
    browser_explanation = _text(locale, "browser_explanation")

    if (
        system_endpoint.is_set
        and env_endpoint.is_set
        and system_endpoint.port != env_endpoint.port
        and system_alive
        and not env_alive
    ):
        return (
            FailureCase.PROXY_PORT_MISMATCH,
            _text(locale, "cause_proxy_mismatch", system_url=system_endpoint.url, env_url=env_endpoint.url),
            "high",
            browser_explanation,
        )

    if env_endpoint.is_set and not env_alive:
        return (
            FailureCase.DEAD_PROXY_PORT,
            _text(locale, "cause_env_dead", env_url=env_endpoint.url),
            "high",
            browser_explanation,
        )

    if system_endpoint.is_set and not system_alive and env_endpoint.is_set and not env_alive:
        return (
            FailureCase.DEAD_PROXY_PORT,
            _text(locale, "cause_all_dead"),
            "high",
            browser_explanation,
        )

    if not system.get("bypass_localhost"):
        return (
            FailureCase.LOCALHOST_PROXIED,
            _text(locale, "cause_localhost"),
            "medium",
            browser_explanation,
        )

    if callback_conflict:
        return (
            FailureCase.CALLBACK_PORT_CONFLICT,
            _text(locale, "cause_callback"),
            "medium",
            browser_explanation,
        )

    if env_endpoint.is_set and not oauth_via_env["ok"] and system_endpoint.is_set and oauth_via_system["ok"]:
        return (
            FailureCase.PROXY_PORT_MISMATCH,
            _text(locale, "cause_oauth_proxy_path"),
            "high",
            browser_explanation,
        )

    if env_endpoint.is_set and not oauth_via_env["ok"] and "certificate" in str(oauth_via_env.get("error", "")).lower():
        return (
            FailureCase.TLS_OR_CA,
            _text(locale, "cause_tls"),
            "medium",
            browser_explanation,
        )

    if env_endpoint.is_set and not oauth_via_env["ok"] and not system_endpoint.is_set:
        return (
            FailureCase.UNKNOWN,
            _text(locale, "cause_unknown_env"),
            "medium",
            browser_explanation,
        )

    return (
        FailureCase.NONE,
        _text(locale, "cause_none"),
        "high",
        browser_explanation,
    )


def _probe_auth_endpoint(client: str, proxy: ProxyEndpoint | None, *, timeout: float = 12.0) -> dict[str, object]:
    if client == "claude":
        return http_probe("https://api.anthropic.com/v1/messages", method="POST", body=b"{}", proxy=proxy, timeout=timeout)
    if client == "gemini":
        return http_probe(
            "https://oauth2.googleapis.com/token",
            method="POST",
            body=b"grant_type=refresh_token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            proxy=proxy,
            timeout=timeout,
        )
    return probe_oauth_token(proxy, timeout=timeout)


def _probe_api_endpoint(client: str, proxy: ProxyEndpoint | None, *, timeout: float = 12.0) -> dict[str, object]:
    if client == "claude":
        return http_probe("https://api.anthropic.com/v1/models", method="GET", proxy=proxy, timeout=timeout)
    if client == "gemini":
        return http_probe("https://generativelanguage.googleapis.com/v1beta/models", method="GET", proxy=proxy, timeout=timeout)
    return probe_chatgpt_api(proxy, timeout=timeout)


def _run_endpoint_probes(
    *,
    client: str,
    env_endpoint: ProxyEndpoint,
    system_endpoint: ProxyEndpoint,
    timeout: float,
) -> dict[str, dict[str, object]]:
    env_proxy = env_endpoint if env_endpoint.is_set else None
    system_proxy = system_endpoint if system_endpoint.is_set else None

    jobs = {
        "oauth_via_env": ("auth", _proxy_key(env_proxy), env_proxy),
        "oauth_via_system": ("auth", _proxy_key(system_proxy), system_proxy),
        "oauth_direct": ("auth", "direct", None),
        "api_via_env": ("api", _proxy_key(env_proxy), env_proxy),
        "api_via_system": ("api", _proxy_key(system_proxy), system_proxy),
    }
    unique_jobs: dict[tuple[str, str], tuple[str, ProxyEndpoint | None]] = {}
    for probe_type, proxy_key, proxy in jobs.values():
        unique_jobs.setdefault((probe_type, proxy_key), (probe_type, proxy))

    def run_one(probe_type: str, proxy: ProxyEndpoint | None) -> dict[str, object]:
        if probe_type == "auth":
            return _probe_auth_endpoint(client, proxy, timeout=timeout)
        return _probe_api_endpoint(client, proxy, timeout=timeout)

    with ThreadPoolExecutor(max_workers=min(5, len(unique_jobs))) as executor:
        futures = {
            key: executor.submit(run_one, probe_type, proxy)
            for key, (probe_type, proxy) in unique_jobs.items()
        }
        results = {key: future.result() for key, future in futures.items()}

    return {
        name: results[(probe_type, proxy_key)]
        for name, (probe_type, proxy_key, _proxy) in jobs.items()
    }


def _proxy_key(proxy: ProxyEndpoint | None) -> str:
    return proxy.url if proxy and proxy.is_set else "direct"


def _evaluate_online_session(
    *,
    client: str,
    login,
    endpoint_probes: dict[str, dict[str, object]],
    network_profile: dict[str, object],
    locale: str,
) -> dict[str, object]:
    auth_ok_paths = _ok_probe_paths(endpoint_probes, ("oauth_via_env", "oauth_via_system", "oauth_direct"))
    api_ok_paths = _ok_probe_paths(endpoint_probes, ("api_via_env", "api_via_system"))
    service_reachable = bool(auth_ok_paths or api_ok_paths)
    network_score = int(network_profile.get("score") or 0)
    public_ip_detected = bool(network_profile.get("public_ip"))
    online_ready = service_reachable and network_score >= 60
    credential_ready = bool(getattr(login, "logged_in", False))
    ok = online_ready and (credential_ready or client not in FULL_DIAGNOSTIC_CLIENTS)

    if ok:
        summary_key = "online_session_ok"
    elif service_reachable and not credential_ready and client in FULL_DIAGNOSTIC_CLIENTS:
        summary_key = "online_session_missing_login"
    elif service_reachable:
        summary_key = "online_session_degraded"
    else:
        summary_key = "online_session_blocked"

    return {
        "mode": "online",
        "ok": ok,
        "summary": _text(
            locale,
            summary_key,
            score=network_score,
            auth_paths=", ".join(auth_ok_paths) or _text(locale, "none_value"),
            api_paths=", ".join(api_ok_paths) or _text(locale, "none_value"),
        ),
        "client": client,
        "credential_ready": credential_ready,
        "service_reachable": service_reachable,
        "online_ready": online_ready,
        "network_score": network_score,
        "public_ip_detected": public_ip_detected,
        "auth_ok_paths": auth_ok_paths,
        "api_ok_paths": api_ok_paths,
        "probe_errors": {
            name: probe.get("error")
            for name, probe in endpoint_probes.items()
            if not probe.get("ok") and probe.get("error")
        },
    }


def _ok_probe_paths(endpoint_probes: dict[str, dict[str, object]], names: tuple[str, ...]) -> list[str]:
    return [name for name in names if bool(endpoint_probes.get(name, {}).get("ok"))]


def _summarize_port_fast(port: int, *, locale: str, timeout: float) -> dict[str, object]:
    listening = tcp_probe("127.0.0.1", port, timeout=timeout)
    if locale == "en":
        summary = f":{port} " + ("listening (owner skipped in fast scan)" if listening else "idle")
    else:
        summary = f":{port} " + ("监听中（快速扫描跳过归属）" if listening else "空闲")
    return {"port": port, "listening": listening, "listeners": [], "summary": summary, "fast_scan": True}


def _endpoint_summary_key(client: str) -> str:
    if client == "claude":
        return "anthropic_summary"
    if client == "gemini":
        return "gemini_summary"
    return "oauth_summary"


def _build_fixes(
    *,
    case: FailureCase,
    system_endpoint: ProxyEndpoint,
    env_endpoint: ProxyEndpoint,
    system_alive: bool,
    env_alive: bool,
    system: dict[str, object],
    client: str,
    logged_in: bool,
    network_profile: dict[str, object] | None = None,
    client_info: dict[str, object] | None = None,
    locale: str = "zh",
) -> list[FixAction]:
    fixes: list[FixAction] = []

    if env_endpoint.is_set and env_alive and (
        not system_endpoint.is_set or not system_alive or system_endpoint.url != env_endpoint.url
    ):
        fixes.append(
            FixAction(
                fix_id="sync-system-proxy",
                description=_text(locale, "fix_sync_system_proxy", url=env_endpoint.url),
                command=f'authkit fix --apply --client "{client}"',
                risk="medium",
                auto_applicable=True,
                rollback_supported=True,
            )
        )

    if case in {FailureCase.PROXY_PORT_MISMATCH, FailureCase.DEAD_PROXY_PORT} and system_endpoint.is_set:
        fixes.append(
            FixAction(
                fix_id="sync-env-proxy",
                description=_text(locale, "fix_sync_proxy", url=system_endpoint.url),
                command=f'authkit sync --apply --proxy "{system_endpoint.url}"',
                risk="low",
                auto_applicable=True,
                rollback_supported=True,
            )
        )

    if case == FailureCase.DEAD_PROXY_PORT and not system_endpoint.is_set:
        fixes.append(
            FixAction(
                fix_id="clear-env-proxy",
                description=_text(locale, "fix_clear_proxy"),
                command="authkit sync --clear --apply",
                risk="low",
                auto_applicable=True,
                rollback_supported=True,
            )
        )

    if not system.get("bypass_localhost"):
        fixes.append(
            FixAction(
                fix_id="set-no-proxy",
                description=_text(locale, "fix_no_proxy"),
                command=f'authkit sync --apply --no-proxy "{DEFAULT_NO_PROXY}"',
                risk="low",
                auto_applicable=True,
                rollback_supported=True,
            )
        )

    if _should_offer_dns_flush(case=case, network_profile=network_profile):
        fixes.append(
            FixAction(
                fix_id="flush-dns-cache",
                description=_text(locale, "fix_flush_dns"),
                command="authkit dns --flush --apply",
                risk="low",
                auto_applicable=True,
            )
        )

    if _should_offer_winsock_reset(case=case, network_profile=network_profile):
        fixes.append(
            FixAction(
                fix_id="winsock-reset",
                description=_text(locale, "fix_winsock_reset"),
                command="authkit winsock --reset --apply",
                risk="medium",
                auto_applicable=False,
                admin_required=True,
                restart_required=True,
            )
        )

    firewall_program = _client_firewall_program(client_info)
    if firewall_program and _should_offer_firewall_allow(case=case, network_profile=network_profile):
        fixes.append(
            FixAction(
                fix_id="allow-firewall-outbound",
                description=_text(locale, "fix_firewall_allow", path=firewall_program),
                command=_firewall_command(client=client, program_path=firewall_program),
                risk="medium",
                auto_applicable=False,
                admin_required=True,
            )
        )

    if case == FailureCase.CALLBACK_PORT_CONFLICT:
        fixes.append(
            FixAction(
                fix_id="inspect-port-1455",
                description=_text(locale, "fix_inspect_port"),
                command='powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 1455 -State Listen | Format-Table -AutoSize"',
                risk="low",
                auto_applicable=False,
            )
        )

    if case == FailureCase.TLS_OR_CA:
        fixes.append(
            FixAction(
                fix_id="configure-client-ca",
                description=_text(locale, "fix_ca", client=client),
                command=f'authkit ca --apply --client "{client}" --cert "C:\\path\\to\\corp-ca.pem"',
                risk="medium",
                auto_applicable=False,
                rollback_supported=True,
            )
        )

    if case == FailureCase.NONE:
        if client == "codex" and not logged_in:
            fixes.append(
                FixAction(
                    fix_id="device-auth-fallback",
                    description=_text(locale, "fix_device_auth"),
                    command="codex login --device-auth",
                    risk="low",
                    auto_applicable=False,
                )
            )
        elif client == "claude" and not logged_in:
            fixes.append(
                FixAction(
                    fix_id="claude-login",
                    description=_text(locale, "fix_claude_login"),
                    command="claude login",
                    risk="low",
                    auto_applicable=False,
                )
            )
        elif client == "gemini" and not logged_in:
            fixes.append(
                FixAction(
                    fix_id="gemini-login",
                    description=_text(locale, "fix_gemini_login"),
                    command="gemini auth login",
                    risk="low",
                    auto_applicable=False,
                )
            )
        return fixes

    if client == "codex":
        if case in {
            FailureCase.PROXY_PORT_MISMATCH,
            FailureCase.DEAD_PROXY_PORT,
            FailureCase.LOCALHOST_PROXIED,
        }:
            fixes.append(
                FixAction(
                    fix_id="restart-codex",
                    description=_text(locale, "fix_restart_codex"),
                    command=_text(locale, "command_restart_codex"),
                    risk="none",
                    auto_applicable=False,
                )
            )
        fixes.append(
            FixAction(
                fix_id="device-auth-fallback",
                description=_text(locale, "fix_device_auth_oauth"),
                command="codex login --device-auth",
                risk="low",
                auto_applicable=False,
            )
        )

    return fixes


def _should_offer_dns_flush(*, case: FailureCase, network_profile: dict[str, object] | None) -> bool:
    if case == FailureCase.NONE:
        return False
    if case == FailureCase.UNKNOWN:
        return True
    if not network_profile:
        return False
    score = int(network_profile.get("score") or 0)
    endpoint_reachable = bool(network_profile.get("endpoint_reachable", True))
    return score < 60 or not endpoint_reachable


def _should_offer_winsock_reset(*, case: FailureCase, network_profile: dict[str, object] | None) -> bool:
    if case == FailureCase.NONE:
        return False
    if not network_profile:
        return case == FailureCase.UNKNOWN
    score = int(network_profile.get("score") or 0)
    endpoint_reachable = bool(network_profile.get("endpoint_reachable", True))
    return case == FailureCase.UNKNOWN and (score < 50 or not endpoint_reachable)


def _should_offer_firewall_allow(*, case: FailureCase, network_profile: dict[str, object] | None) -> bool:
    if case == FailureCase.NONE:
        return False
    if not network_profile:
        return case == FailureCase.UNKNOWN
    endpoint_reachable = bool(network_profile.get("endpoint_reachable", True))
    score = int(network_profile.get("score") or 0)
    return not endpoint_reachable or (case == FailureCase.UNKNOWN and score < 50)


def _client_firewall_program(client_info: dict[str, object] | None) -> str:
    if not client_info:
        return ""
    for key in ("codex_exe", "executable"):
        value = str(client_info.get(key) or "")
        if value:
            return value
    return ""


def _firewall_command(*, client: str, program_path: str) -> str:
    return f'authkit firewall --allow-outbound --client "{client}" --program "{program_path}" --apply'


def _build_official_guidance(
    *,
    client: str,
    case: FailureCase,
    logged_in: bool,
    locale: str = "zh",
) -> list[OfficialGuidance]:
    guidance: list[OfficialGuidance] = []

    if case in {FailureCase.PROXY_PORT_MISMATCH, FailureCase.DEAD_PROXY_PORT, FailureCase.UNKNOWN}:
        guidance.append(_guidance(locale, "proxy_env"))
    if case == FailureCase.LOCALHOST_PROXIED:
        guidance.append(_guidance(locale, "localhost_bypass"))
    if case == FailureCase.TLS_OR_CA:
        guidance.append(_guidance(locale, "certificate"))
    if case == FailureCase.CALLBACK_PORT_CONFLICT:
        guidance.append(_guidance(locale, "callback"))
    if not logged_in:
        guidance.append(_guidance(locale, f"{client}_login" if client in {"codex", "claude", "gemini"} else "generic_login"))

    client_key = f"{client}_verify" if client in {"codex", "claude", "gemini", "vscode", "cursor"} else "generic_verify"
    guidance.append(_guidance(locale, client_key))
    return guidance


def _guidance(locale: str, key: str) -> OfficialGuidance:
    catalog = _guidance_catalog().get(locale, _guidance_catalog()["zh"])
    data = catalog.get(key) or catalog["generic_verify"]
    return OfficialGuidance(
        title=data["title"],
        steps=list(data["steps"]),
        source=data["source"],
        url=data["url"],
    )


def _guidance_catalog() -> dict[str, dict[str, dict[str, object]]]:
    return {
        "zh": {
            "proxy_env": {
                "title": "官方路径：统一客户端进程代理",
                "steps": [
                    "让系统代理、HTTP_PROXY、HTTPS_PROXY 指向同一个可达代理端口。",
                    "设置 NO_PROXY=127.0.0.1,localhost,::1，避免本地回调走代理。",
                    "完全关闭终端和目标客户端后重新打开，再重新诊断。",
                ],
                "source": "VS Code Network / Claude Code Corporate Proxy",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
            "localhost_bypass": {
                "title": "官方路径：绕过 localhost 回调",
                "steps": [
                    "把 127.0.0.1、localhost、::1 加入 NO_PROXY 或代理绕过列表。",
                    "重新打开客户端，重新触发登录。",
                    "如果仍失败，检查回调端口是否被其他进程占用。",
                ],
                "source": "VS Code Network",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
            "certificate": {
                "title": "官方路径：处理企业证书/HTTPS 检查",
                "steps": [
                    "确认企业代理或 HTTPS 检查使用的根证书路径。",
                    "按客户端官方方式配置 CA 证书环境变量或设置项。",
                    "重启终端和客户端后重新运行登录或 doctor 检查。",
                ],
                "source": "Claude Code Corporate Proxy",
                "url": "https://docs.anthropic.com/en/docs/claude-code/corporate-proxy",
            },
            "callback": {
                "title": "官方路径：释放 OAuth 回调端口",
                "steps": [
                    "查看占用 localhost:1455/1457 的进程。",
                    "关闭占用回调端口的旧客户端、WSL 转发或本地服务。",
                    "重新打开目标客户端并重新登录。",
                ],
                "source": "OpenAI Codex CLI Reference",
                "url": "https://developers.openai.com/codex/cli/reference/",
            },
            "codex_login": {
                "title": "官方路径：Codex 登录恢复",
                "steps": [
                    "优先使用 Codex 正常登录流程。",
                    "浏览器 OAuth 失败时，使用 codex login --device-auth。",
                    "登录后重新运行 authkit check --client codex 验证。",
                ],
                "source": "OpenAI Codex CLI Reference",
                "url": "https://developers.openai.com/codex/cli/reference/",
            },
            "claude_login": {
                "title": "官方路径：Claude Code 登录恢复",
                "steps": [
                    "运行 claude login 或配置 ANTHROPIC_API_KEY。",
                    "代理或证书变更后，运行 claude doctor 复核。",
                    "确认终端环境变量在启动 Claude Code 前已经生效。",
                ],
                "source": "Claude Code Troubleshooting",
                "url": "https://docs.anthropic.com/en/docs/claude-code/troubleshooting",
            },
            "gemini_login": {
                "title": "官方路径：Gemini CLI 登录恢复",
                "steps": [
                    "使用 Gemini CLI 官方认证流程登录，或配置 GEMINI_API_KEY / GOOGLE_API_KEY。",
                    "企业网络下先确认 HTTPS_PROXY 和 NO_PROXY 已在终端生效。",
                    "重新运行 gemini --version 和 AuthKit 诊断确认。",
                ],
                "source": "Gemini CLI Authentication / Enterprise",
                "url": "https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/authentication.md",
            },
            "generic_login": {
                "title": "官方路径：在客户端内重新登录",
                "steps": [
                    "使用客户端官方登录入口重新登录。",
                    "如果使用代理，先确保代理环境在客户端启动前已生效。",
                    "重新运行 AuthKit 诊断确认登录层通过。",
                ],
                "source": "Client official documentation",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
            "codex_verify": {
                "title": "成功闭环：Codex 验证",
                "steps": [
                    "重新打开 Codex Desktop 或终端。",
                    "重新执行登录。",
                    "再次运行 AuthKit，确认代理、OAuth、登录状态均通过。",
                ],
                "source": "OpenAI Codex CLI Reference",
                "url": "https://developers.openai.com/codex/cli/reference/",
            },
            "claude_verify": {
                "title": "成功闭环：Claude Code 验证",
                "steps": [
                    "重新打开终端，让代理/证书环境变量重新加载。",
                    "运行 claude doctor。",
                    "再次运行 AuthKit，确认 Anthropic API 和登录层通过。",
                ],
                "source": "Claude Code Troubleshooting",
                "url": "https://docs.anthropic.com/en/docs/claude-code/troubleshooting",
            },
            "gemini_verify": {
                "title": "成功闭环：Gemini CLI 验证",
                "steps": [
                    "重新打开终端，让代理/API Key 环境变量重新加载。",
                    "运行 gemini --version 或一次轻量 Gemini CLI 命令。",
                    "再次运行 AuthKit，确认 Google OAuth/API 和登录层通过。",
                ],
                "source": "Gemini CLI",
                "url": "https://github.com/google-gemini/gemini-cli",
            },
            "vscode_verify": {
                "title": "成功闭环：VS Code / Copilot 验证",
                "steps": [
                    "重启 VS Code。",
                    "运行 Help: Start Extension Bisect 或检查 GitHub Copilot 输出日志。",
                    "确认 VS Code 网络代理设置与系统代理一致。",
                ],
                "source": "VS Code Network / Copilot FAQ",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
            "cursor_verify": {
                "title": "成功闭环：Cursor 验证",
                "steps": [
                    "重启 Cursor。",
                    "确认 Cursor settings 中的 http.proxy、http.noProxy 与系统代理一致。",
                    "如果启用 WSL 运行子进程，确认回调端口未被 WSL 转发占用。",
                ],
                "source": "VS Code Network model",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
            "generic_verify": {
                "title": "成功闭环：重新验证",
                "steps": [
                    "重启目标客户端。",
                    "重新执行登录。",
                    "再次运行 AuthKit，确认异常层清零。",
                ],
                "source": "Client official documentation",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
        },
        "en": {
            "proxy_env": {
                "title": "Official path: align client process proxy",
                "steps": [
                    "Point the system proxy, HTTP_PROXY, and HTTPS_PROXY to the same reachable proxy endpoint.",
                    "Set NO_PROXY=127.0.0.1,localhost,::1 so local callbacks bypass the proxy.",
                    "Fully close the terminal and target client, reopen them, then run diagnosis again.",
                ],
                "source": "VS Code Network / Claude Code Corporate Proxy",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
            "localhost_bypass": {
                "title": "Official path: bypass localhost callbacks",
                "steps": [
                    "Add 127.0.0.1, localhost, and ::1 to NO_PROXY or the proxy bypass list.",
                    "Restart the client and trigger sign-in again.",
                    "If it still fails, inspect whether another process owns the callback port.",
                ],
                "source": "VS Code Network",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
            "certificate": {
                "title": "Official path: handle enterprise certificates",
                "steps": [
                    "Confirm the root certificate path used by the corporate proxy or HTTPS inspection.",
                    "Configure the CA certificate through the client-supported environment variable or setting.",
                    "Restart the terminal and client, then rerun sign-in or doctor checks.",
                ],
                "source": "Claude Code Corporate Proxy",
                "url": "https://docs.anthropic.com/en/docs/claude-code/corporate-proxy",
            },
            "callback": {
                "title": "Official path: free the OAuth callback port",
                "steps": [
                    "Inspect processes using localhost:1455/1457.",
                    "Close stale clients, WSL relays, or local services that own the callback port.",
                    "Reopen the target client and sign in again.",
                ],
                "source": "OpenAI Codex CLI Reference",
                "url": "https://developers.openai.com/codex/cli/reference/",
            },
            "codex_login": {
                "title": "Official path: recover Codex sign-in",
                "steps": [
                    "Use the normal Codex sign-in flow first.",
                    "If browser OAuth fails, run codex login --device-auth.",
                    "After sign-in, run authkit check --client codex again.",
                ],
                "source": "OpenAI Codex CLI Reference",
                "url": "https://developers.openai.com/codex/cli/reference/",
            },
            "claude_login": {
                "title": "Official path: recover Claude Code sign-in",
                "steps": [
                    "Run claude login or configure ANTHROPIC_API_KEY.",
                    "After proxy or certificate changes, run claude doctor.",
                    "Confirm terminal environment variables are loaded before starting Claude Code.",
                ],
                "source": "Claude Code Troubleshooting",
                "url": "https://docs.anthropic.com/en/docs/claude-code/troubleshooting",
            },
            "gemini_login": {
                "title": "Official path: recover Gemini CLI sign-in",
                "steps": [
                    "Use Gemini CLI official authentication or configure GEMINI_API_KEY / GOOGLE_API_KEY.",
                    "On enterprise networks, first confirm HTTPS_PROXY and NO_PROXY are active in the terminal.",
                    "Run gemini --version and AuthKit diagnosis again.",
                ],
                "source": "Gemini CLI Authentication / Enterprise",
                "url": "https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/authentication.md",
            },
            "generic_login": {
                "title": "Official path: sign in inside the client",
                "steps": [
                    "Use the client's official sign-in entry.",
                    "If a proxy is required, ensure the proxy environment is active before starting the client.",
                    "Run AuthKit again and confirm the login layer passes.",
                ],
                "source": "Client official documentation",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
            "codex_verify": {
                "title": "Success loop: verify Codex",
                "steps": [
                    "Reopen Codex Desktop or the terminal.",
                    "Sign in again.",
                    "Run AuthKit again and confirm proxy, OAuth, and login layers all pass.",
                ],
                "source": "OpenAI Codex CLI Reference",
                "url": "https://developers.openai.com/codex/cli/reference/",
            },
            "claude_verify": {
                "title": "Success loop: verify Claude Code",
                "steps": [
                    "Reopen the terminal so proxy/certificate environment variables reload.",
                    "Run claude doctor.",
                    "Run AuthKit again and confirm Anthropic API and login layers pass.",
                ],
                "source": "Claude Code Troubleshooting",
                "url": "https://docs.anthropic.com/en/docs/claude-code/troubleshooting",
            },
            "gemini_verify": {
                "title": "Success loop: verify Gemini CLI",
                "steps": [
                    "Reopen the terminal so proxy/API key environment variables reload.",
                    "Run gemini --version or one lightweight Gemini CLI command.",
                    "Run AuthKit again and confirm Google OAuth/API and login layers pass.",
                ],
                "source": "Gemini CLI",
                "url": "https://github.com/google-gemini/gemini-cli",
            },
            "vscode_verify": {
                "title": "Success loop: verify VS Code / Copilot",
                "steps": [
                    "Restart VS Code.",
                    "Check the GitHub Copilot output log or VS Code network diagnostics.",
                    "Confirm VS Code proxy settings match the system proxy.",
                ],
                "source": "VS Code Network / Copilot FAQ",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
            "cursor_verify": {
                "title": "Success loop: verify Cursor",
                "steps": [
                    "Restart Cursor.",
                    "Confirm http.proxy and http.noProxy match the system proxy path.",
                    "If child processes run in WSL, confirm callback ports are not owned by WSL relay.",
                ],
                "source": "VS Code Network model",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
            "generic_verify": {
                "title": "Success loop: verify again",
                "steps": [
                    "Restart the target client.",
                    "Sign in again.",
                    "Run AuthKit again and confirm issue layers are cleared.",
                ],
                "source": "Client official documentation",
                "url": "https://code.visualstudio.com/docs/setup/network",
            },
        },
    }


def _text(locale: str, key: str, **kwargs: object) -> str:
    if key == "fix_sync_system_proxy":
        text = (
            "Sync the Windows system proxy to the currently reachable proxy {url}"
            if locale == "en"
            else "将 Windows 系统代理同步为当前可用代理 {url}"
        )
        return text.format(**kwargs) if kwargs else text

    catalog = {
        "zh": {
            "not_enabled": "未启用",
            "not_set": "未设置",
            "unknown_value": "未知",
            "none_value": "无",
            "system_proxy": "系统代理: {url}",
            "user_env_proxy": "用户环境变量代理: {url}",
            "port_reachable": "，端口可达",
            "port_unreachable_or_unset": "，端口不可达或未设置",
            "oauth_summary": "OAuth / ChatGPT 端点连通性检查",
            "anthropic_summary": "Claude / Anthropic API 端点连通性检查",
            "gemini_summary": "Gemini / Google OAuth 与 API 端点连通性检查",
            "network_profile_summary": "网络画像: 出口 IP {ip}，环境评分 {score}（{quality}）",
            "online_session_ok": "在线模式通过：本地凭据存在，服务端可达，网络评分 {score}",
            "online_session_missing_login": "在线模式部分通过：服务端可达（认证 {auth_paths} / API {api_paths}），但未检测到本地登录凭据",
            "online_session_degraded": "在线模式降级：服务端可达，但网络评分 {score} 偏低",
            "online_session_blocked": "在线模式阻塞：未能连通认证或 API 服务端点",
            "network_quality_good": "良好",
            "network_quality_fair": "可用",
            "network_quality_weak": "偏弱",
            "network_quality_poor": "较差",
            "network_quality_unknown": "未知",
            "client_specific": "{client} 客户端专项检查",
            "callback_fast_summary": "快速扫描回调端口",
            "browser_explanation": "浏览器通常走 Windows 系统代理（WinINET），而 Codex/Cursor CLI 后端更常读取 HTTP_PROXY/HTTPS_PROXY 环境变量。",
            "cause_proxy_mismatch": "系统代理指向 {system_url} 且可用，但环境变量代理指向 {env_url} 且端口不可达。",
            "cause_env_dead": "环境变量代理 {env_url} 已配置，但本地端口没有进程监听。",
            "cause_all_dead": "系统代理与环境变量代理均指向不可达端口，代理软件可能未启动。",
            "cause_localhost": "系统代理未将 localhost/127.0.0.1 加入绕过列表，OAuth 本地回调可能被错误转发。",
            "cause_callback": "localhost:1455 已被其他进程占用，OAuth 回调可能无法被正确的 Codex 实例接收。",
            "cause_oauth_proxy_path": "通过环境变量代理无法访问 OAuth 端点，但通过系统代理可以，说明客户端走了错误代理路径。",
            "cause_tls": "访问 OAuth 端点时出现证书/TLS 错误，常见于企业 HTTPS 检查或自签 CA。",
            "cause_unknown_env": "环境变量代理无法访问 OAuth 端点，建议同步或清理代理配置后重试。",
            "cause_none": "未检测到明显的代理/OAuth 配置问题。",
            "note_proxy_mismatch": "检测到系统代理与环境变量代理端口不一致，这是 Codex token exchange 失败的最常见原因。",
            "note_localhost": "系统代理未明确绕过 localhost，可能导致 OAuth 回调异常。",
            "note_login_missing_healthy": "网络配置正常，但尚未检测到 Codex 登录凭据，可在 Codex 中登录或使用设备码登录。",
            "note_login_missing": "当前未检测到 ~/.codex/auth.json，修复网络后请重新登录。",
            "note_client_login_missing": "当前未检测到 {client} 凭据，网络路径修复后请重新登录或配置 API Key。",
            "fix_sync_proxy": "将用户环境变量代理同步为系统代理 {url}",
            "fix_clear_proxy": "清理失效的用户级代理环境变量",
            "fix_no_proxy": "设置 NO_PROXY，确保 localhost 不走代理",
            "fix_flush_dns": "刷新 Windows DNS 解析缓存",
            "fix_winsock_reset": "重置 Windows Winsock 网络目录（需要重启后生效）",
            "fix_firewall_allow": "为目标客户端添加 Windows 防火墙出站允许规则：{path}",
            "fix_inspect_port": "检查并关闭占用 1455 端口的进程后重试登录",
            "fix_ca": "为 {client} 配置客户端级企业 CA 证书路径（不导入系统根证书库）",
            "fix_device_auth": "使用设备码登录",
            "fix_claude_login": "登录 Claude Code 或配置 ANTHROPIC_API_KEY",
            "fix_gemini_login": "登录 Gemini CLI 或配置 GEMINI_API_KEY / GOOGLE_API_KEY",
            "fix_restart_codex": "完全退出并重启 Codex Desktop，使新的环境变量生效",
            "command_restart_codex": "请手动关闭 Codex 后重新打开，再点击「使用 ChatGPT 登录」",
            "fix_device_auth_oauth": "使用设备码登录（适合浏览器 OAuth 失败时）",
        },
        "en": {
            "not_enabled": "not enabled",
            "not_set": "not set",
            "unknown_value": "unknown",
            "none_value": "none",
            "system_proxy": "System proxy: {url}",
            "user_env_proxy": "User environment proxy: {url}",
            "port_reachable": ", port reachable",
            "port_unreachable_or_unset": ", port unreachable or not configured",
            "oauth_summary": "OAuth / ChatGPT endpoint connectivity check",
            "anthropic_summary": "Claude / Anthropic API endpoint connectivity check",
            "gemini_summary": "Gemini / Google OAuth and API endpoint connectivity check",
            "network_profile_summary": "Network profile: exit IP {ip}, environment score {score} ({quality})",
            "online_session_ok": "Online mode passed: local credentials exist, service endpoints are reachable, network score {score}",
            "online_session_missing_login": "Online mode partially passed: service endpoints are reachable (auth {auth_paths} / API {api_paths}), but local credentials were not detected",
            "online_session_degraded": "Online mode degraded: service endpoints are reachable, but network score {score} is low",
            "online_session_blocked": "Online mode blocked: auth or API service endpoints are not reachable",
            "network_quality_good": "good",
            "network_quality_fair": "fair",
            "network_quality_weak": "weak",
            "network_quality_poor": "poor",
            "network_quality_unknown": "unknown",
            "client_specific": "{client} client-specific checks",
            "callback_fast_summary": "Fast callback port scan",
            "browser_explanation": "Browsers usually use the Windows system proxy (WinINET), while Codex/Cursor CLI backends more often read HTTP_PROXY/HTTPS_PROXY environment variables.",
            "cause_proxy_mismatch": "The system proxy points to {system_url} and is reachable, but the environment proxy points to {env_url} and its port is unreachable.",
            "cause_env_dead": "Environment proxy {env_url} is configured, but no local process is listening on that port.",
            "cause_all_dead": "Both the system proxy and environment proxy point to unreachable ports. The proxy app may not be running.",
            "cause_localhost": "The system proxy does not bypass localhost/127.0.0.1, so the OAuth local callback may be forwarded incorrectly.",
            "cause_callback": "localhost:1455 is already used by another process, so the OAuth callback may not reach the correct Codex instance.",
            "cause_oauth_proxy_path": "OAuth endpoints fail through the environment proxy but work through the system proxy, which means the client is using the wrong proxy path.",
            "cause_tls": "A certificate/TLS error occurred while accessing the OAuth endpoint, commonly caused by enterprise HTTPS inspection or a self-signed CA.",
            "cause_unknown_env": "The environment proxy cannot reach the OAuth endpoint. Sync or clear proxy settings and try again.",
            "cause_none": "No obvious proxy/OAuth configuration issue was detected.",
            "note_proxy_mismatch": "The system proxy and environment proxy ports differ, which is a common cause of Codex token exchange failures.",
            "note_localhost": "The system proxy does not explicitly bypass localhost, which may break OAuth callbacks.",
            "note_login_missing_healthy": "Network configuration looks healthy, but Codex credentials were not detected. Sign in inside Codex or use device code login.",
            "note_login_missing": "~/.codex/auth.json was not detected. Sign in again after repairing the network path.",
            "note_client_login_missing": "{client} credentials were not detected. Sign in again or configure an API key after repairing the network path.",
            "fix_sync_proxy": "Sync the user environment proxy to the system proxy {url}",
            "fix_clear_proxy": "Clear invalid user-level proxy environment variables",
            "fix_no_proxy": "Set NO_PROXY so localhost does not use the proxy",
            "fix_flush_dns": "Flush the Windows DNS resolver cache",
            "fix_winsock_reset": "Reset the Windows Winsock catalog (restart required)",
            "fix_firewall_allow": "Add a Windows Firewall outbound allow rule for the target client: {path}",
            "fix_inspect_port": "Inspect and close the process using port 1455, then retry sign-in",
            "fix_ca": "Configure a client-level enterprise CA certificate path for {client} without importing it into the system trust store",
            "fix_device_auth": "Use device code login",
            "fix_claude_login": "Sign in to Claude Code or configure ANTHROPIC_API_KEY",
            "fix_gemini_login": "Sign in to Gemini CLI or configure GEMINI_API_KEY / GOOGLE_API_KEY",
            "fix_restart_codex": "Fully quit and restart Codex Desktop so new environment variables take effect",
            "command_restart_codex": "Close Codex manually, reopen it, then click \"Sign in with ChatGPT\"",
            "fix_device_auth_oauth": "Use device code login when browser OAuth fails",
        },
    }
    text = catalog.get(locale, catalog["zh"]).get(key, catalog["zh"].get(key, key))
    return text.format(**kwargs) if kwargs else text
