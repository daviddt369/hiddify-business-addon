# Hiddify Business Addon

Production addon для установки поверх stable Hiddify `12.0.x`.

Текущий релиз:
- `v0.12.0`

## Быстрый порядок установки

1. Base Hiddify
2. Commercial addon
3. Routing addon
4. Cert scripts (опционально)

## Шаг 1 - Base (Hiddify 12.0.x)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.0/scripts/install-base-onecmd.sh)
```

После base:
- зайти в панель
- завершить first setup
- сохранить реальный домен панели

## Шаг 2 - Commercial addon

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.0/scripts/install-commercial-onecmd.sh)
```

## Шаг 3 - Routing addon

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.0/scripts/install-routing-onecmd.sh)
```

## Шаг 4 - Relay cert (опционально)

DNS-01:
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.0/scripts/install-relay-cert-dns01-onecmd.sh)
```

HTTP-01:
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.0/scripts/install-relay-cert-http01-onecmd.sh)
```

## Дорожная карта

1. Зафиксировать стабильный baseline на Hiddify `12.0.x` (текущий этап).
2. Провести аудит совместимости с `12.3.0` без затирания runtime фиксов.
3. Сделать миграционный релиз с отдельным install path для `12.3.x`.

## Структура репозитория

- `scripts/` - onecmd installers (base/commercial/routing/certs)
- `commercial-addon/` - installer бизнес-надстройки
- `relay-cert/` - scripts для relay SSL
- `manager-overlay/` - manager-side overlay
- `panel-overlay/` - panel-side overlay
- `docs/` - документация

## Документация

- `docs/addon-model-ru.md`
- `docs/relay-ssl-ru.md`
