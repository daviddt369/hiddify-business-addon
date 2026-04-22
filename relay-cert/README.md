# relay-cert

Это **опциональный шаг 3** после:

1. official Hiddify beta
2. first setup
3. business addon

Нужен только если используется relay-домен с:

- `mode=relay`
- `need_valid_ssl=true`

## Поддерживаемые сценарии

### Стандартный: `dns-01`

Рекомендуется для обычного пользователя.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/main/relay-cert/install-dns01.sh)
```

### Advanced: `http-01`

Для тех, кто контролирует relay ingress и хочет автоперевыпуск через panel/apply.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/main/relay-cert/install-http01.sh)
```

Подробности:

- `docs/relay-ssl-ru.md`
- для `http-01` на relay должен быть настроен proxy для:
  - `/.well-known/acme-challenge/`
- рекомендуемый файл на relay:
  - `/etc/nginx/conf.d/meta.conf`
