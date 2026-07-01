FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml /app/
RUN pip install --no-cache-dir -e .
COPY . /app

CMD ["python", "-m", "polymarket_mm_bot.dashboard.server"]
