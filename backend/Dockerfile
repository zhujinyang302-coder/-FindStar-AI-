FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# 生产部署请通过环境变量注入
# DATABASE_URL / REDIS_URL / APP_SECRET_KEY / AI_API_KEY / BACKGROUND_JOBS_ENABLED 等。
# 数据库结构迁移不随应用启动自动执行，请在发布流程中显式执行 `alembic upgrade head`。
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]