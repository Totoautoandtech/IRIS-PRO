"""
bots/bot_trading.py
Bot Iris Trading — Données Yahoo Finance, watchlist perso, alertes DM, conseils IA.
Préfixe : !iris
"""
import os
import asyncio
import time
import logging
import discord
from datetime import datetime, timezone
from discord.ext import commands, tasks

# --- CORRECTION ICI : On supprime "utils." ---
from market_data  import (MarketData, format_price, format_change,
                                  get_emoji, market_state_label, format_quote_line)
from user_settings import UserSettings
from shared        import pollinations_chat
logger = logging.getLogger("BotTrading")

ALERT_COOLDOWN = 5 * 60  # 5 min anti-spam

mkt = MarketData()
usr = UserSettings()

live_messages:   dict = {}
alert_cooldowns: dict = {}

intents     = discord.Intents.all()
bot_trading = commands.Bot(command_prefix="!iris ", intents=intents, help_command=None)


# ── Embed dashboard ───────────────────────────────────────
async def build_market_embed(settings: dict, user_id: int) -> discord.Embed:
    watchlist = settings.get("watchlist", [])
    quotes    = await mkt.get_multiple(watchlist)
    now_str   = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    avg_chg   = sum(q.get("changePercent", 0) for q in quotes) / len(quotes) if quotes else 0
    color     = 0x00b894 if avg_chg > 0.5 else (0xff7675 if avg_chg < -0.5 else 0x6C5CE7)
    up        = sum(1 for q in quotes if q.get("changePercent", 0) > 0)
    down      = sum(1 for q in quotes if q.get("changePercent", 0) < 0)
    flat      = len(quotes) - up - down
    trend     = "📈 Haussier" if up > down else ("📉 Baissier" if down > up else "↔️ Neutre")

    embed = discord.Embed(
        title="💜 Iris Trading — Dashboard Live",
        description=(
            f"🕐 **{now_str}** · Auto 30s\n"
            f"{trend} · 🟢 {up} · 🔴 {down} · ⚪ {flat}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if not quotes:
        embed.add_field(name="📭 Watchlist vide", value="Tape `!iris settings add SYMBOLE`", inline=False)
        return embed

    indices = [q for q in quotes if q["symbol"].startswith("^")]
    crypto  = [q for q in quotes if "-USD" in q["symbol"] or "-EUR" in q["symbol"]]
    stocks  = [q for q in quotes if q not in indices and q not in crypto]

    if indices: embed.add_field(name="📊 INDICES", value="\n\n".join(format_quote_line(q) for q in indices), inline=False)
    if stocks:  embed.add_field(name="🏢 ACTIONS", value="\n\n".join(format_quote_line(q) for q in stocks),  inline=False)
    if crypto:  embed.add_field(name="₿ CRYPTO",   value="\n\n".join(format_quote_line(q) for q in crypto),  inline=False)

    states = list({q.get("marketState", "UNKNOWN") for q in quotes})
    embed.add_field(name="🕐 Marchés", value=" · ".join(market_state_label(s) for s in states), inline=False)
    embed.set_footer(text="Iris Trading · Watchlist perso · Yahoo Finance")
    return embed


# ── Conseil IA ────────────────────────────────────────────
async def get_ai_advice(user_id: int, symbols: list) -> str:
    quotes = await mkt.get_multiple(symbols)
    if not quotes:
        return "❌ Données introuvables pour ces symboles."

    settings  = usr.get(user_id)
    portfolio = settings.get("portfolio", [])
    mkt_txt   = "\n".join(
        f"{q['symbol']}: {format_price(q['price'])} ({format_change(q.get('changePercent',0))}% aujourd'hui), "
        f"volume: {q.get('volume',0):,}, état: {q.get('marketState','?')}"
        for q in quotes
    )
    ptf_ctx = ""
    if portfolio:
        ptf_ctx = "\n\nPortfolio : " + ", ".join(
            f"{p['qty']}x {p['symbol']} acheté à {p.get('buy_price','inconnu')}"
            for p in portfolio
        )
    try:
        return await pollinations_chat(
            system=(
                "Tu es Iris, conseillère en trading expérimentée, directe et honnête. "
                "Rappelle TOUJOURS que ce ne sont pas des conseils financiers professionnels. "
                "Réponds en français avec emojis. Maximum 450 mots."
            ),
            user=(
                f"Données actuelles :\n\n{mkt_txt}{ptf_ctx}\n\n"
                "Donne : 1️⃣ Analyse rapide 2️⃣ Points d'attention "
                "3️⃣ Ce que tu ferais 4️⃣ Niveau de risque"
            ),
        )
    except asyncio.TimeoutError:
        return "⏱️ L'IA met trop de temps. Réessaie."
    except Exception as e:
        return f"❌ Erreur IA : {e}"


# ── Boutons Live ──────────────────────────────────────────
class LiveView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="🔄 Actualiser", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, _btn):
        await interaction.response.defer()
        settings = usr.get(self.user_id)
        embed    = await build_market_embed(settings, self.user_id)
        await interaction.message.edit(embed=embed)

    @discord.ui.button(label="➕ Ajouter", style=discord.ButtonStyle.primary)
    async def add_sym(self, interaction: discord.Interaction, _btn):
        await interaction.response.send_message(
            "Tape `!iris settings add SYMBOLE`", ephemeral=True
        )

    @discord.ui.button(label="🤖 Conseil IA", style=discord.ButtonStyle.success)
    async def ai_advice(self, interaction: discord.Interaction, _btn):
        await interaction.response.defer(ephemeral=True)
        reply = await get_ai_advice(
            interaction.user.id,
            usr.get(interaction.user.id).get("watchlist", [])
        )
        await interaction.followup.send(reply, ephemeral=True)


def setup_trading():

    @bot_trading.event
    async def on_ready():
        logger.info(f"📈 Iris Trading connectée : {bot_trading.user}")
        mkt.start()
        update_live_loop.start()
        check_alerts_loop.start()
        await bot_trading.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="les marchés 📈")
        )

    @tasks.loop(seconds=30)
    async def update_live_loop():
        for key, info in list(live_messages.items()):
            try:
                channel = bot_trading.get_channel(info["channel_id"])
                if not channel:
                    live_messages.pop(key, None); continue
                msg      = await channel.fetch_message(info["message_id"])
                settings = usr.get(info["user_id"])
                embed    = await build_market_embed(settings, info["user_id"])
                await msg.edit(embed=embed)
            except discord.NotFound:
                live_messages.pop(key, None)
            except Exception as e:
                logger.warning(f"update_live: {e}")

    @tasks.loop(seconds=60)
    async def check_alerts_loop():
        for user_id, settings in usr.get_all():
            if not settings.get("alerts_enabled", True): continue
            threshold = settings.get("alert_threshold", 3.0)
            symbols   = list(set(
                settings.get("watchlist", []) +
                [p["symbol"] for p in settings.get("portfolio", [])]
            ))
            quotes = await mkt.get_multiple(symbols)
            for data in quotes:
                if abs(data.get("changePercent", 0)) < threshold: continue
                symbol = data["symbol"]
                cd     = alert_cooldowns.setdefault(user_id, {})
                if time.time() - cd.get(symbol, 0) < ALERT_COOLDOWN: continue
                cd[symbol] = time.time()
                try:
                    user      = await bot_trading.fetch_user(user_id)
                    direction = "🚀 Hausse" if data["changePercent"] > 0 else "📉 Baisse"
                    embed = discord.Embed(
                        title=f"🔔 Alerte — {symbol}",
                        description=(
                            f"**{direction} notable !**\n\n"
                            f"📊 Variation : **{format_change(data['changePercent'])}%**\n"
                            f"💲 Prix : **{format_price(data['price'])} {data.get('currency','')}**\n\n"
                            f"_Alerte personnelle · uniquement pour toi · cooldown 5 min._\n"
                            f"Tape `!iris conseil {symbol}` pour un avis IA."
                        ),
                        color=0x00b894 if data["changePercent"] > 0 else 0xff7675,
                        timestamp=datetime.now(timezone.utc),
                    )
                    await user.send(embed=embed)
                except Exception:
                    pass

    # ── Commandes ─────────────────────────────────────────
    @bot_trading.command(name="help")
    async def cmd_help(ctx):
        embed = discord.Embed(
            title="💜 Iris Trading — Aide",
            description="⚠️ *Settings et données 100% personnels — invisibles pour les autres.*",
            color=0x6C5CE7,
        )
        embed.add_field(name="`!iris live`",           value="Dashboard live (auto 30s)",         inline=False)
        embed.add_field(name="`!iris info SYMBOLE`",   value="Fiche détaillée d'un actif",        inline=False)
        embed.add_field(name="`!iris settings`",       value="Ta watchlist, alertes, devise",     inline=False)
        embed.add_field(name="`!iris portfolio`",      value="Ton portfolio & P&L",               inline=False)
        embed.add_field(name="`!iris alert SYM %`",    value="Alerte DM personnelle",             inline=False)
        embed.add_field(name="`!iris conseil [SYM]`",  value="Conseil IA (Pollinations, gratuit)", inline=False)
        embed.add_field(name="`!iris reset`",          value="Réinitialiser tes settings",        inline=False)
        embed.add_field(
            name="💡 Symboles",
            value="`^FCHI` CAC40 · `^GSPC` S&P500 · `BTC-USD` Bitcoin · `AAPL` Apple · `BNP.PA` BNP",
            inline=False,
        )
        embed.set_footer(text="Iris Trading · Yahoo Finance + Pollinations.ai")
        await ctx.send(embed=embed)

    @bot_trading.command(name="live")
    async def cmd_live(ctx):
        uid      = ctx.author.id
        settings = usr.get(uid)
        embed    = await build_market_embed(settings, uid)
        view     = LiveView(uid)
        msg      = await ctx.send(embed=embed, view=view)
        live_messages[f"{ctx.channel.id}:{uid}"] = {
            "channel_id": ctx.channel.id,
            "message_id": msg.id,
            "user_id":    uid,
        }
        try: await ctx.message.delete()
        except Exception: pass

    @bot_trading.command(name="settings")
    async def cmd_settings(ctx, sub: str = "view", *args):
        uid = ctx.author.id
        sub = sub.lower()
        if sub == "view":
            s = usr.get(uid)
            embed = discord.Embed(
                title="⚙️ Tes Paramètres", description="*100% personnels.*", color=0x6C5CE7
            )
            embed.add_field(name="📊 Watchlist",    value=", ".join(s["watchlist"]) or "Vide",         inline=False)
            embed.add_field(name="🔔 Alertes",      value="✅ On" if s["alerts_enabled"] else "❌ Off", inline=True)
            embed.add_field(name="📈 Seuil",        value=f"{s['alert_threshold']}%",                  inline=True)
            embed.add_field(name="💱 Devise",       value=s["currency"],                                inline=True)
            return await ctx.send(embed=embed)
        if sub == "add" and args:
            sym = args[0].upper()
            if not await mkt.is_valid(sym):
                return await ctx.send(f"❌ `{sym}` introuvable. Vérifie le ticker Yahoo Finance.")
            usr.add_to_watchlist(uid, sym)
            return await ctx.send(f"✅ **{sym}** ajouté à **ta** watchlist !")
        if sub == "remove" and args:
            usr.remove_from_watchlist(uid, args[0].upper())
            return await ctx.send(f"🗑️ **{args[0].upper()}** retiré.")
        if sub == "alert" and args:
            val = args[0].lower()
            if val == "on":
                usr.update(uid, {"alerts_enabled": True}); return await ctx.send("🔔 Alertes activées.")
            if val == "off":
                usr.update(uid, {"alerts_enabled": False}); return await ctx.send("🔕 Alertes désactivées.")
            try:
                usr.update(uid, {"alert_threshold": float(val)})
                return await ctx.send(f"📊 Seuil → **{val}%**.")
            except ValueError: pass
        if sub == "currency" and args:
            usr.update(uid, {"currency": args[0].upper()})
            return await ctx.send(f"💱 Devise → **{args[0].upper()}**.")
        await ctx.send("`view` · `add SYM` · `remove SYM` · `alert on/off` · `alert 3` · `currency EUR`")

    @bot_trading.command(name="info")
    async def cmd_info(ctx, symbol: str = None):
        if not symbol:
            return await ctx.send("Usage : `!iris info SYMBOLE`")
        async with ctx.typing():
            data = await mkt.get_detailed_quote(symbol.upper())
        if not data:
            return await ctx.send(f"❌ `{symbol.upper()}` introuvable.")
        color = 0x00b894 if data.get("changePercent", 0) >= 0 else 0xff7675
        embed = discord.Embed(
            title=f"{get_emoji(data.get('changePercent',0))} {data['symbol']} — {data.get('name', symbol)}",
            description="*Information personnelle.*",
            color=color,
        )
        embed.add_field(name="💲 Prix",          value=f"**{format_price(data['price'])}** {data.get('currency','')}", inline=True)
        embed.add_field(name="📊 Variation",     value=f"**{format_change(data.get('changePercent',0))}%**",           inline=True)
        embed.add_field(name="📦 Volume",        value=f"{data.get('volume',0):,}",                                    inline=True)
        embed.add_field(name="⬆️ Haut du jour", value=format_price(data.get("dayHigh")),  inline=True)
        embed.add_field(name="⬇️ Bas du jour",  value=format_price(data.get("dayLow")),   inline=True)
        embed.add_field(name="📈 Haut 52s",      value=format_price(data.get("high52w")),  inline=True)
        embed.add_field(name="📉 Bas 52s",       value=format_price(data.get("low52w")),   inline=True)
        if data.get("marketCap"):
            embed.add_field(name="🏦 Capitalisation", value=f"{data['marketCap']/1e9:.2f}B", inline=True)
        embed.add_field(name="🕐 État", value=market_state_label(data.get("marketState","?")), inline=True)
        embed.set_footer(text="Iris Trading · Yahoo Finance")
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)

    @bot_trading.command(name="portfolio")
    async def cmd_portfolio(ctx, sub: str = "view", *args):
        uid = ctx.author.id
        sub = sub.lower()
        if sub == "add" and len(args) >= 2:
            try:
                qty   = float(args[1])
                price = float(args[2]) if len(args) >= 3 else None
            except ValueError:
                return await ctx.send("❌ Quantité ou prix invalide.")
            usr.add_position(uid, args[0].upper(), qty, price)
            return await ctx.send(f"✅ **{qty}x {args[0].upper()}**" + (f" @ {price}" if price else "") + " ajouté.")
        if sub == "remove" and args:
            usr.remove_position(uid, args[0].upper())
            return await ctx.send(f"🗑️ **{args[0].upper()}** retiré.")
        settings  = usr.get(uid)
        portfolio = settings.get("portfolio", [])
        if not portfolio:
            return await ctx.send("📭 Vide. `!iris portfolio add SYMBOLE QTE PRIX`")
        async with ctx.typing():
            quotes    = await mkt.get_multiple([p["symbol"] for p in portfolio])
            quote_map = {q["symbol"]: q for q in quotes}
        positions = []
        for pos in portfolio:
            data = quote_map.get(pos["symbol"])
            if not data: continue
            cv      = data["price"] * pos["qty"]
            bv      = (pos.get("buy_price") or data["price"]) * pos["qty"]
            pnl     = cv - bv
            pnl_pct = (pnl / bv * 100) if bv else 0
            positions.append({**pos, "price": data["price"], "cv": cv, "pnl": pnl, "pnl_pct": pnl_pct})
        total_val = sum(p["cv"] for p in positions)
        total_pnl = sum(p["pnl"] for p in positions)
        embed = discord.Embed(
            title="💼 Ton Portfolio",
            description="*Privé — personne d'autre ne le voit.*",
            color=0x00b894 if total_pnl >= 0 else 0xff7675,
        )
        for p in positions:
            sign = "+" if p["pnl_pct"] >= 0 else ""
            embed.add_field(
                name=f"{get_emoji(p['pnl_pct'])} {p['symbol']}",
                value=(f"{p['qty']} × {format_price(p['price'])}\n"
                       f"Valeur : **{format_price(p['cv'])}**\n"
                       f"P&L : **{format_change(p['pnl'])}** ({sign}{p['pnl_pct']:.2f}%)"),
                inline=True,
            )
        embed.add_field(name="━━━━━━━━━━", value="\u200b", inline=False)
        embed.add_field(name="💰 Total",   value=f"**{format_price(total_val)}**",  inline=True)
        embed.add_field(name="📊 P&L",     value=f"**{format_change(total_pnl)}**", inline=True)
        embed.set_footer(text="Iris Trading · Données temps réel")
        embed.timestamp = discord.utils.utcnow()
        await ctx.send(embed=embed)

    @bot_trading.command(name="alert")
    async def cmd_alert(ctx, symbol: str = None, threshold: str = None):
        if not symbol or not threshold:
            return await ctx.send("Usage : `!iris alert SYMBOLE SEUIL`")
        try: t = float(threshold)
        except ValueError: return await ctx.send("❌ Seuil invalide.")
        usr.add_custom_alert(ctx.author.id, symbol.upper(), t)
        await ctx.send(
            f"🔔 Alerte : DM **uniquement à toi** si **{symbol.upper()}** bouge de **{t}%**.\n"
            f"_Cooldown 5 min._"
        )

    @bot_trading.command(name="conseil")
    async def cmd_conseil(ctx, *args):
        uid     = ctx.author.id
        symbols = [a.upper() for a in args] if args else usr.get(uid).get("watchlist", [])
        if not symbols:
            return await ctx.send("❓ Précise un symbole ou ajoute des actifs à ta watchlist.")
        async with ctx.typing():
            reply = await get_ai_advice(uid, symbols)
        embed = discord.Embed(
            title="🤖 Conseil Iris IA — Personnel",
            description=reply,
            color=0x6C5CE7,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Iris Trading · Pollinations.ai · Pas des conseils financiers pro")
        await ctx.send(embed=embed)

    @bot_trading.command(name="reset")
    async def cmd_reset(ctx):
        usr.reset(ctx.author.id)
        await ctx.send("🔄 Settings réinitialisés.")
