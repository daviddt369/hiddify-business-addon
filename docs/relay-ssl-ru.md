# Relay SSL: два пути

Если relay не используется, этот шаг не нужен.

Если relay используется и у relay-домена стоит `need_valid_ssl=true`, есть два поддерживаемых пути.

## 1. `dns-01` — рекомендуемый путь

Подходит для обычного пользователя.

Почему:

- не зависит от HTTP ingress relay
- не требует править `nginx stream`
- не требует прокидывать `/.well-known/acme-challenge/`

Команда:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/main/relay-cert/install-dns01.sh)
```

Дальше:

1. смотри TXT challenge
2. добавляй `_acme-challenge.<subdomain>` у DNS-провайдера
3. заверши выпуск сертификата

Если настроен DNS API для `acme.sh`, этот путь тоже подходит.

## 2. `http-01` — advanced путь

Подходит, если:

- relay на `nginx`
- есть контроль над `80/tcp`
- нужен обычный auto-renew через `Apply Configs`

Команда:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/main/relay-cert/install-http01.sh)
```

Этот шаг:

- патчит main-server ACME compatibility
- выводит точный блок для relay nginx

Важно:

- это не universal magic для любого relay
- этот сценарий рассчитан на relay с понятным HTTP ingress

## Что выбирать по умолчанию

Для обычного сценария:

- выбирай `dns-01`

Для инженерного сценария с auto-renew:

- выбирай `http-01`
