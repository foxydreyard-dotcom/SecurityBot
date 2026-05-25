import os
import re
import asyncio
import unicodedata
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

BAD_PATTERNS = [
    "fdp",
    "connard",
    "conard",
    "connar",
    "pute",
    "ptn",
    "encule",
    "enculer",
    "salope",
    "salop",
    "batard",
    "batart",
    "ntm",
    "tg",
    "ta gueule",
    "ferme ta gueule",
    "nique ta mere",
    "nik ta mere",
    "nique ta mer",
    "nik ta mer",
    "nique t mere",
    "nik t mer",
    "nique tes morts",
    "nik tes morts",
]

THREAT_PATTERNS = [
    "je vais te tuer",
    "jvais te tuer",
    "jte tue",
    "je te tue",
    "tu vas mourir",
    "je vais te retrouver",
    "jvais te retrouver",
    "je vais te frapper",
    "jvais te frapper",
    "je vais te demolir",
]

CONTEXT_PATTERNS = [
    "on ma dit",
    "on m a dit",
    "il ma dit",
    "il m a dit",
    "elle ma dit",
    "elle m a dit",
    "jai recu",
    "j ai recu",
    "on ma insulte",
    "on m a insulte",
    "on ma menace",
    "on m a menace",
    "en mp",
    "screen",
    "capture",
    "preuve",
    "temoignage",
    "je viens vous voir",
    "je signale",
    "il a dit que",
    "elle a dit que",
]

DIRECT_ATTACK_WORDS = [
    "tes",
    "t es",
    "tu es",
    "toi",
    "va te",
    "ferme ta",
    "sale",
    "nique",
    "nik",
    "ta mere",
    "ta mer",
    "tes morts",
]


async def log(guild, text):
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(text)


def normalize_text(text):
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9@#\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def contains_pattern(content, patterns):
    content = normalize_text(content)
    return any(pattern in content for pattern in patterns)


def is_context_ignored(content):
    return contains_pattern(content, CONTEXT_PATTERNS)


def contains_bad_word(content):
    return contains_pattern(content, BAD_PATTERNS)


def contains_threat(content):
    return contains_pattern(content, THREAT_PATTERNS)


def is_direct_attack(message):
    content = normalize_text(message.content)

    if len(message.mentions) > 0:
        return True

    return any(word in content for word in DIRECT_ATTACK_WORDS)


def is_report_message(message):
    content = normalize_text(message.content)

    has_context = is_context_ignored(content)
    has_mention = len(message.mentions) > 0
    has_bad = contains_bad_word(content) or contains_threat(content)

    # Témoignage sans mention directe : on laisse passer
    if has_context and not has_mention:
        return True

    # Témoignage avec mention mais formulation de signalement : on laisse passer
    report_words = [
        "je signale",
        "je viens vous voir",
        "on ma dit",
        "il ma dit",
        "elle ma dit",
        "jai recu",
        "en mp",
        "screen",
        "capture",
        "preuve",
    ]

    if has_context and has_bad:
        if any(word in content for word in report_words):
            # sauf si le message commence clairement par une attaque directe
            if content.startswith(("tu ", "toi ", "tes ", "t es ", "sale ", "nique ", "nik ")):
                return False
            return True

    return False


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
    content = message.content
    normalized = normalize_text(content)

    if member.id in safe_members:
        await bot.process_commands(message)
        return

    # Témoignage / signalement : on ne sanctionne pas
    if is_report_message(message):
        await bot.process_commands(message)
        return

    # Menace directe
    if contains_threat(normalized) and is_direct_attack(message):
        await message.delete()
        await quarantine(member, "menace directe")

        await log(
            message.guild,
            f"🚨 Menace directe détectée\n"
            f"Auteur : {member.mention}\n"
            f"Message supprimé."
        )
        return

    # Insulte directe
    if contains_bad_word(normalized) and is_direct_attack(message):
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
    if any(link in normalized for link in SUSPICIOUS_LINKS):
        await message.delete()
        await quarantine(member, "lien suspect")
        return

    # Mots dangereux
    if any(word in normalized for word in DANGEROUS_WORDS):
        await message.delete()
        await quarantine(member, "message dangereux")
        return

    # Spam mentions
    if len(message.mentions) >= 5:
        await message.delete()
        await quarantine(member, "spam mentions")
        return

    # Spam clavier
    if len(normalized) >= 8 and len(set(normalized.replace(" ", ""))) <= 2:
        await message.delete()
        await quarantine(member, "spam clavier")
        return

    if member.id not in message_cache:
        message_cache[member.id] = []

    now = datetime.now(timezone.utc).timestamp()
    message_cache[member.id].append((normalized, now))

    message_cache[member.id] = [
        msg for msg in message_cache[member.id]
        if now - msg[1] <= 10
    ]

    recent_messages = [msg[0] for msg in message_cache[member.id]]

    if recent_messages.count(normalized) >= 3:
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
