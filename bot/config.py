from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "bot.db"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEB_APP_URL = os.getenv("WEB_APP_URL", "").strip()


@dataclass(frozen=True)
class BalanceDefaults:
    start_hp: int = 100
    raid_limit: int = 20
    storage_limit: int = 50
    storage_upgrade_step: int = 10
    storage_upgrade_base_cost: int = 180
    storage_upgrade_cost_step: int = 120
    storage_upgrade_max: int = 150
    warehouse_goal: int = 500
    warehouse_goal_step: int = 50
    event_week_days: int = 7
    event_week_goal: int = 10000
    event_week_goal_step: int = 1000
    event_order_mult: float = 2.0
    cooldown_loot: int = 6
    cooldown_move: int = 6
    cooldown_fight: int = 5
    cooldown_evac: int = 8
    cooldown_medkit: int = 6
    greed_loot: int = 12
    greed_move: int = 8
    greed_fight: int = 15
    greed_medkit: int = 4
    greed_evac_fail: int = 10
    event_base: float = 0.16
    event_greed_mult: float = 0.0028
    evac_base: float = 0.86
    evac_greed_penalty: float = 0.0025
    extract_base_points: int = 40
    kill_points: int = 10
    death_penalty: int = 30
    daily_raid_limit: int = 150
    start_points: int = 50
    raid_entry_fee: int = 20
    raid_entry_bonus: int = 10
    hard_raid_chance: float = 0.12
    hard_raid_loot_bonus_chance: float = 0.45
    hard_raid_evac_penalty: float = 0.12
    controller_legendary_chance: float = 0.35
    evac_event_cost_min: int = 5
    evac_event_cost_max: int = 10
    insurance_max_tokens: int = 2
    shop_daily_limit: int = 3
    shop_tax_step: float = 0.15
    shop_price_medkit: int = 70
    shop_price_insurance: int = 130
    shop_price_evac_beacon: int = 160
    sell_mult: float = 0.6
    daily_order_target: int = 30
    daily_order_reward: int = 3
    daily_order_bonus: int = 40
    daily_case_items: int = 3
    daily_case_pity_days: int = 7
    daily_sell_raidcoin_cap: int = 400
    daily_sell_count_cap: int = 30
    market_listing_cap: int = 10
    quest_daily_count: int = 3
    quest_weekly_count: int = 2
    season_reward_top1: int = 300
    season_reward_top2: int = 200
    season_reward_top3: int = 120
    suspicious_ip_limit: int = 3


DEFAULTS = BalanceDefaults()
