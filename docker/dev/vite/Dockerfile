FROM node:lts-alpine

WORKDIR /usr/src/frontend

COPY ./frontend/package.json ./frontend/package-lock.json ./
COPY ./docker/dev/vite/entrypoint.sh /usr/local/bin/vite-entrypoint
RUN chmod +x /usr/local/bin/vite-entrypoint

ENV PATH ./node_modules/.bin/:$PATH

ENTRYPOINT ["vite-entrypoint"]
