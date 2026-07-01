from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from authkit import __version__
from authkit.models import ProxyEndpoint


TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"
NET_COFFEE_IP_PAGE_URL = "https://ip.net.coffee/ip/{ip}"
NET_COFFEE_GEO_URL = "https://ip.net.coffee/api/geoip/{ip}"
NET_COFFEE_RISK_URL = "https://ip.net.coffee/api/iprisk/{ip}"


def collect_network_profile(
    *,
    client: str,
    env_endpoint: ProxyEndpoint,
    system_endpoint: ProxyEndpoint,
    endpoint_probes: dict[str, dict[str, Any]],
    timeout: float = 2.5,
) -> dict[str, Any]:
    proxy = env_endpoint if env_endpoint.is_set else system_endpoint if system_endpoint.is_set else None
    profile: dict[str, Any] = {
        "client": client,
        "probe_path": "env_proxy" if env_endpoint.is_set else "system_proxy" if system_endpoint.is_set else "direct",
        "public_ip": "",
        "ip_version": "",
        "cloudflare_location": "",
        "geo": {},
        "risk": {},
        "key_facts": {},
        "endpoint_probes": endpoint_probes,
        "ai_endpoint_ok": _endpoint_ok(endpoint_probes),
        "score": 0,
        "quality": "unknown",
        "summary": "",
        "sources": {
            "ip_page": "https://ip.net.coffee/ip/{ip}",
            "trace": TRACE_URL,
            "geo": "https://ip.net.coffee/api/geoip/{ip}",
            "risk": "https://ip.net.coffee/api/iprisk/{ip}",
        },
    }

    trace = _fetch_trace(proxy=proxy, timeout=timeout)
    profile.update(trace)

    ip = str(profile.get("public_ip") or "")
    if ip:
        profile["geo"] = _fetch_json(NET_COFFEE_GEO_URL.format(ip=ip), proxy=proxy, timeout=timeout)
        profile["risk"] = _fetch_json(NET_COFFEE_RISK_URL.format(ip=ip), proxy=proxy, timeout=timeout)

    score, quality, reasons = _score_profile(profile)
    profile["score"] = score
    profile["quality"] = quality
    profile["reasons"] = reasons
    profile["key_facts"] = _key_facts(profile)
    profile["summary"] = _summary(profile)
    return profile


def _fetch_trace(*, proxy: ProxyEndpoint | None, timeout: float) -> dict[str, str]:
    started = time.monotonic()
    text = _fetch_text(TRACE_URL, proxy=proxy, timeout=timeout)
    entries = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            entries[key.strip()] = value.strip()
    ip = entries.get("ip", "")
    return {
        "public_ip": ip,
        "ip_version": "IPv6" if ":" in ip else "IPv4" if ip else "",
        "cloudflare_location": entries.get("loc", ""),
        "cloudflare_colo": entries.get("colo", ""),
        "trace_latency_ms": str(int((time.monotonic() - started) * 1000)),
    }


def _fetch_text(url: str, *, proxy: ProxyEndpoint | None, timeout: float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": f"authkit/{__version__}"})
    handlers: list[urllib.request.BaseHandler] = []
    if proxy and proxy.is_set:
        handlers.append(urllib.request.ProxyHandler({"http": proxy.url, "https": proxy.url}))
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.read(64_000).decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError, TimeoutError):
        return ""


def _fetch_json(url: str, *, proxy: ProxyEndpoint | None, timeout: float) -> dict[str, Any]:
    try:
        data = json.loads(_fetch_text(url, proxy=proxy, timeout=timeout))
        return data if isinstance(data, dict) else {}
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {}


def _endpoint_ok(endpoint_probes: dict[str, dict[str, Any]]) -> bool:
    names = ("oauth_via_env", "oauth_via_system", "oauth_direct", "api_via_env", "api_via_system")
    return any(bool(endpoint_probes.get(name, {}).get("ok")) for name in names)


def _score_profile(profile: dict[str, Any]) -> tuple[int, str, list[str]]:
    score = 100
    reasons: list[str] = []
    if not profile.get("public_ip"):
        score -= 30
        reasons.append("public_ip_unavailable")
    if not profile.get("ai_endpoint_ok"):
        score -= 25
        reasons.append("ai_endpoint_unreachable")

    risk = profile.get("risk") if isinstance(profile.get("risk"), dict) else {}
    if any(risk.get(key) for key in ("is_tor", "is_proxy", "is_vpn")):
        score -= 20
        reasons.append("proxy_or_vpn_risk")
    if risk.get("is_datacenter"):
        score -= 12
        reasons.append("datacenter_exit")
    trust = risk.get("trust_score")
    if isinstance(trust, (int, float)) and trust < 60:
        score -= 12
        reasons.append("low_trust_score")
    if not profile.get("geo"):
        score -= 5
        reasons.append("geo_unavailable")

    score = max(0, min(100, score))
    if score >= 80:
        quality = "good"
    elif score >= 60:
        quality = "fair"
    elif score >= 40:
        quality = "weak"
    else:
        quality = "poor"
    return score, quality, reasons


def _summary(profile: dict[str, Any]) -> str:
    geo = profile.get("geo") if isinstance(profile.get("geo"), dict) else {}
    risk = profile.get("risk") if isinstance(profile.get("risk"), dict) else {}
    location = " ".join(str(geo.get(key) or "") for key in ("country", "region", "city")).strip()
    isp = str(geo.get("isp") or risk.get("asOrganization") or risk.get("company_name") or "").strip()
    ip = profile.get("public_ip") or "unknown"
    endpoint = "AI endpoints reachable" if profile.get("ai_endpoint_ok") else "AI endpoints blocked"
    return f"IP {ip} | {location or 'geo unknown'} | {isp or 'ISP unknown'} | score {profile['score']} {profile['quality']} | {endpoint}"


def _ip_attribute(risk: dict[str, Any]) -> str:
    company_type = str(risk.get("company_type") or "").strip().lower()
    if risk.get("is_datacenter") or company_type in {"hosting", "cdn", "business"}:
        return "hosting"
    if risk.get("isResidential"):
        return "residential"
    if risk.get("is_mobile"):
        return "mobile"
    return company_type or "unknown"


def _security_checks(risk: dict[str, Any]) -> dict[str, bool]:
    return {
        "vpn": bool(risk.get("is_vpn")),
        "proxy": bool(risk.get("is_proxy")),
        "tor": bool(risk.get("is_tor")),
        "crawler": bool(risk.get("is_crawler")),
        "abuse": bool(risk.get("is_abuser")),
        "datacenter": bool(risk.get("is_datacenter")),
        "residential": bool(risk.get("isResidential")),
    }


def _availability(endpoint_probes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    probes: list[dict[str, Any]] = []
    for name, probe in endpoint_probes.items():
        if not isinstance(probe, dict):
            continue
        latency = probe.get("latency_ms")
        probes.append(
            {
                "name": name,
                "ok": bool(probe.get("ok")),
                "status": probe.get("status"),
                "latency_ms": latency if isinstance(latency, int) else None,
            }
        )
    successful_latencies = [
        int(probe["latency_ms"])
        for probe in probes
        if probe.get("ok") and isinstance(probe.get("latency_ms"), int)
    ]
    return {
        "ok": any(bool(probe.get("ok")) for probe in probes),
        "best_latency_ms": min(successful_latencies) if successful_latencies else None,
        "probes": probes,
    }


def _key_facts(profile: dict[str, Any]) -> dict[str, Any]:
    geo = profile.get("geo") if isinstance(profile.get("geo"), dict) else {}
    risk = profile.get("risk") if isinstance(profile.get("risk"), dict) else {}
    endpoint_probes = profile.get("endpoint_probes") if isinstance(profile.get("endpoint_probes"), dict) else {}
    ip = str(profile.get("public_ip") or "")
    location = " ".join(str(geo.get(key) or risk.get(key) or "") for key in ("country", "region", "city")).strip()
    isp = str(geo.get("isp") or risk.get("asOrganization") or risk.get("company_name") or "").strip()
    asn = risk.get("asn") or ""
    as_org = str(risk.get("asOrganization") or risk.get("company_name") or "").strip()
    company_type = str(risk.get("company_type") or "").strip()
    risk_flags = [
        label
        for key, label in (
            ("is_datacenter", "datacenter"),
            ("isResidential", "residential"),
            ("is_vpn", "vpn"),
            ("is_proxy", "proxy"),
            ("is_tor", "tor"),
            ("is_crawler", "crawler"),
            ("is_abuser", "abuse_history"),
            ("is_mobile", "mobile"),
        )
        if risk.get(key)
    ]
    return {
        "ip": ip,
        "ip_version": profile.get("ip_version") or "",
        "net_coffee_url": NET_COFFEE_IP_PAGE_URL.format(ip=ip) if ip else "https://ip.net.coffee/ip/",
        "location": location,
        "country_code": geo.get("country_code") or risk.get("countryCode") or "",
        "country": geo.get("country") or risk.get("country") or "",
        "region": geo.get("region") or risk.get("region") or "",
        "city": geo.get("city") or risk.get("city") or "",
        "isp": isp,
        "asn": asn,
        "as_organization": as_org,
        "company_type": company_type,
        "ip_attribute": _ip_attribute(risk),
        "security_checks": _security_checks(risk),
        "risk_flags": risk_flags,
        "trust_score": risk.get("trust_score", ""),
        "abuser_score": risk.get("abuser_score", ""),
        "rdns": risk.get("rdns", ""),
        "cloudflare_location": profile.get("cloudflare_location") or "",
        "cloudflare_colo": profile.get("cloudflare_colo") or "",
        "score": profile.get("score", 0),
        "quality": profile.get("quality", "unknown"),
        "probe_path": profile.get("probe_path") or "",
        "ai_endpoint_ok": bool(profile.get("ai_endpoint_ok")),
        "availability": _availability(endpoint_probes),
        "dns_leak": {
            "status": "not_checked_desktop",
            "note": "Browser DNS leak testing is not executed by the desktop diagnostic.",
        },
        "webrtc_udp_leak": {
            "status": "not_checked_desktop",
            "note": "Browser WebRTC UDP leak testing is not executed by the desktop diagnostic.",
        },
    }
