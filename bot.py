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

VERIFY_CHANNEL_ID = int(os.getenv("VERIFY_CHANNEL_ID"))
UNVERIFIED_ROLE_ID = int(os.getenv("UNVERIFIED_ROLE_ID"))
MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID"))
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID"))

VERIFY_CODE = os.getenv("VERIFY_CODE", "RENARDDZAKA").strip().lower()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

message_cache = {}
join_cache = []
nuke_cache = {}

raid_mode = False

SUSPICIOUS_LINKS = [
    "discord.gift",
    "free-nitro",
    "nitro-free",
    "grabify",
    "bit.ly",
    "tinyurl",
    "discord.gg",
    "discord.com/invite",
]

DANGEROUS_WORDS = [
    "token grabber",
    "ddos",
    "hack server",
    "free nitro",
    "password",
]

VERIFICATION_MESSAGE = """
Hey !

J'ai créé ce serveur pour réunir ma communauté qui suit mon art, et surtout permettre aux artistes ou personnes qui apprécient l'art et les animaux de trouver ici un endroit où partager ce qu'ils aiment.

Merci de respecter les personnes avec qui tu échanges, même lorsque tu n’es pas d’accord avec elles.
Évite les provocations inutiles, le spam ou tout comportement qui pourrait nuire à l’ambiance du serveur.
Les liens suspects, les comportements malveillants ou les perturbations volontaires ne seront pas tolérés.

Si tu es ici avec de bonnes intentions, alors tu es le bienvenu parmi nous. 🌙

━━━━━━━━━━━━━━━━━━

# 🔐 IMPORTANT — VÉRIFICATION 🔐

**Répond à cette énigme pour rejoindre le serveur :**

> Mon premier est un animal roux, mignon et rusé.
> Mon second est le pseudo de l'artiste de ce serveur.

**Le code d'accès correspond à la combinaison de ces deux réponses, collées (sans espace) et entièrement en MAJUSCULES.**

━━━━━━━━━━━━━━━━━━

`RENARDDZAKA`
"""


async def log(guild, text):
    channel = guild.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(text)


async def refresh_verification_message(guild):
    channel = guild.get_channel(VERIFY_CHANNEL_ID)

    if not channel:
        return

    try:
        await channel.purge(limit=50)
    except Exception:
        pass

    await channel.send(VERIFICATION_MESSAGE)


async def send_verification_message(member):
    channel = member.guild.get_channel(VERIFY_CHANNEL_ID)

    if channel:
        await channel.send(
            f"{member.mention}, lis le message de vérification ci-dessus puis écris le code indiqué pour accéder au serveur.",
            delete_after=12
        )


async def quarantine(member, reason):
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
    print(f"🔐 Code vérification actif : {VERIFY_CODE.upper()}")

    for guild in bot.guilds:
        await refresh_verification_message(guild)


@bot.event
async def on_member_join(member):
    global raid_mode

    welcome_channel = member.guild.get_channel(WELCOME_CHANNEL_ID)

    if welcome_channel:
        try:
            await welcome_channel.send(
                f"<:hi:892451489333780551> <:joy:892479257517883413>\n"
                f"Bienvenue {member.mention} sur le serveur !\n\n"
                f"Nous espérons que tu te plairas ici parmi nous.\n"
                f"Installe-toi confortablement, prends le temps de découvrir les lieux et amuse-toi bien.\n"
                f"<:thx:893254491053367396>"
            )
        except Exception as error:
            await log(member.guild, f"⚠️ Erreur bienvenue : {error}")

    now = datetime.now(timezone.utc)

    unverified_role = member.guild.get_role(UNVERIFIED_ROLE_ID)

    if unverified_role:
        try:
            await member.add_roles(
                unverified_role,
                reason="Nouveau membre en attente de vérification"
            )
        except Exception as error:
            await log(member.guild, f"⚠️ Impossible d’ajouter Non vérifié : {error}")

    await send_verification_message(member)

    join_cache.append(now.timestamp())

    join_cache[:] = [
        t for t in join_cache
        if now.timestamp() - t <= 20
    ]

    if len(join_cache) >= 5 and not raid_mode:
        raid_mode = True
        await log(member.guild, "🚨 Mode raid activé automatiquement.")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not message.guild:
        return

    member = message.author
    content = message.content.strip()
    content_lower = content.lower().strip()

    if message.channel.id == VERIFY_CHANNEL_ID:
        if content_lower.startswith("!"):
            await bot.process_commands(message)
            return

        if content_lower == VERIFY_CODE:
            unverified_role = message.guild.get_role(UNVERIFIED_ROLE_ID)
            member_role = message.guild.get_role(MEMBER_ROLE_ID)
            quarantine_role = message.guild.get_role(QUARANTINE_ROLE_ID)

            try:
                if unverified_role and unverified_role in member.roles:
                    await member.remove_roles(unverified_role)

                if quarantine_role and quarantine_role in member.roles:
                    await member.remove_roles(quarantine_role)

                if member_role and member_role not in member.roles:
                    await member.add_roles(member_role)

                try:
                    await message.delete()
                except Exception:
                    pass

                await message.channel.send(
                    f"✅ {member.mention}, vérification réussie. Bienvenue sur le serveur !",
                    delete_after=8
                )

                await log(
                    message.guild,
                    f"✅ Vérification réussie pour {member.mention}"
                )

            except Exception as error:
                await log(
                    message.guild,
                    f"❌ Erreur vérification : {error}"
                )

            return

        try:
            await message.delete()
        except Exception:
            pass

        await message.channel.send(
            f"❌ {member.mention}, code incorrect.",
            delete_after=6
        )

        return

    unverified_role = message.guild.get_role(UNVERIFIED_ROLE_ID)

    if unverified_role and unverified_role in member.roles:
        try:
            await message.delete()
        except Exception:
            pass
        return

    if any(link in content_lower for link in SUSPICIOUS_LINKS):
        try:
            await message.delete()
        except Exception:
            pass

        await quarantine(member, "lien suspect")
        return

    if any(word in content_lower for word in DANGEROUS_WORDS):
        try:
            await message.delete()
        except Exception:
            pass

        await quarantine(member, "message dangereux")
        return

    if len(message.mentions) >= 5:
        try:
            await message.delete()
        except Exception:
            pass

        await quarantine(member, "spam mentions")
        return

    if len(content_lower) >= 8 and len(set(content_lower.replace(" ", ""))) <= 2:
        try:
            await message.delete()
        except Exception:
            pass

        await quarantine(member, "spam clavier")
        return

    if member.id not in message_cache:
        message_cache[member.id] = []

    now = datetime.now(timezone.utc).timestamp()

    message_cache[member.id].append((content_lower, now))

    message_cache[member.id] = [
        msg for msg in message_cache[member.id]
        if now - msg[1] <= 10
    ]

    recent_messages = [msg[0] for msg in message_cache[member.id]]

    if recent_messages.count(content_lower) >= 3:
        try:
            await message.delete()
        except Exception:
            pass

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
async def status(ctx):
    await ctx.send(
        f"🛡️ Mode raid : {'ACTIF 🚨' if raid_mode else 'inactif ✅'}\n"
        f"🔐 Code : `{VERIFY_CODE.upper()}`"
    )


@bot.command()
@commands.has_permissions(administrator=True)
async def verification(ctx):
    await ctx.send(
        f"🔐 Code actuel : `{VERIFY_CODE.upper()}`"
    )


@bot.command()
@commands.has_permissions(administrator=True)
async def refresh_verif(ctx):
    await refresh_verification_message(ctx.guild)

    await ctx.send(
        "✅ Message vérification actualisé."
    )


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
async def noproblem(ctx, member: discord.Member):
    unverified_role = ctx.guild.get_role(UNVERIFIED_ROLE_ID)
    quarantine_role = ctx.guild.get_role(QUARANTINE_ROLE_ID)
    member_role = ctx.guild.get_role(MEMBER_ROLE_ID)

    try:
        if unverified_role and unverified_role in member.roles:
            await member.remove_roles(unverified_role)

        if quarantine_role and quarantine_role in member.roles:
            await member.remove_roles(quarantine_role)

        if member_role and member_role not in member.roles:
            await member.add_roles(member_role)

    except Exception as error:
        await ctx.send(f"❌ Erreur : {error}")
        return

    await ctx.send(f"✅ {member.mention} validé.")


@bot.command()
@commands.has_permissions(administrator=True)
async def problem(ctx, member: discord.Member):
    await quarantine(member, "manuel")

    await ctx.send(
        f"🚨 {member.mention} placé en quarantaine."
    )


keep_alive()
bot.run(TOKEN)
