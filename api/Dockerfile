FROM python:3.12-slim

WORKDIR /srv/api

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY palio ./palio
COPY alembic.ini ./
COPY migrations ./migrations

RUN uv pip install --system --no-cache .

# Non-root runtime user
RUN useradd --create-home palio
USER palio

EXPOSE 8000
CMD ["uvicorn", "palio.main:app", "--host", "0.0.0.0", "--port", "8000"]
