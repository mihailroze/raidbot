from __future__ import annotations

import time
from typing import Dict, Optional

from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder


def menu_keyboard(web_app_url: Optional[str] = None) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Войти в рейд", callback_data="menu:enter")
    builder.button(text="Мой рейд", callback_data="menu:status")
    builder.button(text="Рейтинг", callback_data="menu:rating")
    builder.button(text="Рейды сегодня", callback_data="menu:daily")
    builder.button(text="Ежедневный кейс", callback_data="menu:case")
    builder.button(text="Лор", callback_data="menu:lore")
    builder.button(text="Хранилище", callback_data="menu:inventory")
    builder.button(text="Общий склад", callback_data="menu:warehouse")
    builder.button(text="Событие", callback_data="menu:event")
    if web_app_url:
        builder.button(text="Открыть приложение", web_app=WebAppInfo(url=web_app_url))
    builder.button(text="Редкости", callback_data="menu:rarity")
    builder.button(text="Снаряжение", callback_data="menu:equip")
    builder.button(text="Крафт", callback_data="menu:craft")
    builder.button(text="Магазин", callback_data="menu:shop")
    builder.button(text="Админ", callback_data="admin:panel")
    if web_app_url:
        builder.adjust(2, 2, 2, 2, 2, 1, 2, 2)
    else:
        builder.adjust(2, 2, 2, 2, 2, 2, 2)
    return builder


def _cooldown_label(text: str, seconds: int) -> str:
    return f"{text} ({seconds}с)" if seconds > 0 else text


def _cooldown_remaining(cooldowns: Optional[Dict], action: str, now: float) -> int:
    if not cooldowns:
        return 0
    until = cooldowns.get(action, 0)
    return max(0, int(until - now + 0.999))


def raid_keyboard(
    session: Dict,
    user_id: int,
    has_medkit: bool,
    cooldowns: Optional[Dict] = None,
) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    session_id = session["id"]
    now = time.time()
    if session["status"] == "combat":
        fight_cd = _cooldown_remaining(cooldowns, "fight", now)
        builder.button(
            text=_cooldown_label("Сражаться", fight_cd),
            callback_data=f"raid:fight:{session_id}:{user_id}",
        )
        if has_medkit:
            med_cd = _cooldown_remaining(cooldowns, "medkit", now)
            builder.button(
                text=_cooldown_label("Расходник", med_cd),
                callback_data=f"raid:medkit:{session_id}:{user_id}",
            )
        if has_medkit:
            builder.adjust(1, 1)
        else:
            builder.adjust(1)
        return builder

    loot_cd = _cooldown_remaining(cooldowns, "loot", now)
    move_cd = _cooldown_remaining(cooldowns, "move", now)
    evac_cd = _cooldown_remaining(cooldowns, "evac", now)
    builder.button(
        text=_cooldown_label("Лутать", loot_cd),
        callback_data=f"raid:loot:{session_id}:{user_id}",
    )
    builder.button(
        text=_cooldown_label("Идти дальше", move_cd),
        callback_data=f"raid:move:{session_id}:{user_id}",
    )
    builder.button(
        text=_cooldown_label("Эвакуация", evac_cd),
        callback_data=f"raid:evac:{session_id}:{user_id}",
    )
    if has_medkit:
        med_cd = _cooldown_remaining(cooldowns, "medkit", now)
        builder.button(
            text=_cooldown_label("Расходник", med_cd),
            callback_data=f"raid:medkit:{session_id}:{user_id}",
        )
        builder.adjust(2, 2)
    else:
        builder.adjust(2, 1)
    return builder


def admin_keyboard(settings: Dict) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    events_text = "События: ВКЛ" if settings["events_enabled"] else "События: ВЫКЛ"
    builder.button(text=events_text, callback_data="admin:events:toggle")
    builder.button(text="Риск +", callback_data="admin:event_base:inc")
    builder.button(text="Риск -", callback_data="admin:event_base:dec")
    builder.button(text="Алчность +", callback_data="admin:greed_mult:inc")
    builder.button(text="Алчность -", callback_data="admin:greed_mult:dec")
    builder.button(text="Эвак +", callback_data="admin:evac_base:inc")
    builder.button(text="Эвак -", callback_data="admin:evac_base:dec")
    builder.button(text="Падение эвак +", callback_data="admin:evac_penalty:inc")
    builder.button(text="Падение эвак -", callback_data="admin:evac_penalty:dec")
    builder.button(text="Цель склада +", callback_data="admin:warehouse_goal:inc")
    builder.button(text="Цель склада -", callback_data="admin:warehouse_goal:dec")
    builder.button(text="Событие: старт", callback_data="admin:event:start")
    builder.button(text="Событие: стоп", callback_data="admin:event:stop")
    builder.button(text="Цель события +", callback_data="admin:event_goal:inc")
    builder.button(text="Цель события -", callback_data="admin:event_goal:dec")
    builder.button(text="Очистить рейтинг", callback_data="admin:reset_rating")
    builder.adjust(2, 2, 2, 2, 2, 2, 2, 2)
    return builder


def admin_reset_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="admin:reset_confirm")
    builder.button(text="Отмена", callback_data="admin:reset_cancel")
    builder.adjust(2)
    return builder


def announce_select_keyboard(chats: list[tuple[int, str]]) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for chat_id, title in chats:
        builder.button(text=title, callback_data=f"announce:select:{chat_id}")
    builder.button(text="Отмена", callback_data="announce:cancel")
    builder.adjust(1)
    return builder


def announce_cancel_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отмена", callback_data="announce:cancel")
    builder.adjust(1)
    return builder


def loot_choice_keyboard(session_id: str, user_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Взять", callback_data=f"raid:take:{session_id}:{user_id}")
    builder.button(text="Не брать", callback_data=f"raid:skip:{session_id}:{user_id}")
    builder.adjust(2)
    return builder


def cleanup_keyboard(user_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Удалить отчет", callback_data=f"cleanup:{user_id}")
    builder.adjust(1)
    return builder


def storage_keyboard(
    page: int,
    total_pages: int,
    sort_key: str,
    user_id: int,
    can_upgrade: bool,
) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    nav_count = 0
    if page > 1:
        builder.button(
            text="◀️",
            callback_data=f"storage:page:{page-1}:{sort_key}:{user_id}",
        )
        nav_count += 1
    if page < total_pages:
        builder.button(
            text="▶️",
            callback_data=f"storage:page:{page+1}:{sort_key}:{user_id}",
        )
        nav_count += 1

    builder.button(text="Сорт: редкость", callback_data=f"storage:sort:rarity:{user_id}")
    builder.button(text="Сорт: ценность", callback_data=f"storage:sort:value:{user_id}")
    builder.button(text="Сорт: имя", callback_data=f"storage:sort:name:{user_id}")
    builder.button(text="Сорт: кол-во", callback_data=f"storage:sort:qty:{user_id}")
    builder.button(text="Продать", callback_data=f"sell:open:{page}:{sort_key}:{user_id}")
    builder.button(
        text="Чертежи",
        callback_data=f"blueprint:open:{page}:{sort_key}:{user_id}",
    )
    if can_upgrade:
        builder.button(
            text="Улучшить склад",
            callback_data=f"storage:upgrade:{page}:{sort_key}:{user_id}",
        )

    row_sizes = []
    if nav_count:
        row_sizes.append(nav_count)
    row_sizes.extend([2, 2, 1, 1])
    if can_upgrade:
        row_sizes.append(1)
    builder.adjust(*row_sizes)
    return builder


def sell_list_keyboard(
    page: int,
    total_pages: int,
    sort_key: str,
    user_id: int,
    items: list[tuple[str, str]],
) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for label, item_id in items:
        builder.button(
            text=label,
            callback_data=f"sell:item:{item_id}:{page}:{sort_key}:{user_id}",
        )
    nav_count = 0
    if page > 1:
        builder.button(
            text="◀️",
            callback_data=f"sell:page:{page-1}:{sort_key}:{user_id}",
        )
        nav_count += 1
    if page < total_pages:
        builder.button(
            text="▶️",
            callback_data=f"sell:page:{page+1}:{sort_key}:{user_id}",
        )
        nav_count += 1
    builder.button(text="Назад", callback_data=f"sell:back:{page}:{sort_key}:{user_id}")
    rows = []
    if items:
        rows.extend([1] * len(items))
    if nav_count:
        rows.append(nav_count)
    rows.append(1)
    builder.adjust(*rows)
    return builder


def sell_item_keyboard(
    item_id: str,
    qty: int,
    page: int,
    sort_key: str,
    user_id: int,
) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    if qty >= 1:
        builder.button(
            text="Продать x1",
            callback_data=f"sell:do:{item_id}:1:{page}:{sort_key}:{user_id}",
        )
    if qty >= 5:
        builder.button(
            text="Продать x5",
            callback_data=f"sell:do:{item_id}:5:{page}:{sort_key}:{user_id}",
        )
    if qty >= 1:
        builder.button(
            text="Продать все",
            callback_data=f"sell:do:{item_id}:all:{page}:{sort_key}:{user_id}",
        )
    builder.button(text="Назад", callback_data=f"sell:page:{page}:{sort_key}:{user_id}")
    rows = []
    btn_count = 0
    if qty >= 1:
        btn_count += 1
    if qty >= 5:
        btn_count += 1
    if qty >= 1:
        btn_count += 1
    if btn_count:
        rows.append(btn_count if btn_count <= 3 else 3)
    rows.append(1)
    builder.adjust(*rows)
    return builder


def blueprint_keyboard(
    items: list[tuple[str, str]],
    page: int,
    total_pages: int,
    sort_key: str,
    user_id: int,
) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for label, item_id in items:
        builder.button(
            text=label,
            callback_data=f"blueprint:study:{item_id}:{page}:{sort_key}:{user_id}",
        )
    nav_count = 0
    if page > 1:
        builder.button(
            text="◀️",
            callback_data=f"blueprint:page:{page-1}:{sort_key}:{user_id}",
        )
        nav_count += 1
    if page < total_pages:
        builder.button(
            text="▶️",
            callback_data=f"blueprint:page:{page+1}:{sort_key}:{user_id}",
        )
        nav_count += 1
    builder.button(
        text="Назад",
        callback_data=f"blueprint:back:{page}:{sort_key}:{user_id}",
    )
    rows = []
    if items:
        rows.extend([1] * len(items))
    if nav_count:
        rows.append(nav_count)
    rows.append(1)
    builder.adjust(*rows)
    return builder


def storage_confirm_keyboard(
    page: int,
    sort_key: str,
    user_id: int,
) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить",
        callback_data=f"storage:confirm:{page}:{sort_key}:{user_id}",
    )
    builder.button(
        text="Отмена",
        callback_data=f"storage:cancel:{page}:{sort_key}:{user_id}",
    )
    builder.adjust(2)
    return builder


def equip_menu_keyboard(user_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Броня", callback_data=f"equip:type:armor:{user_id}")
    builder.button(text="Оружие", callback_data=f"equip:type:weapon:{user_id}")
    builder.button(text="Расходник", callback_data=f"equip:type:medkit:{user_id}")
    builder.button(text="Аугмент", callback_data=f"equip:type:chip:{user_id}")
    builder.adjust(2, 2)
    return builder


def equip_items_keyboard(
    item_type: str,
    page: int,
    total_pages: int,
    user_id: int,
    items: list[tuple[str, str]],
) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for label, item_id in items:
        builder.button(
            text=label,
            callback_data=f"equip:set:{item_type}:{item_id}:{user_id}",
        )
    if page > 1:
        builder.button(
            text="◀️",
            callback_data=f"equip:page:{item_type}:{page-1}:{user_id}",
        )
    if page < total_pages:
        builder.button(
            text="▶️",
            callback_data=f"equip:page:{item_type}:{page+1}:{user_id}",
        )
    builder.button(
        text="Снять",
        callback_data=f"equip:clear:{item_type}:{user_id}",
    )
    rows = []
    if items:
        rows.extend([2] * (len(items) // 2))
        if len(items) % 2:
            rows.append(1)
    nav_count = (1 if page > 1 else 0) + (1 if page < total_pages else 0)
    if nav_count:
        rows.append(nav_count)
    rows.append(1)
    builder.adjust(*rows)
    return builder


def craft_keyboard(recipes: list[dict], user_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for recipe in recipes:
        builder.button(
            text=f"Скрафтить: {recipe['name']}",
            callback_data=f"craft:make:{recipe['id']}:{user_id}",
        )
    if recipes:
        builder.adjust(1)
    return builder


def shop_keyboard(
    user_id: int,
    offer_buttons: Optional[list[tuple[str, str]]] = None,
) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    if offer_buttons:
        for label, callback in offer_buttons:
            builder.button(text=label, callback_data=callback)
    builder.button(text="Купить расходник", callback_data=f"shop:buy:medkit:{user_id}")
    builder.button(text="Купить эвак-устройство", callback_data=f"shop:buy:evac_beacon:{user_id}")
    builder.button(text="Купить страховку", callback_data=f"shop:buy:insurance:{user_id}")
    builder.button(text="Улучшить склад", callback_data=f"shop:upgrade:{user_id}")
    rows = []
    if offer_buttons:
        rows.extend([1] * len(offer_buttons))
    rows.extend([1, 1, 1, 1])
    builder.adjust(*rows)
    return builder


def shop_confirm_keyboard(user_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"shop:confirm:{user_id}")
    builder.button(text="Отмена", callback_data=f"shop:cancel:{user_id}")
    builder.adjust(2)
    return builder
