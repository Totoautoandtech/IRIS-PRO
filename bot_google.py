"""
bot_google.py — Bot Iris Google
Navigateur Discord via Gemini Google Search Grounding.
Préfixe : !google
"""
import os
import logging
import aiohttp
import discord
from discord.ext import commands
from google import genai
from google.genai import types
from shared import safe_send, BROWSER_HEADERS

logger = logging.getLogger("BotGoogle")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ai_client = None
if GEMINI_API_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("🌐 Gemini Google Search initialisé.")
    except Exception as e:
        logger.error(f"Gemini Google init: {e}")

intents    = discord.Intents.all()
bot_google = commands.Bot(command_prefix="!google ", intents=intents, help_command=None)


def setup_google():

    @bot_google.event
    async def on_ready():
        logger.info(f"🌐 Iris Google connectée : {bot_google.user}")
        await bot_google.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="le web 🌍")
        )

    @bot_google.command(name="help")
    async def google_help(ctx):
        embed = discord.Embed(
            title="🌐 Iris Google — Aide",
            description="Navigateur Discord · Gemini + Google Search Grounding",
            color=0x4285F4,
        )
        embed.add_field(name="`!google cherche REQUÊTE`", value="Recherche Google via Gemini (résultats actuels)", inline=False)
        embed.add_field(name="`!google visite URL`",      value="Lire et résumer le contenu d'une page web",       inline=False)
        embed.add_field(name="`!google actu [SUJET]`",    value="Actualités récentes sur un sujet",                inline=False)
        embed.add_field(name="`!google wiki SUJET`",      value="Résumé Wikipédia d'un sujet",                     inline=False)
        embed.set_footer(text="Iris Google · Gemini 2.5 Flash + Google Search Grounding")
        await ctx.send(embed=embed)

    @bot_google.command(name="cherche")
    async def google_cherche(ctx, *, recherche: str = None):
        if not recherche:
            return await ctx.send("Usage : `!google cherche intelligence artificielle`")
        if not ai_client:
            return await ctx.send("❌ `GEMINI_API_KEY` manquante.")
        async with ctx.typing():
            try:
                config   = types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
                response = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"Recherche et résume les informations actuelles sur : {recherche}. Réponds en français.",
                    config=config,
                )
                text  = response.text or "Aucun résultat."
                embed = discord.Embed(
                    title=f"🔍 Résultats — {recherche[:60]}",
                    description=text[:4000] + ("..." if len(text) > 4000 else ""),
                    color=0x4285F4,
                )
                embed.set_footer(text="Iris Google · Google Search Grounding · Gemini 2.5 Flash")
                await ctx.send(embed=embed)
            except Exception as e:
                await ctx.send(f"❌ Erreur : {e}")

    @bot_google.command(name="visite")
    async def google_visite(ctx, url: str = None):
        if not url:
            return await ctx.send("Usage : `!google visite https://exemple.com`")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        async with ctx.typing():
            try:
                async with aiohttp.ClientSession(headers=BROWSER_HEADERS) as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                        if resp.status != 200:
                            return await ctx.send(
                                f"❌ Impossible d'accéder à la page (HTTP {resp.status}).\n"
                                f"_Le site bloque les bots ou la page n'existe pas._"
                            )
                        raw_html = await resp.text()
                if not ai_client:
                    return await ctx.send("❌ Gemini non disponible.")
                prompt   = (
                    f"Tu es un navigateur web. Extrais et résume le contenu principal "
                    f"de cette page en Markdown clair. Ignore menus, pubs et scripts.\n\n"
                    f"{raw_html[:15000]}"
                )
                response = ai_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                embed    = discord.Embed(
                    title="🖥️ Page visitée",
                    description=f"[{url[:100]}]({url})",
                    color=0x4285F4,
                )
                embed.set_footer(text="Iris Google · Résumé IA de la page")
                await ctx.send(embed=embed)
                await safe_send(ctx, response.text)
            except aiohttp.ClientConnectorError:
                await ctx.send(f"❌ Impossible de se connecter à `{url}`. Vérifie l'URL.")
            except Exception as e:
                await ctx.send(f"❌ Erreur : {e}")

    @bot_google.command(name="actu")
    async def google_actu(ctx, *, sujet: str = "actualités du jour"):
        if not ai_client:
            return await ctx.send("❌ `GEMINI_API_KEY` manquante.")
        async with ctx.typing():
            try:
                config   = types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
                response = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=(
                        f"Donne-moi les 5 dernières actualités importantes sur : {sujet}. "
                        f"Format : titre, source, résumé en 2 lignes. Réponds en français."
                    ),
                    config=config,
                )
                embed = discord.Embed(
                    title=f"📰 Actualités — {sujet[:60]}",
                    description=(response.text or "Aucun résultat.")[:4000],
                    color=0x0984E3,
                )
                embed.set_footer(text="Iris Google · Google Search · Données actuelles")
                await ctx.send(embed=embed)
            except Exception as e:
                await ctx.send(f"❌ Erreur : {e}")

    @bot_google.command(name="wiki")
    async def google_wiki(ctx, *, sujet: str = None):
        if not sujet:
            return await ctx.send("Usage : `!google wiki intelligence artificielle`")
        if not ai_client:
            return await ctx.send("❌ `GEMINI_API_KEY` manquante.")
        async with ctx.typing():
            try:
                config   = types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
                response = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=(
                        f"Résume en français ce que dit Wikipédia sur : {sujet}. "
                        f"Structure : définition, points clés, dates importantes si pertinent."
                    ),
                    config=config,
                )
                embed = discord.Embed(
                    title=f"📖 Wikipedia — {sujet[:60]}",
                    description=(response.text or "Aucun résultat.")[:4000],
                    color=0xA29BFE,
                )
                embed.set_footer(text="Iris Google · Résumé Wikipedia via Gemini")
                await ctx.send(embed=embed)
            except Exception as e:
                await ctx.send(f"❌ Erreur : {e}")
