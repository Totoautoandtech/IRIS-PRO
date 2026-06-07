"""
bot_securite.py — Bot Iris Sécurité
Gestion du serveur, arrivées membres, modération, logs, anti-raid.
CORRECTION : requires_admin déplacé en dehors de setup_securite() pour éviter
le bug de scope qui empêchait les commandes de se charger.
Préfixe : !sec
"""
import json
import logging
from datetime import datetime, timezone
from pathlib  import Path
import discord
from discord.ext import commands, tasks

logger   = logging.getLogger("BotSecurite")
CFG_PATH = Path(__file__).parent / "data" / "securite.json"


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

intents      = discord.Intents.all()
bot_securite = commands.Bot(command_prefix="!sec ", intents=intents, help_command=None)

# ── CORRECTION : décorateur défini GLOBALEMENT (hors de setup) ───────────────
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


def setup_securite():

    # ── Events ────────────────────────────────────────────
    @bot_securite.event
    async def on_ready():
        logger.info(f"🛡️ Iris Sécurité connectée : {bot_securite.user}")
        await bot_securite.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="le serveur 🛡️")
        )
        if not cleanup_joins_loop.is_running():
            cleanup_joins_loop.start()

    @bot_securite.event
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
                            f"📜 Pense à lire {rules_mention} avant de commencer.\n"
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
        log_e.add_field(name="ID",           value=str(member.id),                             inline=True)
        log_e.add_field(name="Compte créé",  value=member.created_at.strftime("%d/%m/%Y"),     inline=True)
        log_e.set_footer(text="Iris Sécurité · Log arrivée")
        await send_log(guild, log_e)

    @bot_securite.event
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

    @bot_securite.event
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

    @bot_securite.event
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

    @bot_securite.event
    async def on_message(message: discord.Message):
        if message.author.bot or not message.guild:
            await bot_securite.process_commands(message)
            return
        cfg = get_guild_cfg(message.guild.id)
        for word in cfg.get("banned_words", []):
            if word.lower() in message.content.lower():
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
                break
        await bot_securite.process_commands(message)

    @bot_securite.event
    async def on_member_ban(guild: discord.Guild, user: discord.User):
        await send_log(guild, discord.Embed(
            title="🔨 Membre banni",
            description=f"**{user}** (`{user.id}`) banni.",
            color=0xFF0000, timestamp=datetime.now(timezone.utc),
        ))

    @bot_securite.event
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

    # ── Commandes ─────────────────────────────────────────
    @bot_securite.command(name="help")
    async def sec_help(ctx):
        embed = discord.Embed(
            title="🛡️ Iris Sécurité — Aide",
            description="Gestion complète sécurité + arrivées membres.",
            color=0x6C5CE7,
        )
        embed.add_field(name="─── ⚙️ CONFIG ───",           value="\u200b",                                      inline=False)
        embed.add_field(name="`!sec setup welcome`",         value="Ce salon = bienvenue",                         inline=True)
        embed.add_field(name="`!sec setup logs`",            value="Ce salon = logs",                              inline=True)
        embed.add_field(name="`!sec setup rules`",           value="Ce salon = règles",                            inline=True)
        embed.add_field(name="`!sec setup autorole @R`",     value="Rôle automatique à l'arrivée",                 inline=True)
        embed.add_field(name="`!sec welcome msg TEXTE`",     value="`{user}` `{server}` `{membercount}`",          inline=True)
        embed.add_field(name="`!sec welcome test`",          value="Tester le message de bienvenue",               inline=True)
        embed.add_field(name="─── 🚨 MODÉRATION ───",        value="\u200b",                                      inline=False)
        embed.add_field(name="`!sec ban @u [raison]`",       value="Bannir",           inline=True)
        embed.add_field(name="`!sec kick @u [raison]`",      value="Expulser",         inline=True)
        embed.add_field(name="`!sec mute @u [raison]`",      value="Mute",             inline=True)
        embed.add_field(name="`!sec unmute @u`",             value="Unmute",           inline=True)
        embed.add_field(name="`!sec warn @u RAISON`",        value="Avertissement DM", inline=True)
        embed.add_field(name="`!sec clear N`",               value="Supprimer N msgs", inline=True)
        embed.add_field(name="─── 🔒 ANTI-RAID ───",         value="\u200b",                                      inline=False)
        embed.add_field(name="`!sec antiraid on/off`",       value="Activer/désactiver",                           inline=True)
        embed.add_field(name="`!sec antiraid config N T`",   value="N joins en T secondes = alerte",               inline=True)
        embed.add_field(name="─── 🚫 MOTS INTERDITS ───",    value="\u200b",                                      inline=False)
        embed.add_field(name="`!sec badword add MOT`",       value="Ajouter",  inline=True)
        embed.add_field(name="`!sec badword remove MOT`",    value="Retirer",  inline=True)
        embed.add_field(name="`!sec badword list`",          value="Voir",     inline=True)
        embed.add_field(name="─── 📊 INFO ───",              value="\u200b",                                      inline=False)
        embed.add_field(name="`!sec status`",                value="Config du serveur",  inline=True)
        embed.add_field(name="`!sec userinfo [@u]`",         value="Infos sur un membre", inline=True)
        embed.set_footer(text="Iris Sécurité · Gestion serveur Discord")
        await ctx.send(embed=embed)

    @bot_securite.command(name="setup")
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
            await ctx.send("❓ Cible inconnue : `welcome` · `logs` · `rules` · `autorole`")

    @bot_securite.command(name="welcome")
    @admin_only()
    async def sec_welcome(ctx, sub: str = None, *, texte: str = None):
        cfg = get_guild_cfg(ctx.guild.id)
        if not sub:
            return await ctx.send("`!sec welcome msg TEXTE` · `reset` · `test`")
        sub = sub.lower()
        if sub == "msg" and texte:
            cfg["welcome_msg"] = texte
            save_guild_cfg(ctx.guild.id)
            await ctx.send("✅ Message personnalisé ! Variables : `{user}` `{username}` `{server}` `{membercount}`")
        elif sub == "reset":
            cfg["welcome_msg"] = None
            save_guild_cfg(ctx.guild.id)
            await ctx.send("✅ Message remis par défaut.")
        elif sub == "test":
            cid = cfg.get("welcome_channel")
            if not cid:
                return await ctx.send("❌ Aucun salon de bienvenue. Tape `!sec setup welcome` ici d'abord.")
            channel = ctx.guild.get_channel(cid)
            member  = ctx.author
            rules_mention = f"<#{cfg['rules_channel']}>" if cfg.get("rules_channel") else "les règles"
            if cfg.get("welcome_msg"):
                text = (cfg["welcome_msg"]
                        .replace("{user}", member.mention)
                        .replace("{username}", str(member))
                        .replace("{server}", ctx.guild.name)
                        .replace("{membercount}", str(ctx.guild.member_count)))
                await channel.send(f"[TEST] {text}")
            else:
                embed = discord.Embed(
                    title=f"👋 [TEST] Bienvenue sur {ctx.guild.name} !",
                    description=(
                        f"Salut {member.mention} ! 🎉\n"
                        f"📜 Pense à lire {rules_mention}.\n"
                        f"Tu es le **{ctx.guild.member_count}ème** membre !"
                    ),
                    color=0x00b894,
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                await channel.send(embed=embed)
            await ctx.send(f"✅ Test envoyé dans {channel.mention} !")

    @bot_securite.command(name="ban")
    @admin_only()
    async def sec_ban(ctx, member: discord.Member = None, *, reason: str = "Aucune raison"):
        if not member:
            return await ctx.send("Usage : `!sec ban @user [raison]`")
        try:
            await member.ban(reason=f"[Iris Sécurité] {reason}")
            await ctx.send(embed=discord.Embed(
                title="🔨 Banni",
                description=f"**{member}** banni.\n**Raison :** {reason}",
                color=0xFF0000, timestamp=datetime.now(timezone.utc),
            ))
        except discord.Forbidden:
            await ctx.send("❌ Permission insuffisante pour bannir.")

    @bot_securite.command(name="kick")
    @admin_only()
    async def sec_kick(ctx, member: discord.Member = None, *, reason: str = "Aucune raison"):
        if not member:
            return await ctx.send("Usage : `!sec kick @user [raison]`")
        try:
            await member.kick(reason=f"[Iris Sécurité] {reason}")
            await ctx.send(embed=discord.Embed(
                title="👢 Expulsé",
                description=f"**{member}** expulsé.\n**Raison :** {reason}",
                color=0xFDCB6E, timestamp=datetime.now(timezone.utc),
            ))
        except discord.Forbidden:
            await ctx.send("❌ Permission insuffisante pour expulser.")

    @bot_securite.command(name="mute")
    @admin_only()
    async def sec_mute(ctx, member: discord.Member = None, *, reason: str = "Aucune raison"):
        if not member:
            return await ctx.send("Usage : `!sec mute @user [raison]`")
        cfg  = get_guild_cfg(ctx.guild.id)
        role = ctx.guild.get_role(cfg.get("mute_role")) if cfg.get("mute_role") else None
        if not role:
            try:
                role = await ctx.guild.create_role(name="Muted", reason="Iris Sécurité — mute role")
                for ch in ctx.guild.channels:
                    await ch.set_permissions(role, send_messages=False, speak=False)
                cfg["mute_role"] = role.id
                save_guild_cfg(ctx.guild.id)
            except discord.Forbidden:
                return await ctx.send("❌ Je n'ai pas la permission de créer un rôle Muted.")
        try:
            await member.add_roles(role, reason=f"[Iris Sécurité] {reason}")
            await ctx.send(embed=discord.Embed(
                title="🔇 Muté",
                description=f"**{member}** muté.\n**Raison :** {reason}",
                color=0xA29BFE, timestamp=datetime.now(timezone.utc),
            ))
        except discord.Forbidden:
            await ctx.send("❌ Permission refusée.")

    @bot_securite.command(name="unmute")
    @admin_only()
    async def sec_unmute(ctx, member: discord.Member = None):
        if not member:
            return await ctx.send("Usage : `!sec unmute @user`")
        cfg  = get_guild_cfg(ctx.guild.id)
        role = ctx.guild.get_role(cfg.get("mute_role")) if cfg.get("mute_role") else None
        if not role:
            return await ctx.send("❌ Aucun rôle mute configuré.")
        try:
            await member.remove_roles(role)
            await ctx.send(f"✅ **{member}** démuté.")
        except discord.Forbidden:
            await ctx.send("❌ Permission refusée.")

    @bot_securite.command(name="clear")
    @admin_only()
    async def sec_clear(ctx, n: int = 5):
        if not 1 <= n <= 100:
            return await ctx.send("❌ Entre 1 et 100.")
        deleted = await ctx.channel.purge(limit=n + 1)
        await ctx.send(f"🗑️ **{len(deleted) - 1}** messages supprimés.", delete_after=4)

    @bot_securite.command(name="warn")
    @admin_only()
    async def sec_warn(ctx, member: discord.Member = None, *, reason: str = "Comportement inapproprié"):
        if not member:
            return await ctx.send("Usage : `!sec warn @user raison`")
        try:
            await member.send(f"⚠️ Avertissement sur **{ctx.guild.name}**.\n**Raison :** {reason}")
        except Exception:
            pass
        await ctx.send(embed=discord.Embed(
            title="⚠️ Avertissement",
            description=f"**{member}** averti.\n**Raison :** {reason}",
            color=0xFDCB6E, timestamp=datetime.now(timezone.utc),
        ))
        await send_log(ctx.guild, discord.Embed(
            title="⚠️ Warn",
            description=f"**Membre :** {member.mention}\n**Raison :** {reason}\n**Par :** {ctx.author.mention}",
            color=0xFDCB6E, timestamp=datetime.now(timezone.utc),
        ))

    @bot_securite.command(name="antiraid")
    @admin_only()
    async def sec_antiraid(ctx, sub: str = None, *args):
        cfg = get_guild_cfg(ctx.guild.id)
        if not sub:
            state = "✅ Activé" if cfg["antiraid_enabled"] else "❌ Désactivé"
            return await ctx.send(f"Anti-raid : **{state}** · {cfg['antiraid_joins']} joins/{cfg['antiraid_seconds']}s")
        sub = sub.lower()
        if sub == "on":
            cfg["antiraid_enabled"] = True;  save_guild_cfg(ctx.guild.id); await ctx.send("🔒 Anti-raid activé.")
        elif sub == "off":
            cfg["antiraid_enabled"] = False; save_guild_cfg(ctx.guild.id); await ctx.send("🔓 Anti-raid désactivé.")
        elif sub == "config" and len(args) >= 2:
            try:
                cfg["antiraid_joins"]   = int(args[0])
                cfg["antiraid_seconds"] = int(args[1])
                save_guild_cfg(ctx.guild.id)
                await ctx.send(f"✅ Alerte si **{args[0]} joins** en **{args[1]}s**.")
            except ValueError:
                await ctx.send("Usage : `!sec antiraid config N_JOINS N_SECONDES`")
        else:
            await ctx.send("`!sec antiraid on/off` · `!sec antiraid config 5 10`")

    @bot_securite.command(name="badword")
    @admin_only()
    async def sec_badword(ctx, sub: str = "list", *, word: str = None):
        cfg = get_guild_cfg(ctx.guild.id)
        sub = sub.lower()
        if sub == "add" and word:
            w = word.lower().strip()
            if w not in cfg["banned_words"]:
                cfg["banned_words"].append(w)
                save_guild_cfg(ctx.guild.id)
            await ctx.send(f"🚫 `{w}` ajouté.")
        elif sub == "remove" and word:
            w = word.lower().strip()
            cfg["banned_words"] = [x for x in cfg["banned_words"] if x != w]
            save_guild_cfg(ctx.guild.id)
            await ctx.send(f"✅ `{w}` retiré.")
        elif sub == "list":
            words = cfg.get("banned_words", [])
            await ctx.send(f"🚫 **Mots interdits :** {', '.join(f'`{w}`' for w in words) or 'Aucun'}")
        else:
            await ctx.send("`!sec badword add MOT` · `remove MOT` · `list`")

    @bot_securite.command(name="status")
    async def sec_status(ctx):
        cfg = get_guild_cfg(ctx.guild.id)
        g   = ctx.guild
        embed = discord.Embed(title=f"🛡️ Config — {g.name}", color=0x6C5CE7, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👋 Bienvenue",  value=f"<#{cfg['welcome_channel']}>" if cfg.get("welcome_channel") else "❌", inline=True)
        embed.add_field(name="📋 Logs",       value=f"<#{cfg['log_channel']}>"     if cfg.get("log_channel")     else "❌", inline=True)
        embed.add_field(name="📜 Règles",     value=f"<#{cfg['rules_channel']}>"   if cfg.get("rules_channel")   else "❌", inline=True)
        embed.add_field(name="🎭 Auto-rôle",  value=f"<@&{cfg['autorole']}>"       if cfg.get("autorole")        else "❌", inline=True)
        embed.add_field(name="🚨 Anti-raid",
                        value=f"{'✅' if cfg['antiraid_enabled'] else '❌'} · {cfg['antiraid_joins']} joins/{cfg['antiraid_seconds']}s",
                        inline=True)
        embed.add_field(name="🚫 Mots interdits", value=f"{len(cfg.get('banned_words', []))} mot(s)", inline=True)
        embed.add_field(name="👥 Membres",    value=str(g.member_count), inline=True)
        embed.set_footer(text="Iris Sécurité · Configuration serveur")
        await ctx.send(embed=embed)

    @bot_securite.command(name="userinfo")
    async def sec_userinfo(ctx, member: discord.Member = None):
        member = member or ctx.author
        embed  = discord.Embed(title=f"👤 {member}", color=0x6C5CE7, timestamp=datetime.now(timezone.utc))
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🆔 ID",         value=str(member.id),                                                          inline=True)
        embed.add_field(name="📛 Pseudo",      value=member.display_name,                                                     inline=True)
        embed.add_field(name="🤖 Bot",         value="Oui" if member.bot else "Non",                                          inline=True)
        embed.add_field(name="📅 Créé le",     value=member.created_at.strftime("%d/%m/%Y %H:%M"),                            inline=True)
        embed.add_field(name="📥 Rejoint le",  value=member.joined_at.strftime("%d/%m/%Y %H:%M") if member.joined_at else "?", inline=True)
        embed.add_field(name="🎭 Rôles",       value=", ".join(r.mention for r in member.roles[1:]) or "Aucun",               inline=False)
        embed.set_footer(text="Iris Sécurité · Infos membre")
        await ctx.send(embed=embed)
