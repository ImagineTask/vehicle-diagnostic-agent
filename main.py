"""Entry point: `python main.py` or `uvicorn src.api:app --reload`."""

from __future__ import annotations

import uvicorn

from src.config.settings import settings


def main() -> None:
    uvicorn.run(
        "src.api:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.ENVIRONMENT == "local",
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
