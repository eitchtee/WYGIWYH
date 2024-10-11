# pull official base image
FROM python:3.11-slim-buster AS python
LABEL authors="Herculino de Miranda Trotta"

FROM docker.io/python AS python-build-stage

RUN apt update && apt install --no-install-recommends -y \
  # dependencies for building Python packages \
  build-essential \
  # psycopg2 dependencies \
  gettext \
  libpq-dev

# Requirements are installed here to ensure they will be cached.
COPY ../requirements.txt .

# Create Python Dependency and Sub-Dependency Wheels.
RUN pip wheel --wheel-dir /usr/src/app/wheels  \
  -r requirements.txt


FROM docker.io/python AS python-run-stage
#COPY --from=webpack_build /usr/src/frontend/build /usr/src/frontend/build

# set work directory
WORKDIR /usr/src/app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY --from=python-build-stage /usr/src/app/wheels  /wheels/
RUN apt update && apt install --no-install-recommends -y gettext
RUN pip install --upgrade pip
RUN pip install --no-cache-dir --no-index --find-links=/wheels/ /wheels/* \
  && rm -rf /wheels/

COPY ./docker/dev/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start

COPY ./docker/dev/procrastinate/start /start-procrastinate
RUN sed -i 's/\r$//g' /start-procrastinate
RUN chmod +x /start-procrastinate

# copy project
COPY ./app .
