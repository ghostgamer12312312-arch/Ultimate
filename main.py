"""Bot entrypoint: builds the python-telegram-bot application and starts polling."""

from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

import config
import handlers
from database import Database

logger = logging.getLogger(__name__)

COMMANDS = [
    ("start", "Start your adventure"),
    ("register", "Create your character"),
    ("profile", "View character & allocate stats"),
    ("stats", "Alias for /profile"),
    ("hunt", "Fight monsters for XP and loot"),
    ("boss", "Join a world-boss raid"),
    ("duel", "Challenge a player to PvP"),
    ("inventory", "View bag and equipment"),
    ("equip", "Equip an item"),
    ("shop", "Browse the shop"),
    ("buy", "Buy from the shop"),
    ("sell", "Sell an item"),
    ("craft", "Craft gear and potions"),
    ("market", "Player marketplace"),
    ("clan", "Clan management"),
    ("quest", "Quest log"),
    ("daily", "Claim daily rewards"),
    ("leaderboard", "Top players and clans"),
    ("myid", "Show your Telegram user ID"),
    ("help", "Command guide"),
]


async def post_init(application: Application) -> None:
    db = Database(config.DB_PATH)
    await db.connect()
    await db.init()
    application.bot_data["db"] = db
    logger.info("Database ready at %s", config.DB_PATH)
    bot_user = application.bot.username or "unknown"
    logger.info("Connected to Telegram as @%s (bot id %s)", bot_user, application.bot.id)
    try:
        await application.bot.set_my_commands([BotCommand(cmd, desc) for cmd, desc in COMMANDS])
        logger.info("Bot command menu registered (%d commands)", len(COMMANDS))
    except TelegramError as exc:
        logger.warning("Could not set bot commands: %s", exc)


async def post_shutdown(application: Application) -> None:
    db = application.bot_data.get("db")
    if db is not None:
        await db.close()
        logger.info("Database connection closed.")


def build_application() -> Application:
    application = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("myid", handlers.myid_command))
    application.add_handler(CommandHandler("register", handlers.register_command))
    application.add_handler(CommandHandler("profile", handlers.profile_command))
    application.add_handler(CommandHandler("stats", handlers.profile_command))
    application.add_handler(CommandHandler("hunt", handlers.hunt_command))
    application.add_handler(CommandHandler("boss", handlers.boss_command))
    application.add_handler(CommandHandler("duel", handlers.duel_command))
    application.add_handler(CommandHandler("inventory", handlers.inventory_command))
    application.add_handler(CommandHandler("equip", handlers.equip_command))
    application.add_handler(CommandHandler("shop", handlers.shop_command))
    application.add_handler(CommandHandler("buy", handlers.buy_command))
    application.add_handler(CommandHandler("sell", handlers.sell_command))
    application.add_handler(CommandHandler("craft", handlers.craft_command))
    application.add_handler(CommandHandler("market", handlers.market_command))
    application.add_handler(CommandHandler("clan", handlers.clan_command))
    application.add_handler(CommandHandler("quest", handlers.quest_command))
    application.add_handler(CommandHandler("daily", handlers.daily_command))
    application.add_handler(CommandHandler("leaderboard", handlers.leaderboard_command))
    application.add_handler(CommandHandler("backup", handlers.backup_command))
    application.add_handler(CommandHandler("broadcast", handlers.broadcast_command))
    application.add_handler(CallbackQueryHandler(handlers.callback_router))
    application.add_error_handler(handlers.error_handler)
    return application


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    problems = config.validate()
    if problems:
        for problem in problems:
            logger.warning("Configuration: %s", problem)
    if not config.BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is not configured. Copy .env.example to .env and add your token."
        )

    logger.info("Starting %s v%s", config.GAME_NAME, "1.0.0")
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
