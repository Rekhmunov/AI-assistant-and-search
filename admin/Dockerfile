FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
ARG VITE_API_URL=
ARG VITE_ADMIN_API_KEY=dev-admin-key
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_ADMIN_API_KEY=$VITE_ADMIN_API_KEY
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
