# Модель поставки: official Hiddify + business addon

## Цель

Не держать отдельный тяжёлый fork всего Hiddify, а использовать:

1. `official Hiddify` как базу
2. `business addon` как второй шаг

Это упрощает:

- базовую установку
- обновление upstream
- поддержку коммерческой логики отдельно от core install path

## Что входит в addon

- Telegram bot logic
- Telegram webhook v2 compatibility
- YooKassa / payment flow
- admin notifications
- business UI / business menu
- коммерческие вопросы после установки
- relay SSL optional step

## Что не входит в addon

- полный upstream installer
- runtime state сервера
- generated конфиги
- backup/log/cache/dump
- server-specific secrets

## Итоговый flow

1. official Hiddify beta
2. first setup
3. business addon
4. relay SSL step только при необходимости
