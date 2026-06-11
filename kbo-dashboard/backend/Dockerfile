FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY kbo-dashboard/backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt

COPY kbo-dashboard/backend /app/kbo-dashboard/backend
COPY data /app/data

WORKDIR /app/kbo-dashboard/backend

RUN chmod +x entrypoint.sh

EXPOSE 8001

# 기동 시 DB가 비어 있으면 시드한 뒤 uvicorn 실행.
CMD ["./entrypoint.sh"]
