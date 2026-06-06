"""
bots/bot_securite.py
Bot Iris Sécurité — Gestion du serveur, arrivées membres, modération, logs.
Préfixe : !sec
"""
import os
import asyncio
import json
import logging
from datetime    import datetime, timezone
from pathlib     import Path
import discord
from discord.ext import commands, tasks

logger = logging.getLogger("BotSecurite")

# ── Persistence config par serveur ───────────────────────
CFG_PATH = Path(__file__).parent.parent / "data" / "securite.json"

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

server_cfg: dict = _load_cfg()   # { guild_id: { welcome_channel, log_channel, rules_channel, ... } }

def get_guild_cfg(guild_id: int) -> dict:
    key = str(guild_id)
    if key not in server_cfg:
        server_cfg[key] = {
            "welcome_channel":  None,   # salon d'arrivée
            "log_channel":      None,   # salon de logs modération
            "rules_channel":    None,   # salon des règles
            "welcome_msg":      None,   # message perso (None = message par défaut)
            "autorole":         None,   # rôle auto à l'arrivée
            "antiraid_enabled": False,  # anti-raid
            "antiraid_joins":   5,      # nb de joins rapides déclenchant l'alerte
            "antiraid_seconds": 10,     # fenêtre de temps en secondes
            "banned_words":     [],     # mots interdits
            "mute_role":        None,   # rôle mute
        }
        _save_cfg(server_cfg)
    return server_cfg[str(guild_id)]

def save_guild_cfg(guild_id: int):
    _save_cfg(server_cfg)

# ── Anti-raid : tracker les joins rapides ─────────────────
recent_joins: dict = {}  # guild_id -> [timestamp, ...]

# ── Bot ───────────────────────────────────────────────────
intents               = discord.Intents.all()
bot_securite          = commands.Bot(command_prefix="!sec ", intents=intents, help_command=None)
_mod_log_queue: list  = []


async def send_log(guild: discord.Guild, embed: discord.Embed):
    """Envoie un log dans le salon configuré."""
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


def setup_securite():

    # ══════════════════════════════════════════════════════
    # EVENTS
    # ══════════════════════════════════════════════════════

    @bot_securite.event
    async def on_ready():
        logger.info(f"🛡️ Iris Sécurité connectée : {bot_securite.user}")
        await bot_securite.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="le serveur 🛡️")
        )
        cleanup_joins_loop.start()

    # ── Arrivée d'un membre ───────────────────────────────
    @bot_securite.event
    async def on_member_join(member: discord.Member):
        guild = member.guild
        cfg   = get_guild_cfg(guild.id)
        now   = datetime.now(timezone.utc)

        # ── Anti-raid ──────────────────────────────────────
        if cfg.get("antiraid_enabled"):
            gid      = guild.id
            window   = cfg.get("antiraid_seconds", 10)
            max_join = cfg.get("antiraid_joins", 5)

            joins = recent_joins.setdefault(gid, [])
            joins.append(now.timestamp())
            # Ne garde que les joins dans la fenêtre
            recent_joins[gid] = [t for t in joins if now.timestamp() - t < window]

            if len(recent_joins[gid]) >= max_join:
                log_embed = discord.Embed(
                    title="⚠️ ALERTE ANTI-RAID",
                    description=(
                        f"**{len(recent_joins[gid])} arrivées en {window}s !**\n"
                        f"Dernier membre : {member.mention} (`{member}`)\n\n"
                        f"Vérifiez le serveur immédiatement."
                    ),
                    color=0xFF0000,
                    timestamp=now,
                )
                await send_log(guild, log_embed)

        # ── Message de bienvenue ───────────────────────────
        welcome_cid = cfg.get("welcome_channel")
        if welcome_cid:
            channel = guild.get_channel(welcome_cid)
            if channel:
                custom_msg = cfg.get("welcome_msg")
                rules_cid  = cfg.get("rules_channel")
                rules_mention = f"<#{rules_cid}>" if rules_cid else "les règles du serveur"

                if custom_msg:
                    # Remplacement des variables dans le message perso
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
                            f"📜 Pense à lire {rules_mention} avant de commencer.\n"
                            f"Tu es le **{guild.member_count}ème** membre du serveur !"
                        ),
                        color=0x00b894,
                        timestamp=now,
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text=f"Iris Sécurité · {guild.name}")
                    await channel.send(embed=embed)

        # ── Auto-rôle ─────────────────────────────────────
        autorole_id = cfg.get("autorole")
        if autorole_id:
            role = guild.get_role(autorole_id)
            if role:
                try:
                    await member.add_roles(role, reason="Iris Sécurité — autorole")
                except discord.Forbidden:
                    pass

        # ── Log arrivée ───────────────────────────────────
        log_embed = discord.Embed(
            title="✅ Nouveau membre",
            description=f"{member.mention} (`{member}`) a rejoint le serveur.",
            color=0x00b894,
            timestamp=now,
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.add_field(name="ID", value=str(member.id), inline=True)
        log_embed.add_field(name="Compte créé", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
        log_embed.set_footer(text="Iris Sécurité · Log arrivée")
        await send_log(guild, log_embed)

    # ── Départ d'un membre ────────────────────────────────
    @bot_securite.event
    async def on_member_remove(member: discord.Member):
        guild = member.guild
        now   = datetime.now(timezone.utc)
        embed = discord.Embed(
            title="👋 Membre parti",
            description=f"**{member}** a quitté le serveur.",
            color=0xff7675,
            timestamp=now,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(
            name="Rôles",
            value=", ".join(r.mention for r in member.roles[1:]) or "Aucun",
            inline=False,
        )
        embed.set_footer(text="Iris Sécurité · Log départ")
        await send_log(guild, embed)

    # ── Suppression de message ────────────────────────────
    @bot_securite.event
    async def on_message_delete(message: discord.Message):
        if message.author.bot or not message.guild:
            return
        embed = discord.Embed(
            title="🗑️ Message supprimé",
            description=f"**Auteur :** {message.author.mention}\n**Salon :** {message.channel.mention}",
            color=0xFDCB6E,
            timestamp=datetime.now(timezone.utc),
        )
        content = message.content or "_[Pas de texte]_"
        embed.add_field(name="Contenu", value=content[:1000], inline=False)
        embed.set_footer(text="Iris Sécurité · Log suppression")
        await send_log(message.guild, embed)

    # ── Modification de message ───────────────────────────
    @bot_securite.event
    async def on_message_edit(before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return
        if before.content == after.content:
            return
        embed = discord.Embed(
            title="✏️ Message modifié",
            description=f"**Auteur :** {before.author.mention}\n**Salon :** {before.channel.mention}",
            color=0x74B9FF,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Avant", value=before.content[:500] or "_vide_", inline=False)
        embed.add_field(name="Après", value=after.content[:500] or "_vide_", inline=False)
        embed.set_footer(text="Iris Sécurité · Log modification")
        await send_log(before.guild, embed)

    # ── Détection mots interdits ──────────────────────────
    @bot_securite.event
    async def on_message(message: discord.Message):
        if message.author.bot or not message.guild:
            await bot_securite.process_commands(message)
            return
        cfg          = get_guild_cfg(message.guild.id)
        banned_words = cfg.get("banned_words", [])
        content_low  = message.content.lower()
        for word in banned_words:
            if word.lower() in content_low:
                try:
                    await message.delete()
                    await message.channel.send(
                        f"⚠️ {message.author.mention}, ce message contient un mot interdit et a été supprimé.",
                        delete_after=5,
                    )
                    log_embed = discord.Embed(
                        title="🚫 Mot interdit détecté",
                        description=(
                            f"**Auteur :** {message.author.mention}\n"
                            f"**Salon :** {message.channel.mention}\n"
                            f"**Mot :** `{word}`"
                        ),
                        color=0xFF0000,
                        timestamp=datetime.now(timezone.utc),
                    )
                    await send_log(message.guild, log_embed)
                except discord.Forbidden:
                    pass
                break
        await bot_securite.process_commands(message)

    # ── Ban ───────────────────────────────────────────────
    @bot_securite.event
    async def on_member_ban(guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="🔨 Membre banni",
            description=f"**{user}** (`{user.id}`) a été banni.",
            color=0xFF0000,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Iris Sécurité · Log ban")
        await send_log(guild, embed)

    # ── Unban ─────────────────────────────────────────────
    @bot_securite.event
    async def on_member_unban(guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="✅ Membre débanni",
            description=f"**{user}** (`{user.id}`) a été débanni.",
            color=0x00b894,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Iris Sécurité · Log unban")
        await send_log(guild, embed)

    # ── Nettoyage joins anciens (anti-raid) ───────────────
    @tasks.loop(seconds=30)
    async def cleanup_joins_loop():
        now = datetime.now(timezone.utc).timestamp()
        for gid in list(recent_joins.keys()):
            recent_joins[gid] = [t for t in recent_joins[gid] if now - t < 60]

    # ══════════════════════════════════════════════════════
    # COMMANDES
    # ══════════════════════════════════════════════════════

    def requires_admin():
        """Décorateur — vérifie que l'auteur est admin."""
        async def predicate(ctx):
            if ctx.author.guild_permissions.administrator:
                return True
            await ctx.send("❌ Tu dois être **administrateur** pour utiliser cette commande.")
            return False
        return commands.check(predicate)

    @bot_securite.command(name="help")
    async def sec_help(ctx):
        embed = discord.Embed(
            title="🛡️ Iris Sécurité — Aide",
            description="Gestion complète de la sécurité et des arrivées membres.",
            color=0x6C5CE7,
        )
        embed.add_field(name="─── ⚙️ CONFIG (admin) ───", value="\u200b", inline=False)
        embed.add_field(name="`!sec setup welcome`",     value="Définir ce canal comme salon de bienvenue",  inline=False)
        embed.add_field(name="`!sec setup logs`",        value="Définir ce canal comme salon de logs",       inline=False)
        embed.add_field(name="`!sec setup rules`",       value="Définir ce canal comme salon des règles",    inline=False)
        embed.add_field(name="`!sec setup autorole @R`", value="Rôle automatique à l'arrivée",               inline=False)
        embed.add_field(name="`!sec welcome msg TEXTE`", value="Message de bienvenue perso (`{user}` `{server}` `{membercount}`)", inline=False)
        embed.add_field(name="`!sec welcome reset`",     value="Remettre le message par défaut",             inline=False)
        embed.add_field(name="─── 🚨 MODÉRATION (admin) ───", value="\u200b", inline=False)
        embed.add_field(name="`!sec ban @user [raison]`",    value="Bannir un membre",              inline=False)
        embed.add_field(name="`!sec kick @user [raison]`",   value="Expulser un membre",            inline=False)
        embed.add_field(name="`!sec mute @user [raison]`",   value="Mute un membre",                inline=False)
        embed.add_field(name="`!sec unmute @user`",          value="Unmute un membre",              inline=False)
        embed.add_field(name="`!sec clear N`",               value="Supprimer N messages",          inline=False)
        embed.add_field(name="`!sec warn @user RAISON`",     value="Avertir un membre",             inline=False)
        embed.add_field(name="─── 🔒 ANTI-RAID (admin) ───", value="\u200b", inline=False)
        embed.add_field(name="`!sec antiraid on/off`",       value="Activer/désactiver l'anti-raid", inline=False)
        embed.add_field(name="`!sec antiraid config N T`",   value="N joins en T secondes = alerte", inline=False)
        embed.add_field(name="─── 🚫 MOTS INTERDITS (admin) ───", value="\u200b", inline=False)
        embed.add_field(name="`!sec badword add MOT`",       value="Ajouter un mot interdit",       inline=False)
        embed.add_field(name="`!sec badword remove MOT`",    value="Retirer un mot interdit",       inline=False)
        embed.add_field(name="`!sec badword list`",          value="Voir les mots interdits",       inline=False)
        embed.add_field(name="─── 📊 INFO ───", value="\u200b", inline=False)
        embed.add_field(name="`!sec status`",                value="Voir la config du serveur",     inline=False)
        embed.add_field(name="`!sec userinfo @user`",        value="Infos sur un membre",           inline=False)
        embed.set_footer(text="Iris Sécurité · Gestion serveur Discord")
        await ctx.send(embed=embed)

    # ── Setup ──────────────────────────────────────────────
    @bot_securite.command(name="setup")
    @requires_admin()
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
                return await ctx.send("Usage : `!sec setup autorole @RoleName`")
            role = ctx.message.role_mentions[0]
            cfg["autorole"] = role.id
            save_guild_cfg(ctx.guild.id)
            await ctx.send(f"✅ Auto-rôle → {role.mention}")

        else:
            await ctx.send("❓ Cible inconnue. Utilise : `welcome` · `logs` · `rules` · `autorole`")

    # ── Message de bienvenue perso ────────────────────────
    @bot_securite.command(name="welcome")
    @requires_admin()
    async def sec_welcome(ctx, sub: str = None, *, texte: str = None):
        cfg = get_guild_cfg(ctx.guild.id)
        if not sub:
            return await ctx.send("Usage : `!sec welcome msg TEXTE` · `!sec welcome reset` · `!sec welcome test`")
        sub = sub.lower()
        if sub == "msg" and texte:
            cfg["welcome_msg"] = texte
            save_guild_cfg(ctx.guild.id)
            await ctx.send(f"✅ Message de bienvenue personnalisé !\nVariables : `{{user}}` `{{username}}` `{{server}}` `{{membercount}}`")
        elif sub == "reset":
            cfg["welcome_msg"] = None
            save_guild_cfg(ctx.guild.id)
            await ctx.send("✅ Message de bienvenue remis par défaut.")
        elif sub == "test":
            # Simule l'arrivée de l'auteur
            await _send_welcome_test(ctx)
        else:
            await ctx.send("Usage : `!sec welcome msg TEXTE` · `reset` · `test`")

    async def _send_welcome_test(ctx):
        cfg   = get_guild_cfg(ctx.guild.id)
        cid   = cfg.get("welcome_channel")
        if not cid:
            return await ctx.send("❌ Aucun salon de bienvenue configuré. Tape `!sec setup welcome` ici.")
        channel   = ctx.guild.get_channel(cid)
        member    = ctx.author
        rules_cid = cfg.get("rules_channel")
        rules_mention = f"<#{rules_cid}>" if rules_cid else "les règles"
        custom_msg    = cfg.get("welcome_msg")
        if custom_msg:
            text = (custom_msg
                    .replace("{user}", member.mention)
                    .replace("{username}", str(member))
                    .replace("{server}", ctx.guild.name)
                    .replace("{membercount}", str(ctx.guild.member_count)))
            await channel.send(f"[TEST] {text}")
        else:
            embed = discord.Embed(
                title=f"👋 [TEST] Bienvenue sur {ctx.guild.name} !",
                description=(
                    f"Salut {member.mention}, on est content de t'avoir ici ! 🎉\n\n"
                    f"📜 Pense à lire {rules_mention}.\n"
                    f"Tu es le **{ctx.guild.member_count}ème** membre !"
                ),
                color=0x00b894,
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)
        await ctx.send(f"✅ Test envoyé dans {channel.mention} !")

    # ── Modération ────────────────────────────────────────
    @bot_securite.command(name="ban")
    @requires_admin()
    async def sec_ban(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
        if not member:
            return await ctx.send("Usage : `!sec ban @user [raison]`")
        try:
            await member.ban(reason=f"[Iris Sécurité] {reason}")
            embed = discord.Embed(
                title="🔨 Membre banni",
                description=f"**{member}** a été banni.\n**Raison :** {reason}",
                color=0xFF0000, timestamp=datetime.now(timezone.utc),
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Je n'ai pas la permission de bannir ce membre.")

    @bot_securite.command(name="kick")
    @requires_admin()
    async def sec_kick(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
        if not member:
            return await ctx.send("Usage : `!sec kick @user [raison]`")
        try:
            await member.kick(reason=f"[Iris Sécurité] {reason}")
            embed = discord.Embed(
                title="👢 Membre expulsé",
                description=f"**{member}** a été expulsé.\n**Raison :** {reason}",
                color=0xFDCB6E, timestamp=datetime.now(timezone.utc),
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Je n'ai pas la permission d'expulser ce membre.")

    @bot_securite.command(name="mute")
    @requires_admin()
    async def sec_mute(ctx, member: discord.Member = None, *, reason: str = "Aucune raison"):
        if not member:
            return await ctx.send("Usage : `!sec mute @user [raison]`")
        cfg    = get_guild_cfg(ctx.guild.id)
        rid    = cfg.get("mute_role")
        role   = ctx.guild.get_role(rid) if rid else None
        # Création automatique du rôle mute si absent
        if not role:
            try:
                role = await ctx.guild.create_role(name="Muted", reason="Iris Sécurité — rôle mute")
                for channel in ctx.guild.channels:
                    await channel.set_permissions(role, send_messages=False, speak=False)
                cfg["mute_role"] = role.id
                save_guild_cfg(ctx.guild.id)
            except discord.Forbidden:
                return await ctx.send("❌ Je n'ai pas la permission de créer un rôle mute.")
        try:
            await member.add_roles(role, reason=f"[Iris Sécurité] {reason}")
            embed = discord.Embed(
                title="🔇 Membre muté",
                description=f"**{member}** a été muté.\n**Raison :** {reason}",
                color=0xA29BFE, timestamp=datetime.now(timezone.utc),
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Permission refusée.")

    @bot_securite.command(name="unmute")
    @requires_admin()
    async def sec_unmute(ctx, member: discord.Member = None):
        if not member:
            return await ctx.send("Usage : `!sec unmute @user`")
        cfg  = get_guild_cfg(ctx.guild.id)
        rid  = cfg.get("mute_role")
        role = ctx.guild.get_role(rid) if rid else None
        if not role:
            return await ctx.send("❌ Aucun rôle mute configuré.")
        try:
            await member.remove_roles(role)
            await ctx.send(f"✅ **{member}** a été démuté.")
        except discord.Forbidden:
            await ctx.send("❌ Permission refusée.")

    @bot_securite.command(name="clear")
    @requires_admin()
    async def sec_clear(ctx, n: int = 5):
        if n < 1 or n > 100:
            return await ctx.send("❌ Entre 1 et 100 messages.")
        deleted = await ctx.channel.purge(limit=n + 1)
        await ctx.send(f"🗑️ **{len(deleted) - 1}** messages supprimés.", delete_after=4)

    @bot_securite.command(name="warn")
    @requires_admin()
    async def sec_warn(ctx, member: discord.Member = None, *, reason: str = "Comportement inapproprié"):
        if not member:
            return await ctx.send("Usage : `!sec warn @user raison`")
        try:
            await member.send(
                f"⚠️ Tu as reçu un avertissement sur **{ctx.guild.name}**.\n**Raison :** {reason}"
            )
        except Exception:
            pass
        embed = discord.Embed(
            title="⚠️ Avertissement",
            description=f"**{member}** a été averti.\n**Raison :** {reason}",
            color=0xFDCB6E, timestamp=datetime.now(timezone.utc),
        )
        await ctx.send(embed=embed)
        log_embed = discord.Embed(
            title="⚠️ Warn émis",
            description=f"**Membre :** {member.mention}\n**Raison :** {reason}\n**Par :** {ctx.author.mention}",
            color=0xFDCB6E, timestamp=datetime.now(timezone.utc),
        )
        await send_log(ctx.guild, log_embed)

    # ── Anti-raid ─────────────────────────────────────────
    @bot_securite.command(name="antiraid")
    @requires_admin()
    async def sec_antiraid(ctx, sub: str = None, *args):
        cfg = get_guild_cfg(ctx.guild.id)
        if not sub:
            state = "✅ Activé" if cfg["antiraid_enabled"] else "❌ Désactivé"
            return await ctx.send(f"Anti-raid : **{state}** · {cfg['antiraid_joins']} joins en {cfg['antiraid_seconds']}s")
        sub = sub.lower()
        if sub == "on":
            cfg["antiraid_enabled"] = True
            save_guild_cfg(ctx.guild.id)
            await ctx.send("🔒 Anti-raid **activé**.")
        elif sub == "off":
            cfg["antiraid_enabled"] = False
            save_guild_cfg(ctx.guild.id)
            await ctx.send("🔓 Anti-raid **désactivé**.")
        elif sub == "config" and len(args) >= 2:
            try:
                cfg["antiraid_joins"]   = int(args[0])
                cfg["antiraid_seconds"] = int(args[1])
                save_guild_cfg(ctx.guild.id)
                await ctx.send(f"✅ Anti-raid configuré : alerte si **{args[0]} joins** en **{args[1]}s**.")
            except ValueError:
                await ctx.send("❌ Usage : `!sec antiraid config N_JOINS N_SECONDES`")
        else:
            await ctx.send("Usage : `!sec antiraid on/off` · `!sec antiraid config 5 10`")

    # ── Mots interdits ────────────────────────────────────
    @bot_securite.command(name="badword")
    @requires_admin()
    async def sec_badword(ctx, sub: str = "list", *, word: str = None):
        cfg = get_guild_cfg(ctx.guild.id)
        sub = sub.lower()
        if sub == "add" and word:
            word = word.lower().strip()
            if word not in cfg["banned_words"]:
                cfg["banned_words"].append(word)
                save_guild_cfg(ctx.guild.id)
            await ctx.send(f"🚫 `{word}` ajouté aux mots interdits.")
        elif sub == "remove" and word:
            word = word.lower().strip()
            cfg["banned_words"] = [w for w in cfg["banned_words"] if w != word]
            save_guild_cfg(ctx.guild.id)
            await ctx.send(f"✅ `{word}` retiré.")
        elif sub == "list":
            words = cfg.get("banned_words", [])
            if not words:
                return await ctx.send("📋 Aucun mot interdit configuré.")
            await ctx.send(f"🚫 **Mots interdits :** {', '.join(f'`{w}`' for w in words)}")
        else:
            await ctx.send("Usage : `!sec badword add MOT` · `remove MOT` · `list`")

    # ── Infos ─────────────────────────────────────────────
    @bot_securite.command(name="status")
    async def sec_status(ctx):
        cfg = get_guild_cfg(ctx.guild.id)
        g   = ctx.guild
        embed = discord.Embed(
            title=f"🛡️ Configuration — {g.name}",
            color=0x6C5CE7,
            timestamp=datetime.now(timezone.utc),
        )
        wc = f"<#{cfg['welcome_channel']}>" if cfg.get("welcome_channel") else "❌ Non configuré"
        lc = f"<#{cfg['log_channel']}>"     if cfg.get("log_channel")     else "❌ Non configuré"
        rc = f"<#{cfg['rules_channel']}>"   if cfg.get("rules_channel")   else "❌ Non configuré"
        ar = f"<@&{cfg['autorole']}>"       if cfg.get("autorole")        else "❌ Non configuré"
        embed.add_field(name="👋 Bienvenue",   value=wc, inline=True)
        embed.add_field(name="📋 Logs",        value=lc, inline=True)
        embed.add_field(name="📜 Règles",      value=rc, inline=True)
        embed.add_field(name="🎭 Auto-rôle",   value=ar, inline=True)
        embed.add_field(
            name="🚨 Anti-raid",
            value=(f"{'✅ Activé' if cfg['antiraid_enabled'] else '❌ Désactivé'} · "
                   f"{cfg['antiraid_joins']} joins/{cfg['antiraid_seconds']}s"),
            inline=True,
        )
        embed.add_field(
            name="🚫 Mots interdits",
            value=str(len(cfg.get("banned_words", []))) + " mot(s)",
            inline=True,
        )
        embed.add_field(name="👥 Membres", value=str(g.member_count), inline=True)
        embed.set_footer(text="Iris Sécurité · Configuration serveur")
        await ctx.send(embed=embed)

    @bot_securite.command(name="userinfo")
    async def sec_userinfo(ctx, member: discord.Member = None):
        member = member or ctx.author
        embed  = discord.Embed(
            title=f"👤 {member}",
            color=0x6C5CE7,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🆔 ID",           value=str(member.id),                                    inline=True)
        embed.add_field(name="📛 Pseudo",        value=member.display_name,                               inline=True)
        embed.add_field(name="🤖 Bot",           value="Oui" if member.bot else "Non",                    inline=True)
        embed.add_field(name="📅 Compte créé",   value=member.created_at.strftime("%d/%m/%Y %H:%M"),      inline=True)
        embed.add_field(name="📥 A rejoint",     value=member.joined_at.strftime("%d/%m/%Y %H:%M") if member.joined_at else "?", inline=True)
        embed.add_field(name="🎭 Rôles",
                        value=", ".join(r.mention for r in member.roles[1:]) or "Aucun",
                        inline=False)
        embed.set_footer(text="Iris Sécurité · Infos membre")
        await ctx.send(embed=embed)
