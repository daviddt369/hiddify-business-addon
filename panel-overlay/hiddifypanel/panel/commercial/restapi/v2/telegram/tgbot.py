import telebot
from flask import request, Response, current_app
from apiflask import abort
from apiflask import HTTPError
from flask_restful import Resource
from werkzeug.exceptions import HTTPException
import time
import os
import hmac

from hiddifypanel.models import *
# NOTE: v2 copy of telegram webhook handler to avoid v2->v1 runtime dependency.
from hiddifypanel import Events
from hiddifypanel.cache import cache
logger = telebot.logger


class ExceptionHandler(telebot.ExceptionHandler):
    def handle(self, exception):
        """Improved error handling for Telegram bot exceptions"""
        error_msg = str(exception)
        logger.error(f"Telegram bot error: {error_msg}")
        
        try:
            # Attempt recovery based on error type
            if "webhook" in error_msg.lower():
                if hasattr(bot, 'remove_webhook'):
                    bot.remove_webhook()
                    logger.info("Removed webhook due to error")
            elif "connection" in error_msg.lower():
                # Wait and retry for connection issues
                time.sleep(5)
                return True  # Indicates retry
        except Exception as e:
            logger.error(f"Error during recovery attempt: {str(e)}")
        
        return False  # Don't retry for unknown errors


bot = telebot.TeleBot("1:2", parse_mode="HTML", threaded=False, exception_handler=ExceptionHandler())
bot.username = ''


def _webhook_secret() -> str:
    secret = (
        os.environ.get("HIDDIFY_TELEGRAM_WEBHOOK_SECRET", "")
        or os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    ).strip()
    if secret:
        return secret

    secrets_file = "/etc/hiddify-panel/panel-secrets.env"
    try:
        with open(secrets_file, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("HIDDIFY_TELEGRAM_WEBHOOK_SECRET="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def _webhook_domain_override() -> str:
    domain = (
        (hconfig(ConfigEnum.telegram_webhook_domain) or "")
        or
        os.environ.get("HIDDIFY_TELEGRAM_WEBHOOK_DOMAIN", "")
        or os.environ.get("TELEGRAM_WEBHOOK_DOMAIN", "")
    ).strip().lower()
    if not domain:
        return ""
    if domain.startswith("http://"):
        domain = domain[len("http://"):]
    elif domain.startswith("https://"):
        domain = domain[len("https://"):]
    return domain.split("/", 1)[0].strip()


def _webhook_secret_is_valid(request) -> bool:
    secret = _webhook_secret()
    if not secret:
        logger.error(
            "Telegram webhook rejected: webhook secret is not configured. path=%s remote=%s",
            request.path,
            request.remote_addr,
        )
        return False
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    return bool(received) and hmac.compare_digest(received, secret)


@cache.cache(1000)
def register_bot_cached(set_hook=False, remove_hook=False):
    return register_bot(set_hook, remove_hook)


def register_bot(set_hook=False, remove_hook=False):
    try:
        global bot
        token = hconfig(ConfigEnum.telegram_bot_token)
        if token:
            bot.token = hconfig(ConfigEnum.telegram_bot_token)
            try:
                bot.username = bot.get_me().username
            except BaseException:
                pass
            if remove_hook:
                bot.remove_webhook()
            domain = _webhook_domain_override() or Domain.get_panel_link()
            if not domain:
                raise Exception('Cannot get valid domain for setting telegram bot webhook')

            admin_proxy_path = hconfig(ConfigEnum.proxy_path_admin)

            user_secret = AdminUser.get_super_admin_uuid()
            if set_hook:
                kwargs = {}
                secret = _webhook_secret()
                if not secret:
                    logger.error(
                        "Telegram webhook registration skipped: webhook secret is not configured."
                    )
                    return
                kwargs["secret_token"] = secret
                kwargs.setdefault(
                    "allowed_updates",
                    ["message", "callback_query", "my_chat_member", "pre_checkout_query", "successful_payment"],
                )
                bot.set_webhook(
                    url=f"https://{domain}/{admin_proxy_path}/{user_secret}/api/v2/tgbot/",
                    **kwargs,
                )
    except Exception as e:
        logger.error(e)
        


def init_app(app):
    with app.app_context():
        global bot
        token = hconfig(ConfigEnum.telegram_bot_token)
        if token:
            bot.token = token
            try:
                bot.username = bot.get_me().username
            except BaseException:
                pass


class TGBotResource(Resource):
    def post(self):
        try:
            if not _webhook_secret_is_valid(request):
                logger.error(
                    "Telegram webhook rejected: invalid secret header. path=%s remote=%s",
                    request.path,
                    request.remote_addr,
                )
                return Response("", status=403)
            content_type = (request.headers.get('content-type') or '').lower()
            if content_type.startswith('application/json'):
                token = hconfig(ConfigEnum.telegram_bot_token)
                if token:
                    bot.token = token
                json_string = request.get_data().decode('utf-8')
                logger.info(
                    "Telegram webhook received: path=%s remote=%s bytes=%s",
                    request.path,
                    request.remote_addr,
                    len(json_string),
                )
                update = telebot.types.Update.de_json(json_string)
                # Telegram handlers may call Babel/request-aware helpers.
                # Recreate a request context from the current webhook request so
                # request-bound utilities keep working during update processing.
                with current_app.request_context(request.environ):
                    bot.process_new_updates([update])
                return ''
            else:
                logger.error(
                    "Telegram webhook rejected: invalid content-type=%s",
                    content_type,
                )
                return Response("", status=403)
        except (HTTPError, HTTPException):
            raise
        except Exception as e:
            logger.exception("Telegram webhook processing failed: %s", e)
            return "", 500
