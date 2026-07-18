FROM python:3.12-slim

# Не создавать .pyc, сразу выводить логи
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала зависимости — чтобы кэш Docker переиспользовался
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Затем код
COPY . .

# База лежит в рабочей папке контейнера (на Render диск эфемерный).
ENV DB_PATH=/app/academy_bot.db

# Панель слушает этот порт
EXPOSE 8000

CMD ["python", "run_all.py"]
