from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from bot.config import DEFAULTS
from bot.db import Database
from bot.game import (
    GameData,
    apply_loot,
    calc_evac_chance,
    calc_event_chance,
    calc_inventory_value,
    calc_points,
    can_craft,
    consume_medkit,
    craft_deltas,
    format_item,
    format_loot_summary,
    has_consumable,
    inventory_count,
    normalize_sort,
    pick_random_item,
    rarity_emoji,
    resolve_fight,
    roll_bonus_drop,
    roll_loot_by_rarity,
    RARITY_ORDER,
    SORT_LABELS,
    select_items_by_capacity,
)


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR.parent / "data"))
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR.parent / "bot.db"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBAPP_BOT_USERNAME = os.getenv("WEBAPP_BOT_USERNAME", "").strip()
WEBAPP_DEFAULT_CHAT_ID = os.getenv("WEBAPP_DEFAULT_CHAT_ID", "").strip()
WEBAPP_DEFAULT_THREAD_ID = os.getenv("WEBAPP_DEFAULT_THREAD_ID", "").strip()
WEBAPP_AUTH_MAX_AGE = int(os.getenv("WEBAPP_AUTH_MAX_AGE", "86400"))
WEBAPP_AUTH_SECRET = os.getenv("WEBAPP_AUTH_SECRET", "").strip() or BOT_TOKEN
WEBAPP_TOKEN_TTL = int(os.getenv("WEBAPP_TOKEN_TTL", "2592000"))
WEBAPP_DISABLE_COOLDOWNS = os.getenv("WEBAPP_DISABLE_COOLDOWNS", "1").strip() == "1"
WEBAPP_ADMIN_EMAILS = os.getenv("WEBAPP_ADMIN_EMAILS", "").strip()


def _parse_int(value: str, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


DEFAULT_CHAT_ID = _parse_int(WEBAPP_DEFAULT_CHAT_ID, 1)
DEFAULT_THREAD_ID = _parse_int(WEBAPP_DEFAULT_THREAD_ID, 0)


app = FastAPI(title="Raiders Web App")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

db = Database(DB_PATH)
data = GameData()


ACTION_COOLDOWNS = (
    {}
    if WEBAPP_DISABLE_COOLDOWNS
    else {
        "loot": DEFAULTS.cooldown_loot,
        "move": DEFAULTS.cooldown_move,
        "fight": DEFAULTS.cooldown_fight,
        "evac": DEFAULTS.cooldown_evac,
        "medkit": DEFAULTS.cooldown_medkit,
    }
)

RC_EMOJI = "\U0001FA99"
STORAGE_PAGE_SIZE = 10
SELL_PAGE_SIZE = 8
EQUIP_PAGE_SIZE = 6
BLUEPRINT_PAGE_SIZE = 8
RATING_LIMIT = 10
WAREHOUSE_TOP_LIMIT = 10
MARKET_PAGE_SIZE = 8
MARKET_ITEMS_PAGE_SIZE = 8
QUEST_DAILY_COUNT = DEFAULTS.quest_daily_count
QUEST_WEEKLY_COUNT = DEFAULTS.quest_weekly_count

SHOP_PRICES = {
    "medkit": DEFAULTS.shop_price_medkit,
    "insurance": DEFAULTS.shop_price_insurance,
    "evac_beacon": DEFAULTS.shop_price_evac_beacon,
}
SHOP_ITEM_IDS = {
    "medkit": "bandage",
    "evac_beacon": "remote_raider_flare",
}
BASE_RECIPE_IDS = {
    "recipe_medkit",
    "recipe_evac_beacon",
    "recipe_armor",
    "recipe_module",
}
SHOP_DAILY_ITEM_COUNT = 2
SHOP_DAILY_BLUEPRINT_COUNT = 1
SHOP_RARITY_WEIGHT = {"rare": 6, "epic": 3, "legendary": 1}
SHOP_BLUEPRINT_WEIGHT = {"common": 5, "rare": 4, "epic": 3, "legendary": 2}
CASE_ITEMS_COUNT = DEFAULTS.daily_case_items
CASE_PITY_DAYS = DEFAULTS.daily_case_pity_days
CASE_RARITY_WEIGHT = {"common": 6, "rare": 3, "epic": 2, "legendary": 1}
CASE_GUARANTEE_RARITIES = {"rare", "epic", "legendary"}
SHOP_RARITY_MULT = {"rare": 2.5, "epic": 4.0, "legendary": 6.0}
SHOP_RARITY_MIN = {"rare": 110, "epic": 180, "legendary": 260}
ORDER_TARGET_MULT = {"common": 1.2, "rare": 1.0, "epic": 0.7, "legendary": 0.4}
ORDER_REWARD_MULT = {"common": 1.0, "rare": 1.2, "epic": 1.6, "legendary": 2.5}

ADMIN_EMAILS = {
    email.strip().lower()
    for email in WEBAPP_ADMIN_EMAILS.split(",")
    if email.strip()
}

ONBOARDING_STEPS = [
    "Добро пожаловать в ARC‑терминал. Здесь всё работает через вкладки сверху.",
    "Начни с рейда: вход — в «Рейд», дальше кнопки действий снизу.",
    "Лут хранится на складе, там же можно продавать или выставлять на рынок.",
    "Квесты и сезон — это доп. прогресс и награды. Заглядывай каждый день.",
]

QUEST_POOL_DAILY = [
    {
        "id": "d_loot_items",
        "title": "Добыть {target} предметов",
        "metric": "loot_items",
        "target": (3, 6),
        "reward_points": (12, 22),
        "reward_raidcoins": (4, 8),
    },
    {
        "id": "d_kills",
        "title": "Уничтожить {target} ARC",
        "metric": "kills",
        "target": (2, 4),
        "reward_points": (14, 26),
        "reward_raidcoins": (0, 0),
    },
    {
        "id": "d_extracts",
        "title": "Эвакуироваться {target} раз(а)",
        "metric": "extracts",
        "target": (1, 3),
        "reward_points": (16, 28),
        "reward_raidcoins": (4, 8),
    },
    {
        "id": "d_sell_value",
        "title": "Продать на {target} RC",
        "metric": "sell_value",
        "target": (80, 160),
        "reward_points": (10, 18),
        "reward_raidcoins": (6, 12),
    },
    {
        "id": "d_raids",
        "title": "Войти в рейд {target} раз(а)",
        "metric": "raids_started",
        "target": (2, 4),
        "reward_points": (10, 20),
        "reward_raidcoins": (4, 8),
    },
]

QUEST_POOL_WEEKLY = [
    {
        "id": "w_loot_value",
        "title": "Налутать ценности на {target}",
        "metric": "loot_value",
        "target": (420, 780),
        "reward_points": (80, 140),
        "reward_raidcoins": (20, 35),
    },
    {
        "id": "w_extracts",
        "title": "Эвакуироваться {target} раз(а)",
        "metric": "extracts",
        "target": (6, 10),
        "reward_points": (90, 150),
        "reward_raidcoins": (20, 35),
    },
    {
        "id": "w_raids",
        "title": "Провести {target} рейдов",
        "metric": "raids_started",
        "target": (10, 16),
        "reward_points": (70, 130),
        "reward_raidcoins": (20, 30),
    },
]

STORY_EVENTS = {
    "signal": {
        "text": "📡 Слабый ARC-сигнал пробивается сквозь помехи. Он ведёт глубже в сектор.",
        "choices": [
            {
                "id": "scan",
                "label": "Сканировать",
                "greed": 6,
                "evac_bonus": 0.05,
                "next": "signal_trace",
            },
            {
                "id": "ignore",
                "label": "Игнорировать",
                "greed": -3,
            },
        ],
    },
    "signal_trace": {
        "text": "📶 Источник сигнала — повреждённый ретранслятор. Внутри могут быть данные.",
        "choices": [
            {
                "id": "loot",
                "label": "Извлечь модуль",
                "loot_rolls": 1,
                "greed": 4,
            },
            {
                "id": "cut",
                "label": "Отключить и уйти",
                "greed": -4,
            },
        ],
    },
    "quiet_zone": {
        "text": "🌫️ Тихая зона. Здесь ARC почти не слышны. Можно успокоиться.",
        "choices": [
            {
                "id": "rest",
                "label": "Переждать",
                "greed": -8,
                "heal": 8,
            },
            {
                "id": "move",
                "label": "Не терять темп",
                "greed": 3,
            },
        ],
    },
}


@dataclass
class TgUser:
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class InitDataRequest(BaseModel):
    init_data: str
    chat_id: Optional[int] = None
    thread_id: Optional[int] = None
    login_data: Optional[Dict[str, Any]] = None
    auth_token: Optional[str] = None


class RaidActionRequest(InitDataRequest):
    action: str
    session_id: Optional[str] = None


class PaginationRequest(InitDataRequest):
    page: int = 1
    sort: Optional[str] = None


class StorageUpgradeRequest(InitDataRequest):
    pass


class SellConfirmRequest(InitDataRequest):
    item_id: str
    qty: Optional[int] = None
    qty_raw: Optional[str] = None
    page: int = 1
    sort: Optional[str] = None


class ShopBuyRequest(InitDataRequest):
    kind: str
    item_id: Optional[str] = None
    recipe_id: Optional[str] = None


class CraftMakeRequest(InitDataRequest):
    recipe_id: str


class LoadoutOptionsRequest(PaginationRequest):
    equip_type: str


class LoadoutSetRequest(InitDataRequest):
    equip_type: str
    item_id: Optional[str] = None


class BlueprintListRequest(PaginationRequest):
    pass


class BlueprintStudyRequest(InitDataRequest):
    item_id: str


class DailyCaseOpenRequest(InitDataRequest):
    pass


class RatingRequest(InitDataRequest):
    limit: Optional[int] = None


class QuestClaimRequest(InitDataRequest):
    kind: str
    quest_id: str


class MarketStateRequest(PaginationRequest):
    items_page: int = 1
    items_sort: Optional[str] = None


class MarketListRequest(InitDataRequest):
    item_id: str
    qty_raw: Optional[str] = None
    price: int


class MarketBuyRequest(InitDataRequest):
    listing_id: int


class MarketCancelRequest(InitDataRequest):
    listing_id: int


class AdminUpdateRequest(InitDataRequest):
    event_base: Optional[float] = None
    event_greed_mult: Optional[float] = None
    evac_base: Optional[float] = None
    evac_greed_penalty: Optional[float] = None
    warehouse_goal: Optional[int] = None
    event_week_goal: Optional[int] = None
    daily_sell_raidcoin_cap: Optional[int] = None
    daily_sell_count_cap: Optional[int] = None
    market_listing_cap: Optional[int] = None
    season_reward_top1: Optional[int] = None
    season_reward_top2: Optional[int] = None
    season_reward_top3: Optional[int] = None


class AuthRegisterRequest(BaseModel):
    email: str
    nickname: str
    password: str


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class AuthTelegramRequest(BaseModel):
    login_data: Dict[str, Any]


@app.on_event("startup")
async def startup() -> None:
    await db.connect()
    await db.init()
    data._loot_index = {item["id"]: item for item in data.loot}


@app.on_event("shutdown")
async def shutdown() -> None:
    await db.close()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "bot_username": WEBAPP_BOT_USERNAME,
            "default_chat_id": DEFAULT_CHAT_ID,
            "default_thread_id": DEFAULT_THREAD_ID,
        },
    )


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    return {"status": "ok"}


def _validate_init_data(init_data: str) -> Optional[Dict[str, str]]:
    if not init_data or not BOT_TOKEN:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(
        BOT_TOKEN.encode("utf-8"),
        b"WebAppData",
        hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        secret, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if calculated_hash != received_hash:
        return None
    return pairs


def _validate_init_data_debug(init_data: str) -> tuple[Optional[Dict[str, str]], str]:
    if not BOT_TOKEN:
        return None, "BOT_TOKEN ?? ?????."
    if not init_data:
        return None, "init_data ????."
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None, "?? ??????? ????????? init_data."
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None, "hash ???????????."
    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(
        BOT_TOKEN.encode("utf-8"),
        b"WebAppData",
        hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        secret, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if calculated_hash != received_hash:
        return None, "hash ?? ?????????."
    return pairs, "ok"


def _parse_user(pairs: Dict[str, str]) -> Optional[TgUser]:
    raw_user = pairs.get("user")
    if not raw_user:
        return None
    try:
        payload = json.loads(raw_user)
    except json.JSONDecodeError:
        return None
    user_id = payload.get("id")
    if not user_id:
        return None
    return TgUser(
        id=int(user_id),
        username=payload.get("username"),
        first_name=payload.get("first_name"),
        last_name=payload.get("last_name"),
    )


def _normalize_login_data(login_data: Any) -> Optional[Dict[str, str]]:
    if not login_data:
        return None
    if isinstance(login_data, str):
        try:
            raw = json.loads(login_data)
            if isinstance(raw, dict):
                login_data = raw
        except json.JSONDecodeError:
            try:
                login_data = dict(parse_qsl(login_data, strict_parsing=True))
            except ValueError:
                return None
    if not isinstance(login_data, dict):
        return None
    normalized: Dict[str, str] = {}
    for key, value in login_data.items():
        if value is None:
            continue
        normalized[str(key)] = str(value)
    return normalized


def _validate_login_data(login_data: Any) -> Optional[Dict[str, str]]:
    if not BOT_TOKEN:
        return None
    data = _normalize_login_data(login_data)
    if not data:
        return None
    received_hash = data.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = BOT_TOKEN.encode("utf-8")
    calculated_hash = hmac.new(
        secret, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if calculated_hash != received_hash:
        return None
    auth_date = data.get("auth_date")
    if auth_date:
        try:
            auth_ts = int(auth_date)
            if WEBAPP_AUTH_MAX_AGE > 0:
                if abs(time.time() - auth_ts) > WEBAPP_AUTH_MAX_AGE:
                    return None
        except ValueError:
            return None
    return data


def _validate_login_data_debug(login_data: Any) -> tuple[Optional[Dict[str, str]], str]:
    if not BOT_TOKEN:
        return None, "BOT_TOKEN не задан."
    data = _normalize_login_data(login_data)
    if not data:
        return None, "login_data пуст."
    received_hash = data.pop("hash", None)
    if not received_hash:
        return None, "hash отсутствует."
    data_check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = BOT_TOKEN.encode("utf-8")
    calculated_hash = hmac.new(
        secret, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if calculated_hash != received_hash:
        return None, "hash не совпадает."
    auth_date = data.get("auth_date")
    if auth_date:
        try:
            auth_ts = int(auth_date)
            if WEBAPP_AUTH_MAX_AGE > 0:
                if abs(time.time() - auth_ts) > WEBAPP_AUTH_MAX_AGE:
                    return None, "auth_date истек."
        except ValueError:
            return None, "auth_date некорректный."
    return data, "ok"


def _parse_login_user(data: Dict[str, str]) -> Optional[TgUser]:
    user_id = data.get("id")
    if not user_id:
        return None
    return TgUser(
        id=int(user_id),
        username=data.get("username"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
    )


def _display_name(user: Optional[Dict[str, Any]]) -> str:
    if not user:
        return "Игрок"
    nickname = user.get("nickname")
    if nickname:
        return nickname
    first = user.get("first_name")
    last = user.get("last_name")
    if first or last:
        return " ".join(p for p in (first, last) if p)
    return user.get("username") or "Игрок"


def _is_admin_email(email: Optional[str]) -> bool:
    if not email:
        return False
    return email.strip().lower() in ADMIN_EMAILS


def _daily_period(target_date: date) -> str:
    return target_date.isoformat()


def _weekly_period(target_date: date) -> str:
    year, week, _ = target_date.isocalendar()
    return f"{year}-W{week:02d}"


def _roll_quest(quest_def: Dict[str, Any]) -> Dict[str, Any]:
    target_min, target_max = quest_def["target"]
    target = random.randint(target_min, target_max)
    reward_points = 0
    reward_raidcoins = 0
    if quest_def.get("reward_points"):
        rp_min, rp_max = quest_def["reward_points"]
        reward_points = random.randint(rp_min, rp_max) if rp_max > 0 else 0
    if quest_def.get("reward_raidcoins"):
        rc_min, rc_max = quest_def["reward_raidcoins"]
        reward_raidcoins = random.randint(rc_min, rc_max) if rc_max > 0 else 0
    return {
        "quest_id": quest_def["id"],
        "title": quest_def["title"].format(target=target),
        "metric": quest_def["metric"],
        "target": target,
        "reward_points": reward_points,
        "reward_raidcoins": reward_raidcoins,
    }


async def ensure_player_quests(player_id: int) -> tuple[str, str]:
    today = date.today()
    daily_period = _daily_period(today)
    weekly_period = _weekly_period(today)
    existing_daily = await db.get_player_quests(player_id, "daily", daily_period)
    if not existing_daily:
        picks = random.sample(
            QUEST_POOL_DAILY, min(QUEST_DAILY_COUNT, len(QUEST_POOL_DAILY))
        )
        for quest_def in picks:
            quest = _roll_quest(quest_def)
            quest.update(
                {
                    "player_id": player_id,
                    "kind": "daily",
                    "period": daily_period,
                }
            )
            await db.upsert_player_quest(quest)
    existing_weekly = await db.get_player_quests(player_id, "weekly", weekly_period)
    if not existing_weekly:
        picks = random.sample(
            QUEST_POOL_WEEKLY, min(QUEST_WEEKLY_COUNT, len(QUEST_POOL_WEEKLY))
        )
        for quest_def in picks:
            quest = _roll_quest(quest_def)
            quest.update(
                {
                    "player_id": player_id,
                    "kind": "weekly",
                    "period": weekly_period,
                }
            )
            await db.upsert_player_quest(quest)
    return daily_period, weekly_period


async def build_quests_payload(player_id: int) -> Dict[str, Any]:
    daily_period, weekly_period = await ensure_player_quests(player_id)
    daily = await db.get_player_quests(player_id, "daily", daily_period)
    weekly = await db.get_player_quests(player_id, "weekly", weekly_period)
    return {
        "daily_period": daily_period,
        "weekly_period": weekly_period,
        "daily": daily,
        "weekly": weekly,
    }


async def update_quest_progress(player_id: int, metrics: Dict[str, int]) -> None:
    if not metrics:
        return
    daily_period, weekly_period = await ensure_player_quests(player_id)
    for kind, period in (("daily", daily_period), ("weekly", weekly_period)):
        quests = await db.get_player_quests(player_id, kind, period)
        for quest in quests:
            if quest.get("claimed"):
                continue
            metric = quest.get("metric")
            delta = metrics.get(metric, 0)
            if delta <= 0:
                continue
            progress = int(quest.get("progress", 0)) + int(delta)
            target = int(quest.get("target", 0))
            completed = 1 if progress >= target else 0
            progress = min(progress, target) if target > 0 else progress
            await db.update_player_quest(
                player_id, kind, period, quest["quest_id"], progress, completed
            )


async def get_web_user_info(player_id: int) -> Optional[Dict[str, Any]]:
    return await db.get_web_user_by_player(player_id)


async def check_daily_sell_caps(
    player_id: int, chat_id: int, raidcoins_delta: int, sells_delta: int
) -> tuple[bool, str]:
    settings = await db.ensure_settings(chat_id)
    cap_rc = int(settings.get("daily_sell_raidcoin_cap", DEFAULTS.daily_sell_raidcoin_cap))
    cap_sell = int(settings.get("daily_sell_count_cap", DEFAULTS.daily_sell_count_cap))
    today = date.today().isoformat()
    stats = await db.get_daily_stats(player_id, today)
    if raidcoins_delta > 0 and stats["raidcoins_earned"] + raidcoins_delta > cap_rc:
        return False, f"Дневной лимит RC достигнут ({cap_rc})."
    if sells_delta > 0 and stats["sells_count"] + sells_delta > cap_sell:
        return False, f"Дневной лимит продаж достигнут ({cap_sell})."
    return True, ""


def _previous_month(today: date) -> date:
    if today.month == 1:
        return date(today.year - 1, 12, 1)
    return date(today.year, today.month - 1, 1)


async def finish_previous_season_if_needed(chat_id: int) -> Optional[Dict[str, Any]]:
    prev = _previous_month(date.today())
    season_id, start_date, end_date = db._current_season_bounds(prev)
    season = await db.get_season(season_id)
    if not season:
        return None
    if season.get("closed"):
        return season
    try:
        end_dt = date.fromisoformat(season["end_date"])
    except Exception:
        end_dt = date.today()
    if date.today() <= end_dt:
        return season
    top = await db.get_season_top(season_id, limit=3)
    settings = await db.ensure_settings(chat_id)
    rewards = {
        1: int(settings.get("season_reward_top1", DEFAULTS.season_reward_top1)),
        2: int(settings.get("season_reward_top2", DEFAULTS.season_reward_top2)),
        3: int(settings.get("season_reward_top3", DEFAULTS.season_reward_top3)),
    }
    for idx, row in enumerate(top, start=1):
        reward = rewards.get(idx, 0)
        if reward > 0:
            await db.adjust_raidcoins(row["player_id"], reward)
    await db.close_season(season_id, rewarded=True)
    return await db.get_season(season_id)


def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    iterations = 120_000
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iters)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    ).hex()
    return hmac.compare_digest(candidate, digest)


def _create_token(player_id: int) -> str:
    if not WEBAPP_AUTH_SECRET:
        raise HTTPException(status_code=500, detail="auth secret not configured")
    payload = {
        "pid": player_id,
        "exp": int(time.time()) + max(0, WEBAPP_TOKEN_TTL),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64 = (
        base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
    )
    sig = hmac.new(
        WEBAPP_AUTH_SECRET.encode("utf-8"), b64.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{b64}.{sig}"


def _verify_token(token: str) -> Optional[int]:
    if not token or not WEBAPP_AUTH_SECRET:
        return None
    try:
        b64, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(
        WEBAPP_AUTH_SECRET.encode("utf-8"), b64.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    padded = b64 + "=" * (-len(b64) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    try:
        exp = int(payload.get("exp", 0))
        pid = int(payload.get("pid", 0))
    except (TypeError, ValueError):
        return None
    if exp and time.time() > exp:
        return None
    return pid if pid > 0 else None


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _is_valid_email(email: str) -> bool:
    if "@" not in email:
        return False
    name, _, domain = email.partition("@")
    if not name or "." not in domain:
        return False
    return True


async def _authorize(payload: InitDataRequest) -> tuple[TgUser, int]:
    user: Optional[TgUser] = None
    player_id: Optional[int] = None
    if payload.auth_token:
        pid = _verify_token(payload.auth_token)
        if pid:
            player = await db.get_player(pid)
            if player:
                user = TgUser(
                    id=int(player.get("tg_id") or pid),
                    username=player.get("username"),
                    first_name=player.get("first_name"),
                    last_name=player.get("last_name"),
                )
                player_id = pid
    if payload.init_data:
        pairs, reason = _validate_init_data_debug(payload.init_data)
        if pairs:
            user = _parse_user(pairs)
    if not user and payload.login_data:
        login_pairs = _validate_login_data(payload.login_data)
        if login_pairs:
            user = _parse_login_user(login_pairs)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    if player_id is None:
        player_id = await db.upsert_player(user)
    return user, player_id


def _require_chat_id(payload: InitDataRequest) -> int:
    return int(payload.chat_id) if payload.chat_id is not None else DEFAULT_CHAT_ID


def _require_thread_id(payload: InitDataRequest) -> int:
    return int(payload.thread_id) if payload.thread_id is not None else DEFAULT_THREAD_ID


def cooldown_remaining(session: Dict[str, Any], action: str, now: float) -> int:
    cooldowns = session.get("cooldowns") or {}
    until = cooldowns.get(action, 0)
    return max(0, int(until - now + 0.999))


def set_cooldown(session: Dict[str, Any], action: str, now: float) -> None:
    duration = ACTION_COOLDOWNS.get(action, 0)
    if duration <= 0:
        return
    cooldowns = session.get("cooldowns") or {}
    cooldowns[action] = now + duration
    session["cooldowns"] = cooldowns


def add_greed(session: Dict[str, Any], amount: int) -> int:
    mult = float(session.get("greed_mult", 1.0))
    session["greed"] += int(round(amount * max(0.1, mult)))
    return session["greed"]


def effective_evac_bonus(session: Dict[str, Any]) -> float:
    return float(session.get("evac_bonus", 0)) - float(session.get("evac_penalty", 0))


def apply_hard_loot_bonus(session: Dict[str, Any], items: list[Dict[str, Any]]) -> bool:
    if not session.get("hard_mode"):
        return False
    if not items:
        return False
    if random.random() >= DEFAULTS.hard_raid_loot_bonus_chance:
        return False
    items.append(data.roll_loot())
    return True


def apply_event(
    session: dict[str, Any],
    event: dict[str, Any],
) -> tuple[dict[str, Any], str, bool, list[dict[str, Any]], int]:
    kind = event["kind"]
    if kind == "ambush":
        enemy = data.roll_enemy()
        enemy["hp_current"] = enemy["hp"]
        session["enemy"] = enemy
        session["status"] = "combat"
        return (
            session,
            f"⚠️ Засада! Сканер зафиксировал {enemy['name']} (HP {enemy['hp']}). Бой неизбежен.",
            False,
            [],
            0,
        )
    if kind == "storm":
        damage = int(event.get("damage", 15))
        session["hp"] = max(0, session["hp"] - damage)
        return (
            session,
            f"🌪️ Буря ARC режет связь! Потеряно {damage} HP.",
            session["hp"] <= 0,
            [],
            0,
        )
    if kind == "evac":
        bonus = float(event.get("bonus", 0.15))
        session["evac_bonus"] = min(0.3, session["evac_bonus"] + bonus)
        return (
            session,
            "📡 Эвакуационный коридор открыт. Шанс эвакуации повышен.",
            False,
            [],
            0,
        )
    if kind == "quiet":
        delta = int(event.get("greed_reduce", 12))
        session["greed"] = max(0, session["greed"] - delta)
        return (
            session,
            f"🧘 Тихая зона глушит шум: алчность -{delta}.",
            False,
            [],
            0,
        )
    if kind == "cache":
        rolls = int(event.get("loot_rolls", 2))
        items = [data.roll_loot() for _ in range(rolls)]
        return (session, "📦 Тайник найден! Внутри несколько предметов.", False, items, 0)
    if kind == "evac_window":
        bonus = float(event.get("bonus", 0.15))
        session["evac_bonus"] = min(0.3, session["evac_bonus"] + bonus)
        cost = random.randint(DEFAULTS.evac_event_cost_min, DEFAULTS.evac_event_cost_max)
        return (
            session,
            f"🚨 Окно эвакуации открыто! Шанс эвакуации повышен. Цена: -{cost} очк.",
            False,
            [],
            cost,
        )
    return session, "Тишина…", False, [], 0

def roll_story_event() -> Dict[str, Any]:
    key = random.choice(list(STORY_EVENTS.keys()))
    event = dict(STORY_EVENTS[key])
    event["id"] = key
    return event


def build_story_choice_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event_id": event.get("id"),
        "text": event.get("text"),
        "choices": [
            {"id": choice["id"], "label": choice["label"]}
            for choice in event.get("choices", [])
        ],
    }


def apply_story_choice(
    session: Dict[str, Any],
    choice: Dict[str, Any],
) -> tuple[Dict[str, Any], str, list[Dict[str, Any]]]:
    notes = []
    delta_greed = int(choice.get("greed", 0))
    if delta_greed > 0:
        add_greed(session, delta_greed)
        notes.append(f"Алчность +{delta_greed}.")
    elif delta_greed < 0:
        session["greed"] = max(0, session.get("greed", 0) + delta_greed)
        notes.append(f"Алчность {delta_greed}.")

    bonus = float(choice.get("evac_bonus", 0))
    if bonus:
        before = session.get("evac_bonus", 0.0)
        session["evac_bonus"] = min(0.3, before + bonus)
        notes.append(f"Эвак +{int(round(bonus * 100))}%.")

    heal = int(choice.get("heal", 0))
    if heal > 0:
        session["hp"] = min(session["max_hp"], session["hp"] + heal)
        notes.append(f"HP +{heal}.")

    items: list[Dict[str, Any]] = []
    rolls = int(choice.get("loot_rolls", 0))
    if rolls > 0:
        items = [data.roll_loot() for _ in range(rolls)]
        notes.append("Найдены предметы.")

    return session, " ".join(notes).strip(), items



def build_pending_item(session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    pending = session.get("pending_loot") or []
    if not pending:
        return None
    return data.get_item(pending[0])


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def shop_tax_multiplier(purchases_today: int) -> float:
    return 1.0 + purchases_today * DEFAULTS.shop_tax_step


def storage_upgrade_cost(current_limit: int) -> int:
    base = DEFAULTS.storage_limit
    step = DEFAULTS.storage_upgrade_step
    level = max(0, (current_limit - base) // step)
    return DEFAULTS.storage_upgrade_base_cost + level * DEFAULTS.storage_upgrade_cost_step


def can_upgrade_storage(current_limit: int) -> bool:
    return current_limit + DEFAULTS.storage_upgrade_step <= DEFAULTS.storage_upgrade_max


def is_sellable(item: Optional[Dict[str, Any]]) -> bool:
    if not item:
        return False
    if item.get("non_sellable"):
        return False
    if item.get("type") in ("armor", "weapon"):
        return False
    return True


def sell_price(item: Dict[str, Any], qty: int) -> int:
    base = int(item.get("sell_value", item.get("value", 0)))
    return max(0, int(round(base * DEFAULTS.sell_mult * qty)))


def blueprint_output_id(item_id: str) -> str:
    base = item_id[:-10] if item_id.endswith("_blueprint") else item_id
    if data.get_item(base):
        return base
    alt = f"{base}_i"
    if data.get_item(alt):
        return alt
    return base


def recipe_id_for_blueprint(item_id: str) -> Optional[str]:
    output_id = blueprint_output_id(item_id)
    for recipe in data.list_recipes():
        out = recipe.get("output", {})
        if out.get("item_id") == output_id:
            return recipe.get("id")
    return None


async def get_available_recipes(player_id: int) -> list[Dict[str, Any]]:
    unlocked = await db.get_unlocked_recipes(player_id)
    return [
        recipe
        for recipe in data.list_recipes()
        if recipe.get("id") in BASE_RECIPE_IDS or recipe.get("id") in unlocked
    ]


def format_ingredients(ingredients: Dict[str, Any]) -> str:
    parts = []
    for item_id, qty in ingredients.items():
        item = data.get_item(item_id)
        name = item["name"] if item else item_id
        parts.append(f"{name} x{qty}")
    return ", ".join(parts)


def build_storage_entries(
    items: Dict[str, int],
    sort_key: str,
    page: int,
    page_size: int,
) -> tuple[list[Dict[str, Any]], int, int, str]:
    sort_key = normalize_sort(sort_key)
    entries: list[Dict[str, Any]] = []
    for item_id, qty in items.items():
        if qty <= 0:
            continue
        item = data.get_item(item_id) or {}
        rarity = item.get("rarity", "common")
        entries.append(
            {
                "id": item_id,
                "name": item.get("name", item_id),
                "qty": qty,
                "rarity": rarity,
                "rarity_rank": RARITY_ORDER.get(rarity, 1),
                "value": int(item.get("value", 0)),
                "emoji": item.get("emoji") or rarity_emoji(rarity),
                "type": item.get("type"),
                "blueprint": bool(item.get("blueprint") or item.get("type") == "blueprint"),
            }
        )

    if sort_key == "value":
        entries.sort(
            key=lambda e: (-e["value"], -e["rarity_rank"], e["name"].lower())
        )
    elif sort_key == "name":
        entries.sort(key=lambda e: e["name"].lower())
    elif sort_key == "qty":
        entries.sort(
            key=lambda e: (-e["qty"], -e["rarity_rank"], e["name"].lower())
        )
    else:
        entries.sort(
            key=lambda e: (-e["rarity_rank"], -e["value"], e["name"].lower())
        )

    total_entries = len(entries)
    total_pages = max(1, math.ceil(total_entries / page_size)) if page_size > 0 else 1
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_entries = entries[start:end]
    return page_entries, page, total_pages, sort_key


def build_sell_entries(
    items: Dict[str, int],
    sort_key: str,
    page: int,
    page_size: int,
) -> tuple[list[Dict[str, Any]], int, int, str]:
    sort_key = normalize_sort(sort_key)
    entries: list[Dict[str, Any]] = []
    for item_id, qty in items.items():
        if qty <= 0:
            continue
        item = data.get_item(item_id)
        if not is_sellable(item):
            continue
        rarity = item.get("rarity", "common") if item else "common"
        entries.append(
            {
                "id": item_id,
                "name": item.get("name", item_id) if item else item_id,
                "qty": qty,
                "rarity": rarity,
                "rarity_rank": RARITY_ORDER.get(rarity, 1),
                "value": int(item.get("value", 0)) if item else 0,
                "emoji": item.get("emoji") if item else None,
            }
        )

    if sort_key == "value":
        entries.sort(
            key=lambda e: (-e["value"], -e["rarity_rank"], e["name"].lower())
        )
    elif sort_key == "name":
        entries.sort(key=lambda e: e["name"].lower())
    elif sort_key == "qty":
        entries.sort(
            key=lambda e: (-e["qty"], -e["rarity_rank"], e["name"].lower())
        )
    else:
        entries.sort(
            key=lambda e: (-e["rarity_rank"], -e["value"], e["name"].lower())
        )

    total_entries = len(entries)
    total_pages = max(1, math.ceil(total_entries / page_size)) if page_size > 0 else 1
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    page_entries = entries[start:end]
    return page_entries, page, total_pages, sort_key


def collect_equip_options(
    items: Dict[str, int],
    equip_type: str,
    page: int,
) -> tuple[list[Dict[str, Any]], int, int]:
    type_map = {
        "armor": "armor",
        "weapon": "weapon",
        "medkit": "consumable",
        "chip": "augment",
    }
    item_type = type_map.get(equip_type)
    candidates: list[Dict[str, Any]] = []
    for item_id, qty in items.items():
        if qty <= 0:
            continue
        item = data.get_item(item_id)
        if not item:
            continue
        if item.get("type") != item_type:
            continue
        if equip_type == "medkit":
            if not (item.get("heal") or item.get("evac_bonus")):
                continue
        if equip_type == "chip":
            if not (
                item.get("greed_mult")
                or item.get("evac_bonus")
                or item.get("damage_bonus")
            ):
                continue
        candidates.append(
            {
                "id": item_id,
                "qty": qty,
                "name": item.get("name", item_id),
                "emoji": item.get("emoji") or rarity_emoji(item.get("rarity", "common")),
                "value": int(item.get("value", 0)),
            }
        )

    candidates.sort(key=lambda x: (-x["value"], x["name"].lower()))
    total = len(candidates)
    total_pages = max(1, math.ceil(total / EQUIP_PAGE_SIZE))
    page = max(1, min(page, total_pages))
    start = (page - 1) * EQUIP_PAGE_SIZE
    end = start + EQUIP_PAGE_SIZE
    return candidates[start:end], page, total_pages


def is_case_rare(item: Dict[str, Any]) -> bool:
    if item.get("blueprint") or item.get("type") == "blueprint":
        return True
    return item.get("rarity") in CASE_GUARANTEE_RARITIES


def build_case_pool() -> tuple[list[Dict[str, Any]], list[float]]:
    pool = [item for item in data.loot if item.get("type") != "junk"]
    weights = [
        max(0.01, float(item.get("weight", 1)))
        * CASE_RARITY_WEIGHT.get(item.get("rarity", "common"), 1)
        for item in pool
    ]
    return pool, weights


def roll_daily_case_items(pity: int) -> tuple[list[Dict[str, Any]], int]:
    pool, weights = build_case_pool()
    if not pool:
        return [], pity

    drops: list[Dict[str, Any]] = []
    guaranteed = pity >= max(0, CASE_PITY_DAYS - 1)
    if guaranteed:
        rare_pool = [item for item in pool if is_case_rare(item)]
        if rare_pool:
            rare_weights = [
                max(0.01, float(item.get("weight", 1)))
                * CASE_RARITY_WEIGHT.get(item.get("rarity", "common"), 1)
                for item in rare_pool
            ]
            drops.append(random.choices(rare_pool, weights=rare_weights, k=1)[0])

    while len(drops) < CASE_ITEMS_COUNT:
        drops.append(random.choices(pool, weights=weights, k=1)[0])

    hit_rare = any(is_case_rare(item) for item in drops)
    new_pity = 0 if hit_rare else pity + 1
    return drops, new_pity


def _shop_item_price(item: Dict[str, Any]) -> int:
    rarity = item.get("rarity", "rare")
    mult = SHOP_RARITY_MULT.get(rarity, 3.0)
    min_price = SHOP_RARITY_MIN.get(rarity, 120)
    base = int(round(int(item.get("value", 10)) * mult))
    jitter = random.uniform(0.9, 1.1)
    return max(min_price, int(round(base * jitter)))


def _pick_shop_items() -> list[Dict[str, Any]]:
    picks: list[Dict[str, Any]] = []

    normal_pool = [
        item
        for item in data.loot
        if item.get("rarity") in SHOP_RARITY_WEIGHT
        and item.get("type") not in ("junk", "blueprint")
    ]
    if normal_pool:
        normal_weights = [
            max(1, int(item.get("weight", 1)))
            * SHOP_RARITY_WEIGHT.get(item.get("rarity", "rare"), 1)
            for item in normal_pool
        ]
        count = min(SHOP_DAILY_ITEM_COUNT, len(normal_pool))
        for _ in range(count):
            choice = random.choices(normal_pool, weights=normal_weights, k=1)[0]
            picks.append(choice)
            idx = normal_pool.index(choice)
            normal_pool.pop(idx)
            normal_weights.pop(idx)

    blueprint_pool = [item for item in data.loot if item.get("type") == "blueprint"]
    if blueprint_pool:
        blueprint_weights = [
            max(1, int(item.get("weight", 1)))
            * SHOP_BLUEPRINT_WEIGHT.get(item.get("rarity", "common"), 1)
            for item in blueprint_pool
        ]
        count = min(SHOP_DAILY_BLUEPRINT_COUNT, len(blueprint_pool))
        for _ in range(count):
            choice = random.choices(blueprint_pool, weights=blueprint_weights, k=1)[0]
            picks.append(choice)
            idx = blueprint_pool.index(choice)
            blueprint_pool.pop(idx)
            blueprint_weights.pop(idx)

    return picks


def generate_shop_offers() -> Dict[str, Any]:
    items = []
    for item in _pick_shop_items():
        items.append(
            {
                "item_id": item["id"],
                "price": _shop_item_price(item),
            }
        )
    recipe_offer = None
    recipe_pool = [r for r in data.list_recipes() if r.get("id") not in BASE_RECIPE_IDS]
    if recipe_pool:
        recipe = random.choice(recipe_pool)
        out_id = recipe["output"]["item_id"]
        out_item = data.get_item(out_id)
        rarity = out_item.get("rarity", "epic") if out_item else "epic"
        mult = SHOP_RARITY_MULT.get(rarity, 3.5) + 0.5
        min_price = SHOP_RARITY_MIN.get(rarity, 160)
        base_value = int(out_item.get("value", 60)) if out_item else 60
        price = max(min_price, int(round(base_value * mult)))
        recipe_offer = {"recipe_id": recipe["id"], "price": price}
    return {"items": items, "recipe": recipe_offer, "date": date.today().isoformat()}


async def get_daily_shop(chat_id: int) -> Dict[str, Any]:
    settings = await db.ensure_settings(chat_id)
    today = date.today().isoformat()
    offers = None
    if settings.get("shop_date") == today and settings.get("shop_offers_json"):
        try:
            offers = json.loads(settings["shop_offers_json"])
        except Exception:
            offers = None
    if not offers:
        offers = generate_shop_offers()
        await db.update_settings(
            chat_id,
            shop_date=today,
            shop_offers_json=json.dumps(offers, ensure_ascii=False),
        )
    return offers


def pick_daily_order_item() -> Optional[Dict[str, Any]]:
    pool = []
    weights = []
    for item in data.loot:
        if not is_sellable(item):
            continue
        if item.get("rarity") == "junk":
            continue
        pool.append(item)
        weights.append(max(1, int(item.get("weight", 1))))
    if not pool:
        return None
    return random.choices(pool, weights=weights, k=1)[0]


def build_daily_order_params(item: Dict[str, Any]) -> tuple[int, int, int]:
    rarity = item.get("rarity", "common")
    target_mult = ORDER_TARGET_MULT.get(rarity, 1.0)
    reward_mult = ORDER_REWARD_MULT.get(rarity, 1.0)
    target = max(1, int(round(DEFAULTS.daily_order_target * target_mult)))
    reward = max(1, int(round(DEFAULTS.daily_order_reward * reward_mult)))
    bonus = max(0, int(round(DEFAULTS.daily_order_bonus * reward_mult)))
    return target, reward, bonus


async def get_daily_order(chat_id: int) -> Dict[str, Any]:
    settings = await db.ensure_settings(chat_id)
    today = date.today().isoformat()
    if settings.get("order_date") == today and settings.get("order_item_id"):
        return settings
    item = pick_daily_order_item()
    if not item:
        return settings
    target, reward, bonus = build_daily_order_params(item)
    settings = await db.update_settings(
        chat_id,
        order_date=today,
        order_item_id=item["id"],
        order_target=target,
        order_reward=reward,
        order_bonus=bonus,
    )
    return settings


async def get_active_event_meta(chat_id: int) -> Optional[Dict[str, Any]]:
    settings = await db.ensure_settings(chat_id)
    if not settings.get("event_week_active"):
        return None
    end_date = parse_iso_date(settings.get("event_week_end"))
    if not end_date or date.today() > end_date:
        await db.update_settings(chat_id, event_week_active=0)
        return None
    event_id = settings.get("event_week_id") or settings.get("event_week_start")
    if not event_id:
        await db.update_settings(chat_id, event_week_active=0)
        return None
    if not settings.get("event_week_id"):
        await db.update_settings(chat_id, event_week_id=str(event_id))
    return {
        "id": str(event_id),
        "start": settings.get("event_week_start"),
        "end": settings.get("event_week_end"),
        "goal": int(settings.get("event_week_goal") or DEFAULTS.event_week_goal),
    }


async def clear_lost_loadout_items(
    player_id: int, armor_id: Optional[str] = None, weapon_id: Optional[str] = None
) -> None:
    if not armor_id and not weapon_id:
        return
    loadout = await db.get_loadout(player_id)
    updates: Dict[str, Optional[str]] = {}
    if armor_id and loadout.get("armor_id") == armor_id:
        updates["armor_id"] = None
    if weapon_id and loadout.get("weapon_id") == weapon_id:
        updates["weapon_id"] = None
    if updates:
        await db.set_loadout(player_id, **updates)


async def handle_death_web(
    session: Dict[str, Any],
    player_id: int,
    reason: str,
) -> Dict[str, Any]:
    stake_lost = int(session.get("entry_fee", 0)) + int(session.get("entry_bonus", 0))
    await clear_lost_loadout_items(
        player_id, session.get("armor_item_id"), session.get("weapon_item_id")
    )
    tokens = await db.get_insurance_tokens(player_id)
    insurance_note = ""
    if tokens > 0 and session["inventory"]:
        storage_used = await db.get_inventory_count(player_id)
        storage_limit = await db.get_storage_limit(player_id)
        if storage_used < storage_limit:
            item_id = pick_random_item(session["inventory"])
            if item_id:
                await db.add_inventory_items(player_id, {item_id: 1})
                await db.adjust_insurance_tokens(player_id, -1)
                insurance_note = f"Страховка сработала: сохранён {item_id}."
        else:
            insurance_note = "Страховка не сработала: хранилище заполнено."
    await db.adjust_rating(
        player_id,
        points=-DEFAULTS.death_penalty,
        deaths=1,
    )
    await db.delete_session(session["id"])
    return {
        "status": "dead",
        "message": f"💀 Поражение. {reason} Ставка сгорела: -{stake_lost}. {insurance_note}".strip(),
    }


async def handle_extract_web(
    session: Dict[str, Any],
    player_id: int,
) -> Dict[str, Any]:
    points = calc_points(session)
    stake_return = int(session.get("entry_fee", 0)) + int(session.get("entry_bonus", 0))
    total_points = points + stake_return
    storage_limit = await db.get_storage_limit(player_id)
    storage_used = await db.get_inventory_count(player_id)

    dropped_armor = None
    dropped_weapon = None
    for item_id in (session.get("armor_item_id"), session.get("weapon_item_id")):
        if not item_id:
            continue
        if storage_used < storage_limit:
            await db.add_inventory_items(player_id, {item_id: 1})
            storage_used += 1
        else:
            if item_id == session.get("armor_item_id"):
                dropped_armor = item_id
            if item_id == session.get("weapon_item_id"):
                dropped_weapon = item_id
    if dropped_armor or dropped_weapon:
        await clear_lost_loadout_items(player_id, dropped_armor, dropped_weapon)

    capacity = max(0, storage_limit - storage_used)
    kept, dropped = select_items_by_capacity(session["inventory"], capacity, data)
    await db.add_inventory_items(player_id, kept)
    await db.adjust_rating(
        player_id,
        points=total_points,
        extracts=1,
        loot_value=session["loot_value"],
        kills=session["kills"],
    )
    await update_quest_progress(player_id, {"extracts": 1})
    await db.delete_session(session["id"])
    saved_count = sum(kept.values())
    dropped_count = sum(dropped.values())
    return {
        "status": "extracted",
        "message": (
            f"✅ Эвакуация успешна! Очки +{points}. "
            f"Лут: {format_loot_summary(session)}. "
            f"Сохранено предметов: {saved_count}, потеряно: {dropped_count}."
        ),
    }


async def build_state(player_id: int, chat_id: Optional[int]) -> Dict[str, Any]:
    rating = await db.get_rating(player_id)
    inventory = await db.get_inventory(player_id)
    storage_used = await db.get_inventory_count(player_id)
    storage_limit = await db.get_storage_limit(player_id)
    resolved_chat_id = chat_id if chat_id is not None else DEFAULT_CHAT_ID
    session = await db.get_active_session(player_id, resolved_chat_id)
    settings = await db.ensure_settings(resolved_chat_id)
    web_user = await get_web_user_info(player_id)
    player = await db.get_player(player_id)
    display_name = _display_name(web_user) if web_user else _display_name(player)
    onboarding_required = bool(web_user and not web_user.get("onboarded"))
    quests = await build_quests_payload(player_id)
    season = await build_season_payload(player_id, resolved_chat_id)
    is_admin = _is_admin_email(web_user.get("email") if web_user else None)

    event = None
    if settings and settings.get("event_week_active"):
        event_id = settings.get("event_week_id") or settings.get("event_week_start")
        totals = await db.get_event_totals(resolved_chat_id, str(event_id))
        event = {
            "id": str(event_id),
            "start": settings.get("event_week_start"),
            "end": settings.get("event_week_end"),
            "goal": int(settings.get("event_week_goal") or 0),
            "value_total": int(totals.get("value_total", 0)),
            "items_total": int(totals.get("items_total", 0)),
        }

    pending_item = build_pending_item(session) if session else None
    cooldowns = {}
    if session:
        now = time.time()
        cooldowns = {a: cooldown_remaining(session, a, now) for a in ACTION_COOLDOWNS}

    return {
        "rating": {
            "points": int(rating.get("points", 0)),
            "raids": int(rating.get("raids", 0)),
            "extracts": int(rating.get("extracts", 0)),
            "deaths": int(rating.get("deaths", 0)),
            "kills": int(rating.get("kills", 0)),
            "loot_value_total": int(rating.get("loot_value_total", 0)),
            "raidcoins": int(rating.get("raidcoins", 0)),
            "storage_limit": int(rating.get("storage_limit", DEFAULTS.storage_limit)),
            "insurance_tokens": int(rating.get("insurance_tokens", 0)),
        },
        "storage": {
            "used": storage_used,
            "limit": storage_limit,
            "items": [
                {
                    "id": item_id,
                    "name": (data.get_item(item_id) or {}).get("name", item_id),
                    "emoji": (data.get_item(item_id) or {}).get("emoji"),
                    "qty": qty,
                }
                for item_id, qty in sorted(inventory.items())
            ],
        },
        "session": session,
        "pending_item": pending_item,
        "cooldowns": cooldowns,
        "can_medkit": has_consumable(session, data) if session else False,
        "event": event,
        "quests": quests,
        "season": season,
        "onboarding_required": onboarding_required,
        "onboarding_steps": ONBOARDING_STEPS if onboarding_required else [],
        "is_admin": is_admin,
        "display_name": display_name,
    }


async def build_storage_payload(
    player_id: int,
    sort_key: Optional[str] = None,
    page: int = 1,
) -> Dict[str, Any]:
    items = await db.get_inventory(player_id)
    rating = await db.get_rating(player_id)
    storage_limit = int(rating.get("storage_limit", DEFAULTS.storage_limit))
    storage_used = sum(items.values())
    total_value = calc_inventory_value(items, data)
    entries, page, total_pages, sort_key = build_storage_entries(
        items, sort_key or "rarity", page, STORAGE_PAGE_SIZE
    )
    can_upgrade = can_upgrade_storage(storage_limit)
    upgrade_cost = storage_upgrade_cost(storage_limit) if can_upgrade else None
    return {
        "items": entries,
        "used": storage_used,
        "limit": storage_limit,
        "total_value": total_value,
        "page": page,
        "total_pages": total_pages,
        "sort": sort_key,
        "sort_label": SORT_LABELS.get(sort_key, sort_key),
        "can_upgrade": can_upgrade,
        "upgrade_cost": upgrade_cost,
        "points": int(rating.get("points", 0)),
        "raidcoins": int(rating.get("raidcoins", 0)),
    }


async def build_sell_payload(
    player_id: int,
    sort_key: Optional[str] = None,
    page: int = 1,
) -> Dict[str, Any]:
    items = await db.get_inventory(player_id)
    rating = await db.get_rating(player_id)
    entries, page, total_pages, sort_key = build_sell_entries(
        items, sort_key or "rarity", page, SELL_PAGE_SIZE
    )
    for entry in entries:
        item = data.get_item(entry["id"]) or {}
        entry["emoji"] = entry.get("emoji") or rarity_emoji(entry["rarity"])
        entry["unit_price"] = sell_price(item, 1) if item else 0
        entry["total_price"] = sell_price(item, entry["qty"]) if item else 0
    return {
        "items": entries,
        "page": page,
        "total_pages": total_pages,
        "sort": sort_key,
        "sort_label": SORT_LABELS.get(sort_key, sort_key),
        "raidcoins": int(rating.get("raidcoins", 0)),
    }


async def build_market_payload(
    player_id: int,
    chat_id: int,
    page: int = 1,
    items_page: int = 1,
    sort_key: Optional[str] = None,
) -> Dict[str, Any]:
    items = await db.get_inventory(player_id)
    rating = await db.get_rating(player_id)
    settings = await db.ensure_settings(chat_id)
    item_entries, items_page, items_total_pages, sort_key = build_sell_entries(
        items, sort_key or "rarity", items_page, MARKET_ITEMS_PAGE_SIZE
    )
    for entry in item_entries:
        item = data.get_item(entry["id"]) or {}
        entry["emoji"] = entry.get("emoji") or rarity_emoji(entry["rarity"])
        entry["unit_price"] = sell_price(item, 1) if item else 0
        entry["total_price"] = sell_price(item, entry["qty"]) if item else 0

    total_listings = await db.get_market_listing_count()
    total_pages = max(1, math.ceil(total_listings / MARKET_PAGE_SIZE))
    page = max(1, min(page, total_pages))
    listings = await db.get_market_listings(
        MARKET_PAGE_SIZE, (page - 1) * MARKET_PAGE_SIZE
    )
    listing_rows = []
    for row in listings:
        item = data.get_item(row["item_id"]) or {}
        name = item.get("name", row["item_id"])
        emoji = item.get("emoji") or rarity_emoji(item.get("rarity", "common"))
        seller_name = (row.get("first_name") or row.get("username") or "Игрок").strip()
        listing_rows.append(
            {
                "id": row["id"],
                "item_id": row["item_id"],
                "name": name,
                "emoji": emoji,
                "qty": int(row.get("qty", 1)),
                "price": int(row.get("price", 0)),
                "seller_id": row.get("seller_id"),
                "seller_name": seller_name,
            }
        )

    my_listings = await db.get_player_market_listings(player_id)
    return {
        "raidcoins": int(rating.get("raidcoins", 0)),
        "listing_cap": int(settings.get("market_listing_cap", DEFAULTS.market_listing_cap)),
        "my_listings": my_listings,
        "items": item_entries,
        "items_page": items_page,
        "items_total_pages": items_total_pages,
        "items_sort": sort_key,
        "items_sort_label": SORT_LABELS.get(sort_key, sort_key),
        "listings": listing_rows,
        "page": page,
        "total_pages": total_pages,
    }


async def build_shop_payload(player_id: int, chat_id: int) -> Dict[str, Any]:
    rating = await db.get_rating(player_id)
    points = int(rating.get("points", 0))
    raidcoins = int(rating.get("raidcoins", 0))
    storage_limit = int(rating.get("storage_limit", DEFAULTS.storage_limit))
    insurance = int(rating.get("insurance_tokens", 0))
    storage_used = await db.get_inventory_count(player_id)
    offers = await get_daily_shop(chat_id)
    today = date.today().isoformat()
    purchases_today = await db.get_daily_shop_purchases(player_id, chat_id, today)
    tax_mult = shop_tax_multiplier(purchases_today)
    tax_pct = int(round((tax_mult - 1.0) * 100))
    medkit_price = int(round(SHOP_PRICES["medkit"] * tax_mult))
    evac_price = int(round(SHOP_PRICES["evac_beacon"] * tax_mult))
    insurance_price = int(round(SHOP_PRICES["insurance"] * tax_mult))
    medkit_item = data.get_item(SHOP_ITEM_IDS["medkit"])
    evac_item = data.get_item(SHOP_ITEM_IDS["evac_beacon"])
    medkit_label = format_item(medkit_item) if medkit_item else "Расходник"
    evac_label = format_item(evac_item) if evac_item else "Эвак-устройство"

    unlocked = await db.get_unlocked_recipes(player_id)
    recipe_offer = offers.get("recipe") if offers else None
    recipe_owned = bool(
        recipe_offer
        and recipe_offer.get("recipe_id") in (unlocked | BASE_RECIPE_IDS)
    )

    offer_items = []
    for offer in offers.get("items", []):
        item = data.get_item(offer["item_id"])
        label = format_item(item) if item else offer["item_id"]
        offer_items.append(
            {
                "item_id": offer["item_id"],
                "label": label,
                "price": int(round(offer["price"] * tax_mult)),
                "currency": "points",
            }
        )

    recipe_payload = None
    if recipe_offer:
        recipe = data.get_recipe(recipe_offer["recipe_id"])
        recipe_payload = {
            "recipe_id": recipe_offer["recipe_id"],
            "name": recipe.get("name") if recipe else recipe_offer["recipe_id"],
            "price": int(round(recipe_offer["price"] * tax_mult)),
            "owned": recipe_owned,
        }

    upgrade_cost = storage_upgrade_cost(storage_limit)
    can_upgrade = can_upgrade_storage(storage_limit)

    return {
        "points": points,
        "raidcoins": raidcoins,
        "storage_limit": storage_limit,
        "insurance": insurance,
        "purchases_today": purchases_today,
        "daily_limit": DEFAULTS.shop_daily_limit,
        "tax_pct": tax_pct,
        "limit_reached": purchases_today >= DEFAULTS.shop_daily_limit,
        "static_items": [
            {
                "kind": "medkit",
                "label": medkit_label,
                "price": medkit_price,
                "currency": "rc",
                "available": storage_used < storage_limit,
            },
            {
                "kind": "evac_beacon",
                "label": evac_label,
                "price": evac_price,
                "currency": "rc",
                "available": storage_used < storage_limit,
            },
            {
                "kind": "insurance",
                "label": "Страховка",
                "price": insurance_price,
                "currency": "rc",
                "available": insurance < DEFAULTS.insurance_max_tokens,
            },
        ],
        "offers": offer_items,
        "recipe_offer": recipe_payload,
        "upgrade": {
            "can_upgrade": can_upgrade,
            "cost": upgrade_cost,
        },
    }


async def build_craft_payload(player_id: int) -> Dict[str, Any]:
    items = await db.get_inventory(player_id)
    storage_limit = await db.get_storage_limit(player_id)
    storage_used = sum(items.values())
    recipes = await get_available_recipes(player_id)
    result = []
    for recipe in recipes:
        output = recipe.get("output", {})
        out_item = data.get_item(output.get("item_id", ""))
        ingredients = []
        for ing_id, qty in recipe.get("ingredients", {}).items():
            ing_item = data.get_item(ing_id) or {}
            ingredients.append(
                {
                    "id": ing_id,
                    "name": ing_item.get("name", ing_id),
                    "emoji": ing_item.get("emoji") or rarity_emoji(ing_item.get("rarity", "common")),
                    "qty": int(qty),
                    "have": int(items.get(ing_id, 0)),
                }
            )
        result.append(
            {
                "id": recipe.get("id"),
                "name": recipe.get("name"),
                "output": {
                    "id": output.get("item_id"),
                    "name": out_item.get("name") if out_item else output.get("item_id"),
                    "emoji": out_item.get("emoji") if out_item else None,
                    "qty": int(output.get("qty", 1)),
                },
                "ingredients": ingredients,
                "craftable": can_craft(items, recipe),
            }
        )
    return {
        "recipes": result,
        "storage_used": storage_used,
        "storage_limit": storage_limit,
    }


async def build_blueprint_payload(
    player_id: int,
    page: int = 1,
) -> Dict[str, Any]:
    items = await db.get_inventory(player_id)
    unlocked = await db.get_unlocked_recipes(player_id)
    entries = []
    unsupported = 0
    for item_id, qty in items.items():
        if qty <= 0:
            continue
        item = data.get_item(item_id)
        if not item:
            continue
        if not (item.get("blueprint") or item.get("type") == "blueprint"):
            continue
        recipe_id = recipe_id_for_blueprint(item_id)
        if not recipe_id:
            unsupported += 1
            continue
        entries.append(
            {
                "id": item_id,
                "name": item.get("name", item_id),
                "qty": qty,
                "rarity": item.get("rarity", "common"),
                "emoji": item.get("emoji") or rarity_emoji(item.get("rarity", "common")),
                "recipe_id": recipe_id,
                "unlocked": recipe_id in unlocked,
            }
        )
    entries.sort(
        key=lambda e: (
            e["unlocked"],
            -RARITY_ORDER.get(e["rarity"], 1),
            e["name"].lower(),
        )
    )
    total = len(entries)
    total_pages = max(1, math.ceil(total / BLUEPRINT_PAGE_SIZE))
    page = max(1, min(page, total_pages))
    start = (page - 1) * BLUEPRINT_PAGE_SIZE
    end = start + BLUEPRINT_PAGE_SIZE
    return {
        "items": entries[start:end],
        "page": page,
        "total_pages": total_pages,
        "unsupported": unsupported,
    }


async def build_loadout_payload(player_id: int) -> Dict[str, Any]:
    loadout = await db.get_loadout(player_id)

    def info(item_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not item_id:
            return None
        item = data.get_item(item_id)
        if not item:
            return {"id": item_id, "name": item_id}
        return {
            "id": item_id,
            "name": item.get("name", item_id),
            "emoji": item.get("emoji") or rarity_emoji(item.get("rarity", "common")),
            "rarity": item.get("rarity", "common"),
        }

    return {
        "armor": info(loadout.get("armor_id")),
        "weapon": info(loadout.get("weapon_id")),
        "medkit": info(loadout.get("medkit_id")),
        "chip": info(loadout.get("chip_id")),
    }


async def build_case_payload(player_id: int, chat_id: int) -> Dict[str, Any]:
    today = date.today().isoformat()
    opened = await db.has_daily_case(player_id, chat_id, today)
    pity = await db.get_case_pity(player_id)
    return {
        "opened": opened,
        "pity": pity,
        "items_count": CASE_ITEMS_COUNT,
        "today": today,
    }


async def build_warehouse_payload(chat_id: int) -> Dict[str, Any]:
    settings = await db.ensure_settings(chat_id)
    items = await db.get_warehouse(chat_id)
    goal = int(settings.get("warehouse_goal", DEFAULTS.warehouse_goal))
    total_items = sum(items.values())
    total_value = 0
    entries = []
    for item_id, qty in items.items():
        if qty <= 0:
            continue
        item = data.get_item(item_id) or {}
        value = int(item.get("value", 0))
        total_value += value * qty
        entries.append(
            {
                "id": item_id,
                "qty": qty,
                "name": item.get("name", item_id),
                "emoji": item.get("emoji") or rarity_emoji(item.get("rarity", "common")),
            }
        )
    entries.sort(key=lambda e: (-e["qty"], e["name"].lower()))
    order = await get_daily_order(chat_id)
    order_payload = None
    if order.get("order_item_id") and order.get("order_target"):
        item = data.get_item(order["order_item_id"]) or {}
        target = int(order.get("order_target") or 0)
        reward = int(order.get("order_reward") or DEFAULTS.daily_order_reward)
        bonus = int(order.get("order_bonus") or DEFAULTS.daily_order_bonus)
        today = date.today().isoformat()
        progress = await db.get_daily_order_progress(chat_id, today, order["order_item_id"])
        order_payload = {
            "item_id": order["order_item_id"],
            "name": item.get("name", order["order_item_id"]),
            "emoji": item.get("emoji") or rarity_emoji(item.get("rarity", "common")),
            "target": target,
            "progress": progress,
            "reward": reward,
            "bonus": bonus,
        }
    top_contrib = await db.get_warehouse_top_contributor(chat_id)
    top_payload = None
    if top_contrib:
        name = (
            (top_contrib.get("first_name") or top_contrib.get("username") or "Игрок")
            if isinstance(top_contrib, dict)
            else "Игрок"
        )
        top_payload = {
            "name": name,
            "value_total": int(top_contrib.get("value_total") or 0),
        }
    return {
        "goal": goal,
        "total_items": total_items,
        "total_value": total_value,
        "top_items": entries[:WAREHOUSE_TOP_LIMIT],
        "order": order_payload,
        "top_contrib": top_payload,
    }


async def build_rating_payload(limit: int) -> Dict[str, Any]:
    rows = await db.get_top_ratings(limit)
    result = []
    for idx, row in enumerate(rows, start=1):
        name = (row.get("first_name") or row.get("username") or "Игрок")
        last = row.get("last_name") or ""
        full = f"{name} {last}".strip()
        result.append(
            {
                "rank": idx,
                "name": full or "Игрок",
                "points": int(row.get("points", 0)),
                "extracts": int(row.get("extracts", 0)),
                "kills": int(row.get("kills", 0)),
                "deaths": int(row.get("deaths", 0)),
            }
        )
    return {"rows": result}


async def build_event_payload(player_id: int, chat_id: int) -> Optional[Dict[str, Any]]:
    event = await get_active_event_meta(chat_id)
    if not event:
        return None
    totals = await db.get_event_totals(chat_id, event["id"])
    top = await db.get_event_top(chat_id, event["id"], limit=5)
    me = await db.get_event_player(chat_id, event["id"], player_id)
    top_rows = []
    for row in top:
        name = (row.get("first_name") or row.get("username") or "Игрок")
        last = row.get("last_name") or ""
        full = f"{name} {last}".strip()
        top_rows.append(
            {
                "name": full or "Игрок",
                "value_total": int(row.get("value_total", 0)),
                "items_total": int(row.get("items_total", 0)),
            }
        )
    return {
        "event": event,
        "totals": totals,
        "top": top_rows,
        "me": {
            "value_total": int(me.get("value_total", 0)) if me else 0,
            "items_total": int(me.get("items_total", 0)) if me else 0,
        },
    }


async def build_season_payload(player_id: int, chat_id: int) -> Dict[str, Any]:
    await finish_previous_season_if_needed(chat_id)
    season_id, season_start, season_end = db._current_season_bounds(date.today())
    await db.ensure_season(season_id, season_start, season_end)
    top = await db.get_season_top(season_id, limit=RATING_LIMIT)
    me = await db.get_season_player(season_id, player_id)
    rows = []
    for row in top:
        name = (row.get("first_name") or row.get("username") or "Игрок")
        last = row.get("last_name") or ""
        full = f"{name} {last}".strip()
        rows.append(
            {
                "name": full or "Игрок",
                "points": int(row.get("points", 0)),
                "raids": int(row.get("raids", 0)),
                "extracts": int(row.get("extracts", 0)),
                "deaths": int(row.get("deaths", 0)),
                "kills": int(row.get("kills", 0)),
            }
        )
    return {
        "season": {
            "id": season_id,
            "start": season_start,
            "end": season_end,
        },
        "top": rows,
        "me": {
            "points": int(me.get("points", 0)) if me else 0,
            "raids": int(me.get("raids", 0)) if me else 0,
            "extracts": int(me.get("extracts", 0)) if me else 0,
            "deaths": int(me.get("deaths", 0)) if me else 0,
            "kills": int(me.get("kills", 0)) if me else 0,
        },
    }


@app.post("/api/auth/register")
async def auth_register(payload: AuthRegisterRequest, request: Request) -> Dict[str, Any]:
    email = _normalize_email(payload.email)
    nickname = payload.nickname.strip()
    password = payload.password
    if not _is_valid_email(email):
        return {"ok": False, "message": "Некорректная почта."}
    if len(nickname) < 3:
        return {"ok": False, "message": "Никнейм слишком короткий."}
    if len(password) < 6:
        return {"ok": False, "message": "Пароль слишком короткий."}
    existing = await db.get_web_user_by_email(email)
    if existing:
        return {"ok": False, "message": "Почта уже зарегистрирована."}
    password_hash = _hash_password(password)
    player_id = await db.create_web_user(email, nickname, password_hash)
    ip = request.client.host if request.client else None
    await db.log_web_login(player_id, email, ip)
    await db.update_web_user_login(player_id, ip)
    if ip:
        total = await db.count_recent_ip_accounts(ip)
        if total > DEFAULTS.suspicious_ip_limit:
            await db.add_audit_log(
                "suspicious_ip",
                f"IP {ip} используется {total} аккаунтами за 24ч",
                player_id,
            )
    token = _create_token(player_id)
    return {
        "ok": True,
        "message": "Регистрация успешна.",
        "token": token,
        "user": {"email": email, "nickname": nickname},
    }


@app.post("/api/auth/login")
async def auth_login(payload: AuthLoginRequest, request: Request) -> Dict[str, Any]:
    email = _normalize_email(payload.email)
    password = payload.password
    user = await db.get_web_user_by_email(email)
    if not user:
        return {"ok": False, "message": "Неверная почта или пароль."}
    if not _verify_password(password, user.get("password_hash", "")):
        return {"ok": False, "message": "Неверная почта или пароль."}
    player_id = int(user.get("player_id") or 0)
    if not player_id:
        return {"ok": False, "message": "Пользователь не найден."}
    ip = request.client.host if request.client else None
    await db.log_web_login(player_id, email, ip)
    await db.update_web_user_login(player_id, ip)
    if ip:
        total = await db.count_recent_ip_accounts(ip)
        if total > DEFAULTS.suspicious_ip_limit:
            await db.add_audit_log(
                "suspicious_ip",
                f"IP {ip} используется {total} аккаунтами за 24ч",
                player_id,
            )
    token = _create_token(player_id)
    return {
        "ok": True,
        "message": "Вход выполнен.",
        "token": token,
        "user": {"email": email, "nickname": user.get("nickname")},
    }


@app.post("/api/auth/telegram")
async def auth_telegram(payload: AuthTelegramRequest) -> Dict[str, Any]:
    if not BOT_TOKEN:
        return {"ok": False, "message": "BOT_TOKEN не задан."}
    login_pairs, reason = _validate_login_data_debug(payload.login_data)
    if not login_pairs:
        return {"ok": False, "message": f"Некорректные данные Telegram: {reason}"}
    tg_user = _parse_login_user(login_pairs)
    if not tg_user:
        return {"ok": False, "message": "Пользователь Telegram не найден."}
    player_id = await db.upsert_player(tg_user)
    token = _create_token(player_id)
    display_name = (
        tg_user.username
        or " ".join(p for p in (tg_user.first_name, tg_user.last_name) if p)
        or "Игрок"
    )
    return {
        "ok": True,
        "message": "Вход через Telegram выполнен.",
        "token": token,
        "user": {"nickname": display_name},
    }


@app.post("/api/auth/telegram/init")
async def auth_telegram_init(payload: InitDataRequest) -> Dict[str, Any]:
    if not BOT_TOKEN:
        return {"ok": False, "message": "BOT_TOKEN ?? ?????."}
    pairs = _validate_init_data(payload.init_data)
    if not pairs:
        return {"ok": False, "message": f"???????????? ?????? Telegram initData: {reason}"}
    tg_user = _parse_user(pairs)
    if not tg_user:
        return {"ok": False, "message": "???????????? Telegram ?? ??????."}
    player_id = await db.upsert_player(tg_user)
    token = _create_token(player_id)
    display_name = (
        tg_user.username
        or " ".join(p for p in (tg_user.first_name, tg_user.last_name) if p)
        or "?????"
    )
    return {
        "ok": True,
        "message": "???? ????? Telegram ????????.",
        "token": token,
        "user": {"nickname": display_name},
    }


@app.post("/api/state")
async def state(payload: InitDataRequest) -> Dict[str, Any]:
    user, player_id = await _authorize(payload)
    resolved_chat_id = _require_chat_id(payload)
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
        **await build_state(player_id, resolved_chat_id),
    }


@app.post("/api/onboarding/complete")
async def onboarding_complete(payload: InitDataRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    await db.update_web_user_onboarded(player_id)
    return {"ok": True}


@app.post("/api/quests")
async def quests_state(payload: InitDataRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    quests = await build_quests_payload(player_id)
    return {"ok": True, "quests": quests}


@app.post("/api/quest/claim")
async def quest_claim(payload: QuestClaimRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    if payload.kind not in ("daily", "weekly"):
        return {"ok": False, "message": "Неверный тип квеста."}
    daily_period, weekly_period = await ensure_player_quests(player_id)
    period = daily_period if payload.kind == "daily" else weekly_period
    quests = await db.get_player_quests(player_id, payload.kind, period)
    quest = next((q for q in quests if q.get("quest_id") == payload.quest_id), None)
    if not quest:
        return {"ok": False, "message": "Квест не найден."}
    if not quest.get("completed"):
        return {"ok": False, "message": "Квест ещё не выполнен."}
    if quest.get("claimed"):
        return {"ok": False, "message": "Награда уже получена."}
    reward_points = int(quest.get("reward_points", 0))
    reward_raidcoins = int(quest.get("reward_raidcoins", 0))
    reward_item_id = quest.get("reward_item_id")
    reward_qty = int(quest.get("reward_qty", 0))
    if reward_item_id and reward_qty > 0:
        storage_used = await db.get_inventory_count(player_id)
        storage_limit = await db.get_storage_limit(player_id)
        if storage_used + reward_qty > storage_limit:
            return {"ok": False, "message": "Освободите место на складе."}
        await db.add_inventory_items(player_id, {reward_item_id: reward_qty})
    if reward_points:
        await db.adjust_rating(player_id, points=reward_points)
    if reward_raidcoins:
        await db.adjust_raidcoins(player_id, reward_raidcoins)
    await db.claim_player_quest(player_id, payload.kind, period, payload.quest_id)
    quests_payload = await build_quests_payload(player_id)
    return {
        "ok": True,
        "message": "Награда получена.",
        "quests": quests_payload,
    }


@app.post("/api/raid/enter")
async def raid_enter(payload: InitDataRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    thread_id = _require_thread_id(payload)
    session = await db.get_active_session(player_id, chat_id)
    if session:
        return {"ok": False, "message": "У вас уже есть активный рейд.", "state": await build_state(player_id, chat_id)}

    today = date.today().isoformat()
    raids_today = await db.get_daily_raids(player_id, chat_id, today)
    if raids_today >= DEFAULTS.daily_raid_limit:
        return {"ok": False, "message": "Дневной лимит рейдов исчерпан.", "state": await build_state(player_id, chat_id)}

    entry_fee = DEFAULTS.raid_entry_fee
    rating = await db.get_rating(player_id)
    points = int(rating.get("points", 0))
    entry_bonus = DEFAULTS.raid_entry_bonus if entry_fee > 0 else 0
    if entry_fee > 0 and points < entry_fee:
        entry_fee = 0
        entry_bonus = 0

    loadout = await db.get_loadout(player_id)
    storage_items = await db.get_inventory(player_id)
    hard_mode = random.random() < DEFAULTS.hard_raid_chance
    session = {
        "id": os.urandom(4).hex(),
        "player_id": player_id,
        "chat_id": chat_id,
        "thread_id": thread_id,
        "hp": DEFAULTS.start_hp,
        "max_hp": DEFAULTS.start_hp,
        "greed": 0,
        "loot_value": 0,
        "kills": 0,
        "inventory": {},
        "armor_pct": 0.0,
        "weapon_bonus": 0,
        "armor_item_id": None,
        "weapon_item_id": None,
        "damage_bonus": 0,
        "greed_mult": 1.0,
        "chip_id": None,
        "hard_mode": hard_mode,
        "evac_penalty": DEFAULTS.hard_raid_evac_penalty if hard_mode else 0.0,
        "status": "explore",
        "enemy": None,
        "evac_bonus": 0.0,
        "entry_fee": entry_fee,
        "entry_bonus": entry_bonus,
        "panel_message_id": None,
        "pending_loot": [],
        "pending_choice": None,
        "cooldowns": {},
    }

    armor_id = loadout.get("armor_id")
    if armor_id and storage_items.get(armor_id, 0) > 0:
        item = data.get_item(armor_id)
        if item and item.get("type") == "armor":
            ok = await db.adjust_inventory(player_id, {armor_id: -1})
            if ok:
                session["armor_item_id"] = armor_id
                session["armor_pct"] = float(item.get("armor_pct", 0))

    weapon_id = loadout.get("weapon_id")
    if weapon_id and storage_items.get(weapon_id, 0) > 0:
        item = data.get_item(weapon_id)
        if item and item.get("type") == "weapon":
            ok = await db.adjust_inventory(player_id, {weapon_id: -1})
            if ok:
                session["weapon_item_id"] = weapon_id
                session["weapon_bonus"] = int(item.get("weapon_bonus", 0))

    medkit_id = loadout.get("medkit_id")
    if medkit_id and storage_items.get(medkit_id, 0) > 0:
        ok = await db.adjust_inventory(player_id, {medkit_id: -1})
        if ok:
            session["inventory"][medkit_id] = 1

    chip_id = loadout.get("chip_id")
    if chip_id and storage_items.get(chip_id, 0) > 0:
        chip = data.get_item(chip_id)
        if chip and chip.get("type") == "augment":
            ok = await db.adjust_inventory(player_id, {chip_id: -1})
            if ok:
                session["chip_id"] = chip_id
                greed_mult = chip.get("greed_mult")
                if isinstance(greed_mult, (int, float)) and greed_mult > 0:
                    session["greed_mult"] = float(greed_mult)
                evac_bonus = chip.get("evac_bonus")
                if isinstance(evac_bonus, (int, float)) and evac_bonus > 0:
                    session["evac_bonus"] = min(
                        0.3, session["evac_bonus"] + float(evac_bonus)
                    )
                dmg_bonus = chip.get("damage_bonus")
                if isinstance(dmg_bonus, (int, float)) and dmg_bonus > 0:
                    session["damage_bonus"] += int(dmg_bonus)

    created = await db.create_session(session)
    if not created:
        return {"ok": False, "message": "Не удалось создать сессию.", "state": await build_state(player_id, chat_id)}

    if entry_fee > 0:
        await db.adjust_rating(player_id, points=-entry_fee)
    await db.increment_daily_raids(player_id, chat_id, today)
    await db.update_daily_stats(player_id, today, raids_delta=1)
    await update_quest_progress(player_id, {"raids_started": 1})
    await db.adjust_rating(player_id, raids=1)

    return {"ok": True, "message": "Рейд начат.", "state": await build_state(player_id, chat_id)}


@app.post("/api/raid/action")
async def raid_action(payload: RaidActionRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    action = payload.action
    chat_id = _require_chat_id(payload)
    session = await db.get_active_session(player_id, chat_id)
    if not session:
        return {"ok": False, "message": "Активный рейд не найден.", "state": await build_state(player_id, chat_id)}

    now = time.time()
    if action in ACTION_COOLDOWNS:
        remaining = cooldown_remaining(session, action, now)
        if remaining > 0:
            return {"ok": False, "message": f"Кулдаун: {remaining} сек.", "state": await build_state(player_id, chat_id)}

    if session.get("pending_loot") and action not in ("take", "skip"):
        return {"ok": False, "message": "Сначала решите, взять лут или нет.", "state": await build_state(player_id, chat_id)}

    if session.get("pending_choice") and not action.startswith("choice:"):
        return {"ok": False, "message": "Сначала сделайте выбор события.", "state": await build_state(player_id, chat_id)}

    if action.startswith("choice:"):
        pending = session.get("pending_choice") or {}
        event_id = pending.get("event_id")
        event = STORY_EVENTS.get(event_id or "")
        if not event:
            session["pending_choice"] = None
            await db.update_session(session)
            return {"ok": False, "message": "Событие устарело.", "state": await build_state(player_id, chat_id)}
        choice_id = action.split(":", 1)[1]
        choice = next(
            (c for c in event.get("choices", []) if c.get("id") == choice_id),
            None,
        )
        if not choice:
            return {"ok": False, "message": "Неверный выбор.", "state": await build_state(player_id, chat_id)}
        session["pending_choice"] = None
        session, note, items = apply_story_choice(session, choice)
        msg_parts = []
        if note:
            msg_parts.append(note)
        next_id = choice.get("next")
        if next_id and next_id in STORY_EVENTS:
            next_event = dict(STORY_EVENTS[next_id])
            next_event["id"] = next_id
            session["pending_choice"] = build_story_choice_payload(next_event)
            msg_parts.append(next_event.get("text", ""))
        if items:
            session["pending_loot"] = [item["id"] for item in items]
            msg_parts.append("Лут найден.")
        await db.update_session(session)
        return {"ok": True, "message": " ".join(p for p in msg_parts if p), "state": await build_state(player_id, chat_id)}

    last_event = None

    if action in ("take", "skip"):
        pending_item = build_pending_item(session)
        if not pending_item:
            return {"ok": False, "message": "Нет предмета для выбора.", "state": await build_state(player_id, chat_id)}
        session["pending_loot"] = session.get("pending_loot", [])[1:]
        if action == "take":
            if inventory_count(session) >= DEFAULTS.raid_limit:
                last_event = f"Рейдовый инвентарь заполнен ({DEFAULTS.raid_limit})."
            else:
                session, _ = apply_loot(session, pending_item)
                await update_quest_progress(
                    player_id,
                    {
                        'loot_items': 1,
                        'loot_value': int(pending_item.get('value', 0)),
                    },
                )
                last_event = f"Вы взяли: {format_item(pending_item)}."
        else:
            last_event = f"Вы оставили: {format_item(pending_item)}."
        await db.update_session(session)
        return {"ok": True, "message": last_event, "state": await build_state(player_id, chat_id)}

    if action == "medkit":
        set_cooldown(session, "medkit", now)
        add_greed(session, DEFAULTS.greed_medkit)
        session, msg = consume_medkit(session, data)
        last_event = msg or "Аптечек нет."
        await db.update_session(session)
        return {"ok": True, "message": last_event, "state": await build_state(player_id, chat_id)}

    if action == "fight":
        add_greed(session, DEFAULTS.greed_fight)
        enemy = session.get("enemy")
        if not enemy:
            return {"ok": False, "message": "Врага нет.", "state": await build_state(player_id, chat_id)}
        set_cooldown(session, "fight", now)
        session, fight_log, win = resolve_fight(session, enemy)
        if session["hp"] <= 0:
            result = await handle_death_web(session, player_id, "Поражение в бою.")
            return {"ok": True, "message": result["message"], "state": await build_state(player_id, chat_id)}
        last_event = fight_log
        if win:
            await update_quest_progress(player_id, {"kills": 1})
            drops = []
            drop = roll_bonus_drop(data)
            if drop:
                drops.append(drop)
            controller_bonus = enemy.get("legendary_bonus")
            if controller_bonus is None and enemy.get("controller"):
                controller_bonus = DEFAULTS.controller_legendary_chance
            controller_bonus = float(controller_bonus or 0)
            if controller_bonus > 0 and random.random() < controller_bonus:
                drops.append(roll_loot_by_rarity(data, "legendary"))
                last_event += " 🎯 Контролёр оставил редкий трофей."
            if drops:
                session["pending_loot"] = [item["id"] for item in drops]
        await db.update_session(session)
        return {"ok": True, "message": last_event, "state": await build_state(player_id, chat_id)}

    if session.get("status") == "combat":
        return {"ok": False, "message": "Сначала бой.", "state": await build_state(player_id, chat_id)}

    if action == "loot":
        set_cooldown(session, "loot", now)
        add_greed(session, DEFAULTS.greed_loot)
        if random.random() < 0.18 and not session.get("pending_choice"):
            story_event = roll_story_event()
            session["pending_choice"] = build_story_choice_payload(story_event)
            await db.update_session(session)
            return {"ok": True, "message": story_event.get("text", ""), "state": await build_state(player_id, chat_id)}
        settings = await db.ensure_settings(chat_id)
        if settings["events_enabled"] and random.random() < calc_event_chance(
            session["greed"], settings
        ):
            event = data.roll_event()
            session, event_text, died, items, cost_points = apply_event(session, event)
            if died:
                result = await handle_death_web(session, player_id, event_text)
                return {"ok": True, "message": result["message"], "state": await build_state(player_id, chat_id)}
            if cost_points:
                await db.adjust_rating(player_id, points=-cost_points)
            if items:
                bonus_added = apply_hard_loot_bonus(session, items)
                if bonus_added:
                    event_text += " 🎯 Тяжёлый рейд: найден дополнительный лут."
                session["pending_loot"] = [item["id"] for item in items]
                await db.update_session(session)
                return {"ok": True, "message": event_text, "state": await build_state(player_id, chat_id)}
            last_event = event_text
        else:
            items = [data.roll_loot()]
            bonus_added = apply_hard_loot_bonus(session, items)
            session["pending_loot"] = [item["id"] for item in items]
            await db.update_session(session)
            last_event = "Лут найден." + (" 🎯 Тяжёлый рейд: найден дополнительный лут." if bonus_added else "")
            return {"ok": True, "message": last_event, "state": await build_state(player_id, chat_id)}
        await db.update_session(session)
        return {"ok": True, "message": last_event, "state": await build_state(player_id, chat_id)}

    if action == "move":
        set_cooldown(session, "move", now)
        add_greed(session, DEFAULTS.greed_move)
        if random.random() < 0.18 and not session.get("pending_choice"):
            story_event = roll_story_event()
            session["pending_choice"] = build_story_choice_payload(story_event)
            await db.update_session(session)
            return {"ok": True, "message": story_event.get("text", ""), "state": await build_state(player_id, chat_id)}
        settings = await db.ensure_settings(chat_id)
        if settings["events_enabled"] and random.random() < calc_event_chance(
            session["greed"], settings
        ):
            event = data.roll_event()
            session, event_text, died, items, cost_points = apply_event(session, event)
            if died:
                result = await handle_death_web(session, player_id, event_text)
                return {"ok": True, "message": result["message"], "state": await build_state(player_id, chat_id)}
            if cost_points:
                await db.adjust_rating(player_id, points=-cost_points)
            if items:
                bonus_added = apply_hard_loot_bonus(session, items)
                if bonus_added:
                    event_text += " 🎯 Тяжёлый рейд: найден дополнительный лут."
                session["pending_loot"] = [item["id"] for item in items]
                await db.update_session(session)
                return {"ok": True, "message": event_text, "state": await build_state(player_id, chat_id)}
            last_event = event_text
        else:
            last_event = "Вы продвинулись глубже. Сигнатуры ARC усиливаются."
        await db.update_session(session)
        return {"ok": True, "message": last_event, "state": await build_state(player_id, chat_id)}

    if action == "evac":
        set_cooldown(session, "evac", now)
        settings = await db.ensure_settings(chat_id)
        chance = calc_evac_chance(session["greed"], effective_evac_bonus(session), settings)
        if random.random() < chance:
            result = await handle_extract_web(session, player_id)
            return {"ok": True, "message": result["message"], "state": await build_state(player_id, chat_id)}
        add_greed(session, DEFAULTS.greed_evac_fail)
        enemy = data.roll_enemy()
        enemy["hp_current"] = enemy["hp"]
        session["enemy"] = enemy
        session["status"] = "combat"
        session["evac_bonus"] = 0.0
        last_event = f"Эвакуация сорвана! Засада: {enemy['name']}."
        await db.update_session(session)
        return {"ok": True, "message": last_event, "state": await build_state(player_id, chat_id)}

    return {"ok": False, "message": "Неизвестное действие.", "state": await build_state(player_id, chat_id)}


@app.post("/api/storage")
async def storage(payload: PaginationRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    storage_data = await build_storage_payload(player_id, payload.sort, payload.page)
    return {"ok": True, "storage": storage_data}


@app.post("/api/storage/upgrade")
async def storage_upgrade(payload: StorageUpgradeRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    rating = await db.get_rating(player_id)
    points = int(rating.get("points", 0))
    storage_limit = int(rating.get("storage_limit", DEFAULTS.storage_limit))
    message = ""
    ok = False
    if not can_upgrade_storage(storage_limit):
        message = "Улучшение недоступно."
    else:
        cost = storage_upgrade_cost(storage_limit)
        if points < cost:
            message = f"Нужно {cost} очк."
        else:
            await db.adjust_rating(player_id, points=-cost)
            await db.update_storage_limit(
                player_id, storage_limit + DEFAULTS.storage_upgrade_step
            )
            message = "Склад улучшен."
            ok = True
    storage_data = await build_storage_payload(player_id, None, 1)
    return {"ok": ok, "message": message, "storage": storage_data}


@app.post("/api/sell")
async def sell_list(payload: PaginationRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    sell_data = await build_sell_payload(player_id, payload.sort, payload.page)
    return {"ok": True, "sell": sell_data}


@app.post("/api/sell/confirm")
async def sell_confirm(payload: SellConfirmRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    items = await db.get_inventory(player_id)
    qty_available = items.get(payload.item_id, 0)
    item = data.get_item(payload.item_id)
    notice = ""
    ok = False
    if not item or not is_sellable(item) or qty_available <= 0:
        notice = "Предмет недоступен."
    else:
        if payload.qty_raw:
            if payload.qty_raw == "all":
                sell_qty = qty_available
            else:
                sell_qty = int(payload.qty_raw)
        elif payload.qty is not None:
            sell_qty = int(payload.qty)
        else:
            sell_qty = 1
        sell_qty = max(1, min(sell_qty, qty_available))
        price = sell_price(item, sell_qty)
        today = date.today().isoformat()
        cap_ok, cap_msg = await check_daily_sell_caps(player_id, chat_id, price, 1)
        if not cap_ok:
            notice = cap_msg
            sell_data = await build_sell_payload(player_id, payload.sort, payload.page)
            return {"ok": False, "message": notice, "sell": sell_data}
        ok = await db.adjust_inventory(player_id, {payload.item_id: -sell_qty})
        if not ok:
            notice = "Недостаточно предметов."
        else:
            await db.adjust_raidcoins(player_id, price)
            await db.update_daily_stats(player_id, today, raidcoins_delta=price, sells_delta=1)
            await update_quest_progress(player_id, {"sell_value": price})
            await db.add_warehouse_items(chat_id, {payload.item_id: sell_qty})
            contrib_value = int(item.get("value", 0)) * sell_qty
            if contrib_value > 0:
                await db.add_warehouse_contribution(
                    chat_id, player_id, contrib_value, sell_qty
                )
            event = await get_active_event_meta(chat_id)
            if event and contrib_value > 0:
                await db.add_event_contribution(
                    chat_id,
                    event["id"],
                    player_id,
                    contrib_value,
                    sell_qty,
                )
            today = date.today().isoformat()
            order = await get_daily_order(chat_id)
            bonus_text = ""
            if order.get("order_item_id") == payload.item_id and order.get("order_target"):
                target = int(order.get("order_target") or 0)
                reward_per = int(order.get("order_reward") or DEFAULTS.daily_order_reward)
                bonus = int(order.get("order_bonus") or DEFAULTS.daily_order_bonus)
                if event:
                    reward_per = int(round(reward_per * DEFAULTS.event_order_mult))
                    bonus = int(round(bonus * DEFAULTS.event_order_mult))
                before = await db.get_daily_order_progress(chat_id, today, payload.item_id)
                after = await db.increment_daily_order_progress(
                    chat_id, today, payload.item_id, sell_qty
                )
                remaining = max(0, target - before)
                reward_qty = min(sell_qty, remaining)
                if reward_qty > 0 and reward_per > 0:
                    reward_total = reward_qty * reward_per
                    await db.adjust_raidcoins(player_id, reward_total)
                    bonus_text += f" Заказ дня: +{reward_total} {RC_EMOJI}."
                if before < target <= after and bonus > 0:
                    await db.adjust_raidcoins(player_id, bonus)
                    bonus_text += f" Заказ закрыт! +{bonus} {RC_EMOJI}."
            notice = f"Продано: {format_item(item)} x{sell_qty} → +{price} {RC_EMOJI}.{bonus_text}"
            ok = True
    sell_data = await build_sell_payload(player_id, payload.sort, payload.page)
    return {"ok": ok, "message": notice, "sell": sell_data}


@app.post("/api/market")
async def market_state(payload: MarketStateRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    market = await build_market_payload(
        player_id,
        chat_id,
        page=payload.page,
        items_page=payload.items_page,
        sort_key=payload.items_sort,
    )
    return {"ok": True, "market": market}


@app.post("/api/market/list")
async def market_list(payload: MarketListRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    items = await db.get_inventory(player_id)
    qty_available = items.get(payload.item_id, 0)
    item = data.get_item(payload.item_id)
    if not item or not is_sellable(item) or qty_available <= 0:
        return {"ok": False, "message": "Предмет недоступен."}
    settings = await db.ensure_settings(chat_id)
    listing_cap = int(settings.get("market_listing_cap", DEFAULTS.market_listing_cap))
    active_count = await db.get_player_market_listing_count(player_id)
    if active_count >= listing_cap:
        return {"ok": False, "message": f"Лимит лотов: {listing_cap}."}
    if payload.qty_raw:
        if payload.qty_raw == "all":
            qty = qty_available
        else:
            qty = int(payload.qty_raw)
    else:
        qty = 1
    qty = max(1, min(qty, qty_available))
    price = max(1, int(payload.price))
    ok = await db.adjust_inventory(player_id, {payload.item_id: -qty})
    if not ok:
        return {"ok": False, "message": "Недостаточно предметов."}
    await db.create_market_listing(player_id, payload.item_id, qty, price)
    market = await build_market_payload(player_id, chat_id)
    return {"ok": True, "message": "Лот выставлен.", "market": market}


@app.post("/api/market/buy")
async def market_buy(payload: MarketBuyRequest) -> Dict[str, Any]:
    _, buyer_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    listing = await db.get_market_listing(int(payload.listing_id))
    if not listing:
        return {"ok": False, "message": "Лот уже недоступен."}
    seller_id = int(listing.get("seller_id") or 0)
    if seller_id == buyer_id:
        return {"ok": False, "message": "Нельзя купить свой лот."}
    price = int(listing.get("price", 0))
    buyer_rating = await db.get_rating(buyer_id)
    buyer_rc = int(buyer_rating.get("raidcoins", 0))
    if buyer_rc < price:
        return {"ok": False, "message": "Недостаточно RC."}
    storage_used = await db.get_inventory_count(buyer_id)
    storage_limit = await db.get_storage_limit(buyer_id)
    qty = int(listing.get("qty", 1))
    if storage_used + qty > storage_limit:
        return {"ok": False, "message": "Недостаточно места на складе."}
    cap_ok, cap_msg = await check_daily_sell_caps(seller_id, chat_id, price, 1)
    if not cap_ok:
        return {"ok": False, "message": "Продавец достиг дневного лимита, попробуйте позже."}
    await db.adjust_raidcoins(buyer_id, -price)
    await db.adjust_raidcoins(seller_id, price)
    await db.add_inventory_items(buyer_id, {listing["item_id"]: qty})
    today = date.today().isoformat()
    await db.update_daily_stats(seller_id, today, raidcoins_delta=price, sells_delta=1)
    await update_quest_progress(seller_id, {"sell_value": price})
    await db.delete_market_listing(listing["id"])
    market = await build_market_payload(buyer_id, chat_id)
    return {"ok": True, "message": "Покупка успешна.", "market": market}


@app.post("/api/market/cancel")
async def market_cancel(payload: MarketCancelRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    listing = await db.get_market_listing(int(payload.listing_id))
    if not listing:
        return {"ok": False, "message": "Лот уже закрыт."}
    if int(listing.get("seller_id") or 0) != player_id:
        return {"ok": False, "message": "Это не ваш лот."}
    qty = int(listing.get("qty", 1))
    storage_used = await db.get_inventory_count(player_id)
    storage_limit = await db.get_storage_limit(player_id)
    if storage_used + qty > storage_limit:
        return {"ok": False, "message": "Нет места на складе."}
    await db.add_inventory_items(player_id, {listing["item_id"]: qty})
    await db.delete_market_listing(listing["id"])
    market = await build_market_payload(player_id, chat_id)
    return {"ok": True, "message": "Лот снят.", "market": market}


@app.post("/api/shop")
async def shop_state(payload: InitDataRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    shop_data = await build_shop_payload(player_id, chat_id)
    return {"ok": True, "shop": shop_data}


@app.post("/api/shop/buy")
async def shop_buy(payload: ShopBuyRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    rating = await db.get_rating(player_id)
    points = int(rating.get("points", 0))
    raidcoins = int(rating.get("raidcoins", 0))
    storage_limit = int(rating.get("storage_limit", DEFAULTS.storage_limit))
    insurance = int(rating.get("insurance_tokens", 0))
    storage_used = await db.get_inventory_count(player_id)
    offers = await get_daily_shop(chat_id)
    today = date.today().isoformat()
    purchases_today = await db.get_daily_shop_purchases(player_id, chat_id, today)
    tax_mult = shop_tax_multiplier(purchases_today)
    notice = ""
    ok = False

    if payload.kind in ("medkit", "evac_beacon", "insurance", "offer", "recipe") and purchases_today >= DEFAULTS.shop_daily_limit:
        notice = "Лимит покупок на сегодня исчерпан."
    elif payload.kind == "medkit":
        medkit_item_id = SHOP_ITEM_IDS["medkit"]
        medkit_item = data.get_item(medkit_item_id)
        medkit_name = medkit_item["name"] if medkit_item else "Расходник"
        price = int(round(SHOP_PRICES["medkit"] * tax_mult))
        if storage_used >= storage_limit:
            notice = "Хранилище заполнено."
        elif raidcoins < price:
            notice = f"Недостаточно {RC_EMOJI}."
        else:
            await db.adjust_raidcoins(player_id, -price)
            await db.add_inventory_items(player_id, {medkit_item_id: 1})
            await db.increment_daily_shop_purchases(player_id, chat_id, today)
            notice = f"{medkit_name} куплен."
            ok = True
    elif payload.kind == "evac_beacon":
        evac_item_id = SHOP_ITEM_IDS["evac_beacon"]
        evac_item = data.get_item(evac_item_id)
        evac_name = evac_item["name"] if evac_item else "Эвак-устройство"
        price = int(round(SHOP_PRICES["evac_beacon"] * tax_mult))
        if storage_used >= storage_limit:
            notice = "Хранилище заполнено."
        elif raidcoins < price:
            notice = f"Недостаточно {RC_EMOJI}."
        else:
            await db.adjust_raidcoins(player_id, -price)
            await db.add_inventory_items(player_id, {evac_item_id: 1})
            await db.increment_daily_shop_purchases(player_id, chat_id, today)
            notice = f"{evac_name} куплен."
            ok = True
    elif payload.kind == "insurance":
        if insurance >= DEFAULTS.insurance_max_tokens:
            notice = f"Лимит страховок: {DEFAULTS.insurance_max_tokens}."
        else:
            price = int(round(SHOP_PRICES["insurance"] * tax_mult))
            if raidcoins < price:
                notice = f"Недостаточно {RC_EMOJI}."
            else:
                await db.adjust_raidcoins(player_id, -price)
                await db.adjust_insurance_tokens(player_id, 1)
                await db.increment_daily_shop_purchases(player_id, chat_id, today)
                notice = "Страховка куплена."
                ok = True
    elif payload.kind == "offer":
        offer_item = None
        for offer in offers.get("items", []):
            if offer.get("item_id") == payload.item_id:
                offer_item = offer
                break
        if not offer_item:
            notice = "Витрина обновилась."
        else:
            price = int(round(offer_item["price"] * tax_mult))
            if storage_used >= storage_limit:
                notice = "Хранилище заполнено."
            elif points < price:
                notice = "Недостаточно очков."
            else:
                await db.adjust_rating(player_id, points=-price)
                await db.add_inventory_items(player_id, {payload.item_id: 1})
                await db.increment_daily_shop_purchases(player_id, chat_id, today)
                notice = "Покупка успешна."
                ok = True
    elif payload.kind == "recipe":
        recipe_id = payload.recipe_id or payload.item_id
        recipe_offer = offers.get("recipe") if offers else None
        unlocked = await db.get_unlocked_recipes(player_id)
        if not recipe_id or not recipe_offer or recipe_offer.get("recipe_id") != recipe_id:
            notice = "Витрина обновилась."
        elif recipe_id in unlocked or recipe_id in BASE_RECIPE_IDS:
            notice = "Рецепт уже изучен."
        else:
            price = int(round(recipe_offer["price"] * tax_mult))
            if points < price:
                notice = "Недостаточно очков."
            else:
                await db.adjust_rating(player_id, points=-price)
                await db.unlock_recipe(player_id, recipe_id)
                await db.increment_daily_shop_purchases(player_id, chat_id, today)
                notice = "Рецепт изучен."
                ok = True
    elif payload.kind == "upgrade":
        if not can_upgrade_storage(storage_limit):
            notice = "Улучшение недоступно."
        else:
            cost = storage_upgrade_cost(storage_limit)
            if points < cost:
                notice = f"Нужно {cost} очк."
            else:
                await db.adjust_rating(player_id, points=-cost)
                await db.update_storage_limit(
                    player_id, storage_limit + DEFAULTS.storage_upgrade_step
                )
                notice = "Склад улучшен."
                ok = True
    else:
        notice = "Неизвестная покупка."

    shop_data = await build_shop_payload(player_id, chat_id)
    return {"ok": ok, "message": notice, "shop": shop_data}


@app.post("/api/craft")
async def craft_state(payload: InitDataRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    craft_data = await build_craft_payload(player_id)
    return {"ok": True, "craft": craft_data}


@app.post("/api/craft/make")
async def craft_make(payload: CraftMakeRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    recipes = await get_available_recipes(player_id)
    available_ids = {recipe["id"] for recipe in recipes}
    notice = ""
    ok = False
    if payload.recipe_id not in available_ids:
        notice = "Рецепт недоступен."
    else:
        recipe = data.get_recipe(payload.recipe_id)
        if not recipe:
            notice = "Рецепт не найден."
        else:
            items = await db.get_inventory(player_id)
            if not can_craft(items, recipe):
                notice = "Не хватает ресурсов."
            else:
                consume, produce = craft_deltas(recipe)
                storage_used = await db.get_inventory_count(player_id)
                storage_limit = await db.get_storage_limit(player_id)
                delta_count = sum(produce.values()) + sum(consume.values())
                if storage_used + delta_count > storage_limit:
                    notice = "Хранилище переполнено."
                else:
                    ok_adjust = await db.adjust_inventory(player_id, consume)
                    if not ok_adjust:
                        notice = "Не хватает ресурсов."
                    else:
                        await db.add_inventory_items(player_id, produce)
                        out_item = data.get_item(recipe["output"]["item_id"])
                        out_name = out_item["name"] if out_item else recipe["output"]["item_id"]
                        notice = f"Скрафчено: {out_name}."
                        ok = True
    craft_data = await build_craft_payload(player_id)
    return {"ok": ok, "message": notice, "craft": craft_data}


@app.post("/api/blueprints")
async def blueprint_state(payload: BlueprintListRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    blueprints = await build_blueprint_payload(player_id, payload.page)
    return {"ok": True, "blueprints": blueprints}


@app.post("/api/blueprints/study")
async def blueprint_study(payload: BlueprintStudyRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    items = await db.get_inventory(player_id)
    qty = items.get(payload.item_id, 0)
    item = data.get_item(payload.item_id)
    notice = ""
    ok = False
    if not item or qty <= 0:
        notice = "Чертёж недоступен."
    else:
        recipe_id = recipe_id_for_blueprint(payload.item_id)
        if not recipe_id:
            notice = "Чертёж пока не поддерживается крафтом."
        else:
            unlocked = await db.get_unlocked_recipes(player_id)
            if recipe_id in unlocked or recipe_id in BASE_RECIPE_IDS:
                notice = "Этот чертёж уже изучен."
            else:
                ok_adjust = await db.adjust_inventory(player_id, {payload.item_id: -1})
                if not ok_adjust:
                    notice = "Недостаточно предметов."
                else:
                    await db.unlock_recipe(player_id, recipe_id)
                    recipe = data.get_recipe(recipe_id)
                    recipe_name = recipe.get("name") if recipe else recipe_id
                    notice = f"Чертёж изучен: {recipe_name}."
                    ok = True
    blueprints = await build_blueprint_payload(player_id, 1)
    return {"ok": ok, "message": notice, "blueprints": blueprints}


@app.post("/api/loadout")
async def loadout_state(payload: InitDataRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    loadout = await build_loadout_payload(player_id)
    return {"ok": True, "loadout": loadout}


@app.post("/api/loadout/options")
async def loadout_options(payload: LoadoutOptionsRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    items = await db.get_inventory(player_id)
    options, page, total_pages = collect_equip_options(items, payload.equip_type, payload.page)
    return {
        "ok": True,
        "options": options,
        "page": page,
        "total_pages": total_pages,
        "equip_type": payload.equip_type,
    }


@app.post("/api/loadout/set")
async def loadout_set(payload: LoadoutSetRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    field_map = {
        "armor": "armor_id",
        "weapon": "weapon_id",
        "medkit": "medkit_id",
        "chip": "chip_id",
    }
    field = field_map.get(payload.equip_type)
    notice = ""
    ok = False
    if not field:
        notice = "Неизвестный слот."
    elif not payload.item_id:
        await db.set_loadout(player_id, **{field: None})
        notice = "Слот очищен."
        ok = True
    else:
        item = data.get_item(payload.item_id)
        items = await db.get_inventory(player_id)
        if not item or items.get(payload.item_id, 0) <= 0:
            notice = "Предмет не найден."
        else:
            if payload.equip_type == "armor" and item.get("type") != "armor":
                notice = "Это не броня."
            elif payload.equip_type == "weapon" and item.get("type") != "weapon":
                notice = "Это не оружие."
            elif payload.equip_type == "medkit":
                if item.get("type") != "consumable" or not (item.get("heal") or item.get("evac_bonus")):
                    notice = "Это не расходник."
                else:
                    await db.set_loadout(player_id, **{field: payload.item_id})
                    notice = "Снаряжение обновлено."
                    ok = True
            elif payload.equip_type == "chip":
                if item.get("type") != "augment" or not (
                    item.get("greed_mult") or item.get("evac_bonus") or item.get("damage_bonus")
                ):
                    notice = "Это не аугмент."
                else:
                    await db.set_loadout(player_id, **{field: payload.item_id})
                    notice = "Снаряжение обновлено."
                    ok = True
            else:
                await db.set_loadout(player_id, **{field: payload.item_id})
                notice = "Снаряжение обновлено."
                ok = True
    loadout = await build_loadout_payload(player_id)
    return {"ok": ok, "message": notice, "loadout": loadout}


@app.post("/api/daily_case")
async def daily_case_state(payload: InitDataRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    case_data = await build_case_payload(player_id, chat_id)
    return {"ok": True, "case": case_data}


@app.post("/api/daily_case/open")
async def daily_case_open(payload: DailyCaseOpenRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    today = date.today().isoformat()
    opened = await db.has_daily_case(player_id, chat_id, today)
    if opened:
        return {"ok": False, "message": "Кейс уже открыт.", "case": await build_case_payload(player_id, chat_id)}
    storage_used = await db.get_inventory_count(player_id)
    storage_limit = await db.get_storage_limit(player_id)
    if storage_used + CASE_ITEMS_COUNT > storage_limit:
        return {
            "ok": False,
            "message": "Освободите место в хранилище и попробуйте снова.",
            "case": await build_case_payload(player_id, chat_id),
        }
    pity = await db.get_case_pity(player_id)
    drops, new_pity = roll_daily_case_items(pity)
    if not drops:
        return {"ok": False, "message": "Кейс пуст.", "case": await build_case_payload(player_id, chat_id)}
    add_map: Dict[str, int] = {}
    for item in drops:
        add_map[item["id"]] = add_map.get(item["id"], 0) + 1
    await db.add_inventory_items(player_id, add_map)
    await db.mark_daily_case_opened(player_id, chat_id, today)
    await db.set_case_pity(player_id, new_pity)
    result_items = []
    for item in drops:
        result_items.append(
            {
                "id": item["id"],
                "name": item.get("name", item["id"]),
                "emoji": item.get("emoji") or rarity_emoji(item.get("rarity", "common")),
                "rarity": item.get("rarity", "common"),
                "rare": is_case_rare(item),
            }
        )
    return {
        "ok": True,
        "message": "Кейс открыт.",
        "items": result_items,
        "case": await build_case_payload(player_id, chat_id),
    }


@app.post("/api/warehouse")
async def warehouse_state(payload: InitDataRequest) -> Dict[str, Any]:
    await _authorize(payload)
    chat_id = _require_chat_id(payload)
    warehouse = await build_warehouse_payload(chat_id)
    return {"ok": True, "warehouse": warehouse}


@app.post("/api/rating")
async def rating_state(payload: RatingRequest) -> Dict[str, Any]:
    await _authorize(payload)
    limit = int(payload.limit or RATING_LIMIT)
    limit = max(1, min(50, limit))
    rating = await build_rating_payload(limit)
    return {"ok": True, "rating": rating}


@app.post("/api/season")
async def season_state(payload: InitDataRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    season = await build_season_payload(player_id, chat_id)
    return {"ok": True, "season": season}


@app.post("/api/event")
async def event_state(payload: InitDataRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    event = await build_event_payload(player_id, chat_id)
    return {"ok": True, "event": event}


@app.post("/api/admin/state")
async def admin_state(payload: InitDataRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    web_user = await get_web_user_info(player_id)
    if not _is_admin_email(web_user.get("email") if web_user else None):
        return {"ok": False, "message": "Недостаточно прав."}
    settings = await db.ensure_settings(chat_id)
    return {
        "ok": True,
        "settings": {
            "event_base": settings.get("event_base"),
            "event_greed_mult": settings.get("event_greed_mult"),
            "evac_base": settings.get("evac_base"),
            "evac_greed_penalty": settings.get("evac_greed_penalty"),
            "warehouse_goal": settings.get("warehouse_goal"),
            "event_week_goal": settings.get("event_week_goal"),
            "daily_sell_raidcoin_cap": settings.get(
                "daily_sell_raidcoin_cap", DEFAULTS.daily_sell_raidcoin_cap
            ),
            "daily_sell_count_cap": settings.get(
                "daily_sell_count_cap", DEFAULTS.daily_sell_count_cap
            ),
            "market_listing_cap": settings.get(
                "market_listing_cap", DEFAULTS.market_listing_cap
            ),
            "season_reward_top1": settings.get(
                "season_reward_top1", DEFAULTS.season_reward_top1
            ),
            "season_reward_top2": settings.get(
                "season_reward_top2", DEFAULTS.season_reward_top2
            ),
            "season_reward_top3": settings.get(
                "season_reward_top3", DEFAULTS.season_reward_top3
            ),
        },
    }


@app.post("/api/admin/update")
async def admin_update(payload: AdminUpdateRequest) -> Dict[str, Any]:
    _, player_id = await _authorize(payload)
    chat_id = _require_chat_id(payload)
    web_user = await get_web_user_info(player_id)
    if not _is_admin_email(web_user.get("email") if web_user else None):
        return {"ok": False, "message": "Недостаточно прав."}
    updates: Dict[str, Any] = {}
    for field in (
        "event_base",
        "event_greed_mult",
        "evac_base",
        "evac_greed_penalty",
        "warehouse_goal",
        "event_week_goal",
        "daily_sell_raidcoin_cap",
        "daily_sell_count_cap",
        "market_listing_cap",
        "season_reward_top1",
        "season_reward_top2",
        "season_reward_top3",
    ):
        value = getattr(payload, field)
        if value is not None:
            updates[field] = value
    if updates:
        await db.update_settings(chat_id, **updates)
    settings = await db.ensure_settings(chat_id)
    return {"ok": True, "message": "Настройки обновлены.", "settings": settings}
