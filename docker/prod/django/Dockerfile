FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS python-build-stage

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY uv.lock pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

FROM node:lts-alpine AS vite_build
WORKDIR /usr/src/frontend

COPY ./frontend/package.json ./frontend/package-lock.json* ./

RUN --mount=type=cache,target=/root/.npm \
    npm ci || npm install

COPY ./frontend .
COPY ./app/templates /usr/src/app/templates

RUN npm run build

FROM python:3.11-slim-bookworm AS python-run-stage

ARG VERSION=dev
ENV APP_VERSION=$VERSION

COPY --from=vite_build /usr/src/frontend/build /usr/src/frontend/build

# Copy virtual environment from build stage
COPY --from=python-build-stage /app/.venv /app/.venv

WORKDIR /usr/src/app

RUN addgroup --system app && \
    adduser --system --ingroup app app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Install runtime dependencies
RUN --mount=type=cache,target=/root/.cache/apt \
    apt-get update && \
    apt-get install --no-install-recommends -y gettext supervisor libpq5 && \
    rm -rf /var/lib/apt/lists/*

COPY --chown=app:app ./docker/prod/django/start /start
COPY --chown=app:app ./docker/prod/procrastinate/start /start-procrastinate
COPY --chown=app:app ./docker/prod/supervisord/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY --chown=app:app ./docker/prod/supervisord/supervisord.conf /etc/supervisord.conf
COPY --chown=app:app ./docker/prod/supervisord/start /start-single

RUN sed -i 's/\r$//g' /start && \
    chmod +x /start && \
    sed -i 's/\r$//g' /start-procrastinate && \
    chmod +x /start-procrastinate && \
    sed -i 's/\r$//g' /start-single && \
    chmod +x /start-single

COPY --chown=app:app ./app .

RUN chown -R app:app /usr/src/app && \
    chown -R app:app /usr/src/frontend && \
    mkdir /temp && \
    chown -R app:app /temp

USER app

RUN python manage.py compilemessages --settings "WYGIWYH.settings"
RUN python manage.py collectstatic --noinput

CMD ["/start-single"]
