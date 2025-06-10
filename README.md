# 🧾 NLA — Nginx Log Analyzer

**NLA (Nginx Log Analyzer)** — это инструмент для анализа логов Nginx и генерации HTML-отчетов по самым популярным URL, основанный на времени ответа.

## 🚀 Возможности

- Поддержка логов в формате `.log` и `.gz`
- Подсчёт:
  - Частоты запросов
  - Суммарного, среднего, медианного, максимального времени ответа
- Генерация HTML-отчётов на основе шаблона
- Поддержка конфигурации из JSON-файла

## 📦 Установка

```bash
git clone https://github.com/<your-username>/nla.git
cd nla
poetry install
```

## ⚙️ Пример запуска

```bash
poetry run python -m nla.main --config ./data/config
```


## 📁 Пример конфигурационного файла (config)

```json
{
        "REPORT_SIZE": 10,
        "REPORT_DIR": "../reports",
        "LOG_DIR": "../log",
        "DATA_DIR": "../data",
        "STRUCT_LOG_FILE": "../app.log"
}
```

## 🧪 Тестирование

```bash
poetry run pytest
```

## 🔍 Проверки

```bash
poetry run pre-commit run --all-files
```

## 🛠️ CI
Проект включает GitHub Actions workflow (.github/workflows/main.yml), который запускает:

- black
- isort
- flake8
- mypy
- pytest

при каждом пуше в main или pull request.
