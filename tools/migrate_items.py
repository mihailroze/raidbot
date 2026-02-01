import json
import os
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "bot.db"))
LOOT_PATH = Path(os.getenv("DATA_DIR", ROOT / "data")) / "loot.json"

# Map legacy item ids to new ARCTracker ids.
MIGRATE_MAP = {
    "scrap": "metal_parts",
    "servo": "mechanical_components",
    "toolkit": "rusted_tools",
    "circuit": "arc_circuitry",
    "reinforced_plates": "advanced_mechanical_components",
    "optics": "camera_lens",
    "medkit": "bandage",
    "evac_beacon": "remote_raider_flare",
    "light_armor": "light_shield",
    "tactical_armor": "medium_shield",
    "heavy_armor": "heavy_shield",
    "rifle": "tempest_i",
    "pulse_rifle": "tempest_ii",
    "chip_nav": "tactical_mk1",
    "chip_stabilizer": "looting_mk2",
    "chip_booster": "combat_mk1",
    "arc_chip": "advanced_arc_powercell",
    "nanofiber": "durable_cloth",
    "arc_module": "looting_mk1",
    "arc_core": "arc_motion_core",
    "arc_prism": "arc_alloy",
    "arc_blade": "complex_gun_parts",
}


def load_valid_ids() -> set[str]:
    if not LOOT_PATH.exists():
        raise SystemExit(f"loot.json not found: {LOOT_PATH}")
    items = json.loads(LOOT_PATH.read_text(encoding="utf-8"))
    return {item["id"] for item in items if item.get("id")}


def map_id(item_id: str) -> str | None:
    return MIGRATE_MAP.get(item_id, item_id)


def merge_dict_counts(payload: dict, valid_ids: set[str]) -> dict:
    merged: dict[str, int] = {}
    for key, qty in payload.items():
        new_id = map_id(key)
        if not new_id or new_id not in valid_ids:
            continue
        merged[new_id] = merged.get(new_id, 0) + int(qty)
    return merged


def map_list(payload: list, valid_ids: set[str]) -> list:
    result: list[str] = []
    for item_id in payload:
        new_id = map_id(item_id)
        if not new_id or new_id not in valid_ids:
            continue
        result.append(new_id)
    return result


def migrate_inventory(conn: sqlite3.Connection, valid_ids: set[str]) -> None:
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT player_id, item_id, qty FROM inventory WHERE item_id IN ({})".format(
            ",".join("?" for _ in MIGRATE_MAP)
        ),
        tuple(MIGRATE_MAP.keys()),
    ).fetchall()
    for player_id, item_id, qty in rows:
        new_id = map_id(item_id)
        if not new_id or new_id not in valid_ids:
            cursor.execute(
                "DELETE FROM inventory WHERE player_id = ? AND item_id = ?",
                (player_id, item_id),
            )
            continue
        if new_id == item_id:
            continue
        existing = cursor.execute(
            "SELECT qty FROM inventory WHERE player_id = ? AND item_id = ?",
            (player_id, new_id),
        ).fetchone()
        if existing:
            cursor.execute(
                "UPDATE inventory SET qty = ? WHERE player_id = ? AND item_id = ?",
                (existing[0] + qty, player_id, new_id),
            )
            cursor.execute(
                "DELETE FROM inventory WHERE player_id = ? AND item_id = ?",
                (player_id, item_id),
            )
        else:
            cursor.execute(
                "UPDATE inventory SET item_id = ? WHERE player_id = ? AND item_id = ?",
                (new_id, player_id, item_id),
            )


def migrate_warehouse(conn: sqlite3.Connection, valid_ids: set[str]) -> None:
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT chat_id, item_id, qty FROM warehouse WHERE item_id IN ({})".format(
            ",".join("?" for _ in MIGRATE_MAP)
        ),
        tuple(MIGRATE_MAP.keys()),
    ).fetchall()
    for chat_id, item_id, qty in rows:
        new_id = map_id(item_id)
        if not new_id or new_id not in valid_ids:
            cursor.execute(
                "DELETE FROM warehouse WHERE chat_id = ? AND item_id = ?",
                (chat_id, item_id),
            )
            continue
        if new_id == item_id:
            continue
        existing = cursor.execute(
            "SELECT qty FROM warehouse WHERE chat_id = ? AND item_id = ?",
            (chat_id, new_id),
        ).fetchone()
        if existing:
            cursor.execute(
                "UPDATE warehouse SET qty = ? WHERE chat_id = ? AND item_id = ?",
                (existing[0] + qty, chat_id, new_id),
            )
            cursor.execute(
                "DELETE FROM warehouse WHERE chat_id = ? AND item_id = ?",
                (chat_id, item_id),
            )
        else:
            cursor.execute(
                "UPDATE warehouse SET item_id = ? WHERE chat_id = ? AND item_id = ?",
                (new_id, chat_id, item_id),
            )


def migrate_daily_order(conn: sqlite3.Connection, valid_ids: set[str]) -> None:
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT chat_id, day, item_id, qty FROM daily_order WHERE item_id IN ({})".format(
            ",".join("?" for _ in MIGRATE_MAP)
        ),
        tuple(MIGRATE_MAP.keys()),
    ).fetchall()
    for chat_id, day, item_id, qty in rows:
        new_id = map_id(item_id)
        if not new_id or new_id not in valid_ids:
            cursor.execute(
                "DELETE FROM daily_order WHERE chat_id = ? AND day = ? AND item_id = ?",
                (chat_id, day, item_id),
            )
            continue
        if new_id == item_id:
            continue
        existing = cursor.execute(
            "SELECT qty FROM daily_order WHERE chat_id = ? AND day = ? AND item_id = ?",
            (chat_id, day, new_id),
        ).fetchone()
        if existing:
            cursor.execute(
                "UPDATE daily_order SET qty = ? WHERE chat_id = ? AND day = ? AND item_id = ?",
                (existing[0] + qty, chat_id, day, new_id),
            )
            cursor.execute(
                "DELETE FROM daily_order WHERE chat_id = ? AND day = ? AND item_id = ?",
                (chat_id, day, item_id),
            )
        else:
            cursor.execute(
                "UPDATE daily_order SET item_id = ? WHERE chat_id = ? AND day = ? AND item_id = ?",
                (new_id, chat_id, day, item_id),
            )

    rows = cursor.execute("SELECT chat_id, order_item_id FROM settings WHERE order_item_id IS NOT NULL").fetchall()
    for chat_id, order_item_id in rows:
        new_id = map_id(order_item_id)
        if not new_id or new_id not in valid_ids:
            cursor.execute(
                "UPDATE settings SET order_item_id = NULL, order_date = NULL WHERE chat_id = ?",
                (chat_id,),
            )
            continue
        if new_id != order_item_id:
            cursor.execute(
                "UPDATE settings SET order_item_id = ? WHERE chat_id = ?",
                (new_id, chat_id),
            )


def migrate_loadouts(conn: sqlite3.Connection, valid_ids: set[str]) -> None:
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT player_id, armor_id, weapon_id, medkit_id, chip_id FROM loadouts"
    ).fetchall()
    for player_id, armor_id, weapon_id, medkit_id, chip_id in rows:
        updates = {}
        for col, value in (
            ("armor_id", armor_id),
            ("weapon_id", weapon_id),
            ("medkit_id", medkit_id),
            ("chip_id", chip_id),
        ):
            if not value:
                continue
            new_id = map_id(value)
            if not new_id or new_id not in valid_ids:
                updates[col] = None
            elif new_id != value:
                updates[col] = new_id
        if updates:
            cols = ", ".join(f"{k} = ?" for k in updates.keys())
            cursor.execute(
                f"UPDATE loadouts SET {cols} WHERE player_id = ?",
                (*updates.values(), player_id),
            )


def migrate_sessions(conn: sqlite3.Connection, valid_ids: set[str]) -> None:
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT id, inventory_json, pending_loot_json, armor_item_id, weapon_item_id, chip_id FROM sessions"
    ).fetchall()
    for session_id, inv_json, pending_json, armor_item_id, weapon_item_id, chip_id in rows:
        updates = {}
        if inv_json:
            try:
                inv = json.loads(inv_json)
            except Exception:
                inv = {}
            inv = merge_dict_counts(inv, valid_ids)
            updates["inventory_json"] = json.dumps(inv, ensure_ascii=False)
        if pending_json:
            try:
                pending = json.loads(pending_json)
            except Exception:
                pending = []
            pending = map_list(pending, valid_ids)
            updates["pending_loot_json"] = json.dumps(pending, ensure_ascii=False)
        for col, value in (
            ("armor_item_id", armor_item_id),
            ("weapon_item_id", weapon_item_id),
            ("chip_id", chip_id),
        ):
            if not value:
                continue
            new_id = map_id(value)
            if not new_id or new_id not in valid_ids:
                updates[col] = None
            elif new_id != value:
                updates[col] = new_id
        if updates:
            cols = ", ".join(f"{k} = ?" for k in updates.keys())
            cursor.execute(
                f"UPDATE sessions SET {cols} WHERE id = ?",
                (*updates.values(), session_id),
            )


def main() -> None:
    valid_ids = load_valid_ids()
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    backup = DB_PATH.with_suffix(".bak")
    if not backup.exists():
        backup.write_bytes(DB_PATH.read_bytes())

    conn = sqlite3.connect(DB_PATH)
    try:
        migrate_inventory(conn, valid_ids)
        migrate_warehouse(conn, valid_ids)
        migrate_daily_order(conn, valid_ids)
        migrate_loadouts(conn, valid_ids)
        migrate_sessions(conn, valid_ids)
        conn.commit()
    finally:
        conn.close()

    print("Migration complete.")


if __name__ == "__main__":
    main()
