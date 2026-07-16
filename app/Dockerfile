FROM python:3.12-slim

WORKDIR /code

COPY app/requirements.txt ./app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY scripts ./scripts

EXPOSE 8000

CMD ["sh", "-c", "python -m scripts.database.migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
