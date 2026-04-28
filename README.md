# Hiddify Business Addon

Релизная ветка для stable Hiddify `12.0.x`.

Текущий релиз:
- `v0.12.0`

Поток установки:
1. base Hiddify
2. commercial addon
3. routing addon
4. optional relay cert scripts

## Шаг 1. Base (Hiddify 12.0.x)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.0/scripts/install-base-onecmd.sh)
```

## Шаг 2. Commercial addon

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.0/scripts/install-commercial-onecmd.sh)
```

## Шаг 3. Routing addon

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.0/scripts/install-routing-onecmd.sh)
```

## Шаг 4. Relay cert (optional)

DNS-01:
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.0/scripts/install-relay-cert-dns01-onecmd.sh)
```

HTTP-01:
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.12.0/scripts/install-relay-cert-http01-onecmd.sh)
```

## Структура

- `scripts/` - onecmd installers для base/commercial/routing/certs
- `commercial-addon/` - addon installer
- `relay-cert/` - relay cert scripts
- `manager-overlay/` - manager-side overlay
- `panel-overlay/` - panel-side overlay
- `docs/` - документация
