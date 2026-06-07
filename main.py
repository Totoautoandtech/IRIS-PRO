import sys, os
# Permet à Python de trouver facilement tous les modules dans le même dossier
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

import asyncio
import logging
from aiohttp import web
from dotenv import load_dotenv

# Chargement des variables d'environnement (.env)
load_dotenv()

# Configuration des logs pour voir ce qui se passe sur Render
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("IRIS_MAIN")

# ── IMPORTS DE CHAQUE BOT ─────────────────────────────────
# bot_ia et setup_ia restent intacts selon ta structure d'origine
from bot_ia import bot_ia, setup_ia  
from bot_google import bot_google, setup_google
from bot_trading import bot_trading, setup_trading
from bot_securite import bot_securite, setup_securite

# Récupération des Tokens depuis Render
TOKEN_IA       = os.getenv("DISCORD_TOKEN")
TOKEN_GOOGLE   = os.getenv("DISCORD_TOKEN_ACTU")
TOKEN_TRADING  = os.getenv("DISCORD_TOKEN_TRADING")
TOKEN_SECURITE = os.getenv("DISCORD_TOKEN_SECURITE")

# ── Serveur Web pour le Keep-Alive de Render ──────────────
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

# ── Fonction Principale (Main) ────────────────────────────
async def main():
    logger.info("🚀 Démarrage d'Iris Multi-Bot...")
    await start_web_server()

    # Initialisation et configuration de chaque bot selon ses besoins
    if TOKEN_IA:
        setup_ia()  # Appel SANS argument pour ton code bot_ia d'origine
        logger.info("✅ Configuration Bot IA initialisée.")
        
    if TOKEN_GOOGLE:
        setup_google()  # Appel pour le bot Google Actu
        logger.info("✅ Configuration Bot Google initialisée.")
        
    if TOKEN_TRADING:
        setup_trading()  # Appel pour le bot Trading
        logger.info("✅ Configuration Bot Trading initialisée.")
        
    if TOKEN_SECURITE:
        setup_securite(bot_securite)  # Reçoit l'argument requis pour injecter le GIF et les commandes
        logger.info("✅ Configuration Bot Sécurité initialisée.")

    # Préparation du lancement de toutes les instances de bots
    bots = []
    if TOKEN_IA:       bots.append(bot_ia.start(TOKEN_IA))
    if TOKEN_GOOGLE:   bots.append(bot_google.start(TOKEN_GOOGLE))
    if TOKEN_TRADING:  bots.append(bot_trading.start(TOKEN_TRADING))
    if TOKEN_SECURITE: bots.append(bot_securite.start(TOKEN_SECURITE))

    if not bots:
        logger.error("❌ Aucun token configuré dans l'environnement ! Arrêt.")
        return

    # Lancement simultané de toutes les connexions Discord
    await asyncio.gather(*bots)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt manuel demandé.")
