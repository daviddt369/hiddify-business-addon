# Hiddify Business Addon

Этот репозиторий содержит только нашу надстройку над `official Hiddify`.

Базовый принцип:

1. ставится **официальный Hiddify**
2. проходится **first setup**
3. ставится **наш addon**
4. если используется relay-домен с валидным SSL, выполняется **отдельный шаг relay SSL**

## Шаг 1. База

```bash
bash <(curl -fsSL https://i.hiddify.com/beta)
```

После этого:

- открыть панель
- завершить `first setup`
- сохранить реальный домен панели

## Шаг 2. Коммерческая надстройка

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/main/commercial-addon/install-addon.sh)
```

Что делает addon:

- накатывает manager overlay
- накатывает panel overlay
- запускает интерактивный commercial finalize

## Шаг 3. Relay SSL — только если используется relay-домен

### Стандартный путь: `dns-01`

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/main/relay-cert/install-dns01.sh)
```

### Advanced путь: `http-01` через relay ingress

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/daviddt369/hiddify-business-addon/main/relay-cert/install-http01.sh)
```

## Структура

- `commercial-addon/` — основной addon installer
- `relay-cert/` — отдельный шаг для relay SSL
- `manager-overlay/` — manager-side overlay
- `panel-overlay/` — panel-side overlay
- `docs/` — русские инструкции

## Документация

- `docs/addon-model-ru.md`
- `docs/relay-ssl-ru.md`
