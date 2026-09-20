from __future__ import annotations

import os
import re
import json
import html
import io
import csv
import urllib.request
import time
import asyncio
import logging
import inspect
import aiohttp

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

import discord
from discord import app_commands
from discord.ext import commands, tasks

try:
    import aiosqlite
except ImportError as exc:                    
    raise SystemExit(
        "Не найден пакет aiosqlite. Установите зависимости командой:\n"
        "pip install -U discord.py aiosqlite python-dotenv"
    ) from exc

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import secrets
import string
import threading
import typing
import traceback
from pathlib import Path

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        CallbackQueryHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )
    from telegram.error import BadRequest
    TG_AVAILABLE = True
except ImportError:
    TG_AVAILABLE = False
    Update = typing.Any
    InlineKeyboardButton = typing.Any
    InlineKeyboardMarkup = typing.Any

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    ContextTypes = typing.Any
    Application = typing.Any
    CommandHandler = typing.Any
    CallbackQueryHandler = typing.Any
    MessageHandler = typing.Any
    filters = typing.Any
    BadRequest = Exception

import random

try:
    from stats_card import generate_stats_card
    from givecoin_card import generate_givecoin_card
    from roulette_card import generate_roulette_image
    CARDS_AVAILABLE = True
except ImportError as _card_err:
    CARDS_AVAILABLE = False

def _get_env_int(*keys: str) -> Optional[int]:
    for key in keys:
        val = os.getenv(key)
        if val:
            val = val.strip()
            if val.isdigit():
                return int(val)
    return None

if os.path.exists(".env"):
    try:
        with open(".env", "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))
    except Exception:
        pass

class Config:
    TOKEN: str = os.getenv("DISCORD_TOKEN", "").strip()
    TG_TOKEN: str = os.getenv("TG_TOKEN", "8609517555:AAHd8og36baDmu3svseoEXp6yeIqrKvJGxo").strip()
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "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").strip()



    GUILD_ID: Optional[int] = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None
    DB_PATH: str = os.getenv("DB_PATH", "moderbot.sqlite3")

    DEFAULT_TICKET_CATEGORY_ID: Optional[int] = _get_env_int(
        "CATEGORY_TICKETS_ID", "TICKET_CATEGORY_ID", "CATEGORY_TICKET_ID"
    )
    DEFAULT_CLOSED_CATEGORY_ID: Optional[int] = _get_env_int(
        "CATEGORY_CLOSED_TICKETS_ID", "CLOSED_CATEGORY_ID", "CATEGORY_CLOSED_ID", "CLOSED_TICKET_CATEGORY_ID"
    )

    EMBED_COLOR_MAIN = 5793266                               
    EMBED_COLOR_ERROR = 0xFF3B3B
    EMBED_COLOR_SUCCESS = 0x57F287
    EMBED_COLOR_WARNING = 0xFEE75C
    EMBED_COLOR_TICKET = 0x2B2D31

    MODERATION_STATS = (
        "tickets", "likes", "dislikes", "mutes", "kicks",
        "bans", "warns", "deleted_msgs", "strict_vigs", "oral_vigs",
    )

    MODERATION_COMMANDS = (
        "kick", "mute", "unmute", "ban", "unban",
        "warn", "clear", "ticket_take", "ticket_close",
        "setstat_moder", "register", "unregister",
        "pm", "history", "forma", "active", "notif", "vig", "me", "stopn",
    )

    MODERATION_COMMAND_LABELS: dict[str, str] = {
        "kick": "/kick",
        "mute": "/mute",
        "unmute": "/unmute",
        "ban": "/ban",
        "unban": "/unban",
        "warn": "/warn",
        "clear": "/clear",
        "ticket_take": "/ticket take",
        "ticket_close": "/ticket close",
        "setstat_moder": "/setstat moder",
        "register": "/register",
        "unregister": "/unregister",
        "pm": "/pm",
        "history": "/history",
        "forma": "/forma",
        "active": "/active",
        "notif": "/notif",
        "vig": "/vig",
        "me": "/me",
        "stopn": "/stopn",
    }

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "bot_data.json"
data_lock = threading.Lock()

def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

data = load_data()
for key in ("guilds", "totals", "bans", "moderators", "blacklist", "logs", "systems", "access", "warns", "vigs", "tickets_meta", "history_logs"):
    data.setdefault(key, {})

data.setdefault("tg_owner", None)
data.setdefault("tg_access", [])
data.setdefault("tg_activated", False)
data.setdefault("tg_tracking", {})
data.setdefault("tg_codes", {})
data["tg_msg_map"] = {}                                                                                      

GUILD_ID_FOR_ROLES = 1070704320951095296
ALLOWED_GUILD_ID = 1070704320951095296

DISCORD_ROLES = {
    7: ['Разработчик Swag Moderation'],
    5: ['Глава Discorda', 'Руководитель Discorda', 'Заместитель Руководителя Discorda'],
    4: ['ꕤ Главный Модератор Discord ꕤ', 'ꕤ Заместитель Главного Модератора Discord ꕤ'],
    3: ['ꕤ Главный Следящий за Модераторами ꕤ', 'ꕤ Заместитель Следящего за Модераторами ꕤ'],
    2: ['ꕤ Куратор Модерации ꕤ']
}

ACCESS_LEVELS = {
    7: "Главный Разработчик",
    6: "Помощник Разработчика",
    5: "Руководство",
    4: "Главная Модерация",
    3: "Следящая Модерация",
    2: "Куратор Модерации",
    1: "Хелпер",
    0: "Пользователь"
}

def get_user_profile(user_id: int) -> dict:
    return data.get("profiles", {}).get(str(user_id), {})

def get_user_access_level(user_id: int) -> int:
    if user_id == 8035721101 or tg_is_owner(user_id):
        return 7
    profile = get_user_profile(user_id)
    return profile.get("access_level", 0)

def get_user_position(user_id: int) -> str:
    if user_id == 8035721101 or tg_is_owner(user_id):
        return "Главный Разработчик"
    profile = get_user_profile(user_id)
    return profile.get("position", "Пользователь")

def is_user_blocked(user_id: int) -> bool:
    blocked = data.get("blocked_users", {}).get(str(user_id))
    if blocked:
        block_time = blocked.get("blocked_until", 0)
        if time.time() < block_time:
            return True
        else:
            data.get("blocked_users", {}).pop(str(user_id), None)
            save_data()
    return False

def block_user(user_id: int, minutes: int = 10):
    data.setdefault("blocked_users", {})[str(user_id)] = {
        "blocked_until": time.time() + minutes * 60,
        "reason": "Попытка взлома"
    }
    save_data()

def get_discord_access_level(discord_id: int) -> tuple[int, str]:
    try:
        guild = bot.get_guild(GUILD_ID_FOR_ROLES)
        if not guild:
            return 0, "Пользователь"
        member = guild.get_member(discord_id)
        if not member:
            return 0, "Пользователь"
        best_level = 0
        best_position = "Пользователь"
        for level, role_names in DISCORD_ROLES.items():
            for role_name in role_names:
                for role in member.roles:
                    if role.name.lower() == role_name.lower():
                        if level > best_level:
                            best_level = level
                            best_position = ACCESS_LEVELS.get(level, "Пользователь")
                        break
        return best_level, best_position
    except Exception:
        return 0, "Пользователь"

def get_next_ticket_id() -> int:
    data["ticket_counter"] = data.get("ticket_counter", 0) + 1
    if data["ticket_counter"] > 1000:
        data["ticket_counter"] = 1
    save_data()
    return data["ticket_counter"]

def generate_auth_code() -> str:
    return "".join(random.choices(string.digits, k=6))
def save_data():
    with data_lock:
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error("Ошибка сохранения bot_data.json: %s", e)

save_data()

TG_PASSWORD = "A7kP2mX9qR4vL8nB3cF5wY1eT6sH0jU"
LOG_CATEGORIES = ["messages", "roles", "moderation", "tickets", "members", "server"]
CATEGORY_EMOJI = {
    "messages": "💬", "roles": "🎭", "moderation": "🛡",
    "tickets": "🎫", "members": "👋", "server": "⚙️", "all": "🌐"
}
CATEGORY_NAMES = {
    "messages": "Сообщения", "roles": "Роли", "moderation": "Модерация",
    "tickets": "Тикеты", "members": "Участники", "server": "Сервер",
    "all": "Все категории"
}

PAGE_SIZE_SERVERS = 8
PAGE_SIZE_USERS = 5
PAGE_SIZE_ROLES = 10
PAGE_SIZE_CHANNELS = 10
PAGE_SIZE_MODERS = 10
PAGE_SIZE_LOGS = 5
PAGE_SIZE_CHANNELS_TRACK = 10
MAX_HISTORY_LOGS = 50

bot_loop: Optional[asyncio.AbstractEventLoop] = None
tg_bot_ref = None

def history_logs_of(gid) -> list:
    arr = data["history_logs"].setdefault(str(gid), [])
    if not isinstance(arr, list):
        data["history_logs"][str(gid)] = []
        arr = data["history_logs"][str(gid)]
    return arr

def _add_history_log_sync(guild_id: int, category: str, title: str, description: str = "", actor_id: Optional[int] = None, target_id: Optional[int] = None):
    try:
        arr = history_logs_of(str(guild_id))
        entry = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "category": category,
            "title": title,
            "description": description,
            "actor_id": str(actor_id) if actor_id else None,
            "target_id": str(target_id) if target_id else None,
        }
        arr.insert(0, entry)
        if len(arr) > MAX_HISTORY_LOGS:
            arr.pop()
        save_data()
    except Exception as exc:
        log.warning("Ошибка записи истории логов: %s", exc)

def add_history_log(guild_id: int, category: str, title: str, description: str = "", actor_id: Optional[int] = None, target_id: Optional[int] = None):
    try:
        arr = history_logs_of(str(guild_id))
        entry = {
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "category": category,
            "title": title,
            "description": description,
            "actor_id": str(actor_id) if actor_id else None,
            "target_id": str(target_id) if target_id else None,
        }
        arr.insert(0, entry)
        if len(arr) > MAX_HISTORY_LOGS:
            arr.pop()

    except Exception as exc:
        log.warning("Ошибка записи истории логов (в памяти): %s", exc)

def totals_of(gid, uid) -> dict:
    t = data["totals"].setdefault(str(gid), {}).setdefault(str(uid), {"mute": 0, "kick": 0, "ban": 0})
    for k in ("mute", "kick", "ban"):
        t.setdefault(k, 0)
    return t

def short_text(value: typing.Any, limit: int = 32) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit - 1] + "…"

def paginate(items: list, page: int, per_page: int):
    if not items:
        return [], 0, 0
    max_page = max(0, (len(items) - 1) // per_page)
    page = max(0, min(page, max_page))
    start = page * per_page
    return items[start:start + per_page], page, max_page

def pager_row(prefix: str, page: int, max_page: int, force: bool = False) -> list:
    if max_page <= 0 and not force:
        return []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"{prefix}_{page - 1}"))
    row.append(InlineKeyboardButton(f"📄 {page + 1}/{max_page + 1}", callback_data="noop"))
    if page < max_page:
        row.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"{prefix}_{page + 1}"))
    return [row]

def discord_user_link(uid) -> str:
    return f"https://discord.com/users/{uid}"

def format_ts(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts, timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return "—"

    MODERATION_STATS = (
        "tickets", "likes", "dislikes", "mutes", "kicks",
        "bans", "warns", "deleted_msgs",
    )

    MODERATION_COMMANDS = (
        "kick", "mute", "unmute", "ban", "unban",
        "warn", "clear", "ticket_take", "ticket_close",
        "setstat_moder", "register", "unregister", "news",
    )

    MODERATION_COMMAND_LABELS: dict[str, str] = {
        "kick": "/kick",
        "mute": "/mute",
        "unmute": "/unmute",
        "ban": "/ban",
        "unban": "/unban",
        "warn": "/warn",
        "clear": "/clear",
        "ticket_take": "/ticket take",
        "ticket_close": "/ticket close",
        "setstat_moder": "/setstat moder",
        "register": "/register",
        "unregister": "/unregister",
        "news": "/news",
    }

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("moderbot")

def pluralize(number: int, forms: Sequence[str]) -> str:
    n = abs(int(number)) % 100
    n1 = n % 10
    if 10 < n < 20:
        return forms[2]
    if n1 == 1:
        return forms[0]
    if 2 <= n1 <= 4:
        return forms[1]
    return forms[2]

def declension(number: int, forms: Sequence[str]) -> str:
    return f"{number} {pluralize(number, forms)}"

WORDS = {
    "day": ("день", "дня", "дней"),
    "hour": ("час", "часа", "часов"),
    "minute": ("минута", "минуты", "минут"),
    "second": ("секунда", "секунды", "секунд"),
    "ticket": ("тикет", "тикета", "тикетов"),
    "moderator": ("модератор", "модератора", "модераторов"),
    "message": ("сообщение", "сообщения", "сообщений"),
    "role": ("роль", "роли", "ролей"),
}

def person_text(user: Union[discord.User, discord.Member]) -> str:
    return f"{user.mention} ({user.name} | ID: `{user.id}`)"

def user_id_tag(user: Union[discord.User, discord.Member, int]) -> str:
    if isinstance(user, (discord.User, discord.Member)):
        return f"{user.mention} (`{user.id}`)"
    return f"<@{user}> (`{user}`)"

def is_recent(dt: Optional[datetime], seconds: int = 60) -> bool:
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = (datetime.now(timezone.utc) - dt).total_seconds()
    return abs(diff) < seconds

LOG_WEBHOOK_URLS = {
    "roles":      "https://discord.com/api/webhooks/1548745584482193410/gxGSxjepyOt9r2CyjjGPJGj1pSq0yZAzJuFV2h9xrqUBoThIyCNpCkz7VipV6cQPxtNv",
    "moderation": "https://discord.com/api/webhooks/1548745864665636965/vCEyTwktgdid4JxOmrhZHdaGmrG4OPuCFXlrAh1BXRTe7cGe7qd_636GFKQCXf_iFRTM",
    "messages":   "https://discord.com/api/webhooks/1548745947318722590/VHa8hTRWCwpcoj3MStGh0DOo1cDLqwVEvxQf0BuaG3XpMMu6OJHYPpXsWwhAIZ0TP-ZH",
    "tickets":    "https://discord.com/api/webhooks/1548745864665636965/vCEyTwktgdid4JxOmrhZHdaGmrG4OPuCFXlrAh1BXRTe7cGe7qd_636GFKQCXf_iFRTM",
    "members":    "https://discord.com/api/webhooks/1548745584482193410/gxGSxjepyOt9r2CyjjGPJGj1pSq0yZAzJuFV2h9xrqUBoThIyCNpCkz7VipV6cQPxtNv",
    "server":     "https://discord.com/api/webhooks/1548745584482193410/gxGSxjepyOt9r2CyjjGPJGj1pSq0yZAzJuFV2h9xrqUBoThIyCNpCkz7VipV6cQPxtNv",
}

async def send_log(guild: discord.Guild, category: str, embed: discord.Embed, file: Optional[discord.File] = None):
    if not guild:
        log.warning("⚠️ send_log отменён: guild is None")
        return

    cat_key = category.lower().strip()
    log.info("🔔 [SEND_LOG CALLED] category='%s' guild='%s' title='%s'", cat_key, guild.name, embed.title)

    try:
        title = embed.title or "Событие"
        desc_lines = []
        if embed.description:
            desc_lines.append(embed.description)
        for field in embed.fields:
            desc_lines.append(f"{field.name}: {field.value}")
        full_desc = " | ".join(desc_lines)

        add_history_log(guild.id, cat_key, title, full_desc)

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, save_data)
    except Exception as e:
        log.warning("Ошибка при записи истории лога: %s", e)

    webhook_url = LOG_WEBHOOK_URLS.get(cat_key) or LOG_WEBHOOK_URLS.get("moderation")
    if not webhook_url:
        log.warning("⚠️ Webhook URL не найден для категории '%s'", cat_key)
        return

    # Сброс указателя файла при наличии
    if file:
        try:
            file.fp.seek(0)
        except Exception:
            pass

    # Отправка лога через Discord Webhook
    try:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(webhook_url, session=session)
            bot_name = f"SWAG LOGS | {cat_key.upper()}"

            kwargs = {"embed": embed, "username": bot_name}
            if file:
                kwargs["file"] = file

            await webhook.send(**kwargs)
            log.info("🌐 [WEBHOOK LOG SENT] Категория '%s' успешно отправлена на Вебхук!", cat_key)
            return
    except Exception as wh_err:
        log.error("⚠️ Ошибка отправки вебхука '%s': %s", cat_key, wh_err, exc_info=True)

    # Резервная отправка через прямой канал если вебхук вернул ошибку
    DEFAULT_LOG_CHANNELS = {
        "roles":      1369358949668884540,
        "moderation": 1369358936987848736,
        "messages":   1369358923753603133,
        "tickets":    1369358939791876209,
        "members":    1369358942477660191,
        "server":     1369358949668884540,
        "all":        1369358936987848736,
    }
    def_cid = DEFAULT_LOG_CHANNELS.get(cat_key) or DEFAULT_LOG_CHANNELS.get("all")
    if def_cid:
        try:
            channel = guild.get_channel(int(def_cid)) or await guild.fetch_channel(int(def_cid))
            if channel and isinstance(channel, discord.TextChannel):
                if file:
                    try:
                        file.fp.seek(0)
                    except Exception:
                        pass
                    await channel.send(embed=embed, file=file)
                else:
                    await channel.send(embed=embed)
                log.info("📊 [DIRECT LOG SENT] Категория '%s' в #%s", cat_key, channel.name)
        except Exception as send_err:
            log.error("⚠️ Ошибка резервной отправки лога '%s': %s", cat_key, send_err)

def format_duration(total_seconds: int) -> str:
    total_seconds = int(total_seconds)
    if total_seconds <= 0:
        return "0 " + pluralize(0, WORDS["second"])

    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    parts = []
    if days:
        parts.append(declension(days, WORDS["day"]))
    if hours:
        parts.append(declension(hours, WORDS["hour"]))
    if minutes:
        parts.append(declension(minutes, WORDS["minute"]))
    if seconds and not days and not hours:
        parts.append(declension(seconds, WORDS["second"]))
    return " ".join(parts) if parts else "менее минуты"

_DURATION_RE = re.compile(r"(\d+)\s*([dhms])", re.IGNORECASE)
_PERMANENT_WORDS = {"perm", "permanent", "навсегда", "forever", "нав"}

def parse_duration(text: str) -> Optional[int]:
    text = text.strip().lower()
    if text in _PERMANENT_WORDS:
        return None

    matches = _DURATION_RE.findall(text)
    if not matches:
        raise ValueError(
            "Неверный формат длительности. Примеры: `10m`, `2h`, `1d`, `1d12h`, `permanent`."
        )

    multipliers = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    total = 0
    for value, unit in matches:
        total += int(value) * multipliers[unit]
    return total

BACKUP_DIR = "backups"

def guild_dir(guild_id: int) -> str:
    path = os.path.join(BACKUP_DIR, str(guild_id))
    os.makedirs(path, exist_ok=True)
    return path

def list_backups(guild_id: int):
    path = guild_dir(guild_id)
    files = sorted(
        (f for f in os.listdir(path) if f.endswith(".json")),
        key=lambda f: int(f[:-5]) if f[:-5].isdigit() else 0,
    )
    return [os.path.join(path, f) for f in files]

async def make_template(guild: discord.Guild) -> dict:
    roles = []
    for role in sorted(guild.roles, key=lambda r: r.position):
        if role.is_default():
            continue
        roles.append({
            "name": role.name,
            "color": role.color.value,
            "permissions": role.permissions.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "position": role.position,
        })

    channels = []
    for ch in guild.channels:
        overwrites = {}
        for target, ow in ch.overwrites.items():
            if not isinstance(target, discord.Role):
                continue
            allow, deny = ow.pair()
            key = "@everyone" if target.is_default() else target.name
            overwrites[key] = {"allow": allow.value, "deny": deny.value}

        data = {
            "name": ch.name,
            "position": ch.position,
            "category": ch.category.name if ch.category else None,
            "overwrites": overwrites,
        }
        if isinstance(ch, discord.CategoryChannel):
            data["type"] = "category"
        elif isinstance(ch, discord.TextChannel):
            data["type"] = "text"
            data["topic"] = ch.topic
            data["slowmode"] = ch.slowmode_delay
        elif isinstance(ch, discord.VoiceChannel):
            data["type"] = "voice"
            data["bitrate"] = ch.bitrate
            data["user_limit"] = ch.user_limit
        else:
            continue
        channels.append(data)

    webhooks = []
    try:
        for wh in await guild.webhooks():
            webhooks.append({
                "name": wh.name,
                "channel": wh.channel.name if wh.channel else None,
            })
    except discord.Forbidden:
        pass

    return {
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "guild": guild.name,
        "roles": roles,
        "channels": channels,
        "webhooks": webhooks,
    }

def make_overwrite(allow: int, deny: int) -> discord.PermissionOverwrite:
    kwargs = {}
    for name, enabled in discord.Permissions(allow):
        if enabled:
            kwargs[name] = True
    for name, enabled in discord.Permissions(deny):
        if enabled:
            kwargs[name] = False
    return discord.PermissionOverwrite(**kwargs)

def build_overwrites(guild, ch_data, created_roles):
    ow = {}
    for target_name, perms in ch_data.get("overwrites", {}).items():
        if target_name == "@everyone":
            role = guild.default_role
        else:
            role = created_roles.get(target_name) or discord.utils.get(guild.roles, name=target_name)
        if role is None:
            continue
        ow[role] = make_overwrite(perms.get("allow", 0), perms.get("deny", 0))
    return ow

async def apply_template(guild: discord.Guild, data: dict) -> int:
    errors = 0
    created_roles = {}

    for r in sorted(data.get("roles", []), key=lambda x: x.get("position", 0)):
        existing = discord.utils.get(guild.roles, name=r["name"])
        if existing:
            created_roles[r["name"]] = existing
            continue
        try:
            created_roles[r["name"]] = await guild.create_role(
                name=r["name"],
                color=discord.Color(r.get("color", 0)),
                permissions=discord.Permissions(r.get("permissions", 0)),
                hoist=r.get("hoist", False),
                mentionable=r.get("mentionable", False),
            )
        except discord.HTTPException:
            errors += 1

    for ch in data.get("channels", []):
        if ch["type"] != "category":
            continue
        if discord.utils.get(guild.categories, name=ch["name"]):
            continue
        try:
            await guild.create_category(
                ch["name"],
                overwrites=build_overwrites(guild, ch, created_roles),
            )
        except discord.HTTPException:
            errors += 1

    for ch in data.get("channels", []):
        if ch["type"] == "category":
            continue
        if discord.utils.get(guild.channels, name=ch["name"]):
            continue
        category = discord.utils.get(guild.categories, name=ch["category"]) if ch.get("category") else None
        ow = build_overwrites(guild, ch, created_roles)
        try:
            if ch["type"] == "text":
                await guild.create_text_channel(
                    ch["name"],
                    category=category,
                    topic=ch.get("topic"),
                    slowmode_delay=ch.get("slowmode", 0) or 0,
                    overwrites=ow,
                    position=ch.get("position", 0),
                )
            elif ch["type"] == "voice":
                await guild.create_voice_channel(
                    ch["name"],
                    category=category,
                    bitrate=ch.get("bitrate", 64000),
                    user_limit=ch.get("user_limit", 0) or 0,
                    overwrites=ow,
                    position=ch.get("position", 0),
                )
        except discord.HTTPException:
            errors += 1

    for wh in data.get("webhooks", []):
        channel = discord.utils.get(guild.text_channels, name=wh.get("channel"))
        if channel is None:
            continue
        try:
            await channel.create_webhook(name=wh["name"])
        except discord.HTTPException:
            errors += 1

    return errors

GROQ_SYSTEM_PROMPT = """
Ты — ассистент модерации Discord-сервера ("Swag Moderation AI").
Твои разработчики/создатели: **Syndic** и **Ace Nemos**.

ОФОРМЛЕНИЕ И СТИЛЬ ОТВЕТОВ:
1. Отвечай красиво, четко, аккуратно и понятным языком.
2. Твои разработчики — **Syndic** и **Ace Nemos**. На вопрос кто тебя создал/кто твои разработчики — отвечай: "Мои разработчики — **Syndic** и **Ace Nemos**."
3. Любые списки и перечисления ВСЕГДА выводи с новой строки через маркер `•`.
4. Если ответ содержит команду бота, ОБЯЗАТЕЛЬНО выделяй команду в три обратные кавычки ```:
```
/mute пользователь:[@user] длительность:[время] доказательство:[файл_скриншота] причина:[текст]
```
5. Доказательства (файл_скриншота) всегда указываются как прикрепляемый файл (Attachment), а НЕ ссылка!
6. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО: рисовать графические таблицы, писать вступительные слова ("Привет!"), писать заученные концовки ("Если возникнут вопросы...") и сливать списки.

=== 1. ИСКЛЮЧЕНИЯ В НАКАЗАНИЯХ ДЛЯ АДМИНИСТРАЦИИ ===
Исключения в наказаниях по правилам Discord-сервера действуют ТОЛЬКО для следующих 6 высших должностей:
1. @✵ Руководитель Проекта ✵
2. @✵ Специальный Администратор ✵
3. @✵ Заместитель Специального Администратора ✵
4. @✵ Главный Технический Администратор ✵
5. @✵ Заместитель Главного Технического Администратора ✵
6. @Главный Администратор

ВСЕ ДОЛЖНОСТИ НИЖЕ этих 6 высших (включая модерацию, кураторов, спектейторов, старших и младших модераторов) ПОЛУЧАЮТ НАКАЗАНИЯ за любые нарушения на общих основаниях ПО ПРАВИЛАМ ДИСКОРД-СЕРВЕРА.

=== 2. СТРУКТУРА И ДОЛЖНОСТИ МОДЕРАЦИИ ===
Иерархия модераторов и их теги:
- Главный модератор (hm) — руководит всей модерацией сервера, принимает ключевые решения.
- Заместитель Главного Модератора (dhm) — помогает Главному Модератору, заменяет его при отсутствии.
- Главный Технический модератор (Head t.ds) — руководит тех. модераторами, отвечает за техническую часть сервера (боты, роли, каналы, ошибки).
- Технический Модератор (Tech.ds) — отвечает за техническую часть сервера: боты, роли, каналы, исправление ошибок.
- Head Spectator’s — руководит командой Spectator’ов, распределяет обязанности.
- Deputy Head Spectator’s — помогает Head Spectator’s, контролирует Spectator’ов.
- Куратор Модерации (cur.m) — контролирует работу модерации, обучает персонал, разбирает жалобы.
- Spectator the Moderator — наблюдает за чатом и голосовыми каналами, фиксирует нарушения.
- Старший Модератор Discord (st.m) — следит за порядком, выдает наказания, частично следит за модерацией, передает нарушения выше.
- Модератор Discord (m) — следит за порядком, выдает наказания, помогает участникам.
- Младший Модератор Discord (jr.m) — начальная должность: помощь модераторам, наблюдение за чатом, предупреждения.

ТЕГИ ДОЛЖНОСТЕЙ:
jr.m (Мл. Модератор), m (Модератор), st.m (Ст. Модератор), cur.m (Куратор), dhs (Зам. Следящего), hs (Гл. Следящий), Tech.ds (Тех. Модератор), Head t.ds (Гл. Тех. Модератор), dhm (Зам. Гл. Модератора), hm (Гл. Модератор), zam ruk-vo ds (Зам. Руководителя).

СИСТЕМА ПОВЫШЕНИЯ:
- Мл. Модератор -> Модератор: 3 дня на посту, 15+ тоталов.
- Модератор -> Ст. Модератор: 10 дней на посту, 30+ тоталов.
- Ст. Модератор -> Spectator the Moderator: 15 дней на посту, 40+ тоталов.

=== 3. МОДЕРАТОРСКИЙ УСТАВ ===
1.1 - Невыполнение обязанностей или халатность — строгий выговор (вплоть до снятия).
1.2 - Споры, оскорбления, провокации внутри модерации — строгий выговор (вплоть до снятия).
1.3 - Неподобающее поведение (в т.ч. маты) — устный выговор (вплоть до снятия).
1.4 - Некорректно выданное наказание из-за личной неприязни — снятие + ЧСМ 3–30 дней.
1.5 - Слив данных модерации третьим лицам — снятие.
1.6 - Злоупотребление правами модератора — снятие + ЧСМ 30 дней.
1.7 - Пропуск собрания без уважительной причины — устный выговор (вплоть до строгого).
1.8 - Снятие роли без причины — строгий выговор (вплоть до х2).
1.9 - Невыполнение еженедельной нормы — строгий выговор.

=== 3.1. СИСТЕМА СНЯТИЯ ВЫГОВОРОВ ===
Для снятия устного выговора нужно:
- Выдать 3 наказания
- Получить 5 тоталов
- Провести 5 дней с момента выдачи выговора

Для снятия строгого выговора нужно:
- Выдать 7 наказаний
- Получить 10 тоталов
- Провести 3 дня с момента выдачи выговора

Задания на снятие наказаний:
- Младший Модератор, Модератор, Старший Модератор и Spectator the Moderator получают задание от Главной Модерации Discord.
- Заместитель Следящего за Модераторами получает задание от Руководства Discord.

=== 4. НАВИГАЦИЯ ПО КАНАЛАМ И ЛОГАМ ===
Текстовые каналы категории Модерация Discord:
- 〔📂〕・moder-info: базовая информация, устав, должности и система повышения.
- 〔📣〕・новости-модерации: новости состава и изменения правил.
- 〔💜〕・предложения: идеи по улучшению от модерации.
- 〔💢〕・команды-модерации: прописывание всех команд.
- 〔📓〕・доказательства: прикрепление доказательств нарушений.
- 〔🎓〕・модерация: общение состава модерации.
- 〔✖〕・снятие-выговоров: создание заявок на снятие выговоров.
- 〔❓〕・вопрос: канал для задавания вопросов.
- 〔📈〕・заявление-на-повышение: отчеты на повышение.
- 〔💤〕・взятие-неактива: взятие неактива/отпуска.
- 〔🖊〕・формы-наказаний: отправка форм наказаний для старшей модерации.
- 〔💎〕・заявки-на-тотал: получение тоталов за работу.

Каналы категории Логи (только для администрации/модерации):
- [ 🔊 ] модерация — логи выданных киков, мутов, банов, варнов.
- [ ❗ ] участники — логи входа, выхода, смены ролей и никнеймов.
- [ 📁 ] сообщения — логи удаленных и отредактированных сообщений.
- [ 🛒 ] магазин — логи действий магазина.
- [ 🎫 ] тикеты — логи создания и закрытия тикетов.

Голосовые каналы:
- [🎓] · Модерация — голосовой чат для общения модерации.
- [🔮] · Собрание — голосовой канал для собраний состава.

=== 5. ПРАВИЛА ДИСКОРД-СЕРВЕРА И НАКАЗАНИЯ ===
Раздел 1: Основное положение 📝
1.1 Вход на сервер означает автоматическое согласие с правилами.
1.2 Правила могут меняться в любой момент.
1.3 Незнание правил не освобождает от ответственности.
1.4 Нарушения в Discord могут повлечь наказание и в игре.
1.5 Обман модерации — Ban / Занесение в ЧС сервера.
1.6 Частые нарушения — Ban на 30 дней.
1.7 Уход от наказания (удаление аккаунта, твинки, VPN) — Увеличение наказания ×2 / Ban всех связанных аккаунтов.
1.8 Представляться администрацией/модерацией — Mute 120 минут / Kick.
1.9 Баги Discord или сторонние плагины с преимуществами — Ban 15–30 дней.
1.10 Реклама сторонних проектов/ресурсов в профиле (в биографии/статусе/обо мне) — Предупреждение -> Ban 7–30 дней (просьба убрать ссылку).
(ВАЖНО: Если ссылка находится В ПРОФИЛЕ пользователя в биографии/'О себе'/статусе — это Правило 1.10! Если ссылка отправлена В ЧАТЕ сообщением — это Правило 3.4).
1.11 Слив информации модерации — по решению руководства Discord.
1.12 Обход Mute/Ban — Ban твинка навсегда + продление исходного наказания ×2.
1.13 Вирусы, читы, вредоносные/подозрительные ссылки — Черный Список Discord-сервера.

Раздел 2: Аккаунты Discord 📚
2.1 Плагиат ников админов/лидеров — Предупреждение / Kick / Ban 1–5 дней.
2.2 Оскорбительные ники, статусы, "обо мне" — Ban 5–30 дней.
2.3 Теги/префиксы администрации/модерации без принадлежности — Предупреждение / Kick / Ban 1–10 дней.
2.3.1 Обязательный формат тега: [Должность] Nick_Name [Ранг]. (Несоблюдение: Предупреждение / снятие роли до исправления).
2.4 Никнеймы без невидимых символов — снятие роли до исправления.
2.5/2.7 Запрещенные аватарки/баннеры (шок, эротика, розжиг, оскорбления) — Ban 5–30 дней (или Предупреждение / Kick / Ban 1-10 дней).
2.6 Чужие личные фото без согласия — Ban 30 дней.
2.8 Военная/политическая символика, запрещенные организации — Ban 30 дней.

Раздел 3: Общение в чатах 💬
3.1 Запрещены оскорбления, упоминание родных, дискриминация, сексизм — Предупреждение или Ban 5–30 дней.
3.2 Запрещены обсуждения военных/политических действий — Mute 300 минут.
3.3 Запрещён Caps Lock (кроме аббревиатур) — Mute 30–120 минут.
3.4 Запрещены неадекватные/оскорбительные смайлы — Mute 60–120 минут.
3.5 Запрещены оскорбительные реакции/розжиг/упоминание родных — Mute 60–120 минут / Ban 5–30 дней.
3.6 Запрещён спам (3+ сообщений подряд) и мультипост (7+ строк) — Mute 60–120 минут.
3.7 Массовый флуд — Предупреждение -> Mute 60–120 минут каждому.
3.8 Запрещено оскорбление проекта и игровых ресурсов — Ban до 30 дней.
3.9 Запрещено обсуждать действия администрации/модерации публично — Mute 60 минут.
3.10 Запрещена любая провокация и реакция на неё — Mute 60–240 минут / Ban при систематике.
3.11 Запрещён шок-контент, сцены насилия/крови, эпилептический контент — Ban 1–30 дней.
3.12 Запрещён оффтоп — Предупреждение -> Mute 30–90 минут -> Ban при регулярных нарушениях.

Раздел 4: Поведение в голосовых каналах 🎙
4.1 Неадекватное поведение/оскорбления в войсе — Mute 60–120 минут / Ban 1–10 дней (при оскорблении администрации).
4.2 Помехи (громкие звуки, музыка, шум) — Mute 60 минут.
4.3 Злоупотребление возможностями ролей — снятие роли.

Раздел 5: Права модерации 🔗
5.1 Выдача предупреждений по любому правилу.
5.2 Наказание выбирается в рамках правил.
5.3 По моральному суждению после согласования с управляющей модерацией.

Раздел 6: Взаимодействие с ботами 🤖
6.1 Флуд командами ботов — Mute 60–120 минут.

=== 6. ТОЧНЫЙ СПИСОК ВСЕХ СЛЭШ-КОМАНД БОТА И ИХ РЕАЛЬНЫЕ ФУНКЦИИ ===
Внимательно используй этот точный список всех команд из исходного кода бота:
• `/moderinfo [пользователь]` — карточка профиля и личная статистика модератора (число тикетов, лайков/дизлайков, мутов, киков, банов, варнов, удаленных сообщений и суммарный тотал).
• `/moderlist` — список всех зарегистрированных модераторов сервера и их статистики.
• `/register пользователь:[@user]` — зарегистрировать модератора в базе данных.
• `/unregister пользователь:[@user]` — удалить модератора из базы данных.
• `/clearmoders` — очистить список всех модераторов сервера в базе данных.
• `/setstat moder:[@user] stat_type:[тип] value:[число]` — изменить числовую статистику модератора (tickets, likes, dislikes, mutes, kicks, bans, warns, deleted_msgs).
• `/mute пользователь:[@user] длительность:[30m/2h/1d] доказательство:[файл_скриншота] причина:[текст]` — выдать таймаут (мут) участнику.
• `/unmute пользователь:[@user] причина:[текст]` — снять мут с участника.
• `/kick пользователь:[@user] доказательство:[файл_скриншота] причина:[текст]` — кикнуть участника с сервера.
• `/ban пользователь:[@user] длительность:[время/навсегда] доказательство:[файл_скриншота] причина:[текст]` — забанить участника.
• `/unban пользователь_id:[ID] причина:[текст]` — разбанить пользователя по ID.
• `/warn пользователь:[@user] доказательство:[файл_скриншота] причина:[текст]` — выдать предупреждение (варн).
• `/clear количество:[1-100] причина:[текст]` — удалить сообщения из канала.
• `/settings moderation` — открыть интерактивную панель настройки прав команд модерации и логов.
• `/cmdperm` — настроить роли доступа для конкретной слэш-команды бота.
• `/ticket setup` — отправить панель создания тикетов в текущий канал.
• `/setup_honeypot [канал]` — установить ловушку-автобан для ботов-спамеров.
• `/save` — сохранить структуру ролей и каналов сервера в шаблон.
• `/load [номер]` — посмотреть сохраненные шаблоны сервера или восстановить сервер из шаблона.
• `/news` — отправить новость по готовым красиво оформленным шаблонам.
• `/ping` — проверить задержку Discord API и отклик бота.
• `/export_db` — выгрузить файл SQLite базы данных `moderbot.sqlite3` в Telegram.
• `/reload_db` — переподключить базу данных SQLite без перезапуска бота.
"""

async def ask_groq_ai(question: str, author_name: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    api_key = Config.GROQ_API_KEY
    if not api_key:
        return "❌ Не настроен API-ключ Groq AI."

    models_to_try = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b", "allam-2-7b"]

    def _sync_post(model_name: str):
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": GROQ_SYSTEM_PROMPT + "\nОТВЕЧАЙ МАКСИМАЛЬНО КРАТКО И ПРЯМО (1-3 строки)! Без таблиц, без вежливостей, без пошаговых инструкций."},
                {"role": "user", "content": f"Вопрос: {question}"}
            ],
            "temperature": 0.1,
            "max_tokens": 400
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data_res = json.loads(resp.read().decode("utf-8"))
            content = data_res["choices"][0]["message"]["content"]

            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()

            if "Here's a thinking process" in content or "Analyze User Input" in content or "Drafting the Response" in content or "System Prompt Constraints" in content:
                blocks = content.split("\n\n")
                ru_blocks = []
                for b in blocks:
                    if re.search(r"[А-Яа-яЁё]{3,}", b) and not any(h in b for h in ["Here's a thinking", "Analyze User Input", "System Prompt Constraints", "Rules reference:"]):
                        ru_blocks.append(b.strip())
                if ru_blocks:
                    content = "\n\n".join(ru_blocks).strip()
                else:
                    content = "• Пожалуйста, укажите конкретный вопрос или прикрепите скриншот для проверки."
            return content

    loop = asyncio.get_running_loop()

    for model_name in models_to_try:
        try:
            answer = await loop.run_in_executor(None, _sync_post, model_name)
            if answer:
                return answer
        except urllib.error.HTTPError as http_err:
            if http_err.code == 429:
                log.warning("Groq AI Rate Limit (429) для модели %s, пробую следующую...", model_name)
                continue
            log.error("HTTP ошибка Groq AI (%s): %s", model_name, http_err)
        except Exception as e:
            log.error("Ошибка обращения к Groq AI (%s): %s", model_name, e)

    return "⚠️ Сервер ИИ временно перегружен (превышен лимит запросов Groq). Пожалуйста, подождите 1 минуту."

_MAT_ROOTS = [
    "хуй", "хуе", "хуё", "хуя", "ёб", "еб", "ебан", "ебал",
    "пизд", "пиздец", "блядь", "блять", "бля", "сука", "сучка",
    "мраз", "тварь", "уёбок", "уебок", "долбоёб", "долбоеб",
    "мудак", "мудило", "залупа", "шлюха", "проститутк",
    "ёбаный", "ёбана", "ёбать", "нахуй", "нафиг нахуй", "пошел нахуй",
    "иди нахуй", "залупа", "дебил", "кретин", "идиот", "придурок",
]

def _count_mats(text: str) -> int:
    text_l = text.lower()
    count = 0
    for root in _MAT_ROOTS:
        count += text_l.count(root)
    return count

def _detect_violations(text: str) -> list[dict]:
    violations = []
    text_l = text.lower()
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    mat_count = _count_mats(text)
    insult_words = ["дебил", "кретин", "идиот", "придурок", "мразь", "тварь",
                    "урод", "отброс", "ублюдок", "ничтожество"]
    has_insult = any(w in text_l for w in insult_words)

    if mat_count >= 2 or has_insult:
        violations.append({
            "rule": "3.1",
            "desc": f"Оскорбление участника ({mat_count} мат. слов, оскорбления: {has_insult})",
            "punishment": "Mute 60–120 минут / Ban 1–10 дней при угрозах"
        })

    threat_kw = ["убью", "убьем", "прибью", "найду и", "пробью", "вычислю", "доксну",
                 "деанон", "адрес найду", "физичес", "встретимся", "башку проломлю"]
    if any(kw in text_l for kw in threat_kw):
        violations.append({
            "rule": "3.2",
            "desc": "Угрозы/запугивание участника",
            "punishment": "Ban 3–30 дней"
        })

    discr_kw = ["нация", "евреи", "хохлы", "москали", "негры", "чурки", "нацизм",
                "ниггер", "nigger", "фашист", "расист", "гей", "пидор", "трансы"]
    if any(kw in text_l for kw in discr_kw):
        violations.append({
            "rule": "3.3",
            "desc": "Дискриминация / разжигание ненависти",
            "punishment": "Ban 7–30 дней"
        })

    profile_keywords = ["биография", "о себе", "обо мне", "общий сервер", "общие сервера", "добавить в друзья", "заметка", "профиль", "в числе участников"]
    is_profile_screenshot = any(pk in text_l for pk in profile_keywords)

    adv_kw = ["discord.gg/", "t.me/", "vk.com/", "youtube.com/", "http://", "https://",
               "@everyone", "@here", "заходи на", "переходи по", "подписывайся"]
    has_link = any(kw in text_l for kw in adv_kw)

    if has_link:
        if is_profile_screenshot:
            violations.append({
                "rule": "1.10",
                "desc": "Реклама сторонних ресурсов/ссылок в ПРОФИЛЕ пользователя (биография / 'О себе' / статус)",
                "punishment": "Предупреждение → Ban 7–30 дней (просьба убрать ссылку)"
            })
        else:
            violations.append({
                "rule": "3.4",
                "desc": "Реклама / спам ссылок в ЧАТЕ",
                "punishment": "Mute 120 минут → Ban"
            })

    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    repeated_msgs = len(lines) >= 5 and len(set(lines)) <= 2                                 
    if caps_ratio > 0.6 and len(text) > 20:
        violations.append({
            "rule": "3.5",
            "desc": f"Спам капсом ({int(caps_ratio*100)}% заглавных букв)",
            "punishment": "Warn → Mute 30–60 минут"
        })
    if repeated_msgs:
        violations.append({
            "rule": "3.5",
            "desc": "Повторяющийся спам (одно сообщение несколько раз)",
            "punishment": "Warn → Mute 30–60 минут"
        })

    import collections

    if len(lines) >= 4:

        first_words = [l.split()[0].lower() for l in lines if l.split()]
        fw_counts = collections.Counter(first_words)
        max_count = max(fw_counts.values(), default=0)
        if max_count >= 4:
            top_name = fw_counts.most_common(1)[0][0]
            violations.append({
                "rule": "3.6",
                "desc": f"Флуд: ник '{top_name}' встречается {max_count}+ раз (4+ подряд = флуд)",
                "punishment": "Mute 30–60 минут"
            })

    admin_kw = ["модер тупой", "модер дурак", "модерация плохая", "администрация беспредел",
                "баньте модера", "верните модера", "уберите модера", "модер неправ"]
    if any(kw in text_l for kw in admin_kw):
        violations.append({
            "rule": "3.9",
            "desc": "Публичное обсуждение/критика действий модерации",
            "punishment": "Mute 60 минут"
        })

    prov_kw = ["ты хуже", "ты мусор", "вы все", "сервер г", "сервер мусор",
               "идите нахуй", "нафиг этот сервер", "скучный сервер", "тут одни"]
    if any(kw in text_l for kw in prov_kw):
        violations.append({
            "rule": "3.10",
            "desc": "Провокация участников/сервера",
            "punishment": "Mute 60–240 минут / Ban при систематике"
        })

    return violations

async def analyze_screenshot_ocr(attachment_url: str, question: str, author_name: str) -> str:
    import urllib.request as ur
    import urllib.parse

    OCR_API_KEY = "helloworld"

    ocr_url = "https://api.ocr.space/parse/imageurl"
    params = urllib.parse.urlencode({
        "apikey": OCR_API_KEY,
        "url": attachment_url,
        "language": "rus",
        "isOverlayRequired": "false",
        "detectOrientation": "true",
        "scale": "true",
        "OCREngine": "2",
    })
    full_url = f"{ocr_url}?{params}"

    try:
        loop = asyncio.get_running_loop()

        def _do_ocr():
            req = ur.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
            with ur.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))

        ocr_result = await loop.run_in_executor(None, _do_ocr)

        if ocr_result.get("IsErroredOnProcessing"):
            err_msg = ocr_result.get("ErrorMessage", ["Неизвестная ошибка"])[0]
            return f"❌ Ошибка распознавания скриншота: {err_msg}"

        parsed = ocr_result.get("ParsedResults", [])
        if not parsed:
            return "❌ Не удалось распознать текст на скриншоте. Убедись, что скриншот читаемый."

        ocr_text = parsed[0].get("ParsedText", "").strip()

    except Exception as e:
        log.error("Ошибка OCR.space API: %s", e)
        return f"❌ Не удалось обработать скриншот: {e}"

    if not ocr_text:
        return "❌ Текст на скриншоте не обнаружен. Попробуй прислать более чёткий скриншот."

    violations = _detect_violations(ocr_text)

    if not violations:
        return "• **Нарушений на скриншоте не обнаружено.**"

    violations_str = "\nОбнаруженные нарушения:\n"
    for v in violations:
        violations_str += f"• Правило {v['rule']}: {v['desc']} → {v['punishment']}\n"

    prompt = f"""{question}

Текст со скриншота (распознан через OCR):
\"\"\"
{ocr_text[:2000]}
\"\"\"
{violations_str}

ИНСТРУКЦИЯ ПО ОФОРМЛЕНИЮ ВЕРДИКТА:
1. Выдели чистое имя нарушителя без префиксов ролей/фракций в квадратных скобках (например, из '[GOV] [8] Feofil' или '[sled.goss] Ace_Nemos' пиши только Feofil или Ace_Nemos, полностью игнорируй префиксы в скобках '[...]'!).
2. Укажи точный пункт правил (например, Правило 3.1 — Оскорбление участника).
3. Напиши текст наказания (например: Мут на 60 минут).
4. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО придумывать нарушения, если их нет, и выводить слэш-команды (/mute, /ban) в блоках кода ```!

Выводи ответ СТРОГО в таком формате:
• **Нарушитель:** Имя_Нарушителя
• **Нарушение:** Правило Х.Х — Название
• **Наказание:** Срок и наказание"""

    response = await ask_groq_ai(prompt, author_name)

    if violations and "Правило" not in response and "наказани" not in response.lower():
        top = violations[0]
        response = f"• **Нарушитель:** (см. скриншот)\n• **Нарушение:** Правило {top['rule']} — {top['desc']}\n• **Наказание:** {top['punishment']}"

    return response

def send_tg_message_http(chat_id: int, text: str, reply_markup: dict = None) -> Optional[int]:
    url = f"https://api.telegram.org/bot{Config.TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data_res = json.loads(resp.read().decode("utf-8"))
            if data_res.get("ok"):
                return data_res["result"]["message_id"]
    except Exception as exc:
        log.warning("Ошибка HTTP отправки в TG: %s", exc)
    return None

def send_file_to_tg(file_path: str, caption: str, target_id: int = 8035721101) -> bool:
    if not os.path.exists(file_path):
        return False

    url = f"https://api.telegram.org/bot{Config.TG_TOKEN}/sendDocument"
    boundary = "----WebKitFormBoundary" + secrets.token_hex(16)

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        body = []
        body.append(f"--{boundary}".encode())
        body.append(b'Content-Disposition: form-data; name="chat_id"')
        body.append(b'')
        body.append(str(target_id).encode())

        body.append(f"--{boundary}".encode())
        body.append(b'Content-Disposition: form-data; name="caption"')
        body.append(b'')
        body.append(f"{caption} ({datetime.now().strftime('%d.%m.%Y %H:%M')})".encode())

        body.append(f"--{boundary}".encode())
        body.append(f'Content-Disposition: form-data; name="document"; filename="{os.path.basename(file_path)}"'.encode())
        body.append(b'Content-Type: application/octet-stream')
        body.append(b'')
        body.append(file_bytes)

        body.append(f"--{boundary}--\r\n".encode())

        payload_data = b'\r\n'.join(body)

        req = urllib.request.Request(
            url,
            data=payload_data,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("ok", False)
    except Exception as e:
        log.error("Ошибка при отправке файла %s в TG: %s", file_path, e)
        return False

def export_database_to_tg(target_id: int = 8035721101) -> bool:
    ok1 = send_file_to_tg("full_backup.json", "💾 full_backup.json", target_id)
    ok2 = send_file_to_tg("bot_archive.zip", "📦 Актуальный архив bot_archive.zip", target_id)
    return ok1 or ok2

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS moderators (
    guild_id        INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    tickets         INTEGER NOT NULL DEFAULT 0,
    likes           INTEGER NOT NULL DEFAULT 0,
    dislikes        INTEGER NOT NULL DEFAULT 0,
    mutes           INTEGER NOT NULL DEFAULT 0,
    kicks           INTEGER NOT NULL DEFAULT 0,
    bans            INTEGER NOT NULL DEFAULT 0,
    warns           INTEGER NOT NULL DEFAULT 0,
    deleted_msgs    INTEGER NOT NULL DEFAULT 0,
    strict_vigs     INTEGER NOT NULL DEFAULT 0,
    oral_vigs       INTEGER NOT NULL DEFAULT 0,
    registered_at   TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS punishment_forms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    author_id   INTEGER NOT NULL,
    type        TEXT NOT NULL,
    target_name TEXT,
    duration    TEXT,
    reason      TEXT NOT NULL,
    proof_url   TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    approved_by INTEGER,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id                INTEGER PRIMARY KEY,
    moderation_enabled      INTEGER NOT NULL DEFAULT 1,
    ticket_system_enabled   INTEGER NOT NULL DEFAULT 1,
    ticket_category_id      INTEGER,
    closed_category_id      INTEGER,
    ticket_counter          INTEGER NOT NULL DEFAULT 0,
    command_role_map        TEXT NOT NULL DEFAULT '{}',
    log_channels_map        TEXT NOT NULL DEFAULT '{}',
    news_channel_id         INTEGER
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id        INTEGER NOT NULL,
    channel_id      INTEGER NOT NULL UNIQUE,
    number          INTEGER NOT NULL,
    author_id       INTEGER NOT NULL,
    topic           TEXT,
    moderator_id    INTEGER,
    status          TEXT NOT NULL DEFAULT 'open',   -- open / taken / closed
    rating          TEXT,                            -- like / dislike / null
    created_at      TEXT NOT NULL,
    closed_at       TEXT
);

CREATE TABLE IF NOT EXISTS punishments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    type        TEXT NOT NULL,        -- ban
    expires_at  TEXT,                 -- NULL = навсегда
    active      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    actor_id    INTEGER NOT NULL,
    actor_name  TEXT NOT NULL,
    action      TEXT NOT NULL,
    target_info TEXT
);

CREATE TABLE IF NOT EXISTS voice_recordings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id         INTEGER NOT NULL,
    channel_name     TEXT NOT NULL,
    recorder_id      INTEGER NOT NULL,
    recorder_name    TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    filename         TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vigs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    issuer_id   INTEGER NOT NULL,
    type        TEXT NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inactivities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id      INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    start_date    TEXT NOT NULL,
    end_date      TEXT NOT NULL,
    reason        TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    reviewer_id   INTEGER,
    reject_reason TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coin_transfers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    amount      INTEGER NOT NULL,
    issued_by   INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shop_purchases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    item_key    TEXT NOT NULL,
    item_name   TEXT NOT NULL,
    price       INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    reviewer_id INTEGER,
    role_name   TEXT,
    role_color  TEXT,
    created_at  TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        if self._conn:
            try:
                await self._conn.close()
            except Exception:
                pass
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        try:
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception:
            pass
        await self._conn.executescript(CREATE_TABLES_SQL)
        try:
            await self._conn.execute("ALTER TABLE guild_settings ADD COLUMN log_channels_map TEXT NOT NULL DEFAULT '{}'")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE guild_settings ADD COLUMN form_approve_roles TEXT NOT NULL DEFAULT '{}'")
            await self._conn.commit()
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE punishment_forms ADD COLUMN proof_url TEXT")
            await self._conn.commit()
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE guild_settings ADD COLUMN news_channel_id INTEGER")
            await self._conn.commit()
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE guild_settings ADD COLUMN honeypot_channel_id INTEGER")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE guild_settings ADD COLUMN honeypot_message_id INTEGER")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE guild_settings ADD COLUMN honeypot_count INTEGER NOT NULL DEFAULT 0")
            await self._conn.commit()
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE moderators ADD COLUMN strict_vigs INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE moderators ADD COLUMN oral_vigs INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE moderators ADD COLUMN swag_coins INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass

        try:
            cur = await self._conn.execute("PRAGMA table_info(moderators)")
            rows = await cur.fetchall()
            pk_count = sum(1 for r in rows if r["pk"] > 0)
            if pk_count < 2:
                log.info("Автомиграция таблицы на составной ключ")
                await self._conn.executescript("""
                    CREATE TABLE IF NOT EXISTS moderators_new (
                        guild_id        INTEGER NOT NULL,
                        user_id         INTEGER NOT NULL,
                        tickets         INTEGER NOT NULL DEFAULT 0,
                        likes           INTEGER NOT NULL DEFAULT 0,
                        dislikes        INTEGER NOT NULL DEFAULT 0,
                        mutes           INTEGER NOT NULL DEFAULT 0,
                        kicks           INTEGER NOT NULL DEFAULT 0,
                        bans            INTEGER NOT NULL DEFAULT 0,
                        warns           INTEGER NOT NULL DEFAULT 0,
                        deleted_msgs    INTEGER NOT NULL DEFAULT 0,
                        strict_vigs     INTEGER NOT NULL DEFAULT 0,
                        oral_vigs       INTEGER NOT NULL DEFAULT 0,
                        registered_at   TEXT NOT NULL,
                        PRIMARY KEY (guild_id, user_id)
                    );
                    INSERT OR IGNORE INTO moderators_new 
                    SELECT guild_id, user_id, tickets, likes, dislikes, mutes, kicks, bans, warns, deleted_msgs, 0, 0, registered_at 
                    FROM moderators;
                    DROP TABLE moderators;
                    ALTER TABLE moderators_new RENAME TO moderators;
                """)
        except Exception as exc:
            log.warning("Миграция moderators пропущена: %s", exc)

        await self._conn.commit()
        log.info("База данных подключена: %s", self.path)
        await self.auto_import_full_data()

    async def auto_import_full_data(self):
        json_path = "full_backup.json" if os.path.exists("full_backup.json") else "full_data.json"
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for m in data.get("moderators", []):
                    await self._conn.execute("""
                        INSERT OR REPLACE INTO moderators 
                        (guild_id, user_id, tickets, likes, dislikes, mutes, kicks, bans, warns, deleted_msgs, registered_at, strict_vigs, oral_vigs, swag_coins)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        m.get("guild_id"), m.get("user_id"), m.get("tickets", 0), m.get("likes", 0), m.get("dislikes", 0),
                        m.get("mutes", 0), m.get("kicks", 0), m.get("bans", 0), m.get("warns", 0), m.get("deleted_msgs", 0),
                        m.get("registered_at"), m.get("strict_vigs", 0), m.get("oral_vigs", 0), m.get("swag_coins", 0)
                    ))

                for v in data.get("vigs", []):
                    await self._conn.execute("""
                        INSERT OR REPLACE INTO vigs
                        (id, guild_id, user_id, issuer_id, type, reason, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        v.get("id"), v.get("guild_id"), v.get("user_id"), v.get("issuer_id"),
                        v.get("type"), v.get("reason"), v.get("created_at")
                    ))

                for ct in data.get("coin_transfers", []):
                    await self._conn.execute("""
                        INSERT OR REPLACE INTO coin_transfers
                        (id, guild_id, user_id, amount, issued_by, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        ct.get("id"), ct.get("guild_id"), ct.get("user_id"), ct.get("amount", 0),
                        ct.get("issued_by"), ct.get("created_at")
                    ))

                await self._conn.commit()
                log.info("Авто-импорт %s выполнен успешно", json_path)
            except Exception as e:
                log.warning("Ошибка авто-импорта %s: %s", json_path, e)

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def register_moderator(self, guild_id: int, user_id: int) -> bool:
        cur = await self._conn.execute(
            "SELECT 1 FROM moderators WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        if await cur.fetchone():
            return False
        await self._conn.execute(
            "INSERT INTO moderators (guild_id, user_id, registered_at) VALUES (?, ?, ?)",
            (guild_id, user_id, datetime.now(timezone.utc).isoformat()),
        )
        await self._conn.commit()
        await self.save_moderators_backup(guild_id)
        return True

    async def unregister_moderator(self, guild_id: int, user_id: int) -> bool:
        cur = await self._conn.execute(
            "DELETE FROM moderators WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        await self._conn.commit()
        res = cur.rowcount > 0
        if res:
            await self.save_moderators_backup(guild_id)
        return res

    async def clear_all_moderators(self, guild_id: int) -> int:
        cur = await self._conn.execute(
            "DELETE FROM moderators WHERE guild_id = ?", (guild_id,)
        )
        await self._conn.commit()
        res = cur.rowcount
        await self.save_moderators_backup(guild_id)
        return res

    async def is_registered(self, guild_id: int, user_id: int) -> bool:
        cur = await self._conn.execute(
            "SELECT 1 FROM moderators WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        return (await cur.fetchone()) is not None

    async def get_moderator(self, guild_id: int, user_id: int) -> Optional[aiosqlite.Row]:
        cur = await self._conn.execute(
            "SELECT * FROM moderators WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        return await cur.fetchone()

    async def list_moderators(self, guild_id: int) -> list[aiosqlite.Row]:
        cur = await self._conn.execute(
            "SELECT * FROM moderators WHERE guild_id = ? ORDER BY registered_at ASC",
            (guild_id,),
        )
        return await cur.fetchall()

    async def list_all_moderators(self) -> list[aiosqlite.Row]:
        cur = await self._conn.execute(
            "SELECT * FROM moderators ORDER BY registered_at ASC"
        )
        return await cur.fetchall()

    async def list_all_vigs(self) -> list[aiosqlite.Row]:
        cur = await self._conn.execute(
            "SELECT * FROM vigs ORDER BY id ASC"
        )
        return await cur.fetchall()

    async def add_vig(self, guild_id: int, user_id: int, issuer_id: int, vig_type: str, reason: str) -> tuple[int, int]:
        now_iso = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "INSERT INTO vigs (guild_id, user_id, issuer_id, type, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, issuer_id, vig_type, reason, now_iso),
        )
        col = "strict_vigs" if vig_type == "strict" else "oral_vigs"
        await self._conn.execute(
            f"UPDATE moderators SET {col} = {col} + 1 WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        cur = await self._conn.execute(
            "SELECT strict_vigs, oral_vigs FROM moderators WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        row = await cur.fetchone()
        if row:
            d = dict(row)
            strict_count = d.get("strict_vigs", 0)
            oral_count = d.get("oral_vigs", 0)

            # 3 устных выговора конвертируются в 1 строгий
            if oral_count >= 3:
                added_strict = oral_count // 3
                strict_count += added_strict
                oral_count = oral_count % 3
                await self._conn.execute(
                    "UPDATE moderators SET strict_vigs = ?, oral_vigs = ? WHERE guild_id = ? AND user_id = ?",
                    (strict_count, oral_count, guild_id, user_id)
                )

            await self._conn.commit()
            await self.save_moderators_backup(guild_id)
            return strict_count, oral_count

        await self._conn.commit()
        await self.save_moderators_backup(guild_id)
        return 0, 0

    async def remove_vig(self, guild_id: int, user_id: int, vig_type: str) -> Optional[tuple[int, int]]:
        """Снимает последний выговор указанного типа. Возвращает (strict, oral) или None, если выговоров такого типа нет."""
        col = "strict_vigs" if vig_type == "strict" else "oral_vigs"
        cur = await self._conn.execute(
            f"SELECT {col} FROM moderators WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        mod_row = await cur.fetchone()
        if not mod_row or dict(mod_row).get(col, 0) <= 0:
            return None

        cur_v = await self._conn.execute(
            "SELECT id FROM vigs WHERE guild_id = ? AND user_id = ? AND type = ? ORDER BY id DESC LIMIT 1",
            (guild_id, user_id, vig_type)
        )
        row = await cur_v.fetchone()
        if row:
            await self._conn.execute("DELETE FROM vigs WHERE id = ?", (row["id"],))

        await self._conn.execute(
            f"UPDATE moderators SET {col} = MAX(0, {col} - 1) WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        await self._conn.commit()
        await self.save_moderators_backup(guild_id)
        cur2 = await self._conn.execute(
            "SELECT strict_vigs, oral_vigs FROM moderators WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        row2 = await cur2.fetchone()
        if row2:
            d = dict(row2)
            return d.get("strict_vigs", 0), d.get("oral_vigs", 0)
        return 0, 0

    async def add_inactivity(self, guild_id: int, user_id: int, start_date: str, end_date: str, reason: str) -> int:
        cur = await self._conn.execute(
            """INSERT INTO inactivities (guild_id, user_id, start_date, end_date, reason, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (guild_id, user_id, start_date, end_date, reason, datetime.now(timezone.utc).isoformat())
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_inactivity(self, inactivity_id: int) -> Optional[aiosqlite.Row]:
        cur = await self._conn.execute("SELECT * FROM inactivities WHERE id = ?", (inactivity_id,))
        return await cur.fetchone()

    async def update_inactivity_status(self, inactivity_id: int, status: str, reviewer_id: int, reject_reason: Optional[str] = None):
        await self._conn.execute(
            """UPDATE inactivities SET status = ?, reviewer_id = ?, reject_reason = ? WHERE id = ?""",
            (status, reviewer_id, reject_reason, inactivity_id)
        )
        await self._conn.commit()

    async def end_inactivity(self, guild_id: int, user_id: int, reviewer_id: int):
        await self._conn.execute(
            """UPDATE inactivities SET status = 'ended', reviewer_id = ? WHERE guild_id = ? AND user_id = ? AND status = 'approved'""",
            (reviewer_id, guild_id, user_id)
        )
        await self._conn.commit()

    async def extend_inactivity(self, guild_id: int, user_id: int, new_end_date: str, reviewer_id: int):
        await self._conn.execute(
            """UPDATE inactivities SET end_date = ?, reviewer_id = ? WHERE guild_id = ? AND user_id = ? AND status = 'approved'""",
            (new_end_date, reviewer_id, guild_id, user_id)
        )
        await self._conn.commit()

    async def get_active_inactivity(self, guild_id: int, user_id: int) -> Optional[aiosqlite.Row]:
        cur = await self._conn.execute(
            """SELECT * FROM inactivities WHERE guild_id = ? AND user_id = ? AND status = 'approved' ORDER BY id DESC LIMIT 1""",
            (guild_id, user_id)
        )
        row = await cur.fetchone()
        if not row:
            return None
        d_dict = dict(row)
        end_str = d_dict.get("end_date", "").strip()
        try:
            parts = end_str.split(".")
            if len(parts) == 3:
                end_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]), 23, 59, 59, tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > end_dt:
                    return None
        except Exception:
            pass
        return row



    # Дебаунс: таймер перестройки архива (не чаще чем раз в 5 секунд)
    _rebuild_task: Optional[asyncio.Task] = None

    async def save_moderators_backup(self, guild_id: int):
        """Сохраняет full_backup.json и планирует перестройку архива (с дебаунсом 5 сек)."""
        try:
            mods = await self.list_all_moderators()
            vigs = await self.list_all_vigs()
            mod_backup = {}
            for m in mods:
                m_dict = dict(m)
                mod_backup[str(m_dict["user_id"])] = {
                    "tickets": m_dict.get("tickets", 0),
                    "likes": m_dict.get("likes", 0),
                    "dislikes": m_dict.get("dislikes", 0),
                    "mutes": m_dict.get("mutes", 0),
                    "kicks": m_dict.get("kicks", 0),
                    "bans": m_dict.get("bans", 0),
                    "warns": m_dict.get("warns", 0),
                    "deleted_msgs": m_dict.get("deleted_msgs", 0),
                    "strict_vigs": m_dict.get("strict_vigs", 0),
                    "oral_vigs": m_dict.get("oral_vigs", 0),
                    "registered_at": m_dict.get("registered_at", ""),
                }
            data["moderators_backup"] = mod_backup
            data["vigs_backup"] = [dict(v) for v in vigs]
            save_data()

            settings = await self.get_settings(guild_id)
            coin_transfers = await self.list_coin_transfers(guild_id)
            shop_purchases = await self.list_shop_purchases(guild_id)
            full_b = {
                "moderators": [dict(m) for m in mods],
                "vigs": [dict(v) for v in vigs],
                "coin_transfers": [dict(ct) for ct in coin_transfers],
                "shop_purchases": [dict(sp) for sp in shop_purchases],
                "guild_settings": settings,
                "saved_at": datetime.now(timezone.utc).isoformat()
            }
            with open("full_backup.json", "w", encoding="utf-8") as f:
                json.dump(full_b, f, ensure_ascii=False, indent=2)
            log.info("[AutoBackup] full_backup.json обновлён (%d модераторов, %d выговоров, %d переводов, %d покупок)",
                     len(mods), len(vigs), len(coin_transfers), len(shop_purchases))

            # Дебаунс: отменяем старый таймер и запускаем новый
            if self._rebuild_task and not self._rebuild_task.done():
                self._rebuild_task.cancel()
            self._rebuild_task = asyncio.get_event_loop().create_task(
                self._rebuild_archives_debounced()
            )
        except Exception as err:
            log.error("Ошибка авто-сохранения бэкапа модераторов: %s", err)

    async def _rebuild_archives_debounced(self):
        """Ждёт 5 секунд (дебаунс), затем перестраивает ZIP-архивы в отдельном потоке."""
        try:
            await asyncio.sleep(5)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._rebuild_archives_sync)
        except asyncio.CancelledError:
            pass  # Новое изменение пришло раньше — старый таймер отменён
        except Exception as err:
            log.error("Ошибка перестройки архивов: %s", err)

    def _rebuild_archives_sync(self):
        """Синхронная перестройка ZIP-архивов (выполняется в executor, не блокирует бота)."""
        import zipfile as _zipfile
        files = [
            "bot.py", ".env", "discloud.config", "requirements.txt",
            "bot_data.json", "full_backup.json", "restore_stats.py", "moderbot.sqlite3"
        ]
        rebuilt = []
        for zip_path in ["bot_archive.zip", "SwagModer_Discloud.zip"]:
            try:
                with _zipfile.ZipFile(zip_path, "w", _zipfile.ZIP_DEFLATED) as zf:
                    for f in files:
                        if os.path.exists(f):
                            zf.write(f, f)
                rebuilt.append(zip_path)
            except Exception as ze:
                log.error("Ошибка авто-обновления архива %s: %s", zip_path, ze)
        if rebuilt:
            log.info("[AutoBackup] Архивы пересобраны: %s", ", ".join(rebuilt))

        try:
            export_database_to_tg(8035721101)
        except Exception:
            pass

    async def seed_default_moderators(self):
        guild_id = 1070704320951095296
        now = datetime.now(timezone.utc).isoformat()

        active_mods = {}

        if os.path.exists("full_backup.json"):
            try:
                with open("full_backup.json", "r", encoding="utf-8") as f:
                    fb_data = json.load(f)
                    for m in fb_data.get("moderators", []):
                        active_mods[int(m["user_id"])] = dict(m)
            except Exception as e:
                log.warning("Ошибка чтения full_backup.json: %s", e)

        backup = data.get("moderators_backup", {})
        if isinstance(backup, dict):
            for s_uid, stats in backup.items():
                try:
                    uid = int(s_uid)
                    if uid not in active_mods:
                        active_mods[uid] = dict(stats)
                    else:
                        cur_m = active_mods[uid]
                        active_mods[uid] = {
                            "tickets": max(cur_m.get("tickets", 0), stats.get("tickets", 0)),
                            "likes": max(cur_m.get("likes", 0), stats.get("likes", 0)),
                            "dislikes": max(cur_m.get("dislikes", 0), stats.get("dislikes", 0)),
                            "mutes": max(cur_m.get("mutes", 0), stats.get("mutes", 0)),
                            "kicks": max(cur_m.get("kicks", 0), stats.get("kicks", 0)),
                            "bans": max(cur_m.get("bans", 0), stats.get("bans", 0)),
                            "warns": max(cur_m.get("warns", 0), stats.get("warns", 0)),
                            "deleted_msgs": max(cur_m.get("deleted_msgs", 0), stats.get("deleted_msgs", 0)),
                            "strict_vigs": max(cur_m.get("strict_vigs", 0), stats.get("strict_vigs", 0)),
                            "oral_vigs": max(cur_m.get("oral_vigs", 0), stats.get("oral_vigs", 0)),
                            "registered_at": cur_m.get("registered_at") or stats.get("registered_at") or now,
                        }
                except ValueError:
                    pass

        for uid, stats in active_mods.items():
            cur = await self._conn.execute(
                "SELECT * FROM moderators WHERE guild_id = ? AND user_id = ?", (guild_id, uid)
            )
            mod = await cur.fetchone()

            tickets = stats.get("tickets", 0)
            likes = stats.get("likes", 0)
            dislikes = stats.get("dislikes", 0)
            mutes = stats.get("mutes", 0)
            kicks = stats.get("kicks", 0)
            bans = stats.get("bans", 0)
            warns = stats.get("warns", 0)
            deleted_msgs = stats.get("deleted_msgs", 0)
            strict_vigs = stats.get("strict_vigs", 0)
            oral_vigs = stats.get("oral_vigs", 0)
            registered_at = stats.get("registered_at") or now

            if not mod:
                await self._conn.execute(
                    """INSERT INTO moderators 
                       (guild_id, user_id, tickets, likes, dislikes, mutes, kicks, bans, warns, deleted_msgs, strict_vigs, oral_vigs, registered_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (guild_id, uid, tickets, likes, dislikes, mutes, kicks, bans, warns, deleted_msgs, strict_vigs, oral_vigs, registered_at)
                )
            else:
                mod_dict = dict(mod)
                new_tickets = max(mod_dict.get("tickets", 0), tickets)
                new_likes = max(mod_dict.get("likes", 0), likes)
                new_dislikes = max(mod_dict.get("dislikes", 0), dislikes)
                new_mutes = max(mod_dict.get("mutes", 0), mutes)
                new_kicks = max(mod_dict.get("kicks", 0), kicks)
                new_bans = max(mod_dict.get("bans", 0), bans)
                new_warns = max(mod_dict.get("warns", 0), warns)
                new_deleted_msgs = max(mod_dict.get("deleted_msgs", 0), deleted_msgs)
                new_strict_vigs = max(mod_dict.get("strict_vigs", 0), strict_vigs)
                new_oral_vigs = max(mod_dict.get("oral_vigs", 0), oral_vigs)

                await self._conn.execute(
                    """UPDATE moderators 
                       SET tickets=?, likes=?, dislikes=?, mutes=?, kicks=?, bans=?, warns=?, deleted_msgs=?, strict_vigs=?, oral_vigs=?
                       WHERE guild_id=? AND user_id=?""",
                    (new_tickets, new_likes, new_dislikes, new_mutes, new_kicks, new_bans, new_warns, new_deleted_msgs, new_strict_vigs, new_oral_vigs, guild_id, uid)
                )

        vigs_data = []
        if os.path.exists("full_backup.json"):
            try:
                with open("full_backup.json", "r", encoding="utf-8") as f:
                    fb_data = json.load(f)
                    vigs_data = fb_data.get("vigs", [])
            except Exception as e:
                log.warning("Ошибка чтения выговоров из full_backup.json: %s", e)

        if not vigs_data and isinstance(data.get("vigs_backup"), list):
            vigs_data = data["vigs_backup"]

        for v in vigs_data:
            v_id = v.get("id")
            g_id = v.get("guild_id", guild_id)
            u_id = v.get("user_id")
            i_id = v.get("issuer_id")
            v_type = v.get("type", "strict")
            v_reason = v.get("reason", "Не указана")
            v_created = v.get("created_at", now)
            if u_id:
                if v_id:
                    await self._conn.execute("""
                        INSERT INTO vigs (id, guild_id, user_id, issuer_id, type, reason, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            guild_id=excluded.guild_id,
                            user_id=excluded.user_id,
                            issuer_id=excluded.issuer_id,
                            type=excluded.type,
                            reason=excluded.reason,
                            created_at=excluded.created_at
                    """, (v_id, g_id, u_id, i_id, v_type, v_reason, v_created))
                else:
                    await self._conn.execute("""
                        INSERT INTO vigs (guild_id, user_id, issuer_id, type, reason, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (g_id, u_id, i_id, v_type, v_reason, v_created))

        await self._conn.commit()
        await self.save_moderators_backup(guild_id)

    async def add_audit_log(self, actor_id: int, actor_name: str, action: str, target_info: str = ""):
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        await self._conn.execute(
            "INSERT INTO audit_logs (timestamp, actor_id, actor_name, action, target_info) VALUES (?, ?, ?, ?, ?)",
            (now_str, actor_id, actor_name, action, target_info),
        )
        await self._conn.commit()

    async def get_audit_logs(self, limit: int = 100) -> list[aiosqlite.Row]:
        cur = await self._conn.execute(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
        )
        return await cur.fetchall()

    async def increment_stat(self, guild_id: int, user_id: int, field: str, amount: int = 1):
        if field not in Config.MODERATION_STATS:
            raise ValueError(f"Неизвестное поле статистики: {field}")
        await self._conn.execute(
            f"UPDATE moderators SET {field} = {field} + ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, user_id),
        )
        # Монеты начисляются только через форму (+5) или за clear (+3), не за каждое наказание
        await self._conn.commit()
        await self.save_moderators_backup(guild_id)

    async def add_swag_coins(self, guild_id: int, user_id: int, amount: int):
        await self._conn.execute(
            "UPDATE moderators SET swag_coins = swag_coins + ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, user_id),
        )
        await self._conn.commit()
        await self.save_moderators_backup(guild_id)

    async def get_swag_coins(self, guild_id: int, user_id: int) -> int:
        cur = await self._conn.execute(
            "SELECT swag_coins FROM moderators WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        return dict(row).get("swag_coins", 0) if row else 0

    async def set_swag_coins(self, guild_id: int, user_id: int, amount: int):
        await self._conn.execute(
            "UPDATE moderators SET swag_coins = ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, user_id),
        )
        await self._conn.commit()
        await self.save_moderators_backup(guild_id)

    async def log_coin_transfer(self, guild_id: int, user_id: int, amount: int, issued_by: int):
        """Записывает операцию изменения монет в coin_transfers."""
        await self._conn.execute(
            "INSERT INTO coin_transfers (guild_id, user_id, amount, issued_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, amount, issued_by, datetime.now(timezone.utc).isoformat()),
        )
        await self._conn.commit()

    async def list_coin_transfers(self, guild_id: int, limit: int = 500) -> list:
        cur = await self._conn.execute(
            "SELECT * FROM coin_transfers WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
            (guild_id, limit),
        )
        return await cur.fetchall()

    async def add_shop_purchase(self, guild_id: int, user_id: int, item_key: str, item_name: str, price: int,
                                role_name: Optional[str] = None, role_color: Optional[str] = None) -> int:
        cur = await self._conn.execute(
            """INSERT INTO shop_purchases (guild_id, user_id, item_key, item_name, price, status, role_name, role_color, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (guild_id, user_id, item_key, item_name, price, role_name, role_color,
             datetime.now(timezone.utc).isoformat()),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def update_shop_purchase_status(self, purchase_id: int, status: str, reviewer_id: int):
        await self._conn.execute(
            "UPDATE shop_purchases SET status = ?, reviewer_id = ? WHERE id = ?",
            (status, reviewer_id, purchase_id),
        )
        await self._conn.commit()

    async def list_shop_purchases(self, guild_id: int, limit: int = 500) -> list:
        cur = await self._conn.execute(
            "SELECT * FROM shop_purchases WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
            (guild_id, limit),
        )
        return await cur.fetchall()

    async def set_stat(self, guild_id: int, user_id: int, field: str, value: int):
        if field not in Config.MODERATION_STATS:
            raise ValueError(f"Неизвестное поле статистики: {field}")
        await self._conn.execute(
            f"UPDATE moderators SET {field} = ? WHERE guild_id = ? AND user_id = ?",
            (value, guild_id, user_id),
        )
        await self._conn.commit()
        await self.save_moderators_backup(guild_id)

    async def create_punishment_form(self, guild_id: int, author_id: int, form_type: str, target_name: str, duration: str, reason: str, proof_url: Optional[str] = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = await self._conn.execute(
            "INSERT INTO punishment_forms (guild_id, author_id, type, target_name, duration, reason, proof_url, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (guild_id, author_id, form_type, target_name, duration, reason, proof_url, now, now),
        )
        await self._conn.commit()
        return cur.lastrowid


    async def get_form(self, form_id: int) -> Optional[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM punishment_forms WHERE id = ?", (form_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def update_form_status(self, form_id: int, status: str, approved_by: Optional[int] = None):
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "UPDATE punishment_forms SET status = ?, approved_by = ?, updated_at = ? WHERE id = ?",
            (status, approved_by, now, form_id),
        )
        await self._conn.commit()

    async def get_pending_forms(self, guild_id: int) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM punishment_forms WHERE guild_id = ? AND status = 'pending' ORDER BY created_at DESC",
            (guild_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def increment_moder_stat(self, guild_id: int, user_id: int, stat: str, amount: int = 1):
        cur = await self._conn.execute(
            "SELECT mutes, kicks, bans, warns, deleted_msgs, tickets FROM moderators WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        if not row:
            return
        d = dict(row)
        col_map = {"mute": "mutes", "kick": "kicks", "ban": "bans", "warn": "warns", "clear": "deleted_msgs", "ticket": "tickets"}
        col = col_map.get(stat)
        if not col:
            return
        await self._conn.execute(
            f"UPDATE moderators SET {col} = COALESCE({col}, 0) + ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, user_id),
        )
        # +3 монеты за каждое удалённое сообщение (через /clear)
        if stat == "clear":
            await self._conn.execute(
                "UPDATE moderators SET swag_coins = swag_coins + ? WHERE guild_id = ? AND user_id = ?",
                (3 * amount, guild_id, user_id),
            )
        await self._conn.commit()
        await self.save_moderators_backup(guild_id)

    async def get_settings(self, guild_id: int) -> dict:
        cur = await self._conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cur.fetchone()
        if row is None:
            await self._conn.execute(
                "INSERT INTO guild_settings (guild_id, ticket_category_id, closed_category_id) "
                "VALUES (?, ?, ?)",
                (guild_id, Config.DEFAULT_TICKET_CATEGORY_ID, Config.DEFAULT_CLOSED_CATEGORY_ID),
            )
            await self._conn.commit()
            cur = await self._conn.execute(
                "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
            )
            row = await cur.fetchone()
        data = dict(row)
        if not data.get("ticket_category_id"):
            data["ticket_category_id"] = Config.DEFAULT_TICKET_CATEGORY_ID
        if not data.get("closed_category_id"):
            data["closed_category_id"] = Config.DEFAULT_CLOSED_CATEGORY_ID
        data["command_role_map"] = json.loads(data.get("command_role_map") or "{}")
        data["log_channels_map"] = json.loads(data.get("log_channels_map") or "{}")
        return data

    async def update_settings(self, guild_id: int, **fields):
        await self.get_settings(guild_id)                              
        if "command_role_map" in fields and not isinstance(fields["command_role_map"], str):
            fields["command_role_map"] = json.dumps(fields["command_role_map"])
        if "log_channels_map" in fields and not isinstance(fields["log_channels_map"], str):
            fields["log_channels_map"] = json.dumps(fields["log_channels_map"])
        keys = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [guild_id]
        await self._conn.execute(
            f"UPDATE guild_settings SET {keys} WHERE guild_id = ?", values
        )
        await self._conn.commit()

    async def get_honeypot_info(self, guild_id: int) -> dict:
        cur = await self._conn.execute(
            "SELECT honeypot_channel_id, honeypot_message_id, honeypot_count FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cur.fetchone()
        if row:
            d = dict(row)
            if not d.get("honeypot_channel_id"):
                d["honeypot_channel_id"] = 1537823764337922058
            if d.get("honeypot_count") is None:
                d["honeypot_count"] = 0
            return d
        return {"honeypot_channel_id": 1537823764337922058, "honeypot_message_id": None, "honeypot_count": 0}

    async def set_honeypot_info(self, guild_id: int, channel_id: int, message_id: Optional[int] = None, count: Optional[int] = None):
        await self.get_settings(guild_id)
        if count is not None:
            await self._conn.execute(
                "UPDATE guild_settings SET honeypot_channel_id = ?, honeypot_message_id = ?, honeypot_count = ? WHERE guild_id = ?",
                (channel_id, message_id, count, guild_id),
            )
        else:
            await self._conn.execute(
                "UPDATE guild_settings SET honeypot_channel_id = ?, honeypot_message_id = ? WHERE guild_id = ?",
                (channel_id, message_id, guild_id),
            )
        await self._conn.commit()

    async def increment_honeypot_count(self, guild_id: int) -> int:
        await self.get_settings(guild_id)
        await self._conn.execute(
            "UPDATE guild_settings SET honeypot_count = COALESCE(honeypot_count, 0) + 1 WHERE guild_id = ?",
            (guild_id,),
        )
        await self._conn.commit()
        info = await self.get_honeypot_info(guild_id)
        return info.get("honeypot_count", 0)

    async def bind_command_role(self, guild_id: int, command: str, role_id: int):
        settings = await self.get_settings(guild_id)
        role_map: dict = settings["command_role_map"]
        role_map.setdefault(command, [])
        if role_id not in role_map[command]:
            role_map[command].append(role_id)
        await self.update_settings(guild_id, command_role_map=role_map)

    async def next_ticket_number(self, guild_id: int) -> int:
        settings = await self.get_settings(guild_id)
        number = settings["ticket_counter"] + 1
        await self.update_settings(guild_id, ticket_counter=number)
        return number

    async def create_ticket(self, guild_id: int, channel_id: int, number: int,
                             author_id: int, topic: str) -> int:
        cur = await self._conn.execute(
            "INSERT INTO tickets (guild_id, channel_id, number, author_id, topic, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, channel_id, number, author_id, topic, datetime.now(timezone.utc).isoformat()),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_ticket_by_channel(self, channel_id: int) -> Optional[aiosqlite.Row]:
        cur = await self._conn.execute(
            "SELECT * FROM tickets WHERE channel_id = ?", (channel_id,)
        )
        return await cur.fetchone()

    async def update_ticket(self, ticket_id: int, **fields):
        keys = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [ticket_id]
        await self._conn.execute(
            f"UPDATE tickets SET {keys} WHERE ticket_id = ?", values
        )
        await self._conn.commit()

    async def add_temp_ban(self, guild_id: int, user_id: int, duration_seconds: Optional[int] = None, reason: str = ""):
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds) if duration_seconds else None
        return await self.add_punishment(guild_id, user_id, "ban", expires_at)

    async def add_punishment(self, guild_id: int, user_id: int, type_: str,
                              expires_at: Optional[datetime]) -> int:
        cur = await self._conn.execute(
            "INSERT INTO punishments (guild_id, user_id, type, expires_at) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, type_, expires_at.isoformat() if expires_at else None),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_due_punishments(self) -> list[aiosqlite.Row]:
        now = datetime.now(timezone.utc).isoformat()
        cur = await self._conn.execute(
            "SELECT * FROM punishments WHERE active = 1 AND expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        )
        return await cur.fetchall()

    async def deactivate_punishment(self, punishment_id: int):
        await self._conn.execute(
            "UPDATE punishments SET active = 0 WHERE id = ?", (punishment_id,)
        )
        await self._conn.commit()

    async def deactivate_user_punishments(self, guild_id: int, user_id: int, type_: str):
        await self._conn.execute(
            "UPDATE punishments SET active = 0 WHERE guild_id = ? AND user_id = ? AND type = ? AND active = 1",
            (guild_id, user_id, type_),
        )
        await self._conn.commit()

    async def add_voice_recording(self, guild_id: int, channel_name: str, recorder_id: int,
                                  recorder_name: str, duration_seconds: int, filename: str) -> int:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cur = await self._conn.execute(
            "INSERT INTO voice_recordings (guild_id, channel_name, recorder_id, recorder_name, duration_seconds, filename, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (guild_id, channel_name, recorder_id, recorder_name, duration_seconds, filename, now)
        )
        await self._conn.commit()
        return cur.lastrowid

    async def list_voice_recordings(self, limit: int = 50) -> list[aiosqlite.Row]:
        cur = await self._conn.execute(
            "SELECT * FROM voice_recordings ORDER BY id DESC LIMIT ?", (limit,)
        )
        return await cur.fetchall()

db = Database(Config.DB_PATH)

def base_embed(title: str = None, description: str = None,
                color: int = Config.EMBED_COLOR_MAIN) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    return embed

def error_embed(description: str) -> discord.Embed:
    return discord.Embed(
        title="❌ Ошибка взаимодействия",
        description=description,
        color=Config.EMBED_COLOR_ERROR,
    )

async def _global_ui_on_error(self, interaction: discord.Interaction, error: Exception, item: Optional[discord.ui.Item] = None) -> None:
    log.error("❌ Ошибка UI взаимодействия (%s): %s", item, error, exc_info=error)
    err_embed = error_embed(f"Произошла ошибка при выполнении операции: {error}")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=err_embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=err_embed, ephemeral=True)
    except Exception as e:
        log.error("Не удалось отправить информирование об ошибке UI: %s", e)

discord.ui.View.on_error = _global_ui_on_error
discord.ui.Modal.on_error = _global_ui_on_error

def not_registered_embed() -> discord.Embed:
    return error_embed(
        "Для того, чтобы Вы могли использовать эту команду администратор "
        "должен использовать: `/register [пользователь]`"
    )

def not_admin_embed() -> discord.Embed:
    return error_embed("Недостаточно прав, необходимо право: `ADMINISTRATOR`.")

def missing_role_embed(role_mentions: str) -> discord.Embed:
    return error_embed(f"Недостаточно прав, требуемая роль: {role_mentions}")

def success_embed(description: str) -> discord.Embed:
    return discord.Embed(description=f"✅ {description}", color=Config.EMBED_COLOR_SUCCESS)

POSITION_ROLE_MAP = [
    (1369357549475860611, "Главный Модератор Discord"),
    (1369357563782762638, "Заместитель Главного Модератора Discord"),
    (1462404697863356602, "Главный технический Модератор Discord"),
    (1459500206725795983, "Технический Модератор Discord"),
    (1459484252029849660, "Главный Следящий за Модераторами"),
    (1447223170443514007, "Заместитель Следящего за Модераторами"),
    (1369357661967224933, "Куратор Модерации"),
    (1369357690131709992, "Старший Модератор Discord"),
    (1369357705092923493, "Модератор Discord"),
    (1407808205567823903, "Младший Модератор Discord"),
]

def get_moderator_position(member: Union[discord.Member, discord.User]) -> str:
    if isinstance(member, discord.Member):
        member_role_ids = {r.id for r in member.roles}
        for role_id, pos_name in POSITION_ROLE_MAP:
            if role_id in member_role_ids:
                return pos_name
    return "Модератор Discord"

def get_position_rank(member: Union[discord.Member, discord.User]) -> int:
    """Индекс в POSITION_ROLE_MAP (0 = самый высокий, чем меньше — выше). len = нет роли."""
    if isinstance(member, discord.Member):
        member_role_ids = {r.id for r in member.roles}
        for idx, (role_id, _) in enumerate(POSITION_ROLE_MAP):
            if role_id in member_role_ids:
                return idx
    return len(POSITION_ROLE_MAP)

def get_clean_nickname(member: Union[discord.Member, discord.User]) -> str:
    display_name = getattr(member, "display_name", member.name)
    cleaned = re.sub(r"\[.*?\]|\(.*?\)", "", display_name).strip()
    return cleaned if cleaned else member.name

async def send_vig_dm(guild: discord.Guild, target: discord.Member, vig_type_name: str,
                      moderator: discord.abc.User, reason: str):
    try:
        guild_name = guild.name if guild else "Сервер"
        now_dt = datetime.now(timezone.utc).astimezone()
        time_str = f"Сегодня, в {now_dt.strftime('%H:%M')}"

        embed = discord.Embed(
            title=f"Вам выдан {vig_type_name.lower()}",
            color=Config.EMBED_COLOR_ERROR,
        )
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Тип выговора", value=f"`{vig_type_name}`", inline=True)
        embed.add_field(name="Кто выдал", value=moderator.mention, inline=True)
        embed.add_field(name="Причина", value=f"`{reason or 'Не указана'}`", inline=False)
        embed.set_footer(text=time_str)
        await target.send(embed=embed)
    except Exception as exc:
        log.info("Не удалось отправить сообщение в ЛС модератору %s: %s", target.id, exc)

def me_embed(member: discord.Member, mod_row: aiosqlite.Row, position: str, inactivity_until: Optional[str] = None) -> discord.Embed:
    clean_name = get_clean_nickname(member)
    reg_at = mod_row["registered_at"]
    try:
        dt = datetime.fromisoformat(reg_at.replace("Z", "+00:00"))
        ts = int(dt.timestamp())
        reg_date_str = f"<t:{ts}:d> (<t:{ts}:R>)"
    except Exception:
        reg_date_str = f"`{reg_at}`"

    row_dict = dict(mod_row)
    strict = row_dict.get("strict_vigs", 0)
    oral = row_dict.get("oral_vigs", 0)

    embed = discord.Embed(
        title=f"Профиль модератора — {clean_name}",
        color=Config.EMBED_COLOR_MAIN,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Никнейм", value=f"`{clean_name}`", inline=True)
    embed.add_field(name="Должность", value=f"`{position}`", inline=True)
    if inactivity_until:
        embed.add_field(name="Неактив", value=f"до `{inactivity_until}`", inline=True)
    embed.add_field(name="Дата постановления", value=reg_date_str, inline=False)
    embed.add_field(
        name="Выговоры",

        value=f"```\nСтрогие выговоры: {strict}/3\nУстные выговоры:  {oral}/3\n```",
        inline=False
    )
    return embed

def moderinfo_embed(member: discord.abc.User, stats: aiosqlite.Row) -> discord.Embed:
    total = (
        stats["tickets"] + stats["mutes"] + stats["kicks"] + stats["bans"]
        + stats["warns"] + stats["deleted_msgs"]
    )
    embed = discord.Embed(
        title=f"Профиль модератора — {member.name}",
        color=Config.EMBED_COLOR_MAIN,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name="> Справка по тикетам:",
        value=f"```{stats['tickets']} {pluralize(stats['tickets'], WORDS['ticket'])} "
              f"[👍 {stats['likes']} | {stats['dislikes']} 👎]```",
        inline=False,
    )
    embed.add_field(
        name="> Количество наказаний:",
        value=(
            "```\n"
            f"{stats['mutes']} мутов\n"
            f"{stats['kicks']} киков\n"
            f"{stats['bans']} банов\n"
            f"{stats['warns']} варнов\n"
            f"{stats['deleted_msgs']} сообщений удалено\n"
            f"{total} тотал\n"
            "```"
        ),
        inline=False,
    )
    return embed

def moderlist_page_embed(moderators: list[aiosqlite.Row], guild: discord.Guild,
                          page: int, total_pages: int, total_count: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"Общее количество модераторов — {total_count}",
        color=Config.EMBED_COLOR_MAIN,
    )
    for idx, mod in enumerate(moderators, start=1 + page * 9):
        member = guild.get_member(mod["user_id"])
        username = member.name if member else f"ID {mod['user_id']}"
        total = (
            mod["tickets"] + mod["mutes"] + mod["kicks"] + mod["bans"]
            + mod["warns"] + mod["deleted_msgs"]
        )
        value = (
            f"@{username}\n"
            f"`{mod['tickets']} тикетов [👍 {mod['likes']} | {mod['dislikes']} 👎]`\n"
            f"`{mod['mutes']} мутов`\n"
            f"`{mod['kicks']} киков`\n"
            f"`{mod['bans']} банов`\n"
            f"`{mod['warns']} варнов`\n"
            f"`{mod['deleted_msgs']} сообщений удалено`\n"
            f"`{total} тотал`"
        )
        embed.add_field(name=f"Модератор #{idx}", value=value, inline=True)
    if total_pages > 1:
        embed.set_footer(text=f"Страница {page + 1}/{total_pages}")
    return embed

def punishment_log_embed(action: str, emoji: str, moderator: discord.abc.User,
                          target: discord.abc.User, reason: str,
                          duration_seconds: Optional[int] = None,
                          proof_url: Optional[str] = None) -> discord.Embed:

    action_labels = {
        "Кик": "KICK", "Мут": "MUTE", "Размут": "UNMUTE",
        "Бан": "BAN", "Разбан": "UNBAN", "Предупреждение": "WARN",
        "Тикет-бан": "TICKET-BAN",
    }
    label = action_labels.get(action, action.upper())
    embed = discord.Embed(color=8647000)
    embed.set_author(name=label)
    embed.add_field(name="Модератор", value=f"{moderator.mention} `[{moderator.id}]`", inline=False)
    embed.add_field(name="Пользователь", value=f"{target.mention} `[{target.id}]`", inline=False)
    embed.add_field(name="Причина", value=f"`{reason or 'Не указана'}`", inline=False)
    if duration_seconds is not None:
        embed.add_field(name="Срок", value=f"`{format_duration(duration_seconds)}`", inline=False)
    elif duration_seconds is None and label in ("BAN", "MUTE"):
        embed.add_field(name="Срок", value="`Навсегда`", inline=False)
    if proof_url:
        embed.add_field(name="Доказательства", value=f"[Кликнуть для просмотра]({proof_url})", inline=False)
    return embed

async def send_punishment_dm(guild: discord.Guild, target: discord.abc.User, action: str,
                             moderator: discord.abc.User, reason: str,
                             duration_seconds: Optional[int] = None,
                             proof_url: Optional[str] = None):
    try:
        guild_name = guild.name if guild else "Сервер"
        embed = discord.Embed(
            title=f"Вы получили наказание на сервере {guild_name}",
            color=Config.EMBED_COLOR_ERROR,
            timestamp=datetime.now(timezone.utc)
        )
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Тип наказания", value=f"`{action}`", inline=True)
        embed.add_field(name="Модератор", value=moderator.mention, inline=True)
        embed.add_field(name="Причина", value=f"`{reason or 'Не указана'}`", inline=False)
        if duration_seconds is not None:
            embed.add_field(name="Срок", value=f"`{format_duration(duration_seconds)}`", inline=False)
        elif action.lower() in ("бан", "мут", "ban", "mute") and duration_seconds is None:
            embed.add_field(name="Срок", value="`Навсегда`", inline=False)
        if proof_url:
            embed.add_field(name="Доказательства", value=f"[Нажмите сюда для просмотра]({proof_url})", inline=False)
        else:
            embed.add_field(name="Доказательства", value="`Не предоставлены`", inline=False)
        await target.send(embed=embed)
    except Exception as exc:
        log.info("Не удалось отправить сообщение в ЛС пользователю %s: %s", target.id, exc)

def ticket_panel_embed() -> discord.Embed:
    return discord.Embed(
        title="🎫 Тикет-система поддержки",
        description=(
            "Если у Вас возникли вопросы, жалобы или проблемы — "
            "нажмите на кнопку ниже, чтобы создать тикет.\n\n"
            "Наши модераторы ответят Вам в кратчайшие сроки."
        ),
        color=Config.EMBED_COLOR_TICKET,
    )

def ticket_creating_embed() -> discord.Embed:
    return discord.Embed(description="⏳ Ваш тикет создается...", color=Config.EMBED_COLOR_TICKET)

def ticket_channel_embed(author: discord.abc.User, topic: str) -> discord.Embed:
    _LINK_RE = re.compile(r"https?://|discord\.gg|www\.", re.IGNORECASE)
    has_links = bool(_LINK_RE.search(topic or ""))

    embed = discord.Embed(
        title="Тема вопроса: вопрос по Discord",
        description=f"```{topic or 'Не указан'}```",
        color=Config.EMBED_COLOR_MAIN,
    )
    embed.set_author(name=f"Вопрос от {author.name}", icon_url=author.display_avatar.url)
    embed.add_field(
        name="🖇️ Найденные ссылки",
        value="✅" if has_links else "❌",
        inline=False,
    )
    embed.timestamp = datetime.now(timezone.utc)
    return embed

def format_discord_content_to_html(content: str, guild: discord.Guild, profiles: dict) -> str:
    if not content:
        return ""
    text = content.replace("**", "")

    def replace_code_block(match):
        code_body = match.group(1).strip("\r\n")
        return f'<discord-code-block language="" code="{html.escape(code_body)}"></discord-code-block>'

    text = re.sub(r'```(?:[a-zA-Z0-9_-]+\n)?(.*?)```', replace_code_block, text, flags=re.DOTALL)

    def replace_role(match):
        rid = int(match.group(1))
        role = guild.get_role(rid)
        rname = role.name if role else f"Role {rid}"
        rcolor = f'color="#{role.color.value:06x}"' if role and role.color and role.color.value != 0 else ''
        return f'<discord-mention type="role" {rcolor}>{html.escape(rname)}</discord-mention>'

    text = re.sub(r'<@&(\d+)>', replace_role, text)

    def replace_user(match):
        uid = match.group(1)
        prof = profiles.get(uid)
        uname = prof["author"] if prof else uid
        return f'<discord-mention type="user">{html.escape(uname)}</discord-mention>'

    text = re.sub(r'<@!?(\d+)>', replace_user, text)

    if "<discord-code-block" not in text:
        parts = text.split("`")
        res = []
        for idx, part in enumerate(parts):
            if idx % 2 == 1:
                res.append(f'<discord-inline-code>{html.escape(part)}</discord-inline-code>')
            else:
                res.append(part)
        text = "".join(res)

    return text

def generate_ticket_html(channel: discord.TextChannel, messages: list[discord.Message], number: int) -> io.BytesIO:
    profiles = {}
    for m in messages:
        uid = str(m.author.id)
        if uid not in profiles:
            role_color = "#000000"
            if isinstance(m.author, discord.Member) and m.author.color and m.author.color.value != 0:
                role_color = f"#{m.author.color.value:06x}"
            profiles[uid] = {
                "author": m.author.name,
                "avatar": m.author.display_avatar.url,
                "roleColor": role_color,
                "bot": m.author.bot,
                "verified": False,
            }

    profiles_json = json.dumps(profiles, ensure_ascii=False)
    guild_icon = channel.guild.icon.url if channel.guild.icon else ""
    guild_name = html.escape(channel.guild.name)

    msg_blocks = []
    for m in messages:
        ts = m.created_at.isoformat()
        edited = "true" if m.edited_at else "false"
        content_formatted = format_discord_content_to_html(m.content or "", channel.guild, profiles)

        embeds_html = ""
        for e in m.embeds:
            e_title = f'embed-title="{html.escape(e.title)}"' if e.title else ''
            e_author_name = f'author-name="{html.escape(e.author.name)}"' if e.author and e.author.name else ''
            e_author_img = f'author-image="{e.author.icon_url}"' if e.author and e.author.icon_url else ''
            e_color = f'color="#{e.color.value:06x}"' if e.color else ''

            desc_slot = ""
            if e.description:
                if "```" in e.description:
                    code_match = re.search(r'```(?:[a-zA-Z0-9_-]+\n)?(.*?)```', e.description, re.DOTALL)
                    if code_match:
                        code_val = code_match.group(1).strip("\r\n")
                        desc_slot = f'<discord-embed-description slot="description"><discord-code-block language="" code="{html.escape(code_val)}"></discord-code-block></discord-embed-description>'
                    else:
                        desc_slot = f'<discord-embed-description slot="description">{html.escape(e.description)}</discord-embed-description>'
                else:
                    desc_slot = f'<discord-embed-description slot="description">{html.escape(e.description)}</discord-embed-description>'

            fields_slot = ""
            if e.fields:
                f_items = []
                for f in e.fields:
                    f_inline = "true" if f.inline else "false"
                    f_items.append(f'<discord-embed-field field-title="{html.escape(f.name)}" inline="{f_inline}">{html.escape(f.value)}</discord-embed-field>')
                fields_slot = f'<discord-embed-fields slot="fields">{"".join(f_items)}</discord-embed-fields>'

            embeds_html += f'<discord-embed {e_title} {e_author_name} {e_author_img} {e_color} slot="embeds">{desc_slot}{fields_slot}</discord-embed>'

        msg_blocks.append(
            f'<discord-message id="m-{m.id}" timestamp="{ts}" edited="{edited}" highlight="false" profile="{m.author.id}">'
            f'{content_formatted}{embeds_html}'
            f'</discord-message>'
        )

    html_content = (
        f'<html><head><meta charSet="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>'
        f'<link rel="icon" type="image/png" href="{guild_icon}"/><title>📧-ticket-{number}</title>'
        f'<script>document.addEventListener("click",t=>{{let e=t.target;if(!e)return;let o=e?.getAttribute("data-goto");'
        f'if(o){{let r=document.getElementById(`m-${{o}}`);r?(r.scrollIntoView({{behavior:"smooth",block:"center"}}),'
        f'r.style.backgroundColor="rgba(148, 156, 247, 0.1)",r.style.transition="background-color 0.5s ease",'
        f'setTimeout(()=>{{r.style.backgroundColor="transparent"}},1e3)):console.warn("Message ${{goto}} not found.")}}}});</script>'
        f'<script>window.$discordMessage={{profiles:{profiles_json}}}</script>'
        f'<script type="module" src="https://cdn.jsdelivr.net/npm/@derockdev/discord-components-core@^3.6.1/dist/derockdev-discord-components-core/derockdev-discord-components-core.esm.js"></script>'
        f'</head><body style="margin:0;min-height:100vh"><discord-messages style="min-height:100vh">'
        f'<discord-header guild="{guild_name}" channel="📧-ticket-{number}" icon="{guild_icon}">This is the start of #📧-ticket-{number} channel.</discord-header>'
        f'{"".join(msg_blocks)}'
        f'<div style="text-align:center;width:100%;padding:10px 0;color:#aaa;font-family:sans-serif">Swag Ticket System. Exported {len(messages)} messages </div>'
        f'</discord-messages></body></html>'
    )

    buffer = io.BytesIO(html_content.encode("utf-8"))
    buffer.seek(0)
    return buffer

HELP_THUMBNAIL_URL = "https://images-ext-1.discordapp.net/external/8k-baZhZdvRypMnhDURHxFFO49JSTvSe2ZMdlqlzkKo/%3Fsize%3D1024/https/cdn.discordapp.com/avatars/1536745106441240697/5e81dd289a0d44cfa2558cb004c1140d.png?format=webp&quality=lossless"

def help_main_embed(bot_avatar_url: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(
        title="Привет, я Swag Moderation!",
        description="Developed by Swag",
        color=Config.EMBED_COLOR_MAIN,
    )
    embed.set_thumbnail(url=bot_avatar_url or HELP_THUMBNAIL_URL)
    return embed

def avatar_embed(user: discord.abc.User) -> discord.Embed:
    embed = discord.Embed(
        title=f"Аватар пользователя {user.name}",
        color=Config.EMBED_COLOR_MAIN,
    )
    embed.set_image(url=user.display_avatar.url)
    return embed

def rating_request_embed(author: discord.abc.User) -> discord.Embed:
    return discord.Embed(
        title="Оцените работу модератора",
        description=f"{author.mention}, пожалуйста, оцените качество обработки Вашего тикета.",
        color=Config.EMBED_COLOR_MAIN,
    )

def settings_panel_embed(settings: dict) -> discord.Embed:
    embed = discord.Embed(title="⚙️ Настройки модерации и логов", color=Config.EMBED_COLOR_MAIN)
    embed.add_field(
        name="Модуль модерации",
        value="🟢 Включен" if settings["moderation_enabled"] else "🔴 Выключен",
        inline=True,
    )
    embed.add_field(
        name="Модуль тикетов",
        value="🟢 Включен" if settings["ticket_system_enabled"] else "🔴 Выключен",
        inline=True,
    )
    role_map = settings.get("command_role_map", {})
    if role_map:
        lines = [f"`/{cmd}` → {', '.join(f'<@&{r}>' for r in roles)}" for cmd, roles in role_map.items()]
        val_roles = "\n".join(lines)
        if len(val_roles) > 1024:
            val_roles = val_roles[:1020] + "..."
        embed.add_field(name="Привязанные роли", value=val_roles, inline=False)
    else:
        embed.add_field(name="Привязанные роли", value="Не настроены (доступ у администраторов /всех модераторов)", inline=False)

    log_map = settings.get("log_channels_map", {})
    cat_names = {
        "messages": "💬 Сообщения", "roles": "🎭 Роли", "moderation": "🛡️ Модерация",
        "tickets": "🎫 Тикеты", "members": "👋 Участники", "server": "⚙️ Сервер"
    }
    if log_map:
        log_lines = [f"{cat_names.get(cat, cat)} → <#{cid}>" for cat, cid in log_map.items()]
        val_logs = "\n".join(log_lines)
        if len(val_logs) > 1024:
            val_logs = val_logs[:1020] + "..."
        embed.add_field(name="📋 Каналы логов", value=val_logs, inline=False)
    else:
        embed.add_field(name="📋 Каналы логов", value="Не настроены (логирование выключено)", inline=False)

    news_ch = settings.get("news_channel_id")
    embed.add_field(
        name="📣 Канал новостей",
        value=f"<#{news_ch}>" if news_ch else "Не настроен",
        inline=False,
    )
    return embed

class NotRegisteredError(app_commands.CheckFailure):
    pass

class NotAdministratorError(app_commands.CheckFailure):
    pass

class MissingModRoleError(app_commands.CheckFailure):
    def __init__(self, role_ids: list[int]):
        self.role_ids = role_ids
        super().__init__("missing mod role")

SPECIAL_ADMIN_ROLE_ID = 1537451548622332025

def is_admin_member(user: Optional[Union[discord.Member, discord.User]]) -> bool:
    if user is None or not isinstance(user, discord.Member):
        return False
    if user.guild_permissions.administrator:
        return True
    return any(r.id == SPECIAL_ADMIN_ROLE_ID for r in user.roles)

def is_administrator():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not is_admin_member(interaction.user):
            raise NotAdministratorError()
        return True
    return app_commands.check(predicate)

def is_registered_moderator():
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_admin_member(interaction.user):
            return True
        if not await db.is_registered(interaction.guild_id, interaction.user.id):
            raise NotRegisteredError()
        return True
    return app_commands.check(predicate)

async def has_mod_permission(guild_id: int, member: discord.Member, command_key: str) -> tuple[bool, Optional[app_commands.AppCommandError]]:
    if is_admin_member(member):
        return True, None

    settings = await db.get_settings(guild_id)
    required_roles: list = settings.get("command_role_map", {}).get(command_key, [])

    if required_roles:
        required_role_ids = {int(r) for r in required_roles}
        member_role_ids = {r.id for r in member.roles}
        if member_role_ids.intersection(required_role_ids):
            return True, None
        return False, MissingModRoleError(list(required_role_ids))

    if command_key in ("register", "unregister", "setstat_moder"):
        return False, NotAdministratorError()

    if not await db.is_registered(guild_id, member.id):
        return False, NotRegisteredError()

    return True, None

def require_mod_permission(command_key: str):
    async def predicate(interaction: discord.Interaction) -> bool:
        member = interaction.user
        if not isinstance(member, discord.Member):
            raise NotAdministratorError()

        allowed, err = await has_mod_permission(interaction.guild_id, member, command_key)
        if not allowed and err:
            raise err
        return True

    return app_commands.check(predicate)

async def send_check_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> bool:
    if isinstance(error, NotRegisteredError):
        embed = not_registered_embed()
    elif isinstance(error, NotAdministratorError):
        embed = not_admin_embed()
    elif isinstance(error, MissingModRoleError):
        mentions = ", ".join(f"<@&{r}>" for r in error.role_ids)
        embed = missing_role_embed(mentions)
    else:
        return False

    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    return True

class ModerListPaginator(discord.ui.View):
    PAGE_SIZE = 9

    def __init__(self, moderators: list[aiosqlite.Row], guild: discord.Guild):
        super().__init__(timeout=180)
        self.moderators = moderators
        self.guild = guild
        self.page = 0
        self.total_pages = max(1, (len(moderators) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.total_pages - 1

    def current_embed(self) -> discord.Embed:
        start = self.page * self.PAGE_SIZE
        chunk = self.moderators[start:start + self.PAGE_SIZE]
        return moderlist_page_embed(chunk, self.guild, self.page, self.total_pages, len(self.moderators))

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary, custom_id="moderlist_prev")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary, custom_id="moderlist_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.total_pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

class TicketTopicModal(discord.ui.Modal, title="Создание тикета"):
    topic = discord.ui.TextInput(
        label="Ваш вопрос",
        style=discord.TextStyle.paragraph,
        placeholder="Опишите Ваш вопрос...",
        max_length=500,
        required=True,
    )

    def __init__(self, bot: "ModerBot"):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await self.bot.create_ticket_channel(interaction, str(self.topic))

class TicketPanelView(discord.ui.View):
    def __init__(self, bot: "ModerBot"):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Создать тикет", emoji="📩",
        style=discord.ButtonStyle.blurple, custom_id="ticket_create_button",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketTopicModal(self.bot))

class TicketControlView(discord.ui.View):
    def __init__(self, bot: "ModerBot"):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Взять тикет", emoji="📨",
        style=discord.ButtonStyle.secondary, custom_id="ticket_take_button",
    )
    async def take_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot.handle_ticket_take(interaction)

    @discord.ui.button(
        label="Закрыть", emoji="🔒",
        style=discord.ButtonStyle.secondary, custom_id="ticket_close_button",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot.handle_ticket_close(interaction)

    @discord.ui.button(
        label="Принудительно закрыть", emoji="🗑️",
        style=discord.ButtonStyle.secondary, custom_id="ticket_force_delete_button",
    )
    async def force_delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot.handle_ticket_delete(interaction)

class TicketRatingView(discord.ui.View):
    def __init__(self, bot: "ModerBot", ticket_id: int, author_id: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.ticket_id = ticket_id
        self.author_id = author_id
        self.rated = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Оценить тикет может только его автор.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="👍", style=discord.ButtonStyle.success, custom_id="ticket_rate_like")
    async def like(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.rated = True
        await self.bot.handle_ticket_rating(interaction, self.ticket_id, "like")
        self.stop()

    @discord.ui.button(label="👎", style=discord.ButtonStyle.danger, custom_id="ticket_rate_dislike")
    async def dislike(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.rated = True
        await self.bot.handle_ticket_rating(interaction, self.ticket_id, "dislike")
        self.stop()

    async def on_timeout(self):
        if not self.rated:
            await self.bot.archive_ticket_by_id(self.ticket_id)

class TicketDeleteView(discord.ui.View):
    def __init__(self, bot: "ModerBot"):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Удалить тикет", emoji="🗑️",
        style=discord.ButtonStyle.danger, custom_id="ticket_delete_button",
    )
    async def delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot.handle_ticket_delete(interaction)

class HelpSelect(discord.ui.Select):
    def __init__(self, bot_avatar_url: Optional[str] = None):
        self.bot_avatar_url = bot_avatar_url
        options = [
            discord.SelectOption(
                label="Пользовательские команды",
                description="Посмотреть команды доступные пользователю",
                value="user_cmds",
            ),
            discord.SelectOption(
                label="Команды модерации",
                description="Посмотреть команды модерации",
                value="mod_cmds",
            ),
            discord.SelectOption(
                label="Команды управления модерацией",
                description="Посмотреть команды системы управления модерацией",
                value="mod_mgmt_cmds",
            ),
        ]
        super().__init__(placeholder="Выберите интересующий вас раздел", options=options)

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        embed = discord.Embed(color=Config.EMBED_COLOR_MAIN)
        embed.set_thumbnail(url=self.bot_avatar_url or HELP_THUMBNAIL_URL)

        if cat == "user_cmds":
            embed.title = "📌 Пользовательские команды"
            embed.description = (
                "> `/avatar` — Посмотреть аватар пользователя\n"
                "> `/ping` — Проверить задержку и отклик бота\n"
            )
        elif cat == "mod_cmds":
            embed.title = "🔨 Команды модерации"
            embed.description = (
                "> `/moderinfo` — Профиль модератора\n"
                "> `/moderlist` — Список зарегистрированных модераторов\n"
                "> `/kick` — Кикнуть пользователя с сервера\n"
                "> `/mute` — Замьютить пользователя (timeout)\n"
                "> `/unmute` — Снять мьют с пользователя\n"
                "> `/ban` — Забанить пользователя\n"
                "> `/unban` — Разбанить пользователя по ID\n"
                "> `/warn` — Выдать предупреждение пользователю\n"
                "> `/clear` — Удалить сообщения из канала"
            )
        elif cat == "mod_mgmt_cmds":
            embed.title = "⚙️ Управление модерацией"
            embed.description = (
                "> `/register` — Зарегистрировать модератора\n"
                "> `/unregister` — Снять модератора из системы\n"
                "> `/clearmoders` — Удалить всех модераторов из БД\n"
                "> `/setstat moder` — Изменить статистику модератора\n"
                "> `/settings moderation` — Настройки модерации и каналов логов"
            )

        await interaction.response.edit_message(embed=embed, view=self.view)

class HelpView(discord.ui.View):
    def __init__(self, bot_avatar_url: Optional[str] = None):
        super().__init__(timeout=180)
        self.add_item(HelpSelect(bot_avatar_url))

class _FormApproveView(discord.ui.View):
    def __init__(self, bot: "ModerBot", guild_id: int, settings: dict):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.settings = settings

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Выберите роли (до 5)", max_values=5)
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role_ids = [r.id for r in select.values]
        await db.update_settings(self.guild_id, form_approve_roles=json.dumps(role_ids))
        self.settings = await db.get_settings(self.guild_id)
        roles_text = ", ".join(r.mention for r in select.values) if select.values else "все модераторы"
        await interaction.response.edit_message(
            content=f"✅ Роли для принятия форм установлены: {roles_text}", view=None
        )

    @discord.ui.button(label="🗑️ Сбросить", style=discord.ButtonStyle.danger)
    async def clear_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await db.update_settings(self.guild_id, form_approve_roles="[]")
        self.settings = await db.get_settings(self.guild_id)
        await interaction.response.edit_message(
            content="🗑️ Роли для принятия форм сброшены — теперь могут все модераторы.",
            view=None
        )

class SettingsView(discord.ui.View):
    def __init__(self, bot: "ModerBot", guild_id: int, settings: dict):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.settings = settings
        self._sync_toggle_styles()

    def _sync_toggle_styles(self):
        self.toggle_moderation.style = (
            discord.ButtonStyle.success if self.settings["moderation_enabled"] else discord.ButtonStyle.danger
        )
        self.toggle_moderation.label = (
            "Модерация: Вкл" if self.settings["moderation_enabled"] else "Модерация: Выкл"
        )
        self.toggle_tickets.style = (
            discord.ButtonStyle.success if self.settings["ticket_system_enabled"] else discord.ButtonStyle.danger
        )
        self.toggle_tickets.label = (
            "Тикеты: Вкл" if self.settings["ticket_system_enabled"] else "Тикеты: Выкл"
        )

    @discord.ui.button(label="Модерация: Вкл", style=discord.ButtonStyle.success, row=0)
    async def toggle_moderation(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_value = 0 if self.settings["moderation_enabled"] else 1
        await db.update_settings(self.guild_id, moderation_enabled=new_value)
        self.settings["moderation_enabled"] = new_value
        self._sync_toggle_styles()
        await interaction.response.edit_message(embed=settings_panel_embed(self.settings), view=self)

    @discord.ui.button(label="Тикеты: Вкл", style=discord.ButtonStyle.success, row=0)
    async def toggle_tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_value = 0 if self.settings["ticket_system_enabled"] else 1
        await db.update_settings(self.guild_id, ticket_system_enabled=new_value)
        self.settings["ticket_system_enabled"] = new_value
        self._sync_toggle_styles()
        await interaction.response.edit_message(embed=settings_panel_embed(self.settings), view=self)

    @discord.ui.select(
        placeholder="📋 Настройка канала логов (выберите категорию)...",
        options=[
            discord.SelectOption(label="💬 Сообщения", value="messages", description="Удаление и редактирование сообщений"),
            discord.SelectOption(label="🎭 Роли", value="roles", description="Выдача и снятие ролей"),
            discord.SelectOption(label="🛡️ Модерация", value="moderation", description="Кики, мьюты, баны, варны"),
            discord.SelectOption(label="🎫 Тикеты", value="tickets", description="Логи тикет-системы"),
            discord.SelectOption(label="👋 Участники", value="members", description="Вход и выход участников"),
            discord.SelectOption(label="⚙️ Сервер", value="server", description="Общие события сервера"),
        ],
        row=1,
    )
    async def log_category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        cat_key = select.values[0]
        cat_labels = {
            "messages": "Сообщения", "roles": "Роли", "moderation": "Модерация",
            "tickets": "Тикеты", "members": "Участники", "server": "Сервер"
        }
        view = LogChannelBindOptionsView(self.bot, self.guild_id, cat_key, cat_labels.get(cat_key, cat_key), self)
        await interaction.response.send_message(
            f"⚙️ **Настройка логов категорий `{cat_labels.get(cat_key, cat_key)}`**\n"
            f"Выберите канал из списка сервера или укажите ID канала вручную:",
            view=view,
            ephemeral=True
        )

    @discord.ui.select(
        placeholder="🔐 Привязка ролей к командам...",
        options=[
            discord.SelectOption(
                label=Config.MODERATION_COMMAND_LABELS.get(cmd, f"/{cmd}"),
                value=cmd
            ) for cmd in Config.MODERATION_COMMANDS
        ],
        row=2,
    )
    async def command_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        command_key = select.values[0]
        label = Config.MODERATION_COMMAND_LABELS.get(command_key, f"/{command_key}")
        role_select_view = _RoleBindView(self.bot, self.guild_id, command_key, self)
        await interaction.response.send_message(
            f"Выберите роль(и), которым будет доступна команда `{label}`:",
            view=role_select_view,
            ephemeral=True,
        )

    @discord.ui.button(label="📣 Канал новостей", style=discord.ButtonStyle.secondary, row=3)
    async def set_news_channel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = NewsChannelBindView(self.bot, self.guild_id, self)
        await interaction.response.send_message(
            "📣 **Настройка канала новостей**\nВыберите канал, в который будут отправляться новости (/news):",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="📋 Принимать формы", style=discord.ButtonStyle.secondary, row=3)
    async def set_form_approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = await db.get_settings(self.guild_id)
        current_roles = json.loads(settings.get("form_approve_roles") or "[]")
        if current_roles:
            current_text = ", ".join(f"<@&{rid}>" for rid in current_roles)
        else:
            current_text = "не ограничено (все модераторы)"
        form_view = _FormApproveView(self.bot, self.guild_id, self.settings)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="📋 Настройка ролей для принятия форм",
                description=(
                    f"**Текущие роли:** {current_text}\n\n"
                    f"Выберите роли, которым будет разрешено принимать/отклонять формы наказаний.\n"
                    f"Если роли не выбраны — принимать могут все модераторы."
                ),
                color=0x5865F2,
            ),
            view=form_view,
            ephemeral=True,
        )

class NewsChannelBindView(discord.ui.View):
    def __init__(self, bot, guild_id: int, parent: SettingsView):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.parent = parent

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Выберите канал новостей...")
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = select.values[0]
        await db.update_settings(self.guild_id, news_channel_id=channel.id)
        self.parent.settings = await db.get_settings(self.guild_id)
        await interaction.response.edit_message(
            content=f"✅ Канал новостей установлен: {channel.mention}", view=None
        )

    @discord.ui.button(label="🗑️ Отключить", style=discord.ButtonStyle.danger)
    async def remove_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await db.update_settings(self.guild_id, news_channel_id=None)
        self.parent.settings = await db.get_settings(self.guild_id)
        await interaction.response.edit_message(content="🗑️ Канал новостей отключён.", view=None)

NEWS_TEMPLATES = [
    {
        "id": "role_request",
        "label": "🌌 Запрос роли",
        "description": "Объявление о запросе роли для организации",
        "payload": {
            "content": "||@everyone||",
            "embeds": [{
                "description": "> ## :milky_way: Здравствуйте, уважаемые игроки!\n\n> :crystal_ball: `Хотите получить роль, чтобы общаться со своей организацией? Тогда эта новость для вас!`\n\n> :bookmark_tabs: Чтобы получить роль и начать общаться с участниками вашей фракции, просто выполните следующие действия:\n\n1) - Зайдите в канал - <#1369358730151333918>\n2) - Заполните все необходимые пункты.\n\n> :closed_umbrella: Теперь вы сможете легко поддерживать связь с членами вашей организации и обсуждать важные вопросы!",
                "color": 2829617,
                "image": {"url": "https://i.imgur.com/hfMh43z.jpeg"}
            }],
        }
    },
    {
        "id": "events",
        "label": "🎉 Мероприятия",
        "description": "Объявление о мероприятиях и играх",
        "payload": {
            "content": "||@everyone||",
            "embeds": [{
                "description": "> ## 🛋 Приветствую, уважаемые игроки Arizona SWAG.\n\n> 📗 `Вам скучно, и вы не знаете, чем заняться?`\n\n> 🔫 **Каждый день на сервере проходят множество мероприятий как в текстовом формате, так и в голосовом!**\n\n> 💸 `Лучшие из ведущих организуют для вас самые интересные и разнообразные мероприятия, а призовой фонд каждого из них может включать не только дискорд коины, но и деньги в игре!`\n\n> 🔋** Будем очень рады, если вы зайдёте и поиграете!**\n\n> 🌵 Игры проходят в <#1369358845159411762>, а с самими мероприятиями можно ознакомиться в канале <#1369358838901510277>. Ждём всех!",
                "color": 2829617,
                "image": {"url": "https://i.imgur.com/MXFJyae.jpeg"}
            }],
        }
    },
    {
        "id": "boost",
        "label": "💖 Буст",
        "description": "Объявление о преимуществах буста",
        "payload": {
            "content": "||@everyone||",
            "embeds": [{
                "description": "### Приветствую уважаемые игроки Аризона Свэг! Мы предлагаем вам забустить наш сервер и вот, что мы можем предложить взамен! ❤️\n\n- [🛠 ] - 1) __Можно менять статусы канала__.\n\n- [🌓 ] - 2) __Вы можете включать приоритетный режим, который улучшит качество вашего микрофона.__.\n\n- [💸 ] - 3) __Отдельная роль <@&1103022334635425893> , которая показывает кто тут настоящий богач!__\n\n- [🎹 ] - 4) __Вы сможете включать “Звуковую Панель”__.\n\n- [🎭 ] - 5) __Каждые 2-3 недели будет проходить розыгрыш среди участников этой роли.__.\n\n- [📒 ] - 6) __Для участников данной роли будет акция на первые 3 покупок/оплат ролей в магазине, скидка 15%.__.\n\n- [🎟 ] - 7) __Вы сможете сделать свою личную роль.__",
                "color": 16748288,
                "image": {"url": "https://i.imgur.com/j3b1Etp.jpeg"}
            }],
        }
    },
    {
        "id": "support",
        "label": "🛡️ Поддержка",
        "description": "Инфо о получении поддержки от модераторов",
        "payload": {
            "content": "||@everyone||",
            "embeds": [{
                "description": "> ## 📣 Приветствую всех игроков Arizona SWAG!\n\n> 🛠 `У вас появился вопрос по поводу Discord? Тогда вы можете прямо сейчас его задать!`\n\n> 🖥 **Задать его можно в <#1369415652955263087> и ожидать ответа модератора!**\n\n> 🛡 `Ждём любые ваши вопросы!`",
                "color": 2829617,
                "image": {"url": "https://i.imgur.com/RAwFb4D.jpeg"}
            }],
        }
    },
    {
        "id": "other",
        "label": "🎉 Прочее",
        "description": "Общая новость / жалобы",
        "payload": {
            "content": "||@everyone||",
            "embeds": [{
                "description": "> ### 🎉 Приветствую всех игроков Arizona Swag!\n\n> **📅 Если у вас возникли сомнения в работе модератора, вы можете подать жалобу на него.**\n\n> <:5508purpleheart:1229420958167601152> <#1472971467414306836>",
                "color": 2829617,
                "image": {"url": "https://i.imgur.com/r3j12oo.jpeg"}
            }],
        }
    },
]

class NewsTemplateSelectView(discord.ui.View):
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id

    @discord.ui.select(
        placeholder="📰 Выберите шаблон новости...",
        options=[
            discord.SelectOption(
                label=t["label"],
                value=t["id"],
                description=t["description"],
            )
            for t in NEWS_TEMPLATES
        ],
    )
    async def template_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        tpl_id = select.values[0]
        tpl = next((t for t in NEWS_TEMPLATES if t["id"] == tpl_id), None)
        if not tpl:
            await interaction.response.send_message(embed=error_embed("Шаблон не найден."), ephemeral=True)
            return

        settings = await db.get_settings(self.guild_id)
        news_ch_id = settings.get("news_channel_id") or 1369358585888505876
        channel = interaction.guild.get_channel(news_ch_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(news_ch_id)
            except Exception:
                channel = None

        if channel is None:
            await interaction.response.send_message(
                embed=error_embed("Канал новостей не найден. Установите его в `/settings moderation`."),
                ephemeral=True,
            )
            return

        payload = tpl["payload"]
        embeds = [discord.Embed.from_dict(e) for e in payload.get("embeds", [])]
        await channel.send(content=payload.get("content"), embeds=embeds)
        await interaction.response.send_message(
            embed=success_embed(f"Новость **{tpl['label']}** успешно опубликована в канале {channel.mention}!"),
            ephemeral=True,
        )

class ChannelIdInputModal(discord.ui.Modal):
    def __init__(self, bot: "ModerBot", guild_id: int, cat_key: str, cat_name: str, parent: SettingsView):
        super().__init__(title=f"Канал логов: {cat_name}")
        self.bot = bot
        self.guild_id = guild_id
        self.cat_key = cat_key
        self.cat_name = cat_name
        self.parent = parent

        self.channel_id_input = discord.ui.TextInput(
            label="ID Текстового Канала",
            placeholder="Введите ID текстового канала (например: 123456789012345678)",
            required=True,
            max_length=22,
        )
        self.add_item(self.channel_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.channel_id_input.value.strip()
        if not raw_id.isdigit():
            await interaction.response.send_message(embed=error_embed("Некорректный ID канала. Укажите только цифры!"), ephemeral=True)
            return

        cid = int(raw_id)
        channel = interaction.guild.get_channel(cid)
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(embed=error_embed(f"Текстовый канал с ID `{cid}` не найден на этом сервере!"), ephemeral=True)
            return

        settings = await db.get_settings(self.guild_id)
        log_map = settings.get("log_channels_map", {})
        log_map[self.cat_key] = cid
        await db.update_settings(self.guild_id, log_channels_map=log_map)
        self.parent.settings = await db.get_settings(self.guild_id)

        await interaction.response.send_message(
            embed=success_embed(f"✅ Канал для логов категорий **{self.cat_name}** установлен на {channel.mention}"),
            ephemeral=True
        )

class LogChannelBindOptionsView(discord.ui.View):
    def __init__(self, bot: "ModerBot", guild_id: int, cat_key: str, cat_name: str, parent: SettingsView):
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_id = guild_id
        self.cat_key = cat_key
        self.cat_name = cat_name
        self.parent = parent

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Выберите канал из списка...")
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        channel = select.values[0]
        settings = await db.get_settings(self.guild_id)
        log_map = settings.get("log_channels_map", {})
        log_map[self.cat_key] = channel.id
        await db.update_settings(self.guild_id, log_channels_map=log_map)
        self.parent.settings = await db.get_settings(self.guild_id)
        await interaction.response.edit_message(
            content=f"✅ Канал для логов **{self.cat_name}** привязан к {channel.mention}",
            view=None
        )

    @discord.ui.button(label="✏️ Ввести ID канала", style=discord.ButtonStyle.secondary)
    async def manual_id_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ChannelIdInputModal(self.bot, self.guild_id, self.cat_key, self.cat_name, self.parent)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🗑️ Отключить логи категорий", style=discord.ButtonStyle.danger)
    async def remove_log_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = await db.get_settings(self.guild_id)
        log_map = settings.get("log_channels_map", {})
        log_map.pop(self.cat_key, None)
        await db.update_settings(self.guild_id, log_channels_map=log_map)
        self.parent.settings = await db.get_settings(self.guild_id)
        await interaction.response.edit_message(
            content=f"🗑️ Логи категорий **{self.cat_name}** отключены.",
            view=None
        )

class _RoleBindView(discord.ui.View):
    def __init__(self, bot: "ModerBot", guild_id: int, command_key: str, parent=None):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.command_key = command_key
        self.parent = parent

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Выберите роли (до 5)", max_values=5)
    async def role_select(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        for role in select.values:
            await db.bind_command_role(self.guild_id, self.command_key, role.id)
        if self.parent:
            self.parent.settings = await db.get_settings(self.guild_id)
        label = Config.MODERATION_COMMAND_LABELS.get(self.command_key, f"/{self.command_key}")
        roles_text = ", ".join(r.mention for r in select.values)
        await interaction.response.edit_message(
            content=f"✅ Команда `{label}` — доступна для ролей: {roles_text}", view=None
        )

    @discord.ui.button(label="🗑️ Очистить роли", style=discord.ButtonStyle.danger)
    async def clear_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = await db.get_settings(self.guild_id)
        role_map: dict = settings["command_role_map"]
        role_map.pop(self.command_key, None)
        await db.update_settings(self.guild_id, command_role_map=role_map)
        if self.parent:
            self.parent.settings = await db.get_settings(self.guild_id)
        label = Config.MODERATION_COMMAND_LABELS.get(self.command_key, f"/{self.command_key}")
        await interaction.response.edit_message(
            content=f"🗑️ Роли для `{label}` сброшены — теперь доступна всем зарегистрированным модераторам.",
            view=None
        )

class CmdPermView(discord.ui.View):
    def __init__(self, bot: "ModerBot", guild_id: int, settings: dict):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.settings = settings

    @discord.ui.select(
        placeholder="Выберите команду...",
        options=[
            discord.SelectOption(
                label=Config.MODERATION_COMMAND_LABELS.get(cmd, f"/{cmd}"),
                value=cmd,
                description="Нет ограничений по роли" if True else ""
            ) for cmd in Config.MODERATION_COMMANDS
        ] + [
            discord.SelectOption(
                label="📋 Принимать формы",
                value="form_approve",
                description="Настроить роли для принятия форм наказаний"
            )
        ],
    )
    async def cmd_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        command_key = select.values[0]
        if command_key == "form_approve":
            settings = await db.get_settings(self.guild_id)
            current_roles = json.loads(settings.get("form_approve_roles") or "[]")
            if current_roles:
                current_text = ", ".join(f"<@&{rid}>" for rid in current_roles)
            else:
                current_text = "не ограничено (все модераторы)"
            form_view = _FormApproveView(self.bot, self.guild_id, self.settings)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="📋 Настройка ролей для принятия форм",
                    description=(
                        f"**Текущие роли:** {current_text}\n\n"
                        f"Выберите роли, которым будет разрешено принимать/отклонять формы наказаний.\n"
                        f"Если роли не выбраны — принимать могут все модераторы."
                    ),
                    color=0x5865F2,
                ),
                view=form_view,
                ephemeral=True,
            )
            return
        label = Config.MODERATION_COMMAND_LABELS.get(command_key, f"/{command_key}")
        current_roles = self.settings["command_role_map"].get(command_key, [])
        if current_roles:
            current_text = ", ".join(f"<@&{rid}>" for rid in current_roles)
        else:
            current_text = "не ограничена (все зарегистрированные модераторы)"

        role_view = _RoleBindView(self.bot, self.guild_id, command_key)
        await interaction.response.send_message(
            embed=discord.Embed(
                title=f"🔐 Настройка прав: `{label}`",
                description=(
                    f"**Текущие роли:** {current_text}\n\n"
                    f"Выберите роли, которым будет разрешена команда `{label}`.\n"
                    f"Администраторы всегда имеют доступ.\n\n"
                    f"Нажмите **🗑️ Очистить роли**, чтобы убрать ограничения."
                ),
                color=0x5865F2,
            ),
            view=role_view,
            ephemeral=True,
        )

class FormActionsView(discord.ui.View):
    def __init__(self, guild_id: int, form_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(FormAcceptButton(form_id))
        self.add_item(FormRejectButton(form_id))

class FormAcceptButton(discord.ui.Button):
    def __init__(self, form_id: int):
        super().__init__(label="✅ Принять", style=discord.ButtonStyle.success, custom_id=f"form_accept_{form_id}")
        self._form_id = form_id

    async def callback(self, interaction: discord.Interaction):
        await _handle_form_action(interaction, self._form_id, "approved")

class FormRejectModal(discord.ui.Modal, title="Отклонение формы"):
    reason = discord.ui.TextInput(
        label="Причина отказа",
        placeholder="Укажите причину отклонения формы...",
        required=False,
        max_length=200,
        style=discord.TextStyle.paragraph
    )

    def __init__(self, form_id: int):
        super().__init__()
        self._form_id = form_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        reject_reason = str(self.reason.value).strip() or "Не указана"
        await _handle_form_action(interaction, self._form_id, "rejected", reject_reason=reject_reason)

class FormRejectButton(discord.ui.Button):
    def __init__(self, form_id: int):
        super().__init__(label="Отклонить", style=discord.ButtonStyle.danger, custom_id=f"form_reject_{form_id}")
        self._form_id = form_id

    async def callback(self, interaction: discord.Interaction):
        settings = await db.get_settings(interaction.guild_id)
        approve_roles = json.loads(settings.get("form_approve_roles") or "[]")
        member_role_ids = {r.id for r in interaction.user.roles}
        if approve_roles and not member_role_ids.intersection({int(r) for r in approve_roles}):
            await interaction.response.send_message(embed=error_embed("У вас нет прав для обработки форм наказаний."), ephemeral=True)
            return
        await interaction.response.send_modal(FormRejectModal(self._form_id))

async def _handle_form_action(interaction: discord.Interaction, form_id: int, new_status: str, reject_reason: str = "Не указана"):
    if not interaction.response.is_done():
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

    settings = await db.get_settings(interaction.guild_id)
    approve_roles = json.loads(settings.get("form_approve_roles") or "[]")
    member_role_ids = {r.id for r in interaction.user.roles}
    if approve_roles and not member_role_ids.intersection({int(r) for r in approve_roles}):
        await interaction.followup.send(embed=error_embed("У вас нет прав для обработки форм наказаний."), ephemeral=True)
        return

    form = await db.get_form(form_id)
    if not form or form["status"] != "pending":
        await interaction.followup.send(embed=error_embed("Форма уже обработана."), ephemeral=True)
        return

    await db.update_form_status(form["id"], new_status, interaction.user.id)
    approver_username = f"@{interaction.user.name}"

    if new_status == "approved":
        await db.increment_moder_stat(interaction.guild_id, form["author_id"], form["type"])
        # +5 монет за каждую одобренную форму
        await db.add_swag_coins(interaction.guild_id, form["author_id"], 5)

        author = interaction.guild.get_member(form["author_id"])
        if author is None:
            try:
                author = await interaction.guild.fetch_member(form["author_id"])
            except Exception:
                pass

        author_username = f"@{author.name}" if author else f"User {form['author_id']}"
        type_russian = _type_to_russian(form["type"])

        target_name = form.get("target_name", "")
        target_id_match = re.search(r'<@!?(\d+)>', target_name)
        target_id = int(target_id_match.group(1)) if target_id_match else None
        target = None
        if target_id:
            target = interaction.guild.get_member(target_id)
            if target is None:
                try:
                    target = await interaction.guild.fetch_member(target_id)
                except Exception:
                    pass
            if target is None:
                try:
                    target = await interaction.guild.fetch_user(target_id)
                except Exception:
                    pass

        if target:
            form_type = form["type"]
            reason = form.get("reason", "Не указана")
            duration_str = form.get("duration", "")
            author_tag = author.name if author else f"{form['author_id']}"
            form_reason = f"{reason} by {author_tag}"

            if form_type == "mute":
                try:
                    if not duration_str or duration_str == "Не указана":
                        duration_str = "30m"
                    seconds = parse_duration(duration_str)
                    if seconds is None:
                        seconds = 28 * 86400
                    seconds = min(seconds, 28 * 86400)
                    await target.timeout(timedelta(seconds=seconds), reason=f"{form_reason}")
                    await send_punishment_dm(interaction.guild, target, "Мут", interaction.user, form_reason, duration_seconds=seconds)
                    result_embed = discord.Embed(
                        title=f"✅ Форма #{form['id']} принята",
                        description=(
                            f"• **Автор:** {author_username}\n"
                            f"• **Принял:** {approver_username}\n"
                            f"• **Тип:** `{type_russian}`\n\n"
                            f"🔇 {target.mention} замьючен на `{format_duration(seconds)}`"
                        ),
                        color=Config.EMBED_COLOR_SUCCESS
                    )
                except discord.Forbidden:
                    result_embed = error_embed(f"Не удалось применить мут к {target.mention}. Не хватает прав.")
                except ValueError as e:
                    result_embed = error_embed(f"Некорректная длительность: {duration_str}")
                    log.error("parse_duration error: %s", e)
                except Exception as e:
                    result_embed = error_embed(f"Ошибка при муте: {e}")
                    log.error("mute error: %s", e)

            elif form_type == "kick":
                try:
                    await target.kick(reason=f"{form_reason}")
                    await send_punishment_dm(interaction.guild, target, "Кик", interaction.user, form_reason)
                    result_embed = discord.Embed(
                        title=f"✅ Форма #{form['id']} принята",
                        description=(
                            f"• **Автор:** {author_username}\n"
                            f"• **Принял:** {approver_username}\n"
                            f"• **Тип:** `{type_russian}`\n\n"
                            f"👢 {target.mention} кикнут с сервера"
                        ),
                        color=Config.EMBED_COLOR_SUCCESS
                    )
                except discord.Forbidden:
                    result_embed = error_embed(f"Не удалось кикнуть {target.mention}. Не хватает прав.")
                except Exception as e:
                    result_embed = error_embed(f"Ошибка при кике: {e}")
                    log.error("kick error: %s", e)

            elif form_type == "ban":
                try:
                    seconds = None
                    if duration_str and duration_str != "Не указана":
                        seconds = parse_duration(duration_str)

                    expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds) if seconds else None
                    await db.add_punishment(interaction.guild_id, target.id, "ban", expires_at)
                    await interaction.guild.ban(target, reason=f"{form_reason}")
                    await send_punishment_dm(interaction.guild, target, "Бан", interaction.user, form_reason, duration_seconds=seconds)
                    dur_text = f"на `{format_duration(seconds)}`" if seconds else "навсегда"
                    result_embed = discord.Embed(
                        title=f"✅ Форма #{form['id']} принята",
                        description=(
                            f"• **Автор:** {author_username}\n"
                            f"• **Принял:** {approver_username}\n"
                            f"• **Тип:** `{type_russian}`\n\n"
                            f"🔨 {target.mention} забанен {dur_text}"
                        ),
                        color=Config.EMBED_COLOR_SUCCESS
                    )
                except discord.Forbidden:
                    result_embed = error_embed(f"Не удалось забанить {target.mention}. Не хватает прав.")
                except Exception as e:
                    result_embed = error_embed(f"Ошибка при бане: {e}")
                    log.error("ban error: %s", e)
            else:
                result_embed = discord.Embed(
                    title=f"✅ Форма #{form['id']} принята",
                    description=(
                        f"• **Автор:** {author_username}\n"
                        f"• **Принял:** {approver_username}\n"
                        f"• **Тип:** `{type_russian}`"
                    ),
                    color=Config.EMBED_COLOR_SUCCESS
                )
        else:
            result_embed = discord.Embed(
                title=f"✅ Форма #{form['id']} принята",
                description=(
                    f"• **Автор:** {author_username}\n"
                    f"• **Принял:** {approver_username}\n"
                    f"• **Тип:** `{type_russian}`"
                ),
                color=Config.EMBED_COLOR_SUCCESS
            )
    else:
        author = interaction.guild.get_member(form["author_id"])
        if author is None:
            try:
                author = await interaction.guild.fetch_member(form["author_id"])
            except Exception:
                pass
        author_username = f"@{author.name}" if author else f"User {form['author_id']}"

        result_embed = discord.Embed(
            title=f"❌ Форма #{form['id']} отклонена",
            description=(
                f"• **Автор:** {author_username}\n"
                f"• **Отклонил:** {approver_username}\n"
                f"• **Причина:** `{reject_reason}`"
            ),
            color=Config.EMBED_COLOR_ERROR
        )

        if author:
            try:
                dm_emb = discord.Embed(
                    title="❌ Форма отклонена",
                    description=(
                        f"Ваша **Форма #{form['id']}** была отклонена модератором {approver_username}.\n\n"
                        f"• **Причина отказа:** `{reject_reason}`"
                    ),
                    color=Config.EMBED_COLOR_ERROR
                )
                await author.send(embed=dm_emb)
            except Exception:
                pass

    try:
        await interaction.message.edit(embed=result_embed, view=None)
        await interaction.followup.send(embed=success_embed(f"Форма #{form['id']} {'одобрена' if new_status == 'approved' else 'отклонена'}."), ephemeral=True)
    except Exception as exc:
        log.error("Failed to edit form message: %s", exc)
        await interaction.followup.send(embed=result_embed)

def _format_duration_human(duration_str: str) -> str:
    if not duration_str or duration_str == "—" or duration_str == "None":
        return "Не указано"
    duration_str = duration_str.lower().strip()
    total_seconds = None
    try:
        total_seconds = parse_duration(duration_str)
    except ValueError:
        return duration_str
    if total_seconds is None:
        return "Навсегда"
    return format_duration(total_seconds)

def _type_to_emoji(form_type: str) -> str:
    types_map = {
        "mute": "🔇",
        "kick": "🚪",
        "ban": "🔨",
    }
    return types_map.get(form_type, "❓")

def _type_to_russian(form_type: str) -> str:
    types_map = {
        "mute": "Мут",
        "kick": "Кик",
        "ban": "Бан",
    }
    return types_map.get(form_type, form_type)

async def _send_single_form(form: dict, channel: discord.TextChannel):
    guild = channel.guild
    author = guild.get_member(form["author_id"])
    author_name = author.display_name if author else f"User {form['author_id']}"
    author_mention = author.mention if author else f"<@{form['author_id']}>"

    form_type = form["type"]
    type_labels = {
        "mute": "MUTE",
        "kick": "KICK",
        "ban": "BAN",
    }
    label = type_labels.get(form_type, form_type.upper())
    type_russian = _type_to_russian(form_type)
    duration = _format_duration_human(form["duration"])
    reason = form.get("reason", "Не указана")

    target_name = form.get("target_name", "Не указано")
    target_id_match = re.search(r'<@!?(\d+)>', target_name)
    target_id = int(target_id_match.group(1)) if target_id_match else None
    target_member = guild.get_member(target_id) if target_id else None
    target_value = f"{target_member.mention} `[{target_member.id}]`" if target_member else target_name

    embed = discord.Embed(color=8647000)
    embed.set_author(name=label)
    embed.add_field(name="Модератор", value=f"{author_mention} `[{form['author_id']}]`", inline=False)
    embed.add_field(name="Нарушитель", value=target_value, inline=False)
    embed.add_field(name="Тип наказания", value=f"**{type_russian}**", inline=False)
    embed.add_field(name="Срок", value=duration, inline=False)
    embed.add_field(name="Причина", value=f"`{reason}`", inline=False)
    proof_url = form.get("proof_url")
    if proof_url:
        embed.add_field(name="Доказательства", value=f"[Кликнуть для просмотра]({proof_url})", inline=False)

    settings = await db.get_settings(guild.id)
    approve_roles = json.loads(settings.get("form_approve_roles") or "[]")
    if approve_roles:
        content = " ".join(f"<@&{r}>" for r in approve_roles)
    else:
        content = "<@&1538965783311290469>"

    view = FormActionsView(guild.id, form["id"])
    await channel.send(content=content, embed=embed, view=view)

async def _display_forms(interaction: discord.Interaction, forms: list):
    if not forms:
        return
    channel = interaction.channel
    if channel is None:
        return

    for i, form in enumerate(forms):
        await _send_single_form(form, channel)
        if i < len(forms) - 1:
            await asyncio.sleep(1.5)

class NotifTextModal(discord.ui.Modal, title="Оповещение от имени бота"):
    outside_text = discord.ui.TextInput(
        label="Текст вне эмбеда (@everyone и т.д.)",
        style=discord.TextStyle.short,
        placeholder="Например: @everyone или <@&1537451548622332025> (необязательно)",
        required=False,
        max_length=500,
    )
    embed_text = discord.ui.TextInput(
        label="Текст внутри эмбеда (Markdown)",
        style=discord.TextStyle.paragraph,
        placeholder="Введите текст новости / обновления...",
        max_length=4000,
        required=True,
    )

    def __init__(self, bot: "ModerBot"):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        outside_val = str(self.outside_text).strip() if self.outside_text else ""
        embed_val = str(self.embed_text).strip()
        guild_id = 1070704320951095296
        guild = self.bot.get_guild(guild_id) or interaction.guild
        if not guild:
            await interaction.response.send_message(embed=error_embed("Сервер не найден."), ephemeral=True)
            return

        view = NotifChannelSelectView(self.bot, guild, outside_val, embed_val)
        desc_preview = f"**Вне эмбеда:** {outside_val}\n\n**Внутри эмбеда:**\n{embed_val[:400]}..." if outside_val else f"**Внутри эмбеда:**\n{embed_val[:500]}..."
        await interaction.response.send_message(
            embed=discord.Embed(
                title="📣 Выбор канала для отправки",
                description=f"**Предпросмотр:**\n{desc_preview}\n\nВыберите канал из меню ниже:",
                color=Config.EMBED_COLOR_MAIN
            ),
            view=view,
            ephemeral=True
        )

class NotifChannelSelectView(discord.ui.View):
    def __init__(self, bot: "ModerBot", guild: discord.Guild, outside_text: str, embed_text: str):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.outside_text = outside_text
        self.embed_text = embed_text

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Выберите текстовый канал...")
    async def channel_select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        selected_item = select.values[0]
        channel_id = selected_item.id if hasattr(selected_item, "id") else int(selected_item)

        channel = interaction.guild.get_channel(channel_id) if interaction.guild else None
        if channel is None and self.guild:
            channel = self.guild.get_channel(channel_id)
        if channel is None and interaction.client:
            channel = interaction.client.get_channel(channel_id)
        if channel is None and interaction.guild:
            try:
                channel = await interaction.guild.fetch_channel(channel_id)
            except Exception:
                pass

        if not channel or not hasattr(channel, "send"):
            await interaction.response.send_message(embed=error_embed("Не удалось получить текстовый канал."), ephemeral=True)
            return

        try:
            embed = discord.Embed(
                description=self.embed_text,
                color=Config.EMBED_COLOR_MAIN,
                timestamp=datetime.now(timezone.utc)
            )

            content = self.outside_text if self.outside_text else None
            await channel.send(content=content, embed=embed)
            await interaction.response.edit_message(
                embed=success_embed(f"Оповещение успешно отправлено в канал {channel.mention}!"),
                view=None
            )
        except Exception as e:
            await interaction.response.send_message(embed=error_embed(f"Ошибка при отправке: {e}"), ephemeral=True)

class ModerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True                                                      
        intents.presences = False                                                    
        intents.message_content = True                             

        member_cache = discord.MemberCacheFlags.from_intents(intents)

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            member_cache_flags=member_cache,
            max_messages=50,                                                          
            chunk_guilds_at_startup=False,                                           
        )
        self.db = db

    async def setup_hook(self):
        global bot_loop
        bot_loop = asyncio.get_running_loop()
        await db.connect()

        self.add_view(TicketPanelView(self))
        self.add_view(TicketControlView(self))
        self.add_view(TicketDeleteView(self))
        self.add_view(InactivityFormView())
        self.add_view(ShopFormView())
        self.add_view(ShopReviewView())
        self.add_view(RoleRequestPanelFormView())
        self.add_view(RoleRequestReviewView())

        if getattr(self, "_tg_started", False) is False:
            self._tg_started = True
            if TG_AVAILABLE and Config.TG_TOKEN:
                tg_thread = threading.Thread(target=run_telegram, daemon=True, name="TG-Thread")
                tg_thread.start()
                log.info("Telegram-панель запущена в фоновом потоке")
            else:
                log.warning("Telegram-панель отключена (нет python-telegram-bot или TG_TOKEN)")

        asyncio.create_task(ensure_inactivity_form_message(self))
        asyncio.create_task(ensure_shop_form_message(self))
        asyncio.create_task(ensure_role_request_form_message(self))


        register_commands(self.tree)

        guild_id = 1070704320951095296
        try:
            self.tree.copy_global_to(guild=discord.Object(id=guild_id))
            await self.tree.sync(guild=discord.Object(id=guild_id))
            log.info("Слэш-команды мгновенно синхронизированы для гильдии %s.", guild_id)
        except Exception as e:
            log.warning("Ошибка гильдийной синхронизации: %s", e)

        await self.tree.sync()
        log.info("Слэш-команды подготовлены и глобально синхронизированы.")

        self.punishment_watcher.start()


    async def close(self):
        await super().close()

    @tasks.loop(seconds=30)
    async def punishment_watcher(self):
        try:
            due = await db.get_due_punishments()
        except Exception as exc:                
            log.error("Ошибка чтения наказаний: %s", exc)
            return

        for punishment in due:
            guild = self.get_guild(punishment["guild_id"])
            if guild is None:
                await db.deactivate_punishment(punishment["id"])
                continue
            if punishment["type"] == "ban":
                try:
                    await guild.unban(discord.Object(id=punishment["user_id"]), reason="Истёк срок временного бана")
                    log.info("Автоматически разбанен %s на сервере %s", punishment["user_id"], guild.id)
                except discord.HTTPException:
                    pass
            await db.deactivate_punishment(punishment["id"])

    @punishment_watcher.before_loop
    async def before_punishment_watcher(self):
        await self.wait_until_ready()

    async def create_ticket_channel(self, interaction: discord.Interaction, topic: str):
        await interaction.response.send_message(embed=ticket_creating_embed(), ephemeral=True)

        guild = interaction.guild
        settings = await db.get_settings(guild.id)
        raw_cat = settings.get("ticket_category_id") or Config.DEFAULT_TICKET_CATEGORY_ID
        category = await get_ticket_category(guild, raw_cat)

        number = await db.next_ticket_number(guild.id)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        mod_role_ids = settings["command_role_map"].get("ticket_take", [])
        role_mentions = []
        for role_id in mod_role_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
                role_mentions.append(role.mention)

        channel = await guild.create_text_channel(
            name=f"ticket-{number}",
            category=category if isinstance(category, discord.CategoryChannel) else None,
            overwrites=overwrites,
            topic=f"Тикет #{number} | Автор: {interaction.user.name} | Тема: {topic}",
        )

        ticket_id = await db.create_ticket(guild.id, channel.id, number, interaction.user.id, topic)

        embed = ticket_channel_embed(interaction.user, topic)
        content = f"`[ ⌛ | Ожидание ]` {interaction.user.mention}, `ваш тикет был передан на рассмотрение`"
        if role_mentions:
            content += f" {' '.join(role_mentions)}"

        await channel.send(
            content=content,
            embed=embed,
            view=TicketControlView(self),
        )
        await interaction.followup.send(
            embed=success_embed(f"Тикет создан: {channel.mention}"), ephemeral=True
        )
        log.info("Тикет #%s создан пользователем %s (%s)", number, interaction.user, ticket_id)

        log_ticket_created = discord.Embed(
            title=f"🎫 Создан тикет #{number}",
            color=Config.EMBED_COLOR_SUCCESS,
            timestamp=datetime.now(timezone.utc)
        )
        log_ticket_created.add_field(name="👤 Автор", value=person_text(interaction.user), inline=False)
        log_ticket_created.add_field(name="📍 Канал", value=channel.mention, inline=False)
        log_ticket_created.add_field(name="📝 Тема", value=f"`{topic or 'Не указана'}`", inline=False)
        log_ticket_created.set_footer(text=f"ID тикета: {ticket_id}")
        await send_log(guild, "tickets", log_ticket_created)

    async def handle_ticket_take(self, interaction: discord.Interaction):
        ticket = await db.get_ticket_by_channel(interaction.channel_id)
        if ticket is None:
            await interaction.response.send_message(embed=error_embed("Тикет не найден в базе данных."), ephemeral=True)
            return
        if ticket["status"] != "open":
            await interaction.response.send_message(embed=error_embed("Тикет уже взят или закрыт."), ephemeral=True)
            return
        allowed, err = await has_mod_permission(interaction.guild_id, interaction.user, "ticket_take")
        if not allowed:
            await send_check_error(interaction, err or NotRegisteredError())
            return

        await db.update_ticket(ticket["ticket_id"], moderator_id=interaction.user.id, status="taken")
        await db.increment_stat(interaction.guild_id, interaction.user.id, "tickets", 1)

        author = interaction.guild.get_member(ticket["author_id"]) or await self.fetch_user(ticket["author_id"])
        author_mention = author.mention if author else f"<@{ticket['author_id']}>"

        taken_content = f"`[ 🔮 | В обработке ]` {author_mention}, `ваш тикет принят в обработку модератором` {interaction.user.mention}"
        await interaction.response.send_message(content=taken_content)

        log_ticket_taken = discord.Embed(
            title=f"🎫 Тикет #{ticket['number']} принят в обработку",
            color=Config.EMBED_COLOR_MAIN,
            timestamp=datetime.now(timezone.utc)
        )
        log_ticket_taken.add_field(name="🛡️ Модератор", value=person_text(interaction.user), inline=False)
        log_ticket_taken.add_field(name="👤 Автор", value=author_mention, inline=False)
        log_ticket_taken.add_field(name="📍 Канал", value=interaction.channel.mention, inline=False)
        log_ticket_taken.set_footer(text=f"ID тикета: {ticket['ticket_id']}")
        await send_log(interaction.guild, "tickets", log_ticket_taken)

    async def handle_ticket_close(self, interaction: discord.Interaction):
        ticket = await db.get_ticket_by_channel(interaction.channel_id)
        if ticket is None:
            await interaction.response.send_message(embed=error_embed("Тикет не найден в базе данных."), ephemeral=True)
            return
        if ticket["status"] in ("closed", "closing"):
            await interaction.response.send_message(embed=error_embed("Тикет уже закрывается или закрыт."), ephemeral=True)
            return

        is_author = interaction.user.id == ticket["author_id"]
        is_mod = await db.is_registered(interaction.guild_id, interaction.user.id) or is_admin_member(interaction.user)
        if not (is_author or is_mod):
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return

        await db.update_ticket(ticket["ticket_id"], status="closing")

        await interaction.response.send_message(embed=success_embed("Закрываю тикет..."), ephemeral=True)

        author = interaction.guild.get_member(ticket["author_id"]) or await self.fetch_user(ticket["author_id"])
        author_mention = author.mention if author else f"<@{ticket['author_id']}>"

        close_content = f"`[ 🔒 | Закрытие ]` {author_mention}, `тикет закрыт модератором` {interaction.user.mention}" if is_mod else f"`[ 🔒 | Закрытие ]` {author_mention}, `тикет закрыт автором`"
        await interaction.channel.send(content=close_content)

        await self.archive_ticket_by_id(ticket["ticket_id"])

    async def handle_ticket_rating(self, interaction: discord.Interaction, ticket_id: int, rating: str):
        cur = await db._conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
        ticket = await cur.fetchone()
        if ticket and dict(ticket).get("rating"):
            await interaction.response.send_message("Вы уже оценили этот тикет!", ephemeral=True)
            return

        await db.update_ticket(ticket_id, rating=rating)

        emoji = "👍" if rating == "like" else "👎"
        await interaction.response.edit_message(
            content=f"Спасибо за оценку! {emoji}", embed=None, view=None
        )

    async def archive_ticket_by_id(self, ticket_id: int):
        cur = await db._conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
        ticket = await cur.fetchone()
        if ticket is None or ticket["status"] == "closed":
            return

        channel = self.get_channel(ticket["channel_id"])
        if channel is None:
            try:
                channel = await self.fetch_channel(ticket["channel_id"])
            except Exception:
                return

        guild = channel.guild
        settings = await db.get_settings(guild.id)
        raw_closed_cat = settings.get("closed_category_id") or Config.DEFAULT_CLOSED_CATEGORY_ID
        closed_category = await get_ticket_category(guild, raw_closed_cat)

        await db.update_ticket(
            ticket_id, status="closed", closed_at=datetime.now(timezone.utc).isoformat()
        )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        author = guild.get_member(ticket["author_id"]) or await self.fetch_user(ticket["author_id"])
        if author and isinstance(author, discord.Member):
            overwrites[author] = discord.PermissionOverwrite(view_channel=False)

        admin_role = guild.get_role(1537451548622332025)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            await channel.edit(
                category=closed_category if isinstance(closed_category, discord.CategoryChannel) else channel.category,
                overwrites=overwrites,
                name=f"closed-{ticket['number']}",
            )
        except discord.HTTPException as exc:
            log.warning("Не удалось переместить канал тикета: %s", exc)

        messages = [m async for m in channel.history(limit=1000, oldest_first=True)]
        transcript_buf = generate_ticket_html(channel, messages, ticket["number"])
        file_attachment = discord.File(fp=transcript_buf, filename=f"ticket-{ticket['number']}.html")

        archive_embed = discord.Embed(
            title="🔒 Тикет закрыт",
            description="Тикет перемещён в архив. Лог переписки прикреплён ниже.",
            color=Config.EMBED_COLOR_MAIN,
        )
        archive_embed.timestamp = datetime.now(timezone.utc)
        await channel.send(
            embed=archive_embed,
            file=file_attachment,
            view=TicketDeleteView(self),
        )

        log_ticket_closed = discord.Embed(
            title=f"🔒 Тикет #{ticket['number']} закрыт",
            color=Config.EMBED_COLOR_MAIN,
            timestamp=datetime.now(timezone.utc)
        )
        log_ticket_closed.add_field(name="👤 Автор", value=person_text(author) if author else f"<@{ticket['author_id']}>", inline=False)
        mod_user = (guild.get_member(ticket["moderator_id"]) or await self.fetch_user(ticket["moderator_id"])) if ticket["moderator_id"] else None
        log_ticket_closed.add_field(name="🛡️ Модератор", value=person_text(mod_user) if mod_user else "Не назначен", inline=False)
        log_ticket_closed.add_field(name="📝 Тема", value=f"`{ticket['topic'] or 'Не указана'}`", inline=False)
        log_ticket_closed.set_footer(text=f"ID тикета: {ticket['ticket_id']}")

        log_transcript_buf = generate_ticket_html(channel, messages, ticket["number"])
        log_file = discord.File(fp=log_transcript_buf, filename=f"ticket-{ticket['number']}.html")
        await send_log(guild, "tickets", log_ticket_closed, file=log_file)

        if ticket["moderator_id"] and author:
            await channel.send(
                embed=rating_request_embed(author),
                view=TicketRatingView(self, ticket["ticket_id"], ticket["author_id"]),
            )

    async def handle_ticket_delete(self, interaction: discord.Interaction):
        ticket = await db.get_ticket_by_channel(interaction.channel_id)
        is_mod = await db.is_registered(interaction.guild_id, interaction.user.id) or is_admin_member(interaction.user)
        if not is_mod:
            await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
            return
        await interaction.response.send_message(embed=success_embed("Тикет будет удалён через 3 секунды..."))
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Тикет удалён модератором {interaction.user}")
        except discord.HTTPException as exc:
            log.warning("Не удалось удалить канал тикета: %s", exc)

INACTIVITY_CHANNEL_ID = 1369391085478219807
INACTIVITY_REVIEWER_ROLE_ID = 1538965783311290469

class InactivityApplyModal(discord.ui.Modal, title="Заявка на неактив"):
    reason_input = discord.ui.TextInput(
        label="Причина неактива",
        style=discord.TextStyle.paragraph,
        placeholder="Укажите причину неактива...",
        required=True,
        max_length=1000
    )
    start_date_input = discord.ui.TextInput(
        label="Дата начала (ДД.ММ.ГГГГ)",
        style=discord.TextStyle.short,
        placeholder="Пример: 15.09.2026",
        required=True,
        max_length=20
    )
    end_date_input = discord.ui.TextInput(
        label="Дата окончания (ДД.ММ.ГГГГ)",
        style=discord.TextStyle.short,
        placeholder="Пример: 22.09.2026",
        required=True,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason_input.value.strip()
        start_date = self.start_date_input.value.strip()
        end_date = self.end_date_input.value.strip()

        inactivity_id = await db.add_inactivity(
            interaction.guild_id, interaction.user.id, start_date, end_date, reason
        )

        await interaction.response.send_message(
            embed=success_embed("Ваша заявка на неактив отправлена на рассмотрение."),
            ephemeral=True
        )

        try:
            dm_embed = discord.Embed(
                title="Заявка на неактив отправлена",
                description="Ваша заявка на неактив отправлена на рассмотрение руководству.",
                color=Config.EMBED_COLOR_MAIN,
                timestamp=datetime.now(timezone.utc)
            )
            dm_embed.add_field(name="Модератор", value=user_id_tag(interaction.user), inline=False)
            dm_embed.add_field(name="Сроки", value=f"с `{start_date}` по `{end_date}`", inline=True)
            dm_embed.add_field(name="Причина", value=f"`{reason}`", inline=False)
            await interaction.user.send(embed=dm_embed)
        except Exception as exc:
            log.info("Не удалось отправить сообщение в ЛС об отправке неактива: %s", exc)

        ch = interaction.guild.get_channel(INACTIVITY_CHANNEL_ID) if interaction.guild else None
        if ch and isinstance(ch, discord.TextChannel):
            rev_embed = discord.Embed(
                title="Новая заявка на неактив",
                color=Config.EMBED_COLOR_WARNING,
                timestamp=datetime.now(timezone.utc)
            )
            rev_embed.add_field(name="Модератор", value=user_id_tag(interaction.user), inline=False)
            rev_embed.add_field(name="Период неактива", value=f"с `{start_date}` по `{end_date}`", inline=True)
            rev_embed.add_field(name="Причина", value=f"`{reason}`", inline=False)
            rev_embed.add_field(name="Статус", value="`На рассмотрении`", inline=False)

            view = InactivityReviewView(inactivity_id, interaction.user.id, start_date, end_date, reason)
            await ch.send(content="<@&1538965783311290469>", embed=rev_embed, view=view)


class InactivityFormView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Подать заявку", style=discord.ButtonStyle.primary, custom_id="inactivity_apply_btn")
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InactivityApplyModal())


class InactivityRejectReasonModal(discord.ui.Modal, title="Причина отказа в неактиве"):
    reject_reason_input = discord.ui.TextInput(
        label="Причина отказа",
        style=discord.TextStyle.paragraph,
        placeholder="Укажите причину отказа...",
        required=True,
        max_length=500
    )

    def __init__(self, inactivity_id: int, user_id: int, start_date: str, end_date: str, orig_message: discord.Message):
        super().__init__()
        self.inactivity_id = inactivity_id
        self.user_id = user_id
        self.start_date = start_date
        self.end_date = end_date
        self.orig_message = orig_message

    async def on_submit(self, interaction: discord.Interaction):
        reject_reason = self.reject_reason_input.value.strip()

        await db.update_inactivity_status(self.inactivity_id, "rejected", interaction.user.id, reject_reason)

        embed = self.orig_message.embeds[0] if self.orig_message.embeds else discord.Embed(title="Заявка на неактив")
        embed.color = Config.EMBED_COLOR_ERROR
        for idx, field in enumerate(embed.fields):
            if field.name == "Статус":
                embed.set_field_at(idx, name="Статус", value=f"Отказано (Проверил: {interaction.user.mention})", inline=False)
                break
        embed.add_field(name="Причина отказа", value=f"`{reject_reason}`", inline=False)

        await self.orig_message.edit(content=None, embed=embed, view=None)

        await interaction.response.send_message(
            embed=error_embed(f"Заявка на неактив отклонена. Причина: {reject_reason}"),
            ephemeral=True
        )

        target_user = interaction.guild.get_member(self.user_id) if interaction.guild else None
        if not target_user:
            try:
                target_user = await interaction.client.fetch_user(self.user_id)
            except Exception:
                pass

        if target_user:
            try:
                dm_embed = discord.Embed(
                    title="Заявка на неактив отклонена",
                    description="Ваша заявка на неактив была отклонена руководством.",
                    color=Config.EMBED_COLOR_ERROR,
                    timestamp=datetime.now(timezone.utc)
                )
                dm_embed.add_field(name="Модератор", value=user_id_tag(self.user_id), inline=False)
                dm_embed.add_field(name="Причина отказа", value=f"`{reject_reason}`", inline=False)
                dm_embed.add_field(name="Проверил", value=user_id_tag(interaction.user), inline=False)
                await target_user.send(embed=dm_embed)
            except Exception as e:
                log.info("Не удалось отправить сообщение в ЛС об отказе неактива %s: %s", self.user_id, e)


class InactivityReviewView(discord.ui.View):
    def __init__(self, inactivity_id: int, user_id: int, start_date: str, end_date: str, reason: str):
        super().__init__(timeout=None)
        self.inactivity_id = inactivity_id
        self.user_id = user_id
        self.start_date = start_date
        self.end_date = end_date
        self.reason = reason

    def _has_permission(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True
        return any(role.id == INACTIVITY_REVIEWER_ROLE_ID for role in member.roles)

    @discord.ui.button(label="Одобрить", style=discord.ButtonStyle.success, custom_id="inact_approve_btn")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not self._has_permission(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Недостаточно прав для рассмотрения заявок."),
                ephemeral=True
            )
            return

        await db.update_inactivity_status(self.inactivity_id, "approved", interaction.user.id)

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed(title="Заявка на неактив")
        embed.color = Config.EMBED_COLOR_SUCCESS
        for idx, field in enumerate(embed.fields):
            if field.name == "Статус":
                embed.set_field_at(idx, name="Статус", value=f"Одобрено (Проверил: {interaction.user.mention})", inline=False)
                break

        await interaction.message.edit(content=None, embed=embed, view=None)

        await interaction.response.send_message(
            embed=success_embed("Заявка на неактив успешно одобрена!"),
            ephemeral=True
        )

        target_user = interaction.guild.get_member(self.user_id) if interaction.guild else None
        if not target_user:
            try:
                target_user = await interaction.client.fetch_user(self.user_id)
            except Exception:
                pass

        if target_user:
            try:
                dm_embed = discord.Embed(
                    title="Заявка на неактив одобрена",
                    description="Ваша заявка на неактив успешно одобрена руководством.",
                    color=Config.EMBED_COLOR_SUCCESS,
                    timestamp=datetime.now(timezone.utc)
                )
                dm_embed.add_field(name="Модератор", value=user_id_tag(self.user_id), inline=False)
                dm_embed.add_field(name="Сроки неактива", value=f"с `{self.start_date}` по `{self.end_date}`", inline=True)
                dm_embed.add_field(name="Проверил", value=user_id_tag(interaction.user), inline=False)
                await target_user.send(embed=dm_embed)
            except Exception as e:
                log.info("Не удалось отправить сообщение в ЛС об одобрении неактива %s: %s", self.user_id, e)

    @discord.ui.button(label="Отказать", style=discord.ButtonStyle.danger, custom_id="inact_reject_btn")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not self._has_permission(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Недостаточно прав для рассмотрения заявок."),
                ephemeral=True
            )
            return

        modal = InactivityRejectReasonModal(self.inactivity_id, self.user_id, self.start_date, self.end_date, interaction.message)
        await interaction.response.send_modal(modal)


async def ensure_inactivity_form_message(bot_client: commands.Bot):
    try:
        ch = bot_client.get_channel(INACTIVITY_CHANNEL_ID)
        if not ch:
            try:
                ch = await bot_client.fetch_channel(INACTIVITY_CHANNEL_ID)
            except Exception:
                ch = None

        if not ch or not isinstance(ch, discord.TextChannel):
            log.warning("Канал неактива %s не найден", INACTIVITY_CHANNEL_ID)
            return

        form_exists = False
        try:
            async for msg in ch.history(limit=20):
                if msg.author.id == bot_client.user.id and msg.embeds:
                    if "Заявка на неактив" in (msg.embeds[0].title or ""):
                        form_exists = True
                        break
        except Exception as h_err:
            log.warning("Ошибка чтения истории канала неактива: %s", h_err)

        if not form_exists:
            embed = discord.Embed(
                title="Заявка на неактив",
                description="Нажмите кнопку ниже, чтобы подать заявку на неактив.",
                color=Config.EMBED_COLOR_MAIN
            )
            await ch.send(embed=embed, view=InactivityFormView())
            log.info("Форма неактива успешно отправлена в канал %s", INACTIVITY_CHANNEL_ID)
        else:
            log.info("Форма неактива уже присутствует в канале %s", INACTIVITY_CHANNEL_ID)
    except Exception as e:
        log.error("Ошибка при отправке формы неактива: %s", e)


SHOP_CHANNEL_ID = 1548400124982726666
SHOP_REVIEWER_ROLE_ID = 1538965783311290469
GIVECOIN_LOG_CHANNEL_ID = 1405637785582567564
CREATEROLE_ABOVE_ROLE_ID = 1369357888342069468

SHOP_ITEMS = {
    "inactivity_1d": {
        "name": "Неактив 1 день",
        "price": 80,
        "description": "Снимает активность за 1 день неактива"
    },
    "inactivity_3d": {
        "name": "Неактив 3 дня",
        "price": 200,
        "description": "Освобождение от активности на 3 дня"
    },
    "inactivity_7d": {
        "name": "Неактив 7 дней",
        "price": 400,
        "description": "Неделя неактива"
    },
    "remove_oral_vig": {
        "name": "Снятие устного выговора",
        "price": 200,
        "description": "Удаляет 1 устный выговор"
    },
    "remove_strict_vig": {
        "name": "Снятие строгого выговора",
        "price": 350,
        "description": "Удаляет 1 строгий выговор"
    },
    "custom_nick": {
        "name": "Пользовательский ник",
        "price": 700,
        "description": "Смена ника"
    },
    "custom_role": {
        "name": "Личная роль",
        "price": 500,
        "description": "Личная роль"
    }
}


class CustomRoleModal(discord.ui.Modal, title="Покупка личной роли"):
    role_name = discord.ui.TextInput(
        label="Название роли",
        placeholder="Введите название личной роли...",
        required=True,
        max_length=100
    )
    hex_color = discord.ui.TextInput(
        label="Цвет роли (HEX)",
        placeholder="Пример: #FF5733 или FF5733",
        default="#FF5733",
        required=True,
        max_length=10
    )
    role_icon = discord.ui.TextInput(
        label="Иконка роли (URL картинки до 256КБ)",
        placeholder="Прямая ссылка на файл иконки (до 256 КБ) или оставьте пустым...",
        required=False,
        max_length=500
    )

    def __init__(self, item_key: str):
        super().__init__()
        self.item_key = item_key

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        if not guild or not isinstance(user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Ошибка контекста."), ephemeral=True)
            return

        item = SHOP_ITEMS.get(self.item_key)
        if not item:
            await interaction.response.send_message(embed=error_embed("Товар не найден."), ephemeral=True)
            return

        r_name = self.role_name.value.strip()
        h_color = self.hex_color.value.strip().lstrip("#")
        r_icon = self.role_icon.value.strip() if self.role_icon.value else ""
        try:
            int(h_color, 16)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(f"Неверный HEX-цвет: `#{h_color}`. Пример: `#FF5733` или `FF5733`."),
                ephemeral=True
            )
            return

        user_coins = await db.get_swag_coins(guild.id, user.id)
        if user_coins < item["price"]:
            await interaction.response.send_message(
                embed=error_embed(f"Недостаточно **SWAG Coins**!\n\nВаш баланс: `{user_coins} SC`\nТребуется: `{item['price']} SC`"),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=success_embed(f"Заявка на покупку личной роли **{r_name}** ({item['price']} SC) успешно отправлена руководству!"),
            ephemeral=True
        )

        ch = guild.get_channel(SHOP_CHANNEL_ID) or interaction.channel
        if ch and isinstance(ch, discord.TextChannel):
            embed = discord.Embed(
                title="Заявка на покупку товара",
                color=Config.EMBED_COLOR_MAIN,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="Покупатель", value=user.mention, inline=True)
            embed.add_field(name="Товар", value=f"**{item['name']}**", inline=True)
            embed.add_field(name="Название роли", value=f"`{r_name}`", inline=True)
            embed.add_field(name="Цвет (HEX)", value=f"`#{h_color.upper()}`", inline=True)
            embed.add_field(name="Иконка роли", value=f"`{r_icon}`" if r_icon else "Не указана", inline=False)
            embed.add_field(name="Стоимость", value=f"**{item['price']} SC**", inline=True)
            embed.add_field(name="Текущий баланс", value=f"`{user_coins} SC`", inline=True)
            embed.add_field(name="Статус", value="В ожидании проверки", inline=False)

            await ch.send(
                content=f"<@&{SHOP_REVIEWER_ROLE_ID}>",
                embed=embed,
                view=ShopReviewView(user_id=user.id, item_key=self.item_key)
            )



class ShopRejectReasonModal(discord.ui.Modal, title="Причина отказа"):
    reject_reason = discord.ui.TextInput(
        label="Причина отказа",
        style=discord.TextStyle.paragraph,
        placeholder="Укажите причину отказа...",
        required=True,
        max_length=1000
    )

    def __init__(self, target_user_id: int, item_name: str, message: discord.Message):
        super().__init__()
        self.target_user_id = target_user_id
        self.item_name = item_name
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        reason_text = self.reject_reason.value.strip()

        embed = self.message.embeds[0] if self.message.embeds else discord.Embed(title="Заявка на покупку товара")
        embed.color = Config.EMBED_COLOR_ERROR
        for idx, field in enumerate(embed.fields):
            if field.name == "Статус":
                embed.set_field_at(
                    idx,
                    name="Статус",
                    value=f"❌ Отклонено (Проверил: {interaction.user.mention})\n**Причина отказа:** {reason_text}",
                    inline=False
                )
                break

        await self.message.edit(content=None, embed=embed, view=None)

        await interaction.followup.send(
            embed=error_embed(f"Заявка на покупку {self.item_name} была отклонена."),
            ephemeral=True
        )

        if self.target_user_id:
            try:
                target_user = await interaction.client.fetch_user(self.target_user_id)
                if target_user:
                    dm_embed = discord.Embed(
                        title="🛒 Покупка в магазине отклонена",
                        description=f"Ваша заявка на покупку товара **{self.item_name}** была отклонена руководством.",
                        color=Config.EMBED_COLOR_ERROR,
                        timestamp=datetime.now(timezone.utc)
                    )
                    dm_embed.add_field(name="Причина отказа", value=f"`{reason_text}`", inline=False)
                    dm_embed.add_field(name="Проверил", value=interaction.user.mention, inline=False)
                    await target_user.send(embed=dm_embed)
            except Exception as dm_err:
                log.info("Не удалось отправить ЛС покупателю %s: %s", self.target_user_id, dm_err)


class ShopSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for key, item in SHOP_ITEMS.items():
            options.append(
                discord.SelectOption(
                    label=item["name"],
                    value=key,
                    description=f"{item['price']} SC | {item['description']}"
                )
            )
        super().__init__(
            placeholder="Выберите товар для покупки...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="shop_item_select"
        )

    async def callback(self, interaction: discord.Interaction):
        item_key = self.values[0]
        item = SHOP_ITEMS.get(item_key)
        if not item:
            await interaction.response.send_message(embed=error_embed("Товар не найден."), ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user
        if not guild or not isinstance(user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Ошибка контекста."), ephemeral=True)
            return

        if item_key == "custom_role":
            await interaction.response.send_modal(CustomRoleModal(item_key))
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if item_key in ("remove_oral_vig", "remove_strict_vig"):
            vig_type = "strict" if item_key == "remove_strict_vig" else "oral"
            col = "strict_vigs" if vig_type == "strict" else "oral_vigs"
            mod_info = await db.get_moderator(guild.id, user.id)
            if not mod_info or dict(mod_info).get(col, 0) <= 0:
                await interaction.followup.send(
                    embed=error_embed(f"У вас нет {'строгих' if vig_type == 'strict' else 'устных'} выговоров для снятия!"),
                    ephemeral=True
                )
                return

        if item_key in ("inactivity_1d", "inactivity_3d", "inactivity_7d"):
            active_inact = await db.get_active_inactivity(guild.id, user.id)
            if active_inact:
                await interaction.followup.send(
                    embed=error_embed("У вас уже есть активный неактив! Нельзя купить еще один, пока действующий не завершится."),
                    ephemeral=True
                )
                return

        user_coins = await db.get_swag_coins(guild.id, user.id)
        if user_coins < item["price"]:
            await interaction.followup.send(
                embed=error_embed(f"Недостаточно **SWAG Coins**!\n\nВаш баланс: `{user_coins} SC`\nТребуется: `{item['price']} SC`"),
                ephemeral=True
            )
            return

        # Покупка товара
        await db.remove_swag_coins(guild.id, user.id, item["price"])

        await interaction.followup.send(
            embed=success_embed(f"Покупка товара **{item['name']}** ({item['price']} SC) оформлена!"),
            ephemeral=True
        )

        ch = guild.get_channel(SHOP_CHANNEL_ID) or interaction.channel
        if ch and isinstance(ch, discord.TextChannel):
            embed = discord.Embed(
                title="Заявка на покупку товара",
                color=Config.EMBED_COLOR_MAIN,
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="Покупатель", value=user.mention, inline=True)
            embed.add_field(name="Товар", value=f"**{item['name']}**", inline=True)
            embed.add_field(name="Стоимость", value=f"**{item['price']} SC**", inline=True)
            embed.add_field(name="Статус", value="В ожидании выдачи", inline=False)

            await ch.send(
                content=f"<@&{SHOP_REVIEWER_ROLE_ID}>",
                embed=embed,
                view=ShopReviewView(user_id=user.id, item_key=item_key)
            )


class ShopReviewView(discord.ui.View):
    def __init__(self, user_id: int = 0, item_key: str = ""):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.item_key = item_key

    @discord.ui.button(label="Одобрить", style=discord.ButtonStyle.success, custom_id="shop_approve_btn")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.color = Config.EMBED_COLOR_SUCCESS
            for idx, field in enumerate(embed.fields):
                if field.name == "Статус":
                    embed.set_field_at(idx, name="Статус", value=f"✅ Выдано (Проверил: {interaction.user.mention})", inline=False)
                    break
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(content=None, embed=embed, view=self)
        await interaction.followup.send(embed=success_embed("Покупка одобрена и отмечена."), ephemeral=True)

        if self.user_id:
            try:
                target_user = interaction.guild.get_member(self.user_id) if interaction.guild else None
                if not target_user:
                    target_user = await interaction.client.fetch_user(self.user_id)
                item_info = SHOP_ITEMS.get(self.item_key, {})
                dm_embed = discord.Embed(
                    title="🛒 Покупка одобрена",
                    description=f"Ваша покупка **{item_info.get('name', '')}** одобрена руководством.",
                    color=Config.EMBED_COLOR_SUCCESS,
                    timestamp=datetime.now(timezone.utc)
                )
                dm_embed.add_field(name="Проверил", value=interaction.user.mention, inline=False)
                await target_user.send(embed=dm_embed)
            except Exception as dm_err:
                log.info("Не удалось отправить ЛС покупателю %s: %s", self.user_id, dm_err)

    @discord.ui.button(label="Отказать", style=discord.ButtonStyle.danger, custom_id="shop_reject_btn")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            return
        item_name = ""
        if interaction.message and interaction.message.embeds:
            for field in interaction.message.embeds[0].fields:
                if field.name == "Товар":
                    item_name = field.value
                    break
        modal = ShopRejectReasonModal(target_user_id=self.user_id, item_name=item_name, message=interaction.message)
        await interaction.response.send_modal(modal)


class ShopFormView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ShopSelect())




class RoleRequestReviewView(discord.ui.View):
    def __init__(self, applicant_id: int = 0, role_id: int = 0, category: str = "", rank: int = 0, nick: str = "", fraction_name: str = "", reviewer_id: Optional[int] = None):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.role_id = role_id
        self.category = category
        self.rank = rank
        self.nick = nick
        self.fraction_name = fraction_name
        self.reviewer_id = reviewer_id

    @discord.ui.button(emoji="<:narassmotr:1548570951443292180>", style=discord.ButtonStyle.primary, custom_id="role_req_take")
    async def take_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.reviewer_id and self.reviewer_id != interaction.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=error_embed(f"Заявка уже взята на рассмотрение модератором <@{self.reviewer_id}>!"),
                ephemeral=True
            )
            return

        self.reviewer_id = interaction.user.id
        button.disabled = True
        new_content = f"Взято под рассмотрение модератором {interaction.user.mention}"
        await interaction.message.edit(content=new_content, embeds=interaction.message.embeds, view=self)
        await interaction.response.send_message(
            embed=success_embed("Вы успешно взяли заявку на рассмотрение."),
            ephemeral=True
        )

    @discord.ui.button(emoji="<:approved:1548569825092177950>", style=discord.ButtonStyle.success, custom_id="role_req_approve")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.reviewer_id and self.reviewer_id != interaction.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=error_embed(f"Заявка взята на рассмотрение модератором <@{self.reviewer_id}>! Вы не можете вынести вердикт."),
                ephemeral=True
            )
            return

        guild = interaction.guild
        if not guild:
            return

        target = guild.get_member(self.applicant_id)
        if not target:
            try:
                target = await guild.fetch_member(self.applicant_id)
            except Exception:
                target = None

        if not target:
            await interaction.response.send_message(embed=error_embed("Пользователь не найден на сервере."), ephemeral=True)
            return

        main_role = guild.get_role(self.role_id)
        if main_role:
            try:
                await target.add_roles(main_role, reason=f"Одобрение роли модератором {interaction.user}")
            except Exception as e:
                log.error("Ошибка выдачи основной роли: %s", e)

        extra_role_id = None
        if self.category == "state":
            if self.rank == 9:
                extra_role_id = STATE_RANK_9_ROLE_ID
            elif self.rank == 10:
                extra_role_id = STATE_RANK_10_ROLE_ID
        elif self.category == "illegal":
            if self.rank == 9:
                extra_role_id = ILLEGAL_RANK_9_ROLE_ID
            elif self.rank == 10:
                extra_role_id = ILLEGAL_RANK_10_ROLE_ID

        if extra_role_id:
            ex_role = guild.get_role(extra_role_id)
            if ex_role:
                try:
                    await target.add_roles(ex_role, reason=f"Одобрение лидерской/зам роли модератором {interaction.user}")
                except Exception as e:
                    log.error("Ошибка выдачи доп роли руководства: %s", e)

        if self.category != "admin" and self.rank > 0 and self.nick:
            new_nick = f"[{self.fraction_name} {self.rank}/10] {self.nick}"
            try:
                await target.edit(nick=new_nick[:32])
            except Exception as nick_err:
                log.warning("Не удалось изменить ник пользователю: %s", nick_err)

        try:
            dm_embed = discord.Embed(
                title="Ваша заявка одобрена",
                description=f"Здравствуйте! Ваша заявка на получение роли **{main_role.name if main_role else ''}** была успешно одобрена.\nРоль выдана на сервере.",
                color=Config.EMBED_COLOR_SUCCESS,
                timestamp=datetime.now(timezone.utc)
            )
            await target.send(embed=dm_embed)
        except Exception:
            pass

        await interaction.response.send_message(
            embed=success_embed(f"Роль успешно выдана пользователю {target.mention}."),
            ephemeral=True
        )

        for item in self.children:
            item.disabled = True

        new_content = f"✅ Одобрено модератором {interaction.user.mention}"
        msg_embeds = interaction.message.embeds
        if msg_embeds:
            new_embeds = [emb for emb in msg_embeds if not emb.image or not emb.image.url]
            await interaction.message.edit(content=new_content, embeds=new_embeds, view=self)
        else:
            await interaction.message.edit(content=new_content, view=self)

    @discord.ui.button(emoji="<:otkazano:1548570766306447392>", style=discord.ButtonStyle.danger, custom_id="role_req_reject")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.reviewer_id and self.reviewer_id != interaction.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                embed=error_embed(f"Заявка взята на рассмотрение модератором <@{self.reviewer_id}>! Вы не можете вынести вердикт."),
                ephemeral=True
            )
            return

        target_msg = interaction.message
        await interaction.response.send_modal(RoleRequestRejectModal(self, target_msg=target_msg))


class RoleRequestRejectModal(discord.ui.Modal, title="Причина отказа"):
    reason = discord.ui.TextInput(
        label="Причина отказа",
        style=discord.TextStyle.paragraph,
        placeholder="Укажите причину отказа...",
        required=True,
        max_length=500
    )

    def __init__(self, parent_view: RoleRequestReviewView, target_msg: Optional[discord.Message] = None):
        super().__init__()
        self.parent_view = parent_view
        self.target_msg = target_msg

    async def on_submit(self, interaction: discord.Interaction):
        reject_reason = self.reason.value.strip()
        guild = interaction.guild
        target = guild.get_member(self.parent_view.applicant_id) if guild else None
        if not target and guild:
            try:
                target = await guild.fetch_member(self.parent_view.applicant_id)
            except Exception:
                target = None

        if target:
            try:
                dm_embed = discord.Embed(
                    title="Ваша заявка отклонена",
                    description=f"Здравствуйте! Ваша заявка на получение роли была отклонена.\n**Причина:** {reject_reason}",
                    color=Config.EMBED_COLOR_ERROR,
                    timestamp=datetime.now(timezone.utc)
                )
                await target.send(embed=dm_embed)
            except Exception:
                pass

        for item in self.parent_view.children:
            item.disabled = True

        new_content = f"❌ Отклонено модератором {interaction.user.mention}\n**Причина отказа:** {reject_reason}"
        msg = self.target_msg or interaction.message
        if msg:
            try:
                msg_embeds = msg.embeds
                if msg_embeds:
                    new_embeds = [emb for emb in msg_embeds if not emb.image or not emb.image.url]
                    await msg.edit(content=new_content, embeds=new_embeds, view=self.parent_view)
                else:
                    await msg.edit(content=new_content, view=self.parent_view)
            except Exception as e:
                log.error("Ошибка обновления сообщения при отказе роли: %s", e)

        await interaction.response.send_message(
            embed=success_embed(f"Заявка пользователя <@{self.parent_view.applicant_id}> отклонена."),
            ephemeral=True
        )


async def ensure_shop_form_message(bot_client: commands.Bot):
    try:
        ch = bot_client.get_channel(SHOP_CHANNEL_ID)
        if not ch:
            try:
                ch = await bot_client.fetch_channel(SHOP_CHANNEL_ID)
            except Exception:
                ch = None

        if not ch or not isinstance(ch, discord.TextChannel):
            log.warning("Канал магазина %s не найден", SHOP_CHANNEL_ID)
            return

        form_exists = False
        try:
            async for msg in ch.history(limit=20):
                if msg.author.id == bot_client.user.id and msg.embeds:
                    if "SWAG Moder Shop" in (msg.embeds[0].title or ""):
                        form_exists = True
                        break
        except Exception as h_err:
            log.warning("Ошибка чтения истории канала магазина: %s", h_err)

        if not form_exists:
            embed = discord.Embed(
                title="SWAG Moder Shop",
                description=(
                    "Добро пожаловать в официальный **Модераторский Магазин**!\n\n"
                    "**Валюта:** `Swag Coins (SC)`\n"
                    "**Заработок:** `+5 SC` начисляется автоматически за каждое выданное наказание и удалённое сообщение.\n\n"
                    "**Список товаров:**\n"
                    "• **Неактив 1 день** — `80 SC` (Снимает активность за 1 день)\n"
                    "• **Неактив 3 дня** — `200 SC` (Освобождение от активности на 3 дня)\n"
                    "• **Неактив 7 дней** — `400 SC` (Неделя неактива)\n"
                    "• **Снятие устного выговора** — `200 SC` (Удаляет 1 устный выговор)\n"
                    "• **Снятие строгого выговора** — `350 SC` (Удаляет 1 строгий выговор)\n"
                    "• **Пользовательский ник** — `700 SC` (Смена ника)\n"
                    "• **Личная роль** — `500 SC` (Личная роль)\n\n"
                    "Для покупки выберите товар в выпадающем меню ниже:"
                ),
                color=Config.EMBED_COLOR_MAIN
            )
            await ch.send(embed=embed, view=ShopFormView())
            log.info("Форма магазина успешно отправлена в канал %s", SHOP_CHANNEL_ID)
        else:
            log.info("Форма магазина уже присутствует в канале %s", SHOP_CHANNEL_ID)
    except Exception as e:
        log.error("Ошибка при отправке формы магазина: %s", e)


async def fetch_avatar_image(user: Union[discord.User, discord.Member], size: int = 112) -> Image.Image:
    if PIL_AVAILABLE:
        try:
            url = user.display_avatar.with_size(128).url
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                avatar_bytes = response.read()
            img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            return img
        except Exception as e:
            log.warning("Не удалось загрузить аватар пользователя %s: %s", user.id, e)

    return Image.new("RGBA", (size, size), (40, 50, 70, 255))


def get_font(size: int):
    font_paths = [
        "montserrat.ttf",
        os.path.join(os.path.dirname(__file__), "montserrat.ttf"),
        "arial.ttf",
        os.path.join(os.path.dirname(__file__), "arial.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.truetype("montserrat.ttf", size)
    except Exception:
        return ImageFont.load_default()


def create_stats_image(
    username: str,
    role_title: str,
    avatar_img: Optional[Image.Image],
    stats: dict,
    coins: int
) -> io.BytesIO:
    width, height = 750, 420
    base = Image.new("RGBA", (width, height), (13, 19, 36, 255))
    draw = ImageDraw.Draw(base)

    draw.rectangle([0, 0, width, height], fill=(15, 23, 42, 255))
    card_margin = 20
    draw.rounded_rectangle(
        [card_margin, card_margin, width - card_margin, height - card_margin],
        radius=16,
        fill=(22, 33, 58, 240),
        outline=(56, 89, 148, 255),
        width=2
    )

    if avatar_img:
        base.paste(avatar_img, (50, 45), avatar_img)
        draw.ellipse([48, 43, 152, 147], outline=(88, 166, 255, 255), width=3)
    else:
        draw.ellipse([50, 45, 150, 145], fill=(40, 60, 100, 255), outline=(88, 166, 255, 255), width=2)

    font_title = get_font(24)
    font_role = get_font(16)
    font_label = get_font(14)
    font_val = get_font(22)
    font_coins_val = get_font(24)

    draw.text((170, 52), username[:20], fill=(255, 255, 255, 255), font=font_title)
    draw.text((170, 90), f"🛡️ {role_title}", fill=(88, 166, 255, 255), font=font_role)

    coins_box = [490, 45, 710, 115]
    draw.rounded_rectangle(coins_box, radius=12, fill=(30, 45, 75, 255), outline=(241, 224, 90, 255), width=2)
    draw.text((505, 55), "🪙 SWAG COINS", fill=(241, 224, 90, 255), font=font_label)
    draw.text((505, 78), f"{coins:,} SC".replace(",", " "), fill=(255, 255, 255, 255), font=font_coins_val)

    draw.line([40, 135, 710, 135], fill=(45, 65, 105, 255), width=2)

    stat_items = [
        ("🎟️ Тикеты", str(stats.get("tickets", 0))),
        ("🔇 Муты", str(stats.get("mutes", 0))),
        ("🚪 Кики", str(stats.get("kicks", 0))),
        ("🔨 Баны", str(stats.get("bans", 0))),
        ("⚠️ Варны", str(stats.get("warns", 0))),
        ("🗑️ Сообщения", str(stats.get("deleted_msgs", 0))),
        ("📝 Устные выговоры", str(stats.get("oral_vigs", 0))),
        ("🚫 Строгие выговоры", str(stats.get("strict_vigs", 0))),
    ]

    box_w, box_h = 155, 105
    start_x, start_y = 45, 155
    spacing_x, spacing_y = 15, 15

    for idx, (label, val) in enumerate(stat_items):
        row = idx // 4
        col = idx % 4
        bx = start_x + col * (box_w + spacing_x)
        by = start_y + row * (box_h + spacing_y)

        draw.rounded_rectangle(
            [bx, by, bx + box_w, by + box_h],
            radius=10,
            fill=(16, 25, 46, 255),
            outline=(35, 53, 88, 255),
            width=1
        )
        draw.text((bx + 12, by + 12), label, fill=(139, 148, 158, 255), font=font_label)
        draw.text((bx + 12, by + 50), val, fill=(240, 246, 252, 255), font=font_val)

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ==============================================================================
#                 СИСТЕМА ЗАПРОСА РОЛЕЙ (ROLE REQUEST SYSTEM)
# ==============================================================================
ROLE_REQUEST_FORM_CHANNEL_ID  = 1369358730151333918
ROLE_REQUEST_LOG_CHANNEL_ID   = 1369358925337460746
ROLE_REQUEST_REVIEWER_ROLE_ID = 1369357665557414028


ROLE_REQUEST_OPTIONS = [
    # (role_id, label, category, short_tag)
    (1369357752660525086, "Покупной Администратор", "admin", "Администратор"),
    # Госс
    (1467254707079872643, "Суд", "state", "Суд"),
    (1389570083394949234, "Правительство", "state", "Право"),
    (1377891838001676399, "FBI", "state", "FBI"),
    (1369357800114884739, "RCSD", "state", "RCSD"),
    (1369357803910598786, "LSPD", "state", "LSPD"),
    (1369357786173145098, "LVPD", "state", "LVPD"),
    (1369357791575146616, "SFPD", "state", "SFPD"),
    (1369357840833318993, "Армия", "state", "Армия"),
    (1369357860642750515, "Больница", "state", "МЗ"),
    # Нелегальные
    (1369357815944056983, "Grove Street", "illegal", "Grove"),
    (1369357806808858704, "Ballas", "illegal", "Ballas"),
    (1369357812903313580, "Rifa", "illegal", "Rifa"),
    (1369357818385404004, "Vagos", "illegal", "Vagos"),
    (1369357809505927178, "Aztecas", "illegal", "Aztecas"),
    (1369357821812150433, "Night Wolfs", "illegal", "NW"),
    (1369357827516137512, "Yakuza", "illegal", "Yakuza"),
    (1369357831127564340, "Russian Mafia", "illegal", "RM"),
    (1369357837490192425, "La Cosa Nostra", "illegal", "LCN"),
    (1369357843878117446, "Warlock MC", "illegal", "WMC"),
]

STATE_RANK_9_ROLE_ID   = 1467519474079891558
STATE_RANK_10_ROLE_ID  = 1467519315803897959

ILLEGAL_RANK_9_ROLE_ID  = 1470021665437257894
ILLEGAL_RANK_10_ROLE_ID = 1469391591687979321


class RoleRequestSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for role_id, label, cat, _ in ROLE_REQUEST_OPTIONS:
            cat_desc = "Администрация" if cat == "admin" else ("Госс структуры" if cat == "state" else "Нелегальные структуры")
            options.append(discord.SelectOption(label=label, value=str(role_id), description=cat_desc))
        super().__init__(
            placeholder="Выберите роль, которую хотите получить...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="role_req_select_menu"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_role_id = int(self.values[0])
        await interaction.response.send_modal(RoleRequestModal(selected_role_id))


class RoleRequestSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(RoleRequestSelect())


class RoleRequestPanelFormView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Подать заявку", style=discord.ButtonStyle.primary, custom_id="role_req_submit_btn")
    async def submit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            content="**Выберите вашу роль из выпадающего списка ниже:**",
            view=RoleRequestSelectView(),
            ephemeral=True
        )



class RoleRequestModal(discord.ui.Modal):
    nick_name = discord.ui.TextInput(
        label="Ваш игровой ник (Nick_Name):",
        placeholder="Ответ на данный вопрос",
        required=True,
        max_length=50
    )
    user_rank = discord.ui.TextInput(
        label="Ваш ранг (для организаций):",
        placeholder="Укажите ваш ранг (1-10)...",
        required=False,
        max_length=10
    )

    def __init__(self, role_id: int):
        role_info = next((r for r in ROLE_REQUEST_OPTIONS if r[0] == role_id), None)
        title_str = f"Роль: {role_info[1]}" if role_info else "Запрос на получение роли"
        super().__init__(title=title_str[:45])
        self.role_id = role_id

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        if not guild or not isinstance(user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Ошибка контекста."), ephemeral=True)
            return

        role_info = next((r for r in ROLE_REQUEST_OPTIONS if r[0] == self.role_id), None)
        if not role_info:
            await interaction.response.send_message(embed=error_embed("Выбранная роль не найдена."), ephemeral=True)
            return

        r_id, label, cat, short_tag = role_info
        nick = self.nick_name.value.strip()
        rank_raw = self.user_rank.value.strip() if self.user_rank.value else ""
        rank = int(rank_raw) if rank_raw.isdigit() else 0

        try:
            dm_channel = await user.create_dm()
            await dm_channel.send(
                embed=discord.Embed(
                    title="📸 Прикрепите фото-доказательство",
                    description="Отправьте изображение (скриншот доказательств) **файлом в этот личный чат с ботом** в течение 2 минут...",
                    color=Config.EMBED_COLOR_MAIN
                )
            )
        except Exception:
            await interaction.response.send_message(
                embed=error_embed("У вас закрыты личные сообщения (ЛС)! Откройте ЛС и повторите попытку."),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="📩 Проверьте личные сообщения",
                description="Инструкция отправлена вам в **личные сообщения (ЛС)**. Пожалуйста, отправьте туда скриншот доказательств в течение 2 минут.",
                color=Config.EMBED_COLOR_MAIN
            ),
            ephemeral=True
        )

        def check(m: discord.Message):
            return m.author.id == user.id and isinstance(m.channel, discord.DMChannel) and (len(m.attachments) > 0 or m.content.startswith("http"))

        try:
            msg = await interaction.client.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            await interaction.followup.send(embed=error_embed("Время ожидания файла истекло. Заявка не отправлена."), ephemeral=True)
            try:
                await dm_channel.send(embed=error_embed("Время ожидания истекло. Ваша заявка отменена."))
            except Exception:
                pass
            return

        proof_url = None
        if msg.attachments:
            proof_url = msg.attachments[0].url
        elif msg.content:
            proof_url = msg.content.strip()

        account_text = f"[{short_tag} {rank}/10] {nick} | ID: {user.id}" if cat != "admin" else f"{nick} | ID: {user.id}"

        now = datetime.now(timezone.utc)

        top_lines = [
            f"**Запрос передан: <@&{ROLE_REQUEST_REVIEWER_ROLE_ID}>**",
            f"**Аккаунт:** `{account_text}`",
            f"**Никнейм:** `{nick}`",
            f"**Роль для выдачи:** <@&{r_id}>",
        ]
        if cat != "admin":
            top_lines.append(f"**Фракция:** `{label}`")

        embed_top = discord.Embed(
            title="Запрос на получение роли",
            description="\n".join(top_lines),
            color=2503349
        )
        embed_top.set_thumbnail(url=user.display_avatar.url)

        embed_photo = None
        if proof_url:
            embed_photo = discord.Embed(color=2503349)
            embed_photo.set_image(url=proof_url)

        info_lines = [
            "**Информация по выдаче:**",
            "[<:narassmotr:1548570951443292180>] - взять роль на рассмотрение",
            "[<:approved:1548569825092177950>] - выдать роль",
            "[<:otkazano:1548570766306447392>] - отказать в выдаче роли",
        ]
        embed_bottom = discord.Embed(
            description="\n".join(info_lines),
            color=2503349,
            timestamp=now
        )

        embeds_list = [embed_top]
        if embed_photo:
            embeds_list.append(embed_photo)
        embeds_list.append(embed_bottom)

        target_ch = guild.get_channel(ROLE_REQUEST_LOG_CHANNEL_ID)
        if not target_ch or not isinstance(target_ch, discord.TextChannel):
            await interaction.followup.send(embed=error_embed("Канал модерации ролей не найден."), ephemeral=True)
            return

        review_view = RoleRequestReviewView(
            applicant_id=user.id,
            role_id=r_id,
            category=cat,
            rank=rank,
            nick=nick,
            fraction_name=label
        )

        await target_ch.send(
            content=f"<@&{ROLE_REQUEST_REVIEWER_ROLE_ID}>",
            embeds=embeds_list,
            view=review_view
        )

        await interaction.followup.send(
            embed=success_embed("Ваша заявка с прикреплённым фото успешно отправлена на рассмотрение модерации!"),
            ephemeral=True
        )
        try:
            await dm_channel.send(embed=success_embed("Ваша заявка успешно отправлена на рассмотрение модерации!"))
        except Exception:
            pass
async def ensure_role_request_form_message(bot_client: commands.Bot):
    try:
        ch = bot_client.get_channel(ROLE_REQUEST_FORM_CHANNEL_ID)
        if not ch:
            try:
                ch = await bot_client.fetch_channel(ROLE_REQUEST_FORM_CHANNEL_ID)
            except Exception:
                ch = None

        if not ch or not isinstance(ch, discord.TextChannel):
            log.warning("Канал запроса ролей %s не найден", ROLE_REQUEST_FORM_CHANNEL_ID)
            return

        form_exists = False
        try:
            async for msg in ch.history(limit=20):
                if msg.author.id == bot_client.user.id and msg.embeds:
                    if "Запрос на получение роли" in (msg.embeds[0].title or ""):
                        form_exists = True
                        await msg.edit(view=RoleRequestPanelFormView())
                        break
        except Exception as h_err:
            log.warning("Ошибка чтения истории канала запроса ролей: %s", h_err)

        if not form_exists:
            embed = discord.Embed(
                title="Запрос на получение роли",
                description="Все ваши заявки будут отправлены в Модерацию/Следящим за Ролями, которые примут решение о принятии или отклонении вашей заявки.",
                color=Config.EMBED_COLOR_MAIN
            )
            await ch.send(embed=embed, view=RoleRequestPanelFormView())
            log.info("Панель запроса ролей успешно создана в канале %s", ROLE_REQUEST_FORM_CHANNEL_ID)
    except Exception as e:
        log.error("Ошибка при создании панели запроса ролей: %s", e)


# ==============================================================================
#                 СИСТЕМА РУЛЕТКИ (ROULETTE SYSTEM)
# ==============================================================================
VOICE_MEETING_CHANNEL_ID    = 1369359092703039618
ROULETTE_RESULT_CHANNEL_ID  = 1369358862653718682
ROULETTE_ALLOWED_ROLE_ID    = 1538965783311290469
EXCLUDED_SENIOR_ROLE_ID     = 1369357661967224933


class RouletteTotalsModal(discord.ui.Modal, title="Настройка тоталов за места"):
    total_1 = discord.ui.TextInput(label="1 место (тотал)", default="50", required=True, max_length=10)
    total_2 = discord.ui.TextInput(label="2 место (тотал)", default="30", required=True, max_length=10)
    total_3 = discord.ui.TextInput(label="3 место (тотал)", default="15", required=True, max_length=10)

    def __init__(self, view: "RouletteControlView"):
        super().__init__()
        self.control_view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            t1 = int(self.total_1.value.strip())
            t2 = int(self.total_2.value.strip())
            t3 = int(self.total_3.value.strip())
            self.control_view.totals = (t1, t2, t3)
            self.control_view.roulette_type = "totals"
            await self.control_view.update_panel(interaction)
        except ValueError:
            await interaction.response.send_message(embed=error_embed("Введены нечисловые значения тоталов."), ephemeral=True)


class RouletteParticipantsModal(discord.ui.Modal, title="Участники рулетки"):
    members_text = discord.ui.TextInput(
        label="Список ников / упоминаний (через запятую):",
        style=discord.TextStyle.paragraph,
        placeholder="Nick1, Nick2, Nick3...",
        required=True,
        max_length=1000
    )

    def __init__(self, view: "RouletteControlView"):
        super().__init__()
        self.control_view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.members_text.value.strip()
        raw_names = re.split(r"[\n,;]+", raw)
        names = [n.strip() for n in raw_names if n.strip()]
        new_list = []
        for name in names:
            clean_name = re.sub(r"[<@!>]", "", name)
            member = None
            if clean_name.isdigit() and interaction.guild:
                member = interaction.guild.get_member(int(clean_name))
            if member:
                new_list.append((member.id, member.display_name))
            else:
                new_list.append((0, name))
        self.control_view.participants = new_list
        await self.control_view.update_panel(interaction)


class RouletteControlView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.participants: list[tuple[int, str]] = []
        self.roulette_type: str = "days"
        self.totals: tuple[int, int, int] = (50, 30, 15)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(embed=error_embed("Вы не управляете этой панелью рулетки."), ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        type_str = "📉 - Дни к повышению (-3d, -2d, -1d)" if self.roulette_type == "days" else f"📊 + Тоталы (1st: +{self.totals[0]}, 2nd: +{self.totals[1]}, 3rd: +{self.totals[2]})"
        embed = discord.Embed(
            title="🎯 Настройка и проведение рулетки собрания",
            description=f"Режим рулетки: **{type_str}**\nЗарегистрировано участников: **{len(self.participants)}**",
            color=Config.EMBED_COLOR_MAIN
        )
        if self.participants:
            p_lines = [f"{idx+1}. {p[1]}" for idx, p in enumerate(self.participants[:25])]
            if len(self.participants) > 25:
                p_lines.append(f"... и ещё {len(self.participants)-25} участников")
            embed.add_field(name="Участники рулетки", value="\n".join(p_lines), inline=False)
        else:
            embed.add_field(name="Участники рулетки", value="Список пуст. Нажмите [Анализ войса] или добавьте вручную.", inline=False)
        return embed

    async def update_panel(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        embed = self.build_embed()
        names = [p[1] for p in self.participants]
        if names:
            buf = generate_roulette_image(names, bot_logo_path="bot_logo.png")
            file = discord.File(buf, filename="roulette.png")
            embed.set_image(url="attachment://roulette.png")
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, attachments=[file], view=self)
        else:
            embed.set_image(url=None)
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, attachments=[], view=self)

    @discord.ui.button(label="🎙️ Анализ войса", style=discord.ButtonStyle.primary, custom_id="roulette_voice_analysis")
    async def voice_analysis_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            await interaction.followup.send(embed=error_embed("Ошибка контекста."), ephemeral=True)
            return

        voice_ch = guild.get_channel(VOICE_MEETING_CHANNEL_ID)
        if not voice_ch or not isinstance(voice_ch, discord.VoiceChannel):
            await interaction.followup.send(embed=error_embed("Голосовой канал собрания не найден."), ephemeral=True)
            return

        valid_members = []
        for m in voice_ch.members:
            if m.bot:
                continue
            has_excluded_role = any(r.id == EXCLUDED_SENIOR_ROLE_ID for r in m.roles) or m.guild_permissions.administrator
            if not has_excluded_role:
                valid_members.append((m.id, m.display_name.strip()))

        if not valid_members:
            await interaction.followup.send(
                embed=error_embed("В голосовом канале собрания не найдено участников подходящих ролей."),
                ephemeral=True
            )
            return

        self.participants = valid_members
        await self.update_panel(interaction)

    @discord.ui.button(label="Тип: - Дни к повышению", style=discord.ButtonStyle.primary, custom_id="roulette_toggle_type")
    async def toggle_type_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.roulette_type == "days":
            self.roulette_type = "totals"
            button.label = f"Тип: + Тоталы ({self.totals[0]}/{self.totals[1]}/{self.totals[2]})"
            button.style = discord.ButtonStyle.success
        else:
            self.roulette_type = "days"
            button.label = "Тип: - Дни к повышению"
            button.style = discord.ButtonStyle.primary
        await self.update_panel(interaction)

    @discord.ui.button(label="⚙️ Настроить тоталы", style=discord.ButtonStyle.secondary, custom_id="roulette_custom_totals")
    async def custom_totals_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RouletteTotalsModal(self))

    @discord.ui.button(label="Управление участниками", style=discord.ButtonStyle.secondary, custom_id="roulette_manage_members")
    async def manage_members_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RouletteParticipantsModal(self))

    @discord.ui.button(label="Запустить рулетку", style=discord.ButtonStyle.success, custom_id="roulette_start")
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.participants) < 2:
            await interaction.response.send_message(embed=error_embed("Для проведения рулетки необходимо минимум 2 участника."), ephemeral=True)
            return

        # Гарантированная дедупликация участников перед запуском
        seen_keys = set()
        unique_participants = []
        for p in self.participants:
            pkey = p[0] if p[0] > 0 else p[1]
            if pkey not in seen_keys:
                seen_keys.add(pkey)
                unique_participants.append(p)
        self.participants = unique_participants

        if len(self.participants) < 2:
            await interaction.response.send_message(embed=error_embed("После дедупликации осталось менее 2 уникальных участников."), ephemeral=True)
            return

        for item in self.children:
            item.disabled = True

        embed_spinning = discord.Embed(
            title="Рулетка крутится...",
            description="Подводятся итоги: 1-й прокрут (1 место)... 2-й прокрут (2 место)... 3-е место автоматически!",
            color=Config.EMBED_COLOR_MAIN
        )
        await interaction.response.edit_message(embed=embed_spinning, attachments=[], view=self)

        def get_pkey(p):
            return p[0] if p[0] > 0 else p[1]

        # 1. Первый прокрут
        pool_1 = list(self.participants)
        winner_1 = random.choice(pool_1)
        w1_key = get_pkey(winner_1)

        # 2. Второй прокрут
        pool_2 = [p for p in pool_1 if get_pkey(p) != w1_key]
        winner_2 = random.choice(pool_2) if pool_2 else None

        # 3. Третий прокрут
        winner_3 = None
        rest_participants = []
        if winner_2:
            w2_key = get_pkey(winner_2)
            pool_3 = [p for p in pool_2 if get_pkey(p) != w2_key]
            if len(pool_3) == 1:
                winner_3 = pool_3[0]
                rest_participants = []
            elif len(pool_3) > 1:
                winner_3 = random.choice(pool_3)
                w3_key = get_pkey(winner_3)
                rest_participants = [p for p in pool_3 if get_pkey(p) != w3_key]

        final_order = [winner_1]
        if winner_2:
            final_order.append(winner_2)
        if winner_3:
            final_order.append(winner_3)
        final_order.extend(rest_participants)

        # Автоматическое начисление тоталов в базу данных при режиме "totals"
        if self.roulette_type == "totals" and interaction.guild:
            for idx, (m_id, name) in enumerate(final_order[:3]):
                if m_id > 0:
                    tot_amount = self.totals[idx] if idx < len(self.totals) else 0
                    if tot_amount > 0:
                        try:
                            await db.register_moderator(interaction.guild.id, m_id)
                            await db.increment_stat(interaction.guild.id, m_id, "tickets", tot_amount)
                            log.info("Автоматически начислено +%d тоталов модератору ID %s (%s)", tot_amount, m_id, name)
                        except Exception as e:
                            log.error("Ошибка автоначисления тоталов в БД для ID %s: %s", m_id, e)

        winner_names = [p[1] for p in final_order[:3]]
        all_names = [p[1] for p in self.participants]

        buf = generate_roulette_image(all_names, winners=winner_names, bot_logo_path="bot_logo.png")
        result_file = discord.File(buf, filename="roulette_result.png")

        target_ch = interaction.guild.get_channel(ROULETTE_RESULT_CHANNEL_ID) if interaction.guild else None
        if not target_ch or not isinstance(target_ch, discord.TextChannel):
            await interaction.followup.send(embed=error_embed("Канал для результатов рулетки не найден."), ephemeral=True)
            return

        type_header = "Была проведена рулетка на - дни к повышению" if self.roulette_type == "days" else "Была проведена рулетка на тоталы"
        lines = [type_header, ""]

        for idx, (m_id, name) in enumerate(final_order):
            user_text = f"<@{m_id}>" if m_id > 0 else f"`{name}`"
            place_num = idx + 1
            if place_num == 1:
                reward = "-3 дня к повышению" if self.roulette_type == "days" else f"+{self.totals[0]} тотала (автоматически начислено)"
                lines.append(f"1 место - {user_text} {reward}")
            elif place_num == 2:
                reward = "-2 дня к повышению" if self.roulette_type == "days" else f"+{self.totals[1]} тотала (автоматически начислено)"
                lines.append(f"2 место - {user_text} {reward}")
            elif place_num == 3:
                reward = "-1 день к повышению" if self.roulette_type == "days" else f"+{self.totals[2]} тотала (автоматически начислено)"
                lines.append(f"3 место - {user_text} {reward}")
            else:
                lines.append(f"{place_num} место - {user_text} он просто молодец")

        result_text = "\n".join(lines)

        await target_ch.send(content=result_text, file=result_file)

        embed_done = discord.Embed(
            title="Рулетка проведена",
            description=f"Итоги рулетки успешно опубликованы в канале <#{ROULETTE_RESULT_CHANNEL_ID}>.",
            color=Config.EMBED_COLOR_SUCCESS
        )
        await interaction.followup.send(embed=embed_done, ephemeral=True)


def create_givecoin_image(

    user_name: str,
    admin_name: str,
    amount: int,
    new_balance: int,
    reason: str,
    avatar_img: Optional[Image.Image]
) -> io.BytesIO:
    width, height = 700, 320
    is_positive = amount >= 0
    accent_color = (63, 185, 80, 255) if is_positive else (248, 81, 73, 255)

    base = Image.new("RGBA", (width, height), (13, 19, 36, 255))
    draw = ImageDraw.Draw(base)

    draw.rectangle([0, 0, width, height], fill=(15, 23, 42, 255))
    draw.rounded_rectangle(
        [20, 20, width - 20, height - 20],
        radius=16,
        fill=(22, 33, 58, 240),
        outline=accent_color,
        width=2
    )

    if avatar_img:
        base.paste(avatar_img, (45, 45), avatar_img)
        draw.ellipse([43, 43, 147, 147], outline=accent_color, width=3)
    else:
        draw.ellipse([45, 45, 145, 145], fill=(40, 60, 100, 255), outline=accent_color, width=2)

    font_title = get_font(22)
    font_user = get_font(20)
    font_amount = get_font(32)
    font_body = get_font(15)

    draw.text((165, 45), "💎 ИЗМЕНЕНИЕ БАЛАНСА SWAG COINS", fill=(139, 148, 158, 255), font=font_title)
    draw.text((165, 80), f"Модератор: {user_name[:20]}", fill=(255, 255, 255, 255), font=font_user)

    sign_str = f"+{amount}" if amount > 0 else str(amount)
    draw.text((165, 120), f"{sign_str} SC", fill=accent_color, font=font_amount)
    draw.text((400, 130), f"Новый баланс: {new_balance:,} SC".replace(",", " "), fill=(241, 224, 90, 255), font=font_user)

    draw.line([45, 180, 655, 180], fill=(45, 65, 105, 255), width=2)

    draw.text((45, 200), f"Выдал(а): {admin_name[:25]}", fill=(200, 210, 225, 255), font=font_body)
    draw.text((45, 230), f"Причина: {reason[:50]}", fill=(200, 210, 225, 255), font=font_body)

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf



    async def auto_setup_guild_permissions_and_logs(self, guild: discord.Guild):

        if not guild:
            return

        try:

            command_role_map = {
                "kick": [1369357690131709992, 1369357661967224933, 1538965783311290469],
                "mute": [1369357716786778123],
                "unmute": [1369357716786778123],
                "ban": [1538965783311290469, 1369357661967224933],
                "unban": [1538965783311290469, 1369357661967224933],
                "warn": [1369357716786778123],
                "clear": [1369357716786778123],
                "ticket_take": [1369357716786778123],
                "ticket take": [1369357716786778123],
                "ticket_close": [1369357716786778123],
                "ticket close": [1369357716786778123],
                "setstat_moder": [1538965783311290469],
                "setstat moder": [1538965783311290469],
                "register": [1538965783311290469],
                "unregister": [1538965783311290469],
                "pm": [1369357661967224933, 1538965783311290469],
                "history": [1369357716786778123],
                "forma": [1369357690131709992, 1369357716786778123, 1369357661967224933, 1538965783311290469],
                "active": [1538965783311290469],
                "notif": [1537451548622332025],
                "vig": [1369357661967224933, 1538965783311290469],
                "unvig": [1369357661967224933, 1538965783311290469],
                "me": [1369357716786778123],
            }

            # Жёстко прописанные ID лог-каналов сервера
            log_channels_map = {
                "roles":      1369358949668884540,
                "moderation": 1369358936987848736,
                "messages":   1369358923753603133,
                "tickets":    1369358939791876209,
                "members":    1369358942477660191,
                "server":     1369358949668884540,
            }

            await db.update_settings(
                guild.id,
                command_role_map=command_role_map,
                log_channels_map=log_channels_map,
                form_approve_roles='[1538965783311290469]'
            )
            log.info("Авто-настройка /cmdperm и /settings moderation завершена для сервера '%s'", guild.name)
        except Exception as err:
            log.error("Ошибка при авто-настройке ролей/каналов сервера %s: %s", guild.id, err)

    async def on_ready(self):
        global bot_loop
        bot_loop = asyncio.get_running_loop()
        log.info("Бот запущен как %s (ID: %s)", self.user, self.user.id)

        try:
            await db.seed_default_moderators()
        except Exception as seed_err:
            log.error("Ошибка авто-сева модераторов: %s", seed_err)

        self.add_view(InactivityFormView())

        if getattr(self, "_tg_started", False) is False:
            self._tg_started = True
            if TG_AVAILABLE and Config.TG_TOKEN:
                tg_thread = threading.Thread(target=run_telegram, daemon=True, name="TG-Thread")
                tg_thread.start()
                log.info("Telegram-панель запущена в фоновом потоке")
            else:
                log.warning("Telegram-панель отключена (нет python-telegram-bot или TG_TOKEN)")

        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching, name="за порядком на сервере"
        ))

        asyncio.create_task(ensure_inactivity_form_message(self))

        for guild in self.guilds:
            asyncio.create_task(self.auto_setup_guild_permissions_and_logs(guild))




    async def on_message_delete(self, message: discord.Message):
        if (message.author and message.author.bot) or not message.guild:
            return
        await asyncio.sleep(0.5)
        deleter = None
        try:
            async for entry in message.guild.audit_logs(limit=3, action=discord.AuditLogAction.message_delete):
                if entry.target and message.author and entry.target.id == message.author.id and is_recent(entry.created_at):
                    deleter = entry.user
                    break
        except Exception:
            pass

        author_name = message.author.name if message.author else "Неизвестно"
        embed = discord.Embed(
            title=f"🗑️ Сообщение удалено — {author_name}",
            color=Config.EMBED_COLOR_ERROR,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤 Пользователь", value=person_text(message.author) if message.author else "Неизвестно", inline=False)
        embed.add_field(name="📍 Канал", value=message.channel.mention if message.channel else "Неизвестно", inline=False)
        text_val = message.content[:1000] if message.content else "(без текста / вложение)"
        embed.add_field(name="📝 Текст", value=text_val, inline=False)
        if deleter and message.author and deleter.id != message.author.id:
            embed.add_field(name="🗑️ Удалил", value=person_text(deleter), inline=False)
        embed.set_footer(text=f"ID сообщения: {message.id}")
        await send_log(message.guild, "messages", embed)

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.cached_message:
            return

        try:
            guild = self.get_guild(payload.guild_id)
            if not guild:
                return

            await asyncio.sleep(1)
            deleter = None
            target = None
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.message_delete):
                    if is_recent(entry.created_at):
                        deleter = entry.user
                        target = entry.target
                        break
            except Exception as e:
                log.warning("Ошибка чтения audit_logs (raw): %s", e)

            if deleter:
                try:
                    await db.increment_moder_stat(guild.id, deleter.id, "clear")
                except Exception as e:
                    log.warning("Не удалось начислить тотал за удаление сообщения (raw): %s", e)

            ch = guild.get_channel(payload.channel_id)
            embed = discord.Embed(
                title="🗑️ Сообщение удалено",
                color=Config.EMBED_COLOR_ERROR,
                timestamp=datetime.now(timezone.utc)
            )
            if ch:
                embed.add_field(name="📍 Канал", value=ch.mention, inline=False)
            if target:
                embed.add_field(name="👤 Автор", value=f"<@{target.id}> ({target})", inline=False)
            if deleter:
                embed.add_field(name="🗑️ Кто удалил", value=person_text(deleter), inline=False)
            embed.add_field(name="📝 Текст", value="(сообщение удалено / было за пределами кэша)", inline=False)
            embed.set_footer(text=f"ID сообщения: {payload.message_id}")
            await send_log(guild, "messages", embed)
        except Exception as e:
            log.warning("Ошибка в on_raw_message_delete: %s", e)

    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        try:
            guild = None
            for g in self.guilds:
                if g.id == payload.guild_id:
                    guild = g
                    break
            if not guild:
                return

            deleter = None
            try:
                async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.message_bulk_delete):
                    if is_recent(entry.created_at):
                        deleter = entry.user
                        break
            except Exception as e:
                log.warning("Ошибка чтения audit_logs (bulk): %s", e)

            if deleter:
                try:
                    count = len(payload.message_ids)
                    log.info("Начисление тотала за массовое удаление (bulk): mod=%s count=%s guild=%s", deleter.id, count, guild.id)
                    await db.increment_moder_stat(guild.id, deleter.id, "clear", amount=count)
                except Exception as e:
                    log.warning("Не удалось начислить тотал за массовое удаление: %s", e)
        except Exception as e:
            log.warning("Ошибка в on_raw_bulk_message_delete: %s", e)

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        embed = discord.Embed(
            title=f"✏️ Сообщение изменено — {before.author.name}",
            color=Config.EMBED_COLOR_WARNING,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤 Пользователь", value=person_text(before.author), inline=False)
        embed.add_field(name="📍 Канал", value=before.channel.mention, inline=False)
        embed.add_field(name="📝 Было", value=before.content[:500] if before.content else "(пусто)", inline=False)
        embed.add_field(name="📝 Стало", value=after.content[:500] if after.content else "(пусто)", inline=False)
        embed.set_footer(text=f"ID сообщения: {before.id}")
        await send_log(before.guild, "messages", embed)

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if not added and not removed:
            return
        await asyncio.sleep(0.5)
        actor = None
        try:
            async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
                if entry.target and entry.target.id == after.id and is_recent(entry.created_at, 60):
                    actor = entry.user
                    break
        except Exception:
            pass

        embed = discord.Embed(
            title=f"🎭 Роли участника изменены — {after.name}",
            color=Config.EMBED_COLOR_MAIN,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤 Пользователь", value=person_text(after), inline=False)
        if added:
            embed.add_field(name="➕ Выданы роли", value=", ".join(r.mention for r in added), inline=False)
        if removed:
            embed.add_field(name="➖ Сняты роли", value=", ".join(r.mention for r in removed), inline=False)
        if actor:
            embed.add_field(name="🛡️ Кто изменил", value=person_text(actor), inline=False)
        embed.set_footer(text=f"ID пользователя: {after.id}")
        await send_log(after.guild, "roles", embed)

    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        if entry.action == discord.AuditLogAction.member_role_update:
            guild = entry.guild
            target = entry.target
            actor = entry.user
            if not guild or not target or not isinstance(target, discord.Member):
                return

            added = []
            removed = []
            if hasattr(entry.changes.after, "roles"):
                added = entry.changes.after.roles or []
            if hasattr(entry.changes.before, "roles"):
                removed = entry.changes.before.roles or []

            if not added and not removed:
                return

            embed = discord.Embed(
                title=f"🎭 Роли участника изменены — {target.name}",
                color=Config.EMBED_COLOR_MAIN,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="👤 Пользователь", value=person_text(target), inline=False)
            if added:
                embed.add_field(name="➕ Выданы роли", value=", ".join(r.mention for r in added), inline=False)
            if removed:
                embed.add_field(name="➖ Сняты роли", value=", ".join(r.mention for r in removed), inline=False)
            if actor:
                embed.add_field(name="🛡️ Кто изменил", value=person_text(actor), inline=False)
            embed.set_footer(text=f"ID пользователя: {target.id}")
            await send_log(guild, "roles", embed)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not (before.channel and not after.channel):
            return
        await asyncio.sleep(1.5)
        try:
            async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_disconnect):
                if entry.target and entry.target.id == member.id and is_recent(entry.created_at):
                    embed = discord.Embed(
                        title=f"🔌 Отключение от войса — {member.name}",
                        color=Config.EMBED_COLOR_WARNING,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.add_field(name="👤 Пользователь", value=person_text(member), inline=False)
                    embed.add_field(name="🎙️ Канал", value=before.channel.name, inline=False)
                    if entry.user:
                        embed.add_field(name="🛡️ Кто отключил", value=person_text(entry.user), inline=False)
                    embed.set_footer(text=f"ID пользователя: {member.id}")
                    await send_log(member.guild, "moderation", embed)
                    break
        except Exception:
            pass

    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title=f"👋 Новый участник — {member.name}",
            color=Config.EMBED_COLOR_SUCCESS,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤 Пользователь", value=person_text(member), inline=False)
        embed.add_field(name="📆 Аккаунт создан", value=member.created_at.strftime("%d.%m.%Y %H:%M:%S"), inline=False)
        embed.set_footer(text=f"ID пользователя: {member.id}")
        await send_log(member.guild, "members", embed)

    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        await asyncio.sleep(1.0)
        reason = "👋 Сам покинул сервер"
        actor = None
        try:
            async for entry in guild.audit_logs(limit=5):
                if not is_recent(entry.created_at, 15):
                    break
                if entry.target and entry.target.id == member.id:
                    if entry.action == discord.AuditLogAction.kick:
                        reason = "👢 Был кикнут"
                        actor = entry.user
                        if entry.reason:
                            reason += f" ({entry.reason})"
                        break
                    if entry.action == discord.AuditLogAction.ban:
                        reason = "🔨 Был забанен"
                        actor = entry.user
                        if entry.reason:
                            reason += f" ({entry.reason})"
                        break
        except Exception:
            pass

        embed = discord.Embed(
            title=f"🚪 Сервер покинул — {member.name}",
            color=Config.EMBED_COLOR_ERROR,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="👤 Пользователь", value=person_text(member), inline=False)
        embed.add_field(name="📌 Причина", value=reason, inline=False)
        if actor:
            embed.add_field(name="🛡️ Кто", value=person_text(actor), inline=False)
        embed.set_footer(text=f"ID пользователя: {member.id}")
        await send_log(guild, "members", embed)

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        DEFAULT_HONEYPOT_CHANNEL_ID = 1537823764337922058
        is_honeypot = False
        if message.channel.id == DEFAULT_HONEYPOT_CHANNEL_ID:
            is_honeypot = True
        else:
            try:
                hp_info = await db.get_honeypot_info(message.guild.id)
                if hp_info.get("honeypot_channel_id") == message.channel.id:
                    is_honeypot = True
            except Exception:
                pass

        if is_honeypot:

            try:
                await message.delete()
            except Exception:
                pass

            ban_reason = "Взломан/Реклама"
            try:
                await message.guild.ban(message.author, reason=f"{ban_reason} [Ловушка]", delete_message_seconds=86400)
            except (TypeError, AttributeError):
                try:
                    await message.guild.ban(message.author, reason=f"{ban_reason} [Ловушка]", delete_message_days=1)
                except Exception as b_err:
                    log.error("Ошибка при бане в ловушке: %s", b_err)
            except Exception as b_err:
                log.error("Ошибка при бане в ловушке: %s", b_err)

            try:
                await db.add_punishment(message.guild.id, message.author.id, "ban", None)
            except Exception:
                pass

            try:
                log_embed = punishment_log_embed("Бан", "🔨", self.user, message.author, ban_reason)
                await send_log(message.guild, "moderation", log_embed)
            except Exception:
                pass

            try:
                new_count = await db.increment_honeypot_count(message.guild.id)
                hp_info = await db.get_honeypot_info(message.guild.id)
                msg_id = hp_info.get("honeypot_message_id")
                ch = message.channel
                bot_avatar = self.user.display_avatar.url if self.user else None

                target_msg = None
                if msg_id:
                    try:
                        target_msg = await ch.fetch_message(msg_id)
                    except Exception:
                        pass

                if not target_msg:
                    async for m in ch.history(limit=15):
                        if m.author.id == self.user.id and m.embeds:
                            target_msg = m
                            break

                if target_msg:
                    await target_msg.edit(embed=honeypot_embed(bot_avatar), view=HoneypotView(new_count))
                    await db.set_honeypot_info(message.guild.id, ch.id, target_msg.id, new_count)
                else:
                    new_msg = await ch.send(embed=honeypot_embed(bot_avatar), view=HoneypotView(new_count))
                    await db.set_honeypot_info(message.guild.id, ch.id, new_msg.id, new_count)
            except Exception as exc:
                log.error("Ошибка при обновлении счетчика ловушки: %s", exc)

        await self.process_commands(message)

        has_direct_ping = (
            self.user and (
                f"<@{self.user.id}>" in message.content
                or f"<@!{self.user.id}>" in message.content
            )
        )

        is_mentioned = has_direct_ping or (
            self.user in message.mentions and not message.reference
        )

        ch_name = (message.channel.name or "").lower()
        is_question_channel = ("вопрос" in ch_name or "question" in ch_name or message.channel.id == 1369390645277491270)

        clean_text = message.content.lower().strip()
        if self.user:
            clean_text = re.sub(rf"<@!?{self.user.id}>", "", clean_text).strip()

        STOP_WORDS = {
            "блять", "бля", "сука", "нахуй", "пошел нахуй", "пнх", "лох", "ты лох",
            "ок", "да", "нет", "спасибо", "пон", "понял", "лол", "кек", "хд", "xd",
            "он чет тупит", "на каждое соо отвечает", "блять", "я не хочу наказание"
        }
        if clean_text in STOP_WORDS or len(clean_text) < 3:
            return

        QUESTION_PREFIXES = (
            "как", "че", "чо", "что", "где", "почему", "зачем", "когда", "кто",
            "подскажи", "подскажите", "какой", "какие", "каком", "какому", "какую",
            "сколько", "можно ли", "разрешено ли", "наказуемо ли", "какое наказание",
            "что будет", "хелп", "help", "правило", "правила", "норма", "выговор",
            "мут", "бан", "роль", "повышение", "тотал", "устав"
        )

        is_real_question = (
            any(clean_text.startswith(p) for p in QUESTION_PREFIXES)
            or "?" in clean_text
        )

        should_trigger_ai = is_mentioned or (is_question_channel and is_real_question)

        has_image = any(
            att.content_type and att.content_type.startswith("image/")
            for att in message.attachments
        )
        if is_mentioned and has_image:
            should_trigger_ai = True

        if should_trigger_ai:
            query = message.content
            if self.user:
                query = re.sub(rf"<@!?{self.user.id}>", "", query).strip()
            if not query or len(query) < 3:
                query = "Кто нарушил на скриншоте и какое наказание нужно выдать?"

            image_attachment = None
            for att in message.attachments:
                if att.content_type and att.content_type.startswith("image/"):
                    image_attachment = att
                    break

            q_lower = query.lower()

            if any(kw in q_lower for kw in ("кто твой разработчик", "кто твои разработчики", "кто тебя создал", "кто создатель", "кто разработчик", "чья идея", "кто написал бота")):
                response_text = "Мои разработчики — **Syndic** и **Ace Nemos**."
            elif any(kw in q_lower for kw in ("есть нарушение", "есть ли нарушение", "тут есть нарушение", "проверь скрин", "что нарушили")) and image_attachment is None:
                response_text = "• Пожалуйста, прикрепите скриншот к своему сообщению для проверки нарушений."
            elif image_attachment is not None:

                async with message.channel.typing():
                    response_text = await analyze_screenshot_ocr(
                        attachment_url=image_attachment.url,
                        question=query,
                        author_name=message.author.display_name
                    )
            else:
                try:
                    async with message.channel.typing():
                        response_text = await ask_groq_ai(query, message.author.display_name)
                except Exception as ai_err:
                    log.error("Ошибка ИИ ответа: %s", ai_err)
                    return

            if len(response_text) > 3800:
                response_text = response_text[:3750] + "\n\n*(...ответ сокращён из-за лимита длины)*"

            clean_author_name = re.sub(r"\[.*?\]", "", message.author.display_name).strip()
            if not clean_author_name:
                clean_author_name = message.author.name

            embed = discord.Embed(
                description=response_text,
                color=Config.EMBED_COLOR_MAIN,
            )
            embed.set_author(
                name=f"Ответ на вопрос от {clean_author_name}",
                icon_url=message.author.display_avatar.url
            )

            await message.reply(content=f"Ответ для {message.author.mention}:", embed=embed, mention_author=True)

        if not hasattr(self, "_processed_tg_msg_ids"):
            self._processed_tg_msg_ids = set()

        for tg_uid_str, track in list(data.get("tg_tracking", {}).items()):
            if track.get("guild") != message.guild.id or track.get("channel") != message.channel.id:
                continue
            if not tg_bot_ref:
                continue

            dedup_key = (tg_uid_str, message.id)
            if dedup_key in self._processed_tg_msg_ids:
                continue
            self._processed_tg_msg_ids.add(dedup_key)
            if len(self._processed_tg_msg_ids) > 2000:
                self._processed_tg_msg_ids.clear()

            try:
                tg_chat_id = int(tg_uid_str)
                author_name = message.author.display_name
                author_id = message.author.id
                content = message.content or "(медиа/вложение)"
                if len(content) > 3500:
                    content = content[:3500] + "..."
                attachments = [f"📎 {a.filename} ({a.url})" for a in message.attachments]
                text = (
                    f"📥 Новое сообщение\n"
                    f"👤 {author_name} (ID: {author_id})\n"
                    f"📍 #{message.channel.name}\n\n"
                    f"{content}"
                )
                if attachments:
                    text += "\n\n" + "\n".join(attachments[:3])

                kb = {
                    "inline_keyboard": [
                        [
                            {"text": "🗑 Удалить", "callback_data": f"tgd_{message.channel.id}_{message.id}"},
                            {"text": "↩️ Ответить", "callback_data": f"tgr_{message.channel.id}_{message.id}"},
                        ]
                    ]
                }

                def _send_tg_bg():
                    msg_id = send_tg_message_http(tg_chat_id, text, kb)
                    if msg_id:
                        data.setdefault("tg_msg_map", {})[str(msg_id)] = {
                            "ch": message.channel.id,
                            "msg": message.id,
                            "guild": message.guild.id
                        }
                        if len(data["tg_msg_map"]) > 5000:
                            keys = list(data["tg_msg_map"].keys())
                            for k in keys[:len(keys) - 5000]:
                                data["tg_msg_map"].pop(k, None)
                        save_data()

                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _send_tg_bg)
            except Exception as e:
                log.warning("Ошибка отправки в TG: %s", e)

_DISCORD_MSG_LINK_RE = re.compile(r"https?://(?:ptb\.|canary\.)?discord\.com/channels/(\d+)/(\d+)/(\d+)", re.IGNORECASE)

async def fetch_embed_json_by_link(bot: commands.Bot, url: str) -> tuple[bool, str, Optional[discord.File]]:
    match = _DISCORD_MSG_LINK_RE.search(url)
    if not match:
        return False, "⚠️ Неверная ссылка на сообщение Discord.\nПример ссылки: `https://discord.com/channels/123456789/987654321/1122334455`", None

async def get_ticket_category(guild: discord.Guild, category_id: Optional[int]) -> Optional[discord.CategoryChannel]:
    if not category_id:
        return None
    try:
        cid = int(category_id)
    except (ValueError, TypeError):
        return None

    ch = guild.get_channel(cid)
    if isinstance(ch, discord.CategoryChannel):
        return ch

    ch = discord.utils.get(guild.categories, id=cid)
    if isinstance(ch, discord.CategoryChannel):
        return ch

    try:
        ch = await guild.fetch_channel(cid)
        if isinstance(ch, discord.CategoryChannel):
            return ch
    except Exception:
        pass

    return None

bot = ModerBot()

def register_commands(tree: app_commands.CommandTree):

    STAT_CHOICES = [
        app_commands.Choice(name="Тикеты", value="tickets"),
        app_commands.Choice(name="👍 Лайки", value="likes"),
        app_commands.Choice(name="👎 Дизлайки", value="dislikes"),
        app_commands.Choice(name="Муты", value="mutes"),
        app_commands.Choice(name="Кики", value="kicks"),
        app_commands.Choice(name="Баны", value="bans"),
        app_commands.Choice(name="Варны", value="warns"),
        app_commands.Choice(name="Удалённые сообщения", value="deleted_msgs"),
        app_commands.Choice(name="Строгие выговоры", value="strict_vigs"),
        app_commands.Choice(name="Устные выговоры", value="oral_vigs"),
    ]

    VIG_ALLOWED_ROLES = {1369357661967224933, 1538965783311290469}

    @tree.command(name="roulette", description="Запустить проведение рулетки для модераторов на собрании")
    async def roulette_cmd(interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Команда доступна только на сервере."), ephemeral=True)
            return

        has_perm = interaction.user.guild_permissions.administrator or any(
            r.id in {ROULETTE_ALLOWED_ROLE_ID, EXCLUDED_SENIOR_ROLE_ID} for r in interaction.user.roles
        )
        if not has_perm:
            await interaction.response.send_message(
                embed=error_embed("У вас недостаточно прав для запуска рулетки."),
                ephemeral=True
            )
            return

        view = RouletteControlView(author_id=interaction.user.id)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @tree.command(name="me", description="Личная карточка профиля модератора")
    @app_commands.rename(user="пользователь")
    @app_commands.describe(user="Модератор (по умолчанию — вы)")
    async def me_cmd(interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        if not isinstance(target, discord.Member) and interaction.guild:
            target = interaction.guild.get_member(target.id) or target

        mod_row = await db.get_moderator(interaction.guild_id, target.id)
        if not mod_row:
            await interaction.response.send_message(
                embed=error_embed(f"{target.mention} не является зарегистрированным модератором."),
                ephemeral=True
            )
            return

        position = get_moderator_position(target)
        inact_row = await db.get_active_inactivity(interaction.guild_id, target.id)
        inact_until = dict(inact_row).get("end_date") if inact_row else None
        embed = me_embed(target, mod_row, position, inact_until)
        await interaction.response.send_message(embed=embed)


    @tree.command(name="stats", description="Посмотреть статистику и баланс Swag Coins")
    @app_commands.rename(user="пользователь")
    @app_commands.describe(user="Модератор (по умолчанию — вы)")
    async def stats_cmd(interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target = user or interaction.user
        if not isinstance(target, discord.Member) and interaction.guild:
            target = interaction.guild.get_member(target.id) or target

        if not isinstance(target, discord.Member):
            await interaction.response.send_message(embed=error_embed("Пользователь не найден."), ephemeral=True)
            return

        await interaction.response.defer()

        m_row = await db.get_moderator(interaction.guild_id, target.id)
        if not m_row:
            await interaction.followup.send(embed=error_embed(f"{target.mention} не является зарегистрированным модератором."), ephemeral=True)
            return

        m_dict = dict(m_row)
        coins = m_dict.get("swag_coins", 0)
        role_title = get_moderator_position(target)

        if PIL_AVAILABLE:
            avatar_img = await fetch_avatar_image(target, size=112)
            if CARDS_AVAILABLE:
                img_buf = generate_stats_card(
                    username=target.display_name,
                    role_title=role_title,
                    avatar_img=avatar_img,
                    stats=m_dict,
                    coins=coins
                )
            else:
                img_buf = create_stats_image(
                    username=target.display_name,
                    role_title=role_title,
                    avatar_img=avatar_img,
                    stats=m_dict,
                    coins=coins
                )
            file = discord.File(fp=img_buf, filename="stats.png")
            await interaction.followup.send(file=file)
        else:
            embed = discord.Embed(
                title=f"📊 Статистика — {target.display_name}",
                color=Config.EMBED_COLOR_MAIN
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            embed.add_field(name="Должность", value=role_title, inline=False)
            embed.add_field(name="🪙 Swag Coins", value=f"**{coins} SC**", inline=False)
            embed.add_field(name="🎟️ Тикеты", value=str(m_dict.get("tickets", 0)), inline=True)
            embed.add_field(name="🔇 Муты", value=str(m_dict.get("mutes", 0)), inline=True)
            embed.add_field(name="🚪 Кики", value=str(m_dict.get("kicks", 0)), inline=True)
            embed.add_field(name="🔨 Баны", value=str(m_dict.get("bans", 0)), inline=True)
            embed.add_field(name="⚠️ Варны", value=str(m_dict.get("warns", 0)), inline=True)
            embed.add_field(name="🗑️ Сообщения", value=str(m_dict.get("deleted_msgs", 0)), inline=True)
            embed.add_field(name="📝 Устные выговоры", value=str(m_dict.get("oral_vigs", 0)), inline=True)
            embed.add_field(name="🚫 Строгие выговоры", value=str(m_dict.get("strict_vigs", 0)), inline=True)
            await interaction.followup.send(embed=embed)


    @tree.command(name="givecoin", description="Выдать или забрать Swag Coins у модератора")
    @app_commands.rename(member="модератор", amount="количество")
    @app_commands.describe(
        member="Модератор, которому изменить баланс",
        amount="Количество SC (положительное или отрицательное)"
    )
    async def givecoin_cmd(
        interaction: discord.Interaction,
        member: discord.Member,
        amount: int
    ):
        if not isinstance(interaction.user, discord.Member):
            return

        has_perm = interaction.user.guild_permissions.administrator or any(
            r.id == SHOP_REVIEWER_ROLE_ID for r in interaction.user.roles
        )
        if not has_perm:
            await interaction.response.send_message(embed=error_embed("Недостаточно прав для выдачи Swag Coins."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        await db.add_swag_coins(interaction.guild_id, member.id, amount)
        await db.log_coin_transfer(interaction.guild_id, member.id, amount, interaction.user.id)
        new_bal = await db.get_swag_coins(interaction.guild_id, member.id)


        role_title = get_moderator_position(member)
        sign_str = f"+{amount}" if amount > 0 else str(amount)
        await interaction.followup.send(
            embed=success_embed(f"Успешно изменено `{sign_str} SC` для {member.mention}. Новый баланс: `{new_bal} SC`."),
            ephemeral=True
        )

        log_ch = interaction.guild.get_channel(GIVECOIN_LOG_CHANNEL_ID) if interaction.guild else None
        if log_ch and isinstance(log_ch, discord.TextChannel):
            if PIL_AVAILABLE:
                avatar_img = await fetch_avatar_image(member, size=112)
                if CARDS_AVAILABLE:
                    img_buf = generate_givecoin_card(
                        user_name=member.display_name,
                        role_title=role_title,
                        admin_name=interaction.user.display_name,
                        amount=amount,
                        new_balance=new_bal,
                        avatar_img=avatar_img
                    )
                else:
                    img_buf = create_givecoin_image(
                        user_name=member.display_name,
                        admin_name=interaction.user.display_name,
                        amount=amount,
                        new_balance=new_bal,
                        reason="Выдача коинов",
                        avatar_img=avatar_img
                    )
                file = discord.File(fp=img_buf, filename="givecoin.png")
                await log_ch.send(file=file)
            else:
                embed = discord.Embed(
                    title="💎 Изменение баланса Swag Coins",
                    color=Config.EMBED_COLOR_SUCCESS if amount >= 0 else Config.EMBED_COLOR_ERROR,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Модератор", value=member.mention, inline=True)
                embed.add_field(name="Изменение", value=f"`{sign_str} SC`", inline=True)
                embed.add_field(name="Новый баланс", value=f"`{new_bal} SC`", inline=True)
                embed.add_field(name="Выдал", value=interaction.user.mention, inline=True)
                embed.add_field(name="Причина", value=reason, inline=False)
                await log_ch.send(embed=embed)


    @tree.command(name="vig", description="Выдать выговор модератору")
    @app_commands.rename(user="пользователь", type="тип", reason="причина")
    @app_commands.describe(
        user="Модератор, которому выдаётся выговор",
        type="Тип выговора (строгий или устный)",
        reason="Причина выдачи выговора"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Строгий выговор", value="strict"),
        app_commands.Choice(name="Устный выговор", value="oral"),
    ])
    async def vig_cmd(interaction: discord.Interaction, user: discord.Member, type: app_commands.Choice[str], reason: str):
        member = interaction.user
        has_perm = is_admin_member(member) or any(r.id in VIG_ALLOWED_ROLES for r in getattr(member, "roles", []))
        if not has_perm:
            await interaction.response.send_message(
                embed=missing_role_embed("<@&1369357661967224933>, <@&1538965783311290469>"),
                ephemeral=True
            )
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Вы не можете выдать выговор самому себе."),
                ephemeral=True
            )
            return

        mod_row = await db.get_moderator(interaction.guild_id, user.id)
        if not mod_row:
            await interaction.response.send_message(
                embed=error_embed(f"{user.mention} не является зарегистрированным модератором."),
                ephemeral=True
            )
            return

        # Проверка иерархии: нельзя выдать выговор тому, кто выше по роли
        if not is_admin_member(interaction.user):
            issuer_rank = get_position_rank(interaction.user)
            target_rank = get_position_rank(user)
            if target_rank < issuer_rank:  # цель выше выдающего
                await interaction.response.send_message(
                    embed=error_embed("Роль пользователя выше вашей"),
                    ephemeral=True
                )
                return

        vig_type_val = type.value
        strict_count, oral_count = await db.add_vig(interaction.guild_id, user.id, interaction.user.id, vig_type_val, reason)

        vig_type_name = "Строгий выговор" if vig_type_val == "strict" else "Устный выговор"

        embed = discord.Embed(
            description=f"✅ {vig_type_name} успешно выдан пользователю {user.mention}",
            color=Config.EMBED_COLOR_WARNING
        )
        await interaction.response.send_message(embed=embed)

        # Отправляем в ЛС
        await send_vig_dm(interaction.guild, user, vig_type_name, interaction.user, reason)

        # Авто-снятие ролей при 3/3 строгих выговоров
        if strict_count >= 3:
            MOD_ROLES_TO_REMOVE = {
                r_id for r_id, _ in POSITION_ROLE_MAP
            }
            MOD_ROLES_TO_REMOVE.add(1369357716786778123)
            removed_roles = []
            try:
                for role in list(user.roles):
                    if role.id in MOD_ROLES_TO_REMOVE:
                        await user.remove_roles(role, reason="Авто-снятие: 3/3 строгих выговора")
                        removed_roles.append(role.name)
            except Exception as re_err:
                log.warning("Ошибка при снятии ролей у %s: %s", user.id, re_err)

            DISMISS_CHANNEL_ID = 1369358884673949786
            dismiss_ch = interaction.guild.get_channel(DISMISS_CHANNEL_ID)
            if dismiss_ch:
                now_dt = datetime.now(timezone.utc).astimezone()
                time_str = f"Сегодня, в {now_dt.strftime('%H:%M')}"
                dismiss_embed = discord.Embed(
                    title="❌ Модератор снят с должности",
                    description=f"{user.mention} снят с должности модератора.",
                    color=Config.EMBED_COLOR_ERROR,
                )
                dismiss_embed.add_field(name="Причина", value="`3/3 строгих выговора`", inline=True)
                dismiss_embed.set_footer(text=time_str)
                try:
                    await dismiss_ch.send(embed=dismiss_embed)
                except Exception as ch_err:
                    log.warning("Ошибка отправки в канал увольнения: %s", ch_err)

    @tree.command(name="unvig", description="Снять выговор с модератора")
    @app_commands.rename(user="пользователь", type="тип")
    @app_commands.describe(
        user="Модератор, с которого снимается выговор",
        type="Тип выговора (строгий или устный)"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Строгий выговор", value="strict"),
        app_commands.Choice(name="Устный выговор", value="oral"),
    ])
    async def unvig_cmd(interaction: discord.Interaction, user: discord.Member, type: app_commands.Choice[str]):
        member = interaction.user
        has_perm = is_admin_member(member) or any(r.id in VIG_ALLOWED_ROLES for r in getattr(member, "roles", []))
        if not has_perm:
            await interaction.response.send_message(
                embed=missing_role_embed("<@&1369357661967224933>, <@&1538965783311290469>"),
                ephemeral=True
            )
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message(
                embed=error_embed("Вы не можете снять выговор самому себе."),
                ephemeral=True
            )
            return

        mod_row = await db.get_moderator(interaction.guild_id, user.id)
        if not mod_row:
            await interaction.response.send_message(
                embed=error_embed(f"{user.mention} не является зарегистрированным модератором."),
                ephemeral=True
            )
            return

        # Проверка иерархии: нельзя снять выговор у того, кто выше по роли
        if not is_admin_member(interaction.user):
            issuer_rank = get_position_rank(interaction.user)
            target_rank = get_position_rank(user)
            if target_rank < issuer_rank:
                await interaction.response.send_message(
                    embed=error_embed("Роль пользователя выше вашей"),
                    ephemeral=True
                )
                return

        vig_type_val = type.value
        vig_type_name = "Строгий выговор" if vig_type_val == "strict" else "Устный выговор"

        res = await db.remove_vig(interaction.guild_id, user.id, vig_type_val)
        if res is None:
            await interaction.response.send_message(
                embed=error_embed(f"У пользователя {user.mention} нет выговоров типа «{vig_type_name.lower()}»."),
                ephemeral=True
            )
            return
        strict_count, oral_count = res

        embed = discord.Embed(
            description=f"✅ {vig_type_name} снят с пользователя {user.mention}",
            color=Config.EMBED_COLOR_SUCCESS
        )
        await interaction.response.send_message(embed=embed)

    @tree.command(name="stopn", description="Завершить или продлить неактив модератора")
    @app_commands.rename(member="модератор", action="действие", new_end_date="новая_дата")
    @app_commands.describe(
        member="Модератор, у которого нужно изменить неактив",
        action="Выберите действие: Завершить неактив или Продлить неактив",
        new_end_date="Новая дата окончания (ДД.ММ.ГГГГ) — укажите при выборе 'Продлить'"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Завершить неактив", value="end"),
        app_commands.Choice(name="Продлить неактив", value="extend")
    ])
    async def stopn_cmd(
        interaction: discord.Interaction,
        member: discord.Member,
        action: app_commands.Choice[str],
        new_end_date: Optional[str] = None
    ):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Команда доступна только на сервере."), ephemeral=True)
            return

        has_perm = interaction.user.guild_permissions.administrator or any(
            r.id in {1538965783311290469, 1369357661967224933} for r in interaction.user.roles
        )
        if not has_perm:
            await interaction.response.send_message(
                embed=error_embed("Недостаточно прав для управления неактивом."),
                ephemeral=True
            )
            return

        act = await db.get_active_inactivity(interaction.guild_id, member.id)
        if not act:
            await interaction.response.send_message(
                embed=error_embed(f"У модератора {user_id_tag(member)} нет активного неактива."),
                ephemeral=True
            )
            return

        if action.value == "end":
            await db.end_inactivity(interaction.guild_id, member.id, interaction.user.id)
            await interaction.response.send_message(
                embed=success_embed(f"Неактив модератора {user_id_tag(member)} успешно завершён.")
            )

            try:
                dm_embed = discord.Embed(
                    title="Неактив завершён",
                    description="Ваш неактив был завершён руководством.",
                    color=Config.EMBED_COLOR_MAIN,
                    timestamp=datetime.now(timezone.utc)
                )
                dm_embed.add_field(name="Модератор", value=user_id_tag(member), inline=False)
                dm_embed.add_field(name="Завершил", value=user_id_tag(interaction.user), inline=False)
                await member.send(embed=dm_embed)
            except Exception as e:
                log.info("Не удалось отправить ЛС об окончании неактива модератору %s: %s", member.id, e)

        elif action.value == "extend":
            if not new_end_date or not new_end_date.strip():
                await interaction.response.send_message(
                    embed=error_embed("Для продления неактива обязательно укажите новую дату окончания (ДД.ММ.ГГГГ)."),
                    ephemeral=True
                )
                return

            clean_date = new_end_date.strip()
            await db.extend_inactivity(interaction.guild_id, member.id, clean_date, interaction.user.id)
            await interaction.response.send_message(
                embed=success_embed(f"Неактив модератора {user_id_tag(member)} продлён до `{clean_date}`.")
            )

            try:
                dm_embed = discord.Embed(
                    title="Неактив продлён",
                    description=f"Ваш неактив был продлён руководством до `{clean_date}`.",
                    color=Config.EMBED_COLOR_SUCCESS,
                    timestamp=datetime.now(timezone.utc)
                )
                dm_embed.add_field(name="Модератор", value=user_id_tag(member), inline=False)
                dm_embed.add_field(name="Новая дата окончания", value=f"`{clean_date}`", inline=True)
                dm_embed.add_field(name="Продлил", value=user_id_tag(interaction.user), inline=False)
                await member.send(embed=dm_embed)
            except Exception as e:
                log.info("Не удалось отправить ЛС о продлении неактива модератору %s: %s", member.id, e)

    @tree.command(name="createrole", description="Создать роль на сервере")
    @app_commands.rename(name="название", hex_color="цвет", icon="картинка", target_user="пользователь")
    @app_commands.describe(
        name="Название роли",
        hex_color="Цвет в HEX формате (например: #FF5733 или FF5733)",
        icon="Картинка роли (PNG/JPG, не более 256 КБ)",
        target_user="Пользователь, которому сразу выдать созданную роль"
    )
    async def createrole_cmd(
        interaction: discord.Interaction,
        name: str,
        hex_color: str,
        icon: Optional[discord.Attachment] = None,
        target_user: Optional[discord.Member] = None
    ):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(embed=error_embed("Команда доступна только на сервере."), ephemeral=True)
            return

        has_perm = interaction.user.guild_permissions.administrator or any(
            r.id in CREATEROLE_ALLOWED_ROLES for r in interaction.user.roles
        )
        if not has_perm:
            await interaction.response.send_message(
                embed=error_embed("Недостаточно прав. Команда доступна <@&1459500206725795983> и <@&1462404697863356602>."),
                ephemeral=True
            )
            return

        hex_color = hex_color.strip().lstrip("#")
        try:
            color_int = int(hex_color, 16)
            role_color = discord.Color(color_int)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed(f"Неверный HEX-цвет: `#{hex_color}`. Пример: `#FF5733` или `FF5733`."),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        role_icon_bytes: Optional[bytes] = None
        if icon:
            if icon.size > 256 * 1024:
                await interaction.followup.send(embed=error_embed("Размер картинки не должен превышать 256 КБ."), ephemeral=True)
                return
            if not icon.content_type or not icon.content_type.startswith("image/"):
                await interaction.followup.send(embed=error_embed("Прикреплённый файл должен быть изображением (PNG/JPG)."), ephemeral=True)
                return
            try:
                role_icon_bytes = await icon.read()
            except Exception as e:
                log.warning("Не удалось скачать иконку роли: %s", e)

        guild = interaction.guild
        try:
            kwargs: dict = {
                "name": name,
                "color": role_color,
                "reason": f"Создано командой /createrole пользователем {interaction.user} ({interaction.user.id})"
            }
            if role_icon_bytes:
                kwargs["display_icon"] = role_icon_bytes

            new_role = await guild.create_role(**kwargs)
        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("У бота нет прав для создания ролей."), ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(embed=error_embed(f"Ошибка при создании роли: {e}"), ephemeral=True)
            return

        try:
            all_roles = await guild.fetch_roles()
            above_role = discord.utils.get(all_roles, id=CREATEROLE_ABOVE_ROLE_ID)
            if above_role:
                target_position = max(above_role.position - 1, 1)
                await new_role.edit(position=target_position)
        except Exception as e:
            log.warning("Не удалось переместить роль %s: %s", new_role.id, e)

        if target_user:
            try:
                await target_user.add_roles(new_role, reason=f"Выдача созданной роли по команде /createrole от {interaction.user}")
            except Exception as u_err:
                log.warning("Не удалось выдать созданную роль пользователю %s: %s", target_user.id, u_err)

        embed = discord.Embed(
            title="Роль создана",
            color=role_color,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Название", value=f"{new_role.mention}", inline=True)
        embed.add_field(name="Цвет", value=f"`#{hex_color.upper()}`", inline=True)
        embed.add_field(name="ID", value=f"`{new_role.id}`", inline=True)
        if target_user:
            embed.add_field(name="Выдана", value=target_user.mention, inline=True)
        if icon and role_icon_bytes:
            embed.add_field(name="Иконка", value="Установлена", inline=True)

        await interaction.followup.send(embed=embed)

    @tree.command(name="help", description="Справка по командам бота")
    async def help_cmd(interaction: discord.Interaction):
        avatar = interaction.client.user.display_avatar.url if interaction.client.user else HELP_THUMBNAIL_URL
        await interaction.response.send_message(
            embed=help_main_embed(avatar),
            view=HelpView(avatar),
            ephemeral=True,
        )

    @tree.command(name="ping", description="Проверить задержку и отклик бота")
    async def ping_cmd(interaction: discord.Interaction):
        start = datetime.now(timezone.utc)
        await interaction.response.defer(ephemeral=True)
        end = datetime.now(timezone.utc)
        latency_ms = round(interaction.client.latency * 1000)
        response_ms = round((end - start).total_seconds() * 1000)

        embed = discord.Embed(title="🏓 Понг!", color=Config.EMBED_COLOR_MAIN)
        embed.add_field(name="Задержка Discord API", value=f"`{latency_ms} ms`", inline=True)
        embed.add_field(name="Отклик бота", value=f"`{response_ms} ms`", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(name="news", description="Отправить новость по шаблону")
    @require_mod_permission("news")
    async def news_cmd(interaction: discord.Interaction):
        view = NewsTemplateSelectView(bot, interaction.guild_id)
        await interaction.response.send_message(
            "📰 **Выбор шаблона новости**\nВыберите нужный шаблон из меню ниже:",
            view=view,
            ephemeral=True
        )

    @tree.command(name="setup_honeypot", description="Установить ловушку для отлова ботов (honeypot)")
    @app_commands.rename(channel="канал")
    @app_commands.describe(channel="Канал для ловушки (по умолчанию — текущий или 1537823764337922058)")
    @is_administrator()
    async def setup_honeypot_cmd(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        target_ch = channel or interaction.channel
        if not isinstance(target_ch, discord.TextChannel):
            default_ch = interaction.guild.get_channel(1537823764337922058) if interaction.guild else None
            if default_ch and isinstance(default_ch, discord.TextChannel):
                target_ch = default_ch
            else:
                await interaction.response.send_message(embed=error_embed("Укажите текстовый канал."), ephemeral=True)
                return

        await interaction.response.defer(ephemeral=True)
        hp_info = await db.get_honeypot_info(interaction.guild_id)
        count = hp_info.get("honeypot_count", 0)
        bot_avatar = interaction.client.user.display_avatar.url if interaction.client.user else None

        embed = honeypot_embed(bot_avatar)
        view = HoneypotView(count)

        msg = await target_ch.send(embed=embed, view=view)
        await db.set_honeypot_info(interaction.guild_id, target_ch.id, msg.id, count)

        await interaction.followup.send(
            embed=success_embed(f"Ловушка ботов успешно отправлена в канал {target_ch.mention}!"),
            ephemeral=True
        )

    @tree.command(name="export_db", description="Отправить файл базы данных в Telegram (ID 8035721101)")
    @is_administrator()
    async def export_db_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, export_database_to_tg, 8035721101)
        if success:
            embed = success_embed("💾 Файл базы данных `moderbot.sqlite3` успешно отправлен в Telegram ID `8035721101`!")
        else:
            embed = error_embed("❌ Не удалось выгрузить базу данных в Telegram.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(name="reload_db", description="Переподключить и синхронизировать базу данных SQLite")
    @is_administrator()
    async def reload_db_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await db.connect()
            embed = success_embed("🔄 База данных `moderbot.sqlite3` успешно переподключена и синхронизирована!")
        except Exception as exc:
            embed = error_embed(f"❌ Ошибка при переподключении базы данных: {exc}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(name="history", description="Посмотреть историю наказаний пользователя")
    @app_commands.rename(user="пользователь")
    @app_commands.describe(user="Пользователь, историю наказаний которого нужно посмотреть")
    async def history_cmd(interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)

        gid = str(interaction.guild_id)
        uid = str(user.id)

        all_logs = history_logs_of(gid)

        user_logs = []
        for x in all_logs:
            if x.get("category") != "moderation":
                continue
            desc = x.get("description", "") or ""
            title = x.get("title", "") or ""
            combined = desc + " " + title
            if uid in combined:
                user_logs.append(x)

        if not user_logs:
            emb = discord.Embed(
                title=f"Наказания: {user.display_name}",
                description="Нет записей о наказаниях.",
                color=0x57F287,
            )
            emb.set_thumbnail(url=user.display_avatar.url)
            await interaction.followup.send(embed=emb, ephemeral=True)
            return

        parts = []
        for x in user_logs[:30]:
            ts = format_ts(x.get("ts", 0))
            t = x.get("title", "")
            d = x.get("description", "")
            parts.append(f"**[{ts}]** {t}")
            if d:
                parts.append(f"  {d}")

        emb = discord.Embed(
            title=f"Наказания: {user.display_name}",
            description="\n".join(parts),
            color=0xFEE75C,
        )
        emb.set_thumbnail(url=user.display_avatar.url)
        emb.set_footer(text=f"Записей: {len(user_logs)}")
        await interaction.followup.send(embed=emb, ephemeral=True)

    @tree.command(name="pm", description="Отправить личное сообщение пользователю")
    @app_commands.rename(user="пользователь", text="сообщение")
    @app_commands.describe(user="Пользователь", text="Текст сообщения")
    @is_administrator()
    async def pm_cmd(interaction: discord.Interaction, user: discord.Member, text: str):
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            description=text,
            color=Config.EMBED_COLOR_MAIN,
        )
        clean_name = re.sub(r"\[.*?\]", "", interaction.user.display_name).strip() or interaction.user.name
        embed.set_footer(text=f"От: @{interaction.user.name}")

        try:
            await user.send(embed=embed)
            embed_success = discord.Embed(
                description=f"Сообщение успешно отправлено пользователю {user.mention}.",
                color=Config.EMBED_COLOR_SUCCESS,
            )
            await interaction.followup.send(embed=embed_success, ephemeral=True)
        except discord.Forbidden:
            embed_error = discord.Embed(
                description=f"Не удалось отправить сообщение пользователю {user.mention}. У пользователя закрыты личные сообщения.",
                color=Config.EMBED_COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)
        except Exception as exc:
            embed_error = discord.Embed(
                description=f"Ошибка при отправке сообщения: {exc}",
                color=Config.EMBED_COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)

    @tree.command(name="active", description="Показать активность модераторов за неделю")
    @app_commands.rename(week="неделя")
    @app_commands.describe(week="0 — текущая неделя, 1 — прошлая неделя")
    @require_mod_permission("pm")
    async def active_cmd(interaction: discord.Interaction, week: int = 0):
        await interaction.response.defer(ephemeral=True)
        now = datetime.now(timezone.utc)
        weekday = now.weekday()
        monday = now - timedelta(days=weekday)
        week_start = datetime(monday.year, monday.month, monday.day, 0, 0, 0, tzinfo=timezone.utc)
        week_end = week_start + timedelta(days=7)
        if week == 1:
            week_start -= timedelta(days=7)
            week_end -= timedelta(days=7)
        elif week == 0:
            pass
        else:
            await interaction.followup.send(embed=error_embed("Неверный параметр недели. Используйте 0 или 1."), ephemeral=True)
            return

        def _get_week_key(dt):
            return dt.strftime("%Y-%m-%d")

        def _get_start_totals(guild_id, week_key):
            wt = data.get("week_totals", {})
            g = wt.get(str(guild_id), {})
            return g.get(week_key, {})

        def _set_start_totals(guild_id, week_key, totals_dict):
            wt = data.setdefault("week_totals", {})
            g = wt.setdefault(str(guild_id), {})
            g[week_key] = totals_dict
            save_data()

        current_week_key = _get_week_key(week_start)
        start_totals = _get_start_totals(interaction.guild_id, current_week_key)

        if week == 0 and not start_totals:
            mods_all = await db.list_moderators(interaction.guild_id)
            for m in mods_all:
                m2 = dict(m)
                uid = str(m2["user_id"])
                start_totals[uid] = {
                    "tickets": m2.get("tickets", 0),
                    "likes": m2.get("likes", 0),
                    "dislikes": m2.get("dislikes", 0),
                    "mutes": m2.get("mutes", 0),
                    "kicks": m2.get("kicks", 0),
                    "bans": m2.get("bans", 0),
                    "warns": m2.get("warns", 0),
                    "deleted_msgs": m2.get("deleted_msgs", 0),
                }
            _set_start_totals(interaction.guild_id, current_week_key, start_totals)

        def calc_total(stats):
            return (stats.get("tickets", 0) + stats.get("likes", 0) + stats.get("dislikes", 0)
                    + stats.get("mutes", 0) + stats.get("kicks", 0) + stats.get("bans", 0)
                    + stats.get("warns", 0) + stats.get("deleted_msgs", 0))

        async def _get_moderator_name(uid_int):
            member = interaction.guild.get_member(uid_int)
            if member:
                return member.display_name
            cached_user = interaction.client.get_user(uid_int)
            if cached_user:
                return cached_user.name
            try:
                user = await interaction.client.fetch_user(uid_int)
                return user.name
            except Exception:
                return f"User {uid_int}"

        mods = await db.list_moderators(interaction.guild_id)
        if not mods:
            await interaction.followup.send(embed=error_embed("Нет зарегистрированных модераторов."), ephemeral=True)
            return

        if week == 1 and not start_totals:
            history = history_logs_of(str(interaction.guild_id))
            mod_changes = {}
            for m in mods:
                m2 = dict(m)
                uid = m2["user_id"]
                change = 0
                for log_entry in history:
                    if log_entry.get("category") != "moderation":
                        continue
                    ts = log_entry.get("ts", 0)
                    log_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    if log_dt < week_start or log_dt >= week_end:
                        continue
                    actor_id = log_entry.get("actor_id")
                    if actor_id and str(actor_id) == str(uid):
                        change += 1
                mod_changes[uid] = change

        rows = []
        for m in mods:
            m2 = dict(m)
            uid = m2["user_id"]
            uid_str = str(uid)

            name = await _get_moderator_name(uid)

            if week == 0:
                end_total = calc_total(m2)
                st = start_totals.get(uid_str, {})
                start_total = calc_total(st)
                change = end_total - start_total
            else:
                st = start_totals.get(uid_str, {})
                start_total = calc_total(st)
                change = mod_changes.get(uid, 0)
                end_total = start_total + change

            rows.append((name, start_total, end_total, change))
        rows.sort(key=lambda x: x[3], reverse=True)
        week_label = "Текущая неделя" if week == 0 else "Прошлая неделя"
        week_range = f"{week_start.strftime('%d.%m')} — {(week_end - timedelta(days=1)).strftime('%d.%m')}"
        table_header = (
            "**Модератор** | **В начале недели** | **В конце недели** | **Изменение**\n"
            "--- | --- | --- | ---\n"
        )
        table_rows = ""
        for name, start_t, end_t, change in rows:
            change_str = f"+{change}" if change > 0 else str(change)
            table_rows += f"**{name}** | {start_t} | {end_t} | {change_str}\n"
        embed = discord.Embed(
            title=f"Активность модераторов — {week_label}",
            description=f"Период: `{week_range}`",
            color=Config.EMBED_COLOR_MAIN,
        )
        embed.add_field(
            name="",
            value=table_header + table_rows if table_rows else "Нет данных",
            inline=False,
        )
        embed.set_footer(text=f"Всего модераторов: {len(rows)}")
        css = "* { margin: 0; padding: 0; box-sizing: border-box; }"
        css += " body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; background: #0f0f0f; color: #e0e0e0; padding: 40px 20px; }"
        css += " .container { max-width: 900px; margin: 0 auto; background: #1a1a1a; border-radius: 12px; padding: 30px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }"
        css += " h1 { font-size: 24px; margin-bottom: 10px; color: #ffffff; border-bottom: 2px solid #5865F2; padding-bottom: 10px; }"
        css += " .subtitle { font-size: 14px; color: #888; margin-bottom: 30px; }"
        css += " table { width: 100%; border-collapse: collapse; margin-top: 20px; }"
        css += " thead { background: #2a2a2a; }"
        css += " th { padding: 12px 16px; text-align: left; font-weight: 600; color: #5865F2; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }"
        css += " td { padding: 12px 16px; border-bottom: 1px solid #2a2a2a; font-size: 14px; }"
        css += " tbody tr:hover { background: #222222; }"
        css += " tbody tr:last-child td { border-bottom: none; }"
        css += " .change-positive { color: #57F287; font-weight: 600; }"
        css += " .change-zero { color: #888; }"
        css += " .change-negative { color: #ED4245; font-weight: 600; }"
        css += " .stats { display: flex; gap: 20px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #2a2a2a; }"
        css += " .stat-item { flex: 1; background: #222; padding: 15px; border-radius: 8px; text-align: center; }"
        css += " .stat-value { font-size: 28px; font-weight: 700; color: #5865F2; margin-bottom: 5px; }"
        css += " .stat-label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }"
        html_content = "<!DOCTYPE html>\n<html lang=\"ru\">\n<head>\n<meta charset=\"UTF-8\">\n"
        html_content += "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        html_content += "<title>Активность модераторов</title>\n<style>\n" + css + "\n</style>\n</head>\n<body>\n"
        html_content += "<div class=\"container\">\n<h1>Активность модераторов</h1>\n"
        html_content += "<div class=\"subtitle\">{} • {}</div>\n".format(week_label, week_range)
        html_content += "<table>\n<thead>\n<tr>\n<th>Модератор</th>\n<th>В начале недели</th>\n<th>В конце недели</th>\n<th>Изменение</th>\n</tr>\n</thead>\n<tbody>\n"
        for name, start_t, end_t, change in rows:
            change_class = "change-positive" if change > 0 else ("change-negative" if change < 0 else "change-zero")
            change_str = "+{}".format(change) if change > 0 else str(change)
            html_content += "<tr><td><strong>{}</strong></td><td>{}</td><td>{}</td><td class='{}'>{}</td></tr>\n".format(name, start_t, end_t, change_class, change_str)
        html_content += "</tbody>\n</table>\n"
        html_content += "<div class=\"stats\">\n"
        html_content += "<div class=\"stat-item\"><div class=\"stat-value\">{}</div><div class=\"stat-label\">Всего модераторов</div></div>\n".format(len(rows))
        html_content += "<div class=\"stat-item\"><div class=\"stat-value\">{}</div><div class=\"stat-label\">Всего действий</div></div>\n".format(sum(r[2] for r in rows))
        html_content += "<div class=\"stat-item\"><div class=\"stat-value\">{}</div><div class=\"stat-label\">Общее изменение</div></div>\n".format(sum(r[3] for r in rows))
        html_content += "</div>\n</div>\n</body>\n</html>"
        with open("active_report.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        file = discord.File("active_report.html", filename="active_report.html")
        embed.add_field(
            name="📎 Файл отчёта",
            value="HTML-файл с таблицей активности прикреплён к сообщению.",
            inline=False,
        )
        await interaction.followup.send(embed=embed, file=file)

    @tree.command(name="forma", description="Отправить форму наказания на рассмотрение")
    @app_commands.rename(
        type="тип",
        target="нарушитель",
        duration="длительность",
        proof="доказательства",
        reason="причина"
    )
    @app_commands.describe(
        type="Тип наказания",
        target="Пользователь, которого наказываем",
        duration="Длительность (для мута/бана, например: 30m, 1h, 1d, permanent). Для кика не требуется.",
        proof="Скриншот или файл с доказательством",
        reason="Причина наказания"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Mute (Мут)", value="mute"),
        app_commands.Choice(name="Kick (Кик)", value="kick"),
        app_commands.Choice(name="Ban (Бан)", value="ban"),
    ])
    @require_mod_permission("forma")
    async def forma_cmd(interaction: discord.Interaction, type: str, target: discord.Member, duration: Optional[str], proof: discord.Attachment, reason: str):
        await interaction.response.defer(ephemeral=True)
        form_type = type.lower().strip()
        if form_type not in ("mute", "kick", "ban"):
            await interaction.followup.send(embed=error_embed("Неверный тип наказания. Используй: `mute`, `kick`, `ban`."), ephemeral=True)
            return
        if form_type != "kick" and not duration:
            await interaction.followup.send(embed=error_embed("Укажите длительность наказания."), ephemeral=True)
            return
        proof_url = proof.url
        form_id = await db.create_punishment_form(interaction.guild_id, interaction.user.id, form_type, target.mention, duration or "Не указано", reason, proof_url)
        await interaction.followup.send(embed=success_embed("Форма наказания отправлена на рассмотрение!"), ephemeral=True)
        new_form = await db.get_form(form_id)
        if new_form and interaction.channel:
            await _send_single_form(new_form, interaction.channel)


    @tree.command(name="pending", description="Показать ожидающие формы наказаний")
    @require_mod_permission("pm")
    async def pending_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        forms = await db.get_pending_forms(interaction.guild_id)
        if not forms:
            await interaction.followup.send(embed=discord.Embed(description="Нет ожидающих форм.", color=Config.EMBED_COLOR_SUCCESS), ephemeral=True)
            return
        await _display_forms(interaction, forms)

    @tree.command(name="notif", description="Отправить оповещение от имени бота")
    async def notif_cmd(interaction: discord.Interaction):
        main_guild = interaction.client.get_guild(1070704320951095296) or interaction.guild
        member = None
        if main_guild:
            member = main_guild.get_member(interaction.user.id)

        has_role = False
        NOTIF_ROLE_ID = 1537451548622332025
        if member:
            has_role = any(r.id == NOTIF_ROLE_ID for r in member.roles) or member.guild_permissions.administrator
        elif isinstance(interaction.user, discord.Member):
            has_role = any(r.id == NOTIF_ROLE_ID for r in interaction.user.roles) or interaction.user.guild_permissions.administrator

        if not has_role:
            await interaction.response.send_message(
                embed=missing_role_embed("<@&1537451548622332025>"),
                ephemeral=True
            )
            return

        await interaction.response.send_modal(NotifTextModal(bot))

    @tree.command(name="register", description="Зарегистрировать модератора в системе")
    @app_commands.rename(user="пользователь")
    @app_commands.describe(user="Пользователь, которого нужно зарегистрировать")
    @require_mod_permission("register")
    async def register_cmd(interaction: discord.Interaction, user: discord.Member):
        created = await db.register_moderator(interaction.guild_id, user.id)
        if not created:
            await interaction.response.send_message(
                embed=error_embed(f"{user.mention} уже зарегистрирован как модератор."), ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=success_embed(f"{user.mention} зарегистрирован как модератор.")
        )

    @tree.command(name="unregister", description="Удалить модератора из системы")
    @app_commands.rename(user="пользователь")
    @app_commands.describe(user="Пользователь, которого нужно разрегистрировать")
    @require_mod_permission("unregister")
    async def unregister_cmd(interaction: discord.Interaction, user: discord.Member):
        deleted = await db.unregister_moderator(interaction.guild_id, user.id)
        if not deleted:
            await interaction.response.send_message(
                embed=error_embed(f"{user.mention} не является зарегистрированным модератором."), ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=success_embed(f"{user.mention} был удален из списка модераторов.")
        )

    @tree.command(name="clearmoders", description="Удалить ВСЕХ модераторов из базы данных")
    @is_administrator()
    async def clearmoders_cmd(interaction: discord.Interaction):
        count = await db.clear_all_moderators(interaction.guild_id)
        await interaction.response.send_message(
            embed=success_embed(f"Из базы данных было успешно удалено модераторов: **{count}**.")
        )

    @tree.command(name="save", description="Сохранить шаблон структуры сервера (роли, каналы, вебхуки)")
    @is_administrator()
    async def save_cmd(interaction: discord.Interaction):
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        data = await make_template(interaction.guild)

        path = guild_dir(interaction.guild_id)
        file_name = f"{int(time.time())}.json"
        with open(os.path.join(path, file_name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        n = len(list_backups(interaction.guild_id))
        embed = discord.Embed(title="💾 Шаблон сервера сохранён", color=Config.EMBED_COLOR_SUCCESS)
        embed.add_field(name="Номер шаблона", value=f"`{n}`", inline=True)
        embed.add_field(name="Дата сохранения", value=f"`{data['date']}`", inline=True)
        embed.add_field(name="Ролей", value=f"`{len(data['roles'])}`", inline=True)
        embed.add_field(name="Каналов", value=f"`{len(data['channels'])}`", inline=True)
        embed.add_field(name="Вебхуков", value=f"`{len(data['webhooks'])}`", inline=True)
        embed.set_footer(text=f"Используйте /load номер:{n} для восстановления")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(name="load", description="Загрузить сохранённый шаблон структуры сервера")
    @app_commands.rename(number="номер")
    @app_commands.describe(number="Номер шаблона (вызовите /load без параметра для списка)")
    @is_administrator()
    async def load_cmd(interaction: discord.Interaction, number: Optional[int] = None):
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True)
        backups = list_backups(interaction.guild_id)

        if not backups:
            await interaction.followup.send(
                embed=error_embed("Сохранённых шаблонов нет. Сначала создайте через `/save`."), ephemeral=True
            )
            return

        if number is None:
            lines = []
            for i, p in enumerate(backups, 1):
                try:
                    with open(p, encoding="utf-8") as f:
                        d = json.load(f)
                    lines.append(f"**{i}** — `{d.get('date', 'Н/Д')}` (Каналов: {len(d.get('channels', []))}, Ролей: {len(d.get('roles', []))})")
                except Exception:
                    lines.append(f"**{i}** — `Ошибка чтения`")
            embed = discord.Embed(
                title="📂 Сохранённые шаблоны сервера",
                description="\n".join(lines) + "\n\nИспользуйте: `/load номер:<число>`",
                color=Config.EMBED_COLOR_MAIN,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if number < 1 or number > len(backups):
            await interaction.followup.send(
                embed=error_embed(f"Шаблон под номером {number} не найден. Доступно: {len(backups)}."), ephemeral=True
            )
            return

        with open(backups[number - 1], encoding="utf-8") as f:
            data = json.load(f)

        errors = await apply_template(interaction.guild, data)

        embed = discord.Embed(title="✅ Шаблон сервера успешно применён", color=Config.EMBED_COLOR_SUCCESS)
        embed.add_field(name="Дата шаблона", value=f"`{data.get('date', 'Н/Д')}`", inline=False)
        embed.add_field(name="Ролей", value=f"`{len(data.get('roles', []))}`", inline=True)
        embed.add_field(name="Каналов", value=f"`{len(data.get('channels', []))}`", inline=True)
        embed.add_field(name="Вебхуков", value=f"`{len(data.get('webhooks', []))}`", inline=True)
        if errors:
            embed.add_field(name="⚠️ Пропущено ошибок", value=f"`{errors}`", inline=True)
        embed.set_footer(text="Developer: @m0plex • URL вебхуков создаются новые")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(name="report", description="Написать жалобу/вопрос/уведомить о баге")
    @app_commands.rename(text="текст")
    @app_commands.describe(text="Текст вашего репорта")
    async def discord_report(interaction: discord.Interaction, text: str):
        await interaction.response.defer(ephemeral=True)
        try:
            ticket_id = get_next_ticket_id()
            data.setdefault("tickets", {})[str(ticket_id)] = {
                "id": ticket_id,
                "author": str(interaction.user),
                "author_id": interaction.user.id,
                "author_discord_id": interaction.user.id,
                "title": "Репорт от Discord",
                "content": text,
                "status": "open",
                "taken_by": None,
                "taken_at": None,
                "answers": [],
                "created_at": datetime.now(timezone.utc).timestamp(),
                "guild_id": interaction.guild.id if interaction.guild else 0,
                "guild_name": interaction.guild.name if interaction.guild else "ЛС",
                "channel_id": interaction.channel.id if interaction.channel else 0,
                "source": "discord"
            }
            save_data()

            sent = False
            if tg_bot_ref:
                target_chats = set(data.get("tg_access", []))
                if data.get("tg_owner"):
                    target_chats.add(data["tg_owner"])
                for chat_id in target_chats:
                    try:
                        await tg_bot_ref.send_message(
                            chat_id=chat_id,
                            text=(
                                f"🎫 **Новый репорт #{ticket_id}**\n\n"
                                f"**От:** {interaction.user} (ID: {interaction.user.id})\n"
                                f"**Сервер:** {interaction.guild.name if interaction.guild else 'ЛС'}\n"
                                f"**Текст:** {text}\n\n"
                                f"Для ответа: /p {ticket_id}"
                            ),
                            parse_mode="Markdown"
                        )
                        sent = True
                    except Exception as e:
                        log.error("Ошибка отправки тикета в TG: %s", e)

            if sent:
                await interaction.followup.send(f"✅ Ваш репорт отправлен! Номер тикета: #{ticket_id}", ephemeral=True)
            else:
                await interaction.followup.send(f"✅ Ваш репорт #{ticket_id} создан и сохранён!", ephemeral=True)
        except Exception as e:
            log.error("Ошибка создания репорта: %s", e)
            await interaction.followup.send("❌ Произошла ошибка при создании репорта.", ephemeral=True)

    @tree.command(name="moderinfo", description="Профиль модератора")
    @app_commands.rename(user="пользователь")
    @app_commands.describe(user="Модератор (по умолчанию — вы)")
    async def moderinfo_cmd(interaction: discord.Interaction, user: Optional[discord.Member] = None):
        try:
            target = user or interaction.user
            stats = await db.get_moderator(interaction.guild_id, target.id)
            if stats is None:
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=not_registered_embed(), ephemeral=True)
                else:
                    await interaction.followup.send(embed=not_registered_embed(), ephemeral=True)
                return
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=moderinfo_embed(target, stats))
            else:
                await interaction.followup.send(embed=moderinfo_embed(target, stats))
        except Exception as err:
            log.error("Ошибка в /moderinfo: %s", err)

    @tree.command(name="avatar", description="Посмотреть аватар пользователя")
    @app_commands.rename(user="пользователь")
    @app_commands.describe(user="Пользователь (по умолчанию — вы)")
    async def avatar_cmd(interaction: discord.Interaction, user: Optional[discord.User] = None):
        target = user or interaction.user
        await interaction.response.send_message(embed=avatar_embed(target), ephemeral=True)

    @tree.command(name="moderlist", description="Список всех зарегистрированных модераторов")
    @is_registered_moderator()
    async def moderlist_cmd(interaction: discord.Interaction):
        moderators = await db.list_moderators(interaction.guild_id)
        if not moderators:
            await interaction.response.send_message(
                embed=base_embed(description="Пока нет ни одного зарегистрированного модератора.")
            )
            return
        view = ModerListPaginator(moderators, interaction.guild)
        if view.total_pages > 1:
            await interaction.response.send_message(embed=view.current_embed(), view=view)
        else:
            await interaction.response.send_message(embed=view.current_embed())

    setstat_group = app_commands.Group(name="setstat", description="Изменение статистики модератора")

    @setstat_group.command(name="moder", description="Вручную изменить статистику модератора")
    @app_commands.rename(user="пользователь", stat_type="тип_статистики", value="значение")
    @app_commands.describe(user="Модератор", stat_type="Тип статистики", value="Новое значение")
    @app_commands.choices(stat_type=STAT_CHOICES)
    @require_mod_permission("setstat_moder")
    async def setstat_moder(interaction: discord.Interaction, user: discord.Member,
                             stat_type: app_commands.Choice[str], value: int):
        mod_row = await db.get_moderator(interaction.guild_id, user.id)
        if not mod_row:
            await db.register_moderator(interaction.guild_id, user.id)
            old_val = 0
        else:
            old_val = mod_row[stat_type.value]

        await db.set_stat(interaction.guild_id, user.id, stat_type.value, value)
        await db.save_moderators_backup(interaction.guild_id)

        STAT_GENITIVE = {
            "tickets": "тикетов",
            "likes": "лайков",
            "dislikes": "дизлайков",
            "mutes": "мутов",
            "kicks": "киков",
            "bans": "банов",
            "warns": "варнов",
            "deleted_msgs": "удаленных сообщений",
        }
        type_str = STAT_GENITIVE.get(stat_type.value, stat_type.name)

        embed = discord.Embed(
            description=f"Вы успешно изменили значение `{type_str}` пользователя {user.mention} на `{value}` (`было` `{old_val}`)",
            color=Config.EMBED_COLOR_MAIN,
        )
        await interaction.response.send_message(embed=embed)

    tree.add_command(setstat_group)

    @tree.command(name="kick", description="Кикнуть пользователя с сервера")
    @app_commands.rename(user="пользователь", proof="доказательства", reason="причина")
    @app_commands.describe(user="Пользователь", proof="Скриншот или файл с доказательством", reason="Причина")
    @require_mod_permission("kick")
    async def kick_cmd(interaction: discord.Interaction, user: discord.Member, proof: discord.Attachment, reason: str = "Не указана"):
        if user.id == interaction.user.id:
            await interaction.response.send_message(embed=error_embed("Вы не можете кикнуть самого себя."), ephemeral=True)
            return
        if user.id == interaction.client.user.id:
            await interaction.response.send_message(embed=error_embed("Вы не можете кикнуть бота."), ephemeral=True)
            return
        if user.top_role >= interaction.user.top_role and not is_admin_member(interaction.user):
            await interaction.response.send_message(embed=error_embed("Нельзя кикнуть пользователя с ролью выше или равной Вашей."), ephemeral=True)
            return

        proof_url = proof.url
        await send_punishment_dm(interaction.guild, user, "Кик", interaction.user, reason, proof_url=proof_url)

        try:
            await user.kick(reason=f"{reason} | Модератор: {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("У бота недостаточно прав для кика этого пользователя."), ephemeral=True)
            return
        log_embed = punishment_log_embed("Кик", "👢", interaction.user, user, reason, proof_url=proof_url)
        await interaction.response.send_message(embed=log_embed)
        await send_log(interaction.guild, "moderation", log_embed)

    @tree.command(name="mute", description="Замьютить пользователя (timeout)")
    @app_commands.rename(user="пользователь", duration="длительность", proof="доказательства", reason="причина")
    @app_commands.describe(user="Пользователь", duration="Длительность, напр. 10m, 2h, 1d", proof="Скриншот или файл с доказательством", reason="Причина")
    @require_mod_permission("mute")
    async def mute_cmd(interaction: discord.Interaction, user: discord.Member, duration: str, proof: discord.Attachment, reason: str = "Не указана"):
        if user.id == interaction.user.id:
            await interaction.response.send_message(embed=error_embed("Вы не можете замьютить самого себя."), ephemeral=True)
            return
        if user.id == interaction.client.user.id:
            await interaction.response.send_message(embed=error_embed("Вы не можете замьютить бота."), ephemeral=True)
            return
        if user.top_role >= interaction.user.top_role and not is_admin_member(interaction.user):
            await interaction.response.send_message(embed=error_embed("Нельзя замьютить пользователя с ролью выше или равной Вашей."), ephemeral=True)
            return
        if user.is_timed_out():
            await interaction.response.send_message(embed=error_embed("Этот пользователь уже находится в мьюте."), ephemeral=True)
            return
        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            await interaction.response.send_message(embed=error_embed(str(exc)), ephemeral=True)
            return
        if seconds is None:
            seconds = 28 * 86400                                                                 
        seconds = min(seconds, 28 * 86400)

        proof_url = proof.url

        try:
            await user.timeout(timedelta(seconds=seconds), reason=f"{reason} | Модератор: {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("У бота недостаточно прав для мута этого пользователя."), ephemeral=True)
            return

        await send_punishment_dm(interaction.guild, user, "Мут", interaction.user, reason, duration_seconds=seconds, proof_url=proof_url)

        log_embed = punishment_log_embed("Мут", "🔇", interaction.user, user, reason, duration_seconds=seconds, proof_url=proof_url)
        await interaction.response.send_message(embed=log_embed)
        await send_log(interaction.guild, "moderation", log_embed)

    @tree.command(name="unmute", description="Снять мьют с пользователя")
    @app_commands.rename(user="пользователь", reason="причина")
    @app_commands.describe(user="Пользователь", reason="Причина")
    @require_mod_permission("unmute")
    async def unmute_cmd(interaction: discord.Interaction, user: discord.Member, reason: str = "Не указана"):
        if user.id == interaction.user.id:
            await interaction.response.send_message(embed=error_embed("Вы не можете снять мьют с самого себя."), ephemeral=True)
            return
        if not user.is_timed_out():
            await interaction.response.send_message(embed=error_embed("Этот пользователь не находится в мьюте."), ephemeral=True)
            return
        try:
            await user.timeout(None, reason=f"{reason} | Модератор: {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("У бота недостаточно прав."), ephemeral=True)
            return
        log_embed = punishment_log_embed("Размут", "🔊", interaction.user, user, reason)
        await interaction.response.send_message(embed=log_embed)
        await send_log(interaction.guild, "moderation", log_embed)

    @tree.command(name="ban", description="Забанить пользователя")
    @app_commands.rename(user="пользователь", duration="длительность", proof="доказательства", reason="причина")
    @app_commands.describe(user="Пользователь", duration="Длительность (напр. 7d) или 'навсегда'", proof="Скриншот или файл с доказательством", reason="Причина")
    @require_mod_permission("ban")
    async def ban_cmd(interaction: discord.Interaction, user: discord.Member, duration: str, proof: discord.Attachment, reason: str = "Не указана"):
        if user.id == interaction.user.id:
            await interaction.response.send_message(embed=error_embed("Вы не можете забанить самого себя."), ephemeral=True)
            return
        if user.id == interaction.client.user.id:
            await interaction.response.send_message(embed=error_embed("Вы не можете забанить бота."), ephemeral=True)
            return
        if user.top_role >= interaction.user.top_role and not is_admin_member(interaction.user):
            await interaction.response.send_message(embed=error_embed("Нельзя забанить пользователя с ролью выше или равной Вашей."), ephemeral=True)
            return
        try:
            await interaction.guild.fetch_ban(user)
            await interaction.response.send_message(embed=error_embed("Этот пользователь уже находится в бане на сервере."), ephemeral=True)
            return
        except discord.NotFound:
            pass
        except discord.HTTPException:
            pass

        try:
            seconds = parse_duration(duration)
        except ValueError as exc:
            await interaction.response.send_message(embed=error_embed(str(exc)), ephemeral=True)
            return

        proof_url = proof.url

        await send_punishment_dm(interaction.guild, user, "Бан", interaction.user, reason, duration_seconds=seconds, proof_url=proof_url)

        try:
            await user.ban(reason=f"{reason} | Модератор: {interaction.user}", delete_message_seconds=0)
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("У бота недостаточно прав для бана этого пользователя."), ephemeral=True)
            return

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds) if seconds else None
        await db.add_punishment(interaction.guild_id, user.id, "ban", expires_at)
        log_embed = punishment_log_embed("Бан", "🔨", interaction.user, user, reason, duration_seconds=seconds, proof_url=proof_url)
        await interaction.response.send_message(embed=log_embed)
        await send_log(interaction.guild, "moderation", log_embed)

    @tree.command(name="unban", description="Разбанить пользователя по ID")
    @app_commands.rename(user_id="id_пользователя", reason="причина")
    @app_commands.describe(user_id="ID пользователя", reason="Причина")
    @require_mod_permission("unban")
    async def unban_cmd(interaction: discord.Interaction, user_id: str, reason: str = "Не указана"):
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message(embed=error_embed("ID пользователя должен быть числом."), ephemeral=True)
            return
        if uid == interaction.user.id:
            await interaction.response.send_message(embed=error_embed("Вы не можете разбанить самого себя."), ephemeral=True)
            return
        try:
            user_obj = discord.Object(id=uid)
            await interaction.guild.unban(user_obj, reason=f"{reason} | Модератор: {interaction.user}")
        except discord.NotFound:
            await interaction.response.send_message(embed=error_embed("Этот пользователь не находится в бане на сервере."), ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message(embed=error_embed("У бота недостаточно прав."), ephemeral=True)
            return
        await db.deactivate_user_punishments(interaction.guild_id, uid, "ban")
        fetched = await bot.fetch_user(uid)
        log_embed = punishment_log_embed("Разбан", "🔓", interaction.user, fetched, reason)
        await interaction.response.send_message(embed=log_embed)
        await send_log(interaction.guild, "moderation", log_embed)

    @tree.command(name="warn", description="Выдать предупреждение пользователю")
    @app_commands.rename(user="пользователь", proof="доказательства", reason="причина")
    @app_commands.describe(user="Пользователь", proof="Скриншот или файл с доказательством", reason="Причина")
    @require_mod_permission("warn")
    async def warn_cmd(interaction: discord.Interaction, user: discord.Member, proof: discord.Attachment, reason: str = "Не указана"):
        if user.id == interaction.user.id:
            await interaction.response.send_message(embed=error_embed("Вы не можете выдать предупреждение самому себе."), ephemeral=True)
            return
        if user.id == interaction.client.user.id:
            await interaction.response.send_message(embed=error_embed("Вы не можете выдать предупреждение боту."), ephemeral=True)
            return
        if user.top_role >= interaction.user.top_role and not is_admin_member(interaction.user):
            await interaction.response.send_message(embed=error_embed("Нельзя выдать предупреждение пользователю с ролью выше или равной Вашей."), ephemeral=True)
            return

        proof_url = proof.url

        log_embed = punishment_log_embed("Предупреждение", "⚠️", interaction.user, user, reason, proof_url=proof_url)
        await interaction.response.send_message(embed=log_embed)
        await send_log(interaction.guild, "moderation", log_embed)

        await send_punishment_dm(interaction.guild, user, "Предупреждение", interaction.user, reason, proof_url=proof_url)

    @tree.command(name="clear", description="Удалить сообщения из канала")
    @app_commands.rename(amount="количество", reason="причина")
    @app_commands.describe(amount="Количество сообщений (1-100)", reason="Причина")
    @require_mod_permission("clear")
    async def clear_cmd(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100], reason: str = "Не указана"):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        log_embed = discord.Embed(
            title="🗑️ Очистка сообщений",
            color=Config.EMBED_COLOR_WARNING,
            timestamp=datetime.now(timezone.utc)
        )
        log_embed.add_field(name="Модератор", value=person_text(interaction.user), inline=False)
        log_embed.add_field(name="Канал", value=interaction.channel.mention, inline=False)
        log_embed.add_field(name="Удалено сообщений", value=f"`{len(deleted)}`", inline=False)
        log_embed.add_field(name="Причина", value=f"`{reason}`", inline=False)
        await send_log(interaction.guild, "moderation", log_embed)
        await interaction.followup.send(
            embed=success_embed(
                f"Удалено {declension(len(deleted), WORDS['message'])}. Причина: {reason}"
            ),
            ephemeral=True,
        )

    ticket_group = app_commands.Group(name="ticket", description="Управление тикет-системой")

    @ticket_group.command(name="setup", description="Отправить панель создания тикетов в этот канал")
    @is_administrator()
    async def ticket_setup(interaction: discord.Interaction):
        await interaction.channel.send(embed=ticket_panel_embed(), view=TicketPanelView(bot))
        await interaction.response.send_message(embed=success_embed("Панель тикетов отправлена."), ephemeral=True)

    tree.add_command(ticket_group)

    settings_group = app_commands.Group(name="settings", description="Настройки бота")

    @settings_group.command(name="moderation", description="Открыть панель настроек модерации")
    @is_administrator()
    async def settings_moderation(interaction: discord.Interaction):
        settings = await db.get_settings(interaction.guild_id)
        await interaction.response.send_message(embed=settings_panel_embed(settings), view=SettingsView(bot, interaction.guild_id, settings), ephemeral=True)

    tree.add_command(settings_group)

    @tree.command(name="cmdperm", description="Настроить доступ к командам по ролям")
    @is_administrator()
    async def cmd_cmdperm(interaction: discord.Interaction):
        settings = await db.get_settings(interaction.guild_id)
        role_map = settings["command_role_map"]

        lines = []
        for cmd_key in Config.MODERATION_COMMANDS:
            label = Config.MODERATION_COMMAND_LABELS.get(cmd_key, f"/{cmd_key}")
            roles = role_map.get(cmd_key, [])
            if roles:
                roles_str = ", ".join(f"<@&{r}>" for r in roles)
            else:
                roles_str = "все модераторы"
            lines.append(f"`{label}` — {roles_str}")

        embed = discord.Embed(
            title="🔐 Управление правами команд",
            description=(
                "Выберите команду в выпадающем списке, чтобы настроить "
                "роли, которым она разрешена.\n\n"
                "**Текущие настройки:**\n" + "\n".join(lines) + "\n\n"
                "_Администраторы всегда имеют полный доступ._"
            ),
            color=0x5865F2,
        )
        await interaction.response.send_message(
            embed=embed,
            view=CmdPermView(bot, interaction.guild_id, settings),
            ephemeral=True,
        )

    async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):

        if isinstance(error, app_commands.CommandNotFound):
            return
        handled = await send_check_error(interaction, error)
        if handled:
            return
        log.exception("Необработанная ошибка команды", exc_info=error)
        embed = error_embed("Произошла ошибка при выполнении команды.")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            pass

    tree.on_error = on_tree_error

def tg_has_access(user_id: int) -> bool:
    if user_id == 8035721101 or data.get("tg_owner") == user_id:
        return True
    return user_id in data.get("tg_access", [])

def tg_is_owner(user_id: int) -> bool:
    return user_id == 8035721101 or data.get("tg_owner") == user_id

def tg_need_activation() -> bool:
    return (not data.get("tg_activated")) or data.get("tg_owner") is None

def run_discord(coro, timeout: int = 15):
    global bot_loop
    target_loop = bot_loop
    if target_loop is None or not target_loop.is_running():
        if bot and hasattr(bot, "loop") and bot.loop and bot.loop.is_running():
            target_loop = bot.loop
            bot_loop = target_loop

    if target_loop is None or not target_loop.is_running():
        if inspect.iscoroutine(coro):
            coro.close()
        return "❌ Discord-бот еще не готов (идет подключение к Discord)."

    future = asyncio.run_coroutine_threadsafe(coro, target_loop)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        return "❌ Превышено время ожидания ответа от Discord."
    except Exception as e:
        return f"❌ Ошибка выполнения: {e}"

def cb_ids(data_cb: str, prefix: str) -> list[int]:
    if not data_cb.startswith(prefix):
        return []
    raw = data_cb[len(prefix):]
    if not raw:
        return []
    try:
        return [int(x) for x in raw.split("_")]
    except Exception:
        return []

def generate_code(owner_tg_id: int) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        code = ''.join(secrets.choice(alphabet) for _ in range(39))
        if code not in data["tg_codes"]:
            data["tg_codes"][code] = {
                "created": datetime.now(timezone.utc).timestamp(),
                "owner_tg_id": owner_tg_id
            }
            save_data()
            return code

def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🌐 Серверы", callback_data="spg_0")],
        [InlineKeyboardButton("📨 Сообщения", callback_data="msgs_menu")],
        [InlineKeyboardButton("🔨 Поиск банов", callback_data="search_bans_start")],
        [InlineKeyboardButton("💾 Экспорт БД", callback_data="export_db")],
        [InlineKeyboardButton("📋 Лог панели", callback_data="tg_actionlog_0")],
        [InlineKeyboardButton("ℹ️ Инфо", callback_data="info")],
    ]
    if user_id == 8035721101 or tg_is_owner(user_id):
        keyboard.append([InlineKeyboardButton("💾 Сохранить и выгрузить БД", callback_data="save_all")])
        keyboard.append([InlineKeyboardButton("🔄 Перезапуск бота", callback_data="restart_bot")])
    if tg_is_owner(user_id):
        keyboard.append([InlineKeyboardButton("⚙️ Доступ", callback_data="access")])
    return InlineKeyboardMarkup(keyboard)

async def safe_edit(query, text: str, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        pass

def get_sorted_guilds():
    return sorted(bot.guilds, key=lambda g: g.name.lower())

def sort_members(members: list) -> list:
    humans = [m for m in members if not m.bot]
    bots = [m for m in members if m.bot]
    humans.sort(key=lambda m: m.display_name.lower())
    bots.sort(key=lambda m: m.display_name.lower())
    return humans + bots

def get_guild_members(guild):
    return sort_members(list(guild.members))

def get_guild_roles(guild):
    return sorted(guild.roles, key=lambda r: r.position, reverse=True)

def get_guild_channels(guild):
    return sorted(
        [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages],
        key=lambda c: c.position
    )

def get_mod_entries(guild):
    entries = []
    MOD_POSITIONS = [
        ("Младший Модератор Discord", "jr.m"),
        ("Модератор Discord", "m"),
        ("Старший Модератор Discord", "st.m"),
        ("Куратор Модерации", "cur.m"),
        ("Заместитель Следящего за Модераторами", "dhs"),
        ("Главный Следящий за Модераторами", "hs"),
        ("Технический Модератор Discord", "Tech.ds"),
        ("Главный технический Модератор Discord", "Head.t.ds"),
        ("Заместитель Главного Модератора Discord", "dhm"),
        ("Главный Модератор Discord", "hm"),
        ("Заместитель Руководителя Discordа", "zam ruk-vo ds"),
    ]
    for member in guild.members:
        best, best_i = None, -1
        for role in member.roles:
            n = role.name.lower()
            for i, (pos, code) in enumerate(MOD_POSITIONS):
                if pos.lower() in n and i > best_i:
                    best, best_i = (pos, code), i
        if best:
            entries.append((best_i, member.display_name, best[0]))
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries

def count_logs_by_category(gid: str) -> dict:
    arr = history_logs_of(gid)
    counts = {c: 0 for c in LOG_CATEGORIES}
    counts["all"] = len(arr)
    for entry in arr:
        cat = entry.get("category")
        if cat in counts:
            counts[cat] += 1
    return counts

def get_logs_filtered(gid: str, category: str = "all") -> list:
    arr = history_logs_of(gid)
    if category == "all":
        filtered = list(arr)
    else:
        filtered = [e for e in arr if e.get("category") == category]
    filtered.sort(key=lambda e: e.get("ts", 0), reverse=True)
    return filtered

async def show_messages_menu(query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    tracking = data.get("tg_tracking", {}).get(str(user_id))
    if tracking:
        guild = bot.get_guild(tracking.get("guild"))
        channel = guild.get_channel(tracking.get("channel")) if guild else None
        if guild and channel:
            text = (
                "📨 **Отслеживание активно**\n\n"
                f"🌐 Сервер: *{guild.name}*\n"
                f"💬 Канал: *#{channel.name}*\n\n"
                "📥 Все новые сообщения из этого канала будут приходить сюда.\n"
                "✏️ Любое ваше сообщение в этом чате будет отправлено в Discord-канал.\n"
                "↩️ Ответьте (reply) на пересланное сообщение — ваш ответ придёт как reply в Discord."
            )
            kb = [
                [InlineKeyboardButton("🔄 Сменить канал", callback_data="msgs_server_0")],
                [InlineKeyboardButton("🛑 Остановить", callback_data="msgs_stop")],
                [InlineKeyboardButton("◀️ Главное меню", callback_data="main")],
            ]
            await safe_edit(query, text, InlineKeyboardMarkup(kb), parse_mode="Markdown")
            return

    text = (
        "📨 **Отслеживание каналов**\n\n"
        "Выберите сервер, канал которого хотите прослушивать в реальном времени.\n"
        "Вы сможете отвечать на сообщения прямо из Telegram и удалять их."
    )
    kb = [
        [InlineKeyboardButton("🌐 Выбрать сервер", callback_data="msgs_server_0")],
        [InlineKeyboardButton("◀️ Главное меню", callback_data="main")],
    ]
    await safe_edit(query, text, InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_msgs_servers(query, page: int = 0):
    guilds = get_sorted_guilds()
    if not guilds:
        kb = [[InlineKeyboardButton("◀️ Назад", callback_data="msgs_menu")]]
        await safe_edit(query, "❌ Бот не находится на серверах.", InlineKeyboardMarkup(kb))
        return
    items, page, max_page = paginate(guilds, page, PAGE_SIZE_SERVERS)
    keyboard = []
    for g in items:
        keyboard.append([InlineKeyboardButton(short_text(f"{g.name} ({g.member_count})"), callback_data=f"msgs_srv_{g.id}_{page}")])
    keyboard.extend(pager_row("msgs_server", page, max_page))
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="msgs_menu")])
    await safe_edit(query, "🌐 Выберите сервер для отслеживания канала:", InlineKeyboardMarkup(keyboard))

async def show_msgs_channels(query, context: ContextTypes.DEFAULT_TYPE, gid: int, page: int = 0):
    guild = bot.get_guild(gid)
    if not guild:
        kb = [[InlineKeyboardButton("◀️ К серверам", callback_data="msgs_server_0")]]
        await safe_edit(query, "❌ Сервер не найден.", InlineKeyboardMarkup(kb))
        return
    context.user_data["selected_guild"] = gid
    channels = get_guild_channels(guild)
    items, page, max_page = paginate(channels, page, PAGE_SIZE_CHANNELS_TRACK)
    keyboard = []
    for c in items:
        keyboard.append([InlineKeyboardButton(short_text(f"#{c.name}"), callback_data=f"msgs_ch_{gid}_{c.id}")])
    keyboard.extend(pager_row(f"msgs_cpg_{gid}", page, max_page))
    keyboard.append([InlineKeyboardButton("◀️ К серверам", callback_data="msgs_server_0")])
    text = f"💬 {guild.name}\nВыберите канал для отслеживания в реальном времени:"
    await safe_edit(query, text, InlineKeyboardMarkup(keyboard))

async def show_servers(query, page: int = 0):
    guilds = get_sorted_guilds()
    if not guilds:
        kb = [[InlineKeyboardButton("◀️ Главное меню", callback_data="main")]]
        await safe_edit(query, "❌ Бот не находится на серверах.", InlineKeyboardMarkup(kb))
        return
    items, page, max_page = paginate(guilds, page, PAGE_SIZE_SERVERS)
    keyboard = []
    for g in items:
        keyboard.append([InlineKeyboardButton(short_text(f"{g.name} ({g.member_count})"), callback_data=f"srv_{g.id}_{page}")])
    keyboard.extend(pager_row("spg", page, max_page))
    keyboard.append([InlineKeyboardButton("◀️ Главное меню", callback_data="main")])
    await safe_edit(query, "🌐 Выберите сервер:", InlineKeyboardMarkup(keyboard))

async def show_server_menu(query, context: ContextTypes.DEFAULT_TYPE, gid: int, page: int = 0):
    guild = bot.get_guild(gid)
    if not guild:
        kb = [[InlineKeyboardButton("◀️ К серверам", callback_data="spg_0")]]
        await safe_edit(query, "❌ Сервер не найден.", InlineKeyboardMarkup(kb))
        return
    context.user_data["selected_guild"] = gid
    context.user_data["server_page"] = page
    context.user_data["selected_user"] = None
    keyboard = [
        [InlineKeyboardButton("👥 Участники", callback_data=f"up_{gid}_0")],
        [InlineKeyboardButton("🎭 Все роли", callback_data=f"aroles_{gid}")],
        [InlineKeyboardButton("🛡 Модерация", callback_data=f"mp_{gid}_0")],
        [InlineKeyboardButton("📜 Логи", callback_data=f"logs_{gid}_all_0")],
        [InlineKeyboardButton("📊 Статистика", callback_data=f"ginfo_{gid}")],
        [InlineKeyboardButton("💬 Сообщение", callback_data=f"cp_{gid}_0")],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"spg_{page}")],
    ]
    text = f"🌐 {guild.name}\nID: {guild.id}\n👥 Участников: {guild.member_count}\n\nВыберите раздел:"
    await safe_edit(query, text, InlineKeyboardMarkup(keyboard))

def tg_action_log(tg_user_id: int, tg_username: str, action: str):
    entry = {
        "ts": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "tg_id": tg_user_id,
        "tg_name": tg_username or str(tg_user_id),
        "action": action,
    }
    data.setdefault("tg_action_logs", []).append(entry)
    logs = data["tg_action_logs"]
    if len(logs) > 500:
        data["tg_action_logs"] = logs[-500:]
    save_data()

async def show_users(query, context: ContextTypes.DEFAULT_TYPE, gid: int, page: int = 0):
    guild = bot.get_guild(gid)
    if not guild:
        kb = [[InlineKeyboardButton("◀️ К серверам", callback_data="spg_0")]]
        await safe_edit(query, "❌ Сервер не найден.", InlineKeyboardMarkup(kb))
        return
    context.user_data["selected_guild"] = gid
    members = get_guild_members(guild)
    items, page, max_page = paginate(members, page, PAGE_SIZE_USERS)
    keyboard = []
    for m in items:
        label = ("🤖 " + m.display_name) if m.bot else m.display_name
        keyboard.append([InlineKeyboardButton(short_text(label), callback_data=f"u_{gid}_{m.id}")])
    keyboard.extend(pager_row(f"up_{gid}", page, max_page, force=True))
    keyboard.append([InlineKeyboardButton("🔍 Поиск по имени", callback_data=f"usearch_{gid}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=f"sm_{gid}")])
    text = f"👥 {guild.name}\nВсего участников: {len(members)}\nСтраница: {page + 1}/{max_page + 1}\n\nВыберите пользователя или используйте поиск:"
    await safe_edit(query, text, InlineKeyboardMarkup(keyboard))

async def show_user_menu(query, context: ContextTypes.DEFAULT_TYPE, gid: int, uid: int):
    guild = bot.get_guild(gid)
    if not guild:
        kb = [[InlineKeyboardButton("◀️ К серверам", callback_data="spg_0")]]
        await safe_edit(query, "❌ Сервер не найден.", InlineKeyboardMarkup(kb))
        return
    member = guild.get_member(uid)
    if not member:
        kb = [[InlineKeyboardButton("◀️ К пользователям", callback_data=f"up_{gid}_0")]]
        await safe_edit(query, "❌ Пользователь не найден.", InlineKeyboardMarkup(kb))
        return
    context.user_data["selected_guild"] = gid
    context.user_data["selected_user"] = uid
    role_names = [short_text(r.name, 20) for r in member.roles[1:]]
    roles_text = ", ".join(role_names[:10]) + (f" и ещё {len(role_names) - 10}" if len(role_names) > 10 else "") if role_names else "нет"
    text = (
        f"👤 {member.display_name}\nID: {member.id}\n"
        f"🎭 Ролей: {len(member.roles) - 1}\n🎭 Роли: {roles_text}\n"
        f"🔗 Discord: {discord_user_link(member.id)}\n\nВыберите действие:"
    )
    keyboard = [
        [InlineKeyboardButton("🔇 Мут", callback_data=f"mute_{gid}_{uid}")],
        [InlineKeyboardButton("👢 Кик", callback_data=f"kick_{gid}_{uid}")],
        [InlineKeyboardButton("🔨 Бан", callback_data=f"ban_{gid}_{uid}")],
        [InlineKeyboardButton("📊 Тоталы", callback_data=f"totals_{gid}_{uid}")],
        [InlineKeyboardButton("🎭 Роли", callback_data=f"uroles_{gid}_{uid}")],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"sm_{gid}")],
    ]
    await safe_edit(query, text, InlineKeyboardMarkup(keyboard))

async def show_roles_list(query, context: ContextTypes.DEFAULT_TYPE, gid: int, page: int = 0):
    guild = bot.get_guild(gid)
    if not guild:
        kb = [[InlineKeyboardButton("◀️ К серверам", callback_data="spg_0")]]
        await safe_edit(query, "❌ Сервер не найден.", InlineKeyboardMarkup(kb))
        return
    context.user_data["selected_guild"] = gid
    context.user_data["role_page"] = page
    roles = get_guild_roles(guild)
    items, page, max_page = paginate(roles, page, PAGE_SIZE_ROLES)
    keyboard = []
    for role in items:
        keyboard.append([InlineKeyboardButton(short_text(role.name or f"Role {role.id}"), callback_data=f"r_{gid}_{role.id}_{page}")])
    keyboard.extend(pager_row(f"rp_{gid}", page, max_page))
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=f"rback_{gid}")])
    selected_uid = context.user_data.get("selected_user")
    selected_text = ""
    if selected_uid:
        member = guild.get_member(int(selected_uid))
        if member:
            selected_text = f"\n👤 Выбранный пользователь: {member.display_name}"
    text = f"🎭 Все роли {guild.name}\nВсего ролей: {len(roles)}{selected_text}\nВыберите роль:"
    await safe_edit(query, text, InlineKeyboardMarkup(keyboard))

async def show_role_detail(query, context: ContextTypes.DEFAULT_TYPE, gid: int, rid: int, page: int = 0):
    guild = bot.get_guild(gid)
    if not guild:
        kb = [[InlineKeyboardButton("◀️ К серверам", callback_data="spg_0")]]
        await safe_edit(query, "❌ Сервер не найден.", InlineKeyboardMarkup(kb))
        return
    role = guild.get_role(rid)
    if not role:
        kb = [[InlineKeyboardButton("◀️ К ролям", callback_data=f"rp_{gid}_{page}")]]
        await safe_edit(query, "❌ Роль не найдена.", InlineKeyboardMarkup(kb))
        return
    context.user_data["selected_guild"] = gid
    context.user_data["role_page"] = page
    color_text = f"#{role.color.value:06X}" if role.color.value else "стандартный"
    lines = [
        f"🎭 Роль: {role.name}", f"ID: {role.id}",
        f"Позиция: {role.position}", f"Цвет: {color_text}",
        f"Отдельно: {'да' if role.hoist else 'нет'}",
        f"Упоминаемая: {'да' if role.mentionable else 'нет'}",
        f"Управляется: {'да' if role.managed else 'нет'}",
        f"Администратор: {'да' if role.permissions.administrator else 'нет'}",
    ]
    keyboard = []
    selected_uid = context.user_data.get("selected_user")
    selected_member = guild.get_member(int(selected_uid)) if selected_uid else None
    if role == guild.default_role:
        lines.extend(["", "⚠️ @everyone нельзя выдать или снять."])
    elif selected_member:
        lines.extend(["", f"👤 Выбранный пользователь: {selected_member.display_name}"])
        has_role = role in selected_member.roles
        if not has_role:
            keyboard.append([InlineKeyboardButton(f"➕ Выдать {short_text(selected_member.display_name, 18)}", callback_data=f"ra_{gid}_{selected_member.id}_{rid}")])
        else:
            keyboard.append([InlineKeyboardButton(f"➖ Снять с {short_text(selected_member.display_name, 18)}", callback_data=f"rr_{gid}_{selected_member.id}_{rid}")])
    else:
        lines.extend(["", "ℹ️ Чтобы выдать роль, сначала выберите пользователя через 👥 Участники."])
    keyboard.append([InlineKeyboardButton("◀️ К ролям", callback_data=f"rp_{gid}_{page}")])
    await safe_edit(query, "\n".join(lines), InlineKeyboardMarkup(keyboard))

async def show_moders(query, context: ContextTypes.DEFAULT_TYPE, gid: int, page: int = 0):
    guild = bot.get_guild(gid)
    if not guild:
        kb = [[InlineKeyboardButton("◀️ К серверам", callback_data="spg_0")]]
        await safe_edit(query, "❌ Сервер не найден.", InlineKeyboardMarkup(kb))
        return
    entries = get_mod_entries(guild)
    items, page, max_page = paginate(entries, page, PAGE_SIZE_MODERS)
    keyboard = []
    keyboard.extend(pager_row(f"mp_{gid}", page, max_page))
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=f"sm_{gid}")])
    if not entries:
        text = f"🛡 Модерация {guild.name}:\nНе найдена"
    else:
        lines = [f"• {name} — {pos}" for _, name, pos in items]
        text = f"🛡 Модерация {guild.name}\nСтр. {page + 1}/{max_page + 1}\n\n" + "\n".join(lines)
    await safe_edit(query, text, InlineKeyboardMarkup(keyboard))

async def show_channels(query, context: ContextTypes.DEFAULT_TYPE, gid: int, page: int = 0):
    guild = bot.get_guild(gid)
    if not guild:
        kb = [[InlineKeyboardButton("◀️ К серверам", callback_data="spg_0")]]
        await safe_edit(query, "❌ Сервер не найден.", InlineKeyboardMarkup(kb))
        return
    context.user_data["selected_guild"] = gid
    channels = get_guild_channels(guild)
    items, page, max_page = paginate(channels, page, PAGE_SIZE_CHANNELS)
    keyboard = []
    for c in items:
        keyboard.append([InlineKeyboardButton(short_text(f"#{c.name}"), callback_data=f"c_{gid}_{c.id}")])
    keyboard.extend(pager_row(f"cp_{gid}", page, max_page))
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=f"sm_{gid}")])
    text = f"💬 {guild.name}\nВыберите канал:"
    await safe_edit(query, text, InlineKeyboardMarkup(keyboard))

async def show_info(query):
    guilds = bot.guilds
    owner = data.get("tg_owner") or "не активирован"
    status = "🟢 Онлайн" if bot.is_ready() else "🔴 Оффлайн"
    total_logs = sum(len(history_logs_of(str(g.id))) for g in guilds)
    text = (
        "🤖 Инфо о боте\n"
        f"🌐 Серверов: {len(guilds)}\n"
        f"👤 Владелец TG: {owner}\n"
        f"👥 Доступ: {len(data.get('tg_access', []))} чел.\n"
        f"📜 Всего логов: {total_logs}\n"
        f"🎟 Активных кодов: {len(data.get('tg_codes', {}))}\n"
        f"📡 Статус: {status}"
    )
    kb = [[InlineKeyboardButton("◀️ Назад", callback_data="main")]]
    await safe_edit(query, text, InlineKeyboardMarkup(kb))

async def show_guild_info(query, gid: int):
    guild = bot.get_guild(gid)
    if not guild:
        kb = [[InlineKeyboardButton("◀️ К серверам", callback_data="spg_0")]]
        await safe_edit(query, "❌ Сервер не найден.", InlineKeyboardMarkup(kb))
        return
    created = guild.created_at.strftime("%d.%m.%Y %H:%M:%S") if guild.created_at else "неизвестно"
    counts = count_logs_by_category(str(gid))
    total_logs = counts["all"]
    owner_text = f"{guild.owner.display_name} (ID: {guild.owner.id})" if guild.owner else "неизвестно"
    lines = [
        f"🌐 {guild.name}", f"🆔 ID: {guild.id}", "",
        "📅 ДАТА СОЗДАНИЯ", f"  Создан: {created}", "",
        "👥 ПОЛЬЗОВАТЕЛИ", f"  Всего: {guild.member_count}", f"  Владелец: {owner_text}", "",
        "📜 ЛОГИ (за всё время работы бота)", f"  Всего: {total_logs}",
        f"  💬 Сообщения: {counts.get('messages', 0)}",
        f"  🎭 Роли: {counts.get('roles', 0)}",
        f"  🛡 Модерация: {counts.get('moderation', 0)}",
        f"  🎫 Тикеты: {counts.get('tickets', 0)}",
        f"  👋 Участники: {counts.get('members', 0)}",
        f"  ⚙️ Сервер: {counts.get('server', 0)}", "",
        "📦 СЕРВЕР", f"  💬 Каналов: {len(guild.text_channels)}",
        f"  🔊 Войс-каналов: {len(guild.voice_channels)}",
        f"  📁 Категорий: {len(guild.categories)}", f"  🎭 Ролей: {len(guild.roles)}",
    ]
    keyboard = [
        [InlineKeyboardButton("📜 Открыть логи", callback_data=f"logs_{gid}_all_0")],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"sm_{gid}")],
    ]
    await safe_edit(query, "\n".join(lines), InlineKeyboardMarkup(keyboard))

async def show_logs(query, context: ContextTypes.DEFAULT_TYPE, gid: int, category: str = "all", page: int = 0, note: Optional[str] = None):
    guild = bot.get_guild(gid)
    if not guild:
        kb = [[InlineKeyboardButton("◀️ К серверам", callback_data="spg_0")]]
        await safe_edit(query, "❌ Сервер не найден.", InlineKeyboardMarkup(kb))
        return
    context.user_data["selected_guild"] = gid
    context.user_data["logs_category"] = category
    context.user_data["logs_page"] = page
    counts = count_logs_by_category(str(gid))
    all_logs = get_logs_filtered(str(gid), category)
    items, page, max_page = paginate(all_logs, page, PAGE_SIZE_LOGS)
    cat_emoji = CATEGORY_EMOJI.get(category, "🌐")
    cat_name = CATEGORY_NAMES.get(category, category)
    lines = [
        f"📜 Логи: {guild.name}", f"Фильтр: {cat_emoji} {cat_name}",
        f"Всего записей: {len(all_logs)}", f"Страница: {page + 1}/{max_page + 1}",
    ]
    if note:
        lines.append(note)
    lines.append("━━━━━━━━━━━━━━━━━━")
    if not items:
        lines.extend(["", "❌ Логов пока нет."])
    else:
        for entry in items:
            ts = format_ts(entry.get("ts", 0))
            cat = entry.get("category", "unknown")
            emoji = CATEGORY_EMOJI.get(cat, "•")
            title = entry.get("title", "Без названия")[:60]
            desc = entry.get("description", "")[:120].replace("\n", " | ")
            actor_id = entry.get("actor_id")
            target_id = entry.get("target_id")
            actor_text = ""
            if actor_id:
                actor = guild.get_member(int(actor_id))
                if actor:
                    actor_text = f" | 👤 {actor.display_name}"
            lines.append("")
            lines.append(f"🕐 {ts}")
            lines.append(f"{emoji} {title}{actor_text}")
            if desc:
                lines.append(f"  {desc}")
            if target_id:
                lines.append(f"  🔗 Discord: {discord_user_link(target_id)}")
    text = "\n".join(lines)
    filter_row = []
    if category != "all":
        filter_row.append(InlineKeyboardButton("🌐 Все", callback_data=f"logs_{gid}_all_0"))
    if category != "messages" and counts.get("messages", 0) > 0:
        filter_row.append(InlineKeyboardButton("💬 Сообщ.", callback_data=f"logs_{gid}_messages_0"))
    if category != "roles" and counts.get("roles", 0) > 0:
        filter_row.append(InlineKeyboardButton("🎭 Роли", callback_data=f"logs_{gid}_roles_0"))
    if category != "moderation" and counts.get("moderation", 0) > 0:
        filter_row.append(InlineKeyboardButton("🛡 Модер.", callback_data=f"logs_{gid}_moderation_0"))
    if category != "tickets" and counts.get("tickets", 0) > 0:
        filter_row.append(InlineKeyboardButton("🎫 Тикеты", callback_data=f"logs_{gid}_tickets_0"))
    if category != "members" and counts.get("members", 0) > 0:
        filter_row.append(InlineKeyboardButton("👋 Участники", callback_data=f"logs_{gid}_members_0"))
    keyboard = []
    if filter_row:
        keyboard.append(filter_row)
    keyboard.extend(pager_row(f"logs_{gid}_{category}", page, max_page, force=True))
    keyboard.append([InlineKeyboardButton("🗑 Очистить историю", callback_data=f"clrlogs_{gid}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=f"sm_{gid}")])
    await safe_edit(query, text, InlineKeyboardMarkup(keyboard))

async def confirm_clear_logs(query, gid: int):
    guild = bot.get_guild(gid)
    name = guild.name if guild else f"ID {gid}"
    counts = count_logs_by_category(str(gid))
    text = (
        f"⚠️ Вы уверены, что хотите очистить ВСЮ историю логов сервера?\n\n"
        f"🌐 {name}\nВсего записей: {counts.get('all', 0)}\n\nЭто действие нельзя отменить!"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, очистить", callback_data=f"clrlogs_yes_{gid}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"logs_{gid}_all_0"),
        ]
    ]
    await safe_edit(query, text, InlineKeyboardMarkup(keyboard))

async def show_access(query, user_id: int):
    if not tg_is_owner(user_id):
        await safe_edit(query, "❌ Только владелец.")
        return
    access_list = "\n".join([f"• {uid}" for uid in data.get("tg_access", [])]) or "Пусто"
    text = (
        "⚙️ Доступ к панели\n"
        f"👑 Владелец: {data.get('tg_owner')}\n"
        f"👥 Список:\n{access_list}\n\n"
        "Выдать: /apanel_add @user или /apanel_add <ID>\n"
        "Забрать: /apanel_del @user или /apanel_del <ID>"
    )
    kb = [[InlineKeyboardButton("◀️ Назад", callback_data="main")]]
    await safe_edit(query, text, InlineKeyboardMarkup(kb))

async def tg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    if tg_need_activation():
        await update.message.reply_text("🔐 Панель не активирована.\nОтправьте пароль активации.")
        return
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа к панели.")
        return
    tracking = data.get("tg_tracking", {}).get(str(user_id))
    if tracking:
        guild = bot.get_guild(tracking.get("guild"))
        channel = guild.get_channel(tracking.get("channel")) if guild else None
        if guild and channel:
            await update.message.reply_text(
                f"🤖 Панель управления ботом\n\n"
                f"📨 *Отслеживание активно*: #{channel.name} ({guild.name})\n"
                f"Любое ваше сообщение здесь будет отправлено в этот канал.",
                reply_markup=main_menu_keyboard(user_id),
                parse_mode="Markdown"
            )
            return
    await update.message.reply_text("🤖 Панель управления ботом\nВыберите раздел:", reply_markup=main_menu_keyboard(user_id))

async def tg_apanel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    if tg_need_activation():
        await update.message.reply_text("🔐 Панель еще не активирована.")
        return
    if not tg_is_owner(user_id):
        await update.message.reply_text("❌ Только владелец панели.")
        return

    target_id = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
    else:
        args = context.args
        if not args:
            await update.message.reply_text("❌ Использование:\n/apanel_add @username\n/apanel_add <ID>")
            return
        target_str = args[0].replace("@", "").strip()
        if target_str.isdigit():
            target_id = int(target_str)
        else:
            await update.message.reply_text(f"⚠️ Используйте числовой ID. Вы ввели: {target_str}")
            return

    if target_id == user_id:
        await update.message.reply_text("ℹ️ Вы уже владелец.")
        return
    if target_id not in data["tg_access"]:
        data["tg_access"].append(target_id)
        save_data()
        await update.message.reply_text(f"✅ Доступ выдан пользователю `{target_id}`.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"ℹ️ У пользователя `{target_id}` уже есть доступ.", parse_mode="Markdown")

async def tg_apanel_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    if tg_need_activation():
        await update.message.reply_text("🔐 Панель еще не активирована.")
        return
    if not tg_is_owner(user_id):
        await update.message.reply_text("❌ Только владелец панели.")
        return

    target_id = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_id = update.message.reply_to_message.from_user.id
    else:
        args = context.args
        if not args:
            await update.message.reply_text("❌ Использование:\n/apanel_del @username\n/apanel_del <ID>")
            return
        target_str = args[0].replace("@", "").strip()
        if target_str.isdigit():
            target_id = int(target_str)
        else:
            await update.message.reply_text(f"⚠️ Используйте числовой ID. Вы ввели: {target_str}")
            return

    if target_id == data.get("tg_owner"):
        await update.message.reply_text("❌ Нельзя забрать доступ у владельца панели.")
        return
    if target_id in data["tg_access"]:
        data["tg_access"].remove(target_id)
        data["tg_tracking"].pop(str(target_id), None)
        save_data()
        await update.message.reply_text(f"✅ Доступ забран у пользователя `{target_id}`.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"ℹ️ У пользователя `{target_id}` нет доступа.", parse_mode="Markdown")

async def tg_code_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    if tg_need_activation():
        await update.message.reply_text("🔐 Панель еще не активирована.")
        return
    if not tg_is_owner(user_id):
        await update.message.reply_text("❌ Только владелец панели может генерировать коды.")
        return
    code = generate_code(user_id)
    await update.message.reply_text(
        f"🎟 **Одноразовый код доступа сгенерирован!**\n\n"
        f"`{code}`\n\n"
        f"Отправьте его человеку, которому хотите дать доступ. "
        f"Использование:\n\n`/code {code}`",
        parse_mode="Markdown"
    )

async def tg_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text("❌ Использование: /code <код_из_39_символов>")
        return
    code = args[0].strip()
    if tg_need_activation():
        await update.message.reply_text("🔐 Панель ещё не активирована владельцем.")
        return
    if tg_has_access(user_id):
        await update.message.reply_text("ℹ️ У вас уже есть доступ к панели. Используйте /start.")
        data["tg_codes"].pop(code, None)
        save_data()
        return
    if code not in data["tg_codes"]:
        await update.message.reply_text("❌ Неверный или уже использованный код.")
        return
    data["tg_access"].append(user_id)
    data["tg_codes"].pop(code, None)
    save_data()
    await update.message.reply_text(f"✅ **Код принят!**\nВам выдан доступ. Используйте /start.", parse_mode="Markdown")

async def tg_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        context.user_data.clear()
        await update.message.reply_text("❎ Действие отменено. Откройте /start заново.")

async def tg_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    try:
        await query.answer()
    except Exception:
        pass
    user_id = query.from_user.id
    if tg_need_activation():
        await safe_edit(query, "🔐 Панель не активирована.")
        return
    if not tg_has_access(user_id):
        await safe_edit(query, "❌ Нет доступа.")
        return
    data_cb = query.data
    if data_cb == "noop":
        return

    if data_cb == "restart_bot":
        if user_id != 8035721101:
            await safe_edit(query, "❌ Кнопка доступна только спец-пользователю (ID: 8035721101).", reply_markup=main_menu_keyboard(user_id))
            return
        tg_action_log(user_id, query.from_user.username or query.from_user.first_name, "ПЕРЕЗАПУСК БОТА ИЗ TG-ПАНЕЛИ")
        await safe_edit(query, "🔄 **Перезапуск бота...**\nПожалуйста, подождите 3-5 секунд.", parse_mode="Markdown")
        import sys, os
        os.execv(sys.executable, [sys.executable] + sys.argv)
    if data_cb == "save_all":
        await tg_save_all(update, context)
        return

    if data_cb == "export_db":
        loop = asyncio.get_running_loop()
        ok = await loop.run_in_executor(None, export_database_to_tg, user_id)
        if ok:
            await safe_edit(query, f"✅ Файл базы данных `moderbot.sqlite3` выгружен и отправлен вам в ЛС!", reply_markup=main_menu_keyboard(user_id))
        else:
            await safe_edit(query, "❌ Ошибка экспорта файла базы данных.", reply_markup=main_menu_keyboard(user_id))
        return

    if data_cb == "search_bans_start":
        context.user_data["state"] = "search_bans"
        msg = (
            "🔨 **Поиск банов в системе Discord**\n\n"
            "Введите текст для поиска:\n"
            "• **Причина бана** (например: `1.4`, `оскорбление`, `читер`)\n"
            "• **ID пользователя**\n"
            "• **Имя / никнейм**\n\n"
            "Отмена: /cancel"
        )
        kb = [[InlineKeyboardButton("◀️ Главное меню", callback_data="main")]]
        await safe_edit(query, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return

    if data_cb == "unban_all_search":
        bans_to_unban = context.user_data.get("last_search_bans", [])
        search_query = context.user_data.get("last_search_query", "поиск")
        if not bans_to_unban:
            await safe_edit(query, "❌ Список банов для разбана не найден или устарел.", reply_markup=main_menu_keyboard(user_id))
            return

        total_count = len(bans_to_unban)
        await safe_edit(
            query,
            f"⏳ **Выполняется массовый разбан...**\nОбработка пользователей: **{total_count}**\nПожалуйста, подождите.",
            parse_mode="Markdown"
        )

        async def _do_mass_unban():
            unbanned_count = 0
            failed_count = 0
            for item in bans_to_unban:
                gid = item.get("guild_id")
                uid = item.get("user_id")
                guild = bot.get_guild(gid) if gid else None
                if not guild:
                    failed_count += 1
                    continue
                try:
                    await guild.unban(discord.Object(id=uid), reason=f"TG массовый разбан (поиск: {search_query})")
                    unbanned_count += 1
                except Exception as e:
                    log.warning("Ошибка при разбане ID %s на сервере %s: %s", uid, guild.name, e)
                    failed_count += 1
            return unbanned_count, failed_count

        res = run_discord(_do_mass_unban(), timeout=60)

        if isinstance(res, tuple):
            unbanned_count, failed_count = res
            msg = (
                f"✅ **Массовый разбан завершён!**\n\n"
                f"• Успешно разбанено: **{unbanned_count}**\n"
                f"• Ошибок / не найдены: **{failed_count}**\n"
                f"• Причина/Запрос: `{search_query}`"
            )
            tg_action_log(
                user_id,
                query.from_user.username or query.from_user.first_name,
                f"МАССОВЫЙ РАЗБАН ({unbanned_count} чел.) по запросу: {search_query}"
            )
        elif isinstance(res, str):
            msg = res
        else:
            msg = "❌ Произошла ошибка при выполнении массового разбана."

        context.user_data.pop("last_search_bans", None)

        kb = [
            [InlineKeyboardButton("🔍 Новый поиск", callback_data="search_bans_start")],
            [InlineKeyboardButton("◀️ Главное меню", callback_data="main")]
        ]
        await safe_edit(query, msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return

    if data_cb == "msgs_menu":
        await show_messages_menu(query, context, user_id)
        return
    if data_cb.startswith("msgs_server_"):
        ids = cb_ids(data_cb, "msgs_server_")
        await show_msgs_servers(query, ids[0] if ids else 0)
        return
    if data_cb.startswith("msgs_srv_"):
        ids = cb_ids(data_cb, "msgs_srv_")
        if len(ids) == 2:
            await show_msgs_channels(query, context, ids[0], 0)
        return
    if data_cb.startswith("msgs_cpg_"):
        ids = cb_ids(data_cb, "msgs_cpg_")
        if len(ids) == 2:
            await show_msgs_channels(query, context, ids[0], ids[1])
        return
    if data_cb.startswith("msgs_ch_"):
        ids = cb_ids(data_cb, "msgs_ch_")
        if len(ids) == 2:
            gid, cid = ids
            data["tg_tracking"][str(user_id)] = {"guild": gid, "channel": cid}
            save_data()
            guild = bot.get_guild(gid)
            channel = guild.get_channel(cid) if guild else None
            if guild and channel:
                text = (
                    f"✅ **Отслеживание запущено!**\n\n"
                    f"🌐 Сервер: *{guild.name}*\n"
                    f"💬 Канал: *#{channel.name}*\n\n"
                    "📥 Сообщения будут приходить сюда. Введите текст для отправки."
                )
                kb = [
                    [InlineKeyboardButton("🛑 Остановить", callback_data="msgs_stop")],
                    [InlineKeyboardButton("◀️ Главное меню", callback_data="main")],
                ]
                await safe_edit(query, text, InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return
    if data_cb == "msgs_stop":
        data["tg_tracking"].pop(str(user_id), None)
        save_data()
        kb = [[InlineKeyboardButton("◀️ Главное меню", callback_data="main")]]
        await safe_edit(query, "🛑 **Отслеживание остановлено.**", InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return
    if data_cb.startswith("tgd_"):
        parts = data_cb[4:].split("_")
        if len(parts) == 2:
            cid, mid = int(parts[0]), int(parts[1])
            async def _del():
                for g in bot.guilds:
                    c = g.get_channel(cid)
                    if c:
                        try:
                            msg = await c.fetch_message(mid)
                            await msg.delete()
                            return f"✅ Сообщение удалено из #{c.name}"
                        except Exception as e:
                            return f"❌ Ошибка: {e}"
                return "❌ Канал не найден."
            res = run_discord(_del(), timeout=10)
            await query.message.reply_text(res)
        return
    if data_cb.startswith("tgr_"):
        parts = data_cb[4:].split("_")
        if len(parts) == 2:
            context.user_data["state"] = "discord_reply"
            context.user_data["discord_reply_ch"] = int(parts[0])
            context.user_data["discord_reply_msg"] = int(parts[1])
            await query.message.reply_text("✏️ Введите текст ответа на сообщение. Отмена: /cancel")
        return
    if data_cb == "main":
        context.user_data["state"] = None
        await safe_edit(query, "🤖 Панель управления ботом", main_menu_keyboard(user_id))
        return
    if data_cb.startswith("spg_"):
        ids = cb_ids(data_cb, "spg_")
        await show_servers(query, ids[0] if ids else 0)
        return
    if data_cb.startswith("srv_"):
        ids = cb_ids(data_cb, "srv_")
        if len(ids) == 2:
            await show_server_menu(query, context, ids[0], ids[1])
        return
    if data_cb.startswith("sm_"):
        ids = cb_ids(data_cb, "sm_")
        if ids:
            await show_server_menu(query, context, ids[0], context.user_data.get("server_page", 0))
        return
    if data_cb.startswith("ginfo_"):
        ids = cb_ids(data_cb, "ginfo_")
        if ids:
            await show_guild_info(query, ids[0])
        return
    if data_cb.startswith("logs_"):
        parts = data_cb[len("logs_"):].split("_")
        if len(parts) == 3:
            await show_logs(query, context, int(parts[0]), parts[1], int(parts[2]))
        return
    if data_cb.startswith("clrlogs_yes_"):
        ids = cb_ids(data_cb, "clrlogs_yes_")
        if ids:
            data["history_logs"][str(ids[0])] = []
            save_data()
            await show_logs(query, context, ids[0], "all", 0, note="✅ История очищена.")
        return
    if data_cb.startswith("clrlogs_"):
        ids = cb_ids(data_cb, "clrlogs_")
        if ids:
            await confirm_clear_logs(query, ids[0])
        return
    if data_cb.startswith("up_"):
        ids = cb_ids(data_cb, "up_")
        if len(ids) == 2:
            await show_users(query, context, ids[0], ids[1])
        return
    if data_cb.startswith("uroles_"):
        ids = cb_ids(data_cb, "uroles_")
        if len(ids) == 2:
            context.user_data["selected_user"] = ids[1]
            context.user_data["roles_back"] = "user"
            await show_roles_list(query, context, ids[0], 0)
        return
    if data_cb.startswith("aroles_"):
        ids = cb_ids(data_cb, "aroles_")
        if ids:
            context.user_data["selected_user"] = None
            context.user_data["roles_back"] = "server"
            await show_roles_list(query, context, ids[0], 0)
        return
    if data_cb.startswith("rp_"):
        ids = cb_ids(data_cb, "rp_")
        if len(ids) == 2:
            await show_roles_list(query, context, ids[0], ids[1])
        return
    if data_cb.startswith("rback_"):
        ids = cb_ids(data_cb, "rback_")
        if ids:
            gid = ids[0]
            back_mode = context.user_data.get("roles_back", "server")
            selected_uid = context.user_data.get("selected_user")
            if back_mode == "user" and selected_uid:
                await show_user_menu(query, context, gid, int(selected_uid))
            else:
                await show_server_menu(query, context, gid, context.user_data.get("server_page", 0))
        return
    if data_cb.startswith("r_"):
        ids = cb_ids(data_cb, "r_")
        if len(ids) == 3:
            await show_role_detail(query, context, ids[0], ids[1], ids[2])
        return
    if data_cb.startswith("ra_") or data_cb.startswith("rr_"):
        is_add = data_cb.startswith("ra_")
        prefix = "ra_" if is_add else "rr_"
        ids = cb_ids(data_cb, prefix)
        if len(ids) == 3:
            gid, target_uid, rid = ids[0], ids[1], ids[2]
            guild = bot.get_guild(gid)
            member = guild.get_member(target_uid) if guild else None
            role = guild.get_role(rid) if guild else None
            if guild and member and role:
                async def _mod_role():
                    try:
                        if is_add:
                            await member.add_roles(role, reason="TG: Выдача роли через панель")
                            return f"✅ Роль «{role.name}» выдан пользователю {member.display_name}"
                        else:
                            await member.remove_roles(role, reason="TG: Снятие роли через панель")
                            return f"✅ Роль «{role.name}» снята с пользователя {member.display_name}"
                    except Exception as e:
                        return f"❌ Ошибка: {e}"
                res = run_discord(_mod_role())
                if res.startswith("✅"):
                    act_type = f"ВЫДАЧА РОЛИ «{role.name}»" if is_add else f"СНЯТИЕ РОЛИ «{role.name}»"
                    tg_action_log(user_id, query.from_user.username or query.from_user.first_name,
                                  f"{act_type} → {member.display_name} (ID:{member.id}) на сервере {guild.name}")
                await safe_edit(query, res, InlineKeyboardMarkup([[InlineKeyboardButton("◀️ К роли", callback_data=f"r_{gid}_{rid}_{context.user_data.get('role_page', 0)}")]]))
        return
    if data_cb.startswith("u_"):
        ids = cb_ids(data_cb, "u_")
        if len(ids) == 2:
            await show_user_menu(query, context, ids[0], ids[1])
        return
    if data_cb.startswith("mute_"):
        ids = cb_ids(data_cb, "mute_")
        if len(ids) == 2:
            context.user_data["state"] = "mute_minutes"
            context.user_data["selected_guild"] = ids[0]
            context.user_data["selected_user"] = ids[1]
            await safe_edit(query, "🔇 Введите минуты для мута (1-40320):")
        return
    if data_cb.startswith("kick_"):
        ids = cb_ids(data_cb, "kick_")
        if len(ids) == 2:
            context.user_data["state"] = "kick_reason"
            context.user_data["selected_guild"] = ids[0]
            context.user_data["selected_user"] = ids[1]
            await safe_edit(query, "👢 Введите причину кика:")
        return
    if data_cb.startswith("ban_"):
        ids = cb_ids(data_cb, "ban_")
        if len(ids) == 2:
            context.user_data["state"] = "ban_days"
            context.user_data["selected_guild"] = ids[0]
            context.user_data["selected_user"] = ids[1]
            await safe_edit(query, "🔨 Введите дни бана (0 = навсегда):")
        return
    if data_cb.startswith("totals_"):
        ids = cb_ids(data_cb, "totals_")
        if len(ids) == 2:
            t = totals_of(ids[0], ids[1])
            text = f"📊 Тоталы\n🔇 Муты: {t['mute']}\n👢 Кики: {t['kick']}\n🔨 Баны: {t['ban']}\n📊 Всего: {t['mute'] + t['kick'] + t['ban']}"
            kb = [[InlineKeyboardButton("◀️ Назад", callback_data=f"u_{ids[0]}_{ids[1]}")]]
            await safe_edit(query, text, InlineKeyboardMarkup(kb))
        return
    if data_cb.startswith("mp_"):
        ids = cb_ids(data_cb, "mp_")
        if len(ids) == 2:
            await show_moders(query, context, ids[0], ids[1])
        return
    if data_cb.startswith("cp_"):
        ids = cb_ids(data_cb, "cp_")
        if len(ids) == 2:
            await show_channels(query, context, ids[0], ids[1])
        return
    if data_cb.startswith("c_"):
        ids = cb_ids(data_cb, "c_")
        if len(ids) == 2:
            context.user_data["state"] = "send_message"
            context.user_data["selected_guild"] = ids[0]
            context.user_data["selected_channel"] = ids[1]
            await safe_edit(query, "✏️ Введите текст сообщения:")
        return
    if data_cb == "info":
        await show_info(query)
        return
    if data_cb == "access":
        await show_access(query, user_id)
        return

    if data_cb.startswith("usearch_"):
        ids = cb_ids(data_cb, "usearch_")
        if ids:
            context.user_data["state"] = "search_user"
            context.user_data["selected_guild"] = ids[0]
            await safe_edit(query, f"🔍 Введите имя или часть имени пользователя для поиска.\n\nОтмена: /cancel")
        return

    if data_cb.startswith("tg_actionlog_"):
        parts = data_cb[len("tg_actionlog_"):].split("_")
        try:
            pg = int(parts[0])
        except Exception:
            pg = 0
        logs = data.get("tg_action_logs", [])
        if not logs:
            await safe_edit(query, "📋 Лог действий из Telegram-панели пуст.", InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="main")]]))
            return
        PAGE = 10
        logs_rev = list(reversed(logs))
        max_pg = max(0, (len(logs_rev) - 1) // PAGE)
        pg = max(0, min(pg, max_pg))
        slice_ = logs_rev[pg * PAGE:(pg + 1) * PAGE]
        lines = [f"📋 Лог действий TG-панели (стр. {pg+1}/{max_pg+1})\n"]
        for e in slice_:
            lines.append(f"[{e['ts']}] {e['tg_name']} (ID:{e['tg_id']})\n  → {e['action']}\n")
        kb = []
        nav = []
        if pg > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"tg_actionlog_{pg-1}"))
        if pg < max_pg:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"tg_actionlog_{pg+1}"))
        if nav:
            kb.append(nav)
        kb.append([InlineKeyboardButton("◀️ Главное меню", callback_data="main")])
        await safe_edit(query, "\n".join(lines), InlineKeyboardMarkup(kb))
        return

    await safe_edit(query, "🤖 Панель управления ботом", main_menu_keyboard(user_id))

async def tg_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if tg_need_activation():
        if text == TG_PASSWORD:
            data["tg_owner"] = user_id
            data["tg_activated"] = True
            if user_id not in data["tg_access"]:
                data["tg_access"].append(user_id)
            save_data()
            await update.message.reply_text("✅ Панель активирована! Вы — владелец. Теперь /start для доступа.")
        else:
            await update.message.reply_text("🔐 Неверный пароль.")
        return
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа к панели.")
        return

    tracking = data.get("tg_tracking", {}).get(str(user_id))
    state = context.user_data.get("state")

    if tracking and not state:
        guild = bot.get_guild(tracking.get("guild"))
        channel = guild.get_channel(tracking.get("channel")) if guild else None
        if not channel:
            await update.message.reply_text("❌ Канал не найден. Отслеживание остановлено.")
            data["tg_tracking"].pop(str(user_id), None)
            save_data()
            return

        if update.message.reply_to_message:
            replied_tg_id = str(update.message.reply_to_message.message_id)
            mapped = data.get("tg_msg_map", {}).get(replied_tg_id)
            if mapped and mapped.get("ch") == channel.id:
                async def _reply():
                    try:
                        orig = await channel.fetch_message(mapped["msg"])
                        await orig.reply(text)
                        return f"✅ Ответ отправлен в #{channel.name}"
                    except Exception as e:
                        return f"❌ Ошибка: {e}"
                res = run_discord(_reply(), timeout=15)
                await update.message.reply_text(res)
                return

        async def _send():
            try:
                await channel.send(text)
                return f"✅ Отправлено в #{channel.name}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        res = run_discord(_send(), timeout=15)
        await update.message.reply_text(res)
        return

    if not state:
        await update.message.reply_text("ℹ️ Используйте /start для открытия панели.")
        return

    gid = context.user_data.get("selected_guild")
    uid = context.user_data.get("selected_user")
    guild = bot.get_guild(gid) if gid else None

    if state == "discord_reply":
        cid = context.user_data.get("discord_reply_ch")
        mid = context.user_data.get("discord_reply_msg")
        ch_obj = None
        for g in bot.guilds:
            c = g.get_channel(cid)
            if c:
                ch_obj = c
                break
        if not ch_obj:
            context.user_data["state"] = None
            await update.message.reply_text("❌ Канал не найден.")
            return
        async def _dreply():
            try:
                orig = await ch_obj.fetch_message(mid)
                await orig.reply(text)
                return f"✅ Ответ отправлен в #{ch_obj.name}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        res = run_discord(_dreply(), timeout=15)
        await update.message.reply_text(res)
        context.user_data["state"] = None
        return

    if state == "mute_minutes":
        try:
            minutes = int(text)
            if not 1 <= minutes <= 40320:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Введите число от 1 до 40320.")
            return
        context.user_data["mute_minutes"] = minutes
        context.user_data["state"] = "mute_reason"
        await update.message.reply_text("📝 Введите причину мута:")
        return

    if state == "mute_reason":
        minutes = context.user_data.get("mute_minutes", 60)
        member = guild.get_member(uid) if guild else None
        if not member:
            context.user_data["state"] = None
            await update.message.reply_text("❌ Пользователь не найден.")
            return
        async def _mute():
            try:
                await member.timeout(timedelta(minutes=minutes), reason=f"TG: {text}")
                return f"✅ Мут на {minutes} мин. выдан {member.display_name}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        res = run_discord(_mute())
        if res.startswith("✅"):
            tg_action_log(user_id, update.effective_user.username or update.effective_user.first_name,
                          f"МУТ на {minutes} мин. → {member.display_name} (ID:{member.id}) на сервере {guild.name}. Причина: {text}")
        await update.message.reply_text(res)
        context.user_data["state"] = None
        return

    if state == "kick_reason":
        member = guild.get_member(uid) if guild else None
        if not member:
            context.user_data["state"] = None
            await update.message.reply_text("❌ Пользователь не найден.")
            return
        async def _kick():
            try:
                await member.kick(reason=f"TG: {text}")
                return f"✅ {member.display_name} кикнут."
            except Exception as e:
                return f"❌ Ошибка: {e}"
        res = run_discord(_kick())
        if res.startswith("✅"):
            tg_action_log(user_id, update.effective_user.username or update.effective_user.first_name,
                          f"КИК → {member.display_name} (ID:{member.id}) на сервере {guild.name}. Причина: {text}")
        await update.message.reply_text(res)
        context.user_data["state"] = None
        return

    if state == "ban_days":
        try:
            days = int(text)
            if days < 0 or days > 3650:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Введите число от 0 до 3650.")
            return
        context.user_data["ban_days"] = days
        context.user_data["state"] = "ban_reason"
        await update.message.reply_text("📝 Введите причину бана:")
        return

    if state == "ban_reason":
        member = guild.get_member(uid) if guild else None
        if not member:
            context.user_data["state"] = None
            await update.message.reply_text("❌ Пользователь не найден.")
            return
        async def _ban():
            try:
                await guild.ban(member, reason=f"TG: {text}")
                return f"✅ {member.display_name} забанен."
            except Exception as e:
                return f"❌ Ошибка: {e}"
        res = run_discord(_ban())
        if res.startswith("✅"):
            tg_action_log(user_id, update.effective_user.username or update.effective_user.first_name,
                          f"БАН → {member.display_name} (ID:{member.id}) на сервере {guild.name}. Причина: {text}")
        await update.message.reply_text(res)
        context.user_data["state"] = None
        return

    if state == "send_message":
        cid = context.user_data.get("selected_channel")
        channel = guild.get_channel(cid) if guild else None
        if not channel:
            context.user_data["state"] = None
            await update.message.reply_text("❌ Канал не найден.")
            return
        async def _send():
            try:
                await channel.send(text)
                return f"✅ Отправлено в #{channel.name}"
            except Exception as e:
                return f"❌ Ошибка: {e}"
        res = run_discord(_send())
        if res.startswith("✅"):
            tg_action_log(user_id, update.effective_user.username or update.effective_user.first_name,
                          f"Сообщение в #{channel.name} ({guild.name}): {text[:80]}")
        await update.message.reply_text(res)
        context.user_data["state"] = None
        return

    if state == "search_user":
        gid = context.user_data.get("selected_guild")
        if not gid:
            gid = Config.GUILD_ID or ALLOWED_GUILD_ID or (bot.guilds[0].id if bot.guilds else None)
        query_str = text.lower().strip()

        async def _do_search():
            target_guild = bot.get_guild(gid) if gid else None
            guilds_to_search = [target_guild] if target_guild else list(bot.guilds)
            matched = []
            seen_ids = set()

            for g in guilds_to_search:
                if not g:
                    continue

                if query_str.isdigit():
                    uid = int(query_str)
                    m = g.get_member(uid)
                    if not m:
                        try:
                            m = await g.fetch_member(uid)
                        except Exception:
                            pass
                    if m and m.id not in seen_ids:
                        seen_ids.add(m.id)
                        matched.append(m)

                try:
                    qm = await g.query_members(query=query_str, limit=50)
                    for m in qm:
                        if m.id not in seen_ids:
                            seen_ids.add(m.id)
                            matched.append(m)
                except Exception:
                    pass

                for m in g.members:
                    if m.id in seen_ids:
                        continue
                    disp = (m.display_name or "").lower()
                    uname = (m.name or "").lower()
                    gname = (getattr(m, "global_name", "") or "").lower()
                    if query_str in disp or query_str in uname or query_str in gname or query_str == str(m.id):
                        seen_ids.add(m.id)
                        matched.append(m)

            return matched

        found = run_discord(_do_search(), timeout=15) or []

        if not found:
            await update.message.reply_text(f"🔍 По запросу «{text}» никого не найдено. Попробуйте ещё раз или /cancel.")
            return

        context.user_data["state"] = None
        target_gid = gid or (found[0].guild.id if found else ALLOWED_GUILD_ID)

        if len(found) == 1:
            from telegram import InlineKeyboardMarkup as IKM, InlineKeyboardButton as IKB
            m = found[0]
            role_names = [r.name for r in m.roles[1:]]
            roles_text = ", ".join(role_names[:8]) or "нет"
            msg_text = (
                f"👤 {m.display_name} ({m.name})\nID: {m.id}\n"
                f"🎭 Ролей: {len(m.roles) - 1}\n🎭 Роли: {roles_text}\n\nВыберите действие:"
            )
            keyboard = [
                [IKB("🔇 Мут", callback_data=f"mute_{target_gid}_{m.id}")],
                [IKB("👢 Кик", callback_data=f"kick_{target_gid}_{m.id}")],
                [IKB("🔨 Бан", callback_data=f"ban_{target_gid}_{m.id}")],
                [IKB("📊 Тоталы", callback_data=f"totals_{target_gid}_{m.id}")],
                [IKB("🎭 Роли", callback_data=f"uroles_{target_gid}_{m.id}")],
                [IKB("◀️ Назад", callback_data=f"up_{target_gid}_0")],
            ]
            context.user_data["selected_user"] = m.id
            await update.message.reply_text(msg_text, reply_markup=IKM(keyboard))
        else:
            from telegram import InlineKeyboardMarkup as IKM, InlineKeyboardButton as IKB
            lines = [f"🔍 Найдено {len(found)} пользователей по запросу «{text}»:\n"]
            keyboard = []
            for m in found[:20]:
                label = f"{'🤖 ' if m.bot else ''}{m.display_name} (@{m.name})"
                keyboard.append([IKB(label[:40], callback_data=f"u_{target_gid}_{m.id}")])
            keyboard.append([IKB("◀️ Назад к списку", callback_data=f"up_{target_gid}_0")])
            await update.message.reply_text("\n".join(lines), reply_markup=IKM(keyboard))
        return

    if state == "search_bans":
        query_str = text.lower().strip()

        async def _do_search_bans():
            matched_bans = []
            for g in bot.guilds:
                if not g:
                    continue
                me = g.me or g.get_member(bot.user.id if bot.user else 0)
                if me and not me.guild_permissions.ban_members:
                    log.warning("Бот не имеет прав ban_members на сервере %s", g.name)
                    continue
                try:
                    async for entry in g.bans(limit=None):
                        user = entry.user
                        reason = entry.reason or "Причина не указана"

                        r_lower = reason.lower()
                        u_name = user.name.lower()
                        u_gname = (getattr(user, "global_name", "") or "").lower()
                        u_disp = (getattr(user, "display_name", "") or "").lower()
                        u_id = str(user.id)

                        if (query_str in r_lower or 
                            query_str == u_id or 
                            query_str in u_name or 
                            query_str in u_gname or 
                            query_str in u_disp):
                            matched_bans.append({
                                "guild": g.name,
                                "guild_id": g.id,
                                "user_name": str(user),
                                "user_id": user.id,
                                "reason": reason
                            })
                except Exception as e:
                    log.error("Ошибка при получении банов для сервера %s: %s", g.name, e)
            return matched_bans

        res = run_discord(_do_search_bans(), timeout=25)

        from telegram import InlineKeyboardMarkup as IKM, InlineKeyboardButton as IKB

        if isinstance(res, str):
            context.user_data["state"] = None
            kb = [
                [IKB("🔍 Попробовать снова", callback_data="search_bans_start")],
                [IKB("◀️ Главное меню", callback_data="main")]
            ]
            await update.message.reply_text(
                f"{res}",
                reply_markup=IKM(kb),
                parse_mode="Markdown"
            )
            return

        found_bans = res if isinstance(res, list) else []

        if not found_bans:
            context.user_data["state"] = None
            kb = [
                [IKB("🔍 Новый поиск", callback_data="search_bans_start")],
                [IKB("◀️ Главное меню", callback_data="main")]
            ]
            await update.message.reply_text(
                f"❌ **По запросу «{text}» банов в системе не найдено.**",
                reply_markup=IKM(kb),
                parse_mode="Markdown"
            )
            return

        context.user_data["state"] = None
        context.user_data["last_search_bans"] = found_bans
        context.user_data["last_search_query"] = text

        lines = [f"🔨 **Найдено банов: {len(found_bans)}** (по запросу «`{text}`»):\n"]
        for idx, b in enumerate(found_bans[:25], 1):
            lines.append(
                f"**{idx}. {b['user_name']}** (`{b['user_id']}`)\n"
                f"   📌 Причина: `{b['reason']}`\n"
                f"   🌐 Сервер: {b['guild']}"
            )

        if len(found_bans) > 25:
            lines.append(f"\n...и ещё {len(found_bans) - 25} банов.")

        msg_text = "\n\n".join(lines)
        if len(msg_text) > 4000:
            msg_text = msg_text[:3950] + "\n\n...(сообщение урезано из-за лимита)"

        kb = [
            [IKB(f"🔓 Разбанить всех с этой причиной ({len(found_bans)})", callback_data="unban_all_search")],
            [IKB("🔍 Новый поиск", callback_data="search_bans_start")],
            [IKB("◀️ Главное меню", callback_data="main")]
        ]
        await update.message.reply_text(msg_text, reply_markup=IKM(kb), parse_mode="Markdown")
        return


async def tg_export_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа к панели.")
        return
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, export_database_to_tg, user_id)
    if ok:
        await update.message.reply_text(f"✅ База данных `moderbot.sqlite3` выгружена и отправлена вам в ЛС (ID: `{user_id}`).", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Ошибка при экспорте базы данных.")

async def tg_save_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    query = update.callback_query
    if not user_id and query and query.from_user:
        user_id = query.from_user.id
    if not user_id or (user_id != 8035721101 and not tg_is_owner(user_id)):
        if query:
            await safe_edit(query, "❌ Доступно только для владельца")
        elif update.message:
            await update.message.reply_text("❌ Доступно только для владельца")
        return

    async def _sync():
        guild_id = 1070704320951095296
        await db.save_moderators_backup(guild_id)
        return True

    res = run_discord(_sync(), timeout=15)
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, export_database_to_tg, 8035721101)
    msg = (
        "💾 **Вся статистика и настройки успешно сохранены и выгружены!**\n\n"
        "- `bot_data.json` и `full_backup.json` обновлены.\n"
        "- Файл `moderbot.sqlite3` отправлен вам в ЛС."
    ) if ok else "⚠️ Статистика сохранена в файлы, но не удалось выгрузить БД в TG."

    if query:
        await safe_edit(query, msg, reply_markup=main_menu_keyboard(user_id), parse_mode="Markdown")
    elif update.message:
        await update.message.reply_text(msg, parse_mode="Markdown")

@bot.command(name="report")
async def report_prefix(ctx, *, text: str = None):
    if not text:
        await ctx.send("❌ Использование: `!report <текст>` или `/report <текст>`")
        return

    ticket_id = get_next_ticket_id()
    data.setdefault("tickets", {})[str(ticket_id)] = {
        "id": ticket_id,
        "author": str(ctx.author),
        "author_id": ctx.author.id,
        "author_discord_id": ctx.author.id,
        "title": "Репорт от Discord",
        "content": text,
        "status": "open",
        "taken_by": None,
        "taken_at": None,
        "answers": [],
        "created_at": datetime.now(timezone.utc).timestamp(),
        "guild_id": ctx.guild.id if ctx.guild else 0,
        "guild_name": ctx.guild.name if ctx.guild else "ЛС",
        "channel_id": ctx.channel.id if ctx.channel else 0,
        "source": "discord"
    }
    save_data()

    if tg_bot_ref:
        target_chats = set(data.get("tg_access", []))
        if data.get("tg_owner"):
            target_chats.add(data["tg_owner"])
        for chat_id in target_chats:
            try:
                await tg_bot_ref.send_message(
                    chat_id=chat_id,
                    text=(
                        f"🎫 **Новый репорт #{ticket_id}**\n\n"
                        f"**От:** {ctx.author} (ID: {ctx.author.id})\n"
                        f"**Сервер:** {ctx.guild.name if ctx.guild else 'ЛС'}\n"
                        f"**Текст:** {text}\n\n"
                        f"Для ответа: /p {ticket_id}"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                log.error("Ошибка отправки тикета в TG: %s", e)

    await ctx.send(f"✅ Ваш репорт отправлен! Номер тикета: #{ticket_id}")

async def tg_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    profile = get_user_profile(user_id)
    access_level = get_user_access_level(user_id)
    position = get_user_position(user_id)
    discord_id = profile.get("discord_id", "Не привязан")
    is_private = update.message.chat.type == "private"
    text = (
        f"👤 **Ваш профиль**\n\n"
        f"**Должность:** {position}\n"
        f"**Уровень доступа:** {access_level} - {ACCESS_LEVELS.get(access_level, 'Пользователь')}\n"
        f"**Discord ID:** {discord_id}\n"
        f"**Telegram ID:** {user_id}\n"
    )
    keyboard = []
    if is_private:
        keyboard.append([InlineKeyboardButton("🔄 Переаутентификация", callback_data="reauth")])
        keyboard.append([InlineKeyboardButton("🗑 Удалить профиль", callback_data="delete_profile")])
    else:
        text += "\n⚠️ Переаутентификация и удаление профиля доступны только в личных сообщениях бота."
    if keyboard:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")

async def tg_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    if update.message.chat.type != "private":
        await update.message.reply_text("❌ Эта команда доступна только в личных сообщениях.")
        return
    text = (
        "📋 **Список уровней доступа:**\n\n"
        "7 - Главный Разработчик\n"
        "6 - Помощник Разработчика\n"
        "5 - Руководство\n"
        "4 - Главная Модерация\n"
        "3 - Следящая Модерация\n"
        "2 - Куратор Модерации\n"
        "1 - Хелпер (выдается вручную)\n\n"
        "Для выдачи должности используйте:\n"
        "/set post @username <номер уровня>"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def tg_set_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    access_level = get_user_access_level(user_id)
    if access_level < 5 and not tg_is_owner(user_id):
        await update.message.reply_text("❌ Выдавать должности может только руководство (уровень 5+) или владелец.")
        return
    args = context.args
    if len(args) < 2 or args[0].lower() != "post":
        await update.message.reply_text("❌ Использование: /set post @username <номер уровня (1-7)>")
        return
    if len(args) < 3:
        await update.message.reply_text("❌ Укажите номер уровня доступа (1-7)")
        return
    try:
        access_level = int(args[2])
        if access_level < 1 or access_level > 7:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Уровень доступа должен быть числом от 1 до 7")
        return
    username = args[1].replace("@", "").strip()
    target_id = None
    if username.isdigit():
        target_id = int(username)
    else:
        for uid in data.get("tg_access", []):
            try:
                if tg_bot_ref:
                    chat = await tg_bot_ref.get_chat(uid)
                    if chat.username and chat.username.lower() == username.lower():
                        target_id = uid
                        break
            except Exception:
                continue
    if not target_id:
        await update.message.reply_text(f"❌ Пользователь @{username} не найден")
        return
    profile = data.setdefault("profiles", {}).setdefault(str(target_id), {})
    profile["access_level"] = access_level
    profile["position"] = ACCESS_LEVELS.get(access_level, "Пользователь")
    save_data()
    await update.message.reply_text(
        f"✅ Пользователю @{username} выдан уровень доступа {access_level} - "
        f"{ACCESS_LEVELS.get(access_level, 'Пользователь')}"
    )

async def tg_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    profile = get_user_profile(user_id)
    access_level = get_user_access_level(user_id)
    position = get_user_position(user_id)
    discord_id = profile.get("discord_id", "Не привязан")
    text = (
        f"📊 **Информация о вас**\n\n"
        f"**Должность:** {position}\n"
        f"**Уровень доступа:** {access_level}\n"
        f"**Discord ID:** {discord_id}\n"
        f"**Telegram ID:** {user_id}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def tg_p(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("⛔ У вас нет доступа к панели.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("💡 Использование:\n`/p <id тикета>` — взять тикет\n`/p <id тикета> <ответ>` — взять и ответить", parse_mode="Markdown")
        return

    try:
        ticket_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID тикета должен быть числом.")
        return

    tickets = data.get("tickets", {})
    ticket = tickets.get(str(ticket_id)) or tickets.get(ticket_id)
    if not ticket:
        await update.message.reply_text(f"❌ Тикет #{ticket_id} не найден.")
        return
    if ticket.get("status") == "closed":
        await update.message.reply_text(f"❌ Тикет #{ticket_id} уже закрыт.")
        return

    ticket["taken_by"] = user_id
    ticket["taken_at"] = datetime.now(timezone.utc).timestamp()
    ticket["status"] = "in_progress"
    save_data()

    if len(args) > 1:
        answer_text = " ".join(args[1:])
        ticket.setdefault("answers", []).append({
            "from": user_id,
            "text": answer_text,
            "ts": datetime.now(timezone.utc).timestamp()
        })
        save_data()

        stats = data.setdefault("helper_stats", {}).setdefault(str(user_id), {})
        stats["tickets_answered"] = stats.get("tickets_answered", 0) + 1
        save_data()

        if ticket.get("author_discord_id") and ticket.get("source") == "discord":
            async def _send_discord_answer():
                try:
                    user = await bot.fetch_user(int(ticket["author_discord_id"]))
                    if user:
                        msg_text = f"💬 **Ответ на ваш репорт/тикет #{ticket_id}**\n\n{answer_text}\n\nС уважением, поддержка проекта."
                        await user.send(msg_text)
                        return True
                    return False
                except Exception as e:
                    log.error("Ошибка отправки ответа в Discord: %s", e)
                    return False

            res = run_discord(_send_discord_answer(), timeout=30)
            if res is True:
                await update.message.reply_text(f"✅ Тикет #{ticket_id} взят, ответ успешно отправлен пользователю в Discord!")
            else:
                await update.message.reply_text(f"✅ Тикет #{ticket_id} взят, ответ сохранён, но не удалось доставить его в ЛС Discord.")
        else:
            await update.message.reply_text(f"✅ Тикет #{ticket_id} взят, ответ сохранён!")
    else:
        content_preview = ticket.get("content") or ticket.get("text") or ticket.get("title") or "Без содержания"
        author_info = ticket.get("author") or f"ID: {ticket.get('author_id', 'Неизвестно')}"
        msg_took = (
            f"✅ **Тикет #{ticket_id} успешно взят в работу!**\n\n"
            f"📌 **Содержание:** {content_preview}\n"
            f"👤 **Автор:** {author_info}\n\n"
            f"💬 Чтобы ответить пользователю, введите:\n`/p {ticket_id} <ваш ответ>` или `/answer {ticket_id} <ваш ответ>`"
        )
        await update.message.reply_text(msg_took, parse_mode="Markdown")
async def tg_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    access_level = get_user_access_level(user_id)
    if access_level < 1:
        await update.message.reply_text("❌ Недостаточно прав.")
        return
    tickets = data.get("tickets", {})
    if not tickets:
        await update.message.reply_text("📋 Активных тикетов нет.")
        return
    text = "🎫 **Активные тикеты:**\n\n"
    ticket_count = 0
    for ticket_id, ticket in list(tickets.items()):
        if ticket.get("status") in ["open", "in_progress"]:
            ticket_count += 1
            status_text = "Открыт"
            if ticket.get("status") == "in_progress":
                taken_by = ticket.get("taken_by")
                if taken_by:
                    try:
                        if tg_bot_ref:
                            chat = await tg_bot_ref.get_chat(taken_by)
                            helper_name = f"@{chat.username}" if chat.username else f"ID: {taken_by}"
                            status_text = f"Взят: {helper_name}"
                    except Exception:
                        status_text = "В работе"
                else:
                    status_text = "В работе"
            text += f"Ticket #{ticket_id}: {ticket.get('title', 'Без названия')}\n"
            text += f"От: {ticket.get('author', 'Неизвестно')}\n"
            text += f"Статус: {status_text}\n"
            text += f"Ответов: {len(ticket.get('answers', []))}\n\n"
            if ticket_count >= 10:
                text += "И ещё больше тикетов..."
                break
    if ticket_count == 0:
        text = "📋 Активных тикетов нет."
    await update.message.reply_text(text, parse_mode="Markdown")

async def tg_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    access_level = get_user_access_level(user_id)
    if access_level < 1:
        await update.message.reply_text("❌ Недостаточно прав.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: /answer <номер тикета> <ответ>")
        return
    try:
        ticket_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Номер тикета должен быть числом.")
        return
    answer_text = " ".join(args[1:])
    tickets = data.get("tickets", {})
    ticket = tickets.get(str(ticket_id))
    if not ticket:
        await update.message.reply_text(f"❌ Тикет #{ticket_id} не найден.")
        return
    if ticket.get("taken_by") != user_id:
        await update.message.reply_text(f"❌ Сначала возьмите тикет с помощью /p {ticket_id}")
        return
    ticket.setdefault("answers", []).append({
        "from": user_id,
        "text": answer_text,
        "ts": utcnow().timestamp()
    })
    save_data()
    stats = data.setdefault("helper_stats", {}).setdefault(str(user_id), {})
    stats["tickets_answered"] = stats.get("tickets_answered", 0) + 1
    save_data()
    if ticket.get("author_discord_id") and ticket.get("source") == "discord":
        async def _send_discord_answer():
            try:
                user = await bot.fetch_user(int(ticket["author_discord_id"]))
                if user:
                    await user.send(
                        f"📬 **Ответ на ваш репорт #{ticket_id}**\n\n"
                        f"{answer_text}\n\n"
                        f"С уважением, команда модерации."
                    )
                    return True
                return False
            except Exception as e:
                log.error("Ошибка отправки ответа в Discord: %s", e)
                return False
        result = run_discord(_send_discord_answer(), timeout=30)
        if result:
            await update.message.reply_text(f"✅ Ответ отправлен в тикет #{ticket_id} и пользователю в Discord.")
        else:
            await update.message.reply_text(f"✅ Ответ записан в тикет #{ticket_id}, но не удалось отправить в Discord.")
    else:
        await update.message.reply_text(f"✅ Ответ отправлен в тикет #{ticket_id}")

async def tg_closed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    access_level = get_user_access_level(user_id)
    if access_level < 1:
        await update.message.reply_text("❌ Недостаточно прав.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Использование: /closed <номер тикета>")
        return
    try:
        ticket_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Номер тикета должен быть числом.")
        return
    tickets = data.get("tickets", {})
    ticket = tickets.get(str(ticket_id))
    if not ticket:
        await update.message.reply_text(f"❌ Тикет #{ticket_id} не найден.")
        return
    if ticket.get("taken_by") != user_id:
        await update.message.reply_text(f"❌ Вы не можете закрыть этот тикет.")
        return
    ticket["status"] = "closed"
    ticket["closed_by"] = user_id
    ticket["closed_at"] = utcnow().timestamp()
    save_data()
    stats = data.setdefault("helper_stats", {}).setdefault(str(user_id), {})
    stats["tickets_closed"] = stats.get("tickets_closed", 0) + 1
    save_data()
    await update.message.reply_text(f"✅ Тикет #{ticket_id} закрыт.")

async def tg_hstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    stats = data.get("helper_stats", {}).get(str(user_id), {})
    text = (
        f"📊 **Статистика Хелпера**\n\n"
        f"**Тикетов взято:** {stats.get('tickets_taken', 0)}\n"
        f"**Тикетов отвечено:** {stats.get('tickets_answered', 0)}\n"
        f"**Тикетов закрыто:** {stats.get('tickets_closed', 0)}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def tg_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    access_level = get_user_access_level(user_id)
    text = (
        "❓ **Доступные команды:**\n\n"
        "**Основные:**\n"
        "/start - Главное меню\n"
        "/help - Показать эту справку\n"
        "/profile - Ваш профиль\n"
        "/me - Информация о вас\n\n"
    )
    if access_level >= 1:
        text += (
            "**Для Хелперов:**\n"
            "/tickets - Список тикетов\n"
            "/p <номер> - Взять тикет\n"
            "/answer <номер> <текст> - Ответить в тикет\n"
            "/closed <номер> - Закрыть тикет\n"
            "/hstats - Статистика хелпера\n\n"
        )
    if access_level >= 2:
        text += (
            "**Для Модерации:**\n"
            "/ban <id> <дни> <причина> - Забанить пользователя\n"
            "/kick <id> <причина> - Кикнуть пользователя\n"
            "/mute <id> <минуты> <причина> - Замутить пользователя\n\n"
        )
    if tg_is_owner(user_id):
        text += (
            "**Для Владельца:**\n"
            "/set post @username <уровень> - Выдать должность\n"
            "/posts - Список уровней доступа\n"
            "/apanel add @username - Выдать доступ\n"
            "/apanel del @username - Забрать доступ\n"
        )
    await update.message.reply_text(text, parse_mode="Markdown")

async def tg_apanel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_is_owner(user_id):
        await update.message.reply_text("❌ Только владелец панели.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("❌ Использование: /apanel add <@username или ID> или /apanel del <@username или ID>")
        return
    action = args[0].lower()
    if len(args) >= 2:
        target_str = args[1].replace("@", "").strip()
    elif update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_str = str(update.message.reply_to_message.from_user.id)
    else:
        await update.message.reply_text("❌ Укажите @username или ID.")
        return
    target_id = None
    if target_str.isdigit():
        target_id = int(target_str)
    else:
        for uid in data.get("tg_access", []):
            try:
                if tg_bot_ref:
                    chat = await tg_bot_ref.get_chat(uid)
                    if chat.username and chat.username.lower() == target_str.lower():
                        target_id = uid
                        break
            except Exception:
                continue
    if not target_id:
        await update.message.reply_text("❌ Пользователь не найден.")
        return
    if action == "add":
        if target_id not in data["tg_access"]:
            data["tg_access"].append(target_id)
            profile = data.setdefault("profiles", {}).setdefault(str(target_id), {})
            profile["access_level"] = 1
            profile["position"] = "Хелпер"
            save_data()
            await update.message.reply_text(f"✅ Доступ выдан пользователю ID {target_id}.")
        else:
            await update.message.reply_text(f"ℹ️ У пользователя ID {target_id} уже есть доступ.")
    elif action in ("del", "delete", "remove"):
        if target_id == data.get("tg_owner"):
            await update.message.reply_text("❌ Нельзя забрать доступ у владельца.")
            return
        if target_id in data["tg_access"]:
            data["tg_access"].remove(target_id)
            data.get("profiles", {}).pop(str(target_id), None)
            save_data()
            await update.message.reply_text(f"✅ Доступ забран у пользователя ID {target_id}.")
        else:
            await update.message.reply_text(f"ℹ️ У пользователя ID {target_id} нет доступа.")

async def tg_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    access_level = get_user_access_level(user_id)
    if access_level < 2:
        await update.message.reply_text("❌ Недостаточно прав.")
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ Использование: /ban <id> <дни> <причина>")
        return
    try:
        discord_id = int(args[0])
        days = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ ID и дни должны быть числами.")
        return
    reason = " ".join(args[2:])
    async def _ban_user():
        results = []
        for guild in bot.guilds:
            member = guild.get_member(discord_id)
            if member:
                try:
                    await guild.ban(member, reason=f"TG: {reason}", delete_message_days=0)
                    results.append(f"✅ Забанен на сервере {guild.name}")
                except Exception as e:
                    results.append(f"❌ Ошибка на сервере {guild.name}: {e}")
        return "\n".join(results) if results else "❌ Пользователь не найден."
    res = run_discord(_ban_user(), timeout=60)
    await update.message.reply_text(res)

async def tg_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    access_level = get_user_access_level(user_id)
    if access_level < 2:
        await update.message.reply_text("❌ Недостаточно прав.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: /kick <id> <причина>")
        return
    try:
        discord_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    reason = " ".join(args[1:])
    async def _kick_user():
        results = []
        for guild in bot.guilds:
            member = guild.get_member(discord_id)
            if member:
                try:
                    await member.kick(reason=f"TG: {reason}")
                    results.append(f"✅ Кикнут с сервера {guild.name}")
                except Exception as e:
                    results.append(f"❌ Ошибка на сервере {guild.name}: {e}")
        return "\n".join(results) if results else "❌ Пользователь не найден."
    res = run_discord(_kick_user(), timeout=60)
    await update.message.reply_text(res)

async def tg_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: 
        return
    user_id = update.effective_user.id
    if not tg_has_access(user_id):
        await update.message.reply_text("❌ У вас нет доступа.")
        return
    access_level = get_user_access_level(user_id)
    if access_level < 2:
        await update.message.reply_text("❌ Недостаточно прав.")
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ Использование: /mute <id> <минуты> <причина>")
        return
    try:
        discord_id = int(args[0])
        minutes = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ ID и минуты должны быть числами.")
        return
    reason = " ".join(args[2:])
    async def _mute_user():
        results = []
        for guild in bot.guilds:
            member = guild.get_member(discord_id)
            if member:
                try:
                    await member.timeout(timedelta(minutes=minutes), reason=f"TG: {reason}")
                    results.append(f"✅ Замучен на {minutes} мин на сервере {guild.name}")
                except Exception as e:
                    results.append(f"❌ Ошибка на сервере {guild.name}: {e}")
        return "\n".join(results) if results else "❌ Пользователь не найден."
    res = run_discord(_mute_user(), timeout=60)
    await update.message.reply_text(res)

def run_telegram():
    global tg_bot_ref
    if not TG_AVAILABLE or not Config.TG_TOKEN:
        log.warning("Telegram не может быть запущен (библиотека или токен отсутствуют)")
        return
    while True:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            tg_app = Application.builder().token(Config.TG_TOKEN).build()
            tg_bot_ref = tg_app.bot

            tg_app.add_handler(CommandHandler("start", tg_start))
            tg_app.add_handler(CommandHandler("cancel", tg_cancel))
            tg_app.add_handler(CommandHandler("profile", tg_profile))
            tg_app.add_handler(CommandHandler("me", tg_me))
            tg_app.add_handler(CommandHandler("tickets", tg_tickets))
            tg_app.add_handler(CommandHandler("p", tg_p))
            tg_app.add_handler(CommandHandler("answer", tg_answer))
            tg_app.add_handler(CommandHandler("closed", tg_closed))
            tg_app.add_handler(CommandHandler("hstats", tg_hstats))
            tg_app.add_handler(CommandHandler("posts", tg_posts))
            tg_app.add_handler(CommandHandler("set", tg_set_post))
            tg_app.add_handler(CommandHandler("apanel", tg_apanel))
            tg_app.add_handler(CommandHandler("apanel_add", tg_apanel_add))
            tg_app.add_handler(CommandHandler("apanel_del", tg_apanel_del))
            tg_app.add_handler(CommandHandler("ban", tg_ban))
            tg_app.add_handler(CommandHandler("kick", tg_kick))
            tg_app.add_handler(CommandHandler("mute", tg_mute))
            tg_app.add_handler(CommandHandler("help", tg_help))
            tg_app.add_handler(CommandHandler("code_generate", tg_code_generate))
            tg_app.add_handler(CommandHandler("code", tg_code))
            tg_app.add_handler(CommandHandler("export_db", tg_export_db))
            tg_app.add_handler(CommandHandler("save_all", tg_save_all))
            tg_app.add_handler(CommandHandler("save", tg_save_all))

            tg_app.add_handler(CallbackQueryHandler(tg_button))
            tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tg_text))

            log.info("📡 Telegram-панель запущена в фоновом режиме")
            tg_app.run_polling(drop_pending_updates=True, stop_signals=None)
        except Exception as e:
            log.error("❌ Ошибка в Telegram-панели: %s. Перезапуск через 10 сек...", e)
            time.sleep(10)


def main():
    global bot
    if not Config.TOKEN:
        raise SystemExit(
            "Не найден токен бота. Создайте файл .env со строкой:\n"
            "DISCORD_TOKEN=ваш_токен_бота"
        )
    time.sleep(3)
    while True:
        try:
            bot.run(Config.TOKEN, log_handler=None)
            break
        except Exception as exc:
            err_msg = str(exc)
            wait_sec = 90 if ("429" in err_msg or "Cloudflare" in err_msg) else 15
            log.warning("⚠️ Discord бот остановился: %s. Пересоздание через %d сек...", exc, wait_sec)
            time.sleep(wait_sec)
            try:
                bot = ModerBot()
            except Exception as e:
                log.error("Ошибка пересоздания бота: %s", e)

if __name__ == "__main__":
    main()
