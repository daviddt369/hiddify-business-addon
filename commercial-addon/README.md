# commercial-addon

Этот шаг запускается **только после**:

1. установки official Hiddify
2. завершения first setup
3. сохранения реального домена панели

Команда:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/main/commercial-addon/install-addon.sh)
```

Что делает installer:

- проверяет версию Hiddify
- накатывает manager overlay
- накатывает panel overlay
- создаёт backup заменяемых файлов
- запускает интерактивный commercial finalize

Если relay-домены не используются, на этом установка заканчивается.

Если relay-домены используются и им нужен валидный SSL, выполняется шаг 3 из `relay-cert/`.
