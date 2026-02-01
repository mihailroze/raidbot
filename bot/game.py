from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import DEFAULTS, DATA_DIR


class GameData:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.loot = self._load_json("loot.json")
        self.enemies = self._load_json("enemies.json")
        self.events = self._load_json("events.json")
        self.recipes = self._load_json("recipes.json")
        self._loot_index = {item["id"]: item for item in self.loot}
        self._enemy_index = {enemy["id"]: enemy for enemy in self.enemies}

    def _load_json(self, name: str) -> List[Dict[str, Any]]:
        path = self.data_dir / name
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        return self._loot_index.get(item_id)

    def roll_loot(self) -> Dict[str, Any]:
        return weighted_choice(self.loot, "weight")

    def roll_enemy(self) -> Dict[str, Any]:
        return weighted_choice(self.enemies, "weight")

    def get_enemy(self, enemy_id: str) -> Optional[Dict[str, Any]]:
        enemy = self._enemy_index.get(enemy_id)
        return dict(enemy) if enemy else None

    def roll_event(self) -> Dict[str, Any]:
        return weighted_choice(self.events, "weight")

    def get_recipe(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        for recipe in self.recipes:
            if recipe.get("id") == recipe_id:
                return recipe
        return None

    def list_recipes(self) -> List[Dict[str, Any]]:
        return list(self.recipes)


def weighted_choice(items: List[Dict[str, Any]], weight_key: str) -> Dict[str, Any]:
    total = sum(item.get(weight_key, 0) for item in items)
    if total <= 0:
        return random.choice(items)
    pick = random.uniform(0, total)
    current = 0.0
    for item in items:
        current += item.get(weight_key, 0)
        if pick <= current:
            return item
    return items[-1]


def calc_event_chance(greed: int, settings: Dict[str, Any]) -> float:
    chance = settings["event_base"] + greed * settings["event_greed_mult"]
    return clamp(chance, 0.05, 0.85)


def calc_evac_chance(greed: int, evac_bonus: float, settings: Dict[str, Any]) -> float:
    chance = settings["evac_base"] - greed * settings["evac_greed_penalty"] + evac_bonus
    return clamp(chance, 0.1, 0.95)


def clamp(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))


def apply_loot(session: Dict[str, Any], item: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    inventory = session["inventory"]
    inventory[item["id"]] = inventory.get(item["id"], 0) + 1
    session["loot_value"] += int(item.get("value", 0))

    item_type = item.get("type")
    message = f"Найдено: {format_item(item)}."

    if item_type == "armor":
        armor_pct = float(item.get("armor_pct", 0))
        if armor_pct > session["armor_pct"]:
            session["armor_pct"] = armor_pct
            message += " Экипировано: броня."
    elif item_type == "weapon":
        bonus = int(item.get("weapon_bonus", 0))
        if bonus > session["weapon_bonus"]:
            session["weapon_bonus"] = bonus
            message += " Экипировано: оружие."

    return session, message


def has_consumable(session: Dict[str, Any], data: GameData) -> bool:
    for item_id, count in session["inventory"].items():
        if count <= 0:
            continue
        item = data.get_item(item_id)
        if item and item.get("type") == "consumable":
            if item.get("heal") or item.get("evac_bonus"):
                return True
    return False


def consume_medkit(session: Dict[str, Any], data: GameData) -> Tuple[Dict[str, Any], Optional[str]]:
    candidates = []
    for item_id, count in session["inventory"].items():
        if count <= 0:
            continue
        item = data.get_item(item_id)
        if item and item.get("type") == "consumable":
            if not (item.get("heal") or item.get("evac_bonus")):
                continue
            candidates.append((item_id, count, item))

    if not candidates:
        return session, None

    chosen = None
    if session["hp"] < session["max_hp"]:
        healers = [c for c in candidates if int(c[2].get("heal", 0)) > 0]
        if healers:
            chosen = max(healers, key=lambda c: int(c[2].get("heal", 0)))
    if not chosen:
        boosters = [
            c for c in candidates if float(c[2].get("evac_bonus", 0) or 0) > 0
        ]
        if boosters:
            chosen = max(boosters, key=lambda c: float(c[2].get("evac_bonus", 0) or 0))
    if not chosen:
        chosen = candidates[0]

    item_id, count, item = chosen
    session["inventory"][item_id] = count - 1

    heal = int(item.get("heal", 0))
    if heal > 0:
        session["hp"] = min(session["max_hp"], session["hp"] + heal)
        return session, f"Использована {item['name']}: +{heal} HP."

    bonus = float(item.get("evac_bonus", 0) or 0)
    if bonus > 0:
        before = float(session.get("evac_bonus", 0.0))
        after = min(0.3, before + bonus)
        session["evac_bonus"] = after
        applied = max(0.0, after - before)
        pct = int(round(applied * 100))
        if pct <= 0:
            return session, f"{item['name']}: шанс эвакуации уже максимум."
        return session, f"Использован {item['name']}: шанс эвакуации +{pct}%."

    return session, f"Использован {item['name']}."


def resolve_fight(session: Dict[str, Any], enemy: Dict[str, Any]) -> Tuple[Dict[str, Any], str, bool]:
    log = []
    enemy_hp = int(enemy.get("hp_current", enemy.get("hp", 0)))
    enemy_name = enemy.get("name", "ARC-бот")

    rounds = 0
    while session["hp"] > 0 and enemy_hp > 0 and rounds < 10:
        rounds += 1
        player_damage = (
            random.randint(10, 18)
            + session["weapon_bonus"]
            + int(session.get("damage_bonus", 0))
        )
        enemy_hp -= player_damage
        log.append(f"Вы нанесли {player_damage} урона.")
        if enemy_hp <= 0:
            break
        enemy_damage = random.randint(enemy["dmg_min"], enemy["dmg_max"])
        reduced = max(1, int(enemy_damage * (1 - session["armor_pct"])))
        session["hp"] -= reduced
        log.append(f"{enemy_name} наносит {reduced} урона.")

    enemy["hp_current"] = max(0, enemy_hp)
    session["enemy"] = enemy if enemy_hp > 0 else None

    survived = session["hp"] > 0
    if survived and enemy_hp <= 0:
        session["kills"] += 1
        session["status"] = "explore"
        log.append(f"Враг уничтожен: {enemy_name}.")
        return session, " ".join(log), True

    if not survived:
        log.append("Вы погибли в бою.")
    else:
        session["status"] = "combat"
        log.append(f"Бой продолжается. HP врага: {enemy_hp}.")
    return session, " ".join(log), False


def roll_bonus_drop(data: GameData, chance: float = 0.4) -> Optional[Dict[str, Any]]:
    if random.random() < chance:
        return data.roll_loot()
    return None


def roll_loot_by_rarity(data: GameData, rarity: str) -> Dict[str, Any]:
    pool = [item for item in data.loot if item.get("rarity") == rarity]
    if not pool:
        return data.roll_loot()
    return weighted_choice(pool, "weight")


def format_loot_summary(session: Dict[str, Any]) -> str:
    total_items = sum(session["inventory"].values())
    return f"{total_items}/{DEFAULTS.raid_limit} предметов, ценность {session['loot_value']}"


def calc_points(session: Dict[str, Any]) -> int:
    return DEFAULTS.extract_base_points + session["loot_value"] + session["kills"] * DEFAULTS.kill_points


def rarity_emoji(rarity: str) -> str:
    mapping = {
        "junk": "\U0001F7E4",
        "common": "\U0001F7E2",
        "rare": "\U0001F535",
        "epic": "\U0001F7E3",
        "legendary": "\U0001F7E1",
    }
    return mapping.get(rarity, "\u26aa\ufe0f")


def rarity_label(rarity: str) -> str:
    mapping = {
        "junk": "мусор",
        "common": "обычный",
        "rare": "редкий",
        "epic": "эпический",
        "legendary": "легендарный",
    }
    return mapping.get(rarity, rarity)


RARITY_ORDER = {
    "junk": 0,
    "common": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
}

SORT_LABELS = {
    "rarity": "редкость",
    "value": "ценность",
    "name": "имя",
    "qty": "кол-во",
}


def format_item(item: Dict[str, Any]) -> str:
    emoji = item.get("emoji") or rarity_emoji(item.get("rarity", "common"))
    rarity = rarity_label(item.get("rarity", "common"))
    if item.get("blueprint") or item.get("type") == "blueprint":
        return f"?? {emoji} {item['name']} (??????, {rarity})"
    return f"{emoji} {item['name']} ({rarity})"


def inventory_count(session: Dict[str, Any]) -> int:
    return sum(session["inventory"].values())


def select_items_by_capacity(
    items: Dict[str, int],
    capacity: int,
    data: GameData,
) -> Tuple[Dict[str, int], Dict[str, int]]:
    if capacity <= 0:
        return {}, dict(items)
    pool: List[Dict[str, Any]] = []
    for item_id, qty in items.items():
        if qty <= 0:
            continue
        item = data.get_item(item_id)
        if not item:
            continue
        for _ in range(qty):
            pool.append(item)
    if not pool:
        return {}, {}
    pool.sort(key=lambda it: int(it.get("value", 0)), reverse=True)
    kept = pool[:capacity]
    dropped = pool[capacity:]
    kept_map: Dict[str, int] = {}
    dropped_map: Dict[str, int] = {}
    for item in kept:
        kept_map[item["id"]] = kept_map.get(item["id"], 0) + 1
    for item in dropped:
        dropped_map[item["id"]] = dropped_map.get(item["id"], 0) + 1
    return kept_map, dropped_map


def format_inventory(items: Dict[str, int], data: GameData) -> str:
    if not items:
        return "Хранилище пусто."
    parts = []
    total = 0
    for item_id, qty in items.items():
        item = data.get_item(item_id)
        if item:
            emoji = item.get("emoji") or rarity_emoji(item.get("rarity", "common"))
            name = item["name"]
        else:
            emoji = "⚪️"
            name = item_id
        parts.append(f"{emoji} {name} x{qty}")
        total += qty
    parts.sort()
    return "Хранилище:\n" + "\n".join(parts) + f"\nВсего: {total}/{DEFAULTS.storage_limit}"


def calc_inventory_value(items: Dict[str, int], data: GameData) -> int:
    total_value = 0
    for item_id, qty in items.items():
        if qty <= 0:
            continue
        item = data.get_item(item_id)
        if not item:
            continue
        total_value += int(item.get("value", 0)) * qty
    return total_value


def can_craft(items: Dict[str, int], recipe: Dict[str, Any]) -> bool:
    ingredients = recipe.get("ingredients", {})
    for item_id, qty in ingredients.items():
        if items.get(item_id, 0) < int(qty):
            return False
    return True


def craft_deltas(recipe: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, int]]:
    ingredients = recipe.get("ingredients", {})
    output = recipe.get("output", {})
    consume = {item_id: -int(qty) for item_id, qty in ingredients.items()}
    produce = {output["item_id"]: int(output.get("qty", 1))}
    return consume, produce


def pick_random_item(items: Dict[str, int]) -> Optional[str]:
    pool: List[str] = []
    for item_id, qty in items.items():
        if qty <= 0:
            continue
        pool.extend([item_id] * qty)
    if not pool:
        return None
    return random.choice(pool)


def normalize_sort(sort_key: str) -> str:
    if sort_key not in SORT_LABELS:
        return "rarity"
    return sort_key


def get_storage_page(
    items: Dict[str, int],
    data: GameData,
    sort_key: str,
    page: int,
    page_size: int,
) -> Tuple[List[str], int, int, str]:
    sort_key = normalize_sort(sort_key)
    entries: List[Dict[str, Any]] = []
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

    if not page_entries:
        return ["Хранилище пусто."], page, total_pages, sort_key

    lines = []
    for entry in page_entries:
        lines.append(
            f"{entry['emoji']} {entry['name']} x{entry['qty']} (ценн. {entry['value']})"
        )
    return lines, page, total_pages, sort_key


def rarity_legend() -> str:
    return (
        "Редкости: "
        "🟤 мусор, "
        "🟢 обычный, "
        "🔵 редкий, "
        "🟣 эпический, "
        "🟡 легендарный"
    )
