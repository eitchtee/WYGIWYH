FROM python:3.11.8-slim-buster AS python-build-stage

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    gettext \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt .
RUN pip wheel --wheel-dir /usr/src/app/wheels -r requirements.txt

FROM node:lts-alpine AS webpack_build
WORKDIR /usr/src/frontend
COPY ./frontend .
COPY ./app/templates /usr/src/app/templates
RUN npm config set registry https://registry.npmmirror.com/ && \
    npm install --verbose && \
    npm run build && \
    npm cache clean --force

FROM python:3.11.8-slim-buster AS python-run-stage
COPY --from=webpack_build /usr/src/frontend/build /usr/src/frontend/build

WORKDIR /usr/src/app

RUN addgroup --system app && \
    adduser --system --ingroup app app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=python-build-stage /usr/src/app/wheels /wheels/
RUN apt-get update && \
    apt-get install --no-install-recommends -y gettext && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --upgrade pip && \
    pip install --no-cache-dir --no-index --find-links=/wheels/ /wheels/* && \
    rm -rf /wheels/ ~/.cache/pip/*

COPY --chown=app:app ./docker/prod/django/start /start
COPY --chown=app:app ./docker/prod/procrastinate/start /start-procrastinate
RUN sed -i 's/\r$//g' /start && \
    chmod +x /start && \
    sed -i 's/\r$//g' /start-procrastinate && \
    chmod +x /start-procrastinate

COPY --chown=app:app ./app .

RUN chown -R app:app /usr/src/app && \
    chown -R app:app /usr/src/frontend && \
    mkdir /temp && \
    chown -R app:app /temp

USER app

RUN python manage.py compilemessages --settings "WYGIWYH.settings"
