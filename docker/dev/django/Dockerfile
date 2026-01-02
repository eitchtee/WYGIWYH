FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ARG VERSION=dev
ENV APP_VERSION=$VERSION

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN addgroup --system app && \
    adduser --ingroup app --home /home/app app && \
    mkdir -p /home/app && \
    chown -R app:app /home/app

RUN apt-get update && \
    apt-get install --no-install-recommends -y gettext supervisor git && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --all-extras

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

ENV PATH="/opt/venv/bin:$PATH"

COPY ./app .

USER app

CMD ["/start-supervisor"]
