import uvicorn

from polymarket_mm_bot.dashboard.startup import dashboard_port


def main() -> None:
    uvicorn.run(
        "polymarket_mm_bot.dashboard.app:app",
        host="0.0.0.0",
        port=dashboard_port(),
    )


if __name__ == "__main__":
    main()
