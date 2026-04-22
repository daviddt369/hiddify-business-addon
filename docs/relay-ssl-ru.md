# Relay SSL: два пути

Если relay не используется, этот шаг не нужен.

Если relay используется и у relay-домена стоит `need_valid_ssl=true`, есть два поддерживаемых пути:

1. `dns-01` — стандартный и рекомендуемый
2. `http-01` — advanced, если relay контролируешь сам

## 1. `dns-01` — рекомендуемый путь

Это основной путь для обычного пользователя.

Почему:

- не зависит от HTTP ingress relay
- не требует править relay nginx
- не требует прокидывать `/.well-known/acme-challenge/`

Команда:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.1.7/relay-cert/install-dns01.sh)
```

Что дальше:

1. В панели Hiddify или в `acme.sh` появится challenge для домена.
2. Добавляешь TXT-запись вида:
   - `_acme-challenge.<subdomain>`
3. Ждёшь обновления DNS.
4. Нажимаешь `Apply Configs` в панели.
5. Проверяешь, что сертификат появился в:
   - `/opt/hiddify-manager/ssl/<relay-domain>.crt`

Если у тебя настроен DNS API для `acme.sh`, этот путь тоже подходит и будет удобнее, чем ручной TXT.

## 2. `http-01` — advanced путь

Этот путь подходит, если:

- relay работает на `nginx`
- relay-домен смотрит на relay IP
- есть контроль над `80/tcp`
- нужен обычный выпуск и перевыпуск через `Apply Configs`

Команда:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/v0.1.7/relay-cert/install-http01.sh)
```

Важно:

- на `stable` мы подтвердили, что для `http-01` relay-домена достаточно правильно настроенного relay nginx
- если relay проксирует `/.well-known/acme-challenge/` на main server, panel сама выпускает сертификат через `Apply Configs`

### Что нужно настроить на relay-сервере

Файл:

```nginx
/etc/nginx/conf.d/meta.conf
```

Минимальный блок:

```nginx
server {
    listen 80;
    server_name _;

    location /meta/ {
        alias /opt/meta/;
        autoindex on;
    }

    location ^~ /.well-known/acme-challenge/ {
        proxy_pass http://193.23.197.96:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Где:

- `193.23.197.96` — это IP main Hiddify server
- relay-домен (`link.mediaserv.site` или другой) должен резолвиться в IP relay-сервера

После изменения:

```bash
nginx -t
systemctl reload nginx
```

### Как проверить, что relay готов к выпуску

На relay или с любой внешней машины:

```bash
curl -I http://<relay-domain>/.well-known/acme-challenge/test
```

Если relay proxy уже настроен правильно, ты не должен получать локальный `404` от дефолтного nginx relay-сервера.

### Что дальше делать на main server

1. В панели добавляешь relay-домен.
2. У relay-домена должно быть:
   - `mode=relay`
   - `need_valid_ssl=true`
3. Нажимаешь `Apply Configs`.
4. Проверяешь выпуск:

```bash
openssl x509 -in /opt/hiddify-manager/ssl/<relay-domain>.crt -noout -issuer -subject -dates
```

### Что мы подтвердили на продовом сценарии

На рабочем сценарии сертификат для `link.mediaserv.site` выпустился через `http-01` так:

- CA шёл на `http://link.mediaserv.site/.well-known/acme-challenge/...`
- DNS `link.mediaserv.site` указывал на relay IP
- relay nginx проксировал challenge на main server
- main server отдавал challenge из `acme.sh/www`
- после этого Hiddify panel сама установила cert в:
  - `/opt/hiddify-manager/ssl/link.mediaserv.site.crt`

## Что выбирать по умолчанию

Для обычного сценария:

- выбирай `dns-01`

Для relay под собственным контролем и auto-renew через панель:

- выбирай `http-01`
