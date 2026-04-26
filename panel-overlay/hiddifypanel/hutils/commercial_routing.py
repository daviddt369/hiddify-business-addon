import ipaddress
import re
from dataclasses import asdict, dataclass
from typing import Any

from hiddifypanel.models import ConfigEnum
from hiddifypanel.models.commercial_routing_custom_rule import CommercialRoutingCustomRule

PREFIX_MAP = {
    "domain": "domain_exact",
    "suffix": "domain_suffix",
    "wildcard": "domain_wildcard",
    "regex": "domain_regex",
    "ip": "ip",
    "cidr": "cidr",
    "cidr6": "cidr",
}


@dataclass
class BulkParseError:
    line_no: int
    raw: str
    error: str


@dataclass
class RouteSimulationResult:
    input_value: str
    normalized_input: str
    matched_rule: str | None
    source: str
    outbound: str
    note: str | None = None


def _idna_host(host: str) -> str:
    labels = [p.encode("idna").decode("ascii") for p in host.split(".") if p]
    return ".".join(labels)


def normalize_domain_rule(rule_type: str, value: str) -> str:
    v = value.strip().lower()

    if rule_type == "domain_regex":
        re.compile(v)
        return v

    if rule_type == "domain_wildcard":
        if not v.startswith("*."):
            raise ValueError("wildcard rule must start with '*.'")
        v = v[2:]

    if rule_type == "domain_suffix" and v.startswith("."):
        v = v[1:]

    if not v:
        raise ValueError("empty domain value")

    return _idna_host(v)


def normalize_ip_rule(rule_type: str, value: str) -> str:
    v = value.strip().lower()
    if rule_type == "ip":
        return str(ipaddress.ip_address(v))
    if rule_type == "cidr":
        return str(ipaddress.ip_network(v, strict=False))
    raise ValueError("unsupported ip rule")


def validate_custom_rule(rule_type: str, value: str) -> tuple[bool, str | None, str | None]:
    if rule_type not in set(PREFIX_MAP.values()):
        return False, None, "unsupported rule type"
    try:
        if rule_type.startswith("domain_"):
            normalized = normalize_domain_rule(rule_type, value)
        else:
            normalized = normalize_ip_rule(rule_type, value)
    except Exception as exc:
        return False, None, str(exc)
    return True, normalized, None


def parse_bulk_rules(text: str) -> tuple[list[dict[str, Any]], list[BulkParseError]]:
    rules = []
    errors = []
    for idx, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            errors.append(BulkParseError(idx, raw, "missing ':' separator"))
            continue
        prefix, value = line.split(":", 1)
        prefix = prefix.strip().lower()
        value = value.strip()
        if prefix not in PREFIX_MAP:
            errors.append(BulkParseError(idx, raw, f"unknown prefix '{prefix}'"))
            continue
        rule_type = PREFIX_MAP[prefix]
        ok, normalized, err = validate_custom_rule(rule_type, value)
        if not ok:
            errors.append(BulkParseError(idx, raw, err or "invalid rule"))
            continue
        rules.append({
            "rule_type": rule_type,
            "value": value,
            "normalized_value": normalized,
            "enabled": True,
            "outbound_policy": "direct_ru",
        })
    return rules, errors


def parse_builtin_suffixes(raw_suffixes: str) -> list[str]:
    out = []
    seen = set()
    for raw in (raw_suffixes or "").split(","):
        item = raw.strip().lower()
        if not item:
            continue
        if item.startswith("."):
            item = item[1:]
        item = _idna_host(item)
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def suffix_to_xray_tld_regex(suffix: str) -> str:
    return f"regexp:.*\\.{re.escape(suffix)}$"


def load_enabled_custom_rules() -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "rule_type": r.rule_type,
            "value": r.value,
            "normalized_value": r.normalized_value,
            "outbound_policy": r.outbound_policy,
            "enabled": r.enabled,
            "comment": r.comment,
        }
        for r in CommercialRoutingCustomRule.query.filter_by(enabled=True).order_by(CommercialRoutingCustomRule.id.asc()).all()
    ]




def _cfg(hconfigs: dict[str, Any], key: ConfigEnum, default: Any = None) -> Any:
    return hconfigs.get(key, default)


def build_preview(hconfigs: dict[str, Any], custom_rules: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "layer1_enabled": bool(_cfg(hconfigs, ConfigEnum.commercial_routing_enable)),
        "router_core_type": _cfg(hconfigs, ConfigEnum.commercial_router_core_type, "xray"),
        "router_target": "/etc/xray-router/config.json",
        "custom_rules_total": len(custom_rules),
        "builtin_ru_suffixes": parse_builtin_suffixes(_cfg(hconfigs, ConfigEnum.commercial_ru_domain_suffixes, "")),
        "geoip_enabled": bool(_cfg(hconfigs, ConfigEnum.commercial_ru_geoip_enabled)),
        "apply_required": True,
        "apply_notice": "Настройки сохранены, но router-core config не применён. Запустите commercial-routing apply.",
    }


def simulate_route_match(input_value: str, hconfigs: dict[str, Any], custom_rules: list[dict[str, Any]]) -> RouteSimulationResult:
    normalized = input_value.strip().lower()
    try:
        ip = str(ipaddress.ip_address(normalized))
        for rule in custom_rules:
            if not rule.get("enabled"):
                continue
            if rule["rule_type"] == "ip" and rule["normalized_value"] == ip:
                return RouteSimulationResult(input_value, ip, ip, "custom_ru_ip", "direct-ru")
            if rule["rule_type"] == "cidr" and ipaddress.ip_address(ip) in ipaddress.ip_network(rule["normalized_value"], strict=False):
                return RouteSimulationResult(input_value, ip, rule["normalized_value"], "custom_ru_ip", "direct-ru")
        return RouteSimulationResult(
            input_value, ip, None, "geoip_runtime_not_simulated", "to-de",
            "GeoIP match is not simulated in UI; requires runtime router test."
        )
    except ValueError:
        pass

    host = _idna_host(normalized.lstrip("."))
    for rule in custom_rules:
        if not rule.get("enabled"):
            continue
        rt = rule["rule_type"]
        nv = rule["normalized_value"]
        if rt == "domain_exact" and host == nv:
            return RouteSimulationResult(input_value, host, nv, "custom_ru_domain", "direct-ru")
        if rt in ("domain_suffix", "domain_wildcard") and (host == nv or host.endswith("." + nv)):
            return RouteSimulationResult(input_value, host, nv, "custom_ru_domain", "direct-ru")
        if rt == "domain_regex" and re.search(nv, host):
            return RouteSimulationResult(input_value, host, nv, "custom_ru_domain", "direct-ru")

    for suffix in parse_builtin_suffixes(_cfg(hconfigs, ConfigEnum.commercial_ru_domain_suffixes, "")):
        if host == suffix or host.endswith("." + suffix):
            return RouteSimulationResult(input_value, host, suffix, "builtin_ru_suffix", "direct-ru")

    return RouteSimulationResult(input_value, host, None, "default_global", "to-de")
