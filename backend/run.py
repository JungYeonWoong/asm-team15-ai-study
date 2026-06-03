"""개발 서버 실행 진입점: python run.py (uvicorn app.main:app)."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
