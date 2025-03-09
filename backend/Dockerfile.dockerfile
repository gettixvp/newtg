# Базовый образ с Python
FROM python:3.11.11-slim

# Установка рабочей директории
WORKDIR /app

# Установка Poetry
RUN pip install poetry==1.7.1

# Копирование файлов Poetry
COPY pyproject.toml poetry.lock* ./

# Установка зависимостей
RUN poetry config virtualenvs.create false && poetry install --no-dev

# Копирование кода
COPY . .

# Команда запуска (замени на свою)
CMD ["python", "main.py"]
