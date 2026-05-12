"""
EasyPassword Backend - FastAPI Application

Stack: Python + FastAPI + PostgreSQL + Redis
Version: V1
"""

from fastapi import FastAPI

app = FastAPI(
    title="EasyPassword API",
    description="Passwordless vault with WebAuthn and end-to-end encryption",
    version="1.0.0",
)


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
