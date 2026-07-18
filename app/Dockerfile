FROM python:3.12-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28

WORKDIR /code

RUN groupadd --gid 10001 vantage \
    && useradd --uid 10001 --gid vantage --create-home --home-dir /home/vantage \
        --shell /usr/sbin/nologin vantage

ENV HOME=/home/vantage

COPY app/requirements.txt ./app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

COPY --chown=vantage:vantage app ./app
COPY --chown=vantage:vantage alembic.ini ./alembic.ini
COPY --chown=vantage:vantage alembic ./alembic
COPY --chown=vantage:vantage scripts ./scripts

EXPOSE 8000

USER 10001:10001

CMD ["sh", "-c", "python -m scripts.database.migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
