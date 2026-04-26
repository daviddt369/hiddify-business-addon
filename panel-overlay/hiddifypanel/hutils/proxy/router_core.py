from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from hiddifypanel.hutils import commercial_routing


@dataclass
class RouterRenderResult:
    config: dict[str, Any]
    target_path: str
    service_name: str
    core_type: str


def _first(params: dict[str, list[str]], *names: str, default: str = "") -> str:
    for name in names:
        values = params.get(name)
        if values and values[0] is not None:
            return unquote(str(values[0]))
    return default


def _split_csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def _as_bool(value: str) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


def _uri_params(uri: str):
    parsed = urlparse(uri.strip())
    params = parse_qs(parsed.query, keep_blank_values=True)
    return parsed, params


def _port(parsed, default: int = 443) -> int:
    return int(parsed.port or default)


def _host(parsed) -> str:
    host = parsed.hostname
    if not host:
        raise ValueError("DE URI host is empty")
    return host


def _build_stream_settings(params: dict[str, list[str]], fallback_host: str, fallback_port: int) -> dict[str, Any]:
    network = _first(params, "type", "network", default="tcp").lower()
    if network == "h2":
        network = "http"

    security = _first(params, "security", default="tls" if fallback_port == 443 else "none").lower()

    stream: dict[str, Any] = {
        "network": network,
        "security": security,
    }

    sni = _first(params, "sni", "serverName", default=fallback_host)
    alpn = _split_csv(_first(params, "alpn", default=""))
    fp = _first(params, "fp", "fingerprint", default="")
    allow_insecure = _first(params, "allowInsecure", "allow_insecure", default="")

    if security == "tls":
        tls: dict[str, Any] = {}
        if sni:
            tls["serverName"] = sni
        if alpn:
            tls["alpn"] = alpn
        if fp:
            tls["fingerprint"] = fp
        if allow_insecure:
            tls["allowInsecure"] = _as_bool(allow_insecure)
        stream["tlsSettings"] = tls

    elif security == "reality":
        reality: dict[str, Any] = {}
        if sni:
            reality["serverName"] = sni
        if fp:
            reality["fingerprint"] = fp

        pbk = _first(params, "pbk", "publicKey", default="")
        sid = _first(params, "sid", "shortId", default="")
        spider_x = _first(params, "spx", "spiderX", default="")

        if pbk:
            reality["publicKey"] = pbk
        if sid:
            reality["shortId"] = sid
        if spider_x:
            reality["spiderX"] = spider_x

        stream["realitySettings"] = reality

    elif security == "none":
        pass

    else:
        raise ValueError(f"Unsupported security: {security}")

    path = _first(params, "path", default="")
    host_header = _first(params, "host", default="")
    service_name = _first(params, "serviceName", "service_name", default="")

    if network == "ws":
        ws: dict[str, Any] = {}
        if path:
            ws["path"] = path
        if host_header:
            ws["headers"] = {"Host": host_header}
        stream["wsSettings"] = ws

    elif network == "grpc":
        grpc: dict[str, Any] = {}
        if service_name:
            grpc["serviceName"] = service_name
        if host_header:
            grpc["authority"] = host_header
        stream["grpcSettings"] = grpc

    elif network == "httpupgrade":
        httpupgrade: dict[str, Any] = {}
        if path:
            httpupgrade["path"] = path
        if host_header:
            httpupgrade["host"] = host_header
        stream["httpupgradeSettings"] = httpupgrade

    elif network == "xhttp":
        xhttp: dict[str, Any] = {}
        if path:
            xhttp["path"] = path
        if host_header:
            xhttp["host"] = host_header
        stream["xhttpSettings"] = xhttp

    elif network in {"tcp", "http"}:
        pass

    else:
        raise ValueError(f"Unsupported network type: {network}")

    return stream


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

    raise ValueError(f"Unsupported rule_type: {rt}")


def _xray_builtin_suffix_rules(hconfigs: dict[str, Any]) -> list[dict[str, Any]]:
    suffixes = commercial_routing.parse_builtin_suffixes(
        hconfigs.get("commercial_ru_domain_suffixes", "")
    )
    if not suffixes:
        return []

    return [{
        "type": "field",
        "domain": [commercial_routing.suffix_to_xray_tld_regex(s) for s in suffixes],
        "outboundTag": "direct-ru",
    }]


def _xray_geoip_rules(hconfigs: dict[str, Any]) -> list[dict[str, Any]]:
    if not bool(hconfigs.get("commercial_ru_geoip_enabled")):
        return []

    return [{
        "type": "field",
        "ip": ["geoip:ru"],
        "outboundTag": "direct-ru",
    }]


def _build_vless_outbound(uri: str) -> dict[str, Any]:
    if not uri or not uri.strip():
        raise ValueError("commercial_de_vless_uri is empty")

    parsed, params = _uri_params(uri)

    if parsed.scheme.lower() != "vless":
        raise ValueError("DE VLESS URI must start with vless://")

    user_id = unquote(parsed.username or "")
    if not user_id:
        raise ValueError("VLESS UUID is empty")

    host = _host(parsed)
    port = _port(parsed, 443)

    user: dict[str, Any] = {
        "id": user_id,
        "encryption": _first(params, "encryption", default="none"),
    }

    flow = _first(params, "flow", default="")
    if flow:
        user["flow"] = flow

    return {
        "tag": "to-de",
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": host,
                    "port": port,
                    "users": [user],
                }
            ]
        },
        "streamSettings": _build_stream_settings(params, host, port),
    }


def _build_trojan_outbound(uri: str) -> dict[str, Any]:
    if not uri or not uri.strip():
        raise ValueError("commercial_de_trojan_uri is empty")

    parsed, params = _uri_params(uri)

    if parsed.scheme.lower() != "trojan":
        raise ValueError("DE Trojan URI must start with trojan://")

    password = unquote(parsed.username or "")
    if not password:
        raise ValueError("Trojan password is empty")

    host = _host(parsed)
    port = _port(parsed, 443)

    return {
        "tag": "to-de",
        "protocol": "trojan",
        "settings": {
            "servers": [
                {
                    "address": host,
                    "port": port,
                    "password": password,
                }
            ]
        },
        "streamSettings": _build_stream_settings(params, host, port),
    }


def _read_secret_ref(ref: str) -> str:
    ref = (ref or "").strip()

    if not ref:
        raise ValueError("commercial_de_private_key_ref is empty")

    if ref.startswith("env:"):
        name = ref[4:].strip()
        value = os.environ.get(name, "")
        if not value:
            raise ValueError(f"Environment variable is empty: {name}")
        return value.strip()

    if ref.startswith("file:"):
        path = ref[5:].strip()
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()

    if os.path.exists(ref):
        with open(ref, "r", encoding="utf-8") as f:
            return f.read().strip()

    return ref


def _build_wireguard_outbound(hconfigs: dict[str, Any]) -> dict[str, Any]:
    endpoint = (hconfigs.get("commercial_de_endpoint") or "").strip()
    public_key = (hconfigs.get("commercial_de_public_key") or "").strip()
    private_key = _read_secret_ref(hconfigs.get("commercial_de_private_key_ref") or "")

    if not endpoint:
        raise ValueError("commercial_de_endpoint is required for wireguard")
    if not public_key:
        raise ValueError("commercial_de_public_key is required for wireguard")

    address_raw = (hconfigs.get("commercial_de_vless_uri") or "").strip()
    addresses = _split_csv(address_raw) if address_raw else ["10.66.66.2/32"]

    mtu_raw = (hconfigs.get("commercial_de_trojan_uri") or "").strip()
    mtu = int(mtu_raw) if mtu_raw else 1280

    return {
        "tag": "to-de",
        "protocol": "wireguard",
        "settings": {
            "secretKey": private_key,
            "address": addresses,
            "peers": [
                {
                    "publicKey": public_key,
                    "endpoint": endpoint,
                    "allowedIPs": ["0.0.0.0/0", "::/0"],
                }
            ],
            "mtu": mtu,
        },
    }


def _build_to_de_outbound(hconfigs: dict[str, Any]) -> dict[str, Any]:
    tunnel_type = (hconfigs.get("commercial_de_tunnel_type") or "test_blackhole").strip().lower()

    if tunnel_type == "test_blackhole":
        return {"tag": "to-de", "protocol": "blackhole"}

    if tunnel_type == "vless":
        return _build_vless_outbound(hconfigs.get("commercial_de_vless_uri") or "")

    if tunnel_type == "trojan":
        return _build_trojan_outbound(hconfigs.get("commercial_de_trojan_uri") or "")

    if tunnel_type == "wireguard":
        return _build_wireguard_outbound(hconfigs)

    raise ValueError(f"Unsupported commercial_de_tunnel_type: {tunnel_type}")


def render_xray_router_config(hconfigs: dict[str, Any], custom_rules: list[dict[str, Any]]) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []

    for rule in custom_rules:
        if rule.get("enabled"):
            rules.append(_xray_custom_rule(rule))

    rules.extend(_xray_builtin_suffix_rules(hconfigs))
    rules.extend(_xray_geoip_rules(hconfigs))

    rules.append({
        "type": "field",
        "network": "tcp,udp",
        "outboundTag": "to-de",
    })

    return {
        "log": {
            "loglevel": "warning"
        },
        "inbounds": [
            {
                "tag": "from-hiddify",
                "listen": "127.0.0.1",
                "port": int(hconfigs.get("commercial_router_port", 20808)),
                "protocol": "socks",
                "settings": {
                    "auth": "noauth",
                    "udp": True,
                    "ip": "127.0.0.1",
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                    "routeOnly": True,
                },
            }
        ],
        "outbounds": [
            _build_to_de_outbound(hconfigs),
            {
                "tag": "direct-ru",
                "protocol": "freedom",
            },
            {
                "tag": "block",
                "protocol": "blackhole",
            },
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": rules,
        },
    }


def render_desired_config(hconfigs: dict[str, Any], custom_rules: list[dict[str, Any]]) -> RouterRenderResult:
    core_type = (hconfigs.get("commercial_router_core_type") or "xray").strip().lower()

    if core_type != "xray":
        raise NotImplementedError("singbox-router generator is not implemented in first stage")

    return RouterRenderResult(
        config=render_xray_router_config(hconfigs, custom_rules),
        target_path="/etc/xray-router/config.json",
        service_name="xray-router",
        core_type="xray",
    )