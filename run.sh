#!/usr/bin/env bash
# 실행 스크립트. 필요한 것은 알아서 설치한다.
#
#   ./run.sh          프론트를 빌드해 한 대로 서비스 (http://localhost:8000)
#   ./run.sh dev      백엔드(8000) + 프론트 개발 서버(5173). 코드 고치면 바로 반영
#   ./run.sh test     파이썬 테스트와 프론트 타입 검사
#   ./run.sh smoke    브라우저 3개로 한 판을 끝까지 진행 (서버가 떠 있어야 함)
#
# 필요한 것: Python 3.10 이상, Node 18 이상.
set -euo pipefail
cd "$(dirname "$0")"

VENV=backend/.venv
PY="$VENV/bin/python"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "$1 이(가) 필요합니다. 설치하고 다시 시도해 주세요." >&2
    exit 1
  }
}

# 파이썬 의존성은 backend/.venv 안에만 설치한다. 시스템 파이썬은 건드리지 않는다.
ensure_backend() {
  need python3
  if [ ! -x "$PY" ]; then
    echo "→ 파이썬 가상환경을 만듭니다 ($VENV)"
    python3 -m venv "$VENV"
  fi
  if [ ! -f "$VENV/.installed" ] || [ backend/requirements-dev.txt -nt "$VENV/.installed" ]; then
    echo "→ 파이썬 패키지를 설치합니다"
    "$PY" -m pip install --quiet --upgrade pip
    "$PY" -m pip install --quiet -r backend/requirements-dev.txt
    touch "$VENV/.installed"
  fi
}

ensure_frontend() {
  need npm
  if [ ! -d frontend/node_modules ] || [ frontend/package.json -nt frontend/node_modules ]; then
    echo "→ 프론트 패키지를 설치합니다"
    (cd frontend && npm install --no-fund --no-audit)
  fi
}

case "${1:-serve}" in
  serve)
    ensure_backend
    ensure_frontend
    echo "→ 프론트를 빌드합니다"
    (cd frontend && npm run build)
    echo
    echo "   http://localhost:${PORT:-8000} 에서 열립니다. 멈추려면 Ctrl+C."
    echo
    cd backend && exec ../"$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;

  dev)
    ensure_backend
    ensure_frontend
    (cd backend && ../"$PY" -m uvicorn app.main:app --reload --port 8000) &
    backend=$!
    trap 'kill $backend 2>/dev/null || true' EXIT
    echo
    echo "   http://localhost:5173 으로 접속하세요 (API 는 8000 으로 넘어갑니다)."
    echo
    (cd frontend && npm run dev)
    ;;

  test)
    ensure_backend
    ensure_frontend
    (cd backend && ../"$PY" -m pytest -q)
    (cd frontend && npm run typecheck)
    ;;

  smoke)
    ensure_frontend
    if [ ! -d frontend/node_modules/playwright ]; then
      echo "→ 스모크 테스트용 playwright 를 설치합니다"
      (cd frontend && npm install --no-save --no-fund playwright)
    fi
    # 이미 크로미움이 있는 환경이면 CHROME_PATH 로 알려 주고 내려받기를 건너뛴다.
    if [ -z "${CHROME_PATH:-}" ]; then
      (cd frontend && npx playwright install chromium) || {
        echo "브라우저를 내려받지 못했습니다. 이미 크로미움이 있다면 CHROME_PATH 로 알려 주세요:" >&2
        echo "  CHROME_PATH=/경로/chrome ./run.sh smoke" >&2
        exit 1
      }
    fi
    (cd frontend && npm run smoke)
    ;;

  *)
    echo "쓰임: $0 [serve|dev|test|smoke]" >&2
    exit 1
    ;;
esac
