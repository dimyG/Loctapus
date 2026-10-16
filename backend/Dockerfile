FROM python:3.14-slim
WORKDIR /app

# Dependencies in their own layer: a code-only rebuild reinstalls nothing. The
# manifest-only dummy build installs the declared dependencies and no packages.
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY scripts/ scripts/
RUN pip install --no-cache-dir --no-deps .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips=*"]
