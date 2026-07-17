FROM python:3.12-slim

WORKDIR /srv/api

# WeasyPrint native deps + proper Arabic typography for reports (§9).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi8 \
        fonts-noto-core fonts-noto-ui-core \
    && rm -rf /var/lib/apt/lists/*

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
