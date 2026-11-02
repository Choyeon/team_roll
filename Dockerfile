FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/team_roll

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY static ./static
COPY alembic.ini pyproject.toml ./

# 实时连接表与限流计数器都在进程内存里，因此固定单 worker；扩容请横向多副本 + 会话粘连。
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /srv/team_roll/data \
    && chown -R appuser:appuser /srv/team_roll
USER appuser

ENV DATABASE_URL=sqlite:////srv/team_roll/data/team_roll.db \
    ENVIRONMENT=prod

EXPOSE 8803
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8803/healthz',timeout=4).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8803", "--workers", "1"]
