.PHONY: run test lint format check-all coverage

# Запуск приложения
run:
	poetry run python -m nla.log_analyzer

# Запуск тестов
test:
	poetry run pytest

# Запуск тестов с покрытием
coverage:
	poetry run pytest --cov=nla --cov-report=term

# Проверки: mypy + flake8
lint:
	poetry run mypy nla/
	poetry run flake8 nla/ tests/

# Форматирование: black + isort
format:
	poetry run black .
	poetry run isort .

# Проверка форматирования и линтеров
check-all:
	poetry run black . --check
	poetry run isort . --check-only
	poetry run flake8 nla tests
	poetry run mypy nla

# Синхронизация poetry
sync:
	poetry lock && poetry install
