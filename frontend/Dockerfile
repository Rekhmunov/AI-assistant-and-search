FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
ARG VITE_API_URL=
ARG VITE_MAX_BOT_URL=https://max.ru
ARG VITE_PUBLIC_URL=https://glosix.ru
ARG VITE_BUILD_ID=dev
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_MAX_BOT_URL=$VITE_MAX_BOT_URL
ENV VITE_PUBLIC_URL=$VITE_PUBLIC_URL
ENV VITE_BUILD_ID=$VITE_BUILD_ID
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
