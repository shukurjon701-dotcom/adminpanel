"""
run_all.py — единая точка запуска для хостинга.

Запускает В ОДНОМ процессе (одном asyncio-цикле) сразу:
  1) Telegram-бота (bot.py, режим polling)
  2) веб админ-панель (admin_panel.py, FastAPI + uvicorn)

Оба используют одну и ту же базу academy_bot.db, поэтому их удобно
держать вместе. Локально можно по-прежнему запускать их по отдельности
(python3 bot.py и python3 admin_panel.py) — этот файл ничего не ломает.
"""

import asyncio
import logging
import os

import uvicorn

# ВАЖНО: импорт bot и admin_panel исполняет их код верхнего уровня,
# поэтому переменные окружения (TELEGRAM_BOT_TOKEN, GROQ_API_KEY и т.д.)
# уже должны быть заданы к этому моменту.
import bot
import admin_panel

log = logging.getLogger("run_all")

# На хостинге порт обычно передаётся через переменную PORT.
PORT = int(os.getenv("PORT", os.getenv("ADMIN_PORT", "8000")))


async def run_web_panel():
    config = uvicorn.Config(
        admin_panel.app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )
    server = uvicorn.Server(config)
    log.info(f"🖥️  Админ-панель запускается на порту {PORT}")
    await server.serve()


async def main():
    await asyncio.gather(
        run_web_panel(),
        bot.main(),
    )


if __name__ == "__main__":
    asyncio.run(main())
