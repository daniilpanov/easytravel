FROM node:20-alpine AS build

WORKDIR /srv/web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend ./
RUN npm run build

FROM nginx:alpine
COPY --from=build /srv/web/dist /usr/share/nginx/html
EXPOSE 80
