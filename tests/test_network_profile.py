from authkit.checks import network_profile
from authkit.checks.network_profile import _key_facts, _score_profile
from authkit.models import ProxyEndpoint


def test_network_profile_score_good_exit():
    score, quality, reasons = _score_profile(
        {
            "public_ip": "203.0.113.10",
            "ai_endpoint_ok": True,
            "geo": {"country": "United States", "isp": "Example ISP"},
            "risk": {"trust_score": 90},
        }
    )

    assert score == 100
    assert quality == "good"
    assert reasons == []


def test_network_profile_score_penalizes_risky_exit():
    score, quality, reasons = _score_profile(
        {
            "public_ip": "203.0.113.10",
            "ai_endpoint_ok": False,
            "geo": {},
            "risk": {
                "is_tor": True,
                "is_proxy": True,
                "is_datacenter": True,
                "trust_score": 30,
            },
        }
    )

    assert score < 50
    assert quality in {"weak", "poor"}
    assert "ai_endpoint_unreachable" in reasons
    assert "proxy_or_vpn_risk" in reasons


def test_network_profile_key_facts_for_ui():
    facts = _key_facts(
        {
            "public_ip": "203.0.113.10",
            "ip_version": "IPv4",
            "cloudflare_location": "US",
            "cloudflare_colo": "SFO",
            "probe_path": "env_proxy",
            "ai_endpoint_ok": True,
            "score": 88,
            "quality": "good",
            "endpoint_probes": {"api_via_env": {"ok": True, "status": 200, "latency_ms": 115}},
            "geo": {"country": "United States", "region": "California", "city": "San Francisco", "isp": "Example ISP"},
            "risk": {
                "asn": 64500,
                "asOrganization": "Example Network",
                "isResidential": True,
                "is_vpn": False,
                "is_proxy": False,
                "trust_score": 91,
            },
        }
    )

    assert facts["ip"] == "203.0.113.10"
    assert facts["net_coffee_url"] == "https://ip.net.coffee/ip/203.0.113.10"
    assert facts["location"] == "United States California San Francisco"
    assert facts["isp"] == "Example ISP"
    assert facts["asn"] == 64500
    assert facts["risk_flags"] == ["residential"]
    assert facts["ai_endpoint_ok"] is True
    assert facts["country"] == "United States"
    assert facts["city"] == "San Francisco"
    assert facts["ip_attribute"] == "residential"
    assert facts["security_checks"]["vpn"] is False
    assert facts["security_checks"]["residential"] is True
    assert facts["availability"]["ok"] is True
    assert facts["availability"]["best_latency_ms"] == 115
    assert facts["dns_leak"]["status"] == "not_checked_desktop"
    assert facts["webrtc_udp_leak"]["status"] == "not_checked_desktop"


def test_network_profile_json_fetch_uses_proxy(monkeypatch):
    proxy = ProxyEndpoint("http", "127.0.0.1", 7890)
    calls = []

    def fake_fetch_text(url, *, proxy, timeout):
        calls.append((url, proxy, timeout))
        return '{"ok": true}'

    monkeypatch.setattr(network_profile, "_fetch_text", fake_fetch_text)

    data = network_profile._fetch_json("https://ip.net.coffee/api/geoip/203.0.113.10", proxy=proxy, timeout=1.5)

    assert data == {"ok": True}
    assert calls == [("https://ip.net.coffee/api/geoip/203.0.113.10", proxy, 1.5)]
