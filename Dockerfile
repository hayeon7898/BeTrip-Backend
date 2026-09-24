FROM python:3.12-slim

WORKDIR /app

# scripts/seed.sql 실행용 psql 클라이언트
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# 컨테이너 시작 시 마이그레이션 적용 -> 시드 데이터 삽입(ON CONFLICT DO NOTHING이라 안전) -> 서버 기동
CMD ["sh", "-c", "alembic upgrade head && psql \"$(echo $DATABASE_URL | sed 's/+asyncpg//')\" -f scripts/seed.sql && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
