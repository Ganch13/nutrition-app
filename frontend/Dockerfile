FROM node:24-slim
WORKDIR /app

# Не отправлять анонимную статистику Next.js
ENV NEXT_TELEMETRY_DISABLED=1

# Обычный пользователь node (встроен в образ) вместо root
RUN chown node:node /app
USER node

# Как и в backend: сначала зависимости (кэшируется), потом код
COPY --chown=node:node package.json package-lock.json ./
RUN npm ci
COPY --chown=node:node . .

# Адрес API вшивается в код при сборке:
#   http://localhost:8000 — запуск на одном компьютере (docker-compose.yml);
#   /api — публичный сервер, где сайт и API на одном домене (deploy/docker-compose.prod.yml).
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000

# Docker сам проверяет, что сайт отвечает
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:3000/login').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["npm", "start", "--", "-H", "0.0.0.0"]
