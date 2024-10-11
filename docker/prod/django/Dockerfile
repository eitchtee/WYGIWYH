# pull official base image
FROM python:3.11.8-slim-buster AS python
LABEL authors="Herculino de Miranda Trotta"

FROM docker.io/python AS python-build-stage

RUN apt-get update && apt-get install --no-install-recommends -y \
  # dependencies for building Python packages
  build-essential \
  gettext \
  # psycopg2 dependencies
  libpq-dev

# Requirements are installed here to ensure they will be cached.
COPY ./requirements.txt .

# Create Python Dependency and Sub-Dependency Wheels.
RUN pip wheel --wheel-dir /usr/src/app/wheels  \
  -r requirements.txt

FROM node:lts-alpine AS webpack_build

WORKDIR /usr/src/frontend

COPY ./frontend .
COPY ./app/templates /usr/src/app/templates
RUN npm config set registry https://registry.npmmirror.com/
RUN npm install --verbose
RUN npm run build

FROM docker.io/python AS python-run-stage
COPY --from=webpack_build /usr/src/frontend/build /usr/src/frontend/build

# set work directory
WORKDIR /usr/src/app

RUN addgroup --system app \
    && adduser --system --ingroup app app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY --from=python-build-stage /usr/src/app/wheels  /wheels/
RUN apt update && apt install --no-install-recommends -y gettext
RUN pip install --upgrade pip
RUN pip install --no-cache-dir --no-index --find-links=/wheels/ /wheels/* \
  && rm -rf /wheels/

COPY --chown=app:app ./docker/prod/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start

COPY --chown=app:app ./docker/prod/celery/worker/start /start-celeryworker
RUN sed -i 's/\r$//g' /start-celeryworker
RUN chmod +x /start-celeryworker

COPY --chown=app:app ./docker/prod/celery/beat/start /start-celerybeat
RUN sed -i 's/\r$//g' /start-celerybeat
RUN chmod +x /start-celerybeat

COPY --chown=app:app ./docker/prod/celery/flower/start /start-flower
RUN sed -i 's/\r$//g' /start-flower
RUN chmod +x /start-flower

# copy project
COPY ./app .

# chown all the files to the app user
RUN chown -R app:app /usr/src/app
RUN chown -R app:app /usr/src/frontend

RUN mkdir /temp
RUN chown -R app:app /temp

# change to the app user
USER app

RUN python manage.py compilemessages --settings "WYGIWYH.settings"
