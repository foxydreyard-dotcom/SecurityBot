import os
import re
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv
from keep_alive import keep_alive

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
QUARANTINE_ROLE_ID = int(os.getenv("QUARANTINE_ROLE_ID"))

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

message_cache = {}
join_cache = []
nuke_cache = {}

raid_mode = False
safe_members = set()

SUSPICIOUS_LINKS = [
    "discord.gift",
    "free-nitro",
    "nitro-free",
    "grabify",
    "bit.ly",
    "tinyurl",
]

DANGEROUS_WORDS = [
    "token grabber",
    "ddos",
    "hack server",
    "free nitro",
    "password",
]

BAD_WORDS = [
    "fdp",
    "connard",
    "pute",
    "enculé",
    "salope",
    "ntm",
    "tg",
    "ferme ta gueule",
    "bâtard",
    "nique ta mère",
    "nique ta mere",
    "nique tes morts",
]

THREAT_WORDS = [
    "je vais te tuer",
    "je vais te retrouver",
    "tu vas mourir",
    "je vais te frapper",
    "je vais te démolir",
]

CONTEXT_IGNORE = [
    "on m'a dit",
    "il m'a dit",
    "elle m'a dit",
    "j'ai reçu",
    "on m'a insulté",
    "on m'a menacé",
    "en mp",
    "screen",
    "capture",
    "preuve",
    "témoignage",
]


async def log(guild, text):
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(text)


def is_context_ignored(content):
    return any(text in content.lower() for text in CONTEXT_IGNORE)


def contains_bad_word(content):
    return any(word in content.lower() for word in BAD_WORDS)


def contains_threat(content):
    return any(word in content.lower() for word in THREAT_WORDS)


def is_direct_attack(message):
    content = message.content.lower()

    direct_words = [
        "t'es",
        "tu es",
        "va te",
        "ferme ta",
        "sale",
        "nique",
        "ta mère",
        "ta mere",
        "tes morts",
    ]

    if len(message.mentions) > 0:
        return True

    return any(word in content for word in direct_words)


async def quarantine(member, reason):
    if member.id in safe_members:
        return

    role = member.guild.get_role(QUARANTINE_ROLE_ID)

    if role:
        try:
            await member.add_roles(role, reason=reason)
        except Exception as error:
            await log(member.guild, f"⚠️ Erreur quarantaine : {error}")

    await log(
        member.guild,
        f"🚨 Membre isolé\n"
        f"Utilisateur : {member.mention}\n"
        f"Raison : {reason}"
    )


async def check_nuke(guild, user, action):
    if user.bot:
        return

    if user.id in safe_members:
        await log(guild, f"🟢 Action ignorée safe list : {user.mention}")
        return

    now = datetime.now(timezone.utc).timestamp()

    if user.id not in nuke_cache:
        nuke_cache[user.id] = []

    nuke_cache[user.id].append(now)

    nuke_cache[user.id] = [
        t for t in nuke_cache[user.id]
        if now - t <= 30
    ]

    await log(
        guild,
        f"⚠️ Action sensible détectée\n"
        f"Utilisateur : {user.mention}\n"
        f"Action : {action}\n"
        f"Compteur : {len(nuke_cache[user.id])}/3"
    )

    if len(nuke_cache[user.id]) >= 3:
        member = guild.get_member(user.id)
        if member:
            await quarantine(member, f"anti-nuke : {action}")


@bot.event
async def on_ready():
    print(f"✅ Bot sécurité connecté : {bot.user}")


@bot.event
async def on_member_join(member):
    global raid_mode

    if member.id in safe_members:
        await log(member.guild, f"🟢 Membre safe : {member.mention}")
        return

    now = datetime.now(timezone.utc)
    join_cache.append(now.timestamp())

    join_cache[:] = [
        t for t in join_cache
        if now.timestamp() - t <= 20
    ]

    if len(join_cache) >= 5 and not raid_mode:
        raid_mode = True
        await log(member.guild, "🚨 Mode raid activé automatiquement.")

    account_age = now - member.created_at

    risk = 0
    reasons = []

    if account_age.days < 7:
        risk += 3
        reasons.append("compte récent")

    if member.avatar is None:
        risk += 1
        reasons.append("pas d'avatar")

    if re.search(r"(admin|modo|staff|nitro)", member.name.lower()):
        risk += 2
        reasons.append("pseudo suspect")

    if raid_mode:
        risk += 5
        reasons.append("mode raid")

    await log(
        member.guild,
        f"👤 Nouveau membre : {member.mention}\n"
        f"Risque : {risk}\n"
        f"Détails : {', '.join(reasons) if reasons else 'aucun'}"
    )

    if risk >= 3:
        await quarantine(member, "profil suspect")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not message.guild:
        return

    member = message.author
    content = message.content.lower().strip()

    if member.id in safe_members:
        await bot.process_commands(message)
        return

    # Ignore témoignages seulement si ce n’est PAS une attaque directe
    if is_context_ignored(content) and not is_direct_attack(message):
        await bot.process_commands(message)
        return

    # Menaces directes
    if contains_threat(content) and is_direct_attack(message):
        await message.delete()
        await quarantine(member, "menace directe")

        await log(
            message.guild,
            f"🚨 Menace directe détectée\n"
            f"Auteur : {member.mention}\n"
            f"Message supprimé."
        )
        return

    # Insultes directes
    if contains_bad_word(content) and is_direct_attack(message):
        await message.delete()

        await log(
            message.guild,
            f"⚠️ Insulte directe détectée\n"
            f"Auteur : {member.mention}\n"
            f"Message supprimé."
        )

        try:
            await member.send("⚠️ Merci de rester respectueux sur le serveur.")
        except Exception:
            pass

        return

    # Liens suspects
    if any(link in content for link in SUSPICIOUS_LINKS):
        await message.delete()
        await quarantine(member, "lien suspect")
        return

    # Mots dangereux
    if any(word in content for word in DANGEROUS_WORDS):
        await message.delete()
        await quarantine(member, "message dangereux")
        return

    # Spam mentions
    if len(message.mentions) >= 5:
        await message.delete()
        await quarantine(member, "spam mentions")
        return

    # Spam clavier
    if len(content) >= 8 and len(set(content)) <= 2:
        await message.delete()
        await quarantine(member, "spam clavier")
        return

    if member.id not in message_cache:
        message_cache[member.id] = []

    now = datetime.now(timezone.utc).timestamp()
    message_cache[member.id].append((content, now))

    message_cache[member.id] = [
        msg for msg in message_cache[member.id]
        if now - msg[1] <= 10
    ]

    recent_messages = [msg[0] for msg in message_cache[member.id]]

    if recent_messages.count(content) >= 3:
        await message.delete()
        await quarantine(member, "message répété")
        return

    if len(message_cache[member.id]) >= 6:
        await quarantine(member, "flood")
        return

    await bot.process_commands(message)


@bot.event
async def on_guild_channel_create(channel):
    await asyncio.sleep(2)

    async for entry in channel.guild.audit_logs(
        limit=5,
        action=discord.AuditLogAction.channel_create
    ):
        if entry.target and entry.target.id == channel.id:
            await check_nuke(channel.guild, entry.user, "création salon")
            break


@bot.event
async def on_guild_channel_delete(channel):
    await asyncio.sleep(2)

    async for entry in channel.guild.audit_logs(
        limit=5,
        action=discord.AuditLogAction.channel_delete
    ):
        await check_nuke(channel.guild, entry.user, "suppression salon")
        break


@bot.event
async def on_guild_role_delete(role):
    await asyncio.sleep(2)

    async for entry in role.guild.audit_logs(
        limit=5,
        action=discord.AuditLogAction.role_delete
    ):
        await check_nuke(role.guild, entry.user, "suppression rôle")
        break


@bot.command()
@commands.has_permissions(administrator=True)
async def securite(ctx):
    await ctx.send("🛡️ Système sécurité actif.")


@bot.command()
@commands.has_permissions(administrator=True)
async def raid_on(ctx):
    global raid_mode
    raid_mode = True
    await ctx.send("🚨 Mode raid activé.")


@bot.command()
@commands.has_permissions(administrator=True)
async def raid_off(ctx):
    global raid_mode
    raid_mode = False
    join_cache.clear()
    await ctx.send("✅ Mode raid désactivé.")


@bot.command()
@commands.has_permissions(administrator=True)
async def status(ctx):
    await ctx.send(
        f"🛡️ **Statut sécurité**\n"
        f"Mode raid : {'ACTIF 🚨' if raid_mode else 'inactif ✅'}\n"
        f"Membres safe : {len(safe_members)}\n"
        f"Anti-nuke surveillé : {len(nuke_cache)} utilisateur(s)"
    )


@bot.command()
@commands.has_permissions(administrator=True)
async def noproblem(ctx, member: discord.Member):
    safe_members.add(member.id)

    role = ctx.guild.get_role(QUARANTINE_ROLE_ID)

    try:
        if role and role in member.roles:
            await member.remove_roles(role, reason="safe")
    except Exception as error:
        await ctx.send(f"❌ Erreur : {error}")
        return

    await ctx.send(f"✅ {member.mention} validé.")
    await log(ctx.guild, f"🟢 {member.mention} retiré quarantaine.")


@bot.command()
@commands.has_permissions(administrator=True)
async def problem(ctx, member: discord.Member):
    safe_members.discard(member.id)
    await quarantine(member, "ajout manuel")
    await ctx.send(f"🚨 {member.mention} placé en quarantaine.")


keep_alive()
bot.run(TOKEN)
