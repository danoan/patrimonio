FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app
WORKDIR /srv
# The editable install below doesn't leave a working sys.path redirect for script
# invocation (only for interactive/-c use, via cwd) — pin it explicitly so
# `python docker/migrate.py` etc. can import `app` regardless of how it's invoked.
ENV PYTHONPATH=/srv

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY app/ app/
COPY alembic.ini ./
COPY migrations/ migrations/
COPY docker/ docker/
RUN chmod +x docker/entrypoint.sh

RUN mkdir -p /data && chown app:app /data
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fs http://localhost:8000/ || exit 1

ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
