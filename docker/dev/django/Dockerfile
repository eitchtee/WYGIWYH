FROM python:3.11-slim-buster AS python-build-stage

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY ../requirements.txt .
RUN pip wheel --wheel-dir /usr/src/app/wheels -r requirements.txt

FROM python:3.11-slim-buster AS python-run-stage

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=python-build-stage /usr/src/app/wheels /wheels/

RUN apt-get update && \
    apt-get install --no-install-recommends -y gettext && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && \
    pip install --no-cache-dir --no-index --find-links=/wheels/ /wheels/* && \
    rm -rf /wheels/ ~/.cache/pip/*

COPY ./docker/dev/django/start /start
COPY ./docker/dev/procrastinate/start /start-procrastinate
RUN sed -i 's/\r$//g' /start && \
    chmod +x /start && \
    sed -i 's/\r$//g' /start-procrastinate && \
    chmod +x /start-procrastinate

COPY ./app .
