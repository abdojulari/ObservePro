FROM python:3.12-slim

WORKDIR /app

RUN useradd --create-home --uid 10001 observe

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
COPY entrypoint.sh .

RUN mkdir -p /data && chown -R observe:observe /app /data

USER observe

EXPOSE 8000 4319

CMD ["sh", "entrypoint.sh", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
