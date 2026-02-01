from __future__ import annotations

import asyncio
import html
import json
import math
import random
import secrets
import time
from urllib.parse import parse_qsl, urlencode, urlparse
from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter

from .config import BOT_TOKEN, DEFAULTS, WEB_APP_URL
from .db import Database
from .game import (
    GameData,
    apply_loot,
    calc_evac_chance,
    calc_event_chance,
    calc_points,
    consume_medkit,
    calc_inventory_value,
    format_loot_summary,
    format_item,
    get_storage_page,
    can_craft,
    craft_deltas,
    has_consumable,
    inventory_count,
    normalize_sort,
    pick_random_item,
    rarity_emoji,
    rarity_legend,
    resolve_fight,
    roll_bonus_drop,
    roll_loot_by_rarity,
    RARITY_ORDER,
    SORT_LABELS,
    select_items_by_capacity,
)
from .keyboards import (
    admin_keyboard,
    admin_reset_keyboard,
    announce_cancel_keyboard,
    announce_select_keyboard,
    cleanup_keyboard,
    loot_choice_keyboard,
    menu_keyboard,
    raid_keyboard,
    storage_keyboard,
    storage_confirm_keyboard,
    equip_items_keyboard,
    equip_menu_keyboard,
    craft_keyboard,
    shop_keyboard,
    shop_confirm_keyboard,
    sell_list_keyboard,
    sell_item_keyboard,
    blueprint_keyboard,
)


db = Database()
data = GameData()
dp = Dispatcher()
PANEL_TTL = 180
INFO_TTL = 60
STORAGE_PAGE_SIZE = 10
EQUIP_PAGE_SIZE = 6
SELL_PAGE_SIZE = 8
BLUEPRINT_PAGE_SIZE = 8
EVENT_TOP_LIMIT = 5
EVENT_ANNOUNCE_TTL = 300
EVENT_ANNOUNCE_REPEAT_TTL = 600
EVENT_ANNOUNCE_INTERVAL = 3600
EVENT_ACHIEVEMENT_ID = "first_pioneer"
EVENT_ACHIEVEMENT_TITLE = "Первопроходец"
EVENT_REWARD_BLUEPRINT_ID = "looting_mk3_safekeeper_blueprint"
announce_state: Dict[int, Dict[str, Any]] = {}
event_announce_last: Dict[int, float] = {}

ACTION_COOLDOWNS = {
    "loot": DEFAULTS.cooldown_loot,
    "move": DEFAULTS.cooldown_move,
    "fight": DEFAULTS.cooldown_fight,
    "evac": DEFAULTS.cooldown_evac,
    "medkit": DEFAULTS.cooldown_medkit,
}

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
RC_EMOJI = "\U0001FA99"


def mention(user) -> str:
    name = user.full_name or user.username or "игрок"
    return f'<a href="tg://user?id={user.id}">{html.escape(name)}</a>'


def mention_by_id(user_id: int, name: str) -> str:
    safe_name = html.escape(name or "игрок")
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'


def fmt_rc(amount: int) -> str:
    return f"{amount} {RC_EMOJI}"


def user_display_name(row: Dict[str, Any]) -> str:
    name = row.get("first_name") or row.get("username") or "Игрок"
    last = row.get("last_name") or ""
    full = f"{name} {last}".strip()
    return html.escape(full) if full else "Игрок"


def render_panel(
    user,
    session: Dict[str, Any],
    settings: Dict[str, Any],
    storage_used: int,
    storage_limit: int,
    last_event: Optional[str] = None,
) -> str:
    danger = (
        calc_event_chance(session["greed"], settings)
        if settings.get("events_enabled")
        else 0.0
    )
    evac = calc_evac_chance(session["greed"], effective_evac_bonus(session), settings)
    raid_used = inventory_count(session)
    equip_line = (
        f"Экипировка: броня {int(session['armor_pct']*100)}%, "
        f"оружие +{session['weapon_bonus']}"
    )
    if session.get("damage_bonus"):
        equip_line += f", урон +{int(session['damage_bonus'])}"

    lines = [
        f"🎮 Рейд | {mention(user)}",
        f"Статус: {'Бой' if session['status'] == 'combat' else 'В рейде'}",
        f"HP: {session['hp']}/{session['max_hp']}",
        f"Алчность: {session['greed']} (риск события ~{int(danger*100)}%)",
        f"Шанс эвакуации: {int(evac*100)}%",
        f"Лут (рейд): {format_loot_summary(session)}",
        f"Слоты рейда: {raid_used}/{DEFAULTS.raid_limit}",
        f"Хранилище: {storage_used}/{storage_limit}",
        equip_line,
    ]
    if session.get("hard_mode"):
        penalty = int(float(session.get("evac_penalty", 0)) * 100)
        lines.append(f"Режим: Тяжёлый рейд (эвак -{penalty}%)")
    entry_fee = int(session.get("entry_fee", 0))
    entry_bonus = int(session.get("entry_bonus", 0))
    if entry_fee > 0:
        lines.append(
            f"Ставка: -{entry_fee} очк., при эвакуации +{entry_fee + entry_bonus}"
        )
    chip_id = session.get("chip_id")
    if chip_id:
        chip = data.get_item(chip_id)
        if chip:
            effects = []
            greed_mult = chip.get("greed_mult")
            if isinstance(greed_mult, (int, float)) and greed_mult < 1:
                effects.append(f"-{int((1 - greed_mult) * 100)}% алчн.")
            evac_bonus = chip.get("evac_bonus")
            if isinstance(evac_bonus, (int, float)) and evac_bonus > 0:
                effects.append(f"+{int(evac_bonus * 100)}% эвак.")
            dmg_bonus = chip.get("damage_bonus")
            if isinstance(dmg_bonus, (int, float)) and dmg_bonus > 0:
                effects.append(f"+{int(dmg_bonus)} урона")
            effect_text = f" ({', '.join(effects)})" if effects else ""
            lines.append(f"Аугмент: {format_item(chip)}{effect_text}")
    if effective_evac_bonus(session) > 0:
        lines.append(
            f"Бонус эвакуации: +{int(effective_evac_bonus(session)*100)}%"
        )
    if session["status"] == "combat" and session["enemy"]:
        enemy = session["enemy"]
        lines.append(
            f"⚠️ Враг: {enemy['name']} (HP {enemy['hp_current']}/{enemy['hp']})"
        )
    if last_event:
        lines.append("")
        lines.append(last_event)
    return "\n".join(lines)


def render_rating(rows: list[Dict[str, Any]], champion_id: Optional[int] = None) -> str:
    if not rows:
        return "Рейтинг пуст. Стань первым!"
    name_width = 18

    def truncate(text: str, width: int) -> str:
        if len(text) <= width:
            return text
        if width <= 1:
            return text[:width]
        return text[: width - 1] + "…"

    table_lines = [
        "№  Игрок                Очк  Эвак  Килл  Смрт",
        "────────────────────────────────────────────",
    ]
    for idx, row in enumerate(rows, start=1):
        raw_name = (row.get("first_name") or row.get("username") or "Игрок")
        last = row.get("last_name") or ""
        full_name = f"{raw_name} {last}".strip() or "Игрок"
        name = truncate(full_name, name_width)
        badge = " 🏅" if champion_id and row.get("player_id") == champion_id else ""
        line = (
            f"{idx:>2}  {name:<{name_width}} {row['points']:>4}  {row['extracts']:>4} "
            f"{row['kills']:>4}  {row['deaths']:>4}{badge}"
        )
        table_lines.append(line)
    table = "\n".join(html.escape(line) for line in table_lines)
    return (
        "🏆 <b>Рейтинг (топ-10)</b>\n"
        "<b>Очк</b> — очки | <b>Эвак</b> — эвакуации | <b>Килл</b> — убийства | <b>Смрт</b> — смерти\n"
        + table
    )


def format_short_date(value: Optional[str]) -> str:
    if not value:
        return "—"
    try:
        return date.fromisoformat(value).strftime("%d.%m")
    except ValueError:
        return value


def build_webapp_url(base_url: str, chat_id: int, thread_id: int) -> str:
    if not base_url:
        return ""
    url = urlparse(base_url)
    if url.scheme != "https":
        return ""
    query = dict(parse_qsl(url.query))
    query.update({"chat_id": str(chat_id), "thread_id": str(thread_id)})
    return url._replace(query=urlencode(query)).geturl()


def render_admin(settings: Dict[str, Any]) -> str:
    events_state = "ВКЛ" if settings["events_enabled"] else "ВЫКЛ"
    event_week_state = "ВКЛ" if settings.get("event_week_active") else "ВЫКЛ"
    event_period = ""
    if settings.get("event_week_active"):
        start = format_short_date(settings.get("event_week_start"))
        end = format_short_date(settings.get("event_week_end"))
        event_period = f" ({start}–{end})"
    return (
        "⚙️ Админ-панель\n"
        f"События: {events_state}\n"
        f"Событие недели: {event_week_state}{event_period}\n"
        f"Базовый риск: {settings['event_base']:.2f}\n"
        f"Множитель алчности: {settings['event_greed_mult']:.4f}\n"
        f"Базовая эвакуация: {settings['evac_base']:.2f}\n"
        f"Падение эвакуации: {settings['evac_greed_penalty']:.4f}\n"
        f"Цель склада: {settings.get('warehouse_goal', DEFAULTS.warehouse_goal)}\n"
        f"Цель события (ценн.): {settings.get('event_week_goal', DEFAULTS.event_week_goal)}"
    )


def storage_upgrade_cost(current_limit: int) -> int:
    base = DEFAULTS.storage_limit
    step = DEFAULTS.storage_upgrade_step
    level = max(0, (current_limit - base) // step)
    return DEFAULTS.storage_upgrade_base_cost + level * DEFAULTS.storage_upgrade_cost_step


def can_upgrade_storage(current_limit: int) -> bool:
    return current_limit + DEFAULTS.storage_upgrade_step <= DEFAULTS.storage_upgrade_max


def build_storage_view(
    user,
    items: Dict[str, int],
    sort_key: str,
    page: int,
    storage_limit: int,
    points: int,
    raidcoins: int,
    notice: Optional[str] = None,
) -> Tuple[str, int, int, str]:
    lines, page, total_pages, sort_key = get_storage_page(
        items, data, sort_key, page, STORAGE_PAGE_SIZE
    )
    used = sum(items.values())
    total_value = calc_inventory_value(items, data)
    sort_label = SORT_LABELS.get(sort_key, sort_key)
    text_lines = [
        f"🧰 Хранилище | {mention(user)}",
        f"Слоты: {used}/{storage_limit}",
        f"Очки: {points}",
        f"{RC_EMOJI}: {raidcoins}",
        f"Суммарная ценность: {total_value}",
        f"Сортировка: {sort_label}",
        f"Страница: {page}/{total_pages}",
        "",
    ]
    text_lines.extend(lines)

    if can_upgrade_storage(storage_limit):
        cost = storage_upgrade_cost(storage_limit)
        text_lines.append("")
        text_lines.append(
            f"Улучшение: +{DEFAULTS.storage_upgrade_step} слотов за {cost} очк."
        )
    else:
        text_lines.append("")
        text_lines.append("Лимит хранилища максимальный.")

    if notice:
        text_lines.append("")
        text_lines.append(notice)

    return "\n".join(text_lines), page, total_pages, sort_key


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


def build_blueprint_view(
    user,
    items: Dict[str, int],
    unlocked: set[str],
    page: int,
    sort_key: str,
    notice: Optional[str] = None,
) -> Tuple[str, list[tuple[str, str]], int]:
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
                "unlocked": recipe_id in unlocked,
                "item": item,
                "recipe_id": recipe_id,
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
    page_entries = entries[start:end]

    lines = [
        f"📘 Чертежи | {mention(user)}",
        f"Доступно: {total}",
        f"Страница: {page}/{total_pages}",
        "",
    ]
    if not entries:
        lines.append("Чертежей с рецептами нет.")
    else:
        for entry in page_entries:
            status = "✅" if entry["unlocked"] else "📘"
            label = format_item(entry["item"])
            suffix = " — изучен" if entry["unlocked"] else ""
            lines.append(f"{status} {label} x{entry['qty']}{suffix}")
    if unsupported:
        lines.append("")
        lines.append(f"В хранилище есть ещё {unsupported} чертеж(ей) без рецептов.")
    if notice:
        lines.append("")
        lines.append(notice)

    buttons: list[tuple[str, str]] = []
    for entry in page_entries:
        if entry["unlocked"]:
            continue
        buttons.append((f"Изучить: {entry['name']}", entry["id"]))
    return "\n".join(lines), buttons, total_pages


def is_case_rare(item: Dict[str, Any]) -> bool:
    if item.get("blueprint") or item.get("type") == "blueprint":
        return True
    return item.get("rarity") in CASE_GUARANTEE_RARITIES


def build_case_pool() -> tuple[list[Dict[str, Any]], list[float]]:
    pool = [
        item for item in data.loot if item.get("type") != "junk"
    ]
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


async def get_admin_bound_chats(bot: Bot, user_id: int) -> list[Dict[str, Any]]:
    bound = await db.get_bound_threads()
    result = []
    for row in bound:
        chat_id = int(row["chat_id"])
        thread_id = row.get("thread_id")
        if not thread_id:
            continue
        if not await is_admin(bot, chat_id, user_id):
            continue
        title = str(chat_id)
        try:
            chat = await bot.get_chat(chat_id)
            if chat.title:
                title = chat.title
        except Exception:
            pass
        result.append({"chat_id": chat_id, "thread_id": thread_id, "title": title})
    return result


async def get_available_recipes(player_id: int) -> list[Dict[str, Any]]:
    unlocked = await db.get_unlocked_recipes(player_id)
    return [
        recipe
        for recipe in data.list_recipes()
        if recipe.get("id") in BASE_RECIPE_IDS or recipe.get("id") in unlocked
    ]


def build_shop_buttons(offers: Optional[Dict[str, Any]], user_id: int) -> list[tuple[str, str]]:
    buttons: list[tuple[str, str]] = []
    if not offers:
        return buttons
    for offer in offers.get("items", []):
        item = data.get_item(offer["item_id"])
        if item:
            is_blueprint = item.get("blueprint") or item.get("type") == "blueprint"
            prefix = "Купить чертёж" if is_blueprint else "Купить"
            label = f"{prefix}: {item.get('emoji','')} {item['name']}"
        else:
            label = "Купить предмет"
        buttons.append((label.strip(), f"shop:offer:{offer['item_id']}:{user_id}"))
    recipe_offer = offers.get("recipe")
    if recipe_offer:
        recipe = data.get_recipe(recipe_offer["recipe_id"])
        label = f"Купить рецепт: {recipe['name']}" if recipe else "Купить рецепт дня"
        buttons.append((label, f"shop:recipe:{recipe_offer['recipe_id']}:{user_id}"))
    return buttons


def render_loot_choice(user, item: Dict[str, Any]) -> str:
    return (
        f"🎯 {mention(user)} нашел {format_item(item)}.\n"
        "Решите: взять или оставить."
    )


def get_pending_item(session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not session.get("pending_loot"):
        return None
    item_id = session["pending_loot"][0]
    return data.get_item(item_id)


def equip_type_label(equip_type: str) -> str:
    return {
        "armor": "Броня",
        "weapon": "Оружие",
        "medkit": "Расходник",
        "chip": "Аугмент",
    }.get(equip_type, equip_type)


def format_loadout_item(item_id: Optional[str]) -> str:
    if not item_id:
        return "нет"
    item = data.get_item(item_id)
    return format_item(item) if item else item_id


def build_loadout_view(user, loadout: Dict[str, Optional[str]]) -> str:
    return (
        f"🎒 Снаряжение | {mention(user)}\n"
        f"Броня: {format_loadout_item(loadout.get('armor_id'))}\n"
        f"Оружие: {format_loadout_item(loadout.get('weapon_id'))}\n"
        f"Расходник: {format_loadout_item(loadout.get('medkit_id'))}\n"
        f"Аугмент: {format_loadout_item(loadout.get('chip_id'))}"
    )


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


def build_sell_entries(
    items: Dict[str, int], sort_key: str, page: int
) -> Tuple[list[Dict[str, Any]], int, int, str]:
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
    total_pages = max(1, math.ceil(total_entries / SELL_PAGE_SIZE))
    page = max(1, min(page, total_pages))
    start = (page - 1) * SELL_PAGE_SIZE
    end = start + SELL_PAGE_SIZE
    page_entries = entries[start:end]
    return page_entries, page, total_pages, sort_key


def build_sell_view(
    user,
    entries: list[Dict[str, Any]],
    page: int,
    total_pages: int,
    sort_key: str,
    raidcoins: int,
    notice: Optional[str] = None,
) -> str:
    lines = [
        f"💰 Продажа | {mention(user)}",
        f"{RC_EMOJI}: {raidcoins}",
        f"Сортировка: {SORT_LABELS.get(sort_key, sort_key)}",
        f"Страница: {page}/{total_pages}",
        f"Комиссия: {int(round((1 - DEFAULTS.sell_mult) * 100))}%",
        "",
    ]
    if not entries:
        lines.append("Нечего продавать.")
    else:
        for entry in entries:
            item = data.get_item(entry["id"]) or {}
            emoji = entry.get("emoji") or rarity_emoji(entry["rarity"])
            unit_price = sell_price(item, 1)
            lines.append(
                f"{emoji} {entry['name']} x{entry['qty']} (цена {fmt_rc(unit_price)})"
            )
    if notice:
        lines.append("")
        lines.append(notice)
    return "\n".join(lines)


def build_warehouse_view(
    user,
    items: Dict[str, int],
    goal: int,
    order: Optional[Dict[str, Any]] = None,
    order_progress: int = 0,
    top_contrib: Optional[Dict[str, Any]] = None,
) -> str:
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
    goal = max(1, int(goal))
    progress_pct = int(round(min(1.0, total_items / goal) * 100))
    lines = [
        f"🏢 Общий склад | {mention(user)}",
        f"Цель склада: {total_items}/{goal} ({progress_pct}%)",
        f"Суммарная ценность: {total_value}",
    ]
    if top_contrib:
        name = (
            (top_contrib.get("first_name") or top_contrib.get("username") or "Игрок")
            if isinstance(top_contrib, dict)
            else "Игрок"
        )
        user_id = int(top_contrib.get("tg_id") or 0)
        value_total = int(top_contrib.get("value_total") or 0)
        lines.append(
            f"🏅 Лидер склада: {mention_by_id(user_id, name)} — {value_total} ценн."
        )
    if order and order.get("order_item_id") and order.get("order_target"):
        item = data.get_item(order["order_item_id"]) or {}
        item_name = item.get("name", order["order_item_id"])
        emoji = item.get("emoji") or rarity_emoji(item.get("rarity", "common"))
        target = int(order.get("order_target") or 0)
        reward = int(order.get("order_reward") or DEFAULTS.daily_order_reward)
        bonus = int(order.get("order_bonus") or DEFAULTS.daily_order_bonus)
        order_pct = int(round(min(1.0, order_progress / max(1, target)) * 100))
        lines.extend(
            [
                "",
                f"📦 Заказ дня: {emoji} {item_name}",
                f"Прогресс: {order_progress}/{target} ({order_pct}%)",
                f"Награда: +{reward} {RC_EMOJI} за предмет, бонус +{bonus} {RC_EMOJI}",
            ]
        )
    lines.append("")
    if not entries:
        lines.append("Склад пуст.")
    else:
        lines.append("Топ предметов:")
        for entry in entries[:10]:
            lines.append(f"{entry['emoji']} {entry['name']} x{entry['qty']}")
    return "\n".join(lines)


def build_equip_list(
    items: Dict[str, int],
    equip_type: str,
    page: int,
) -> Tuple[str, list[tuple[str, str]], int]:
    type_map = {
        "armor": "armor",
        "weapon": "weapon",
        "medkit": "consumable",
        "chip": "augment",
    }
    item_type = type_map.get(equip_type)
    candidates = []
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
        candidates.append((item_id, qty, item))
    candidates.sort(key=lambda x: (-int(x[2].get("value", 0)), x[2]["name"].lower()))
    total = len(candidates)
    total_pages = max(1, math.ceil(total / EQUIP_PAGE_SIZE))
    page = max(1, min(page, total_pages))
    start = (page - 1) * EQUIP_PAGE_SIZE
    end = start + EQUIP_PAGE_SIZE
    page_items = candidates[start:end]

    labels = []
    lines = [f"Выберите: {equip_type_label(equip_type)}"]
    if not page_items:
        lines.append("Нет подходящих предметов.")
    else:
        for item_id, qty, item in page_items:
            label = f"{item.get('emoji','')} {item['name']} x{qty}"
            labels.append((label.strip(), item_id))
        lines.append(f"Страница: {page}/{total_pages}")
    return "\n".join(lines), labels, total_pages


def cooldown_remaining(session: Dict[str, Any], action: str, now: float) -> int:
    cooldowns = session.get("cooldowns") or {}
    until = cooldowns.get(action, 0)
    return max(0, int(until - now + 0.999))


def set_cooldown(session: Dict[str, Any], action: str, now: float) -> None:
    duration = ACTION_COOLDOWNS.get(action, 0)
    if duration <= 0:
        return
    session.setdefault("cooldowns", {})[action] = now + duration


def add_greed(session: Dict[str, Any], amount: int) -> int:
    mult = float(session.get("greed_mult", 1.0))
    delta = max(0, int(round(amount * mult)))
    session["greed"] += delta
    return delta


def effective_evac_bonus(session: Dict[str, Any]) -> float:
    return float(session.get("evac_bonus", 0)) - float(session.get("evac_penalty", 0))


def shop_tax_multiplier(purchases_today: int) -> float:
    return 1.0 + purchases_today * DEFAULTS.shop_tax_step


def apply_hard_loot_bonus(session: Dict[str, Any], items: list[Dict[str, Any]]) -> bool:
    if not session.get("hard_mode"):
        return False
    if not items:
        return False
    if random.random() >= DEFAULTS.hard_raid_loot_bonus_chance:
        return False
    items.append(data.roll_loot())
    return True


def format_ingredients(ingredients: Dict[str, Any]) -> str:
    parts = []
    for item_id, qty in ingredients.items():
        item = data.get_item(item_id)
        name = item["name"] if item else item_id
        parts.append(f"{name} x{qty}")
    return ", ".join(parts)


async def schedule_delete(bot: Bot, chat_id: int, message_id: int, delay: int = 60) -> None:
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def _markup_equal(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return a.model_dump() == b.model_dump()
    except Exception:
        return False


async def safe_edit_text(
    message: Message,
    text: str,
    reply_markup=None,
    parse_mode: Optional[str] = None,
) -> str:
    if parse_mode == ParseMode.HTML and message.html_text:
        same_text = message.html_text == text
    else:
        same_text = (message.text or "") == text
    same_markup = _markup_equal(message.reply_markup, reply_markup)
    if same_text and same_markup:
        return "same"
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return "edited"
    except TelegramRetryAfter as e:
        await asyncio.sleep(int(e.retry_after))
        try:
            await message.edit_text(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )
            return "edited"
        except TelegramBadRequest as e2:
            if "message is not modified" in str(e2).lower():
                return "same"
            if "message to edit not found" in str(e2).lower():
                return "missing"
            raise
        except TelegramNetworkError:
            return "network"
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return "same"
        if "message to edit not found" in str(e).lower():
            return "missing"
        raise
    except TelegramNetworkError:
        return "network"


async def answer_auto_delete(
    message: Message,
    text: str,
    reply_markup=None,
    parse_mode: Optional[str] = None,
    delay: int = 60,
) -> Message:
    msg = await message.answer(
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
    if delay > 0:
        asyncio.create_task(
            schedule_delete(message.bot, msg.chat.id, msg.message_id, delay=delay)
        )
    return msg


async def ensure_bound_thread(cb: CallbackQuery) -> Optional[Dict[str, Any]]:
    settings = await db.ensure_settings(cb.message.chat.id)
    if not settings.get("thread_id"):
        await cb.answer("Бот не привязан. Админ: /bind в нужной теме.", show_alert=True)
        return None
    if cb.message.message_thread_id != settings["thread_id"]:
        await cb.answer("Бот работает в другой теме.", show_alert=True)
        return None
    return settings


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


async def normalize_event_settings(
    chat_id: int,
    settings: Dict[str, Any],
    bot: Optional[Bot] = None,
) -> Dict[str, Any]:
    return await finish_event_if_needed(bot, chat_id, settings)


async def get_active_event(
    chat_id: int, bot: Optional[Bot] = None
) -> Optional[Dict[str, Any]]:
    settings = await db.ensure_settings(chat_id)
    settings = await finish_event_if_needed(bot, chat_id, settings)
    if not settings.get("event_week_active"):
        return None
    end_date = parse_iso_date(settings.get("event_week_end"))
    if not end_date:
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


async def event_announce_loop(bot: Bot) -> None:
    while True:
        await asyncio.sleep(60)
        try:
            settings_list = await db.get_active_event_settings()
        except Exception:
            continue
        now = time.time()
        for settings in settings_list:
            chat_id = int(settings.get("chat_id") or 0)
            if not chat_id:
                continue
            settings = await finish_event_if_needed(bot, chat_id, settings)
            if not settings.get("event_week_active"):
                continue
            last_sent = event_announce_last.get(chat_id, 0)
            if now - last_sent < EVENT_ANNOUNCE_INTERVAL:
                continue
            event_id = settings.get("event_week_id") or settings.get("event_week_start")
            if not event_id:
                await db.update_settings(chat_id, event_week_active=0)
                event_announce_last.pop(chat_id, None)
                continue
            event = {
                "id": str(event_id),
                "start": settings.get("event_week_start"),
                "end": settings.get("event_week_end"),
                "goal": int(settings.get("event_week_goal") or DEFAULTS.event_week_goal),
            }
            await send_event_announcement(
                bot,
                chat_id,
                None,
                event,
                pin=False,
                auto_delete=True,
                delete_delay=EVENT_ANNOUNCE_REPEAT_TTL,
            )
            event_announce_last[chat_id] = now


async def send_event_announcement(
    bot: Bot,
    chat_id: int,
    thread_id: Optional[int],
    event: Dict[str, Any],
    *,
    pin: bool = False,
    auto_delete: bool = False,
    delete_delay: int = EVENT_ANNOUNCE_TTL,
) -> None:
    start = format_short_date(event.get("start"))
    end = format_short_date(event.get("end"))
    goal = int(event.get("goal") or DEFAULTS.event_week_goal)
    reward_line = format_event_reward_line()
    text = (
        "📣 <b>Старт события: Контракт ARC — Неделя поставок</b>\n"
        f"Период: {start}–{end}\n"
        f"Цель события: {goal} ценн.\n"
        f"Заказ дня: награды x{DEFAULTS.event_order_mult:g}\n"
        f"{reward_line}\n"
        "Сдача предметов: Хранилище → Продать\n"
        "Следить за прогрессом: кнопка «Событие»"
    )
    try:
        kwargs = {"parse_mode": ParseMode.HTML}
        if thread_id is not None:
            kwargs["message_thread_id"] = thread_id
        msg = await bot.send_message(chat_id, text, **kwargs)
    except Exception:
        return
    if pin:
        try:
            await bot.pin_chat_message(chat_id, msg.message_id)
        except Exception:
            pass
    if auto_delete:
        asyncio.create_task(
            schedule_delete(bot, chat_id, msg.message_id, delay=delete_delay)
        )


def format_event_reward_line() -> str:
    reward_label = "чертёж Добыча 3 (Хранитель) тут и в игре"
    return f"Награда лидеру: ачивка «{EVENT_ACHIEVEMENT_TITLE}», {reward_label}"


async def award_event_winner(chat_id: int, event_id: str) -> Optional[Dict[str, Any]]:
    if not event_id:
        return None
    top = await db.get_event_top(chat_id, event_id, 1)
    if not top:
        return None
    winner = top[0]
    player_id = int(winner.get("player_id") or 0)
    if player_id:
        if data.get_item(EVENT_REWARD_BLUEPRINT_ID):
            await db.add_inventory_items(player_id, {EVENT_REWARD_BLUEPRINT_ID: 1})
        await db.add_achievement(player_id, EVENT_ACHIEVEMENT_ID)
    return winner


async def send_event_finish_announcement(
    bot: Optional[Bot],
    chat_id: int,
    winner: Optional[Dict[str, Any]],
) -> None:
    if not bot:
        return
    reward_line = format_event_reward_line()
    if winner:
        raw_name = (winner.get("first_name") or winner.get("username") or "Игрок")
        last = winner.get("last_name") or ""
        name = f"{raw_name} {last}".strip() or "Игрок"
        user_id = int(winner.get("tg_id") or 0)
        display_name = mention_by_id(user_id, name) if user_id else html.escape(name)
        text = (
            "🏁 <b>Событие завершено!</b>\n"
            f"Победитель: {display_name}\n"
            f"{reward_line}"
        )
    else:
        text = (
            "🏁 <b>Событие завершено!</b>\n"
            "Победитель не определён.\n"
            f"{reward_line}"
        )
    try:
        await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
    except Exception:
        pass


async def finish_event_if_needed(
    bot: Optional[Bot],
    chat_id: int,
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    if not settings.get("event_week_active"):
        return settings
    end_date = parse_iso_date(settings.get("event_week_end"))
    if not end_date or date.today() <= end_date:
        return settings
    event_id = settings.get("event_week_id") or settings.get("event_week_start")
    if not event_id:
        settings = await db.update_settings(chat_id, event_week_active=0)
        event_announce_last.pop(chat_id, None)
        return settings
    if not settings.get("event_week_awarded"):
        winner = await award_event_winner(chat_id, str(event_id))
        await send_event_finish_announcement(bot, chat_id, winner)
        settings = await db.update_settings(
            chat_id, event_week_active=0, event_week_awarded=1
        )
    else:
        settings = await db.update_settings(chat_id, event_week_active=0)
    event_announce_last.pop(chat_id, None)
    return settings


async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in ("administrator", "creator")


async def handle_death(
    cb: CallbackQuery,
    session: Dict[str, Any],
    player_id: int,
    reason: str,
) -> None:
    insurance_note = ""
    stake_lost = int(session.get("entry_fee", 0)) + int(session.get("entry_bonus", 0))
    equip_lost = []
    for item_id in (session.get("armor_item_id"), session.get("weapon_item_id")):
        if not item_id:
            continue
        item = data.get_item(item_id)
        equip_lost.append(format_item(item) if item else item_id)
    await clear_lost_loadout_items(
        player_id, session.get("armor_item_id"), session.get("weapon_item_id")
    )
    tokens = await db.get_insurance_tokens(player_id)
    if tokens > 0 and session["inventory"]:
        storage_used = await db.get_inventory_count(player_id)
        storage_limit = await db.get_storage_limit(player_id)
        if storage_used < storage_limit:
            item_id = pick_random_item(session["inventory"])
            if item_id:
                item = data.get_item(item_id)
                await db.add_inventory_items(player_id, {item_id: 1})
                await db.adjust_insurance_tokens(player_id, -1)
                saved_label = format_item(item) if item else item_id
                insurance_note = f"\nСтраховка сработала: сохранен {saved_label}."
        else:
            insurance_note = "\nСтраховка не сработала: хранилище заполнено."
    await db.adjust_rating(
        player_id,
        points=-DEFAULTS.death_penalty,
        deaths=1,
    )
    await db.delete_session(session["id"])
    stake_note = f"\nСтавка сгорела: -{stake_lost} очк." if stake_lost > 0 else ""
    equip_note = f"\nСнаряжение потеряно: {', '.join(equip_lost)}." if equip_lost else ""
    text = (
        f"💀 {mention(cb.from_user)} погиб. {reason}\n"
        f"Лут потерян.{insurance_note}{stake_note}{equip_note}\n"
        "Сообщение удалится через 60 секунд."
    )
    result = await safe_edit_text(
        cb.message,
        text,
        reply_markup=cleanup_keyboard(cb.from_user.id).as_markup(),
        parse_mode=ParseMode.HTML,
    )
    if result in ("missing", "network"):
        await answer_auto_delete(
            cb.message,
            text,
            reply_markup=cleanup_keyboard(cb.from_user.id).as_markup(),
            parse_mode=ParseMode.HTML,
            delay=60,
        )
    asyncio.create_task(
        schedule_delete(cb.bot, cb.message.chat.id, cb.message.message_id, delay=60)
    )


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


async def sync_loadout_if_idle(player_id: int, chat_id: int) -> Dict[str, Optional[str]]:
    loadout = await db.get_loadout(player_id)
    session = await db.get_active_session(player_id, chat_id)
    if session:
        return loadout
    items = await db.get_inventory(player_id)
    updates: Dict[str, Optional[str]] = {}
    for slot in ("armor", "weapon", "medkit", "chip"):
        key = f"{slot}_id"
        item_id = loadout.get(key)
        if item_id and items.get(item_id, 0) <= 0:
            updates[key] = None
    if updates:
        await db.set_loadout(player_id, **updates)
        for key in updates:
            loadout[key] = None
    return loadout


async def handle_extract_success(
    cb: CallbackQuery,
    session: Dict[str, Any],
    player_id: int,
) -> None:
    points = calc_points(session)
    stake_return = int(session.get("entry_fee", 0)) + int(session.get("entry_bonus", 0))
    total_points = points + stake_return
    storage_limit = await db.get_storage_limit(player_id)
    storage_used = await db.get_inventory_count(player_id)
    equip_returned = []
    equip_dropped = []
    dropped_armor = None
    dropped_weapon = None
    for item_id in (session.get("armor_item_id"), session.get("weapon_item_id")):
        if not item_id:
            continue
        item = data.get_item(item_id)
        label = format_item(item) if item else item_id
        if storage_used < storage_limit:
            await db.add_inventory_items(player_id, {item_id: 1})
            storage_used += 1
            equip_returned.append(label)
        else:
            equip_dropped.append(label)
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
    await db.delete_session(session["id"])
    saved_count = sum(kept.values())
    dropped_count = sum(dropped.values())
    inventory_note = (
        f"Хранилище: +{saved_count} предметов."
        if dropped_count == 0
        else f"Хранилище: +{saved_count}, потеряно из-за лимита: {dropped_count}."
    )
    equip_note = ""
    if equip_returned:
        equip_note = f"\nСнаряжение возвращено: {', '.join(equip_returned)}."
    if equip_dropped:
        equip_note += f"\nСнаряжение потеряно (склад полон): {', '.join(equip_dropped)}."
    stake_note = f"\nСтавка возвращена: +{stake_return} очк." if stake_return > 0 else ""
    text = (
        f"✅ Эвакуация успешна, {mention(cb.from_user)}!\n"
        f"Очки: +{points}{stake_note}\n"
        f"Лут: {format_loot_summary(session)}\n"
        f"Убийства: {session['kills']}\n"
        f"{inventory_note}{equip_note}\n"
        "Сообщение удалится через 60 секунд."
    )
    result = await safe_edit_text(
        cb.message,
        text,
        reply_markup=cleanup_keyboard(cb.from_user.id).as_markup(),
        parse_mode=ParseMode.HTML,
    )
    if result in ("missing", "network"):
        await answer_auto_delete(
            cb.message,
            text,
            reply_markup=cleanup_keyboard(cb.from_user.id).as_markup(),
            parse_mode=ParseMode.HTML,
            delay=60,
        )
    asyncio.create_task(
        schedule_delete(cb.bot, cb.message.chat.id, cb.message.message_id, delay=60)
    )


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
    if kind == "boss":
        boss_id = event.get("enemy_id", "arc_collector")
        enemy = data.get_enemy(boss_id) or data.roll_enemy()
        enemy["hp_current"] = enemy["hp"]
        session["enemy"] = enemy
        session["status"] = "combat"
        return (
            session,
            f"🛑 Сигнал высокого уровня! Появился {enemy['name']} — элитная цель.",
            False,
            [],
            0,
        )
    if kind == "storm":
        dmg = random.randint(event.get("dmg_min", 6), event.get("dmg_max", 18))
        reduced = max(1, int(dmg * (1 - session["armor_pct"])))
        session["hp"] -= reduced
        died = session["hp"] <= 0
        return (
            session,
            f"🌩 Электрошквал прорвал сектор: -{reduced} HP.",
            died,
            [],
            0,
        )
    if kind == "anomaly":
        roll = random.random()
        if roll < 0.35:
            heal = random.randint(event.get("heal_min", 6), event.get("heal_max", 16))
            session["hp"] = min(session["max_hp"], session["hp"] + heal)
            return (
                session,
                f"🌀 Аномалия стабилизировала пульс: +{heal} HP.",
                False,
                [],
                0,
            )
        if roll < 0.7:
            dmg = random.randint(event.get("dmg_min", 6), event.get("dmg_max", 18))
            reduced = max(1, int(dmg * (1 - session["armor_pct"])))
            session["hp"] -= reduced
            died = session["hp"] <= 0
            return (
                session,
                f"🌀 Аномалия ударила по экипировке: -{reduced} HP.",
                died,
                [],
                0,
            )
        if roll < 0.85:
            delta = random.randint(
                event.get("greed_down_min", 8), event.get("greed_down_max", 18)
            )
            session["greed"] = max(0, session["greed"] - delta)
            return (
                session,
                f"🌀 Аномалия сбила шум: алчность -{delta}.",
                False,
                [],
                0,
            )
        delta = random.randint(
            event.get("greed_up_min", 6), event.get("greed_up_max", 16)
        )
        add_greed(session, delta)
        return (
            session,
            f"🌀 Аномалия усилила риск: алчность +{delta}.",
            False,
            [],
            0,
        )
    if kind == "quiet_zone":
        delta = random.randint(
            event.get("greed_reduce_min", 8), event.get("greed_reduce_max", 20)
        )
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


@dp.message(Command("announce"))
async def announce_command(message: Message) -> None:
    if message.chat.type != "private":
        await message.reply("Команда /announce доступна только в личных сообщениях с ботом.")
        return
    chats = await get_admin_bound_chats(message.bot, message.from_user.id)
    if not chats:
        await message.reply("Нет доступных привязанных тем. Проверьте /bind и права администратора.")
        return
    if len(chats) == 1:
        target = chats[0]
        announce_state[message.from_user.id] = {
            "chat_id": target["chat_id"],
            "thread_id": target["thread_id"],
        }
        await message.reply(
            f"Отправьте текст анонса для «{target['title']}».",
            reply_markup=announce_cancel_keyboard().as_markup(),
        )
        return
    buttons = [(c["chat_id"], c["title"]) for c in chats]
    await message.reply(
        "Куда отправить анонс?",
        reply_markup=announce_select_keyboard(buttons).as_markup(),
    )


@dp.callback_query(F.data.startswith("announce:"))
async def announce_callback(cb: CallbackQuery) -> None:
    if cb.message.chat.type != "private":
        await cb.answer("Доступно только в личных сообщениях.", show_alert=True)
        return
    parts = cb.data.split(":")
    action = parts[1]
    if action == "cancel":
        announce_state.pop(cb.from_user.id, None)
        await safe_edit_text(
            cb.message,
            "Отменено.",
            reply_markup=None,
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return
    if action == "select":
        chat_id = int(parts[2])
        chats = await get_admin_bound_chats(cb.bot, cb.from_user.id)
        target = next((c for c in chats if c["chat_id"] == chat_id), None)
        if not target:
            await cb.answer("Нет доступа к этой теме.", show_alert=True)
            return
        announce_state[cb.from_user.id] = {
            "chat_id": target["chat_id"],
            "thread_id": target["thread_id"],
        }
        await safe_edit_text(
            cb.message,
            f"Отправьте текст анонса для «{target['title']}».",
            reply_markup=announce_cancel_keyboard().as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return
    await cb.answer()


@dp.message(F.chat.type == "private")
async def announce_input(message: Message) -> None:
    state = announce_state.get(message.from_user.id)
    if not state:
        return
    text = (message.text or "").strip()
    if not text:
        await message.reply("Нужен текст анонса. Отправьте сообщение или /cancel.")
        return
    if text.lower() in ("/cancel", "отмена"):
        announce_state.pop(message.from_user.id, None)
        await message.reply("Отменено.")
        return
    try:
        await message.bot.send_message(
            state["chat_id"],
            text,
            message_thread_id=state["thread_id"],
        )
        await message.reply("Анонс отправлен.")
    except Exception:
        await message.reply("Не удалось отправить анонс. Проверьте права бота.")
    announce_state.pop(message.from_user.id, None)


@dp.message(Command("bind"))
async def bind_thread(message: Message) -> None:
    if not message.message_thread_id:
        await message.reply("Команду /bind нужно вызывать внутри темы.")
        return
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.reply("Нужны права администратора.")
        return
    await db.set_thread(message.chat.id, message.message_thread_id)
    webapp_url = build_webapp_url(
        WEB_APP_URL, message.chat.id, message.message_thread_id
    )
    msg = await message.answer(
        "Тема привязана. Используйте кнопки ниже.",
        reply_markup=menu_keyboard(webapp_url).as_markup(),
    )
    try:
        await message.bot.pin_chat_message(message.chat.id, msg.message_id)
    except Exception:
        pass


@dp.callback_query(F.data.startswith("menu:"))
async def menu_handler(cb: CallbackQuery) -> None:
    settings = await ensure_bound_thread(cb)
    if not settings:
        return
    action = cb.data.split(":")[1]
    player_id = await db.upsert_player(cb.from_user)
    rating = await db.get_rating(player_id)
    storage_used = await db.get_inventory_count(player_id)
    storage_limit = int(rating.get("storage_limit", DEFAULTS.storage_limit))
    points = int(rating.get("points", 0))
    raidcoins = int(rating.get("raidcoins", 0))
    if action == "enter":
        session = await db.get_active_session(player_id, cb.message.chat.id)
        if session:
            await cb.answer(
                "Вы уже в рейде. Используйте кнопку «Мой рейд».",
                show_alert=True,
            )
            return
        today = date.today().isoformat()
        raids_today = await db.get_daily_raids(player_id, cb.message.chat.id, today)
        if raids_today >= DEFAULTS.daily_raid_limit:
            await cb.answer(
                f"Дневной лимит рейдов исчерпан ({DEFAULTS.daily_raid_limit}). Попробуйте завтра.",
                show_alert=True,
            )
            return
        entry_fee = DEFAULTS.raid_entry_fee
        loadout = await db.get_loadout(player_id)
        storage_items = await db.get_inventory(player_id)
        equip_notes = []
        hard_mode = random.random() < DEFAULTS.hard_raid_chance
        evac_penalty = DEFAULTS.hard_raid_evac_penalty if hard_mode else 0.0
        entry_bonus = DEFAULTS.raid_entry_bonus if entry_fee > 0 else 0
        if entry_fee > 0 and points < entry_fee:
            entry_fee = 0
            entry_bonus = 0
            equip_notes.append("Недостаточно очков для ставки — рейд без ставки.")
        session = {
            "id": secrets.token_hex(4),
            "player_id": player_id,
            "chat_id": cb.message.chat.id,
            "thread_id": cb.message.message_thread_id,
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
            "evac_penalty": evac_penalty,
            "entry_fee": entry_fee,
            "entry_bonus": entry_bonus,
            "status": "explore",
            "enemy": None,
            "evac_bonus": 0.0,
            "panel_message_id": None,
            "pending_loot": [],
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
                    equip_notes.append(f"Броня взята в рейд: {format_item(item)}")
                else:
                    equip_notes.append("Броня недоступна.")
        weapon_id = loadout.get("weapon_id")
        if weapon_id and storage_items.get(weapon_id, 0) > 0:
            item = data.get_item(weapon_id)
            if item and item.get("type") == "weapon":
                ok = await db.adjust_inventory(player_id, {weapon_id: -1})
                if ok:
                    session["weapon_item_id"] = weapon_id
                    session["weapon_bonus"] = int(item.get("weapon_bonus", 0))
                    equip_notes.append(f"Оружие взято в рейд: {format_item(item)}")
                else:
                    equip_notes.append("Оружие недоступно.")
        medkit_id = loadout.get("medkit_id")
        if medkit_id and storage_items.get(medkit_id, 0) > 0:
            ok = await db.adjust_inventory(player_id, {medkit_id: -1})
            if ok:
                session["inventory"][medkit_id] = 1
                equip_notes.append("Расходник добавлен.")
            else:
                equip_notes.append("Расходник недоступен.")
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
                    equip_notes.append(f"Аугмент: {format_item(chip)}")
                else:
                    equip_notes.append("Аугмент недоступен.")
        storage_used = await db.get_inventory_count(player_id)
        created = await db.create_session(session)
        if not created:
            restore_items = {}
            if session.get("armor_item_id"):
                restore_items[session["armor_item_id"]] = (
                    restore_items.get(session["armor_item_id"], 0) + 1
                )
            if session.get("weapon_item_id"):
                restore_items[session["weapon_item_id"]] = (
                    restore_items.get(session["weapon_item_id"], 0) + 1
                )
            if session.get("chip_id"):
                restore_items[session["chip_id"]] = (
                    restore_items.get(session["chip_id"], 0) + 1
                )
            for item_id, qty in session.get("inventory", {}).items():
                if qty > 0:
                    restore_items[item_id] = restore_items.get(item_id, 0) + qty
            if restore_items:
                await db.add_inventory_items(player_id, restore_items)
            await cb.answer(
                "Вы уже в рейде. Используйте кнопку «Мой рейд».",
                show_alert=True,
            )
            return
        if entry_fee > 0:
            await db.adjust_rating(player_id, points=-entry_fee)
            equip_notes.append(
                f"Ставка: -{entry_fee} очк. (эвак +{entry_fee + entry_bonus})."
            )
        if hard_mode:
            equip_notes.append("Режим: тяжёлый рейд (лут ↑, эвак ↓).")
        await db.increment_daily_raids(player_id, cb.message.chat.id, today)
        await db.adjust_rating(player_id, raids=1)
        entry_note = "Вы вошли в рейд."
        if equip_notes:
            entry_note += " " + " ".join(equip_notes)
        text = render_panel(
            cb.from_user, session, settings, storage_used, storage_limit, entry_note
        )
        msg = await answer_auto_delete(
            cb.message,
            text,
            reply_markup=raid_keyboard(
                session, cb.from_user.id, False, session.get("cooldowns")
            ).as_markup(),
            parse_mode=ParseMode.HTML,
            delay=PANEL_TTL,
        )
        session["panel_message_id"] = msg.message_id
        await db.update_session(session)
        await cb.answer()
        return
    if action == "status":
        session = await db.get_active_session(player_id, cb.message.chat.id)
        if not session:
            await cb.answer("У вас нет активного рейда.", show_alert=True)
            return
        if session.get("pending_loot"):
            pending_item = get_pending_item(session)
            if pending_item:
                text = "⏳ Незавершенный выбор лута.\n" + render_loot_choice(
                    cb.from_user, pending_item
                )
                await answer_auto_delete(
                    cb.message,
                    text,
                    reply_markup=loot_choice_keyboard(
                        session["id"], cb.from_user.id
                    ).as_markup(),
                    parse_mode=ParseMode.HTML,
                    delay=PANEL_TTL,
                )
                await cb.answer()
                return
            session["pending_loot"] = []
            await db.update_session(session)
            last_event = "Предыдущий выбор лута сброшен."
        else:
            last_event = None
        text = render_panel(
            cb.from_user, session, settings, storage_used, storage_limit, last_event
        )
        msg = await answer_auto_delete(
            cb.message,
            text,
            reply_markup=raid_keyboard(
                session,
                cb.from_user.id,
                has_consumable(session, data),
                session.get("cooldowns"),
            ).as_markup(),
            parse_mode=ParseMode.HTML,
            delay=PANEL_TTL,
        )
        session["panel_message_id"] = msg.message_id
        await db.update_session(session)
        await cb.answer()
        return
    if action == "rating":
        rows = await db.get_top_ratings()
        top = await db.get_warehouse_top_contributor(cb.message.chat.id)
        champion_id = top.get("player_id") if top else None
        text = render_rating(rows, champion_id)
        await answer_auto_delete(
            cb.message,
            text,
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return
    if action == "daily":
        today = date.today().isoformat()
        raids_today = await db.get_daily_raids(player_id, cb.message.chat.id, today)
        remaining = max(0, DEFAULTS.daily_raid_limit - raids_today)
        text = (
            f"📊 Рейды сегодня | {mention(cb.from_user)}\n"
            f"Использовано: {raids_today}/{DEFAULTS.daily_raid_limit}\n"
            f"Осталось: {remaining}"
        )
        await answer_auto_delete(
            cb.message,
            text,
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return
    if action == "case":
        today = date.today().isoformat()
        opened = await db.has_daily_case(player_id, cb.message.chat.id, today)
        if opened:
            await answer_auto_delete(
                cb.message,
                f"📦 Ежедневный кейс уже получен сегодня | {mention(cb.from_user)}",
                parse_mode=ParseMode.HTML,
                delay=INFO_TTL,
            )
            await cb.answer()
            return
        free_slots = storage_limit - storage_used
        if free_slots < CASE_ITEMS_COUNT:
            await answer_auto_delete(
                cb.message,
                (
                    f"📦 Ежедневный кейс | {mention(cb.from_user)}\n"
                    f"Нужно {CASE_ITEMS_COUNT} свободных слота. Сейчас свободно: {free_slots}.\n"
                    "Освободите место и откройте кейс снова."
                ),
                parse_mode=ParseMode.HTML,
                delay=INFO_TTL,
            )
            await cb.answer()
            return
        pity = await db.get_case_pity(player_id)
        drops, new_pity = roll_daily_case_items(pity)
        if not drops:
            await answer_auto_delete(
                cb.message,
                f"📦 Ежедневный кейс | {mention(cb.from_user)}\nСписок лута пуст.",
                parse_mode=ParseMode.HTML,
                delay=INFO_TTL,
            )
            await cb.answer()
            return
        counts: Dict[str, int] = {}
        for item in drops:
            counts[item["id"]] = counts.get(item["id"], 0) + 1
        await db.add_inventory_items(player_id, counts)
        await db.mark_daily_case_opened(player_id, cb.message.chat.id, today)
        await db.set_case_pity(player_id, new_pity)
        rare_hits = [item for item in drops if is_case_rare(item)]
        lines = [
            "╔══════════════════════════════╗",
            f"🎁 <b>ЕЖЕДНЕВНЫЙ КЕЙС</b> | {mention(cb.from_user)}",
            "╚══════════════════════════════╝",
        ]
        if rare_hits:
            lines.append("🌟 <b>РЕДКАЯ НАГРАДА!</b> 🌟")
        lines.append("------------------------------")
        lines.append("Выпало:")
        for item in drops:
            marker = "💎" if is_case_rare(item) else "•"
            lines.append(f"{marker} {format_item(item)}")
        lines.append("------------------------------")
        if any(item.get("blueprint") or item.get("type") == "blueprint" for item in drops):
            lines.append("")
            lines.append("📘 Чертёж найден! Изучить: Хранилище → Чертежи.")
        lines.append("")
        lines.append("Легенда: 💎 редкое/чертёж, • обычное.")
        text = "\n".join(lines)
        await answer_auto_delete(
            cb.message,
            text,
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return
    if action == "lore":
        text = (
            f"📜 Лор и правила | {mention(cb.from_user)}\n"
            "Город живёт на руинах старых секторов, где автономные машины ARC до сих пор охраняют своё.\n"
            "Вы — рейдер. Входите в сектор, собираете трофеи, сражаетесь и пытаетесь эвакуироваться.\n\n"
            "💠 Цель: копить очки, держать лидерство и выживать.\n"
            "⚠️ Алчность повышает риск событий — чем глубже, тем опаснее.\n"
            "🎒 Лут сохраняется только после успешной эвакуации.\n"
            "💳 Ставка списывается при входе и возвращается с бонусом при эвакуации.\n"
            "🛒 Магазин обновляется раз в сутки и имеет налог на покупки.\n"
            "🧠 Аугменты дают временные бафы только на текущий рейд."
        )
        await answer_auto_delete(
            cb.message,
            text,
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return
    if action == "inventory":
        items = await db.get_inventory(player_id)
        text, page, total_pages, sort_key = build_storage_view(
            cb.from_user,
            items,
            "rarity",
            1,
            storage_limit,
            points,
            raidcoins,
        )
        await answer_auto_delete(
            cb.message,
            text,
            reply_markup=storage_keyboard(
                page, total_pages, sort_key, cb.from_user.id, can_upgrade_storage(storage_limit)
            ).as_markup(),
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return
    if action == "warehouse":
        items = await db.get_warehouse(cb.message.chat.id)
        order = await get_daily_order(cb.message.chat.id)
        today = date.today().isoformat()
        order_progress = 0
        if order.get("order_item_id"):
            order_progress = await db.get_daily_order_progress(
                cb.message.chat.id, today, order["order_item_id"]
            )
        goal = int(settings.get("warehouse_goal", DEFAULTS.warehouse_goal))
        total_items = sum(items.values())
        if total_items > goal:
            step = max(1, DEFAULTS.warehouse_goal_step)
            new_goal = int(math.ceil(total_items / step) * step)
            if new_goal > goal:
                settings = await db.update_settings(
                    cb.message.chat.id, warehouse_goal=new_goal
                )
                goal = new_goal
        top = await db.get_warehouse_top_contributor(cb.message.chat.id)
        text = build_warehouse_view(
            cb.from_user, items, goal, order, order_progress, top
        )
        await answer_auto_delete(
            cb.message,
            text,
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return
    if action == "event":
        event = await get_active_event(cb.message.chat.id, cb.bot)
        if not event:
            text = (
                f"📣 Событие | {mention(cb.from_user)}\n"
                "Сейчас нет активного события.\n"
                "Админ может запустить его в админ-панели."
            )
            await answer_auto_delete(
                cb.message,
                text,
                parse_mode=ParseMode.HTML,
                delay=INFO_TTL,
            )
            await cb.answer()
            return
        totals = await db.get_event_totals(cb.message.chat.id, event["id"])
        top = await db.get_event_top(cb.message.chat.id, event["id"], EVENT_TOP_LIMIT)
        player = await db.get_event_player(cb.message.chat.id, event["id"], player_id)
        start = format_short_date(event.get("start"))
        end = format_short_date(event.get("end"))
        end_date = parse_iso_date(event.get("end"))
        days_left = (end_date - date.today()).days + 1 if end_date else 0
        goal = max(1, int(event.get("goal") or DEFAULTS.event_week_goal))
        value_total = int(totals.get("value_total", 0))
        items_total = int(totals.get("items_total", 0))
        progress_pct = int(round(min(1.0, value_total / goal) * 100))
        lines = [
            f"📣 <b>Контракт ARC: Неделя поставок</b> | {mention(cb.from_user)}",
            f"Период: {start}–{end} (осталось {days_left} дн.)",
            f"Прогресс: {value_total}/{goal} ценн. ({progress_pct}%)",
            f"Сдано предметов: {items_total}",
            f"Заказ дня: награды x{DEFAULTS.event_order_mult:g}",
            format_event_reward_line(),
            "Сдача идёт через Хранилище → Продать.",
        ]
        if top:
            lines.append("")
            lines.append("Топ вкладов:")
            for idx, row in enumerate(top, start=1):
                raw_name = (row.get("first_name") or row.get("username") or "Игрок")
                last = row.get("last_name") or ""
                name = f"{raw_name} {last}".strip() or "Игрок"
                user_id = int(row.get("tg_id") or 0)
                value = int(row.get("value_total") or 0)
                display_name = mention_by_id(user_id, name) if user_id else html.escape(name)
                lines.append(f"{idx}. {display_name} — {value} ценн.")
        if player:
            lines.append("")
            lines.append(
                f"Твой вклад: {int(player.get('value_total') or 0)} ценн., {int(player.get('items_total') or 0)} предметов."
            )
        text = "\n".join(lines)
        await answer_auto_delete(
            cb.message,
            text,
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return
    if action == "rarity":
        await answer_auto_delete(
            cb.message,
            rarity_legend(),
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return
    if action == "equip":
        loadout = await sync_loadout_if_idle(player_id, cb.message.chat.id)
        text = build_loadout_view(cb.from_user, loadout)
        await answer_auto_delete(
            cb.message,
            text,
            reply_markup=equip_menu_keyboard(cb.from_user.id).as_markup(),
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return
    if action == "craft":
        items = await db.get_inventory(player_id)
        recipes = await get_available_recipes(player_id)
        lines = [f"🛠 Крафт | {mention(cb.from_user)}"]
        for recipe in recipes:
            ok = "✅" if can_craft(items, recipe) else "❌"
            ing = format_ingredients(recipe["ingredients"])
            out = recipe["output"]["item_id"]
            out_item = data.get_item(out)
            out_name = out_item["name"] if out_item else out
            lines.append(f"{ok} {recipe['name']}: {out_name} ({ing})")
        text = "\n".join(lines)
        await answer_auto_delete(
            cb.message,
            text,
            reply_markup=craft_keyboard(recipes, cb.from_user.id).as_markup(),
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return
    if action == "shop":
        insurance = await db.get_insurance_tokens(player_id)
        offers = await get_daily_shop(cb.message.chat.id)
        today = date.today().isoformat()
        purchases_today = await db.get_daily_shop_purchases(
            player_id, cb.message.chat.id, today
        )
        unlocked = await db.get_unlocked_recipes(player_id)
        recipe_offer = offers.get("recipe") if offers else None
        recipe_owned = bool(
            recipe_offer
            and recipe_offer.get("recipe_id") in unlocked | BASE_RECIPE_IDS
        )
        text = build_shop_view(
            cb.from_user,
            points,
            raidcoins,
            storage_limit,
            insurance,
            offers,
            recipe_owned,
            purchases_today,
            None,
        )
        offer_buttons = build_shop_buttons(offers, cb.from_user.id)
        await answer_auto_delete(
            cb.message,
            text,
            reply_markup=shop_keyboard(cb.from_user.id, offer_buttons).as_markup(),
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return


@dp.callback_query(F.data.startswith("admin:"))
async def admin_handler(cb: CallbackQuery) -> None:
    settings = await ensure_bound_thread(cb)
    if not settings:
        return
    settings = await normalize_event_settings(cb.message.chat.id, settings, cb.bot)
    if not await is_admin(cb.bot, cb.message.chat.id, cb.from_user.id):
        await cb.answer("Нужны права администратора.", show_alert=True)
        return
    notice = None
    parts = cb.data.split(":")
    if parts[1] == "panel":
        text = render_admin(settings)
        await answer_auto_delete(
            cb.message,
            text,
            reply_markup=admin_keyboard(settings).as_markup(),
            parse_mode=ParseMode.HTML,
            delay=INFO_TTL,
        )
        await cb.answer()
        return
    if parts[1] == "reset_rating":
        text = render_admin(settings) + "\n\nПодтвердить очистку рейтинга?"
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=admin_reset_keyboard().as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return
    if parts[1] == "reset_confirm":
        await db.reset_ratings()
        text = render_admin(settings)
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=admin_keyboard(settings).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer("Рейтинг очищен.")
        return
    if parts[1] == "reset_cancel":
        text = render_admin(settings)
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=admin_keyboard(settings).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer("Отменено.")
        return
    if parts[1] == "events" and parts[2] == "toggle":
        new_value = 0 if settings["events_enabled"] else 1
        settings = await db.update_settings(cb.message.chat.id, events_enabled=new_value)
    elif parts[1] == "event" and parts[2] == "start":
        if settings.get("event_week_active"):
            await cb.answer("Событие уже активно.")
            return
        start_date = date.today()
        end_date = start_date + timedelta(days=max(1, DEFAULTS.event_week_days) - 1)
        event_id = start_date.isoformat()
        goal = int(settings.get("event_week_goal") or DEFAULTS.event_week_goal)
        settings = await db.update_settings(
            cb.message.chat.id,
            event_week_active=1,
            event_week_id=event_id,
            event_week_start=start_date.isoformat(),
            event_week_end=end_date.isoformat(),
            event_week_goal=goal,
            event_week_awarded=0,
        )
        await send_event_announcement(
            cb.bot,
            cb.message.chat.id,
            None,
            {"start": start_date.isoformat(), "end": end_date.isoformat(), "goal": goal},
            pin=True,
            auto_delete=False,
        )
        event_announce_last[cb.message.chat.id] = time.time()
        notice = "Событие запущено на неделю."
    elif parts[1] == "event" and parts[2] == "stop":
        if not settings.get("event_week_active"):
            await cb.answer("Событие не активно.")
            return
        settings = await db.update_settings(cb.message.chat.id, event_week_active=0)
        event_announce_last.pop(cb.message.chat.id, None)
        notice = "Событие остановлено."
    elif parts[1] == "event_goal":
        delta = DEFAULTS.event_week_goal_step if parts[2] == "inc" else -DEFAULTS.event_week_goal_step
        current = int(settings.get("event_week_goal") or DEFAULTS.event_week_goal)
        new_value = max(100, current + delta)
        settings = await db.update_settings(cb.message.chat.id, event_week_goal=new_value)
    elif parts[1] == "event_base":
        delta = 0.02 if parts[2] == "inc" else -0.02
        new_value = max(0.05, min(0.5, settings["event_base"] + delta))
        settings = await db.update_settings(cb.message.chat.id, event_base=new_value)
    elif parts[1] == "greed_mult":
        delta = 0.0005 if parts[2] == "inc" else -0.0005
        new_value = max(0.0005, min(0.01, settings["event_greed_mult"] + delta))
        settings = await db.update_settings(cb.message.chat.id, event_greed_mult=new_value)
    elif parts[1] == "evac_base":
        delta = 0.02 if parts[2] == "inc" else -0.02
        new_value = max(0.5, min(0.95, settings["evac_base"] + delta))
        settings = await db.update_settings(cb.message.chat.id, evac_base=new_value)
    elif parts[1] == "evac_penalty":
        delta = 0.0005 if parts[2] == "inc" else -0.0005
        new_value = max(0.0005, min(0.02, settings["evac_greed_penalty"] + delta))
        settings = await db.update_settings(
            cb.message.chat.id, evac_greed_penalty=new_value
        )
    elif parts[1] == "warehouse_goal":
        delta = DEFAULTS.warehouse_goal_step if parts[2] == "inc" else -DEFAULTS.warehouse_goal_step
        current = int(settings.get("warehouse_goal", DEFAULTS.warehouse_goal))
        new_value = max(100, min(10000, current + delta))
        settings = await db.update_settings(cb.message.chat.id, warehouse_goal=new_value)
    text = render_admin(settings)
    await safe_edit_text(
        cb.message,
        text,
        reply_markup=admin_keyboard(settings).as_markup(),
        parse_mode=ParseMode.HTML,
    )
    if notice:
        await cb.answer(notice)
    else:
        await cb.answer()


@dp.callback_query(F.data.startswith("storage:"))
async def storage_handler(cb: CallbackQuery) -> None:
    settings = await ensure_bound_thread(cb)
    if not settings:
        return
    parts = cb.data.split(":")
    action = parts[1]

    if action == "page":
        page = int(parts[2])
        sort_key = parts[3]
        user_id = int(parts[4])
    elif action == "sort":
        sort_key = parts[2]
        user_id = int(parts[3])
        page = 1
    elif action == "upgrade":
        page = int(parts[2])
        sort_key = parts[3]
        user_id = int(parts[4])
    elif action == "confirm":
        page = int(parts[2])
        sort_key = parts[3]
        user_id = int(parts[4])
    elif action == "cancel":
        page = int(parts[2])
        sort_key = parts[3]
        user_id = int(parts[4])
    else:
        await cb.answer()
        return

    if cb.from_user.id != user_id:
        await cb.answer("Это не ваше хранилище.", show_alert=True)
        return

    player_id = await db.get_player_id(cb.from_user.id)
    if not player_id:
        player_id = await db.upsert_player(cb.from_user)

    rating = await db.get_rating(player_id)
    points = int(rating.get("points", 0))
    raidcoins = int(rating.get("raidcoins", 0))
    storage_limit = int(rating.get("storage_limit", DEFAULTS.storage_limit))
    notice = None

    if action == "upgrade":
        if not can_upgrade_storage(storage_limit):
            notice = "Лимит хранилища максимальный."
        else:
            cost = storage_upgrade_cost(storage_limit)
            if points < cost:
                notice = f"Нужно {cost} очк. для улучшения."
            else:
                items = await db.get_inventory(player_id)
                text, page, total_pages, sort_key = build_storage_view(
                    cb.from_user, items, sort_key, page, storage_limit, points, raidcoins
                )
                await safe_edit_text(
                    cb.message,
                    f"{text}\n\nПодтвердить улучшение за {cost} очк.?",
                    reply_markup=storage_confirm_keyboard(
                        page, sort_key, cb.from_user.id
                    ).as_markup(),
                    parse_mode=ParseMode.HTML,
                )
                await cb.answer()
                return
    elif action == "confirm":
        if not can_upgrade_storage(storage_limit):
            notice = "Лимит хранилища максимальный."
        else:
            cost = storage_upgrade_cost(storage_limit)
            if points < cost:
                notice = f"Нужно {cost} очк. для улучшения."
            else:
                await db.adjust_rating(player_id, points=-cost)
                await db.update_storage_limit(
                    player_id, storage_limit + DEFAULTS.storage_upgrade_step
                )
                rating = await db.get_rating(player_id)
                points = int(rating.get("points", 0))
                raidcoins = int(rating.get("raidcoins", 0))
                storage_limit = int(
                    rating.get("storage_limit", DEFAULTS.storage_limit)
                )
                notice = f"Хранилище улучшено до {storage_limit} слотов."
    elif action == "cancel":
        notice = "Улучшение отменено."

    items = await db.get_inventory(player_id)
    text, page, total_pages, sort_key = build_storage_view(
        cb.from_user, items, sort_key, page, storage_limit, points, raidcoins, notice
    )
    await safe_edit_text(
        cb.message,
        text,
        reply_markup=storage_keyboard(
            page, total_pages, sort_key, cb.from_user.id, can_upgrade_storage(storage_limit)
        ).as_markup(),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("blueprint:"))
async def blueprint_handler(cb: CallbackQuery) -> None:
    settings = await ensure_bound_thread(cb)
    if not settings:
        return
    parts = cb.data.split(":")
    action = parts[1]

    if action in ("open", "page"):
        page = int(parts[2])
        sort_key = parts[3]
        user_id = int(parts[4])
    elif action == "study":
        item_id = parts[2]
        page = int(parts[3])
        sort_key = parts[4]
        user_id = int(parts[5])
    elif action == "back":
        page = int(parts[2])
        sort_key = parts[3]
        user_id = int(parts[4])
    else:
        await cb.answer()
        return
    if cb.from_user.id != user_id:
        await cb.answer("Это не ваши чертежи.", show_alert=True)
        return

    player_id = await db.get_player_id(cb.from_user.id)
    if not player_id:
        player_id = await db.upsert_player(cb.from_user)

    if action == "back":
        rating = await db.get_rating(player_id)
        points = int(rating.get("points", 0))
        raidcoins = int(rating.get("raidcoins", 0))
        storage_limit = int(rating.get("storage_limit", DEFAULTS.storage_limit))
        items = await db.get_inventory(player_id)
        text, page, total_pages, sort_key = build_storage_view(
            cb.from_user, items, sort_key, page, storage_limit, points, raidcoins
        )
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=storage_keyboard(
                page, total_pages, sort_key, cb.from_user.id, can_upgrade_storage(storage_limit)
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    items = await db.get_inventory(player_id)
    unlocked = await db.get_unlocked_recipes(player_id)
    notice = None

    if action == "study":
        qty = items.get(item_id, 0)
        item = data.get_item(item_id)
        if not item or qty <= 0:
            notice = "Чертёж недоступен."
        else:
            recipe_id = recipe_id_for_blueprint(item_id)
            if not recipe_id:
                notice = "Чертёж пока не поддерживается крафтом."
            elif recipe_id in unlocked:
                notice = "Этот чертёж уже изучен."
            else:
                ok = await db.adjust_inventory(player_id, {item_id: -1})
                if not ok:
                    notice = "Недостаточно предметов."
                else:
                    await db.unlock_recipe(player_id, recipe_id)
                    unlocked = await db.get_unlocked_recipes(player_id)
                    recipe = data.get_recipe(recipe_id)
                    recipe_name = recipe.get("name") if recipe else recipe_id
                    notice = f"Чертёж изучен: {recipe_name}."
        items = await db.get_inventory(player_id)

    text, buttons, total_pages = build_blueprint_view(
        cb.from_user, items, unlocked, page, sort_key, notice
    )
    await safe_edit_text(
        cb.message,
        text,
        reply_markup=blueprint_keyboard(
            buttons, page, total_pages, sort_key, cb.from_user.id
        ).as_markup(),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("sell:"))
async def sell_handler(cb: CallbackQuery) -> None:
    settings = await ensure_bound_thread(cb)
    if not settings:
        return
    parts = cb.data.split(":")
    action = parts[1]
    user_id = int(parts[-1])
    if cb.from_user.id != user_id:
        await cb.answer("Это не ваше хранилище.", show_alert=True)
        return

    player_id = await db.get_player_id(cb.from_user.id)
    if not player_id:
        player_id = await db.upsert_player(cb.from_user)

    rating = await db.get_rating(player_id)
    points = int(rating.get("points", 0))
    raidcoins = int(rating.get("raidcoins", 0))
    storage_limit = int(rating.get("storage_limit", DEFAULTS.storage_limit))

    if action in ("open", "page"):
        page = int(parts[2])
        sort_key = parts[3]
        items = await db.get_inventory(player_id)
        entries, page, total_pages, sort_key = build_sell_entries(items, sort_key, page)
        labels = []
        for entry in entries:
            item = data.get_item(entry["id"])
            emoji = entry.get("emoji") or rarity_emoji(entry["rarity"])
            labels.append((f"{emoji} {entry['name']} x{entry['qty']}", entry["id"]))
        text = build_sell_view(
            cb.from_user, entries, page, total_pages, sort_key, raidcoins
        )
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=sell_list_keyboard(
                page, total_pages, sort_key, cb.from_user.id, labels
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    if action == "item":
        item_id = parts[2]
        page = int(parts[3])
        sort_key = parts[4]
        items = await db.get_inventory(player_id)
        qty = items.get(item_id, 0)
        item = data.get_item(item_id)
        if not item or not is_sellable(item) or qty <= 0:
            await cb.answer("Предмет недоступен.", show_alert=True)
            return
        unit_price = sell_price(item, 1)
        total_price = sell_price(item, qty)
        text = (
            f"💰 Продажа | {mention(cb.from_user)}\n"
            f"{format_item(item)}\n"
            f"Количество: {qty}\n"
        f"Цена за 1: {fmt_rc(unit_price)}\n"
        f"Цена за все: {fmt_rc(total_price)}"
        )
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=sell_item_keyboard(
                item_id, qty, page, sort_key, cb.from_user.id
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    if action == "do":
        item_id = parts[2]
        qty_raw = parts[3]
        page = int(parts[4])
        sort_key = parts[5]
        items = await db.get_inventory(player_id)
        qty_available = items.get(item_id, 0)
        item = data.get_item(item_id)
        notice = None
        if not item or not is_sellable(item) or qty_available <= 0:
            notice = "Предмет недоступен."
        else:
            sell_qty = qty_available if qty_raw == "all" else int(qty_raw)
            sell_qty = max(1, min(sell_qty, qty_available))
            price = sell_price(item, sell_qty)
            ok = await db.adjust_inventory(player_id, {item_id: -sell_qty})
            if not ok:
                notice = "Недостаточно предметов."
            else:
                await db.adjust_raidcoins(player_id, price)
                await db.add_warehouse_items(cb.message.chat.id, {item_id: sell_qty})
                contrib_value = int(item.get("value", 0)) * sell_qty
                if contrib_value > 0:
                    await db.add_warehouse_contribution(
                        cb.message.chat.id, player_id, contrib_value, sell_qty
                    )
                event = await get_active_event(cb.message.chat.id, cb.bot)
                if event and contrib_value > 0:
                    await db.add_event_contribution(
                        cb.message.chat.id,
                        event["id"],
                        player_id,
                        contrib_value,
                        sell_qty,
                    )
                today = date.today().isoformat()
                order = await get_daily_order(cb.message.chat.id)
                bonus_text = ""
                reward_total = 0
                if order.get("order_item_id") == item_id and order.get("order_target"):
                    target = int(order.get("order_target") or 0)
                    reward_per = int(order.get("order_reward") or DEFAULTS.daily_order_reward)
                    bonus = int(order.get("order_bonus") or DEFAULTS.daily_order_bonus)
                    if event:
                        reward_per = int(round(reward_per * DEFAULTS.event_order_mult))
                        bonus = int(round(bonus * DEFAULTS.event_order_mult))
                    before = await db.get_daily_order_progress(
                        cb.message.chat.id, today, item_id
                    )
                    after = await db.increment_daily_order_progress(
                        cb.message.chat.id, today, item_id, sell_qty
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
                raidcoins = await db.get_raidcoins(player_id)
                notice = f"Продано: {format_item(item)} x{sell_qty} → +{price} {RC_EMOJI}.{bonus_text}"
        items = await db.get_inventory(player_id)
        entries, page, total_pages, sort_key = build_sell_entries(items, sort_key, page)
        labels = []
        for entry in entries:
            item = data.get_item(entry["id"])
            emoji = entry.get("emoji") or rarity_emoji(entry["rarity"])
            labels.append((f"{emoji} {entry['name']} x{entry['qty']}", entry["id"]))
        text = build_sell_view(
            cb.from_user, entries, page, total_pages, sort_key, raidcoins, notice
        )
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=sell_list_keyboard(
                page, total_pages, sort_key, cb.from_user.id, labels
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    if action == "back":
        page = int(parts[2])
        sort_key = parts[3]
        items = await db.get_inventory(player_id)
        text, page, total_pages, sort_key = build_storage_view(
            cb.from_user,
            items,
            sort_key,
            page,
            storage_limit,
            points,
            raidcoins,
        )
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=storage_keyboard(
                page, total_pages, sort_key, cb.from_user.id, can_upgrade_storage(storage_limit)
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    await cb.answer()


@dp.callback_query(F.data.startswith("equip:"))
async def equip_handler(cb: CallbackQuery) -> None:
    settings = await ensure_bound_thread(cb)
    if not settings:
        return
    parts = cb.data.split(":")
    action = parts[1]
    equip_type = parts[2] if len(parts) > 2 else ""
    user_id = int(parts[-1])
    if cb.from_user.id != user_id:
        await cb.answer("Это не ваше снаряжение.", show_alert=True)
        return

    player_id = await db.get_player_id(cb.from_user.id)
    if not player_id:
        player_id = await db.upsert_player(cb.from_user)

    if action == "type":
        page = 1
        items = await db.get_inventory(player_id)
        text, labels, total_pages = build_equip_list(items, equip_type, page)
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=equip_items_keyboard(
                equip_type, page, total_pages, cb.from_user.id, labels
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    if action == "page":
        page = int(parts[3])
        equip_type = parts[2]
        items = await db.get_inventory(player_id)
        text, labels, total_pages = build_equip_list(items, equip_type, page)
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=equip_items_keyboard(
                equip_type, page, total_pages, cb.from_user.id, labels
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    if action == "set":
        equip_type = parts[2]
        item_id = parts[3]
        key = f"{equip_type}_id"
        await db.set_loadout(player_id, **{key: item_id})
        loadout = await db.get_loadout(player_id)
        text = build_loadout_view(cb.from_user, loadout)
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=equip_menu_keyboard(cb.from_user.id).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer("Снаряжение обновлено.")
        return

    if action == "clear":
        equip_type = parts[2]
        key = f"{equip_type}_id"
        await db.set_loadout(player_id, **{key: None})
        loadout = await db.get_loadout(player_id)
        text = build_loadout_view(cb.from_user, loadout)
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=equip_menu_keyboard(cb.from_user.id).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer("Снаряжение снято.")
        return

@dp.callback_query(F.data.startswith("raid:"))
async def raid_handler(cb: CallbackQuery) -> None:
    settings = await ensure_bound_thread(cb)
    if not settings:
        return
    _, action, session_id, user_id = cb.data.split(":")
    if int(user_id) != cb.from_user.id:
        await cb.answer("Это не ваша сессия.", show_alert=True)
        return
    session = await db.get_session_by_id(session_id)
    if not session:
        await cb.answer("Сессия не найдена.", show_alert=True)
        return
    player_id = await db.get_player_id(cb.from_user.id)
    if player_id != session["player_id"]:
        await cb.answer("Это не ваша сессия.", show_alert=True)
        return

    last_event = None
    storage_used = await db.get_inventory_count(player_id)
    storage_limit = await db.get_storage_limit(player_id)
    now = time.time()

    if action in ACTION_COOLDOWNS:
        remaining = cooldown_remaining(session, action, now)
        if remaining > 0:
            await cb.answer(f"Кулдаун: {remaining} сек.", show_alert=True)
            return

    if session.get("pending_loot") and action not in ("take", "skip"):
        await cb.answer("Сначала решите, взять лут или нет.", show_alert=True)
        return

    if action in ("take", "skip"):
        pending_item = get_pending_item(session)
        if not pending_item:
            await cb.answer("Нет предмета для выбора.", show_alert=True)
            return
        session["pending_loot"] = session.get("pending_loot", [])[1:]
        if action == "take":
            if inventory_count(session) >= DEFAULTS.raid_limit:
                last_event = f"Рейдовый инвентарь заполнен ({DEFAULTS.raid_limit}). Предмет оставлен."
            else:
                session, _ = apply_loot(session, pending_item)
                last_event = f"Вы взяли: {format_item(pending_item)}."
        else:
            last_event = f"Вы оставили: {format_item(pending_item)}."

        await db.update_session(session)
        next_item = get_pending_item(session)
        if next_item:
            await safe_edit_text(
                cb.message,
                render_loot_choice(cb.from_user, next_item),
                reply_markup=loot_choice_keyboard(session["id"], cb.from_user.id).as_markup(),
                parse_mode=ParseMode.HTML,
            )
            await cb.answer()
            return

        text = render_panel(
            cb.from_user, session, settings, storage_used, storage_limit, last_event
        )
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=raid_keyboard(
                session,
                cb.from_user.id,
                has_consumable(session, data),
                session.get("cooldowns"),
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    if action == "medkit":
        set_cooldown(session, "medkit", now)
        add_greed(session, DEFAULTS.greed_medkit)
        session, msg = consume_medkit(session, data)
        last_event = msg or "Аптечек нет."
        await db.update_session(session)
        text = render_panel(
            cb.from_user, session, settings, storage_used, storage_limit, last_event
        )
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=raid_keyboard(
                session,
                cb.from_user.id,
                has_consumable(session, data),
                session.get("cooldowns"),
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    if action == "fight":
        add_greed(session, DEFAULTS.greed_fight)
        enemy = session["enemy"]
        if not enemy:
            await cb.answer("Врага нет.", show_alert=True)
            return
        set_cooldown(session, "fight", now)
        session, fight_log, win = resolve_fight(session, enemy)
        last_event = fight_log
        if session["hp"] <= 0:
            await handle_death(cb, session, player_id, "Поражение в бою.")
            return
        if win:
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
                await safe_edit_text(
                    cb.message,
                    f"{last_event}\n{render_loot_choice(cb.from_user, drops[0])}",
                    reply_markup=loot_choice_keyboard(session["id"], cb.from_user.id).as_markup(),
                    parse_mode=ParseMode.HTML,
                )
                await cb.answer()
                return
        await db.update_session(session)
        text = render_panel(
            cb.from_user, session, settings, storage_used, storage_limit, last_event
        )
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=raid_keyboard(
                session,
                cb.from_user.id,
                has_consumable(session, data),
                session.get("cooldowns"),
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    if session["status"] == "combat":
        await cb.answer("Сначала бой.", show_alert=True)
        return

    if action == "loot":
        set_cooldown(session, "loot", now)
        add_greed(session, DEFAULTS.greed_loot)
        if settings["events_enabled"] and random.random() < calc_event_chance(
            session["greed"], settings
        ):
            event = data.roll_event()
            session, event_text, died, items, cost_points = apply_event(session, event)
            if died:
                await handle_death(cb, session, player_id, event_text)
                return
            if cost_points:
                await db.adjust_rating(player_id, points=-cost_points)
            if items:
                bonus_added = apply_hard_loot_bonus(session, items)
                if bonus_added:
                    event_text += "\n🎯 Тяжёлый рейд: найден дополнительный лут."
                session["pending_loot"] = [item["id"] for item in items]
                await db.update_session(session)
                first_item = get_pending_item(session)
                await safe_edit_text(
                    cb.message,
                    f"{event_text}\n{render_loot_choice(cb.from_user, first_item)}",
                    reply_markup=loot_choice_keyboard(session["id"], cb.from_user.id).as_markup(),
                    parse_mode=ParseMode.HTML,
                )
                await cb.answer()
                return
            last_event = event_text
        else:
            items = [data.roll_loot()]
            bonus_added = apply_hard_loot_bonus(session, items)
            session["pending_loot"] = [item["id"] for item in items]
            await db.update_session(session)
            await safe_edit_text(
                cb.message,
                render_loot_choice(cb.from_user, items[0])
                + ("\n🎯 Тяжёлый рейд: найден дополнительный лут." if bonus_added else ""),
                reply_markup=loot_choice_keyboard(session["id"], cb.from_user.id).as_markup(),
                parse_mode=ParseMode.HTML,
            )
            await cb.answer()
            return
        await db.update_session(session)
        text = render_panel(
            cb.from_user, session, settings, storage_used, storage_limit, last_event
        )
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=raid_keyboard(
                session,
                cb.from_user.id,
                has_consumable(session, data),
                session.get("cooldowns"),
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    if action == "move":
        set_cooldown(session, "move", now)
        add_greed(session, DEFAULTS.greed_move)
        if settings["events_enabled"] and random.random() < calc_event_chance(
            session["greed"], settings
        ):
            event = data.roll_event()
            session, event_text, died, items, cost_points = apply_event(session, event)
            if died:
                await handle_death(cb, session, player_id, event_text)
                return
            if cost_points:
                await db.adjust_rating(player_id, points=-cost_points)
            if items:
                bonus_added = apply_hard_loot_bonus(session, items)
                if bonus_added:
                    event_text += "\n🎯 Тяжёлый рейд: найден дополнительный лут."
                session["pending_loot"] = [item["id"] for item in items]
                await db.update_session(session)
                first_item = get_pending_item(session)
                await safe_edit_text(
                    cb.message,
                    f"{event_text}\n{render_loot_choice(cb.from_user, first_item)}",
                    reply_markup=loot_choice_keyboard(session["id"], cb.from_user.id).as_markup(),
                    parse_mode=ParseMode.HTML,
                )
                await cb.answer()
                return
            last_event = event_text
        else:
            last_event = "Вы продвинулись глубже. Сигнатуры ARC усиливаются."
        await db.update_session(session)
        text = render_panel(
            cb.from_user, session, settings, storage_used, storage_limit, last_event
        )
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=raid_keyboard(
                session,
                cb.from_user.id,
                has_consumable(session, data),
                session.get("cooldowns"),
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return

    if action == "evac":
        set_cooldown(session, "evac", now)
        chance = calc_evac_chance(session["greed"], effective_evac_bonus(session), settings)
        if random.random() < chance:
            await handle_extract_success(cb, session, player_id)
            return
        add_greed(session, DEFAULTS.greed_evac_fail)
        enemy = data.roll_enemy()
        enemy["hp_current"] = enemy["hp"]
        session["enemy"] = enemy
        session["status"] = "combat"
        session["evac_bonus"] = 0.0
        last_event = f"Эвакуация сорвана! Перехват связи — засада: {enemy['name']}."
        await db.update_session(session)
        text = render_panel(
            cb.from_user, session, settings, storage_used, storage_limit, last_event
        )
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=raid_keyboard(
                session,
                cb.from_user.id,
                has_consumable(session, data),
                session.get("cooldowns"),
            ).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return


@dp.callback_query(F.data.startswith("craft:"))
async def craft_handler(cb: CallbackQuery) -> None:
    settings = await ensure_bound_thread(cb)
    if not settings:
        return
    parts = cb.data.split(":")
    action = parts[1]
    recipe_id = parts[2] if len(parts) > 2 else ""
    user_id = int(parts[3]) if len(parts) > 3 else 0
    if cb.from_user.id != user_id:
        await cb.answer("Это не ваш крафт.", show_alert=True)
        return

    player_id = await db.get_player_id(cb.from_user.id)
    if not player_id:
        player_id = await db.upsert_player(cb.from_user)

    available_recipes = await get_available_recipes(player_id)
    available_ids = {recipe["id"] for recipe in available_recipes}

    if action == "make":
        if recipe_id not in available_ids:
            await cb.answer("Рецепт недоступен.", show_alert=True)
            return
        recipe = data.get_recipe(recipe_id)
        if not recipe:
            await cb.answer("Рецепт не найден.", show_alert=True)
            return
        items = await db.get_inventory(player_id)
        if not can_craft(items, recipe):
            await cb.answer("Не хватает ресурсов.", show_alert=True)
            return
        consume, produce = craft_deltas(recipe)
        storage_used = await db.get_inventory_count(player_id)
        storage_limit = await db.get_storage_limit(player_id)
        delta_count = sum(produce.values()) + sum(consume.values())
        if storage_used + delta_count > storage_limit:
            await cb.answer("Хранилище переполнено.", show_alert=True)
            return
        ok = await db.adjust_inventory(player_id, consume)
        if not ok:
            await cb.answer("Не хватает ресурсов.", show_alert=True)
            return
        await db.add_inventory_items(player_id, produce)
        out_item = data.get_item(recipe["output"]["item_id"])
        out_name = out_item["name"] if out_item else recipe["output"]["item_id"]
        notice = f"Скрафчено: {out_name}."
        items = await db.get_inventory(player_id)
        recipes = await get_available_recipes(player_id)
        lines = [f"🛠 Крафт | {mention(cb.from_user)}", notice]
        for r in recipes:
            ok_flag = "✅" if can_craft(items, r) else "❌"
            ing = format_ingredients(r["ingredients"])
            out = r["output"]["item_id"]
            out_item = data.get_item(out)
            out_name = out_item["name"] if out_item else out
            lines.append(f"{ok_flag} {r['name']}: {out_name} ({ing})")
        text = "\n".join(lines)
        await safe_edit_text(
            cb.message,
            text,
            reply_markup=craft_keyboard(recipes, cb.from_user.id).as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await cb.answer()
        return


def build_shop_view(
    user,
    points: int,
    raidcoins: int,
    storage_limit: int,
    insurance: int,
    offers: Optional[Dict[str, Any]],
    recipe_owned: bool,
    purchases_today: int,
    notice: Optional[str],
) -> str:
    upgrade_cost = storage_upgrade_cost(storage_limit)
    can_upgrade = can_upgrade_storage(storage_limit)
    tax_mult = shop_tax_multiplier(purchases_today)
    tax_pct = int(round((tax_mult - 1.0) * 100))
    medkit_price = int(round(SHOP_PRICES["medkit"] * tax_mult))
    evac_price = int(round(SHOP_PRICES["evac_beacon"] * tax_mult))
    insurance_price = int(round(SHOP_PRICES["insurance"] * tax_mult))
    medkit_item = data.get_item(SHOP_ITEM_IDS["medkit"])
    evac_item = data.get_item(SHOP_ITEM_IDS["evac_beacon"])
    medkit_label = format_item(medkit_item) if medkit_item else "Расходник"
    evac_label = format_item(evac_item) if evac_item else "Эвак-устройство"
    lines = [
        f"🛒 Магазин | {mention(user)}",
        f"Очки: {points}",
        f"{RC_EMOJI}: {raidcoins}",
        f"Слоты склада: {storage_limit}",
        f"Страховка: {insurance} (лимит {DEFAULTS.insurance_max_tokens})",
        f"Покупок сегодня: {purchases_today}/{DEFAULTS.shop_daily_limit} (налог +{tax_pct}%)",
        "Обновление витрины: раз в сутки",
        "",
        f"{medkit_label} — {medkit_price} {RC_EMOJI}.",
        f"{evac_label} — {evac_price} {RC_EMOJI}.",
        f"Страховка — {insurance_price} {RC_EMOJI}.",
    ]
    if purchases_today >= DEFAULTS.shop_daily_limit:
        lines.append("Лимит покупок исчерпан до завтра.")
    if offers:
        lines.append("")
        lines.append("🎯 Витрина дня:")
        for idx, offer in enumerate(offers.get("items", []), start=1):
            item = data.get_item(offer["item_id"])
            label = format_item(item) if item else offer["item_id"]
            offer_price = int(round(offer["price"] * tax_mult))
            lines.append(f"{idx}. {label} — {offer_price} очк.")
        recipe_offer = offers.get("recipe")
        if recipe_offer:
            recipe = data.get_recipe(recipe_offer["recipe_id"])
            recipe_name = recipe["name"] if recipe else recipe_offer["recipe_id"]
            owned_note = " (уже изучен)" if recipe_owned else ""
            recipe_price = int(round(recipe_offer["price"] * tax_mult))
            lines.append(
                f"Рецепт дня: {recipe_name} — {recipe_price} очк.{owned_note}"
            )
    if can_upgrade:
        lines.append(f"Улучшить склад (+{DEFAULTS.storage_upgrade_step}) — {upgrade_cost} очк.")
    else:
        lines.append("Улучшить склад — недоступно (максимум).")
    if notice:
        lines.append("")
        lines.append(notice)
    return "\n".join(lines)


@dp.callback_query(F.data.startswith("shop:"))
async def shop_handler(cb: CallbackQuery) -> None:
    settings = await ensure_bound_thread(cb)
    if not settings:
        return
    parts = cb.data.split(":")
    action = parts[1]
    user_id = int(parts[-1]) if len(parts) > 2 else 0
    item_id = parts[2] if len(parts) > 2 else ""
    if cb.from_user.id != user_id:
        await cb.answer("Это не ваш магазин.", show_alert=True)
        return

    player_id = await db.get_player_id(cb.from_user.id)
    if not player_id:
        player_id = await db.upsert_player(cb.from_user)

    rating = await db.get_rating(player_id)
    points = int(rating.get("points", 0))
    raidcoins = int(rating.get("raidcoins", 0))
    storage_limit = int(rating.get("storage_limit", DEFAULTS.storage_limit))
    insurance = int(rating.get("insurance_tokens", 0))
    storage_used = await db.get_inventory_count(player_id)
    offers = await get_daily_shop(cb.message.chat.id)
    today = date.today().isoformat()
    purchases_today = await db.get_daily_shop_purchases(
        player_id, cb.message.chat.id, today
    )
    notice = None

    tax_mult = shop_tax_multiplier(purchases_today)
    if action in ("buy", "offer", "recipe") and purchases_today >= DEFAULTS.shop_daily_limit:
        notice = "Лимит покупок на сегодня исчерпан."
    elif action == "buy":
        if item_id == "medkit":
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
                purchases_today = await db.increment_daily_shop_purchases(
                    player_id, cb.message.chat.id, today
                )
                notice = f"{medkit_name} куплен."
        elif item_id == "evac_beacon":
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
                purchases_today = await db.increment_daily_shop_purchases(
                    player_id, cb.message.chat.id, today
                )
                notice = f"{evac_name} куплен."
        elif item_id == "insurance":
            if insurance >= DEFAULTS.insurance_max_tokens:
                notice = f"Лимит страховок: {DEFAULTS.insurance_max_tokens}."
            else:
                price = int(round(SHOP_PRICES["insurance"] * tax_mult))
                if raidcoins < price:
                    notice = f"Недостаточно {RC_EMOJI}."
                else:
                    await db.adjust_raidcoins(player_id, -price)
                    await db.adjust_insurance_tokens(player_id, 1)
                    purchases_today = await db.increment_daily_shop_purchases(
                        player_id, cb.message.chat.id, today
                    )
                    notice = "Страховка куплена."
    elif action == "offer":
        offer_item = None
        for offer in offers.get("items", []):
            if offer.get("item_id") == item_id:
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
                await db.add_inventory_items(player_id, {item_id: 1})
                purchases_today = await db.increment_daily_shop_purchases(
                    player_id, cb.message.chat.id, today
                )
                notice = "Покупка успешна."
    elif action == "recipe":
        recipe_offer = offers.get("recipe") if offers else None
        recipe_id = item_id
        unlocked = await db.get_unlocked_recipes(player_id)
        if not recipe_offer or recipe_offer.get("recipe_id") != recipe_id:
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
                purchases_today = await db.increment_daily_shop_purchases(
                    player_id, cb.message.chat.id, today
                )
                notice = "Рецепт изучен."
    elif action == "upgrade":
        if not can_upgrade_storage(storage_limit):
            notice = "Улучшение недоступно."
        else:
            cost = storage_upgrade_cost(storage_limit)
            if points < cost:
                notice = f"Нужно {cost} очк."
            else:
                unlocked = await db.get_unlocked_recipes(player_id)
                recipe_offer = offers.get("recipe") if offers else None
                recipe_owned = bool(
                    recipe_offer
                    and recipe_offer.get("recipe_id") in unlocked | BASE_RECIPE_IDS
                )
                text = build_shop_view(
                    cb.from_user,
                    points,
                    raidcoins,
                    storage_limit,
                    insurance,
                    offers,
                    recipe_owned,
                    purchases_today,
                    notice,
                )
                await safe_edit_text(
                    cb.message,
                    f"{text}\n\nПодтвердить улучшение за {cost} очк.?",
                    reply_markup=shop_confirm_keyboard(cb.from_user.id).as_markup(),
                    parse_mode=ParseMode.HTML,
                )
                await cb.answer()
                return
    elif action == "confirm":
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
                rating = await db.get_rating(player_id)
                points = int(rating.get("points", 0))
                storage_limit = int(
                    rating.get("storage_limit", DEFAULTS.storage_limit)
                )
                notice = f"Склад улучшен до {storage_limit}."
    elif action == "cancel":
        notice = "Покупка отменена."

    rating = await db.get_rating(player_id)
    points = int(rating.get("points", 0))
    raidcoins = int(rating.get("raidcoins", 0))
    storage_limit = int(rating.get("storage_limit", DEFAULTS.storage_limit))
    insurance = int(rating.get("insurance_tokens", 0))
    unlocked = await db.get_unlocked_recipes(player_id)
    recipe_offer = offers.get("recipe") if offers else None
    recipe_owned = bool(
        recipe_offer and recipe_offer.get("recipe_id") in unlocked | BASE_RECIPE_IDS
    )
    text = build_shop_view(
        cb.from_user,
        points,
        raidcoins,
        storage_limit,
        insurance,
        offers,
        recipe_owned,
        purchases_today,
        notice,
    )
    offer_buttons = build_shop_buttons(offers, cb.from_user.id)
    await safe_edit_text(
        cb.message,
        text,
        reply_markup=shop_keyboard(cb.from_user.id, offer_buttons).as_markup(),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()

@dp.callback_query(F.data.startswith("cleanup:"))
async def cleanup_handler(cb: CallbackQuery) -> None:
    user_id = int(cb.data.split(":")[1])
    if cb.from_user.id != user_id and not await is_admin(
        cb.bot, cb.message.chat.id, cb.from_user.id
    ):
        await cb.answer("Можно удалить только свой отчет.", show_alert=True)
        return
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.answer()


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан. Укажите его в .env")
    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await db.connect()
    await db.init()
    asyncio.create_task(event_announce_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
