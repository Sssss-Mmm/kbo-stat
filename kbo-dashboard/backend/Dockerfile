# 베이스 이미지는 digest 로 고정(재현 가능한 빌드). 올릴 때는 새 digest 로 테스트 후 바꾼다.
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 전이 의존성까지 고정한 목록(requirements.lock). requirements.txt 는 사람이 고치는 최상위 목록이다.
COPY kbo-dashboard/backend/requirements.lock /tmp/backend-requirements.lock
RUN pip install --no-cache-dir --no-deps -r /tmp/backend-requirements.lock && pip check

COPY kbo-dashboard/backend /app/kbo-dashboard/backend
COPY data /app/data

WORKDIR /app/kbo-dashboard/backend

RUN chmod +x entrypoint.sh

EXPOSE 8001

# 기동 시 DB가 비어 있으면 시드한 뒤 uvicorn 실행.
CMD ["./entrypoint.sh"]
