import os
import json
import time
import datetime
import threading
import traceback

import numpy as np
import pytz
import yfinance as yf
from flask import Flask, jsonify, request, render_template_string

from us_holidays import is_us_equity_holiday

app = Flask(__name__)

# ============================================================
# CONFIG
# ============================================================
SECRET_KEY = os.environ.get("RUN_KEY", "changeme")
# Secret-safe auth hardening:
# Prefer passing RUN_KEY via the X-Run-Key header. URL query keys are still
# supported temporarily for backward compatibility, but they are deprecated
# because platform access logs can expose full request URLs.
ALLOW_QUERY_KEY_AUTH = os.environ.get("ALLOW_QUERY_KEY_AUTH", "true").lower() in ["1", "true", "yes", "on"]
# State persistence: use a mounted Railway volume or explicit STATE_DIR when available.
# This solves the phone/GitHub redeploy problem where local state.json can reset on every deploy.
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("PERSISTENT_STATE_DIR") or os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
STATE_FILENAME = os.environ.get("STATE_FILENAME", os.environ.get("STATE_FILE", "state.json"))
if STATE_DIR:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
    except Exception:
        pass
    STATE_FILE = os.path.join(STATE_DIR, os.path.basename(STATE_FILENAME))
    STATE_PERSISTENCE_MODE = "persistent_volume"
else:
    STATE_FILE = STATE_FILENAME
    STATE_PERSISTENCE_MODE = "local_ephemeral"
MARKET_CACHE_TTL = int(os.environ.get("MARKET_CACHE_TTL", "300"))

MARKET_TZ = pytz.timezone(os.environ.get("MARKET_TZ", "America/Chicago"))
REGULAR_OPEN_HOUR = int(os.environ.get("REGULAR_OPEN_HOUR", "8"))
REGULAR_OPEN_MINUTE = int(os.environ.get("REGULAR_OPEN_MINUTE", "30"))
REGULAR_CLOSE_HOUR = int(os.environ.get("REGULAR_CLOSE_HOUR", "15"))
REGULAR_CLOSE_MINUTE = int(os.environ.get("REGULAR_CLOSE_MINUTE", "0"))

AUTO_RUN_ENABLED = os.environ.get("AUTO_RUN_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
AUTO_RUN_INTERVAL_SECONDS = int(os.environ.get("AUTO_RUN_INTERVAL_SECONDS", "300"))
AUTO_RUN_MARKET_ONLY = os.environ.get("AUTO_RUN_MARKET_ONLY", "true").lower() not in ["0", "false", "no", "off"]

# Critical safety fix:
# Manual /paper/run no longer places entries/exits after regular session by default.
ALLOW_MANUAL_AFTER_HOURS_TRADING = os.environ.get(
    "ALLOW_MANUAL_AFTER_HOURS_TRADING", "false"
).lower() in ["1", "true", "yes", "on"]

MAX_DAILY_LOSS_PCT = float(os.environ.get("MAX_DAILY_LOSS_PCT", "0.03"))
MAX_INTRADAY_DRAWDOWN_PCT = float(os.environ.get("MAX_INTRADAY_DRAWDOWN_PCT", "0.025"))
COOLDOWN_SECONDS = int(os.environ.get("COOLDOWN_SECONDS", "1800"))
MIN_TRADE_ALLOC = float(os.environ.get("MIN_TRADE_ALLOC", "50"))

# Entry extension guard. Blocks chasing overstretched 5m moves.
EXTENSION_MAX_ABOVE_DAY_OPEN = float(os.environ.get("EXTENSION_MAX_ABOVE_DAY_OPEN", "0.055"))
EXTENSION_MAX_BELOW_DAY_OPEN = float(os.environ.get("EXTENSION_MAX_BELOW_DAY_OPEN", "0.055"))
EXTENSION_NEAR_HIGH_FACTOR = float(os.environ.get("EXTENSION_NEAR_HIGH_FACTOR", "0.996"))
EXTENSION_NEAR_LOW_FACTOR = float(os.environ.get("EXTENSION_NEAR_LOW_FACTOR", "1.004"))
EXTENSION_BIG_MOVE_CONFIRM = float(os.environ.get("EXTENSION_BIG_MOVE_CONFIRM", "0.035"))
EXTENSION_MAX_FROM_MA20 = float(os.environ.get("EXTENSION_MAX_FROM_MA20", "0.035"))

# Rotation guard. These are intentionally tighter than the prior version to reduce churn.
ROTATION_SCORE_MULTIPLIER = float(os.environ.get("ROTATION_SCORE_MULTIPLIER", "1.45"))
ROTATION_MIN_SCORE_EDGE = float(os.environ.get("ROTATION_MIN_SCORE_EDGE", "0.0065"))
ROTATION_MIN_HOLD_SECONDS = int(os.environ.get("ROTATION_MIN_HOLD_SECONDS", "2700"))
ROTATION_KEEP_WINNER_PCT = float(os.environ.get("ROTATION_KEEP_WINNER_PCT", "0.005"))

# Profit protection. Allows the bot to keep managing open risk, but blocks fresh risk
# after a strong day or after a meaningful giveback from the intraday equity peak.
DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT = float(os.environ.get("DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT", "0.0075"))
DAY_PROFIT_HARD_LOCK_PCT = float(os.environ.get("DAY_PROFIT_HARD_LOCK_PCT", "0.0100"))
DAY_PROFIT_GIVEBACK_LOCK_PCT = float(os.environ.get("DAY_PROFIT_GIVEBACK_LOCK_PCT", "0.0030"))

# Entry quality controls. These reduce opening-churn, weak low-score fills,
# and single-sector overconcentration when one theme dominates the scanner.
OPENING_WARMUP_MINUTES = int(os.environ.get("OPENING_WARMUP_MINUTES", "15"))
MAX_NEW_ENTRIES_PER_CYCLE = int(os.environ.get("MAX_NEW_ENTRIES_PER_CYCLE", "2"))
MIN_ENTRY_SCORE_RISK_ON = float(os.environ.get("MIN_ENTRY_SCORE_RISK_ON", "0.0120"))
MIN_ENTRY_SCORE_CONSTRUCTIVE = float(os.environ.get("MIN_ENTRY_SCORE_CONSTRUCTIVE", "0.0120"))
MIN_ENTRY_SCORE_NEUTRAL = float(os.environ.get("MIN_ENTRY_SCORE_NEUTRAL", "0.0140"))
MIN_ENTRY_SCORE_DEFENSIVE = float(os.environ.get("MIN_ENTRY_SCORE_DEFENSIVE", "0.0160"))
MIN_SHORT_ENTRY_SCORE = float(os.environ.get("MIN_SHORT_ENTRY_SCORE", "0.0120"))
MAX_SECTOR_EXPOSURE_PCT = float(os.environ.get("MAX_SECTOR_EXPOSURE_PCT", "0.45"))
MAX_POSITIONS_PER_SECTOR = int(os.environ.get("MAX_POSITIONS_PER_SECTOR", "3"))

# Adaptive Tech Leadership Mode. This loosens tech/growth exposure limits only
# when QQQ/XLK-style leadership is confirmed. The goal is to participate in real
# tech-led bull trends without blindly chasing every tech signal. Non-tech sectors
# still use the normal caps above.
TECH_LEADERSHIP_MODE_ENABLED = os.environ.get("TECH_LEADERSHIP_MODE_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
TECH_LEADERSHIP_SECTORS = [s.strip().upper() for s in os.environ.get("TECH_LEADERSHIP_SECTORS", "XLK,XLY").split(",") if s.strip()]
TECH_LEADERSHIP_MIN_RISK_SCORE = int(os.environ.get("TECH_LEADERSHIP_MIN_RISK_SCORE", "70"))
TECH_LEADERSHIP_MAX_EXPOSURE_PCT = float(os.environ.get("TECH_LEADERSHIP_MAX_EXPOSURE_PCT", "0.65"))
TECH_LEADERSHIP_CAUTION_EXPOSURE_PCT = float(os.environ.get("TECH_LEADERSHIP_CAUTION_EXPOSURE_PCT", "0.60"))
TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR = int(os.environ.get("TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR", "4"))
TECH_LEADERSHIP_SCORE_RELIEF = float(os.environ.get("TECH_LEADERSHIP_SCORE_RELIEF", "0.0015"))
TECH_LEADERSHIP_BREADTH_SCORE_BUMP = float(os.environ.get("TECH_LEADERSHIP_BREADTH_SCORE_BUMP", "0.0005"))
TECH_LEADERSHIP_BREADTH_ALLOC_REDUCTION = float(os.environ.get("TECH_LEADERSHIP_BREADTH_ALLOC_REDUCTION", "0.95"))
TECH_LEADERSHIP_ALLOW_GAP_PULLBACK = os.environ.get("TECH_LEADERSHIP_ALLOW_GAP_PULLBACK", "true").lower() not in ["0", "false", "no", "off"]

# Self-defense feedback loop. These rules make the bot stop hunting after a bad sequence
# and automatically compile intraday/end-of-day diagnostics into state.json.
SELF_DEFENSE_STOP_LOSS_LIMIT = int(os.environ.get("SELF_DEFENSE_STOP_LOSS_LIMIT", "2"))
SELF_DEFENSE_REALIZED_LOSS_PAUSE_PCT = float(os.environ.get("SELF_DEFENSE_REALIZED_LOSS_PAUSE_PCT", "0.005"))
SELF_DEFENSE_HARD_DAILY_LOSS_PCT = float(os.environ.get("SELF_DEFENSE_HARD_DAILY_LOSS_PCT", "0.010"))
TRAIL_ACTIVATION_PROFIT_PCT = float(os.environ.get("TRAIL_ACTIVATION_PROFIT_PCT", "0.0075"))
LATE_DAY_ENTRY_CUTOFF_MINUTES = int(os.environ.get("LATE_DAY_ENTRY_CUTOFF_MINUTES", "30"))
ENTRY_SCORE_LOSS_STEP = float(os.environ.get("ENTRY_SCORE_LOSS_STEP", "0.004"))
VIX_RISING_SCORE_BUMP = float(os.environ.get("VIX_RISING_SCORE_BUMP", "0.002"))
RATES_RISING_SCORE_BUMP = float(os.environ.get("RATES_RISING_SCORE_BUMP", "0.001"))
VIX_RISING_ALLOC_REDUCTION = float(os.environ.get("VIX_RISING_ALLOC_REDUCTION", "0.70"))
MAX_REPORTS_STORED = int(os.environ.get("MAX_REPORTS_STORED", "80"))

# Futures / breadth / relative-strength confirmation. These are confirmation layers,
# not standalone trade triggers. They raise quality requirements or reduce size when
# index futures or breadth conflict with the regular-session risk-on signal.
FUTURES_BIAS_ENABLED = os.environ.get("FUTURES_BIAS_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
FUTURES_ES_SYMBOL = os.environ.get("FUTURES_ES_SYMBOL", "ES=F")
FUTURES_NQ_SYMBOL = os.environ.get("FUTURES_NQ_SYMBOL", "NQ=F")
FUTURES_BULLISH_NQ_PCT = float(os.environ.get("FUTURES_BULLISH_NQ_PCT", "0.0035"))
FUTURES_BULLISH_ES_PCT = float(os.environ.get("FUTURES_BULLISH_ES_PCT", "0.0020"))
FUTURES_BEARISH_NQ_PCT = float(os.environ.get("FUTURES_BEARISH_NQ_PCT", "-0.0035"))
FUTURES_BEARISH_ES_PCT = float(os.environ.get("FUTURES_BEARISH_ES_PCT", "-0.0030"))
FUTURES_GAP_UP_CHASE_PCT = float(os.environ.get("FUTURES_GAP_UP_CHASE_PCT", "0.0075"))
FUTURES_SCORE_BUMP_CAUTION = float(os.environ.get("FUTURES_SCORE_BUMP_CAUTION", "0.0025"))
FUTURES_SCORE_BUMP_BEARISH = float(os.environ.get("FUTURES_SCORE_BUMP_BEARISH", "0.0040"))
FUTURES_ALLOC_REDUCTION_CAUTION = float(os.environ.get("FUTURES_ALLOC_REDUCTION_CAUTION", "0.80"))
FUTURES_ALLOC_REDUCTION_BEARISH = float(os.environ.get("FUTURES_ALLOC_REDUCTION_BEARISH", "0.55"))

BREADTH_CONFIRMATION_ENABLED = os.environ.get("BREADTH_CONFIRMATION_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
BREADTH_SCORE_BUMP_NARROW = float(os.environ.get("BREADTH_SCORE_BUMP_NARROW", "0.0020"))
BREADTH_ALLOC_REDUCTION_NARROW = float(os.environ.get("BREADTH_ALLOC_REDUCTION_NARROW", "0.85"))
RELATIVE_STRENGTH_SCORE_BONUS = float(os.environ.get("RELATIVE_STRENGTH_SCORE_BONUS", "0.0020"))
RELATIVE_STRENGTH_SCORE_PENALTY = float(os.environ.get("RELATIVE_STRENGTH_SCORE_PENALTY", "0.0015"))

# Winner protection / profit-taking. These stop good trades from becoming full losers
# and bank part of a move while leaving a runner.
PARTIAL_PROFIT_ENABLED = os.environ.get("PARTIAL_PROFIT_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
PARTIAL_PROFIT_TRIGGER_PCT = float(os.environ.get("PARTIAL_PROFIT_TRIGGER_PCT", "0.0200"))
PARTIAL_PROFIT_FRACTION = float(os.environ.get("PARTIAL_PROFIT_FRACTION", "0.33"))
PROFIT_LOCK_LEVEL_1_PCT = float(os.environ.get("PROFIT_LOCK_LEVEL_1_PCT", "0.0075"))
PROFIT_LOCK_LEVEL_2_PCT = float(os.environ.get("PROFIT_LOCK_LEVEL_2_PCT", "0.0125"))
PROFIT_LOCK_LEVEL_3_PCT = float(os.environ.get("PROFIT_LOCK_LEVEL_3_PCT", "0.0200"))
PROFIT_LOCK_BREAKEVEN_PCT = float(os.environ.get("PROFIT_LOCK_BREAKEVEN_PCT", "0.0010"))
PROFIT_LOCK_LEVEL_3_FLOOR_PCT = float(os.environ.get("PROFIT_LOCK_LEVEL_3_FLOOR_PCT", "0.0075"))

# Stricter behavior after stop-outs. One stop forces stronger, sector-aligned entries;
# two stop-outs already trigger self-defense from the feedback loop.
POST_STOP_SCORE_BUMP = float(os.environ.get("POST_STOP_SCORE_BUMP", "0.0040"))
POST_STOP_REQUIRE_SECTOR_LEADER = os.environ.get("POST_STOP_REQUIRE_SECTOR_LEADER", "true").lower() not in ["0", "false", "no", "off"]
POST_STOP_EXCEPTIONAL_SCORE = float(os.environ.get("POST_STOP_EXCEPTIONAL_SCORE", "0.0300"))

# Pullback/reclaim watchlist for strong symbols that were rejected only because they
# were extended. The bot can consider them again after a controlled pullback.
PULLBACK_RECLAIM_ENABLED = os.environ.get("PULLBACK_RECLAIM_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
PULLBACK_WATCH_TTL_SECONDS = int(os.environ.get("PULLBACK_WATCH_TTL_SECONDS", "3600"))
PULLBACK_MAX_ABOVE_MA20 = float(os.environ.get("PULLBACK_MAX_ABOVE_MA20", "0.0120"))
PULLBACK_RECLAIM_SCORE_BONUS = float(os.environ.get("PULLBACK_RECLAIM_SCORE_BONUS", "0.0010"))

# Controlled pullback starter. This is a conservative participation valve for
# strong trend days where futures are extended and breadth is tech-concentrated.
# It allows at most a small, high-quality starter after the opening noise has
# passed, while preserving all late-day, self-defense, sector, and stop controls.
CONTROLLED_PULLBACK_ENTRY_ENABLED = os.environ.get("CONTROLLED_PULLBACK_ENTRY_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
CONTROLLED_PULLBACK_MIN_SCORE = float(os.environ.get("CONTROLLED_PULLBACK_MIN_SCORE", "0.0120"))
CONTROLLED_PULLBACK_SCORE_DISCOUNT = float(os.environ.get("CONTROLLED_PULLBACK_SCORE_DISCOUNT", "0.0050"))
CONTROLLED_PULLBACK_MINUTES_AFTER_OPEN = int(os.environ.get("CONTROLLED_PULLBACK_MINUTES_AFTER_OPEN", "60"))
CONTROLLED_PULLBACK_NO_ENTRY_LAST_MINUTES = int(os.environ.get("CONTROLLED_PULLBACK_NO_ENTRY_LAST_MINUTES", "60"))
CONTROLLED_PULLBACK_MAX_ENTRIES_PER_DAY = int(os.environ.get("CONTROLLED_PULLBACK_MAX_ENTRIES_PER_DAY", "1"))
CONTROLLED_PULLBACK_ALLOC_FACTOR = float(os.environ.get("CONTROLLED_PULLBACK_ALLOC_FACTOR", "0.50"))
CONTROLLED_PULLBACK_REQUIRE_CAUTION_CONTEXT = os.environ.get("CONTROLLED_PULLBACK_REQUIRE_CAUTION_CONTEXT", "true").lower() not in ["0", "false", "no", "off"]
CONTROLLED_PULLBACK_REQUIRE_SECTOR_LEADER = os.environ.get("CONTROLLED_PULLBACK_REQUIRE_SECTOR_LEADER", "true").lower() not in ["0", "false", "no", "off"]
CONTROLLED_PULLBACK_ALLOW_EMPTY_BOOK_ONLY = os.environ.get("CONTROLLED_PULLBACK_ALLOW_EMPTY_BOOK_ONLY", "true").lower() not in ["0", "false", "no", "off"]


# Expanded scanner universe and bucket-risk controls. These let the bot scan
# AI/data-center infrastructure, bitcoin-miner/HPC compute, power/cooling,
# and small-cap momentum without treating those volatile names like mega-cap tech.
EXPANDED_SCANNER_ENABLED = os.environ.get("EXPANDED_SCANNER_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
CATALYST_MOMENTUM_ENABLED = os.environ.get("CATALYST_MOMENTUM_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
CATALYST_MIN_INTRADAY_MOVE_PCT = float(os.environ.get("CATALYST_MIN_INTRADAY_MOVE_PCT", "0.08"))
CATALYST_VOLUME_SURGE_RATIO = float(os.environ.get("CATALYST_VOLUME_SURGE_RATIO", "2.0"))
CATALYST_SCORE_BONUS = float(os.environ.get("CATALYST_SCORE_BONUS", "0.0040"))
CATALYST_STRONG_SCORE_BONUS = float(os.environ.get("CATALYST_STRONG_SCORE_BONUS", "0.0060"))
THEME_CONFIRMATION_ENABLED = os.environ.get("THEME_CONFIRMATION_ENABLED", "true").lower() not in ["0", "false", "no", "off"]
THEME_CONFIRMATION_MIN_SIGNALS = int(os.environ.get("THEME_CONFIRMATION_MIN_SIGNALS", "2"))
THEME_CONFIRMATION_MIN_SCORE = float(os.environ.get("THEME_CONFIRMATION_MIN_SCORE", "0.0060"))
THEME_CONFIRMATION_SCORE_BONUS = float(os.environ.get("THEME_CONFIRMATION_SCORE_BONUS", "0.0015"))

# Bucket-level exposure limits and sizing factors. These are applied in addition
# to sector caps, self-defense, stop losses, controlled pullbacks, and profit guards.
MEGA_CAP_AI_ALLOC_FACTOR = float(os.environ.get("MEGA_CAP_AI_ALLOC_FACTOR", "1.00"))
SEMI_LEADER_ALLOC_FACTOR = float(os.environ.get("SEMI_LEADER_ALLOC_FACTOR", "0.85"))
DATA_CENTER_INFRA_ALLOC_FACTOR = float(os.environ.get("DATA_CENTER_INFRA_ALLOC_FACTOR", "0.70"))
BITCOIN_AI_COMPUTE_ALLOC_FACTOR = float(os.environ.get("BITCOIN_AI_COMPUTE_ALLOC_FACTOR", "0.45"))
SMALL_CAP_MOMENTUM_ALLOC_FACTOR = float(os.environ.get("SMALL_CAP_MOMENTUM_ALLOC_FACTOR", "0.35"))
BENCHMARK_ETF_ALLOC_FACTOR = float(os.environ.get("BENCHMARK_ETF_ALLOC_FACTOR", "0.75"))

# Precious metals / safe-haven bucket. These are separate from tech and small-cap momentum
# so gold, silver, miners, and royalty/streaming names can be used during dollar/rate weakness
# or defensive rotations without over-sizing high-beta miners.
PRECIOUS_METALS_ALLOC_FACTOR = float(os.environ.get("PRECIOUS_METALS_ALLOC_FACTOR", "0.55"))
PRECIOUS_METALS_MAX_EXPOSURE_PCT = float(os.environ.get("PRECIOUS_METALS_MAX_EXPOSURE_PCT", "0.30"))
PRECIOUS_METALS_MAX_POSITIONS = int(os.environ.get("PRECIOUS_METALS_MAX_POSITIONS", "3"))
PRECIOUS_METALS_SAFE_HAVEN_SCORE_BONUS = float(os.environ.get("PRECIOUS_METALS_SAFE_HAVEN_SCORE_BONUS", "0.0030"))
PRECIOUS_METALS_TREND_SCORE_BONUS = float(os.environ.get("PRECIOUS_METALS_TREND_SCORE_BONUS", "0.0015"))
PRECIOUS_METALS_WEAK_DOLLAR_SCORE_BONUS = float(os.environ.get("PRECIOUS_METALS_WEAK_DOLLAR_SCORE_BONUS", "0.0010"))

DATA_CENTER_INFRA_MAX_EXPOSURE_PCT = float(os.environ.get("DATA_CENTER_INFRA_MAX_EXPOSURE_PCT", "0.40"))
BITCOIN_AI_COMPUTE_MAX_EXPOSURE_PCT = float(os.environ.get("BITCOIN_AI_COMPUTE_MAX_EXPOSURE_PCT", "0.25"))
SMALL_CAP_MOMENTUM_MAX_EXPOSURE_PCT = float(os.environ.get("SMALL_CAP_MOMENTUM_MAX_EXPOSURE_PCT", "0.15"))
DATA_CENTER_INFRA_MAX_POSITIONS = int(os.environ.get("DATA_CENTER_INFRA_MAX_POSITIONS", "3"))
BITCOIN_AI_COMPUTE_MAX_POSITIONS = int(os.environ.get("BITCOIN_AI_COMPUTE_MAX_POSITIONS", "2"))
SMALL_CAP_MOMENTUM_MAX_POSITIONS = int(os.environ.get("SMALL_CAP_MOMENTUM_MAX_POSITIONS", "2"))

RUN_LOCK = threading.Lock()
AUTO_THREAD_STARTED = False

# ============================================================
# UNIVERSE
# ============================================================
MEGA_CAP_AI = ["MSFT", "AMZN", "GOOGL", "META", "PLTR"]
SEMI_LEADERS = ["NVDA", "AMD", "AVGO", "TSM", "MU", "ARM", "MRVL", "ON", "LSCC", "MPWR", "MCHP", "ALAB", "ACLS", "UCTT"]
CLOUD_CYBER_SOFTWARE = ["SNOW", "NET", "CRWD", "PANW", "SHOP", "ROKU", "COIN"]
DATA_CENTER_HARDWARE_NETWORKING = ["SMCI", "ANET", "DELL", "HPE", "CIEN", "GLW", "COHR", "LITE", "AAOI", "WDC", "STX", "TER"]
DATA_CENTER_POWER_COOLING = ["VRT", "ETN", "PWR", "GEV", "VST", "CEG", "NRG", "MOD", "POWL", "IESC"]
BITCOIN_AI_COMPUTE = ["HUT", "IREN", "CIFR", "WULF", "CLSK", "MARA", "RIOT", "BTDR", "CORZ", "APLD"]
SMALL_CAP_MOMENTUM = ["SOUN", "RGTI", "QBTS", "IONQ", "RKLB", "JOBY", "ACHR", "RXRX", "TEM", "BBAI", "AI"]
ENERGY_LEADERS = ["XOM", "CVX"]
PRECIOUS_METAL_ETFS = ["GLD", "IAU", "PHYS", "SLV", "PSLV"]
PRECIOUS_METAL_MINERS = ["GDX", "GDXJ", "SIL", "SILJ", "NEM", "GOLD", "AEM", "WPM", "FNV", "RGLD", "PAAS", "AG", "HL", "CDE"]
PRECIOUS_METALS = PRECIOUS_METAL_ETFS + PRECIOUS_METAL_MINERS
PRECIOUS_METALS_MACRO = ["GLD", "SLV", "GDX", "GDXJ", "UUP"]
BENCHMARKS = ["SPY", "QQQ"]

UNIVERSE = list(dict.fromkeys(
    SEMI_LEADERS
    + MEGA_CAP_AI
    + CLOUD_CYBER_SOFTWARE
    + DATA_CENTER_HARDWARE_NETWORKING
    + DATA_CENTER_POWER_COOLING
    + BITCOIN_AI_COMPUTE
    + SMALL_CAP_MOMENTUM
    + PRECIOUS_METALS
    + ENERGY_LEADERS
    + BENCHMARKS
))

SECTOR_ETFS = ["XLK", "XLY", "XLF", "XLE", "XLV", "XLU", "XLI", "XLP"]
FUTURES_SYMBOLS = [FUTURES_ES_SYMBOL, FUTURES_NQ_SYMBOL]
BREADTH_SYMBOLS = ["RSP", "IWM", "DIA", "ARKK"]
MACRO_SYMBOLS = ["SPY", "QQQ", "^VIX", "^TNX"] + SECTOR_ETFS + BREADTH_SYMBOLS + PRECIOUS_METALS_MACRO

SYMBOL_SECTOR = {
    "NVDA": "XLK", "AMD": "XLK", "AVGO": "XLK", "TSM": "XLK", "MU": "XLK", "ARM": "XLK",
    "MRVL": "XLK", "ON": "XLK", "LSCC": "XLK", "MPWR": "XLK", "MCHP": "XLK", "ALAB": "XLK", "ACLS": "XLK", "UCTT": "XLK",
    "MSFT": "XLK", "PLTR": "XLK", "SNOW": "XLK", "NET": "XLK", "CRWD": "XLK", "PANW": "XLK",
    "AMZN": "XLY", "SHOP": "XLY", "ROKU": "XLY", "GOOGL": "XLY", "META": "XLY",
    "COIN": "XLF",
    "SMCI": "XLK", "ANET": "XLK", "DELL": "XLK", "HPE": "XLK", "CIEN": "XLK", "GLW": "XLK", "COHR": "XLK", "LITE": "XLK", "AAOI": "XLK",
    "WDC": "XLK", "STX": "XLK", "TER": "XLK",
    "VRT": "XLI", "ETN": "XLI", "PWR": "XLI", "GEV": "XLI", "MOD": "XLI", "POWL": "XLI", "IESC": "XLI",
    "VST": "XLU", "CEG": "XLU", "NRG": "XLU",
    "HUT": "XLK", "IREN": "XLK", "CIFR": "XLK", "WULF": "XLK", "CLSK": "XLK", "MARA": "XLK", "RIOT": "XLK", "BTDR": "XLK", "CORZ": "XLK", "APLD": "XLK",
    "SOUN": "XLK", "RGTI": "XLK", "QBTS": "XLK", "IONQ": "XLK", "RKLB": "XLI", "JOBY": "XLI", "ACHR": "XLI",
    "RXRX": "XLV", "TEM": "XLV", "BBAI": "XLK", "AI": "XLK",
    "GLD": "PRECIOUS_METALS", "IAU": "PRECIOUS_METALS", "PHYS": "PRECIOUS_METALS",
    "SLV": "PRECIOUS_METALS", "PSLV": "PRECIOUS_METALS",
    "GDX": "PRECIOUS_METALS", "GDXJ": "PRECIOUS_METALS", "SIL": "PRECIOUS_METALS", "SILJ": "PRECIOUS_METALS",
    "NEM": "PRECIOUS_METALS", "GOLD": "PRECIOUS_METALS", "AEM": "PRECIOUS_METALS",
    "WPM": "PRECIOUS_METALS", "FNV": "PRECIOUS_METALS", "RGLD": "PRECIOUS_METALS",
    "PAAS": "PRECIOUS_METALS", "AG": "PRECIOUS_METALS", "HL": "PRECIOUS_METALS", "CDE": "PRECIOUS_METALS",
    "XOM": "XLE", "CVX": "XLE",
    "SPY": "SPY", "QQQ": "QQQ"
}

SYMBOL_BUCKET = {}
for _s in MEGA_CAP_AI:
    SYMBOL_BUCKET[_s] = "mega_cap_ai"
for _s in SEMI_LEADERS:
    SYMBOL_BUCKET[_s] = "semi_leaders"
for _s in CLOUD_CYBER_SOFTWARE:
    SYMBOL_BUCKET[_s] = "cloud_cyber_software"
for _s in DATA_CENTER_HARDWARE_NETWORKING + DATA_CENTER_POWER_COOLING:
    SYMBOL_BUCKET[_s] = "data_center_infra"
for _s in BITCOIN_AI_COMPUTE:
    SYMBOL_BUCKET[_s] = "bitcoin_ai_compute"
for _s in SMALL_CAP_MOMENTUM:
    SYMBOL_BUCKET[_s] = "small_cap_momentum"
for _s in PRECIOUS_METALS:
    SYMBOL_BUCKET[_s] = "precious_metals"
for _s in ENERGY_LEADERS:
    SYMBOL_BUCKET[_s] = "energy_leaders"
for _s in BENCHMARKS:
    SYMBOL_BUCKET[_s] = "benchmark_etf"

BUCKET_CONFIG = {
    "mega_cap_ai": {"alloc_factor": MEGA_CAP_AI_ALLOC_FACTOR, "max_exposure_pct": 0.65, "max_positions": 4},
    "semi_leaders": {"alloc_factor": SEMI_LEADER_ALLOC_FACTOR, "max_exposure_pct": 0.60, "max_positions": 4},
    "cloud_cyber_software": {"alloc_factor": 0.85, "max_exposure_pct": 0.45, "max_positions": 3},
    "data_center_infra": {"alloc_factor": DATA_CENTER_INFRA_ALLOC_FACTOR, "max_exposure_pct": DATA_CENTER_INFRA_MAX_EXPOSURE_PCT, "max_positions": DATA_CENTER_INFRA_MAX_POSITIONS},
    "bitcoin_ai_compute": {"alloc_factor": BITCOIN_AI_COMPUTE_ALLOC_FACTOR, "max_exposure_pct": BITCOIN_AI_COMPUTE_MAX_EXPOSURE_PCT, "max_positions": BITCOIN_AI_COMPUTE_MAX_POSITIONS},
    "small_cap_momentum": {"alloc_factor": SMALL_CAP_MOMENTUM_ALLOC_FACTOR, "max_exposure_pct": SMALL_CAP_MOMENTUM_MAX_EXPOSURE_PCT, "max_positions": SMALL_CAP_MOMENTUM_MAX_POSITIONS},
    "precious_metals": {"alloc_factor": PRECIOUS_METALS_ALLOC_FACTOR, "max_exposure_pct": PRECIOUS_METALS_MAX_EXPOSURE_PCT, "max_positions": PRECIOUS_METALS_MAX_POSITIONS},
    "energy_leaders": {"alloc_factor": 0.75, "max_exposure_pct": 0.35, "max_positions": 2},
    "benchmark_etf": {"alloc_factor": BENCHMARK_ETF_ALLOC_FACTOR, "max_exposure_pct": 0.35, "max_positions": 2},
    "default": {"alloc_factor": 0.75, "max_exposure_pct": 0.30, "max_positions": 2},
}

_market_cache = {"ts": 0, "data": None}
_price_cache = {"ts": 0, "data": {}}


# ============================================================
# STATE
# ============================================================
def now_local():
    return datetime.datetime.now(MARKET_TZ)


def now_ts():
    return int(time.time())


def today_key():
    return now_local().strftime("%Y-%m-%d")


def local_ts_text(ts=None):
    if ts is None:
        ts = time.time()
    return datetime.datetime.fromtimestamp(ts, MARKET_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")


def default_risk_controls():
    return {
        "date": today_key(),
        "day_start_equity": 10000.0,
        "day_peak_equity": 10000.0,
        "day_pnl_pct": 0.0,
        "daily_loss_pct": 0.0,
        "daily_drawdown_pct": 0.0,  # kept for dashboard compatibility; now never negative
        "intraday_drawdown_pct": 0.0,
        "profit_guard_active": False,
        "profit_guard_reason": "",
        "halted": False,
        "halt_reason": "",
        "cooldowns": {}
    }


def default_realized_pnl():
    return {
        "date": today_key(),
        "today": 0.0,
        "total": 0.0,
        "wins_today": 0,
        "losses_today": 0,
        "wins_total": 0,
        "losses_total": 0
    }


def default_performance():
    return {
        "realized_pnl_today": 0.0,
        "realized_pnl_total": 0.0,
        "unrealized_pnl": 0.0,
        "wins_today": 0,
        "losses_today": 0,
        "wins_total": 0,
        "losses_total": 0,
        "open_positions": {}
    }


def default_auto_runner():
    return {
        "enabled": AUTO_RUN_ENABLED,
        "market_only": AUTO_RUN_MARKET_ONLY,
        "interval_seconds": AUTO_RUN_INTERVAL_SECONDS,
        "market_open_now": False,
        "market_clock": {},
        "last_run_ts": None,
        "last_run_local": None,
        "last_run_source": None,
        "last_result": None,
        "last_attempt_ts": None,
        "last_attempt_local": None,
        "last_attempt_source": None,
        "last_successful_run_ts": None,
        "last_successful_run_local": None,
        "last_successful_run_source": None,
        "last_skip_ts": None,
        "last_skip_local": None,
        "last_skip_reason": None,
        "last_error": None,
        "last_error_trace": None,
        "thread_started": False
    }


def default_feedback_loop():
    return {
        "date": today_key(),
        "updated_local": None,
        "self_defense_mode": False,
        "block_new_entries": False,
        "hard_halt": False,
        "late_day_entry_cutoff": False,
        "reasons": [],
        "actions": [],
        "stop_losses_today": 0,
        "realized_loss_pct": 0.0,
        "dynamic_min_long_score": MIN_ENTRY_SCORE_RISK_ON,
        "vix_rising": False,
        "rates_rising": False
    }


def default_reports():
    return {
        "date": today_key(),
        "last_intraday_report": None,
        "last_end_of_day_report": None,
        "intraday_history": [],
        "daily_history": []
    }


def default_scanner_audit():
    return {
        "date": today_key(),
        "last_updated_local": None,
        "last_cycle_source": None,
        "signals_found": 0,
        "accepted_entries": [],
        "blocked_entries": [],
        "rejected_signals": [],
        "long_signals": [],
        "short_signals": [],
        "bucket_summary": {},
        "notes": []
    }


def default_state():
    return {
        "cash": 10000.0,
        "equity": 10000.0,
        "peak": 10000.0,
        "positions": {},
        "history": [],
        "trades": [],
        "last_market": {},
        "risk_controls": default_risk_controls(),
        "auto_runner": default_auto_runner(),
        "realized_pnl": default_realized_pnl(),
        "performance": default_performance(),
        "feedback_loop": default_feedback_loop(),
        "reports": default_reports(),
        "pullback_watchlist": {},
        "scanner_audit": default_scanner_audit()
    }


def load_state():
    state = default_state()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                state.update(loaded)
        except Exception:
            pass

    state.setdefault("cash", 10000.0)
    state.setdefault("equity", 10000.0)
    state.setdefault("peak", state.get("equity", 10000.0))
    state.setdefault("positions", {})
    state.setdefault("history", [])
    state.setdefault("trades", [])
    state.setdefault("last_market", {})
    state.setdefault("risk_controls", default_risk_controls())
    state.setdefault("auto_runner", default_auto_runner())
    state.setdefault("realized_pnl", default_realized_pnl())
    state.setdefault("performance", default_performance())
    state.setdefault("feedback_loop", default_feedback_loop())
    state.setdefault("reports", default_reports())
    state.setdefault("pullback_watchlist", {})
    state.setdefault("scanner_audit", default_scanner_audit())

    # Backfill newer fields without breaking old state.json.
    rc = state["risk_controls"]
    rc.setdefault("day_pnl_pct", 0.0)
    rc.setdefault("daily_loss_pct", max(0.0, float(rc.get("daily_drawdown_pct", 0.0))))
    rc["daily_drawdown_pct"] = max(0.0, float(rc.get("daily_drawdown_pct", 0.0)))
    rc.setdefault("profit_guard_active", False)
    rc.setdefault("profit_guard_reason", "")
    rc.setdefault("self_defense_active", False)
    rc.setdefault("self_defense_reason", "")
    rc.setdefault("cooldowns", {})

    for symbol, pos in state.get("positions", {}).items():
        if not isinstance(pos, dict):
            continue
        pos.setdefault("side", "long")
        pos.setdefault("entry_time", int(time.time()))
        pos.setdefault("score", 0.0)
        pos.setdefault("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN"))
        pos.setdefault("bucket", SYMBOL_BUCKET.get(symbol, "default"))
        pos.setdefault("adds", 0)
        pos.setdefault("partial_taken", False)
        pos.setdefault("last_price", pos.get("entry", 0))
        if pos.get("side", "long") == "short":
            pos.setdefault("trough", pos.get("last_price", pos.get("entry", 0)))
            pos.setdefault("margin", float(pos.get("entry", 0)) * float(pos.get("shares", 0)))
        else:
            pos.setdefault("peak", pos.get("last_price", pos.get("entry", 0)))

    return state


def save_state(state):
    directory = os.path.dirname(os.path.abspath(STATE_FILE))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    backup = STATE_FILE + ".bak"
    with open(tmp, "w") as f:
        json.dump(state, f)
    if os.path.exists(STATE_FILE):
        try:
            import shutil
            shutil.copy2(STATE_FILE, backup)
        except Exception:
            pass
    os.replace(tmp, STATE_FILE)


portfolio = load_state()


# ============================================================
# MARKET CLOCK
# ============================================================
def market_clock():
    now = now_local()
    open_dt = now.replace(
        hour=REGULAR_OPEN_HOUR,
        minute=REGULAR_OPEN_MINUTE,
        second=0,
        microsecond=0
    )
    close_dt = now.replace(
        hour=REGULAR_CLOSE_HOUR,
        minute=REGULAR_CLOSE_MINUTE,
        second=0,
        microsecond=0
    )

    # Check explicit full-day US equity holidays first (deterministic, no-network)
    try:
        if is_us_equity_holiday(now):
            reason = "holiday"
            is_open = False
            return {
                "is_open": bool(is_open),
                "now_local": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "reason": reason,
                "regular_open_local": open_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "regular_close_local": close_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "timezone": str(MARKET_TZ)
            }
    except Exception:
        # If holiday predicate fails for any reason, fall back to prior behavior
        pass

    if now.weekday() >= 5:
        reason = "weekend"
        is_open = False
    elif now < open_dt:
        reason = "before_regular_session"
        is_open = False
    elif now >= close_dt:
        reason = "after_regular_session"
        is_open = False
    else:
        reason = "regular_session"
        is_open = True

    return {
        "is_open": bool(is_open),
        "now_local": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "reason": reason,
        "regular_open_local": open_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "regular_close_local": close_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "timezone": str(MARKET_TZ)
    }


def regular_open_datetime(reference=None):
    reference = reference or now_local()
    return reference.replace(
        hour=REGULAR_OPEN_HOUR,
        minute=REGULAR_OPEN_MINUTE,
        second=0,
        microsecond=0
    )


def opening_warmup_status(clock=None):
    """Return whether fresh entries should be paused during the opening noise window."""
    clock = clock or market_clock()
    current = now_local()
    open_dt = regular_open_datetime(current)
    elapsed_seconds = max(0, int((current - open_dt).total_seconds()))
    warmup_seconds = max(0, OPENING_WARMUP_MINUTES * 60)
    active = bool(clock.get("is_open", False)) and elapsed_seconds < warmup_seconds

    return {
        "active": bool(active),
        "minutes_since_open": round(elapsed_seconds / 60, 1),
        "required_warmup_minutes": OPENING_WARMUP_MINUTES,
        "seconds_remaining": max(0, warmup_seconds - elapsed_seconds) if active else 0,
        "reason": "opening_warmup_active" if active else "ok"
    }

# rest of file unchanged...
