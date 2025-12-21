FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ARG VERSION=dev
ENV APP_VERSION=$VERSION

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && \
    apt-get install --no-install-recommends -y gettext supervisor && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY ./docker/dev/django/start /start
COPY ./docker/dev/procrastinate/start /start-procrastinate
COPY ./docker/dev/supervisord/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY ./docker/dev/supervisord/supervisord.conf /etc/supervisord.conf
COPY ./docker/dev/supervisord/start /start-supervisor

RUN sed -i 's/\r$//g' /start && \
    chmod +x /start && \
    sed -i 's/\r$//g' /start-procrastinate && \
    chmod +x /start-procrastinate && \
    sed -i 's/\r$//g' /start-supervisor && \
    chmod +x /start-supervisor

ENV PATH="/usr/src/app/.venv/bin:$PATH"

COPY ./app .

CMD ["/start-supervisor"]
