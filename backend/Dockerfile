FROM python:3.14-slim AS base
WORKDIR /app

# Dependencies in their own layer: a code-only rebuild reinstalls no dependencies. The
# manifest-only dummy build installs the declared dependencies and no packages.
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Both later stages run as this unprivileged user, and the dev stage has to chown to it.
RUN useradd --create-home appuser

# Shared runtime metadata: the dev image stays runnable on its own, not only behind the
# compose services' command overrides.
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips=*"]

# Development stage, selected by deploy/docker-compose.dev.yml: the code is installed
# editable, so the files Compose Watch syncs into /app are the ones the running process
# imports - there is no second copy in site-packages to shadow them. The chown matters
# because the process runs as appuser and Compose Watch writes as that same user.
FROM base AS dev
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY scripts/ scripts/
RUN pip install --no-cache-dir --no-deps -e . && chown -R appuser:appuser /app
USER appuser

# Production stage (the default): a regular, non-editable install of the code.
FROM base AS prod
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY scripts/ scripts/
RUN pip install --no-cache-dir --no-deps .

USER appuser
