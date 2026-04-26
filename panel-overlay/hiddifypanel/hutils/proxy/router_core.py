from dataclasses import dataclass
from typing import Any

from hiddifypanel.hutils import commercial_routing
from hiddifypanel.models import ConfigEnum


@dataclass
class RouterRenderResult:
    config: dict[str, Any]
    target_path: str
    service_name: str
    core_type: str


def _cfg(hconfigs: dict[str, Any], key: ConfigEnum, default: Any = None) -> Any:
    return hconfigs.get(key, default)


def _xray_custom_rule(rule: dict[str, Any]) -> dict[str, Any]:
    rt = rule["rule_type"]
    nv = rule["normalized_value"]
    if rt == "domain_exact":
        return {"type": "field", "domain": [f"full:{nv}"], "outboundTag": "direct-ru"}
    if rt in ("domain_suffix", "domain_wildcard"):
        return {"type": "field", "domain": [f"domain:{nv}"], "outboundTag": "direct-ru"}
    if rt == "domain_regex":
        return {"type": "field", "domain": [f"regexp:{nv}"], "outboundTag": "direct-ru"}
    if rt in ("ip", "cidr"):
        return {"type": "field", "ip": [nv], "outboundTag": "direct-ru"}
    raise ValueError(f"unsupported rule_type {rt}")


def _xray_builtin_suffix_rules(hconfigs: dict[str, Any]) -> list[dict[str, Any]]:
    suffixes = commercial_routing.parse_builtin_suffixes(_cfg(hconfigs, ConfigEnum.commercial_ru_domain_suffixes, ""))
    if not suffixes:
        return []
    return [{
        "type": "field",
        "domain": [commercial_routing.suffix_to_xray_tld_regex(s) for s in suffixes],
        "outboundTag": "direct-ru",
    }]


def _xray_geoip_rules(hconfigs: dict[str, Any]) -> list[dict[str, Any]]:
    if not bool(_cfg(hconfigs, ConfigEnum.commercial_ru_geoip_enabled)):
        return []
    return [{"type": "field", "ip": ["geoip:ru"], "outboundTag": "direct-ru"}]


def _build_to_de_outbound(hconfigs: dict[str, Any]) -> dict[str, Any]:
    tunnel_type = _cfg(hconfigs, ConfigEnum.commercial_de_tunnel_type, "test_blackhole")
    if tunnel_type == "test_blackhole":
        return {"tag": "to-de", "protocol": "blackhole"}
    if tunnel_type == "vless":
        raise NotImplementedError("vless to-de renderer is not implemented yet")
    if tunnel_type == "trojan":
        raise NotImplementedError("trojan to-de renderer is not implemented yet")
    if tunnel_type == "wireguard":
        raise NotImplementedError("wireguard to-de renderer is not implemented yet")
    raise ValueError(f"unsupported commercial_de_tunnel_type {tunnel_type}")


def render_xray_router_config(hconfigs: dict[str, Any], custom_rules: list[dict[str, Any]]) -> dict[str, Any]:
    rules = []
    for rule in custom_rules:
        if rule.get("enabled"):
            rules.append(_xray_custom_rule(rule))
    rules.extend(_xray_builtin_suffix_rules(hconfigs))
    rules.extend(_xray_geoip_rules(hconfigs))
    rules.append({"type": "field", "network": "tcp,udp", "outboundTag": "to-de"})

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "tag": "from-hiddify",
            "listen": "127.0.0.1",
            "port": int(_cfg(hconfigs, ConfigEnum.commercial_router_port, 20808)),
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True, "ip": "127.0.0.1"},
            "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "routeOnly": True},
        }],
        "outbounds": [
            _build_to_de_outbound(hconfigs),
            {"tag": "direct-ru", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {"domainStrategy": "IPIfNonMatch", "rules": rules},
    }


def render_desired_config(hconfigs: dict[str, Any], custom_rules: list[dict[str, Any]]) -> RouterRenderResult:
    core_type = _cfg(hconfigs, ConfigEnum.commercial_router_core_type, "xray")
    if core_type != "xray":
        raise NotImplementedError("singbox-router generator is not implemented in first stage")
    return RouterRenderResult(
        config=render_xray_router_config(hconfigs, custom_rules),
        target_path="/etc/xray-router/config.json",
        service_name="xray-router",
        core_type="xray",
    )
