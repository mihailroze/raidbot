from __future__ import annotations

import json
import random
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import aiosqlite

from .config import DEFAULTS, DB_PATH


class Database:
    def __init__(self, path=DB_PATH):
        self.path = str(path)
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.execute("PRAGMA journal_mode = WAL")
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def init(self) -> None:
        assert self.conn is not None
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ratings (
                player_id INTEGER PRIMARY KEY,
                points INTEGER NOT NULL DEFAULT 0,
                raids INTEGER NOT NULL DEFAULT 0,
                extracts INTEGER NOT NULL DEFAULT 0,
                deaths INTEGER NOT NULL DEFAULT 0,
                kills INTEGER NOT NULL DEFAULT 0,
                loot_value_total INTEGER NOT NULL DEFAULT 0,
                storage_limit INTEGER NOT NULL DEFAULT 50,
                raidcoins INTEGER NOT NULL DEFAULT 0,
                insurance_tokens INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                player_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                thread_id INTEGER NOT NULL,
                hp INTEGER NOT NULL,
                max_hp INTEGER NOT NULL,
                greed INTEGER NOT NULL,
                loot_value INTEGER NOT NULL,
                kills INTEGER NOT NULL,
                inventory_json TEXT NOT NULL,
                armor_pct REAL NOT NULL,
                weapon_bonus INTEGER NOT NULL,
                armor_item_id TEXT,
                weapon_item_id TEXT,
                status TEXT NOT NULL,
                enemy_json TEXT,
                evac_bonus REAL NOT NULL,
                damage_bonus INTEGER NOT NULL DEFAULT 0,
                greed_mult REAL NOT NULL DEFAULT 1.0,
                chip_id TEXT,
                hard_mode INTEGER NOT NULL DEFAULT 0,
                evac_penalty REAL NOT NULL DEFAULT 0,
                entry_fee INTEGER NOT NULL DEFAULT 0,
                entry_bonus INTEGER NOT NULL DEFAULT 0,
                panel_message_id INTEGER,
                pending_loot_json TEXT,
                pending_choice_json TEXT,
                cooldowns_json TEXT,
                started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS sessions_player_chat_idx
                ON sessions(player_id, chat_id);

            CREATE TABLE IF NOT EXISTS settings (
                chat_id INTEGER PRIMARY KEY,
                thread_id INTEGER,
                events_enabled INTEGER NOT NULL DEFAULT 1,
                event_base REAL NOT NULL,
                event_greed_mult REAL NOT NULL,
                evac_base REAL NOT NULL,
                evac_greed_penalty REAL NOT NULL,
                warehouse_goal INTEGER NOT NULL DEFAULT 500,
                event_week_active INTEGER NOT NULL DEFAULT 0,
                event_week_id TEXT,
                event_week_start TEXT,
                event_week_end TEXT,
                event_week_goal INTEGER NOT NULL DEFAULT 10000,
                event_week_awarded INTEGER NOT NULL DEFAULT 0,
                order_date TEXT,
                order_item_id TEXT,
                order_target INTEGER,
                order_reward INTEGER,
                order_bonus INTEGER
            );

            CREATE TABLE IF NOT EXISTS inventory (
                player_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(player_id, item_id),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS loadouts (
                player_id INTEGER PRIMARY KEY,
                armor_id TEXT,
                weapon_id TEXT,
                medkit_id TEXT,
                chip_id TEXT,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS unlocked_recipes (
                player_id INTEGER NOT NULL,
                recipe_id TEXT NOT NULL,
                PRIMARY KEY(player_id, recipe_id),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS daily_raids (
                player_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(player_id, chat_id, day),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS daily_shop (
                player_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(player_id, chat_id, day),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS daily_cases (
                player_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                opened_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(player_id, chat_id, day),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS daily_order (
                chat_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                item_id TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(chat_id, day, item_id)
            );
            CREATE TABLE IF NOT EXISTS warehouse (
                chat_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(chat_id, item_id)
            );
            CREATE TABLE IF NOT EXISTS warehouse_contrib (
                chat_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                value_total INTEGER NOT NULL DEFAULT 0,
                items_total INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(chat_id, player_id),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS achievements (
                player_id INTEGER NOT NULL,
                achievement_id TEXT NOT NULL,
                acquired_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(player_id, achievement_id),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS web_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                nickname TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS web_logins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                ip TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS player_quests (
                player_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                period TEXT NOT NULL,
                quest_id TEXT NOT NULL,
                title TEXT NOT NULL,
                metric TEXT NOT NULL,
                target INTEGER NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                reward_points INTEGER NOT NULL DEFAULT 0,
                reward_raidcoins INTEGER NOT NULL DEFAULT 0,
                reward_item_id TEXT,
                reward_qty INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0,
                claimed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(player_id, kind, period, quest_id),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS market_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                qty INTEGER NOT NULL,
                price INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(seller_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                kind TEXT NOT NULL,
                detail TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS daily_stats (
                player_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                raidcoins_earned INTEGER NOT NULL DEFAULT 0,
                sells_count INTEGER NOT NULL DEFAULT 0,
                raids_started INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(player_id, day),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS seasons (
                season_id TEXT PRIMARY KEY,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                closed INTEGER NOT NULL DEFAULT 0,
                rewarded INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS season_ratings (
                season_id TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                points INTEGER NOT NULL DEFAULT 0,
                raids INTEGER NOT NULL DEFAULT 0,
                extracts INTEGER NOT NULL DEFAULT 0,
                deaths INTEGER NOT NULL DEFAULT 0,
                kills INTEGER NOT NULL DEFAULT 0,
                loot_value_total INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(season_id, player_id),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS event_contrib (
                chat_id INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                value_total INTEGER NOT NULL DEFAULT 0,
                items_total INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(chat_id, event_id, player_id),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );
            """
        )
        await self._ensure_column("sessions", "pending_loot_json", "TEXT")
        await self._ensure_column("sessions", "pending_choice_json", "TEXT")
        await self._ensure_column("sessions", "cooldowns_json", "TEXT")
        await self._ensure_column("sessions", "damage_bonus", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column("sessions", "greed_mult", "REAL NOT NULL DEFAULT 1.0")
        await self._ensure_column("sessions", "chip_id", "TEXT")
        await self._ensure_column("sessions", "armor_item_id", "TEXT")
        await self._ensure_column("sessions", "weapon_item_id", "TEXT")
        await self._ensure_column("sessions", "hard_mode", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column("sessions", "evac_penalty", "REAL NOT NULL DEFAULT 0")
        await self._ensure_column("sessions", "entry_fee", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column("sessions", "entry_bonus", "INTEGER NOT NULL DEFAULT 0")
        await self._ensure_column(
            "ratings",
            "storage_limit",
            f"INTEGER NOT NULL DEFAULT {DEFAULTS.storage_limit}",
        )
        await self._ensure_column(
            "ratings",
            "insurance_tokens",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await self._ensure_column(
            "ratings",
            "raidcoins",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await self._ensure_column(
            "ratings",
            "case_pity",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await self._ensure_column(
            "web_users",
            "onboarded",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await self._ensure_column("web_users", "last_ip", "TEXT")
        await self._ensure_column("web_users", "last_login_at", "TEXT")
        await self._ensure_column("settings", "shop_date", "TEXT")
        await self._ensure_column("settings", "shop_offers_json", "TEXT")
        await self._ensure_column(
            "settings",
            "warehouse_goal",
            f"INTEGER NOT NULL DEFAULT {DEFAULTS.warehouse_goal}",
        )
        await self._ensure_column(
            "settings",
            "daily_sell_raidcoin_cap",
            f"INTEGER NOT NULL DEFAULT {DEFAULTS.daily_sell_raidcoin_cap}",
        )
        await self._ensure_column(
            "settings",
            "daily_sell_count_cap",
            f"INTEGER NOT NULL DEFAULT {DEFAULTS.daily_sell_count_cap}",
        )
        await self._ensure_column(
            "settings",
            "market_listing_cap",
            f"INTEGER NOT NULL DEFAULT {DEFAULTS.market_listing_cap}",
        )
        await self._ensure_column(
            "settings",
            "season_reward_top1",
            f"INTEGER NOT NULL DEFAULT {DEFAULTS.season_reward_top1}",
        )
        await self._ensure_column(
            "settings",
            "season_reward_top2",
            f"INTEGER NOT NULL DEFAULT {DEFAULTS.season_reward_top2}",
        )
        await self._ensure_column(
            "settings",
            "season_reward_top3",
            f"INTEGER NOT NULL DEFAULT {DEFAULTS.season_reward_top3}",
        )
        await self._ensure_column(
            "settings",
            "event_week_active",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await self._ensure_column("settings", "event_week_id", "TEXT")
        await self._ensure_column("settings", "event_week_start", "TEXT")
        await self._ensure_column("settings", "event_week_end", "TEXT")
        await self._ensure_column(
            "settings",
            "event_week_goal",
            f"INTEGER NOT NULL DEFAULT {DEFAULTS.event_week_goal}",
        )
        await self._ensure_column(
            "settings",
            "event_week_awarded",
            "INTEGER NOT NULL DEFAULT 0",
        )
        await self._ensure_column("settings", "order_date", "TEXT")
        await self._ensure_column("settings", "order_item_id", "TEXT")
        await self._ensure_column("settings", "order_target", "INTEGER")
        await self._ensure_column("settings", "order_reward", "INTEGER")
        await self._ensure_column("settings", "order_bonus", "INTEGER")
        await self._ensure_column("loadouts", "chip_id", "TEXT")
        await self.conn.commit()

    async def ensure_settings(self, chat_id: int) -> Dict[str, Any]:
        assert self.conn is not None
        row = await self._fetchone(
            "SELECT * FROM settings WHERE chat_id = ?",
            (chat_id,),
        )
        if row:
            return dict(row)
        await self.conn.execute(
            """
            INSERT INTO settings (
                chat_id, thread_id, events_enabled,
                event_base, event_greed_mult, evac_base, evac_greed_penalty,
                warehouse_goal, order_date, order_item_id, order_target, order_reward, order_bonus
            ) VALUES (?, NULL, 1, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL)
            """,
            (
                chat_id,
                DEFAULTS.event_base,
                DEFAULTS.event_greed_mult,
                DEFAULTS.evac_base,
                DEFAULTS.evac_greed_penalty,
                DEFAULTS.warehouse_goal,
            ),
        )
        await self.conn.commit()
        return await self.ensure_settings(chat_id)

    async def get_bound_threads(self) -> List[Dict[str, Any]]:
        rows = await self._fetchall(
            "SELECT chat_id, thread_id FROM settings WHERE thread_id IS NOT NULL",
            (),
        )
        return [dict(row) for row in rows]

    async def set_thread(self, chat_id: int, thread_id: int) -> None:
        assert self.conn is not None
        await self.ensure_settings(chat_id)
        await self.conn.execute(
            "UPDATE settings SET thread_id = ? WHERE chat_id = ?",
            (thread_id, chat_id),
        )
        await self.conn.commit()

    async def update_settings(self, chat_id: int, **kwargs: Any) -> Dict[str, Any]:
        assert self.conn is not None
        if not kwargs:
            return await self.ensure_settings(chat_id)
        cols = ", ".join(f"{k} = ?" for k in kwargs.keys())
        await self.conn.execute(
            f"UPDATE settings SET {cols} WHERE chat_id = ?",
            (*kwargs.values(), chat_id),
        )
        await self.conn.commit()
        return await self.ensure_settings(chat_id)

    async def upsert_player(self, user) -> int:
        assert self.conn is not None
        row = await self._fetchone(
            "SELECT id FROM players WHERE tg_id = ?",
            (user.id,),
        )
        if row:
            await self.conn.execute(
                """
                UPDATE players
                SET username = ?, first_name = ?, last_name = ?
                WHERE tg_id = ?
                """,
                (user.username, user.first_name, user.last_name, user.id),
            )
            await self.conn.commit()
            return row["id"]
        cursor = await self.conn.execute(
            """
            INSERT INTO players (tg_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            """,
            (user.id, user.username, user.first_name, user.last_name),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def get_player_id(self, tg_id: int) -> Optional[int]:
        row = await self._fetchone(
            "SELECT id FROM players WHERE tg_id = ?",
            (tg_id,),
        )
        return row["id"] if row else None

    async def get_player(self, player_id: int) -> Optional[Dict[str, Any]]:
        row = await self._fetchone(
            "SELECT * FROM players WHERE id = ?",
            (player_id,),
        )
        return dict(row) if row else None

    async def get_web_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        row = await self._fetchone(
            "SELECT * FROM web_users WHERE email = ?",
            (email,),
        )
        return dict(row) if row else None

    async def create_web_user(
        self, email: str, nickname: str, password_hash: str
    ) -> int:
        assert self.conn is not None
        # Create a synthetic player tied to the web user.
        player_id = None
        for _ in range(10):
            tg_id = -random.randint(1, 2_000_000_000)
            try:
                cursor = await self.conn.execute(
                    """
                    INSERT INTO players (tg_id, username, first_name, last_name)
                    VALUES (?, ?, ?, NULL)
                    """,
                    (tg_id, nickname, nickname),
                )
                player_id = cursor.lastrowid
                break
            except aiosqlite.IntegrityError:
                continue
        if not player_id:
            raise RuntimeError("Failed to create player")

        await self.conn.execute(
            """
            INSERT INTO web_users (player_id, email, password_hash, nickname)
            VALUES (?, ?, ?, ?)
            """,
            (player_id, email, password_hash, nickname),
        )
        await self.conn.commit()
        return player_id

    async def get_web_user_by_player(self, player_id: int) -> Optional[Dict[str, Any]]:
        row = await self._fetchone(
            "SELECT * FROM web_users WHERE player_id = ?",
            (player_id,),
        )
        return dict(row) if row else None

    async def update_web_user_onboarded(self, player_id: int) -> None:
        assert self.conn is not None
        await self.conn.execute(
            "UPDATE web_users SET onboarded = 1 WHERE player_id = ?",
            (player_id,),
        )
        await self.conn.commit()

    async def update_web_user_login(self, player_id: int, ip: Optional[str]) -> None:
        assert self.conn is not None
        await self.conn.execute(
            "UPDATE web_users SET last_ip = ?, last_login_at = CURRENT_TIMESTAMP WHERE player_id = ?",
            (ip, player_id),
        )
        await self.conn.commit()

    async def log_web_login(self, player_id: int, email: str, ip: Optional[str]) -> None:
        assert self.conn is not None
        await self.conn.execute(
            "INSERT INTO web_logins (player_id, email, ip) VALUES (?, ?, ?)",
            (player_id, email, ip),
        )
        await self.conn.commit()

    async def count_recent_ip_accounts(self, ip: str, hours: int = 24) -> int:
        row = await self._fetchone(
            """
            SELECT COUNT(DISTINCT player_id) AS total
            FROM web_logins
            WHERE ip = ? AND created_at >= datetime('now', ?)
            """,
            (ip, f"-{int(hours)} hours"),
        )
        return int(row["total"]) if row else 0

    async def add_audit_log(
        self, kind: str, detail: str, player_id: Optional[int] = None
    ) -> None:
        assert self.conn is not None
        await self.conn.execute(
            "INSERT INTO audit_log (player_id, kind, detail) VALUES (?, ?, ?)",
            (player_id, kind, detail),
        )
        await self.conn.commit()

    async def get_session_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        row = await self._fetchone(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        )
        return self._row_to_session(row) if row else None

    async def get_active_session(self, player_id: int, chat_id: int) -> Optional[Dict[str, Any]]:
        row = await self._fetchone(
            "SELECT * FROM sessions WHERE player_id = ? AND chat_id = ?",
            (player_id, chat_id),
        )
        return self._row_to_session(row) if row else None

    async def create_session(self, session: Dict[str, Any]) -> bool:
        assert self.conn is not None
        cursor = await self.conn.execute(
            """
            INSERT INTO sessions (
                id, player_id, chat_id, thread_id, hp, max_hp, greed,
                loot_value, kills, inventory_json, armor_pct, weapon_bonus,
                armor_item_id, weapon_item_id, status, enemy_json, evac_bonus,
                damage_bonus, greed_mult, chip_id,
                hard_mode, evac_penalty, entry_fee, entry_bonus,
                panel_message_id, pending_loot_json, pending_choice_json, cooldowns_json
            )
            SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM sessions WHERE player_id = ? AND chat_id = ?
            )
            """,
            (
                session["id"],
                session["player_id"],
                session["chat_id"],
                session["thread_id"],
                session["hp"],
                session["max_hp"],
                session["greed"],
                session["loot_value"],
                session["kills"],
                json.dumps(session["inventory"], ensure_ascii=False),
                session["armor_pct"],
                session["weapon_bonus"],
                session.get("armor_item_id"),
                session.get("weapon_item_id"),
                session["status"],
                json.dumps(session["enemy"], ensure_ascii=False)
                if session["enemy"]
                else None,
                session["evac_bonus"],
                session.get("damage_bonus", 0),
                session.get("greed_mult", 1.0),
                session.get("chip_id"),
                1 if session.get("hard_mode") else 0,
                session.get("evac_penalty", 0),
                session.get("entry_fee", 0),
                session.get("entry_bonus", 0),
                session.get("panel_message_id"),
                json.dumps(session.get("pending_loot", []), ensure_ascii=False),
                json.dumps(session.get("pending_choice"), ensure_ascii=False),
                json.dumps(session.get("cooldowns", {}), ensure_ascii=False),
                session["player_id"],
                session["chat_id"],
            ),
        )
        await self.conn.commit()
        return cursor.rowcount == 1

    async def update_session(self, session: Dict[str, Any]) -> None:
        assert self.conn is not None
        await self.conn.execute(
            """
            UPDATE sessions SET
                hp = ?, max_hp = ?, greed = ?, loot_value = ?, kills = ?,
                inventory_json = ?, armor_pct = ?, weapon_bonus = ?,
                armor_item_id = ?, weapon_item_id = ?,
                status = ?, enemy_json = ?, evac_bonus = ?, damage_bonus = ?, greed_mult = ?, chip_id = ?,
                hard_mode = ?, evac_penalty = ?, entry_fee = ?, entry_bonus = ?,
                panel_message_id = ?, pending_loot_json = ?, pending_choice_json = ?, cooldowns_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                session["hp"],
                session["max_hp"],
                session["greed"],
                session["loot_value"],
                session["kills"],
                json.dumps(session["inventory"], ensure_ascii=False),
                session["armor_pct"],
                session["weapon_bonus"],
                session.get("armor_item_id"),
                session.get("weapon_item_id"),
                session["status"],
                json.dumps(session["enemy"], ensure_ascii=False)
                if session["enemy"]
                else None,
                session["evac_bonus"],
                session.get("damage_bonus", 0),
                session.get("greed_mult", 1.0),
                session.get("chip_id"),
                1 if session.get("hard_mode") else 0,
                session.get("evac_penalty", 0),
                session.get("entry_fee", 0),
                session.get("entry_bonus", 0),
                session.get("panel_message_id"),
                json.dumps(session.get("pending_loot", []), ensure_ascii=False),
                json.dumps(session.get("pending_choice"), ensure_ascii=False),
                json.dumps(session.get("cooldowns", {}), ensure_ascii=False),
                session["id"],
            ),
        )
        await self.conn.commit()

    async def delete_session(self, session_id: str) -> None:
        assert self.conn is not None
        await self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await self.conn.commit()

    async def adjust_rating(
        self,
        player_id: int,
        points: int = 0,
        raids: int = 0,
        extracts: int = 0,
        deaths: int = 0,
        kills: int = 0,
        loot_value: int = 0,
    ) -> None:
        assert self.conn is not None
        await self.conn.execute(
            """
            INSERT INTO ratings (
                player_id, points, raids, extracts, deaths, kills, loot_value_total, storage_limit, raidcoins, insurance_tokens
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                points = points + excluded.points,
                raids = raids + excluded.raids,
                extracts = extracts + excluded.extracts,
                deaths = deaths + excluded.deaths,
                kills = kills + excluded.kills,
                loot_value_total = loot_value_total + excluded.loot_value_total
            """,
            (
                player_id,
                points,
                raids,
                extracts,
                deaths,
                kills,
                loot_value,
                DEFAULTS.storage_limit,
                0,
                0,
            ),
        )
        season_id, season_start, season_end = self._current_season_bounds(date.today())
        await self.ensure_season(season_id, season_start, season_end)
        await self.conn.execute(
            """
            INSERT INTO season_ratings (
                season_id, player_id, points, raids, extracts, deaths, kills, loot_value_total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(season_id, player_id) DO UPDATE SET
                points = points + excluded.points,
                raids = raids + excluded.raids,
                extracts = extracts + excluded.extracts,
                deaths = deaths + excluded.deaths,
                kills = kills + excluded.kills,
                loot_value_total = loot_value_total + excluded.loot_value_total
            """,
            (
                season_id,
                player_id,
                points,
                raids,
                extracts,
                deaths,
                kills,
                loot_value,
            ),
        )
        await self.conn.commit()

    async def reset_ratings(self) -> None:
        assert self.conn is not None
        await self.conn.execute(
            """
            UPDATE ratings SET
                points = ?,
                raids = 0,
                extracts = 0,
                deaths = 0,
                kills = 0,
                loot_value_total = 0
            """,
            (DEFAULTS.start_points,),
        )
        await self.conn.commit()

    async def get_top_ratings(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT p.tg_id, p.username, p.first_name, p.last_name, r.player_id,
                   r.points, r.raids, r.extracts, r.deaths, r.kills, r.loot_value_total
            FROM ratings r
            JOIN players p ON p.id = r.player_id
            WHERE NOT (
                r.points = ?
                AND r.raids = 0
                AND r.extracts = 0
                AND r.deaths = 0
                AND r.kills = 0
                AND r.loot_value_total = 0
            )
            ORDER BY r.points DESC
            LIMIT ?
            """,
            (DEFAULTS.start_points, limit),
        )
        return [dict(row) for row in rows]

    async def ensure_rating(self, player_id: int) -> None:
        assert self.conn is not None
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO ratings (player_id, points, storage_limit, raidcoins, insurance_tokens)
            VALUES (?, ?, ?, 0, 0)
            """,
            (player_id, DEFAULTS.start_points, DEFAULTS.storage_limit),
        )
        await self.conn.commit()

    async def get_rating(self, player_id: int) -> Dict[str, Any]:
        await self.ensure_rating(player_id)
        row = await self._fetchone(
            "SELECT * FROM ratings WHERE player_id = ?",
            (player_id,),
        )
        if not row:
            return {}
        rating = dict(row)
        if (
            rating.get("points", 0) < DEFAULTS.raid_entry_fee
            and rating.get("raids", 0) == 0
            and rating.get("extracts", 0) == 0
            and rating.get("deaths", 0) == 0
            and rating.get("kills", 0) == 0
            and rating.get("loot_value_total", 0) == 0
        ):
            await self.conn.execute(
                "UPDATE ratings SET points = ? WHERE player_id = ?",
                (DEFAULTS.start_points, player_id),
            )
            await self.conn.commit()
            rating["points"] = DEFAULTS.start_points
        return rating

    async def get_storage_limit(self, player_id: int) -> int:
        rating = await self.get_rating(player_id)
        return int(rating.get("storage_limit", DEFAULTS.storage_limit))

    async def update_storage_limit(self, player_id: int, new_limit: int) -> None:
        assert self.conn is not None
        await self.ensure_rating(player_id)
        await self.conn.execute(
            "UPDATE ratings SET storage_limit = ? WHERE player_id = ?",
            (new_limit, player_id),
        )
        await self.conn.commit()

    async def get_insurance_tokens(self, player_id: int) -> int:
        rating = await self.get_rating(player_id)
        return int(rating.get("insurance_tokens", 0))

    async def get_raidcoins(self, player_id: int) -> int:
        rating = await self.get_rating(player_id)
        return int(rating.get("raidcoins", 0))

    async def update_raidcoins(self, player_id: int, new_value: int) -> None:
        assert self.conn is not None
        await self.ensure_rating(player_id)
        await self.conn.execute(
            "UPDATE ratings SET raidcoins = ? WHERE player_id = ?",
            (new_value, player_id),
        )
        await self.conn.commit()

    async def adjust_raidcoins(self, player_id: int, delta: int) -> int:
        current = await self.get_raidcoins(player_id)
        new_value = max(0, current + delta)
        await self.update_raidcoins(player_id, new_value)
        return new_value

    async def update_insurance_tokens(self, player_id: int, new_value: int) -> None:
        assert self.conn is not None
        await self.ensure_rating(player_id)
        await self.conn.execute(
            "UPDATE ratings SET insurance_tokens = ? WHERE player_id = ?",
            (new_value, player_id),
        )
        await self.conn.commit()

    async def adjust_insurance_tokens(self, player_id: int, delta: int) -> int:
        current = await self.get_insurance_tokens(player_id)
        new_value = max(0, current + delta)
        await self.update_insurance_tokens(player_id, new_value)
        return new_value

    async def get_warehouse(self, chat_id: int) -> Dict[str, int]:
        rows = await self._fetchall(
            "SELECT item_id, qty FROM warehouse WHERE chat_id = ?",
            (chat_id,),
        )
        return {row["item_id"]: row["qty"] for row in rows if row["qty"] > 0}

    async def add_warehouse_items(self, chat_id: int, items: Dict[str, int]) -> None:
        assert self.conn is not None
        if not items:
            return
        for item_id, qty in items.items():
            if qty <= 0:
                continue
            await self.conn.execute(
                """
                INSERT INTO warehouse (chat_id, item_id, qty)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id, item_id) DO UPDATE SET
                    qty = qty + excluded.qty
                """,
                (chat_id, item_id, qty),
            )
        await self.conn.commit()

    async def add_warehouse_contribution(
        self, chat_id: int, player_id: int, value_delta: int, items_delta: int
    ) -> None:
        assert self.conn is not None
        if value_delta <= 0 and items_delta <= 0:
            return
        await self.conn.execute(
            """
            INSERT INTO warehouse_contrib (chat_id, player_id, value_total, items_total)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, player_id) DO UPDATE SET
                value_total = value_total + excluded.value_total,
                items_total = items_total + excluded.items_total
            """,
            (chat_id, player_id, max(0, value_delta), max(0, items_delta)),
        )
        await self.conn.commit()

    async def get_warehouse_top_contributor(self, chat_id: int) -> Optional[Dict[str, Any]]:
        row = await self._fetchone(
            """
            SELECT p.tg_id, p.username, p.first_name, p.last_name, c.player_id, c.value_total
            FROM warehouse_contrib c
            JOIN players p ON p.id = c.player_id
            WHERE c.chat_id = ?
            ORDER BY c.value_total DESC
            LIMIT 1
            """,
            (chat_id,),
        )
        return dict(row) if row else None

    async def get_active_event_settings(self) -> List[Dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT *
            FROM settings
            WHERE event_week_active = 1
            """,
            (),
        )
        return [dict(row) for row in rows]

    async def add_achievement(self, player_id: int, achievement_id: str) -> bool:
        assert self.conn is not None
        if not achievement_id:
            return False
        cursor = await self.conn.execute(
            """
            INSERT OR IGNORE INTO achievements (player_id, achievement_id)
            VALUES (?, ?)
            """,
            (player_id, achievement_id),
        )
        await self.conn.commit()
        return cursor.rowcount == 1

    async def add_event_contribution(
        self, chat_id: int, event_id: str, player_id: int, value_delta: int, items_delta: int
    ) -> None:
        assert self.conn is not None
        if not event_id:
            return
        if value_delta <= 0 and items_delta <= 0:
            return
        await self.conn.execute(
            """
            INSERT INTO event_contrib (chat_id, event_id, player_id, value_total, items_total)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, event_id, player_id) DO UPDATE SET
                value_total = value_total + excluded.value_total,
                items_total = items_total + excluded.items_total
            """,
            (chat_id, event_id, player_id, max(0, value_delta), max(0, items_delta)),
        )
        await self.conn.commit()

    async def get_event_totals(self, chat_id: int, event_id: str) -> Dict[str, int]:
        row = await self._fetchone(
            """
            SELECT COALESCE(SUM(value_total), 0) AS value_total,
                   COALESCE(SUM(items_total), 0) AS items_total
            FROM event_contrib
            WHERE chat_id = ? AND event_id = ?
            """,
            (chat_id, event_id),
        )
        if not row:
            return {"value_total": 0, "items_total": 0}
        return {"value_total": int(row["value_total"]), "items_total": int(row["items_total"])}

    async def get_event_top(
        self, chat_id: int, event_id: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT p.tg_id, p.username, p.first_name, p.last_name, c.player_id,
                   c.value_total, c.items_total
            FROM event_contrib c
            JOIN players p ON p.id = c.player_id
            WHERE c.chat_id = ? AND c.event_id = ?
            ORDER BY c.value_total DESC
            LIMIT ?
            """,
            (chat_id, event_id, limit),
        )
        return [dict(row) for row in rows]

    async def get_event_player(
        self, chat_id: int, event_id: str, player_id: int
    ) -> Optional[Dict[str, Any]]:
        row = await self._fetchone(
            """
            SELECT value_total, items_total
            FROM event_contrib
            WHERE chat_id = ? AND event_id = ? AND player_id = ?
            """,
            (chat_id, event_id, player_id),
        )
        return dict(row) if row else None

    async def get_inventory(self, player_id: int) -> Dict[str, int]:
        rows = await self._fetchall(
            "SELECT item_id, qty FROM inventory WHERE player_id = ?",
            (player_id,),
        )
        return {row["item_id"]: row["qty"] for row in rows if row["qty"] > 0}

    async def get_inventory_count(self, player_id: int) -> int:
        row = await self._fetchone(
            "SELECT COALESCE(SUM(qty), 0) AS total FROM inventory WHERE player_id = ?",
            (player_id,),
        )
        return int(row["total"]) if row else 0

    async def add_inventory_items(self, player_id: int, items: Dict[str, int]) -> None:
        assert self.conn is not None
        if not items:
            return
        for item_id, qty in items.items():
            if qty <= 0:
                continue
            await self.conn.execute(
                """
                INSERT INTO inventory (player_id, item_id, qty)
                VALUES (?, ?, ?)
                ON CONFLICT(player_id, item_id) DO UPDATE SET
                    qty = qty + excluded.qty
                """,
                (player_id, item_id, qty),
            )
        await self.conn.commit()

    async def adjust_inventory(self, player_id: int, deltas: Dict[str, int]) -> bool:
        assert self.conn is not None
        if not deltas:
            return True
        current = await self.get_inventory(player_id)
        for item_id, delta in deltas.items():
            new_qty = current.get(item_id, 0) + delta
            if new_qty < 0:
                return False
        for item_id, delta in deltas.items():
            new_qty = current.get(item_id, 0) + delta
            if new_qty <= 0:
                await self.conn.execute(
                    "DELETE FROM inventory WHERE player_id = ? AND item_id = ?",
                    (player_id, item_id),
                )
            else:
                await self.conn.execute(
                    """
                    INSERT INTO inventory (player_id, item_id, qty)
                    VALUES (?, ?, ?)
                    ON CONFLICT(player_id, item_id) DO UPDATE SET
                        qty = excluded.qty
                    """,
                    (player_id, item_id, new_qty),
                )
        await self.conn.commit()
        return True

    async def ensure_loadout(self, player_id: int) -> None:
        assert self.conn is not None
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO loadouts (player_id, armor_id, weapon_id, medkit_id, chip_id)
            VALUES (?, NULL, NULL, NULL, NULL)
            """,
            (player_id,),
        )
        await self.conn.commit()

    async def get_loadout(self, player_id: int) -> Dict[str, Optional[str]]:
        await self.ensure_loadout(player_id)
        row = await self._fetchone(
            "SELECT armor_id, weapon_id, medkit_id, chip_id FROM loadouts WHERE player_id = ?",
            (player_id,),
        )
        if not row:
            return {"armor_id": None, "weapon_id": None, "medkit_id": None, "chip_id": None}
        return {
            "armor_id": row["armor_id"],
            "weapon_id": row["weapon_id"],
            "medkit_id": row["medkit_id"],
            "chip_id": row["chip_id"],
        }

    async def set_loadout(self, player_id: int, **kwargs: Optional[str]) -> None:
        assert self.conn is not None
        await self.ensure_loadout(player_id)
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs.keys())
        await self.conn.execute(
            f"UPDATE loadouts SET {cols} WHERE player_id = ?",
            (*kwargs.values(), player_id),
        )
        await self.conn.commit()

    async def get_unlocked_recipes(self, player_id: int) -> set[str]:
        rows = await self._fetchall(
            "SELECT recipe_id FROM unlocked_recipes WHERE player_id = ?",
            (player_id,),
        )
        return {row["recipe_id"] for row in rows}

    async def unlock_recipe(self, player_id: int, recipe_id: str) -> None:
        assert self.conn is not None
        await self.conn.execute(
            "INSERT OR IGNORE INTO unlocked_recipes (player_id, recipe_id) VALUES (?, ?)",
            (player_id, recipe_id),
        )
        await self.conn.commit()

    async def get_daily_raids(self, player_id: int, chat_id: int, day: str) -> int:
        row = await self._fetchone(
            "SELECT count FROM daily_raids WHERE player_id = ? AND chat_id = ? AND day = ?",
            (player_id, chat_id, day),
        )
        return int(row["count"]) if row else 0

    async def increment_daily_raids(self, player_id: int, chat_id: int, day: str) -> int:
        assert self.conn is not None
        await self.conn.execute(
            """
            INSERT INTO daily_raids (player_id, chat_id, day, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(player_id, chat_id, day) DO UPDATE SET
                count = count + 1
            """,
            (player_id, chat_id, day),
        )
        await self.conn.commit()
        return await self.get_daily_raids(player_id, chat_id, day)

    async def get_daily_shop_purchases(
        self, player_id: int, chat_id: int, day: str
    ) -> int:
        row = await self._fetchone(
            "SELECT count FROM daily_shop WHERE player_id = ? AND chat_id = ? AND day = ?",
            (player_id, chat_id, day),
        )
        return int(row["count"]) if row else 0

    async def increment_daily_shop_purchases(
        self, player_id: int, chat_id: int, day: str
    ) -> int:
        assert self.conn is not None
        await self.conn.execute(
            """
            INSERT INTO daily_shop (player_id, chat_id, day, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(player_id, chat_id, day) DO UPDATE SET
                count = count + 1
            """,
            (player_id, chat_id, day),
        )
        await self.conn.commit()
        return await self.get_daily_shop_purchases(player_id, chat_id, day)

    async def has_daily_case(
        self, player_id: int, chat_id: int, day: str
    ) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM daily_cases WHERE player_id = ? AND chat_id = ? AND day = ?",
            (player_id, chat_id, day),
        )
        return row is not None

    async def mark_daily_case_opened(
        self, player_id: int, chat_id: int, day: str
    ) -> None:
        assert self.conn is not None
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO daily_cases (player_id, chat_id, day)
            VALUES (?, ?, ?)
            """,
            (player_id, chat_id, day),
        )
        await self.conn.commit()

    async def get_case_pity(self, player_id: int) -> int:
        rating = await self.get_rating(player_id)
        return int(rating.get("case_pity", 0))

    async def set_case_pity(self, player_id: int, value: int) -> None:
        assert self.conn is not None
        await self.ensure_rating(player_id)
        await self.conn.execute(
            "UPDATE ratings SET case_pity = ? WHERE player_id = ?",
            (max(0, int(value)), player_id),
        )
        await self.conn.commit()

    async def get_daily_order_progress(self, chat_id: int, day: str, item_id: str) -> int:
        row = await self._fetchone(
            "SELECT qty FROM daily_order WHERE chat_id = ? AND day = ? AND item_id = ?",
            (chat_id, day, item_id),
        )
        return int(row["qty"]) if row else 0

    async def increment_daily_order_progress(
        self, chat_id: int, day: str, item_id: str, delta: int
    ) -> int:
        assert self.conn is not None
        await self.conn.execute(
            """
            INSERT INTO daily_order (chat_id, day, item_id, qty)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, day, item_id) DO UPDATE SET
                qty = qty + excluded.qty
            """,
            (chat_id, day, item_id, delta),
        )
        await self.conn.commit()
        return await self.get_daily_order_progress(chat_id, day, item_id)

    def _current_season_bounds(self, target_date: date) -> tuple[str, str, str]:
        season_id = f"{target_date.year}-{target_date.month:02d}"
        start = target_date.replace(day=1)
        if target_date.month == 12:
            end = date(target_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(target_date.year, target_date.month + 1, 1) - timedelta(days=1)
        return season_id, start.isoformat(), end.isoformat()

    async def ensure_season(self, season_id: str, start_date: str, end_date: str) -> None:
        assert self.conn is not None
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO seasons (season_id, start_date, end_date)
            VALUES (?, ?, ?)
            """,
            (season_id, start_date, end_date),
        )
        await self.conn.commit()

    async def get_season(self, season_id: str) -> Optional[Dict[str, Any]]:
        row = await self._fetchone(
            "SELECT * FROM seasons WHERE season_id = ?",
            (season_id,),
        )
        return dict(row) if row else None

    async def close_season(self, season_id: str, rewarded: bool = False) -> None:
        assert self.conn is not None
        await self.conn.execute(
            "UPDATE seasons SET closed = 1, rewarded = ? WHERE season_id = ?",
            (1 if rewarded else 0, season_id),
        )
        await self.conn.commit()

    async def get_season_top(
        self, season_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT p.tg_id, p.username, p.first_name, p.last_name, r.player_id,
                   r.points, r.raids, r.extracts, r.deaths, r.kills, r.loot_value_total
            FROM season_ratings r
            JOIN players p ON p.id = r.player_id
            WHERE r.season_id = ?
            ORDER BY r.points DESC
            LIMIT ?
            """,
            (season_id, limit),
        )
        return [dict(row) for row in rows]

    async def get_season_player(
        self, season_id: str, player_id: int
    ) -> Optional[Dict[str, Any]]:
        row = await self._fetchone(
            """
            SELECT points, raids, extracts, deaths, kills, loot_value_total
            FROM season_ratings
            WHERE season_id = ? AND player_id = ?
            """,
            (season_id, player_id),
        )
        return dict(row) if row else None

    async def get_player_quests(
        self, player_id: int, kind: str, period: str
    ) -> List[Dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT *
            FROM player_quests
            WHERE player_id = ? AND kind = ? AND period = ?
            ORDER BY quest_id
            """,
            (player_id, kind, period),
        )
        return [dict(row) for row in rows]

    async def upsert_player_quest(self, quest: Dict[str, Any]) -> None:
        assert self.conn is not None
        await self.conn.execute(
            """
            INSERT OR IGNORE INTO player_quests (
                player_id, kind, period, quest_id, title, metric, target, progress,
                reward_points, reward_raidcoins, reward_item_id, reward_qty, completed, claimed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quest["player_id"],
                quest["kind"],
                quest["period"],
                quest["quest_id"],
                quest["title"],
                quest["metric"],
                quest["target"],
                quest.get("progress", 0),
                quest.get("reward_points", 0),
                quest.get("reward_raidcoins", 0),
                quest.get("reward_item_id"),
                quest.get("reward_qty", 0),
                quest.get("completed", 0),
                quest.get("claimed", 0),
            ),
        )
        await self.conn.commit()

    async def update_player_quest(
        self,
        player_id: int,
        kind: str,
        period: str,
        quest_id: str,
        progress: int,
        completed: int,
    ) -> None:
        assert self.conn is not None
        await self.conn.execute(
            """
            UPDATE player_quests
            SET progress = ?, completed = ?, updated_at = CURRENT_TIMESTAMP
            WHERE player_id = ? AND kind = ? AND period = ? AND quest_id = ?
            """,
            (progress, completed, player_id, kind, period, quest_id),
        )
        await self.conn.commit()

    async def claim_player_quest(
        self, player_id: int, kind: str, period: str, quest_id: str
    ) -> None:
        assert self.conn is not None
        await self.conn.execute(
            """
            UPDATE player_quests
            SET claimed = 1, updated_at = CURRENT_TIMESTAMP
            WHERE player_id = ? AND kind = ? AND period = ? AND quest_id = ?
            """,
            (player_id, kind, period, quest_id),
        )
        await self.conn.commit()

    async def get_market_listings(self, limit: int, offset: int = 0) -> List[Dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT l.id, l.seller_id, l.item_id, l.qty, l.price, l.created_at,
                   p.username, p.first_name, p.last_name
            FROM market_listings l
            JOIN players p ON p.id = l.seller_id
            ORDER BY l.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [dict(row) for row in rows]

    async def get_market_listing_count(self) -> int:
        row = await self._fetchone(
            "SELECT COUNT(1) AS total FROM market_listings",
            (),
        )
        return int(row["total"]) if row else 0

    async def get_market_listing(self, listing_id: int) -> Optional[Dict[str, Any]]:
        row = await self._fetchone(
            "SELECT * FROM market_listings WHERE id = ?",
            (listing_id,),
        )
        return dict(row) if row else None

    async def get_player_market_listings(self, player_id: int) -> List[Dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT id, item_id, qty, price, created_at
            FROM market_listings
            WHERE seller_id = ?
            ORDER BY created_at DESC
            """,
            (player_id,),
        )
        return [dict(row) for row in rows]

    async def get_player_market_listing_count(self, player_id: int) -> int:
        row = await self._fetchone(
            "SELECT COUNT(1) AS total FROM market_listings WHERE seller_id = ?",
            (player_id,),
        )
        return int(row["total"]) if row else 0

    async def create_market_listing(
        self, seller_id: int, item_id: str, qty: int, price: int
    ) -> int:
        assert self.conn is not None
        cursor = await self.conn.execute(
            """
            INSERT INTO market_listings (seller_id, item_id, qty, price)
            VALUES (?, ?, ?, ?)
            """,
            (seller_id, item_id, qty, price),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def delete_market_listing(self, listing_id: int) -> None:
        assert self.conn is not None
        await self.conn.execute(
            "DELETE FROM market_listings WHERE id = ?",
            (listing_id,),
        )
        await self.conn.commit()

    async def get_daily_stats(self, player_id: int, day: str) -> Dict[str, int]:
        row = await self._fetchone(
            """
            SELECT raidcoins_earned, sells_count, raids_started
            FROM daily_stats
            WHERE player_id = ? AND day = ?
            """,
            (player_id, day),
        )
        if not row:
            return {"raidcoins_earned": 0, "sells_count": 0, "raids_started": 0}
        return {
            "raidcoins_earned": int(row["raidcoins_earned"]),
            "sells_count": int(row["sells_count"]),
            "raids_started": int(row["raids_started"]),
        }

    async def update_daily_stats(
        self,
        player_id: int,
        day: str,
        raidcoins_delta: int = 0,
        sells_delta: int = 0,
        raids_delta: int = 0,
    ) -> Dict[str, int]:
        assert self.conn is not None
        await self.conn.execute(
            """
            INSERT INTO daily_stats (player_id, day, raidcoins_earned, sells_count, raids_started)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(player_id, day) DO UPDATE SET
                raidcoins_earned = raidcoins_earned + excluded.raidcoins_earned,
                sells_count = sells_count + excluded.sells_count,
                raids_started = raids_started + excluded.raids_started
            """,
            (player_id, day, max(0, raidcoins_delta), max(0, sells_delta), max(0, raids_delta)),
        )
        await self.conn.commit()
        return await self.get_daily_stats(player_id, day)

    async def _fetchone(self, query: str, params: tuple) -> Optional[aiosqlite.Row]:
        assert self.conn is not None
        async with self.conn.execute(query, params) as cursor:
            return await cursor.fetchone()

    async def _fetchall(self, query: str, params: tuple) -> List[aiosqlite.Row]:
        assert self.conn is not None
        async with self.conn.execute(query, params) as cursor:
            return await cursor.fetchall()

    def _row_to_session(self, row: aiosqlite.Row) -> Dict[str, Any]:
        inventory = json.loads(row["inventory_json"]) if row["inventory_json"] else {}
        enemy = json.loads(row["enemy_json"]) if row["enemy_json"] else None
        pending_loot = (
            json.loads(row["pending_loot_json"]) if row["pending_loot_json"] else []
        )
        pending_choice_raw = None
        if "pending_choice_json" in row.keys():
            pending_choice_raw = row["pending_choice_json"]
        pending_choice = json.loads(pending_choice_raw) if pending_choice_raw else None
        cooldowns = json.loads(row["cooldowns_json"]) if row["cooldowns_json"] else {}
        return {
            "id": row["id"],
            "player_id": row["player_id"],
            "chat_id": row["chat_id"],
            "thread_id": row["thread_id"],
            "hp": row["hp"],
            "max_hp": row["max_hp"],
            "greed": row["greed"],
            "loot_value": row["loot_value"],
            "kills": row["kills"],
            "inventory": inventory,
            "armor_pct": row["armor_pct"],
            "weapon_bonus": row["weapon_bonus"],
            "armor_item_id": row["armor_item_id"],
            "weapon_item_id": row["weapon_item_id"],
            "status": row["status"],
            "enemy": enemy,
            "evac_bonus": row["evac_bonus"],
            "damage_bonus": row["damage_bonus"] if row["damage_bonus"] is not None else 0,
            "greed_mult": row["greed_mult"] if row["greed_mult"] is not None else 1.0,
            "chip_id": row["chip_id"],
            "hard_mode": bool(row["hard_mode"]) if row["hard_mode"] is not None else False,
            "evac_penalty": row["evac_penalty"] if row["evac_penalty"] is not None else 0,
            "entry_fee": row["entry_fee"] if row["entry_fee"] is not None else 0,
            "entry_bonus": row["entry_bonus"] if row["entry_bonus"] is not None else 0,
            "panel_message_id": row["panel_message_id"],
            "pending_loot": pending_loot,
            "pending_choice": pending_choice,
            "cooldowns": cooldowns,
        }

    async def _ensure_column(self, table: str, column: str, column_type: str) -> None:
        assert self.conn is not None
        try:
            await self.conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
            )
        except Exception:
            return
