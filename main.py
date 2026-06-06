import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))
import asyncio
import logging
import os
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("IRIS_MAIN")

# Import de chaque bot
from bots.bot_ia       import bot_ia,      setup_ia
from bots.bot_google   import bot_google,   setup_google
from bots.bot_trading  import bot_trading,  setup_trading
from bots.bot_securite import bot_securite, setup_securite

TOKEN_IA       = os.getenv("DISCORD_TOKEN")
TOKEN_GOOGLE   = os.getenv("DISCORD_TOKEN_ACTU")
TOKEN_TRADING  = os.getenv("DISCORD_TOKEN_TRADING")
TOKEN_SECURITE = os.getenv("DISCORD_TOKEN_SECURITE")

# ── Web server keep-alive Render ──────────────────────────
async def handle_ping(request):
    return web.Response(text="Iris Multi-Bot OK — 4 bots actifs")

async def start_web_server():
    app    = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port   = int(os.environ.get("PORT", 10000))
    site   = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Web server Render démarré sur le port {port}")

# ── Main ──────────────────────────────────────────────────
async def main():
    logger.info("🚀 Démarrage Iris Multi-Bot...")
    await start_web_server()

    # Setup (enregistre les commandes/events de chaque bot)
    setup_ia()
    setup_google()
    setup_trading()
    setup_securite()

    bots = []
    if TOKEN_IA:       bots.append(bot_ia.start(TOKEN_IA))
    if TOKEN_GOOGLE:   bots.append(bot_google.start(TOKEN_GOOGLE))
    if TOKEN_TRADING:  bots.append(bot_trading.start(TOKEN_TRADING))
    if TOKEN_SECURITE: bots.append(bot_securite.start(TOKEN_SECURITE))

    if not bots:
        logger.error("❌ Aucun token configuré !")
        return

    await asyncio.gather(*bots)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt manuel.")
