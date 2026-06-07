"""
bot_ia.py — Bot Iris IA
Gemini 2.5 Flash + génération d'images Pollinations CORRIGÉE.
CORRECTION IMAGE : on vérifie que l'image est bien générée avant d'envoyer.
Préfixe : !ia
"""
import os
import urllib.parse
import logging
import aiohttp
import discord
from discord.ext import commands
from google import genai
from shared import safe_send

logger = logging.getLogger("BotIA")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ai_client = None
if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("🔮 Gemini initialisé.")
    except Exception as e:
        logger.error(f"Gemini init: {e}")

intents = discord.Intents.all()
bot_ia  = commands.Bot(command_prefix="!ia ", intents=intents, help_command=None)


async def generate_image_url(prompt: str) -> str:
    """
    Génère une image via Pollinations.ai.
    CORRECTION : on force le modèle 'flux' et on vérifie que l'URL répond bien.
    """
    encoded   = urllib.parse.quote(prompt, safe="")
    image_url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1024&height=576&nologo=true&model=flux&seed=42"
    )
    # Vérification que l'image est bien accessible (évite l'embed vide)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=45)) as resp:
            if resp.status != 200:
                raise Exception(f"Pollinations a retourné HTTP {resp.status}")
            content_type = resp.headers.get("Content-Type", "")
            if "image" not in content_type:
                raise Exception(f"Type de contenu inattendu : {content_type}")
    return image_url


def setup_ia():

    @bot_ia.event
    async def on_ready():
        logger.info(f"🔮 Iris IA connectée : {bot_ia.user}")
        await bot_ia.change_presence(
            activity=discord.Activity(type=discord.ActivityType.playing, name="IA & Images 🐾")
        )

    @bot_ia.event
    async def on_message(message):
        if message.author.bot:
            return
        if bot_ia.user and bot_ia.user in message.mentions:
            prompt = (message.content
                      .replace(f"<@{bot_ia.user.id}>", "")
                      .replace(f"<@!{bot_ia.user.id}>", "")
                      .strip())
            if prompt:
                if not ai_client:
                    await message.channel.send("⚠️ Gemini non disponible. Vérifie `GEMINI_API_KEY`.")
                    return
                async with message.channel.typing():
                    try:
                        resp = ai_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                        await safe_send(message.channel, resp.text)
                    except Exception as e:
                        await message.channel.send(f"⚠️ Erreur Gemini : {e}")
        await bot_ia.process_commands(message)

    @bot_ia.command(name="help")
    async def ia_help(ctx):
        embed = discord.Embed(
            title="🔮 Iris IA — Aide",
            description="Bot IA · Gemini 2.5 Flash + génération d'images Pollinations",
            color=0x6C5CE7,
        )
        embed.add_field(name="`!ia ask QUESTION`",  value="Poser une question à Gemini",               inline=False)
        embed.add_field(name="`@Iris QUESTION`",    value="Mentionner le bot pour une réponse rapide",  inline=False)
        embed.add_field(name="`!ia imagine SUJET`", value="Générer une image IA (Pollinations · Flux)", inline=False)
        embed.set_footer(text="Iris IA · Gemini 2.5 Flash + Pollinations Flux")
        await ctx.send(embed=embed)

    @bot_ia.command(name="ask")
    async def ia_ask(ctx, *, question: str = None):
        if not question:
            return await ctx.send("Usage : `!ia ask ta question`")
        if not ai_client:
            return await ctx.send("❌ Gemini non configuré. Vérifie `GEMINI_API_KEY`.")
        async with ctx.typing():
            try:
                resp = ai_client.models.generate_content(model="gemini-2.5-flash", contents=question)
                await safe_send(ctx, resp.text)
            except Exception as e:
                await ctx.send(f"⚠️ Erreur : {e}")

    @bot_ia.command(name="imagine")
    async def ia_imagine(ctx, *, prompt: str = None):
        """
        CORRECTION PRINCIPALE :
        - On attend que Pollinations génère vraiment l'image (peut prendre 10-30s)
        - On envoie d'abord un message d'attente
        - On vérifie que l'URL retourne bien une image avant d'envoyer l'embed
        """
        if not prompt:
            return await ctx.send("Usage : `!ia imagine un dragon cyberpunk`")

        wait_msg = await ctx.send("🎨 Génération de l'image en cours... (10-30 secondes)")
        async with ctx.typing():
            try:
                image_url = await generate_image_url(prompt)
                embed = discord.Embed(
                    title=f"🎨 {prompt[:100]}",
                    color=0x6C5CE7,
                )
                embed.set_image(url=image_url)
                embed.set_footer(text="Iris IA · Pollinations.ai · Modèle Flux")
                await wait_msg.delete()
                await ctx.send(embed=embed)
            except Exception as e:
                await wait_msg.edit(content=f"❌ Erreur génération image : {e}\n_Réessaie avec un prompt différent._")
