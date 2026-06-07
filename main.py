import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))
import asyncio
import logging
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("IRIS_MAIN")

# Import de chaque bot (Variables du bot + Fonctions setup)
from bot_ia import bot_ia, setup_ia
from bot_google import bot_google, setup_google
from bot_trading import bot_trading, setup_trading
from bot_securite import bot_securite, setup_securite  # Importation corrigée ici !

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

    # CORRECTION : On passe chaque bot à sa fonction de setup respective
    if TOKEN_IA:
        setup_ia(bot_ia)
    if TOKEN_GOOGLE:
        setup_google(bot_google)
    if TOKEN_TRADING:
        setup_trading(bot_trading)
    if TOKEN_SECURITE:
        setup_securite(bot_securite)  # Le paramètre manquant est résolu ici !

    # Lancement de toutes les tâches en parallèle
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
