# Основа: Python 3.12, как у вас на компьютере; slim = урезанная версия, меньше размер
FROM python:3.12-slim

# Не создавать файлы .pyc и сразу выводить журнал (иначе строки застревают в буфере и появляются в docker logs с задержкой)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Рабочая папка внутри контейнера, дальнейшие команды выполняются в ней
WORKDIR /app

# Сначала только список библиотек: Docker запоминает этот слой и при следующих
# сборках не ставит библиотеки заново, пока requirements.txt не изменился
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Обычный пользователь без прав администратора: если в приложении найдут уязвимость,
# взломщик получит доступ только к папке с фото, а не ко всему контейнеру.
# Папка /data/uploads — место для фото прогресса; в compose к ней подключается том (данные переживают пересборку).
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/uploads \
    && chown app:app /data/uploads
ENV UPLOAD_DIR=/data/uploads

# Теперь код (без .venv, .env и тестов, см. .dockerignore). Файлы принадлежат root и доступны приложению только для чтения
COPY . .
USER app

EXPOSE 8000

# Docker сам проверяет, что сервер отвечает и видит базу (/health); при сбое контейнер помечается unhealthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# При старте: применить миграции, затем запустить сервер.
# 0.0.0.0 = принимать подключения снаружи контейнера (127.0.0.1 виден только изнутри).
# exec — сервер становится главным процессом контейнера и получает сигнал остановки.
# Процесс один (без --workers): счётчики попыток входа хранятся в памяти процесса.
# --no-server-header — не сообщать в ответах, что это uvicorn.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn main:app --host 0.0.0.0 --port 8000 --no-server-header"]
