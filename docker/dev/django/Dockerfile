FROM python:3.11-slim-bookworm AS python-build-stage

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY ../requirements.txt .
RUN pip wheel --wheel-dir /usr/src/app/wheels -r requirements.txt

FROM python:3.11-slim-bookworm AS python-run-stage

ARG VERSION=dev
ENV APP_VERSION=$VERSION

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=python-build-stage /usr/src/app/wheels /wheels/

RUN apt-get update && \
    apt-get install --no-install-recommends -y gettext supervisor && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && \
    pip install --no-cache-dir --no-index --find-links=/wheels/ /wheels/* && \
    rm -rf /wheels/ ~/.cache/pip/*

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

COPY ./app .
