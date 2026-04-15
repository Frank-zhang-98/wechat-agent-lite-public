from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("WAL_CONSOLE_HOST", "0.0.0.0"),
        port=int(os.getenv("WAL_CONSOLE_PORT", "8080")),
        reload=False,
    )
