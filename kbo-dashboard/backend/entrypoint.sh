#!/bin/sh
set -e

# DB가 비어 있으면 최초 1회 시드 후 API 기동.
python seed_if_empty.py

exec uvicorn main:app --host 0.0.0.0 --port 8001
