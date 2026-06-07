"""
bot_securite.py — Bot Iris Sécurité
Gestion du serveur, arrivées membres, modération, logs, anti-raid, et soutien psychologique.
Rattaché au bot principal via setup_securite(bot) dans main.py
"""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
import discord
from discord.ext import commands, tasks
# Au tout début de bot_securite.py (après tes imports) :
intents = discord.Intents.all()
bot_securite = commands.Bot(command_prefix="!sec ", intents=intents, help_command=None)
logger   = logging.getLogger("BotSecurite")
CFG_PATH = Path(__file__).parent / "data" / "securite.json"

# --- REGEX DE DÉTECTION (Suicide & Meurtre) ---
KEYWORDS_DETRESSE = [
    r"suicide", r"envie de mourir", r"me tuer", r"finir mes jours", 
    r"automutilation", r"me couper", r"plus envie de vivre", r"tout arreter",
    r"meurtre", r"tuer quelqu", r"envie de tuer", r"assassiner"
]

def _load_cfg() -> dict:
    try:
        if CFG_PATH.exists():
            return json.loads(CFG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Erreur chargement securite.json: {e}")
    return {}

def _save_cfg(data: dict):
    try:
        CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CFG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Erreur sauvegarde securite.json: {e}")

server_cfg: dict = _load_cfg()
recent_joins: dict = {}

def get_guild_cfg(guild_id: int) -> dict:
    key = str(guild_id)
    if key not in server_cfg:
        server_cfg[key] = {
            "welcome_channel":  None,
            "log_channel":      None,
            "rules_channel":    None,
            "welcome_msg":      None,
            "autorole":         None,
            "antiraid_enabled": False,
            "antiraid_joins":   5,
            "antiraid_seconds": 10,
            "banned_words":     [],
            "mute_role":        None,
        }
        _save_cfg(server_cfg)
    return server_cfg[str(guild_id)]

def save_guild_cfg(guild_id: int):
    _save_cfg(server_cfg)

# ── CORRECTION : Décorateur défini globalement pour être accessible ───────────────
def admin_only():
    """Vérifie que l'auteur est administrateur du serveur."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.guild_permissions.administrator:
            return True
        await ctx.send("❌ Tu dois être **administrateur** pour utiliser cette commande.")
        return False
    return commands.check(predicate)

async def send_log(guild: discord.Guild, embed: discord.Embed):
    cfg = get_guild_cfg(guild.id)
    cid = cfg.get("log_channel")
    if not cid:
        return
    channel = guild.get_channel(cid)
    if channel:
        try:
            await channel.send(embed=embed)
        except Exception:
            pass


def setup_securite(bot: commands.Bot):
    """
    Injecte toutes les commandes et événements de sécurité dans le bot de main.py
    """

    # ── Événements (Events) ────────────────────────────────────────────
    @bot.event
    async def on_ready():
        logger.info(f"🛡️ Module Iris Sécurité rattaché avec succès.")
        if not cleanup_joins_loop.is_running():
            cleanup_joins_loop.start()

    @bot.event
    async def on_member_join(member: discord.Member):
        guild = member.guild
        cfg   = get_guild_cfg(guild.id)
        now   = datetime.now(timezone.utc)

        # Anti-raid
        if cfg.get("antiraid_enabled"):
            gid    = guild.id
            window = cfg.get("antiraid_seconds", 10)
            max_j  = cfg.get("antiraid_joins", 5)
            joins  = recent_joins.setdefault(gid, [])
            joins.append(now.timestamp())
            recent_joins[gid] = [t for t in joins if now.timestamp() - t < window]
            if len(recent_joins[gid]) >= max_j:
                await send_log(guild, discord.Embed(
                    title="⚠️ ALERTE ANTI-RAID",
                    description=(
                        f"**{len(recent_joins[gid])} arrivées en {window}s !**\n"
                        f"Dernier : {member.mention} (`{member}`)\n"
                        f"Vérifiez le serveur immédiatement !"
                    ),
                    color=0xFF0000, timestamp=now,
                ))

        # Message de bienvenue
        wc_id = cfg.get("welcome_channel")
        if wc_id:
            channel = guild.get_channel(wc_id)
            if channel:
                rules_mention = f"<#{cfg['rules_channel']}>" if cfg.get("rules_channel") else "les règles"
                custom_msg    = cfg.get("welcome_msg")
                if custom_msg:
                    text = (custom_msg
                            .replace("{user}", member.mention)
                            .replace("{username}", str(member))
                            .replace("{server}", guild.name)
                            .replace("{membercount}", str(guild.member_count)))
                    await channel.send(text)
                else:
                    embed = discord.Embed(
                        title=f"👋 Bienvenue sur {guild.name} !",
                        description=(
                            f"Salut {member.mention}, on est content de t'avoir ici ! 🎉\n\n"
                            f"📜 Pense à lire {rules_mention} avant de commencement.\n"
                            f"Tu es le **{guild.member_count}ème** membre !"
                        ),
                        color=0x00b894, timestamp=now,
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text=f"Iris Sécurité · {guild.name}")
                    await channel.send(embed=embed)

        # Auto-rôle
        ar_id = cfg.get("autorole")
        if ar_id:
            role = guild.get_role(ar_id)
            if role:
                try:
                    await member.add_roles(role, reason="Iris Sécurité — autorole")
                except discord.Forbidden:
                    pass

        # Log arrivée
        log_e = discord.Embed(
            title="✅ Nouveau membre",
            description=f"{member.mention} (`{member}`) a rejoint.",
            color=0x00b894, timestamp=now,
        )
        log_e.set_thumbnail(url=member.display_avatar.url)
        log_e.add_field(name="ID",           value=str(member.id),                     inline=True)
        log_e.add_field(name="Compte créé",  value=member.created_at.strftime("%d/%m/%Y"),     inline=True)
        log_e.set_footer(text="Iris Sécurité · Log arrivée")
        await send_log(guild, log_e)

    @bot.event
    async def on_member_remove(member: discord.Member):
        embed = discord.Embed(
            title="👋 Membre parti",
            description=f"**{member}** a quitté.",
            color=0xff7675, timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID",    value=str(member.id), inline=True)
        embed.add_field(name="Rôles", value=", ".join(r.mention for r in member.roles[1:]) or "Aucun", inline=False)
        embed.set_footer(text="Iris Sécurité · Log départ")
        await send_log(member.guild, embed)

    @bot.event
    async def on_message_delete(message: discord.Message):
        if message.author.bot or not message.guild:
            return
        embed = discord.Embed(
            title="🗑️ Message supprimé",
            description=f"**Auteur :** {message.author.mention} · **Salon :** {message.channel.mention}",
            color=0xFDCB6E, timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Contenu", value=(message.content or "_vide_")[:1000], inline=False)
        embed.set_footer(text="Iris Sécurité · Log suppression")
        await send_log(message.guild, embed)

    @bot.event
    async def on_message_edit(before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        embed = discord.Embed(
            title="✏️ Message modifié",
            description=f"**Auteur :** {before.author.mention} · **Salon :** {before.channel.mention}",
            color=0x74B9FF, timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Avant", value=(before.content or "_vide_")[:500], inline=False)
        embed.add_field(name="Après", value=(after.content  or "_vide_")[:500], inline=False)
        embed.set_footer(text="Iris Sécurité · Log modification")
        await send_log(before.guild, embed)

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return

        # 1. AJOUT : Détection Suicide & Meurtre (Envoi d'un GIF de réconfort)
        content_lower = message.content.lower()
        is_detresse = any(re.search(pattern, content_lower) for pattern in KEYWORDS_DETRESSE)
        
        if is_detresse and message.guild:
            gif_url = "https://media.discordapp.net/attachments/936319431615856670/952366836131975208/C8BC6C5F-41DA-4AF6-9808-721753CE760B.gif?ex=6a26b97b&is=6a2567fb&hm=e2b013d54618dec77517fd04a0e4fb04865826117bd9f960031012a3a3bb5506&"
            
            embed_care = discord.Embed(
                title="💜 Iris : Je suis là pour toi",
                description=(
                    f"{message.author.mention}, j'ai détecté des mots qui signalent que tu traverses un moment très difficile ou violent.\n"
                    "Sache que tu n'es pas seul(e) et qu'il existe des personnes prêtes à t'écouter sans aucun jugement.\n\n"
                    "📞 **Services d'aide gratuits et anonymes :**\n"
                    "• **Suicide Écoute** : 3114 (24h/24)\n"
                    "• **SOS Amitié** : 09 72 39 40 50\n"
                    "• **Fil Santé Jeunes** : 3224\n\n"
                    "*Si un danger est immédiat, compose le 15, 17 ou 112.*"
                ),
                color=0xff7675
            )
            embed_care.set_image(url=gif_url)
            await message.channel.send(embed=embed_care)
            logger.warning(f"🚨 Alerte détresse/meurtre par {message.author.name} dans #{message.channel.name}")
            return  # On bloque le message pour ne pas appliquer de punition ou d'autres commandes

        # 2. Modération des Badwords classiques
        if message.guild:
            cfg = get_guild_cfg(message.guild.id)
            for word in cfg.get("banned_words", []):
                if word.lower() in content_lower:
                    try:
                        await message.delete()
                        await message.channel.send(
                            f"⚠️ {message.author.mention}, ton message a été supprimé (mot interdit).",
                            delete_after=5,
                        )
                        await send_log(message.guild, discord.Embed(
                            title="🚫 Mot interdit",
                            description=f"**Auteur :** {message.author.mention} · **Mot :** `{word}`",
                            color=0xFF0000, timestamp=datetime.now(timezone.utc),
                        ))
                    except discord.Forbidden:
                        pass
                    return

        # Très important pour que les commandes fonctionnent dans main.py
        await bot.process_commands(message)

    @bot.event
    async def on_member_ban(guild: discord.Guild, user: discord.User):
        await send_log(guild, discord.Embed(
            title="🔨 Membre banni",
            description=f"**{user}** (`{user.id}`) banni.",
            color=0xFF0000, timestamp=datetime.now(timezone.utc),
        ))

    @bot.event
    async def on_member_unban(guild: discord.Guild, user: discord.User):
        await send_log(guild, discord.Embed(
            title="✅ Membre débanni",
            description=f"**{user}** (`{user.id}`) débanni.",
            color=0x00b894, timestamp=datetime.now(timezone.utc),
        ))

    @tasks.loop(seconds=30)
    async def cleanup_joins_loop():
        now = datetime.now(timezone.utc).timestamp()
        for gid in list(recent_joins.keys()):
            recent_joins[gid] = [t for t in recent_joins[gid] if now - t < 60]

    # ── Commandes (Rattachées à l'instance globale `bot`) ─────────────────
    @bot.command(name="sec_help")
    async def sec_help(ctx):
        embed = discord.Embed(title="🛡️ Iris Sécurité — Aide", color=0x6C5CE7)
        embed.add_field(name="`!sec setup welcome`", value="Ce salon = bienvenue", inline=True)
        embed.add_field(name="`!sec setup logs`", value="Ce salon = logs", inline=True)
        embed.add_field(name="`!sec clear N`", value="Supprimer N messages", inline=True)
        embed.add_field(name="`!sec status`", value="Voir la config", inline=True)
        await ctx.send(embed=embed)

    @bot.command(name="setup")
    @admin_only()
    async def sec_setup(ctx, target: str = None, *args):
        if not target:
            return await ctx.send("Usage : `!sec setup welcome|logs|rules|autorole`")
        cfg = get_guild_cfg(ctx.guild.id)
        t   = target.lower()
        if t == "welcome":
            cfg["welcome_channel"] = ctx.channel.id
            save_guild_cfg(ctx.guild.id)
            await ctx.send(f"✅ Salon de bienvenue → {ctx.channel.mention}")
        elif t == "logs":
            cfg["log_channel"] = ctx.channel.id
            save_guild_cfg(ctx.guild.id)
            await ctx.send(f"✅ Salon de logs → {ctx.channel.mention}")
        elif t == "rules":
            cfg["rules_channel"] = ctx.channel.id
            save_guild_cfg(ctx.guild.id)
            await ctx.send(f"✅ Salon des règles → {ctx.channel.mention}")
        elif t == "autorole":
            if not ctx.message.role_mentions:
                return await ctx.send("Usage : `!sec setup autorole @NomDuRole`")
            role              = ctx.message.role_mentions[0]
            cfg["autorole"]   = role.id
            save_guild_cfg(ctx.guild.id)
            await ctx.send(f"✅ Auto-rôle → {role.mention}")
        else:
            await ctx.send("❓ Cible inconnue.")

    @bot.command(name="welcome")
    @admin_only()
    async def sec_welcome(ctx, sub: str = None, *, texte: str = None):
        cfg = get_guild_cfg(ctx.guild.id)
        if not sub: return
        sub = sub.lower()
        if sub == "msg" and texte:
            cfg["welcome_msg"] = texte
            save_guild_cfg(ctx.guild.id)
            await ctx.send("✅ Message mis à jour.")
        elif sub == "test":
            cid = cfg.get("welcome_channel")
            if not cid: return
            channel = ctx.guild.get_channel(cid)
            await channel.send(f"[TEST] Bienvenue {ctx.author.mention}")

    @bot.command(name="ban")
    @admin_only()
    async def sec_ban(ctx, member: discord.Member = None, *, reason: str = "Aucune raison"):
        if not member: return
        await member.ban(reason=reason)
        await ctx.send(f"🔨 **{member}** a été banni.")

    @bot.command(name="kick")
    @admin_only()
    async def sec_kick(ctx, member: discord.Member = None, *, reason: str = "Aucune raison"):
        if not member: return
        await member.kick(reason=reason)
        await ctx.send(f"👢 **{member}** a été expulsé.")

    @bot.command(name="mute")
    @admin_only()
    async def sec_mute(ctx, member: discord.Member = None, *, reason: str = "Aucune raison"):
        if not member: return
        cfg  = get_guild_cfg(ctx.guild.id)
        role = ctx.guild.get_role(cfg.get("mute_role"))
        if not role:
            role = await ctx.guild.create_role(name="Muted")
            cfg["mute_role"] = role.id
            save_guild_cfg(ctx.guild.id)
        await member.add_roles(role)
        await ctx.send(f"🔇 **{member}** est muté.")

    @bot.command(name="unmute")
    @admin_only()
    async def sec_unmute(ctx, member: discord.Member = None):
        if not member: return
        cfg  = get_guild_cfg(ctx.guild.id)
        role = ctx.guild.get_role(cfg.get("mute_role"))
        if role:
            await member.remove_roles(role)
            await ctx.send(f"✅ **{member}** démuté.")

    @bot.command(name="clear")
    @admin_only()
    async def sec_clear(ctx, n: int = 5):
        deleted = await ctx.channel.purge(limit=n + 1)
        await ctx.send(f"🗑️ **{len(deleted) - 1}** messages supprimés.", delete_after=4)

    @bot.command(name="warn")
    @admin_only()
    async def sec_warn(ctx, member: discord.Member = None, *, reason: str = "Inapproprié"):
        if not member: return
        try: await member.send(f"⚠️ Warn sur {ctx.guild.name} : {reason}")
        except: pass
        await ctx.send(f"⚠️ **{member}** a reçu un avertissement.")

    @bot.command(name="antiraid")
    @admin_only()
    async def sec_antiraid(ctx, sub: str = None, *args):
        cfg = get_guild_cfg(ctx.guild.id)
        if not sub: return
        if sub.lower() == "on":
            cfg["antiraid_enabled"] = True
            save_guild_cfg(ctx.guild.id)
            await ctx.send("🔒 Anti-raid activé.")
        elif sub.lower() == "off":
            cfg["antiraid_enabled"] = False
            save_guild_cfg(ctx.guild.id)
            await ctx.send("🔓 Anti-raid désactivé.")

    @bot.command(name="badword")
    @admin_only()
    async def sec_badword(ctx, sub: str = "list", *, word: str = None):
        cfg = get_guild_cfg(ctx.guild.id)
        if sub.lower() == "add" and word:
            cfg["banned_words"].append(word.lower())
            save_guild_cfg(ctx.guild.id)
            await ctx.send(f"🚫 `{word}` ajouté aux mots interdits.")
        elif sub.lower() == "list":
            await ctx.send(f"Mots interdits : {', '.join(cfg['banned_words'])}")

    @bot.command(name="status")
    async def sec_status(ctx):
        cfg = get_guild_cfg(ctx.guild.id)
        embed = discord.Embed(title=f"🛡️ Config — {ctx.guild.name}", color=0x6C5CE7)
        embed.add_field(name="Anti-raid", value="✅" if cfg["antiraid_enabled"] else "❌")
        embed.add_field(name="Mots interdits", value=f"{len(cfg['banned_words'])}")
        await ctx.send(embed=embed)
