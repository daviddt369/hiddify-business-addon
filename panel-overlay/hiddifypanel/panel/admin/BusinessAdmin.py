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
from hiddifypanel.panel import hiddify


class BusinessSettingsForm(FlaskForm):
    telegram_bot_token = wtf.StringField(
        _("Токен Telegram бота"),
        validators=[
            wtf.validators.Optional(),
            wtf.validators.Regexp(
                r"^([0-9]{8,12}:[a-zA-Z0-9_-]{30,40})$",
                re.IGNORECASE,
                _("config.Invalid_telegram_bot_token"),
            ),
        ],
        description=_("Токен из @BotFather для работы коммерческого Telegram-бота."),
        render_kw={"class": "ltr"},
    )

    telegram_webhook_domain = wtf.StringField(
        _("Домен Telegram webhook"),
        validators=[
            wtf.validators.Optional(),
            wtf.validators.Regexp(
                r"^([A-Za-z0-9.-]+\.[A-Za-z]{2,})$",
                re.IGNORECASE,
                _("config.Invalid_domain"),
            ),
        ],
        description=_(
            "Фиксированный домен для webhook. Если пусто — используется домен панели "
            "(полезно для стабильности webhook при нескольких direct-доменах)."
        ),
        render_kw={"class": "ltr"},
    )

    telegram_payment_provider_token = wtf.StringField(
        _("YooKassa provider token (Telegram payments)"),
        validators=[
            wtf.validators.Optional(),
            wtf.validators.Regexp(
                r"^([0-9]{5,}:[A-Za-z0-9_:-]+)$",
                re.IGNORECASE,
                _("Invalid YooKassa/Telegram provider token"),
            ),
        ],
        description=_("Токен Telegram Payments provider (YooKassa через BotFather)."),
        render_kw={"class": "ltr"},
    )

    support_url = wtf.StringField(
        _("Ссылка поддержки"),
        validators=[
            wtf.validators.Optional(),
            wtf.validators.Regexp(
                r"^(https?://|tg://|mailto:|tel:).+",
                re.IGNORECASE,
                _("Invalid support URL"),
            ),
        ],
        description=_(
            "Ссылка поддержки для пользователей, которых нет в базе "
            "(используется в боте при закрытой регистрации пользователей)."
        ),
        render_kw={"class": "ltr"},
    )

    submit = wtf.SubmitField(_("Подтвердить"))


class BusinessAdmin(FlaskView):
    decorators = [login_required(roles={Role.super_admin})]

    def index(self):
        form = BusinessSettingsForm(
            telegram_bot_token=hconfig(ConfigEnum.telegram_bot_token) or "",
            telegram_webhook_domain=hconfig(ConfigEnum.telegram_webhook_domain) or "",
            telegram_payment_provider_token=hconfig(ConfigEnum.telegram_payment_provider_token) or "",
            support_url=hconfig(ConfigEnum.support_url) or "",
        )
        return render_template("business-settings.html", form=form)

    def post(self):
        form = BusinessSettingsForm()
        old_configs = get_hconfigs()

        if not form.validate_on_submit():
            csrf_errors = form.errors.get("csrf_token", [])
            if csrf_errors:
                hutils.flask.flash(_("Сессия истекла. Обновите страницу и повторите сохранение."), "danger")
                return redirect(request.path)

            hutils.flask.flash(_("config.validation-error"), "danger")
            for field_name, errors in form.errors.items():
                if field_name == "csrf_token":
                    continue
                for error_message in errors:
                    hutils.flask.flash(error_message, "danger")
            return render_template("business-settings.html", form=form)

        submitted = {
            ConfigEnum.telegram_bot_token: (form.telegram_bot_token.data or "").strip(),
            ConfigEnum.telegram_webhook_domain: (form.telegram_webhook_domain.data or "").strip().lower(),
            ConfigEnum.telegram_payment_provider_token: (form.telegram_payment_provider_token.data or "").strip(),
            ConfigEnum.support_url: (form.support_url.data or "").strip(),
        }

        for key, value in submitted.items():
            if old_configs.get(key) != value:
                set_hconfig(key, value, commit=False)

        db.session.commit()

        from hiddifypanel.panel.commercial.telegrambot import register_bot

        register_bot(set_hook=True)

        reset_action = hiddify.check_need_reset(old_configs)
        hutils.flask.flash(_("config.configs_have_been_updated"), "success")
        if reset_action:
            return reset_action
        return redirect(request.path)
