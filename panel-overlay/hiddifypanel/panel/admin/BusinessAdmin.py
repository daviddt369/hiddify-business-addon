import json
import re

import wtforms as wtf
from flask import redirect, render_template, request
from flask_babel import lazy_gettext as _
from flask_classful import FlaskView
from flask_wtf import FlaskForm

from hiddifypanel import hutils
from hiddifypanel.auth import login_required
from hiddifypanel.database import db
from hiddifypanel.models import ConfigEnum, Role, get_hconfigs, hconfig, set_hconfig
from hiddifypanel.models.commercial_routing_custom_rule import CommercialRoutingCustomRule
from hiddifypanel.panel import hiddify
from hiddifypanel.panel.commercial.telegrambot.secrets import telegram_bot_token, telegram_payment_provider_token
from hiddifypanel.hutils import commercial_routing

# BEGIN COMMERCIAL ROUTING EDITABLE UI CONFIG
COMMERCIAL_ROUTING_DIRECT_DNS_KEY = "commercial_direct_dns_servers"
COMMERCIAL_ROUTING_PROXY_DNS_KEY = "commercial_proxy_dns_servers"
COMMERCIAL_ROUTING_BLOCKED_DOMAINS_KEY = "commercial_blocked_domains"
COMMERCIAL_ROUTING_UI_PRIMARY_PATH = commercial_routing.COMMERCIAL_ROUTING_UI_PRIMARY_PATH
COMMERCIAL_ROUTING_UI_LEGACY_PATH = commercial_routing.COMMERCIAL_ROUTING_UI_LEGACY_PATH

DEFAULT_COMMERCIAL_ROUTING_DIRECT_DNS = "77.88.8.8\n77.88.8.1"
DEFAULT_COMMERCIAL_ROUTING_PROXY_DNS = "1.1.1.1\n1.0.0.1\n8.8.8.8\n8.8.4.4"
DEFAULT_COMMERCIAL_ROUTING_BLOCKED_DOMAINS = "gosuslugi.ru\ngslb.gosuslugi.ru\ngu-st.ru\nnalog.ru\nnalog.gov.ru"


def _commercial_routing_config_text(key, default):
    try:
        from pathlib import Path

        routing_ui_paths = tuple(Path(p) for p in commercial_routing.commercial_routing_ui_read_paths())

        for routing_ui_path in routing_ui_paths:
            if not routing_ui_path.exists():
                continue

            try:
                data = json.loads(routing_ui_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            if not isinstance(data, dict):
                continue

            value = data.get(key)
            value = "" if value is None else str(value)
            value = value.replace("\r\n", "\n").replace("\r", "\n")

            if value.strip():
                return value
    except Exception:
        pass

    return default
# END COMMERCIAL ROUTING EDITABLE UI CONFIG


class BusinessSettingsForm(FlaskForm):
    telegram_bot_token = wtf.StringField(_("Токен Telegram бота"), validators=[wtf.validators.Optional(), wtf.validators.Regexp(r"^([0-9]{8,12}:[a-zA-Z0-9_-]{30,40})$", re.IGNORECASE, _("config.Invalid_telegram_bot_token"))], description=_("Токен из @BotFather для работы коммерческого Telegram-бота."), render_kw={"class": "ltr", "placeholder": "123456789:AA..."})
    telegram_webhook_domain = wtf.StringField(_("Домен Telegram webhook"), validators=[wtf.validators.Optional(), wtf.validators.Regexp(r"^([A-Za-z0-9.-]+\.[A-Za-z]{2,})$", re.IGNORECASE, _("config.Invalid_domain"))], description=_("Фиксированный домен для webhook. Если пусто - используется домен панели (полезно для стабильности webhook при нескольких direct-доменах)."), render_kw={"class": "ltr", "placeholder": "tgbot.example.com"})
    telegram_payment_provider_token = wtf.StringField(_("YooKassa provider token (Telegram payments)"), validators=[wtf.validators.Optional(), wtf.validators.Regexp(r"^([0-9]{5,}:[A-Za-z0-9_:-]+)$", re.IGNORECASE, _("Invalid YooKassa/Telegram provider token"))], description=_("Токен Telegram Payments provider (YooKassa через BotFather)."), render_kw={"class": "ltr"})
    support_url = wtf.StringField(_("Ссылка поддержки"), validators=[wtf.validators.Optional(), wtf.validators.Regexp(r"^(https?://|tg://|mailto:|tel:).+", re.IGNORECASE, _("Invalid support URL"))], description=_("Ссылка поддержки для пользователя, которая есть у него (например в меню или кнопке обращения к администратору)."), render_kw={"class": "ltr"})
    telegram_instruction_button_text = wtf.StringField(_("Текст кнопки инструкции"), validators=[wtf.validators.Optional(), wtf.validators.Length(max=64)], description=_("Текст reply-кнопки, которая отправляет сохранённое приветственное сообщение."))
    telegram_welcome_message = wtf.TextAreaField(_("Приветственное сообщение / инструкция"), validators=[wtf.validators.Optional(), wtf.validators.Length(max=4000)], description=_("Сообщение один раз для новых пользователей Telegram и по кнопке Инструкция. Поддерживается HTML и ссылки."), render_kw={"rows": 8})
    telegram_subscription_expiry_reminder_days = wtf.StringField(_("Дни до напоминания о продлении"), validators=[wtf.validators.Optional(), wtf.validators.Length(max=64)], description=_("Список через запятую, например 2,1. Бот напомнит за столько дней до окончания подписки."))
    telegram_subscription_expiry_reminder_message = wtf.TextAreaField(_("Текст напоминания о продлении"), validators=[wtf.validators.Optional(), wtf.validators.Length(max=4000)], description=_("Текст автоматического напоминания в Telegram. Доступен плейсхолдер {days_left}."), render_kw={"rows": 5})

    commercial_routing_enable = wtf.BooleanField("Enable commercial routing redirect")
    commercial_router_host = wtf.StringField("Commercial router host", validators=[wtf.validators.Optional(), wtf.validators.Length(max=255)])
    commercial_router_port = wtf.StringField("Commercial router port", validators=[wtf.validators.Optional(), wtf.validators.Length(max=8)])
    commercial_router_protocol = wtf.SelectField("Commercial router protocol", choices=[("socks5", "socks5")])
    commercial_apply_to_xray = wtf.BooleanField("Apply redirect to Xray")
    commercial_apply_to_singbox = wtf.BooleanField("Apply redirect to sing-box")
    commercial_domestic_policy = wtf.SelectField("Domestic policy", choices=[("keep_hiddify", "keep_hiddify"), ("send_to_router", "send_to_router"), ("direct_ru", "direct_ru"), ("block", "block")])
    commercial_udp443_policy = wtf.SelectField("UDP/443 policy", choices=[("keep_block", "keep_block"), ("allow_to_router", "allow_to_router")])

    commercial_ru_domain_suffixes = wtf.StringField("Builtin RU suffixes")
    commercial_ru_geoip_enabled = wtf.BooleanField("Enable geoip:ru in router-core")
    commercial_default_global_policy = wtf.SelectField("Default global policy", choices=[("to_de", "to_de")])
    commercial_router_core_type = wtf.SelectField("Router-core type", choices=[("xray", "xray")])
    commercial_de_tunnel_type = wtf.SelectField("DE tunnel type", choices=[("test_blackhole", "test_blackhole"), ("vless", "vless"), ("trojan", "trojan"), ("wireguard", "wireguard")])
    commercial_de_endpoint = wtf.StringField("DE endpoint")
    commercial_de_public_key = wtf.StringField("DE public key")
    commercial_de_private_key_ref = wtf.StringField("DE private key ref")
    commercial_de_vless_uri = wtf.TextAreaField("DE VLESS URI", render_kw={"rows": 3})
    commercial_de_trojan_uri = wtf.TextAreaField("DE Trojan URI", render_kw={"rows": 3})


    # BEGIN COMMERCIAL ROUTING EDITABLE UI FIELDS
    commercial_blocked_domains = wtf.TextAreaField(
        "Blocked sensitive domains",
        validators=[wtf.validators.Optional()],
        description="Домены для blackhole. Один домен на строку. Можно писать gosuslugi.ru или domain:gosuslugi.ru.",
        render_kw={"rows": 6},
    )
    commercial_direct_dns_servers = wtf.TextAreaField(
        "Direct DNS servers",
        validators=[wtf.validators.Optional()],
        description="DNS для RU/direct маршрута. Один IP на строку.",
        render_kw={"rows": 4},
    )
    commercial_proxy_dns_servers = wtf.TextAreaField(
        "Proxy / Global DNS servers",
        validators=[wtf.validators.Optional()],
        description="DNS для global/to-de маршрута. Один IP на строку.",
        render_kw={"rows": 4},
    )
    # END COMMERCIAL ROUTING EDITABLE UI FIELDS

    custom_ru_rules_bulk = wtf.TextAreaField("Custom RU rules bulk import", render_kw={"rows": 6})
    test_route_input = wtf.StringField("Test route input")
    submit = wtf.SubmitField(_("Сохранить"))


class BusinessAdmin(FlaskView):
    decorators = [login_required(roles={Role.super_admin})]

    def _build_form(self):
        form = BusinessSettingsForm(
            telegram_bot_token=telegram_bot_token(),
            telegram_webhook_domain=hconfig(ConfigEnum.telegram_webhook_domain) or "",
            telegram_payment_provider_token=telegram_payment_provider_token(),
            support_url=hconfig(ConfigEnum.support_url) or "",
            telegram_instruction_button_text=hconfig(ConfigEnum.telegram_instruction_button_text) or "Инструкция",
            telegram_welcome_message=hconfig(ConfigEnum.telegram_welcome_message) or "",
            telegram_subscription_expiry_reminder_days=hconfig(ConfigEnum.telegram_subscription_expiry_reminder_days) or "2,1",
            telegram_subscription_expiry_reminder_message=hconfig(ConfigEnum.telegram_subscription_expiry_reminder_message) or "У вас заканчивается подписка через {days_left} дн. Не забудьте продлить тариф.",
            commercial_routing_enable=bool(hconfig(ConfigEnum.commercial_routing_enable)),
            commercial_router_host=hconfig(ConfigEnum.commercial_router_host) or "127.0.0.1",
            commercial_router_port=hconfig(ConfigEnum.commercial_router_port) or "20808",
            commercial_router_protocol=hconfig(ConfigEnum.commercial_router_protocol) or "socks5",
            commercial_apply_to_xray=bool(hconfig(ConfigEnum.commercial_apply_to_xray)),
            commercial_apply_to_singbox=bool(hconfig(ConfigEnum.commercial_apply_to_singbox)),
            commercial_domestic_policy=hconfig(ConfigEnum.commercial_domestic_policy) or "keep_hiddify",
            commercial_udp443_policy=hconfig(ConfigEnum.commercial_udp443_policy) or "keep_block",
            commercial_ru_domain_suffixes=hconfig(ConfigEnum.commercial_ru_domain_suffixes) or ".ru,.su,.xn--p1ai",
            commercial_ru_geoip_enabled=bool(hconfig(ConfigEnum.commercial_ru_geoip_enabled)),
            commercial_default_global_policy=hconfig(ConfigEnum.commercial_default_global_policy) or "to_de",
            commercial_router_core_type=hconfig(ConfigEnum.commercial_router_core_type) or "xray",
            commercial_de_tunnel_type=hconfig(ConfigEnum.commercial_de_tunnel_type) or "test_blackhole",
            commercial_de_endpoint=hconfig(ConfigEnum.commercial_de_endpoint) or "",
            commercial_de_public_key=hconfig(ConfigEnum.commercial_de_public_key) or "",
            commercial_de_private_key_ref=hconfig(ConfigEnum.commercial_de_private_key_ref) or "",
            commercial_de_vless_uri=hconfig(ConfigEnum.commercial_de_vless_uri) or "",
            commercial_de_trojan_uri=hconfig(ConfigEnum.commercial_de_trojan_uri) or "",
            commercial_blocked_domains=_commercial_routing_config_text(COMMERCIAL_ROUTING_BLOCKED_DOMAINS_KEY, DEFAULT_COMMERCIAL_ROUTING_BLOCKED_DOMAINS),
            commercial_direct_dns_servers=_commercial_routing_config_text(COMMERCIAL_ROUTING_DIRECT_DNS_KEY, DEFAULT_COMMERCIAL_ROUTING_DIRECT_DNS),
            commercial_proxy_dns_servers=_commercial_routing_config_text(COMMERCIAL_ROUTING_PROXY_DNS_KEY, DEFAULT_COMMERCIAL_ROUTING_PROXY_DNS),
        )
        form.custom_ru_rules_bulk.data = commercial_routing.custom_rules_to_bulk_text(commercial_routing.load_enabled_custom_rules())
        return form

    def index(self):
        form = self._build_form()
        custom_rules = commercial_routing.load_enabled_custom_rules()
        preview = commercial_routing.build_preview(get_hconfigs(), custom_rules)
        test_result = None
        if request.args.get("test_route"):
            test_result = commercial_routing.simulate_route_match(request.args.get("test_route"), get_hconfigs(), custom_rules)
        return render_template("business-settings.html", form=form, commercial_routing_preview=preview, custom_rules=custom_rules, test_result=test_result, commercial_routing_notice=None)

    def post(self):
        form = BusinessSettingsForm()
        old_configs = get_hconfigs()
        if not form.validate_on_submit():
            hutils.flask.flash(_("config.validation-error"), "danger")
            return render_template("business-settings.html", form=form, commercial_routing_preview=commercial_routing.build_preview(get_hconfigs(), commercial_routing.load_enabled_custom_rules()), custom_rules=commercial_routing.load_enabled_custom_rules(), test_result=None, commercial_routing_notice=None)

        if (form.commercial_router_port.data or "").strip():
            try:
                port = int((form.commercial_router_port.data or "").strip())
                if not (1 <= port <= 65535):
                    raise ValueError
            except Exception:
                hutils.flask.flash("Invalid commercial router port", "danger")
                return render_template("business-settings.html", form=form, commercial_routing_preview=commercial_routing.build_preview(get_hconfigs(), commercial_routing.load_enabled_custom_rules()), custom_rules=commercial_routing.load_enabled_custom_rules(), test_result=None, commercial_routing_notice=None)

        submitted = {
            ConfigEnum.telegram_bot_token: (form.telegram_bot_token.data or "").strip(),
            ConfigEnum.telegram_webhook_domain: (form.telegram_webhook_domain.data or "").strip().lower(),
            ConfigEnum.telegram_payment_provider_token: (form.telegram_payment_provider_token.data or "").strip(),
            ConfigEnum.support_url: (form.support_url.data or "").strip(),
            ConfigEnum.telegram_instruction_button_text: (form.telegram_instruction_button_text.data or "").strip() or "Инструкция",
            ConfigEnum.telegram_welcome_message: (form.telegram_welcome_message.data or "").strip(),
            ConfigEnum.telegram_subscription_expiry_reminder_days: (form.telegram_subscription_expiry_reminder_days.data or "").strip() or "2,1",
            ConfigEnum.telegram_subscription_expiry_reminder_message: (form.telegram_subscription_expiry_reminder_message.data or "").strip(),
            ConfigEnum.commercial_routing_enable: bool(form.commercial_routing_enable.data),
            ConfigEnum.commercial_router_host: (form.commercial_router_host.data or "").strip() or "127.0.0.1",
            ConfigEnum.commercial_router_port: (form.commercial_router_port.data or "").strip() or "20808",
            ConfigEnum.commercial_router_protocol: (form.commercial_router_protocol.data or "").strip() or "socks5",
            ConfigEnum.commercial_apply_to_xray: bool(form.commercial_apply_to_xray.data),
            ConfigEnum.commercial_apply_to_singbox: bool(form.commercial_apply_to_singbox.data),
            ConfigEnum.commercial_domestic_policy: (form.commercial_domestic_policy.data or "keep_hiddify").strip(),
            ConfigEnum.commercial_udp443_policy: (form.commercial_udp443_policy.data or "keep_block").strip(),
            ConfigEnum.commercial_ru_domain_suffixes: (form.commercial_ru_domain_suffixes.data or "").strip() or ".ru,.su,.xn--p1ai",
            ConfigEnum.commercial_ru_geoip_enabled: bool(form.commercial_ru_geoip_enabled.data),
            ConfigEnum.commercial_default_global_policy: (form.commercial_default_global_policy.data or "to_de").strip(),
            ConfigEnum.commercial_router_core_type: (form.commercial_router_core_type.data or "xray").strip(),
            ConfigEnum.commercial_de_tunnel_type: (form.commercial_de_tunnel_type.data or "test_blackhole").strip(),
            ConfigEnum.commercial_de_endpoint: (form.commercial_de_endpoint.data or "").strip(),
            ConfigEnum.commercial_de_public_key: (form.commercial_de_public_key.data or "").strip(),
            ConfigEnum.commercial_de_private_key_ref: (form.commercial_de_private_key_ref.data or "").strip(),
            ConfigEnum.commercial_de_vless_uri: (form.commercial_de_vless_uri.data or "").strip(),
            ConfigEnum.commercial_de_trojan_uri: (form.commercial_de_trojan_uri.data or "").strip(),
            COMMERCIAL_ROUTING_BLOCKED_DOMAINS_KEY: (form.commercial_blocked_domains.data or "").strip(),
            COMMERCIAL_ROUTING_DIRECT_DNS_KEY: (form.commercial_direct_dns_servers.data or "").strip(),
            COMMERCIAL_ROUTING_PROXY_DNS_KEY: (form.commercial_proxy_dns_servers.data or "").strip(),
        }

        # BEGIN HIDDIFY ROUTING UI JSON SAVE
        routing_ui_submitted = {}
        for _routing_ui_key in (
            COMMERCIAL_ROUTING_BLOCKED_DOMAINS_KEY,
            COMMERCIAL_ROUTING_DIRECT_DNS_KEY,
            COMMERCIAL_ROUTING_PROXY_DNS_KEY,
        ):
            if _routing_ui_key in submitted:
                routing_ui_submitted[_routing_ui_key] = submitted.pop(_routing_ui_key)

        for key, value in submitted.items():
            if old_configs.get(key) != value:
                set_hconfig(key, value, commit=False)

        if routing_ui_submitted:
            from pathlib import Path
            import json

            # Stage A1 keeps panel behavior unchanged: write primary JSON first,
            # then mirror the same payload to the legacy /etc path used by runtime apply.
            primary_routing_ui_path = Path(COMMERCIAL_ROUTING_UI_PRIMARY_PATH)
            legacy_routing_ui_path = Path(COMMERCIAL_ROUTING_UI_LEGACY_PATH)

            primary_routing_ui_path.parent.mkdir(parents=True, exist_ok=True)

            current_routing_ui = {}
            for _candidate_path in (primary_routing_ui_path, legacy_routing_ui_path):
                try:
                    if _candidate_path.exists():
                        _loaded = json.loads(_candidate_path.read_text(encoding="utf-8"))
                        if isinstance(_loaded, dict):
                            current_routing_ui = _loaded
                            break
                except Exception:
                    pass

            for _routing_ui_key, _routing_ui_value in routing_ui_submitted.items():
                current_routing_ui[str(_routing_ui_key)] = "" if _routing_ui_value is None else str(_routing_ui_value)

            _serialized_routing_ui = json.dumps(current_routing_ui, indent=2, ensure_ascii=False) + "\n"

            primary_routing_ui_path.write_text(_serialized_routing_ui, encoding="utf-8")

            try:
                legacy_routing_ui_path.parent.mkdir(parents=True, exist_ok=True)
                legacy_routing_ui_path.write_text(_serialized_routing_ui, encoding="utf-8")
            except Exception:
                pass
        # END HIDDIFY ROUTING UI JSON SAVE

        bulk_text = (form.custom_ru_rules_bulk.data or "").strip()
        if bulk_text:
            rules, errors = commercial_routing.parse_bulk_rules(bulk_text)
        else:
            rules, errors = [], []

        if errors:
            for err in errors:
                hutils.flask.flash(f"Bulk rule line {err.line_no}: {err.error}", "danger")
            return render_template(
                "business-settings.html",
                form=form,
                commercial_routing_preview=commercial_routing.build_preview(get_hconfigs(), commercial_routing.load_enabled_custom_rules()),
                custom_rules=commercial_routing.load_enabled_custom_rules(),
                test_result=None,
                commercial_routing_notice=None,
            )

        unique_rules = {}
        for rule in rules:
            unique_rules[(rule["rule_type"], rule["normalized_value"])] = rule

        CommercialRoutingCustomRule.query.delete()
        for rule in unique_rules.values():
            db.session.add(CommercialRoutingCustomRule(**rule))

        db.session.commit()

        commercial_routing_notice = None
        try:
            import subprocess
            apply_proc = subprocess.run(
                ["sudo", "-n", "/opt/hiddify-manager/common/commander.py", "commercial-routing-apply"],
                capture_output=True,
                text=True,
                timeout=90,
            )
            if apply_proc.returncode == 0:
                commercial_routing_notice = "Router-core config применён, xray-router перезапущен."
                hutils.flask.flash(commercial_routing_notice, "success")
            else:
                msg = ((apply_proc.stderr or "") + "\n" + (apply_proc.stdout or "")).strip()
                commercial_routing_notice = "Настройки сохранены, но router-core config не применён: " + (msg[-1000:] if msg else "unknown error")
                hutils.flask.flash(commercial_routing_notice, "danger")
        except Exception as exc:
            commercial_routing_notice = f"Настройки сохранены, но router-core config не применён: {exc}"
            hutils.flask.flash(commercial_routing_notice, "danger")

        telegram_related_keys = {
            ConfigEnum.telegram_bot_token,
            ConfigEnum.telegram_webhook_domain,
            ConfigEnum.telegram_payment_provider_token,
        }
        if any(old_configs.get(k) != submitted.get(k) for k in telegram_related_keys):
            from hiddifypanel.panel.commercial.telegrambot import register_bot
            register_bot(set_hook=True)

        reset_action = hiddify.check_need_reset(old_configs)
        hutils.flask.flash(_("config.configs_have_been_updated"), "success")
        notice = commercial_routing_notice or "Настройки сохранены, но router-core config не применён. Запустите commercial-routing apply."
        if reset_action:
            return reset_action
        return render_template(
            "business-settings.html",
            form=self._build_form(),
            commercial_routing_preview=commercial_routing.build_preview(get_hconfigs(), commercial_routing.load_enabled_custom_rules()),
            custom_rules=commercial_routing.load_enabled_custom_rules(),
            test_result=commercial_routing.simulate_route_match((form.test_route_input.data or "").strip(), get_hconfigs(), commercial_routing.load_enabled_custom_rules()) if (form.test_route_input.data or "").strip() else None,
            commercial_routing_notice=notice,
        )
