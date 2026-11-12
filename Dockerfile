FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system gamer && adduser --system --ingroup gamer gamer

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
RUN mkdir -p /app/data /app/backups && chown -R gamer:gamer /app

USER gamer

ENV DB_PATH=/app/data/rpg.db \
    BACKUP_DIR=/app/backups

CMD ["./start.sh"]
