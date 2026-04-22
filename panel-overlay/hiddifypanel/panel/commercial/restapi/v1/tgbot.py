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
    return (
        os.environ.get("HIDDIFY_TELEGRAM_WEBHOOK_SECRET", "")
        or os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    ).strip()


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
        return True
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
                if secret:
                    kwargs["secret_token"] = secret
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
            if request.headers.get('content-type') == 'application/json':
                json_string = request.get_data().decode('utf-8')
                logger.info(
                    "Telegram webhook received: path=%s remote=%s bytes=%s",
                    request.path,
                    request.remote_addr,
                    len(json_string),
                )
                update = telebot.types.Update.de_json(json_string)
                # Telegram handlers rely on Flask extensions such as Babel.
                # Keep processing inside an explicit app context so webhook
                # updates behave the same as panel-triggered flows.
                with current_app.app_context():
                    bot.process_new_updates([update])
                return ''
            else:
                logger.error(
                    "Telegram webhook rejected: invalid content-type=%s",
                    request.headers.get('content-type'),
                )
                return Response("", status=403)
        except (HTTPError, HTTPException):
            raise
        except Exception as e:
            logger.exception("Telegram webhook processing failed: %s", e)
            return "", 500
