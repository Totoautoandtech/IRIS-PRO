"""
bots/bot_ia.py
Bot Iris IA — Gemini 2.5 Flash + génération d'images Pollinations.
Préfixe : !ia
"""
import os
import urllib.parse
import logging
import discord
from discord.ext import commands
from google import genai
from utils.shared import safe_send

logger = logging.getLogger("BotIA")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ── Client Gemini ─────────────────────────────────────────
ai_client = None
if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("🔮 Gemini initialisé.")
    except Exception as e:
        logger.error(f"Gemini init: {e}")

# ── Bot ───────────────────────────────────────────────────
intents = discord.Intents.all()
bot_ia  = commands.Bot(command_prefix="!ia ", intents=intents, help_command=None)


def setup_ia():
    """Appelé par main.py pour enregistrer les events/commandes."""

    # ── Events ────────────────────────────────────────────
    @bot_ia.event
    async def on_ready():
        logger.info(f"🔮 Iris IA connectée : {bot_ia.user}")
        await bot_ia.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing, name="IA & Images 🐾"
            )
        )

    @bot_ia.event
    async def on_message(message):
        if message.author.bot:
            return
        # Réponse si le bot est mentionné directement
        if bot_ia.user and bot_ia.user in message.mentions:
            prompt = (
                message.content
                .replace(f"<@{bot_ia.user.id}>", "")
                .replace(f"<@!{bot_ia.user.id}>", "")
                .strip()
            )
            if prompt:
                if not ai_client:
                    await message.channel.send("⚠️ Gemini non disponible.")
                    return
                async with message.channel.typing():
                    try:
                        resp = ai_client.models.generate_content(
                            model="gemini-2.5-flash", contents=prompt
                        )
                        await safe_send(message.channel, resp.text)
                    except Exception as e:
                        await message.channel.send(f"⚠️ Erreur Gemini : {e}")
        await bot_ia.process_commands(message)

    # ── Commandes ─────────────────────────────────────────
    @bot_ia.command(name="help")
    async def ia_help(ctx):
        embed = discord.Embed(
            title="🔮 Iris IA — Aide",
            description="Bot IA propulsé par Gemini 2.5 Flash + Pollinations.ai",
            color=0x6C5CE7,
        )
        embed.add_field(name="`!ia ask QUESTION`",  value="Poser une question à Gemini",              inline=False)
        embed.add_field(name="`@Iris QUESTION`",    value="Mentionner le bot pour une réponse rapide", inline=False)
        embed.add_field(name="`!ia imagine SUJET`", value="Générer une image IA (Pollinations)",       inline=False)
        embed.set_footer(text="Iris IA · Gemini 2.5 Flash + Pollinations.ai")
        await ctx.send(embed=embed)

    @bot_ia.command(name="ask")
    async def ia_ask(ctx, *, question: str = None):
        if not question:
            return await ctx.send("Usage : `!ia ask ta question`")
        if not ai_client:
            return await ctx.send("❌ Gemini non configuré. Vérifie `GEMINI_API_KEY`.")
        async with ctx.typing():
            try:
                resp = ai_client.models.generate_content(
                    model="gemini-2.5-flash", contents=question
                )
                await safe_send(ctx, resp.text)
            except Exception as e:
                await ctx.send(f"⚠️ Erreur : {e}")

    @bot_ia.command(name="imagine")
    async def ia_imagine(ctx, *, prompt: str = None):
        if not prompt:
            return await ctx.send("Usage : `!ia imagine un dragon cyberpunk`")
        async with ctx.typing():
            try:
                encoded   = urllib.parse.quote(prompt)
                image_url = (
                    f"https://image.pollinations.ai/prompt/{encoded}"
                    f"?width=1024&height=576&nologo=true&enhance=true&model=flux"
                )
                embed = discord.Embed(title=f"🎨 {prompt[:100]}", color=0x6C5CE7)
                embed.set_image(url=image_url)
                embed.set_footer(text="Iris IA · Pollinations.ai · Modèle Flux")
                await ctx.send(embed=embed)
            except Exception as e:
                await ctx.send(f"❌ Erreur image : {e}")
