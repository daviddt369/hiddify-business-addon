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
        render_kw={"class": "ltr", "readonly": True, "placeholder": "server-only"},
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
            "Фиксированный домен для webhook. Если пусто - используется домен панели "
            "(полезно для стабильности webhook при нескольких direct-доменах)."
        ),
        render_kw={"class": "ltr", "readonly": True, "placeholder": "server-only"},
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
            "Ссылка поддержки для пользователя, которая есть у него "
            "(например в меню или кнопке обращения к администратору)."
        ),
        render_kw={"class": "ltr"},
    )

    telegram_instruction_button_text = wtf.StringField(
        _("Текст кнопки инструкции"),
        validators=[wtf.validators.Optional(), wtf.validators.Length(max=64)],
        description=_("Текст reply-кнопки, которая отправляет сохранённое приветственное сообщение."),
    )

    telegram_welcome_message = wtf.TextAreaField(
        _("Приветственное сообщение / инструкция"),
        validators=[wtf.validators.Optional(), wtf.validators.Length(max=4000)],
        description=_("Сообщение один раз для новых пользователей Telegram и по кнопке Инструкция. Поддерживается HTML и ссылки."),
        render_kw={"rows": 8},
    )

    telegram_subscription_expiry_reminder_days = wtf.StringField(
        _("Дни до напоминания о продлении"),
        validators=[wtf.validators.Optional(), wtf.validators.Length(max=64)],
        description=_("Список через запятую, например 2,1. Бот напомнит за столько дней до окончания подписки."),
    )

    telegram_subscription_expiry_reminder_message = wtf.TextAreaField(
        _("Текст напоминания о продлении"),
        validators=[wtf.validators.Optional(), wtf.validators.Length(max=4000)],
        description=_("Текст автоматического напоминания в Telegram. Доступен плейсхолдер {days_left}."),
        render_kw={"rows": 5},
    )

    submit = wtf.SubmitField(_("Сохранить"))


class BusinessAdmin(FlaskView):
    decorators = [login_required(roles={Role.super_admin})]

    def index(self):
        form = BusinessSettingsForm(
            telegram_bot_token="",
            telegram_webhook_domain=hconfig(ConfigEnum.telegram_webhook_domain) or "",
            telegram_payment_provider_token="",
            support_url=hconfig(ConfigEnum.support_url) or "",
            telegram_instruction_button_text=hconfig(ConfigEnum.telegram_instruction_button_text) or "Инструкция",
            telegram_welcome_message=hconfig(ConfigEnum.telegram_welcome_message) or "",
            telegram_subscription_expiry_reminder_days=hconfig(ConfigEnum.telegram_subscription_expiry_reminder_days) or "2,1",
            telegram_subscription_expiry_reminder_message=hconfig(ConfigEnum.telegram_subscription_expiry_reminder_message) or "У вас заканчивается подписка через {days_left} дн. Не забудьте продлить тариф.",
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
            ConfigEnum.telegram_webhook_domain: (form.telegram_webhook_domain.data or "").strip().lower(),
            ConfigEnum.support_url: (form.support_url.data or "").strip(),
            ConfigEnum.telegram_instruction_button_text: (form.telegram_instruction_button_text.data or "").strip() or "Инструкция",
            ConfigEnum.telegram_welcome_message: (form.telegram_welcome_message.data or "").strip(),
            ConfigEnum.telegram_subscription_expiry_reminder_days: (form.telegram_subscription_expiry_reminder_days.data or "").strip() or "2,1",
            ConfigEnum.telegram_subscription_expiry_reminder_message: (form.telegram_subscription_expiry_reminder_message.data or "").strip(),
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
