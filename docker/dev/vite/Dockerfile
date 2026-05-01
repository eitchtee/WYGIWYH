FROM node:lts-alpine

WORKDIR /usr/src/frontend

COPY ./frontend/package.json ./frontend/package-lock.json ./

RUN npm ci --verbose && npm cache clean --force

ENV PATH ./node_modules/.bin/:$PATH

CMD ["npm", "run", "dev"]
