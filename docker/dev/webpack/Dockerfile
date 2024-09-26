FROM docker.io/node:18-bookworm-slim

WORKDIR /usr/src/frontend

COPY ./frontend/package.json .

RUN npm install --verbose && npm cache clean --force

ENV PATH ./node_modules/.bin/:$PATH
