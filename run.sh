#!/usr/bin/env bash
# 개발용 실행 스크립트.
#
#   ./run.sh dev     백엔드(8000)와 프론트 개발 서버(5173)를 같이 띄운다
#   ./run.sh serve   프론트를 빌드해 백엔드 한 대로 서비스한다 (배포와 같은 모양)
#   ./run.sh test    파이썬 테스트와 프론트 타입 검사를 돌린다
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-dev}" in
  dev)
    (cd backend && python3 -m uvicorn app.main:app --reload --port 8000) &
    backend=$!
    trap 'kill $backend 2>/dev/null || true' EXIT
    (cd frontend && npm run dev)
    ;;
  serve)
    (cd frontend && npm install && npm run build)
    cd backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  test)
    (cd backend && python3 -m pytest -q)
    (cd frontend && npm run typecheck)
    ;;
  *)
    echo "쓰임: $0 [dev|serve|test]" >&2
    exit 1
    ;;
esac
