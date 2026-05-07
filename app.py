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
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
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
        "pullback_watchlist": {}
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
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
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


# ============================================================
# HELPERS
# ============================================================
AUTH_HINT = "Set RUN_KEY in Railway and send it with the X-Run-Key header. Do not put secrets in the URL."


def auth_context():
    """Return sanitized auth status. Never returns or logs the supplied key."""
    header_key = request.headers.get("X-Run-Key")
    query_key_present = "key" in request.args
    query_key = request.args.get("key") if ALLOW_QUERY_KEY_AUTH else None

    supplied = header_key or query_key
    method = "header" if header_key else ("query" if query_key_present else "none")

    ok = SECRET_KEY == "changeme" or (supplied is not None and supplied == SECRET_KEY)
    deprecated_query_key_used = bool(query_key_present)

    warning = None
    if deprecated_query_key_used:
        warning = (
            "URL query-key authentication is deprecated because request URLs can appear "
            "in Railway/Gunicorn access logs. Rotate RUN_KEY if it was exposed and use "
            "the X-Run-Key header going forward."
        )

    if query_key_present and not ALLOW_QUERY_KEY_AUTH:
        ok = False
        warning = "URL query-key authentication is disabled. Use the X-Run-Key header."

    return {
        "ok": bool(ok),
        "method": method,
        "query_key_present": bool(query_key_present),
        "deprecated_query_key_used": deprecated_query_key_used,
        "warning": warning,
        "header_supported": True,
        "query_key_auth_allowed": bool(ALLOW_QUERY_KEY_AUTH)
    }


def key_ok():
    return bool(auth_context().get("ok", False))


def auth_failed_payload():
    return {
        "error": "unauthorized",
        "hint": AUTH_HINT,
        "preferred_auth": "X-Run-Key header",
        "curl_example": 'curl -H "X-Run-Key: YOUR_RUN_KEY" https://trading-bot-clean.up.railway.app/paper/run',
        "query_key_auth_allowed_temporarily": bool(ALLOW_QUERY_KEY_AUTH)
    }


def attach_auth_warning(payload):
    ctx = auth_context()
    if isinstance(payload, dict) and ctx.get("warning"):
        payload.setdefault("_auth_warning", {
            "message": ctx.get("warning"),
            "auth_method_used": ctx.get("method"),
            "preferred_auth": "X-Run-Key header",
            "rotate_run_key_recommended_if_exposed": True
        })
    return payload


def clean(arr):
    arr = np.asarray(arr).astype(float).flatten()
    return arr[~np.isnan(arr)]


def _series_from_df(df, column):
    if df is None or getattr(df, "empty", True):
        return np.array([])

    try:
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            matches = [c for c in df.columns if c[0] == column or c[-1] == column]
            if matches:
                return clean(df[matches[0]].values)
    except Exception:
        pass

    if column not in df:
        return np.array([])

    return clean(df[column].values)


def price_series(df, column="Close"):
    return _series_from_df(df, column)


def download_prices(symbol, period="5d", interval="5m"):
    try:
        return yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
    except Exception:
        return None


def latest_price(symbol):
    now = time.time()
    cached = _price_cache["data"].get(symbol)
    if cached and now - cached["ts"] < 60:
        return cached["price"]

    try:
        df = download_prices(symbol, period="1d", interval="5m")
        prices = price_series(df, "Close")
        if len(prices) == 0:
            return None
        px = float(prices[-1])
        _price_cache["data"][symbol] = {"ts": now, "price": px}
        return px
    except Exception:
        return None


def pct_change(prices, bars):
    if len(prices) <= bars or float(prices[-bars]) == 0:
        return 0.0
    return float((prices[-1] / prices[-bars]) - 1)


def sma(prices, bars):
    if len(prices) < bars:
        return None
    return float(np.mean(prices[-bars:]))


def trend_state(prices):
    if len(prices) < 30:
        return "unknown"

    fast = sma(prices, 8)
    slow = sma(prices, 20)

    if fast is None or slow is None:
        return "unknown"

    if prices[-1] > slow and fast > slow:
        return "up"
    if prices[-1] < slow and fast < slow:
        return "down"
    return "flat"


def position_pnl_pct(pos, px):
    entry = float(pos.get("entry", 0))
    if entry <= 0:
        return 0.0

    if pos.get("side", "long") == "short":
        return (entry - float(px)) / entry

    return (float(px) - entry) / entry


def position_pnl_dollars(pos, px):
    shares = float(pos.get("shares", 0))
    entry = float(pos.get("entry", 0))
    if pos.get("side", "long") == "short":
        return (entry - float(px)) * shares
    return (float(px) - entry) * shares


def position_value(pos, px):
    shares = float(pos.get("shares", 0))
    if pos.get("side", "long") == "short":
        margin = float(pos.get("margin", float(pos.get("entry", 0)) * shares))
        return margin + position_pnl_dollars(pos, px)
    return shares * float(px)


def record_trade(action, symbol, side, px, shares, extra=None):
    trade = {
        "time": int(time.time()),
        "action": action,
        "symbol": symbol,
        "side": side,
        "price": round(float(px), 4),
        "shares": round(float(shares), 6)
    }

    if extra:
        trade.update(extra)

    portfolio.setdefault("trades", []).append(trade)
    portfolio["trades"] = portfolio["trades"][-500:]


def get_realized_pnl():
    rp = portfolio.setdefault("realized_pnl", default_realized_pnl())

    if rp.get("date") != today_key():
        rp["date"] = today_key()
        rp["today"] = 0.0
        rp["wins_today"] = 0
        rp["losses_today"] = 0

    rp.setdefault("today", 0.0)
    rp.setdefault("total", 0.0)
    rp.setdefault("wins_today", 0)
    rp.setdefault("losses_today", 0)
    rp.setdefault("wins_total", 0)
    rp.setdefault("losses_total", 0)
    return rp


def add_realized_pnl(pnl_dollars):
    pnl_dollars = float(pnl_dollars)
    rp = get_realized_pnl()

    rp["today"] = round(float(rp.get("today", 0.0)) + pnl_dollars, 2)
    rp["total"] = round(float(rp.get("total", 0.0)) + pnl_dollars, 2)

    if pnl_dollars >= 0:
        rp["wins_today"] = int(rp.get("wins_today", 0)) + 1
        rp["wins_total"] = int(rp.get("wins_total", 0)) + 1
    else:
        rp["losses_today"] = int(rp.get("losses_today", 0)) + 1
        rp["losses_total"] = int(rp.get("losses_total", 0)) + 1

    return rp


def get_risk_controls():
    rc = portfolio.setdefault("risk_controls", default_risk_controls())
    today = today_key()

    if rc.get("date") != today:
        current_equity = float(portfolio.get("equity", 10000.0))
        rc.clear()
        rc.update(default_risk_controls())
        rc["day_start_equity"] = current_equity
        rc["day_peak_equity"] = current_equity

    rc.setdefault("cooldowns", {})
    rc.setdefault("profit_guard_active", False)
    rc.setdefault("profit_guard_reason", "")
    rc.setdefault("self_defense_active", False)
    rc.setdefault("self_defense_reason", "")
    return rc


def prune_cooldowns():
    rc = get_risk_controls()
    now = time.time()
    rc["cooldowns"] = {
        symbol: until for symbol, until in rc.get("cooldowns", {}).items()
        if float(until) > now
    }
    return rc["cooldowns"]


def is_in_cooldown(symbol):
    cooldowns = prune_cooldowns()
    return float(cooldowns.get(symbol, 0)) > time.time()


def set_cooldown(symbol):
    rc = get_risk_controls()
    rc.setdefault("cooldowns", {})[symbol] = time.time() + COOLDOWN_SECONDS


def update_daily_risk_controls(equity):
    rc = get_risk_controls()
    equity = float(equity)
    start = max(float(rc.get("day_start_equity", equity)), 0.01)
    old_peak = max(float(rc.get("day_peak_equity", equity)), 0.01)
    peak = max(old_peak, equity, 0.01)

    day_pnl_pct = (equity - start) / start
    daily_loss_pct = max(0.0, (start - equity) / start)
    intraday_drawdown_pct = max(0.0, (peak - equity) / peak)

    rc["day_peak_equity"] = peak
    rc["day_pnl_pct"] = round(day_pnl_pct * 100, 3)
    rc["daily_loss_pct"] = round(daily_loss_pct * 100, 3)
    rc["daily_drawdown_pct"] = round(daily_loss_pct * 100, 3)  # dashboard compatibility
    rc["intraday_drawdown_pct"] = round(intraday_drawdown_pct * 100, 3)

    daily_loss_triggered = daily_loss_pct >= MAX_DAILY_LOSS_PCT
    intraday_dd_triggered = intraday_drawdown_pct >= MAX_INTRADAY_DRAWDOWN_PCT

    realized_today = float(get_realized_pnl().get("today", 0.0))
    realized_loss_pct = max(0.0, -realized_today / start)
    hard_realized_loss_triggered = realized_loss_pct >= SELF_DEFENSE_HARD_DAILY_LOSS_PCT

    if daily_loss_triggered:
        rc["halted"] = True
        rc["halt_reason"] = f"daily loss limit hit ({MAX_DAILY_LOSS_PCT * 100:.1f}%)"
    elif intraday_dd_triggered:
        rc["halted"] = True
        rc["halt_reason"] = f"intraday drawdown limit hit ({MAX_INTRADAY_DRAWDOWN_PCT * 100:.1f}%)"
    elif hard_realized_loss_triggered:
        rc["halted"] = True
        rc["halt_reason"] = f"self-defense hard realized loss hit ({SELF_DEFENSE_HARD_DAILY_LOSS_PCT * 100:.2f}%)"

    # Profit guard controls entries/rotations only. Existing stops still work.
    peak_return_pct = (peak - start) / start
    giveback_pct = (peak - equity) / start

    rc["profit_guard_active"] = False
    rc["profit_guard_reason"] = ""

    if peak_return_pct >= DAY_PROFIT_HARD_LOCK_PCT:
        rc["profit_guard_active"] = True
        rc["profit_guard_reason"] = f"day profit hard lock reached ({DAY_PROFIT_HARD_LOCK_PCT * 100:.2f}%)"
    elif day_pnl_pct >= DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT:
        rc["profit_guard_active"] = True
        rc["profit_guard_reason"] = f"day profit pause reached ({DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT * 100:.2f}%)"
    elif peak_return_pct >= DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT and giveback_pct >= DAY_PROFIT_GIVEBACK_LOCK_PCT:
        rc["profit_guard_active"] = True
        rc["profit_guard_reason"] = f"profit giveback guard triggered ({DAY_PROFIT_GIVEBACK_LOCK_PCT * 100:.2f}%)"

    return rc


def performance_snapshot():
    rp = get_realized_pnl()
    open_pnl = {}
    unrealized_total = 0.0

    for s, pos in portfolio.get("positions", {}).items():
        px = float(pos.get("last_price", pos.get("entry", 0)))
        pnl_dollars = position_pnl_dollars(pos, px)
        pnl_pct = position_pnl_pct(pos, px) * 100
        unrealized_total += pnl_dollars

        open_pnl[s] = {
            "side": pos.get("side", "long"),
            "entry": round(float(pos.get("entry", 0)), 4),
            "last_price": round(px, 4),
            "shares": round(float(pos.get("shares", 0)), 6),
            "pnl_dollars": round(float(pnl_dollars), 2),
            "pnl_pct": round(float(pnl_pct), 2),
            "score": round(float(pos.get("score", 0.0)), 6),
            "sector": pos.get("sector", SYMBOL_SECTOR.get(s, "UNKNOWN")),
            "entry_time": pos.get("entry_time"),
            "adds": pos.get("adds", 0)
        }

    perf = {
        "realized_pnl_today": round(float(rp.get("today", 0.0)), 2),
        "realized_pnl_total": round(float(rp.get("total", 0.0)), 2),
        "wins_today": int(rp.get("wins_today", 0)),
        "losses_today": int(rp.get("losses_today", 0)),
        "wins_total": int(rp.get("wins_total", 0)),
        "losses_total": int(rp.get("losses_total", 0)),
        "unrealized_pnl": round(float(unrealized_total), 2),
        "open_positions": open_pnl
    }
    portfolio["performance"] = perf
    return perf


def reset_state(starting_cash=10000.0):
    global portfolio
    portfolio = default_state()
    portfolio["cash"] = float(starting_cash)
    portfolio["equity"] = float(starting_cash)
    portfolio["peak"] = float(starting_cash)
    portfolio["risk_controls"] = default_risk_controls()
    portfolio["risk_controls"]["day_start_equity"] = float(starting_cash)
    portfolio["risk_controls"]["day_peak_equity"] = float(starting_cash)
    portfolio["auto_runner"] = default_auto_runner()
    portfolio["realized_pnl"] = default_realized_pnl()
    portfolio["performance"] = default_performance()
    save_state(portfolio)
    return portfolio



# ============================================================
# FUTURES / BREADTH CONFIRMATION
# ============================================================
def _safe_pct_change_from_first(prices):
    prices = clean(prices)
    if len(prices) < 2 or float(prices[0]) == 0:
        return 0.0
    return float((prices[-1] / prices[0]) - 1)


def _intraday_trend(prices):
    prices = clean(prices)
    if len(prices) < 20:
        return "unknown"
    ma20 = sma(prices, 20)
    ma8 = sma(prices, 8)
    if ma20 is None or ma8 is None:
        return "unknown"
    if prices[-1] > ma20 and ma8 >= ma20:
        return "up"
    if prices[-1] < ma20 and ma8 <= ma20:
        return "down"
    return "flat"


def futures_bias_status():
    if not FUTURES_BIAS_ENABLED:
        return {"enabled": False, "bias": "disabled", "action": "normal"}

    payload = {
        "enabled": True,
        "es_symbol": FUTURES_ES_SYMBOL,
        "nq_symbol": FUTURES_NQ_SYMBOL,
        "es_pct": 0.0,
        "nq_pct": 0.0,
        "nq_vs_es_pct": 0.0,
        "es_trend": "unknown",
        "nq_trend": "unknown",
        "bias": "unknown",
        "action": "normal",
        "reason": "insufficient_futures_data"
    }

    try:
        es_df = download_prices(FUTURES_ES_SYMBOL, period="2d", interval="5m")
        nq_df = download_prices(FUTURES_NQ_SYMBOL, period="2d", interval="5m")
        es = price_series(es_df, "Close")
        nq = price_series(nq_df, "Close")
        if len(es) < 20 or len(nq) < 20:
            return payload

        es_pct = _safe_pct_change_from_first(es)
        nq_pct = _safe_pct_change_from_first(nq)
        nq_vs_es = nq_pct - es_pct
        es_trend = _intraday_trend(es)
        nq_trend = _intraday_trend(nq)

        payload.update({
            "es_pct": round(es_pct * 100, 3),
            "nq_pct": round(nq_pct * 100, 3),
            "nq_vs_es_pct": round(nq_vs_es * 100, 3),
            "es_trend": es_trend,
            "nq_trend": nq_trend
        })

        if nq_pct >= FUTURES_GAP_UP_CHASE_PCT:
            payload.update({
                "bias": "bullish_but_extended",
                "action": "gap_chase_protection",
                "reason": "nq_gap_up_extended_avoid_chasing_first_move"
            })
        elif nq_pct >= FUTURES_BULLISH_NQ_PCT and es_pct >= FUTURES_BULLISH_ES_PCT and nq_vs_es >= 0 and nq_trend != "down":
            payload.update({
                "bias": "bullish",
                "action": "normal",
                "reason": "es_and_nq_confirm_risk_on_with_nq_leadership"
            })
        elif nq_pct <= FUTURES_BEARISH_NQ_PCT or es_pct <= FUTURES_BEARISH_ES_PCT or (nq_trend == "down" and es_trend == "down"):
            payload.update({
                "bias": "bearish",
                "action": "block_opening_longs",
                "reason": "futures_weak_or_downtrend"
            })
        elif es_pct > 0 and nq_pct < 0:
            payload.update({
                "bias": "mixed_tech_caution",
                "action": "tech_caution",
                "reason": "es_green_but_nq_red_avoid_aggressive_tech_concentration"
            })
        elif es_pct < 0 or nq_pct < 0 or nq_trend == "flat":
            payload.update({
                "bias": "cautious",
                "action": "reduce_aggression",
                "reason": "futures_mixed_or_soft"
            })
        else:
            payload.update({
                "bias": "mixed",
                "action": "normal",
                "reason": "futures_not_decisive"
            })
    except Exception as exc:
        payload["error"] = str(exc)

    return payload


def breadth_status(series=None, spy_5d=None, qqq_5d=None):
    if not BREADTH_CONFIRMATION_ENABLED:
        return {"enabled": False, "state": "disabled", "action": "normal"}

    series = series or {}
    spy_5d = 0.0 if spy_5d is None else float(spy_5d)
    qqq_5d = 0.0 if qqq_5d is None else float(qqq_5d)

    rsp_5d = pct_change(series.get("RSP", np.array([])), 5)
    iwm_5d = pct_change(series.get("IWM", np.array([])), 5)
    dia_5d = pct_change(series.get("DIA", np.array([])), 5)
    arkk_5d = pct_change(series.get("ARKK", np.array([])), 5)

    participation = sum(1 for x in [rsp_5d, iwm_5d, dia_5d] if x > 0)
    qqq_minus_rsp = qqq_5d - rsp_5d

    state = "supportive"
    action = "normal"
    reason = "broad_participation_supportive"

    if qqq_5d > 0 and rsp_5d <= 0 and iwm_5d <= 0:
        state = "narrow_mega_cap_led"
        action = "reduce_aggression"
        reason = "qqq_positive_but_equal_weight_and_small_caps_weak"
    elif participation <= 1 and (spy_5d > 0 or qqq_5d > 0):
        state = "mixed_narrow"
        action = "reduce_aggression"
        reason = "limited_breadth_under_index_strength"
    elif qqq_minus_rsp > 0.025:
        state = "tech_concentrated"
        action = "tech_caution"
        reason = "qqq_outperforming_equal_weight_by_large_margin"
    elif spy_5d < 0 and qqq_5d < 0:
        state = "weak"
        action = "risk_off_confirmation"
        reason = "major_indices_weak"

    return {
        "enabled": True,
        "state": state,
        "action": action,
        "reason": reason,
        "rsp_5d_pct": round(rsp_5d * 100, 2),
        "iwm_5d_pct": round(iwm_5d * 100, 2),
        "dia_5d_pct": round(dia_5d * 100, 2),
        "arkk_5d_pct": round(arkk_5d * 100, 2),
        "qqq_minus_rsp_5d_pct": round(qqq_minus_rsp * 100, 2),
        "positive_breadth_count": int(participation)
    }


def precious_metals_status(series=None, spy_5d=None, qqq_5d=None, vix_5d=None, rates_5d=None):
    """Evaluate whether gold/silver/miners deserve defensive or momentum attention."""
    series = series or {}
    spy_5d = 0.0 if spy_5d is None else float(spy_5d)
    qqq_5d = 0.0 if qqq_5d is None else float(qqq_5d)
    vix_5d = 0.0 if vix_5d is None else float(vix_5d)
    rates_5d = 0.0 if rates_5d is None else float(rates_5d)

    gld = series.get("GLD", np.array([]))
    slv = series.get("SLV", np.array([]))
    gdx = series.get("GDX", np.array([]))
    gdxj = series.get("GDXJ", np.array([]))
    uup = series.get("UUP", np.array([]))

    gld_5d = pct_change(gld, 5)
    slv_5d = pct_change(slv, 5)
    gdx_5d = pct_change(gdx, 5)
    gdxj_5d = pct_change(gdxj, 5)
    uup_5d = pct_change(uup, 5)

    gld_trend = trend_state(gld)
    slv_trend = trend_state(slv)
    miners_confirming = (gdx_5d > 0 and gdxj_5d > 0)
    metals_positive_count = sum(1 for x in [gld_5d, slv_5d, gdx_5d, gdxj_5d] if x > 0)
    metals_outperform_spy = max(gld_5d, slv_5d, gdx_5d, gdxj_5d) > spy_5d
    dollar_weak = uup_5d < 0
    rates_falling = rates_5d < 0
    market_soft = spy_5d < 0 or qqq_5d < 0
    volatility_rising = vix_5d > 0

    state = "neutral"
    action = "normal"
    reason = "precious_metals_not_confirmed"
    score_bonus = 0.0

    if metals_positive_count >= 2 and metals_outperform_spy and (market_soft or volatility_rising or rates_falling or dollar_weak):
        state = "safe_haven_bid"
        action = "allow_defensive_metals"
        reason = "metals_outperforming_with_safe_haven_macro_support"
        score_bonus = PRECIOUS_METALS_SAFE_HAVEN_SCORE_BONUS
        if dollar_weak:
            score_bonus += PRECIOUS_METALS_WEAK_DOLLAR_SCORE_BONUS
    elif metals_positive_count >= 3 and (gld_trend == "up" or slv_trend == "up") and miners_confirming:
        state = "bullish_momentum"
        action = "allow_metals_momentum"
        reason = "gold_silver_miners_confirming_uptrend"
        score_bonus = PRECIOUS_METALS_TREND_SCORE_BONUS
    elif gld_5d < 0 and slv_5d < 0 and gdx_5d < 0:
        state = "weak"
        action = "avoid_metals"
        reason = "gold_silver_miners_not_confirming"

    return {
        "enabled": True,
        "state": state,
        "action": action,
        "reason": reason,
        "score_bonus": round(float(score_bonus), 6),
        "gld_5d_pct": round(gld_5d * 100, 2),
        "slv_5d_pct": round(slv_5d * 100, 2),
        "gdx_5d_pct": round(gdx_5d * 100, 2),
        "gdxj_5d_pct": round(gdxj_5d * 100, 2),
        "uup_5d_pct": round(uup_5d * 100, 2),
        "dollar_weak": bool(dollar_weak),
        "rates_falling": bool(rates_falling),
        "market_soft": bool(market_soft),
        "volatility_rising": bool(volatility_rising),
        "metals_positive_count": int(metals_positive_count),
        "miners_confirming": bool(miners_confirming)
    }


# ============================================================
# MARKET / REGIME ENGINE
# ============================================================
def market_status(force=False):
    now = time.time()
    if not force and _market_cache["data"] and now - _market_cache["ts"] < MARKET_CACHE_TTL:
        return _market_cache["data"]

    series = {}
    for symbol in MACRO_SYMBOLS:
        try:
            df = download_prices(symbol, period="30d", interval="1d")
            prices = price_series(df, "Close")
            if len(prices) >= 10:
                series[symbol] = prices
        except Exception:
            continue

    spy = series.get("SPY", np.array([]))
    qqq = series.get("QQQ", np.array([]))
    vix = series.get("^VIX", np.array([]))
    tnx = series.get("^TNX", np.array([]))

    spy_trend = trend_state(spy)
    qqq_trend = trend_state(qqq)
    vix_5d = pct_change(vix, 5)
    tnx_5d = pct_change(tnx, 5)
    spy_5d = pct_change(spy, 5)
    qqq_5d = pct_change(qqq, 5)

    risk_score = 50

    if spy_trend == "up":
        risk_score += 15
    elif spy_trend == "down":
        risk_score -= 18

    if qqq_trend == "up":
        risk_score += 12
    elif qqq_trend == "down":
        risk_score -= 15

    if vix_5d < -0.05:
        risk_score += 10
    elif vix_5d > 0.08:
        risk_score -= 15

    if qqq_5d > spy_5d:
        risk_score += 5
    else:
        risk_score -= 3

    if tnx_5d > 0.05 and qqq_5d < 0:
        risk_score -= 6

    sector_scores = []
    for symbol in SECTOR_ETFS:
        prices = series.get(symbol, np.array([]))
        sector_scores.append((symbol, pct_change(prices, 5)))

    sector_scores = sorted(sector_scores, key=lambda x: x[1], reverse=True)
    sector_leaders = [s for s, _ in sector_scores[:3]]

    defensive_sectors = ["XLU", "XLV", "XLP"]
    risk_on_sectors = ["XLK", "XLY", "XLF", "XLE"]

    defensive_count = sum(1 for s in sector_leaders if s in defensive_sectors)
    risk_on_sector_count = sum(1 for s in sector_leaders if s in risk_on_sectors)

    defensive_leadership = defensive_count >= 2
    growth_leadership = risk_on_sector_count >= 1

    if growth_leadership:
        risk_score += 5
    if defensive_leadership:
        risk_score -= 5

    risk_score = int(max(0, min(100, risk_score)))

    if risk_score >= 70:
        mode = "risk_on"
        trade_permission = "aggressive"
        regime = "bull"
    elif risk_score >= 55:
        mode = "constructive"
        trade_permission = "normal"
        regime = "bull" if spy_trend == "up" else "neutral"
    elif risk_score >= 40:
        mode = "neutral"
        trade_permission = "reduced"
        regime = "neutral"
    elif risk_score >= 25:
        mode = "risk_off"
        trade_permission = "defensive"
        regime = "bear"
    else:
        mode = "crash_warning"
        trade_permission = "protective"
        regime = "bear"

    broad_market_soft = spy_5d <= 0 or qqq_5d <= 0
    defensive_rotation = defensive_count >= 2 and not growth_leadership and broad_market_soft
    bear_confirmed = (
        spy_trend == "down"
        and qqq_trend == "down"
        and spy_5d < 0
        and qqq_5d < 0
        and vix_5d > 0
    )

    if bear_confirmed:
        mode = "risk_off"
        trade_permission = "short_bias"
        regime = "bear"
    elif defensive_rotation:
        mode = "defensive_rotation"
        trade_permission = "defensive_pause"
        regime = "defensive"

    futures = futures_bias_status()
    breadth = breadth_status(series=series, spy_5d=spy_5d, qqq_5d=qqq_5d)
    precious_metals = precious_metals_status(series=series, spy_5d=spy_5d, qqq_5d=qqq_5d, vix_5d=vix_5d, rates_5d=tnx_5d)

    # Futures, breadth, and precious metals are confirmation layers. They do not override the whole
    # regime by themselves, but they do inform risk score and downstream sizing.
    if futures.get("action") in ["block_opening_longs", "tech_caution"]:
        risk_score = int(max(0, risk_score - 5))
    elif futures.get("bias") == "bullish":
        risk_score = int(min(100, risk_score + 3))

    if breadth.get("action") in ["reduce_aggression", "tech_caution"]:
        risk_score = int(max(0, risk_score - 3))
    elif breadth.get("state") == "supportive":
        risk_score = int(min(100, risk_score + 2))

    if precious_metals.get("action") == "allow_defensive_metals" and broad_market_soft:
        risk_score = int(max(0, risk_score - 2))

    result = {
        "market_mode": mode,
        "risk_score": risk_score,
        "trade_permission": trade_permission,
        "regime": regime,
        "spy_trend": spy_trend,
        "qqq_trend": qqq_trend,
        "spy_5d_pct": round(spy_5d * 100, 2),
        "qqq_5d_pct": round(qqq_5d * 100, 2),
        "vix_5d_pct": round(vix_5d * 100, 2),
        "rates_5d_pct": round(tnx_5d * 100, 2),
        "sector_leaders": sector_leaders,
        "defensive_leadership": defensive_leadership,
        "growth_leadership": growth_leadership,
        "defensive_count": defensive_count,
        "risk_on_sector_count": risk_on_sector_count,
        "defensive_rotation": defensive_rotation,
        "broad_market_soft": broad_market_soft,
        "bear_confirmed": bear_confirmed,
        "futures_bias": futures,
        "breadth": breadth,
        "precious_metals": precious_metals
    }

    result["tech_leadership"] = tech_leadership_status(result)

    _market_cache["ts"] = now
    _market_cache["data"] = result
    return result


def risk_parameters(market):
    mode = market.get("market_mode", "neutral")

    if mode == "risk_on":
        return {
            "max_positions": 4,
            "long_alloc_pct": 0.15,
            "short_alloc_pct": 0.10,
            "long_scale_pct": 0.0,
            "short_scale_pct": 0.08,
            "allow_longs": True,
            "allow_shorts": False,
            "stop_loss": -0.012,
            "trail_long": 0.98,
            "trail_short": 1.02
        }

    if mode == "constructive":
        return {
            "max_positions": 4,
            "long_alloc_pct": 0.12,
            "short_alloc_pct": 0.08,
            "long_scale_pct": 0.0,
            "short_scale_pct": 0.06,
            "allow_longs": True,
            "allow_shorts": False,
            "stop_loss": -0.012,
            "trail_long": 0.982,
            "trail_short": 1.018
        }

    if mode == "neutral":
        return {
            "max_positions": 3,
            "long_alloc_pct": 0.08,
            "short_alloc_pct": 0.08,
            "long_scale_pct": 0.0,
            "short_scale_pct": 0.04,
            "allow_longs": True,
            "allow_shorts": False,
            "stop_loss": -0.010,
            "trail_long": 0.985,
            "trail_short": 1.015
        }

    if mode == "risk_off":
        return {
            "max_positions": 3,
            "long_alloc_pct": 0.05,
            "short_alloc_pct": 0.10,
            "long_scale_pct": 0.0,
            "short_scale_pct": 0.08,
            "allow_longs": False,
            "allow_shorts": bool(market.get("bear_confirmed", False)),
            "stop_loss": -0.010,
            "trail_long": 0.985,
            "trail_short": 1.020
        }

    return {
        "max_positions": 2,
        "long_alloc_pct": 0.04,
        "short_alloc_pct": 0.08,
        "long_scale_pct": 0.0,
        "short_scale_pct": 0.04,
        "allow_longs": False,
        "allow_shorts": mode == "crash_warning" and bool(market.get("bear_confirmed", False)),
        "stop_loss": -0.008,
        "trail_long": 0.987,
        "trail_short": 1.018
    }


# ============================================================
# SIGNALS
# ============================================================
def fetch_intraday(symbol):
    df = download_prices(symbol, period="5d", interval="5m")
    if df is None or getattr(df, "empty", True):
        return None
    return df


def intraday_arrays(df):
    return {
        "close": price_series(df, "Close"),
        "open": price_series(df, "Open"),
        "high": price_series(df, "High"),
        "low": price_series(df, "Low"),
        "volume": price_series(df, "Volume")
    }



def symbol_bucket(symbol):
    return SYMBOL_BUCKET.get(symbol, "default")


def bucket_config(symbol_or_bucket):
    bucket = symbol_or_bucket if symbol_or_bucket in BUCKET_CONFIG else symbol_bucket(symbol_or_bucket)
    cfg = dict(BUCKET_CONFIG.get(bucket, BUCKET_CONFIG["default"]))
    cfg["bucket"] = bucket
    return cfg


def bucket_alloc_factor(symbol):
    return float(bucket_config(symbol).get("alloc_factor", 1.0))


def portfolio_bucket_stats(exclude_symbol=None):
    equity = max(float(portfolio.get("equity", portfolio.get("cash", 0.0))), 0.01)
    bucket_values = {}
    bucket_counts = {}
    for symbol, pos in portfolio.get("positions", {}).items():
        if exclude_symbol and symbol == exclude_symbol:
            continue
        px = float(pos.get("last_price", pos.get("entry", 0.0)))
        value = position_value(pos, px)
        bucket = pos.get("bucket") or symbol_bucket(symbol)
        bucket_values[bucket] = bucket_values.get(bucket, 0.0) + value
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    return equity, bucket_values, bucket_counts


def catalyst_momentum_context(symbol, arrays, market):
    default = {"active": False, "score_bonus": 0.0, "reason": "not_active", "bucket": symbol_bucket(symbol)}
    if not CATALYST_MOMENTUM_ENABLED:
        default["reason"] = "catalyst_momentum_disabled"
        return default
    closes = arrays.get("close", np.array([]))
    opens = arrays.get("open", np.array([]))
    vols = arrays.get("volume", np.array([]))
    if len(closes) < 25 or len(opens) == 0:
        default["reason"] = "not_enough_intraday_data"
        return default
    session_bars = min(len(closes), 78)
    session_open = float(opens[-session_bars]) if len(opens) >= session_bars else float(opens[0])
    px = float(closes[-1])
    if session_open <= 0 or px <= 0:
        default["reason"] = "bad_price"
        return default
    intraday_move = (px / session_open) - 1.0
    volume_surge = 0.0
    if len(vols) >= 30:
        recent_vol = float(np.sum(vols[-6:]))
        base_slice = vols[-60:-6] if len(vols) >= 66 else vols[:-6]
        base_avg_6bar = float(np.mean(base_slice)) * 6 if len(base_slice) > 0 else 0.0
        volume_surge = recent_vol / base_avg_6bar if base_avg_6bar > 0 else 0.0
    bucket = symbol_bucket(symbol)
    catalyst_bucket = bucket in ["bitcoin_ai_compute", "data_center_infra", "small_cap_momentum", "semi_leaders", "precious_metals"]
    strong_move = intraday_move >= CATALYST_MIN_INTRADAY_MOVE_PCT
    volume_confirmed = volume_surge >= CATALYST_VOLUME_SURGE_RATIO
    medium_move_confirmed = intraday_move >= (CATALYST_MIN_INTRADAY_MOVE_PCT * 0.625) and volume_confirmed
    if catalyst_bucket and (strong_move or medium_move_confirmed):
        bonus = CATALYST_STRONG_SCORE_BONUS if strong_move and volume_confirmed else CATALYST_SCORE_BONUS
        return {
            "active": True,
            "bucket": bucket,
            "score_bonus": float(bonus),
            "intraday_move_pct": round(intraday_move * 100, 2),
            "volume_surge_ratio": round(volume_surge, 2),
            "reason": "catalyst_momentum_confirmed" if volume_confirmed else "large_move_catalyst_watch",
            "theme": "ai_data_center_compute" if bucket in ["bitcoin_ai_compute", "data_center_infra"] else bucket,
        }
    return {"active": False, "bucket": bucket, "score_bonus": 0.0, "intraday_move_pct": round(intraday_move * 100, 2), "volume_surge_ratio": round(volume_surge, 2), "reason": "no_catalyst_threshold"}


def apply_theme_confirmation(signals):
    if not THEME_CONFIRMATION_ENABLED or not signals:
        return signals
    counts = {}
    for sig in signals:
        bucket = sig.get("bucket") or symbol_bucket(sig.get("symbol"))
        if float(sig.get("score", 0.0) or 0.0) >= THEME_CONFIRMATION_MIN_SCORE:
            counts[bucket] = counts.get(bucket, 0) + 1
    confirmed = {bucket for bucket, count in counts.items() if count >= THEME_CONFIRMATION_MIN_SIGNALS}
    for sig in signals:
        bucket = sig.get("bucket") or symbol_bucket(sig.get("symbol"))
        if bucket in confirmed and bucket not in ["benchmark_etf", "default"]:
            sig["score"] = round(float(sig.get("score", 0.0)) + THEME_CONFIRMATION_SCORE_BONUS, 6)
            sig["theme_confirmation"] = {"active": True, "bucket": bucket, "bucket_signal_count": counts.get(bucket, 0), "score_bonus": THEME_CONFIRMATION_SCORE_BONUS}
    return signals


def signal_score(symbol, prices, market, side="long", benchmark_prices=None):
    if len(prices) < 35:
        return 0.0

    px = float(prices[-1])
    ma8 = sma(prices, 8)
    ma20 = sma(prices, 20)
    ma34 = sma(prices, 34)

    if ma8 is None or ma20 is None or ma34 is None or px <= 0:
        return 0.0

    r3 = pct_change(prices, 3)
    r6 = pct_change(prices, 6)
    r12 = pct_change(prices, 12)
    r24 = pct_change(prices, 24)

    sector = SYMBOL_SECTOR.get(symbol, "UNKNOWN")
    sector_bonus = 0.003 if sector in market.get("sector_leaders", []) else 0.0

    # Relative-strength overlay: prefer names that are beating QQQ/SPY rather than
    # merely drifting higher with the index.
    rs_adjustment = 0.0
    if benchmark_prices is not None and len(benchmark_prices) > 24:
        symbol_12 = pct_change(prices, 12)
        bench_12 = pct_change(benchmark_prices, 12)
        symbol_24 = pct_change(prices, 24)
        bench_24 = pct_change(benchmark_prices, 24)
        rs_edge = (0.60 * (symbol_12 - bench_12)) + (0.40 * (symbol_24 - bench_24))
        if side == "long":
            if rs_edge > 0.003:
                rs_adjustment += RELATIVE_STRENGTH_SCORE_BONUS
            elif rs_edge < -0.003:
                rs_adjustment -= RELATIVE_STRENGTH_SCORE_PENALTY
        else:
            if rs_edge < -0.003:
                rs_adjustment += RELATIVE_STRENGTH_SCORE_BONUS
            elif rs_edge > 0.003:
                rs_adjustment -= RELATIVE_STRENGTH_SCORE_PENALTY

    if side == "long":
        if not (px > ma20 and ma8 >= ma20 and ma20 >= ma34):
            return 0.0
        score = (0.35 * r3) + (0.30 * r6) + (0.25 * r12) + (0.10 * r24)
        if px > ma8:
            score += 0.001
        score += sector_bonus + rs_adjustment
        if symbol_bucket(symbol) == "precious_metals":
            metals = market.get("precious_metals", {}) or {}
            if metals.get("action") in ["allow_defensive_metals", "allow_metals_momentum"]:
                score += float(metals.get("score_bonus", 0.0) or 0.0)
        return max(0.0, float(score))

    if not (px < ma20 and ma8 <= ma20 and ma20 <= ma34):
        return 0.0

    score = (0.35 * -r3) + (0.30 * -r6) + (0.25 * -r12) + (0.10 * -r24)
    if px < ma8:
        score += 0.001
    if sector in market.get("sector_leaders", []):
        score -= 0.003
    score += rs_adjustment
    return max(0.0, float(score))


def entry_extension_check(symbol, side, arrays):
    closes = arrays.get("close", np.array([]))
    opens = arrays.get("open", np.array([]))
    highs = arrays.get("high", np.array([]))
    lows = arrays.get("low", np.array([]))

    if len(closes) < 20 or len(opens) == 0:
        return True, "ok"

    px = float(closes[-1])
    day_open = float(opens[-1])

    session_bars = min(len(closes), 78)
    session_high = float(np.max(highs[-session_bars:])) if len(highs) >= session_bars else float(np.max(closes[-session_bars:]))
    session_low = float(np.min(lows[-session_bars:])) if len(lows) >= session_bars else float(np.min(closes[-session_bars:]))
    ma20 = sma(closes, 20)

    if day_open <= 0 or px <= 0:
        return True, "ok"

    from_open = (px / day_open) - 1

    if side == "long":
        if from_open > EXTENSION_MAX_ABOVE_DAY_OPEN:
            return False, "extended_above_day_open"
        if from_open > EXTENSION_BIG_MOVE_CONFIRM and session_high > 0 and px >= session_high * EXTENSION_NEAR_HIGH_FACTOR:
            return False, "too_close_to_intraday_high_after_big_move"
        if ma20 and ma20 > 0 and (px / ma20 - 1) > EXTENSION_MAX_FROM_MA20:
            return False, "extended_above_5m_ma20"
        return True, "ok"

    if from_open < -EXTENSION_MAX_BELOW_DAY_OPEN:
        return False, "extended_below_day_open"
    if from_open < -EXTENSION_BIG_MOVE_CONFIRM and session_low > 0 and px <= session_low * EXTENSION_NEAR_LOW_FACTOR:
        return False, "too_close_to_intraday_low_after_big_move"
    if ma20 and ma20 > 0 and (ma20 / px - 1) > EXTENSION_MAX_FROM_MA20:
        return False, "extended_below_5m_ma20"

    return True, "ok"



def prune_pullback_watchlist():
    watch = portfolio.setdefault("pullback_watchlist", {})
    now = time.time()
    expired = [s for s, item in watch.items() if now - float(item.get("ts", 0)) > PULLBACK_WATCH_TTL_SECONDS]
    for s in expired:
        watch.pop(s, None)
    return watch


def register_pullback_candidate(symbol, side, score, reason, arrays):
    if not PULLBACK_RECLAIM_ENABLED or side != "long":
        return
    if reason not in ["extended_above_5m_ma20", "too_close_to_intraday_high_after_big_move", "extended_above_day_open"]:
        return
    closes = arrays.get("close", np.array([]))
    if len(closes) < 20:
        return
    portfolio.setdefault("pullback_watchlist", {})[symbol] = {
        "symbol": symbol,
        "side": side,
        "score": round(float(score), 6),
        "reason": reason,
        "ts": time.time(),
        "created_local": local_ts_text(),
        "last_price": round(float(closes[-1]), 4),
        "ma20": round(float(sma(closes, 20) or closes[-1]), 4)
    }


def pullback_reclaim_check(symbol, side, score, arrays):
    if not PULLBACK_RECLAIM_ENABLED or side != "long":
        return False, "pullback_reclaim_disabled"
    watch = prune_pullback_watchlist()
    item = watch.get(symbol)
    if not item:
        return False, "not_on_pullback_watchlist"
    closes = arrays.get("close", np.array([]))
    if len(closes) < 25:
        return False, "not_enough_bars_for_reclaim"
    px = float(closes[-1])
    ma8 = sma(closes, 8)
    ma20 = sma(closes, 20)
    if not ma8 or not ma20 or ma20 <= 0:
        return False, "missing_ma_for_reclaim"
    near_ma20 = px <= ma20 * (1 + PULLBACK_MAX_ABOVE_MA20)
    reclaimed_ma8 = px > ma8 and closes[-2] <= ma8
    trend_ok = ma8 >= ma20 * 0.997
    score_ok = float(score) >= max(MIN_ENTRY_SCORE_RISK_ON, float(item.get("score", 0)) * 0.70)
    if near_ma20 and (reclaimed_ma8 or trend_ok) and score_ok:
        watch.pop(symbol, None)
        return True, "pullback_reclaim_after_extension"
    return False, "waiting_for_pullback_reclaim"


def scan_signals(market):
    long_signals = []
    short_signals = []
    rejected = []
    prune_pullback_watchlist()

    benchmark_prices = np.array([])
    try:
        qqq_df = fetch_intraday("QQQ")
        benchmark_prices = price_series(qqq_df, "Close")
    except Exception:
        benchmark_prices = np.array([])

    for symbol in UNIVERSE:
        if is_in_cooldown(symbol):
            rejected.append({"symbol": symbol, "reason": "cooldown"})
            continue

        df = fetch_intraday(symbol)
        if df is None:
            rejected.append({"symbol": symbol, "reason": "no_data"})
            continue

        arrays = intraday_arrays(df)
        closes = arrays["close"]
        if len(closes) < 35:
            rejected.append({"symbol": symbol, "reason": "not_enough_bars"})
            continue

        px = float(closes[-1])
        catalyst = catalyst_momentum_context(symbol, arrays, market)
        long_score = signal_score(symbol, closes, market, "long", benchmark_prices=benchmark_prices)
        short_score = signal_score(symbol, closes, market, "short", benchmark_prices=benchmark_prices)
        if catalyst.get("active") and long_score > 0:
            long_score += float(catalyst.get("score_bonus", 0.0))

        bucket = symbol_bucket(symbol)
        sector = SYMBOL_SECTOR.get(symbol, "UNKNOWN")

        if long_score > 0:
            ok, reason = entry_extension_check(symbol, "long", arrays)
            if ok:
                long_signals.append({
                    "symbol": symbol, "side": "long", "score": round(float(long_score), 6),
                    "price": px, "sector": sector, "bucket": bucket, "catalyst": catalyst
                })
            else:
                register_pullback_candidate(symbol, "long", long_score, reason, arrays)
                reclaim_ok, reclaim_reason = pullback_reclaim_check(symbol, "long", long_score, arrays)
                if reclaim_ok:
                    long_signals.append({
                        "symbol": symbol, "side": "long", "score": round(float(long_score) + PULLBACK_RECLAIM_SCORE_BONUS, 6),
                        "price": px, "sector": sector, "bucket": bucket, "entry_context": reclaim_reason, "catalyst": catalyst
                    })
                else:
                    rejected.append({"symbol": symbol, "side": "long", "score": round(float(long_score), 6), "reason": reason, "bucket": bucket, "catalyst": catalyst, "pullback_reclaim_status": reclaim_reason})

        if short_score > 0:
            ok, reason = entry_extension_check(symbol, "short", arrays)
            if ok:
                short_signals.append({
                    "symbol": symbol, "side": "short", "score": round(float(short_score), 6),
                    "price": px, "sector": sector, "bucket": bucket
                })
            else:
                rejected.append({"symbol": symbol, "side": "short", "score": round(float(short_score), 6), "reason": reason, "bucket": bucket})

    long_signals = apply_theme_confirmation(long_signals)
    long_signals = sorted(long_signals, key=lambda x: x["score"], reverse=True)
    short_signals = sorted(short_signals, key=lambda x: x["score"], reverse=True)
    return long_signals, short_signals, rejected


def tech_leadership_status(market):
    """Return adaptive tech/growth leadership permissions for XLK/XLY-style markets."""
    market = market or {}
    futures = market.get("futures_bias", {}) or {}
    breadth = market.get("breadth", {}) or {}
    sector_leaders = market.get("sector_leaders", []) or []

    qqq_5d = safe_float(market.get("qqq_5d_pct"))
    spy_5d = safe_float(market.get("spy_5d_pct"))
    risk_score = int(safe_float(market.get("risk_score")))
    qqq_trend = market.get("qqq_trend")
    spy_trend = market.get("spy_trend")
    mode = market.get("market_mode")

    tech_sector_leading = any(s in sector_leaders for s in TECH_LEADERSHIP_SECTORS)
    qqq_outperforming = qqq_5d > spy_5d
    strong_index_context = (
        mode in ["risk_on", "constructive"]
        and risk_score >= TECH_LEADERSHIP_MIN_RISK_SCORE
        and qqq_trend == "up"
        and spy_trend in ["up", "flat", "unknown"]
        and qqq_5d > 0
        and qqq_outperforming
    )

    futures_breakdown = futures.get("action") in ["block_opening_longs"] or futures.get("bias") in ["bearish", "mixed_bearish"]
    active = bool(TECH_LEADERSHIP_MODE_ENABLED and strong_index_context and tech_sector_leading and not futures_breakdown)

    caution_reasons = []
    if safe_float(market.get("vix_5d_pct")) > 0:
        caution_reasons.append("vix_rising")
    if futures.get("action") in ["gap_chase_protection", "reduce_aggression", "tech_caution"]:
        caution_reasons.append(f"futures_{futures.get('action')}")
    if breadth.get("action") in ["tech_caution", "reduce_aggression"]:
        caution_reasons.append(f"breadth_{breadth.get('state')}")

    if not active:
        cap = MAX_SECTOR_EXPOSURE_PCT
        max_pos = MAX_POSITIONS_PER_SECTOR
        state = "inactive"
        reason = "tech leadership not confirmed"
    elif caution_reasons:
        cap = max(MAX_SECTOR_EXPOSURE_PCT, TECH_LEADERSHIP_CAUTION_EXPOSURE_PCT)
        max_pos = max(MAX_POSITIONS_PER_SECTOR, TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR)
        state = "active_cautious"
        reason = ",".join(caution_reasons)
    else:
        cap = max(MAX_SECTOR_EXPOSURE_PCT, TECH_LEADERSHIP_MAX_EXPOSURE_PCT)
        max_pos = max(MAX_POSITIONS_PER_SECTOR, TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR)
        state = "active_confirmed"
        reason = "qqq_outperforming_with_tech_sector_leadership"

    return {
        "enabled": bool(TECH_LEADERSHIP_MODE_ENABLED),
        "active": bool(active),
        "state": state,
        "reason": reason,
        "sectors": TECH_LEADERSHIP_SECTORS,
        "risk_score": risk_score,
        "qqq_5d_pct": round(qqq_5d, 2),
        "spy_5d_pct": round(spy_5d, 2),
        "qqq_outperforming_spy": bool(qqq_outperforming),
        "sector_leaders": sector_leaders,
        "tech_sector_leading": bool(tech_sector_leading),
        "max_tech_sector_exposure_pct": round(cap * 100, 2),
        "max_tech_positions_per_sector": int(max_pos),
        "score_relief": TECH_LEADERSHIP_SCORE_RELIEF if active else 0.0,
        "caution_reasons": caution_reasons
    }


def effective_sector_exposure_cap(market, sector):
    tech = tech_leadership_status(market)
    if sector in TECH_LEADERSHIP_SECTORS and tech.get("active"):
        return (TECH_LEADERSHIP_CAUTION_EXPOSURE_PCT if tech.get("state") == "active_cautious" else TECH_LEADERSHIP_MAX_EXPOSURE_PCT)
    return MAX_SECTOR_EXPOSURE_PCT


def effective_max_positions_per_sector(market, sector):
    tech = tech_leadership_status(market)
    if sector in TECH_LEADERSHIP_SECTORS and tech.get("active"):
        return max(MAX_POSITIONS_PER_SECTOR, TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR)
    return MAX_POSITIONS_PER_SECTOR


def tech_leadership_entry_context(market, sector):
    tech = tech_leadership_status(market)
    return bool(sector in TECH_LEADERSHIP_SECTORS and tech.get("active")), tech


def min_entry_score_for_market(market, side="long"):
    mode = market.get("market_mode", "neutral")

    if side == "short":
        base = MIN_SHORT_ENTRY_SCORE
    elif mode == "risk_on":
        base = MIN_ENTRY_SCORE_RISK_ON
    elif mode == "constructive":
        base = MIN_ENTRY_SCORE_CONSTRUCTIVE
    elif mode == "neutral":
        base = MIN_ENTRY_SCORE_NEUTRAL
    else:
        base = MIN_ENTRY_SCORE_DEFENSIVE

    if side == "short":
        return round(float(base), 6)

    # Dynamic quality tightening: after losses or when VIX/rates are rising,
    # the bot requires stronger signals instead of continuing to hunt.
    rp = get_realized_pnl()
    losses_today = int(rp.get("losses_today", 0))
    adjusted = float(base) + min(losses_today, 1) * ENTRY_SCORE_LOSS_STEP

    # Stop-loss specific bump: after one stop-out, require materially stronger
    # signals; after two, the feedback loop blocks entries entirely.
    try:
        stop_losses_today = sum(
            1 for t in trades_for_date(today_key())
            if t.get("action") == "exit" and t.get("exit_reason") == "stop_loss"
        )
        if stop_losses_today >= 1:
            adjusted += POST_STOP_SCORE_BUMP
    except Exception:
        pass

    if float(market.get("vix_5d_pct", 0.0) or 0.0) > 0:
        adjusted += VIX_RISING_SCORE_BUMP
    if float(market.get("rates_5d_pct", 0.0) or 0.0) > 1.0:
        adjusted += RATES_RISING_SCORE_BUMP

    futures = market.get("futures_bias", {}) or {}
    if futures.get("action") in ["reduce_aggression", "tech_caution", "gap_chase_protection"]:
        adjusted += FUTURES_SCORE_BUMP_CAUTION
    elif futures.get("action") == "block_opening_longs":
        adjusted += FUTURES_SCORE_BUMP_BEARISH

    breadth = market.get("breadth", {}) or {}
    tech = tech_leadership_status(market)
    if breadth.get("action") in ["reduce_aggression", "tech_caution"]:
        if tech.get("active"):
            adjusted += TECH_LEADERSHIP_BREADTH_SCORE_BUMP
        else:
            adjusted += BREADTH_SCORE_BUMP_NARROW

    if tech.get("active"):
        adjusted -= TECH_LEADERSHIP_SCORE_RELIEF
        adjusted = max(float(base), adjusted)

    return round(float(adjusted), 6)


def apply_aggression_adjustments(params, market):
    """Reduce allocation when surface regime is risk-on but internals are less supportive."""
    adjusted = dict(params or {})
    vix_rising = float(market.get("vix_5d_pct", 0.0) or 0.0) > 0
    rates_rising = float(market.get("rates_5d_pct", 0.0) or 0.0) > 1.0

    reduction_reasons = []
    factor = 1.0

    if vix_rising:
        factor *= VIX_RISING_ALLOC_REDUCTION
        reduction_reasons.append("vix_rising")
    if rates_rising:
        factor *= 0.85
        reduction_reasons.append("rates_rising")

    futures = market.get("futures_bias", {}) or {}
    if futures.get("action") in ["reduce_aggression", "tech_caution", "gap_chase_protection"]:
        factor *= FUTURES_ALLOC_REDUCTION_CAUTION
        reduction_reasons.append(f"futures_{futures.get('action')}")
    elif futures.get("action") == "block_opening_longs":
        factor *= FUTURES_ALLOC_REDUCTION_BEARISH
        reduction_reasons.append("futures_bearish")

    breadth = market.get("breadth", {}) or {}
    tech = tech_leadership_status(market)
    if breadth.get("action") in ["reduce_aggression", "tech_caution"]:
        if tech.get("active"):
            factor *= TECH_LEADERSHIP_BREADTH_ALLOC_REDUCTION
            reduction_reasons.append(f"adaptive_tech_{breadth.get('state')}")
        else:
            factor *= BREADTH_ALLOC_REDUCTION_NARROW
            reduction_reasons.append(f"breadth_{breadth.get('state')}")

    if tech.get("active"):
        adjusted["tech_leadership_mode"] = tech

    if reduction_reasons:
        adjusted["long_alloc_pct"] = round(float(adjusted.get("long_alloc_pct", 0.0)) * factor, 4)
        adjusted["aggression_reduced"] = True
        adjusted["aggression_reduction_reason"] = ",".join(reduction_reasons)
        adjusted["aggression_reduction_factor"] = round(float(factor), 4)
    else:
        adjusted["aggression_reduced"] = False
        adjusted["aggression_reduction_reason"] = ""
        adjusted["aggression_reduction_factor"] = 1.0

    return adjusted


def portfolio_sector_stats(exclude_symbol=None):
    equity = max(float(portfolio.get("equity", portfolio.get("cash", 0.0))), 0.01)
    sector_values = {}
    sector_counts = {}

    for symbol, pos in portfolio.get("positions", {}).items():
        if exclude_symbol and symbol == exclude_symbol:
            continue

        px = float(pos.get("last_price", pos.get("entry", 0.0)))
        value = position_value(pos, px)
        sector = pos.get("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN"))
        sector_values[sector] = sector_values.get(sector, 0.0) + value
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    return equity, sector_values, sector_counts


def estimated_trade_allocation(signal, params):
    side = signal.get("side", "long")
    symbol = signal.get("symbol", "")
    alloc_pct = float(params.get("short_alloc_pct" if side == "short" else "long_alloc_pct", 0.0))
    equity = max(float(portfolio.get("equity", portfolio.get("cash", 0.0))), 0.01)
    cash = max(float(portfolio.get("cash", 0.0)), 0.0)
    alloc_factor = float(signal.get("alloc_factor", 1.0) or 1.0)
    bucket_factor = bucket_alloc_factor(symbol) if side == "long" else 0.75
    return min(cash, equity * alloc_pct * alloc_factor * bucket_factor)




def controlled_pullback_window_status(clock=None):
    """Return whether a controlled pullback starter is allowed by time-of-day."""
    clock = clock or market_clock()
    current = now_local()
    open_dt = regular_open_datetime(current)
    close_dt = current.replace(
        hour=REGULAR_CLOSE_HOUR,
        minute=REGULAR_CLOSE_MINUTE,
        second=0,
        microsecond=0
    )

    minutes_since_open = max(0.0, (current - open_dt).total_seconds() / 60.0)
    minutes_to_close = max(0.0, (close_dt - current).total_seconds() / 60.0)

    active = (
        bool(clock.get("is_open", False))
        and minutes_since_open >= CONTROLLED_PULLBACK_MINUTES_AFTER_OPEN
        and minutes_to_close > CONTROLLED_PULLBACK_NO_ENTRY_LAST_MINUTES
    )

    if not bool(clock.get("is_open", False)):
        reason = "market_not_open"
    elif minutes_since_open < CONTROLLED_PULLBACK_MINUTES_AFTER_OPEN:
        reason = "waiting_after_open"
    elif minutes_to_close <= CONTROLLED_PULLBACK_NO_ENTRY_LAST_MINUTES:
        reason = "too_close_to_close"
    else:
        reason = "ok"

    return {
        "active": bool(active),
        "reason": reason,
        "minutes_since_open": round(minutes_since_open, 1),
        "required_minutes_after_open": CONTROLLED_PULLBACK_MINUTES_AFTER_OPEN,
        "minutes_to_close": round(minutes_to_close, 1),
        "no_entry_last_minutes": CONTROLLED_PULLBACK_NO_ENTRY_LAST_MINUTES
    }


def controlled_pullback_entries_today():
    try:
        return sum(
            1 for t in trades_for_date(today_key())
            if t.get("action") == "entry"
            and str(t.get("entry_context", "")).startswith("controlled_pullback")
        )
    except Exception:
        return 0


def controlled_pullback_context_active(market):
    futures = market.get("futures_bias", {}) or {}
    breadth = market.get("breadth", {}) or {}
    return (
        futures.get("action") in ["gap_chase_protection", "reduce_aggression", "tech_caution"]
        or breadth.get("action") in ["tech_caution", "reduce_aggression"]
    )


def controlled_pullback_entry_check(signal, params, market, dynamic_min_score, exclude_symbol=None):
    """Conservative starter override for valid long signals on extended trend days.

    This does not override halts, self-defense, late-day cutoff, sector caps, or cooldowns.
    It only lets one small starter through when the regular dynamic score floor is high
    because futures/breadth/VIX are cautionary, but the candidate still has acceptable
    momentum, sector alignment, and enough time left in the session.
    """
    symbol = signal.get("symbol")
    side = signal.get("side", "long")
    sector = signal.get("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN"))
    score = float(signal.get("score", 0.0) or 0.0)
    clock = market_clock()
    window = controlled_pullback_window_status(clock)
    rc = get_risk_controls()
    feedback = portfolio.get("feedback_loop") or default_feedback_loop()

    if not CONTROLLED_PULLBACK_ENTRY_ENABLED:
        return False, {"reason": "controlled_pullback_disabled"}
    if side != "long":
        return False, {"reason": "controlled_pullback_long_only"}
    if not window.get("active", False):
        return False, {"reason": "controlled_pullback_time_filter", "window": window}
    if bool(rc.get("halted", False)) or bool(rc.get("profit_guard_active", False)):
        return False, {"reason": "risk_or_profit_guard_active"}
    if bool(feedback.get("block_new_entries", False)) or bool(feedback.get("hard_halt", False)):
        return False, {"reason": "feedback_loop_blocks_entries"}
    if bool(feedback.get("late_day_entry_cutoff", False)):
        return False, {"reason": "late_day_entry_cutoff"}
    if CONTROLLED_PULLBACK_REQUIRE_CAUTION_CONTEXT and not controlled_pullback_context_active(market):
        return False, {"reason": "controlled_pullback_context_not_active"}
    if CONTROLLED_PULLBACK_ALLOW_EMPTY_BOOK_ONLY and len(portfolio.get("positions", {}) or {}) > 0:
        return False, {"reason": "controlled_pullback_empty_book_only"}
    if controlled_pullback_entries_today() >= CONTROLLED_PULLBACK_MAX_ENTRIES_PER_DAY:
        return False, {
            "reason": "controlled_pullback_daily_limit",
            "max_entries_per_day": CONTROLLED_PULLBACK_MAX_ENTRIES_PER_DAY
        }

    try:
        stop_losses_today = sum(
            1 for t in trades_for_date(today_key())
            if t.get("action") == "exit" and t.get("exit_reason") == "stop_loss"
        )
    except Exception:
        stop_losses_today = 0
    if stop_losses_today > 0:
        return False, {"reason": "controlled_pullback_no_after_stop_loss", "stop_losses_today": stop_losses_today}

    sector_aligned = sector in market.get("sector_leaders", [])
    if CONTROLLED_PULLBACK_REQUIRE_SECTOR_LEADER and not sector_aligned and score < POST_STOP_EXCEPTIONAL_SCORE:
        return False, {
            "reason": "controlled_pullback_sector_alignment_required",
            "sector": sector,
            "sector_leaders": market.get("sector_leaders", []),
            "score": round(score, 6),
            "required_exceptional_score": POST_STOP_EXCEPTIONAL_SCORE
        }

    base_floor = max(CONTROLLED_PULLBACK_MIN_SCORE, MIN_ENTRY_SCORE_RISK_ON)
    # Do not let very weak names bypass the dynamic filter. The starter may only
    # use a modest discount from the active floor, and still must beat the base floor.
    discounted_dynamic_floor = max(base_floor, float(dynamic_min_score) - CONTROLLED_PULLBACK_SCORE_DISCOUNT)
    required_score = min(float(dynamic_min_score), discounted_dynamic_floor)
    required_score = max(base_floor, required_score)

    if score < required_score:
        return False, {
            "reason": "controlled_pullback_score_below_required",
            "symbol": symbol,
            "score": round(score, 6),
            "required_score": round(required_score, 6),
            "dynamic_required_score": round(float(dynamic_min_score), 6),
            "base_floor": round(base_floor, 6)
        }

    equity, sector_values, sector_counts = portfolio_sector_stats(exclude_symbol=exclude_symbol)
    sector_count = int(sector_counts.get(sector, 0))
    max_sector_positions = effective_max_positions_per_sector(market, sector)
    if sector not in [None, "", "UNKNOWN"] and sector_count >= max_sector_positions:
        return False, {
            "reason": "controlled_pullback_sector_position_limit",
            "sector": sector,
            "current_sector_positions": sector_count,
            "max_positions_per_sector": max_sector_positions,
            "tech_leadership": tech_leadership_status(market)
        }

    proposed_alloc = estimated_trade_allocation(signal, params) * CONTROLLED_PULLBACK_ALLOC_FACTOR
    projected_sector_value = float(sector_values.get(sector, 0.0)) + proposed_alloc
    projected_sector_pct = projected_sector_value / equity if equity > 0 else 0.0
    sector_cap = effective_sector_exposure_cap(market, sector)
    if sector not in [None, "", "UNKNOWN"] and projected_sector_pct > sector_cap:
        return False, {
            "reason": "controlled_pullback_sector_exposure_cap",
            "sector": sector,
            "projected_sector_pct": round(projected_sector_pct * 100, 2),
            "max_sector_exposure_pct": round(sector_cap * 100, 2),
            "tech_leadership": tech_leadership_status(market)
        }

    bucket = signal.get("bucket") or symbol_bucket(symbol)
    cfg = bucket_config(bucket)
    _, bucket_values, bucket_counts = portfolio_bucket_stats(exclude_symbol=exclude_symbol)
    bucket_count = int(bucket_counts.get(bucket, 0))
    projected_bucket_value = float(bucket_values.get(bucket, 0.0)) + proposed_alloc
    projected_bucket_pct = projected_bucket_value / equity if equity > 0 else 0.0
    if bucket_count >= int(cfg.get("max_positions", 99)):
        return False, {"reason": "controlled_pullback_bucket_position_limit", "bucket": bucket, "current_bucket_positions": bucket_count, "max_bucket_positions": int(cfg.get("max_positions", 99))}
    if projected_bucket_pct > float(cfg.get("max_exposure_pct", 1.0)):
        return False, {"reason": "controlled_pullback_bucket_exposure_cap", "bucket": bucket, "projected_bucket_pct": round(projected_bucket_pct * 100, 2), "max_bucket_exposure_pct": round(float(cfg.get("max_exposure_pct", 1.0)) * 100, 2)}

    return True, {
        "reason": "controlled_pullback_entry_ok",
        "symbol": symbol,
        "score": round(score, 6),
        "required_score": round(required_score, 6),
        "dynamic_required_score": round(float(dynamic_min_score), 6),
        "alloc_factor": CONTROLLED_PULLBACK_ALLOC_FACTOR,
        "bucket": bucket,
        "bucket_alloc_factor": bucket_alloc_factor(symbol),
        "sector": sector,
        "sector_aligned": sector_aligned,
        "window": window,
        "futures_bias": market.get("futures_bias", {}),
        "breadth": market.get("breadth", {})
    }

def entry_quality_check(signal, params, market, exclude_symbol=None):
    """Validate signal quality before opening a new position or rotating into one."""
    symbol = signal.get("symbol")
    side = signal.get("side", "long")
    sector = signal.get("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN"))
    score = float(signal.get("score", 0.0))
    min_score = float(min_entry_score_for_market(market, side))

    if score < min_score:
        controlled_ok, controlled_info = controlled_pullback_entry_check(
            signal, params, market, min_score, exclude_symbol=exclude_symbol
        )
        if controlled_ok:
            signal["entry_context"] = "controlled_pullback_starter"
            signal["alloc_factor"] = CONTROLLED_PULLBACK_ALLOC_FACTOR
            return True, controlled_info

        return False, {
            "reason": "entry_score_below_minimum",
            "symbol": symbol,
            "score": round(score, 6),
            "required_score": round(min_score, 6),
            "market_mode": market.get("market_mode"),
            "controlled_pullback_info": controlled_info
        }

    try:
        stop_losses_today = sum(
            1 for t in trades_for_date(today_key())
            if t.get("action") == "exit" and t.get("exit_reason") == "stop_loss"
        )
    except Exception:
        stop_losses_today = 0

    if (
        side == "long"
        and POST_STOP_REQUIRE_SECTOR_LEADER
        and stop_losses_today >= 1
        and sector not in market.get("sector_leaders", [])
        and score < POST_STOP_EXCEPTIONAL_SCORE
    ):
        return False, {
            "reason": "post_stop_sector_alignment_required",
            "symbol": symbol,
            "sector": sector,
            "score": round(score, 6),
            "required_exceptional_score": POST_STOP_EXCEPTIONAL_SCORE,
            "sector_leaders": market.get("sector_leaders", []),
            "stop_losses_today": stop_losses_today
        }

    futures = market.get("futures_bias", {}) or {}
    if side == "long" and futures.get("action") == "block_opening_longs":
        return False, {
            "reason": "futures_bias_block_opening_longs",
            "symbol": symbol,
            "score": round(score, 6),
            "futures_bias": futures
        }

    if side == "long" and futures.get("action") == "tech_caution" and sector == "XLK" and score < POST_STOP_EXCEPTIONAL_SCORE:
        return False, {
            "reason": "futures_tech_caution_requires_exceptional_score",
            "symbol": symbol,
            "sector": sector,
            "score": round(score, 6),
            "required_exceptional_score": POST_STOP_EXCEPTIONAL_SCORE,
            "futures_bias": futures
        }

    equity, sector_values, sector_counts = portfolio_sector_stats(exclude_symbol=exclude_symbol)
    sector_count = int(sector_counts.get(sector, 0))

    max_sector_positions = effective_max_positions_per_sector(market, sector)
    if sector not in [None, "", "UNKNOWN"] and sector_count >= max_sector_positions:
        return False, {
            "reason": "sector_position_limit",
            "symbol": symbol,
            "sector": sector,
            "current_sector_positions": sector_count,
            "max_positions_per_sector": max_sector_positions,
            "tech_leadership": tech_leadership_status(market)
        }

    proposed_alloc = estimated_trade_allocation(signal, params)
    projected_sector_value = float(sector_values.get(sector, 0.0)) + proposed_alloc
    projected_sector_pct = projected_sector_value / equity if equity > 0 else 0.0

    sector_cap = effective_sector_exposure_cap(market, sector)
    if sector not in [None, "", "UNKNOWN"] and projected_sector_pct > sector_cap:
        return False, {
            "reason": "sector_exposure_cap",
            "symbol": symbol,
            "sector": sector,
            "projected_sector_pct": round(projected_sector_pct * 100, 2),
            "max_sector_exposure_pct": round(sector_cap * 100, 2),
            "tech_leadership": tech_leadership_status(market)
        }

    bucket = signal.get("bucket") or symbol_bucket(symbol)
    cfg = bucket_config(bucket)
    bucket_equity, bucket_values, bucket_counts = portfolio_bucket_stats(exclude_symbol=exclude_symbol)
    bucket_count = int(bucket_counts.get(bucket, 0))
    if bucket_count >= int(cfg.get("max_positions", 99)):
        return False, {
            "reason": "bucket_position_limit",
            "symbol": symbol,
            "bucket": bucket,
            "current_bucket_positions": bucket_count,
            "max_bucket_positions": int(cfg.get("max_positions", 99))
        }
    projected_bucket_value = float(bucket_values.get(bucket, 0.0)) + proposed_alloc
    projected_bucket_pct = projected_bucket_value / bucket_equity if bucket_equity > 0 else 0.0
    if projected_bucket_pct > float(cfg.get("max_exposure_pct", 1.0)):
        return False, {
            "reason": "bucket_exposure_cap",
            "symbol": symbol,
            "bucket": bucket,
            "projected_bucket_pct": round(projected_bucket_pct * 100, 2),
            "max_bucket_exposure_pct": round(float(cfg.get("max_exposure_pct", 1.0)) * 100, 2)
        }

    return True, {
        "reason": "entry_quality_ok",
        "symbol": symbol,
        "score": round(score, 6),
        "required_score": round(min_score, 6),
        "sector": sector,
        "bucket": bucket,
        "bucket_alloc_factor": bucket_alloc_factor(symbol),
        "projected_sector_pct": round(projected_sector_pct * 100, 2),
        "max_sector_exposure_pct": round(effective_sector_exposure_cap(market, sector) * 100, 2),
        "projected_bucket_pct": round(projected_bucket_pct * 100, 2),
        "max_bucket_exposure_pct": round(float(cfg.get("max_exposure_pct", 1.0)) * 100, 2),
        "sector_positions_after_entry": sector_count + 1,
        "bucket_positions_after_entry": bucket_count + 1,
        "max_positions_per_sector": effective_max_positions_per_sector(market, sector),
        "max_positions_per_bucket": int(cfg.get("max_positions", 99)),
        "tech_leadership": tech_leadership_status(market)
    }


def entry_controls_snapshot(clock=None, market=None, params=None, risk_controls=None):
    clock = clock or market_clock()
    market = market or (portfolio.get("last_market") or market_status(force=False))
    params = params or apply_aggression_adjustments(risk_parameters(market), market)
    risk_controls = risk_controls or get_risk_controls()
    warmup = opening_warmup_status(clock)
    equity, sector_values, sector_counts = portfolio_sector_stats()

    return {
        "opening_warmup": warmup,
        "max_new_entries_per_cycle": MAX_NEW_ENTRIES_PER_CYCLE,
        "min_entry_score": {
            "risk_on": MIN_ENTRY_SCORE_RISK_ON,
            "constructive": MIN_ENTRY_SCORE_CONSTRUCTIVE,
            "neutral": MIN_ENTRY_SCORE_NEUTRAL,
            "defensive": MIN_ENTRY_SCORE_DEFENSIVE,
            "short": MIN_SHORT_ENTRY_SCORE,
            "active_long_floor": min_entry_score_for_market(market, "long"),
            "active_short_floor": min_entry_score_for_market(market, "short")
        },
        "futures_bias": market.get("futures_bias", {}),
        "breadth": market.get("breadth", {}),
        "precious_metals": market.get("precious_metals", {}),
        "winner_protection": {
            "partial_profit_enabled": PARTIAL_PROFIT_ENABLED,
            "partial_profit_trigger_pct": round(PARTIAL_PROFIT_TRIGGER_PCT * 100, 2),
            "partial_profit_fraction_pct": round(PARTIAL_PROFIT_FRACTION * 100, 2),
            "trail_activation_profit_pct": round(TRAIL_ACTIVATION_PROFIT_PCT * 100, 2),
            "profit_lock_level_1_pct": round(PROFIT_LOCK_LEVEL_1_PCT * 100, 2),
            "profit_lock_level_2_pct": round(PROFIT_LOCK_LEVEL_2_PCT * 100, 2),
            "profit_lock_level_3_pct": round(PROFIT_LOCK_LEVEL_3_PCT * 100, 2)
        },
        "pullback_watchlist_count": len(portfolio.get("pullback_watchlist", {}) or {}),
        "controlled_pullback": {
            "enabled": CONTROLLED_PULLBACK_ENTRY_ENABLED,
            "window": controlled_pullback_window_status(clock),
            "min_score": CONTROLLED_PULLBACK_MIN_SCORE,
            "max_entries_per_day": CONTROLLED_PULLBACK_MAX_ENTRIES_PER_DAY,
            "entries_today": controlled_pullback_entries_today(),
            "alloc_factor": CONTROLLED_PULLBACK_ALLOC_FACTOR,
            "require_caution_context": CONTROLLED_PULLBACK_REQUIRE_CAUTION_CONTEXT,
            "require_sector_leader": CONTROLLED_PULLBACK_REQUIRE_SECTOR_LEADER,
            "empty_book_only": CONTROLLED_PULLBACK_ALLOW_EMPTY_BOOK_ONLY
        },
        "sector_controls": {
            "max_sector_exposure_pct": round(MAX_SECTOR_EXPOSURE_PCT * 100, 2),
            "max_positions_per_sector": MAX_POSITIONS_PER_SECTOR,
            "adaptive_tech_leadership": tech_leadership_status(market),
            "effective_sector_caps_pct": {
                sector: round(effective_sector_exposure_cap(market, sector) * 100, 2)
                for sector in sorted(set(list(sector_values.keys()) + TECH_LEADERSHIP_SECTORS))
            },
            "effective_sector_position_limits": {
                sector: effective_max_positions_per_sector(market, sector)
                for sector in sorted(set(list(sector_counts.keys()) + TECH_LEADERSHIP_SECTORS))
            },
            "current_sector_exposure_pct": {
                k: round((v / max(equity, 0.01)) * 100, 2)
                for k, v in sorted(sector_values.items(), key=lambda x: x[1], reverse=True)
            },
            "current_sector_position_counts": dict(sorted(sector_counts.items(), key=lambda x: x[1], reverse=True))
        },
        "risk_halted": bool(risk_controls.get("halted", False)),
        "profit_guard_active": bool(risk_controls.get("profit_guard_active", False)),
        "feedback_loop": feedback_loop_status(market=market, params=params, risk_controls=risk_controls, clock=clock, persist=False),
        "long_alloc_pct": params.get("long_alloc_pct"),
        "short_alloc_pct": params.get("short_alloc_pct")
    }


# ============================================================
# PORTFOLIO OPERATIONS
# ============================================================
def calculate_equity(refresh_prices=True):
    equity = float(portfolio.get("cash", 0.0))

    for symbol, pos in list(portfolio.get("positions", {}).items()):
        px = None
        if refresh_prices:
            px = latest_price(symbol)
        if px is None:
            px = float(pos.get("last_price", pos.get("entry", 0)))

        pos["last_price"] = float(px)

        if pos.get("side", "long") == "short":
            pos["trough"] = min(float(pos.get("trough", px)), float(px))
        else:
            pos["peak"] = max(float(pos.get("peak", px)), float(px))

        equity += position_value(pos, px)

    portfolio["equity"] = round(float(equity), 2)
    portfolio["peak"] = max(float(portfolio.get("peak", equity)), equity)
    portfolio.setdefault("history", []).append(round(float(equity), 2))
    portfolio["history"] = portfolio["history"][-500:]
    update_daily_risk_controls(equity)
    performance_snapshot()
    return equity


def exit_position(symbol, px, reason, market_mode=None, extra=None):
    pos = portfolio.get("positions", {}).get(symbol)
    if not pos:
        return None

    side = pos.get("side", "long")
    shares = float(pos.get("shares", 0))
    entry = float(pos.get("entry", 0))
    pnl = position_pnl_dollars(pos, px)
    pnl_pct = position_pnl_pct(pos, px)

    if side == "short":
        margin = float(pos.get("margin", entry * shares))
        portfolio["cash"] = float(portfolio.get("cash", 0.0)) + margin + pnl
    else:
        portfolio["cash"] = float(portfolio.get("cash", 0.0)) + shares * float(px)

    del portfolio["positions"][symbol]
    add_realized_pnl(pnl)
    set_cooldown(symbol)

    details = {
        "exit_reason": reason,
        "pnl_dollars": round(float(pnl), 2),
        "pnl_pct": round(float(pnl_pct) * 100, 2),
        "cooldown_seconds": COOLDOWN_SECONDS,
        "market_mode": market_mode
    }
    if extra:
        details.update(extra)

    record_trade("exit", symbol, side, px, shares, details)

    return {
        "symbol": symbol,
        "side": side,
        "price": round(float(px), 4),
        "shares": round(shares, 6),
        "pnl_dollars": round(float(pnl), 2),
        "pnl_pct": round(float(pnl_pct) * 100, 2),
        "reason": reason
    }



def reduce_position(symbol, px, fraction, reason, market_mode=None, extra=None):
    """Take partial profit while leaving the remaining position open."""
    pos = portfolio.get("positions", {}).get(symbol)
    if not pos:
        return None

    fraction = max(0.0, min(float(fraction), 0.95))
    shares_total = float(pos.get("shares", 0.0))
    shares_to_close = shares_total * fraction
    if shares_to_close <= 0:
        return None

    side = pos.get("side", "long")
    entry = float(pos.get("entry", 0.0))
    realized_pnl = (float(px) - entry) * shares_to_close
    if side == "short":
        realized_pnl = (entry - float(px)) * shares_to_close
        margin_total = float(pos.get("margin", entry * shares_total))
        margin_released = margin_total * fraction
        pos["margin"] = max(0.0, margin_total - margin_released)
        portfolio["cash"] = float(portfolio.get("cash", 0.0)) + margin_released + realized_pnl
    else:
        portfolio["cash"] = float(portfolio.get("cash", 0.0)) + shares_to_close * float(px)

    pos["shares"] = max(0.0, shares_total - shares_to_close)
    pos["partial_taken"] = True
    pos["last_partial_exit_time"] = int(time.time())

    add_realized_pnl(realized_pnl)

    details = {
        "exit_reason": reason,
        "pnl_dollars": round(float(realized_pnl), 2),
        "pnl_pct": round(float(position_pnl_pct(pos, px)) * 100, 2),
        "fraction_closed": round(float(fraction), 4),
        "remaining_shares": round(float(pos.get("shares", 0.0)), 6),
        "market_mode": market_mode
    }
    if extra:
        details.update(extra)

    record_trade("partial_exit", symbol, side, px, shares_to_close, details)

    return {
        "symbol": symbol,
        "side": side,
        "price": round(float(px), 4),
        "shares_closed": round(shares_to_close, 6),
        "remaining_shares": round(float(pos.get("shares", 0.0)), 6),
        "pnl_dollars": round(float(realized_pnl), 2),
        "reason": reason
    }


def enter_position(signal, params, market_mode=None):
    symbol = signal["symbol"]
    side = signal["side"]
    px = float(signal["price"])

    if symbol in portfolio.get("positions", {}):
        return {"symbol": symbol, "side": side, "blocked": True, "reason": "already_held"}

    if is_in_cooldown(symbol):
        return {"symbol": symbol, "side": side, "blocked": True, "reason": "cooldown"}

    alloc_pct = float(params["short_alloc_pct"] if side == "short" else params["long_alloc_pct"])
    alloc_factor = float(signal.get("alloc_factor", 1.0) or 1.0)
    alloc_factor = max(0.05, min(1.0, alloc_factor))
    bucket_factor = bucket_alloc_factor(symbol) if side == "long" else 0.75
    equity = max(float(portfolio.get("equity", portfolio.get("cash", 0.0))), 0.01)
    alloc = min(float(portfolio.get("cash", 0.0)), equity * alloc_pct * alloc_factor * bucket_factor)

    if alloc < MIN_TRADE_ALLOC or px <= 0:
        return {"symbol": symbol, "side": side, "blocked": True, "reason": "insufficient_cash_or_bad_price"}

    shares = alloc / px
    portfolio["cash"] = float(portfolio.get("cash", 0.0)) - alloc

    pos = {
        "side": side,
        "entry": px,
        "last_price": px,
        "shares": shares,
        "entry_time": int(time.time()),
        "score": float(signal.get("score", 0.0)),
        "sector": signal.get("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN")),
        "bucket": signal.get("bucket", symbol_bucket(symbol)),
        "adds": 0,
        "partial_taken": False,
        "entry_context": signal.get("entry_context", "scanner"),
        "catalyst": signal.get("catalyst", {}),
        "theme_confirmation": signal.get("theme_confirmation", {})
    }

    if side == "short":
        pos["margin"] = alloc
        pos["trough"] = px
    else:
        pos["peak"] = px

    portfolio.setdefault("positions", {})[symbol] = pos

    trade_extra = {
        "alloc": round(float(alloc), 2),
        "score": round(float(signal.get("score", 0.0)), 6),
        "sector": pos["sector"],
        "market_mode": market_mode
    }
    if signal.get("entry_context"):
        trade_extra["entry_context"] = signal.get("entry_context")
    if alloc_factor < 1.0:
        trade_extra["alloc_factor"] = round(float(alloc_factor), 4)

    record_trade("entry", symbol, side, px, shares, trade_extra)

    result = {
        "symbol": symbol,
        "side": side,
        "entry": round(px, 4),
        "shares": round(shares, 6),
        "alloc": round(alloc, 2),
        "score": round(float(signal.get("score", 0.0)), 6)
    }
    if signal.get("entry_context"):
        result["entry_context"] = signal.get("entry_context")
    if alloc_factor < 1.0:
        result["alloc_factor"] = round(float(alloc_factor), 4)
    return result


def manage_exits(params, market):
    exits = []
    mode = market.get("market_mode", "neutral")

    for symbol, pos in list(portfolio.get("positions", {}).items()):
        px = latest_price(symbol)
        if px is None:
            continue

        px = float(px)
        pos["last_price"] = px

        side = pos.get("side", "long")
        pnl_pct = position_pnl_pct(pos, px)

        exit_reason = None

        if pnl_pct <= float(params.get("stop_loss", -0.012)):
            exit_reason = "stop_loss"

        if side == "long":
            pos["peak"] = max(float(pos.get("peak", px)), px)
            entry = max(float(pos.get("entry", px)), 0.01)
            peak_profit_pct = (float(pos.get("peak", px)) - entry) / entry

            if PARTIAL_PROFIT_ENABLED and not bool(pos.get("partial_taken", False)) and pnl_pct >= PARTIAL_PROFIT_TRIGGER_PCT:
                partial = reduce_position(
                    symbol,
                    px,
                    PARTIAL_PROFIT_FRACTION,
                    "partial_profit_long",
                    market_mode=mode,
                    extra={"peak_profit_pct": round(peak_profit_pct * 100, 2)}
                )
                if partial:
                    exits.append(partial)
                    # Refresh remaining position reference after share reduction.
                    pos = portfolio.get("positions", {}).get(symbol)
                    if not pos:
                        continue

            # Winner-lock tiers. These are distinct from a normal trailing stop:
            # they make sure a good trade does not round-trip back into a loser.
            if peak_profit_pct >= PROFIT_LOCK_LEVEL_3_PCT and pnl_pct <= PROFIT_LOCK_LEVEL_3_FLOOR_PCT:
                exit_reason = exit_reason or "profit_lock_long_level_3"
            elif peak_profit_pct >= PROFIT_LOCK_LEVEL_2_PCT and pnl_pct <= PROFIT_LOCK_BREAKEVEN_PCT:
                exit_reason = exit_reason or "profit_lock_long_breakeven"
            elif peak_profit_pct >= PROFIT_LOCK_LEVEL_1_PCT and pnl_pct <= 0:
                exit_reason = exit_reason or "profit_lock_long_no_red"

            if peak_profit_pct >= TRAIL_ACTIVATION_PROFIT_PCT:
                if px <= float(pos.get("peak", px)) * float(params.get("trail_long", 0.98)):
                    exit_reason = exit_reason or "trailing_stop_long"

            if market.get("bear_confirmed") or mode in ["risk_off", "crash_warning", "defensive_rotation"]:
                exit_reason = exit_reason or "market_regime_protection"

        else:
            pos["trough"] = min(float(pos.get("trough", px)), px)
            entry = max(float(pos.get("entry", px)), 0.01)
            trough_profit_pct = (entry - float(pos.get("trough", px))) / entry

            if PARTIAL_PROFIT_ENABLED and not bool(pos.get("partial_taken", False)) and pnl_pct >= PARTIAL_PROFIT_TRIGGER_PCT:
                partial = reduce_position(
                    symbol,
                    px,
                    PARTIAL_PROFIT_FRACTION,
                    "partial_profit_short",
                    market_mode=mode,
                    extra={"trough_profit_pct": round(trough_profit_pct * 100, 2)}
                )
                if partial:
                    exits.append(partial)
                    pos = portfolio.get("positions", {}).get(symbol)
                    if not pos:
                        continue

            if trough_profit_pct >= PROFIT_LOCK_LEVEL_3_PCT and pnl_pct <= PROFIT_LOCK_LEVEL_3_FLOOR_PCT:
                exit_reason = exit_reason or "profit_lock_short_level_3"
            elif trough_profit_pct >= PROFIT_LOCK_LEVEL_2_PCT and pnl_pct <= PROFIT_LOCK_BREAKEVEN_PCT:
                exit_reason = exit_reason or "profit_lock_short_breakeven"
            elif trough_profit_pct >= PROFIT_LOCK_LEVEL_1_PCT and pnl_pct <= 0:
                exit_reason = exit_reason or "profit_lock_short_no_red"

            if trough_profit_pct >= TRAIL_ACTIVATION_PROFIT_PCT:
                if px >= float(pos.get("trough", px)) * float(params.get("trail_short", 1.02)):
                    exit_reason = exit_reason or "trailing_stop_short"

            if not market.get("bear_confirmed", False) and mode in ["risk_on", "constructive"]:
                exit_reason = exit_reason or "short_disabled_regime"

        if exit_reason:
            result = exit_position(symbol, px, exit_reason, market_mode=mode)
            if result:
                exits.append(result)

    return exits


def weakest_position_for_rotation(new_signal):
    candidates = []
    now = int(time.time())

    for symbol, pos in portfolio.get("positions", {}).items():
        if symbol == new_signal["symbol"]:
            continue

        px = float(pos.get("last_price", pos.get("entry", 0)))
        pnl_pct = position_pnl_pct(pos, px)
        held_seconds = now - int(pos.get("entry_time", now))
        score = float(pos.get("score", 0.0))
        same_side = pos.get("side", "long") == new_signal["side"]

        # Rotation should usually replace the weakest name on the same side.
        # It may replace a different side only if the market has explicitly changed.
        candidates.append({
            "symbol": symbol,
            "side": pos.get("side", "long"),
            "score": score,
            "pnl_pct": pnl_pct,
            "held_seconds": held_seconds,
            "same_side": same_side,
            "sector": pos.get("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN"))
        })

    if not candidates:
        return None

    same_side_candidates = [c for c in candidates if c["same_side"]]
    pool = same_side_candidates if same_side_candidates else candidates
    return sorted(pool, key=lambda c: (c["score"], c["pnl_pct"]))[0]


def rotation_allowed(new_signal, weakest, market):
    new_score = float(new_signal.get("score", 0.0))
    weak_score = float(weakest.get("score", 0.0))
    weak_pnl = float(weakest.get("pnl_pct", 0.0))
    held = int(weakest.get("held_seconds", 0))

    required_score = max(
        weak_score * ROTATION_SCORE_MULTIPLIER,
        weak_score + ROTATION_MIN_SCORE_EDGE
    )

    if held < ROTATION_MIN_HOLD_SECONDS:
        return False, {
            "reason": "rotation_min_hold_not_met",
            "held_seconds": held,
            "required_hold_seconds": ROTATION_MIN_HOLD_SECONDS,
            "new_score": round(new_score, 6),
            "weakest_score": round(weak_score, 6),
            "required_score": round(required_score, 6),
            "weakest_symbol": weakest.get("symbol")
        }

    if weak_pnl >= ROTATION_KEEP_WINNER_PCT:
        return False, {
            "reason": "keep_winner_guard",
            "weakest_pnl_pct": round(weak_pnl * 100, 2),
            "keep_winner_pct": round(ROTATION_KEEP_WINNER_PCT * 100, 2),
            "new_score": round(new_score, 6),
            "weakest_score": round(weak_score, 6),
            "weakest_symbol": weakest.get("symbol")
        }

    if new_score < required_score:
        return False, {
            "reason": "rotation_threshold_not_met",
            "new_score": round(new_score, 6),
            "weakest_score": round(weak_score, 6),
            "required_score": round(required_score, 6),
            "weakest_symbol": weakest.get("symbol")
        }

    sector_aligned = new_signal.get("sector") in market.get("sector_leaders", [])
    weak_sector_aligned = weakest.get("sector") in market.get("sector_leaders", [])

    # Require even better evidence when rotating into a sector that is not a current leader.
    if not sector_aligned and weak_sector_aligned:
        required_sector_score = required_score + ROTATION_MIN_SCORE_EDGE
        if new_score < required_sector_score:
            return False, {
                "reason": "sector_alignment_guard",
                "new_score": round(new_score, 6),
                "weakest_score": round(weak_score, 6),
                "required_score": round(required_sector_score, 6),
                "sector_aligned": False,
                "weak_sector_aligned": True,
                "weakest_symbol": weakest.get("symbol")
            }

    return True, {
        "reason": "rotation_to_stronger_signal",
        "new_score": round(new_score, 6),
        "weakest_score": round(weak_score, 6),
        "required_score": round(required_score, 6),
        "held_seconds": held,
        "weakest_pnl_pct": round(weak_pnl * 100, 2),
        "sector_aligned": sector_aligned,
        "weakest_symbol": weakest.get("symbol")
    }


def try_entries_and_rotations(long_signals, short_signals, params, market, new_entries_allowed=True, entry_block_reason=None):
    entries = []
    rotations = []
    blocked_entries = []

    max_positions = int(params.get("max_positions", 0))
    mode = market.get("market_mode", "neutral")

    candidate_signals = []
    if params.get("allow_longs", False):
        candidate_signals.extend(long_signals)
    if params.get("allow_shorts", False):
        candidate_signals.extend(short_signals)

    candidate_signals = sorted(candidate_signals, key=lambda x: x["score"], reverse=True)

    if not new_entries_allowed:
        block_reason = entry_block_reason or "new_entries_not_allowed"
        for signal in candidate_signals[:10]:
            blocked_entries.append({
                "symbol": signal.get("symbol"),
                "side": signal.get("side"),
                "score": signal.get("score"),
                "reason": block_reason
            })
        return entries, rotations, blocked_entries

    entries_this_cycle = 0

    for signal in candidate_signals:
        symbol = signal["symbol"]
        side = signal["side"]

        if symbol in portfolio.get("positions", {}):
            blocked_entries.append({"symbol": symbol, "side": side, "reason": "already_held", "score": signal.get("score")})
            continue

        if is_in_cooldown(symbol):
            blocked_entries.append({"symbol": symbol, "side": side, "reason": "cooldown", "score": signal.get("score")})
            continue

        if entries_this_cycle >= MAX_NEW_ENTRIES_PER_CYCLE:
            blocked_entries.append({
                "symbol": symbol,
                "side": side,
                "score": signal.get("score"),
                "reason": "max_new_entries_per_cycle",
                "max_new_entries_per_cycle": MAX_NEW_ENTRIES_PER_CYCLE
            })
            continue

        if len(portfolio.get("positions", {})) < max_positions:
            ok, quality_info = entry_quality_check(signal, params, market)
            if not ok:
                blocked_entries.append({
                    "symbol": symbol,
                    "side": side,
                    "score": signal.get("score"),
                    "reason": "entry_quality_block",
                    "quality_info": quality_info
                })
                continue

            entry = enter_position(signal, params, market_mode=mode)
            if entry and not entry.get("blocked"):
                entry["quality_info"] = quality_info
                entries.append(entry)
                entries_this_cycle += 1
            else:
                blocked_entries.append(entry)
            continue

        weakest = weakest_position_for_rotation(signal)
        if not weakest:
            blocked_entries.append({"symbol": symbol, "side": side, "reason": "max_positions_full", "score": signal.get("score")})
            continue

        allowed, info = rotation_allowed(signal, weakest, market)
        if not allowed:
            blocked_entries.append({
                "symbol": symbol,
                "side": side,
                "score": signal.get("score"),
                "reason": "max_positions_full_no_rotation",
                "rotation_info": info
            })
            continue

        weakest_symbol = weakest["symbol"]
        ok, quality_info = entry_quality_check(signal, params, market, exclude_symbol=weakest_symbol)
        if not ok:
            blocked_entries.append({
                "symbol": symbol,
                "side": side,
                "score": signal.get("score"),
                "reason": "rotation_entry_quality_block",
                "rotation_info": info,
                "quality_info": quality_info
            })
            continue

        pos = portfolio.get("positions", {}).get(weakest_symbol)
        if not pos:
            continue

        px_out = latest_price(weakest_symbol) or float(pos.get("last_price", pos.get("entry", 0)))
        exit_result = exit_position(
            weakest_symbol,
            px_out,
            "rotation_to_stronger_signal",
            market_mode=mode,
            extra={
                "new_score": round(float(signal.get("score", 0.0)), 6),
                "weakest_score": round(float(weakest.get("score", 0.0)), 6),
                "weakest_pnl_pct": round(float(weakest.get("pnl_pct", 0.0)) * 100, 2),
                "held_seconds": weakest.get("held_seconds"),
                "sector_aligned": signal.get("sector") in market.get("sector_leaders", [])
            }
        )

        entry_result = enter_position(signal, params, market_mode=mode)
        if entry_result and not entry_result.get("blocked"):
            entry_result["quality_info"] = quality_info
            entries_this_cycle += 1

        rotations.append({
            "out": weakest_symbol,
            "in": symbol,
            "exit": exit_result,
            "entry": entry_result,
            "info": info,
            "quality_info": quality_info
        })

    return entries, rotations, blocked_entries


# ============================================================
# RUN CYCLE
# ============================================================
def set_auto_attempt(source):
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    ts = now_ts()
    ar["last_attempt_ts"] = ts
    ar["last_attempt_local"] = local_ts_text(ts)
    ar["last_attempt_source"] = source
    ar["last_error"] = None
    ar["last_error_trace"] = None


def set_auto_skip(reason, clock):
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    ts = now_ts()
    ar["last_skip_ts"] = ts
    ar["last_skip_local"] = local_ts_text(ts)
    ar["last_skip_reason"] = reason
    ar["market_open_now"] = bool(clock.get("is_open", False))
    ar["market_clock"] = clock


def set_auto_success(source, result, clock):
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    ts = now_ts()
    ar["last_run_ts"] = ts
    ar["last_run_local"] = local_ts_text(ts)
    ar["last_run_source"] = source
    ar["last_successful_run_ts"] = ts
    ar["last_successful_run_local"] = local_ts_text(ts)
    ar["last_successful_run_source"] = source
    ar["last_result"] = result
    ar["market_open_now"] = bool(clock.get("is_open", False))
    ar["market_clock"] = clock


def set_auto_error(exc):
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    ar["last_error"] = str(exc)
    ar["last_error_trace"] = traceback.format_exc()


def run_cycle(source="manual", allow_after_hours=None):
    if allow_after_hours is None:
        allow_after_hours = ALLOW_MANUAL_AFTER_HOURS_TRADING

    with RUN_LOCK:
        set_auto_attempt(source)
        clock = market_clock()
        portfolio.setdefault("auto_runner", default_auto_runner())["market_clock"] = clock
        portfolio["auto_runner"]["market_open_now"] = bool(clock.get("is_open", False))

        # Critical fix: manual and auto runs cannot trade outside regular session unless explicitly enabled.
        market_only = AUTO_RUN_MARKET_ONLY if source == "auto" else True
        if market_only and not clock["is_open"] and not allow_after_hours:
            calculate_equity(refresh_prices=True)
            reason = f"market closed: {clock['reason']}"
            market = portfolio.get("last_market") or market_status(force=False)
            params = apply_aggression_adjustments(risk_parameters(market), market)
            rc = update_daily_risk_controls(float(portfolio.get("equity", 0.0)))
            feedback = feedback_loop_status(market=market, params=params, risk_controls=rc, clock=clock, persist=True)
            report = None
            if clock.get("reason") == "after_regular_session":
                report = store_compiled_report("end_of_day", market=market, params=params, risk_controls=rc, clock=clock)
            set_auto_skip(reason, clock)
            save_state(portfolio)
            return {
                "skipped": True,
                "reason": reason,
                "market_open_now": False,
                "market_clock": clock,
                "cash": round(float(portfolio.get("cash", 0.0)), 2),
                "equity": round(float(portfolio.get("equity", 0.0)), 2),
                "positions": list(portfolio.get("positions", {}).keys()),
                "performance": performance_snapshot(),
                "risk_controls": get_risk_controls(),
                "feedback_loop": feedback,
                "compiled_report": report
            }

        market = market_status(force=True)
        params = apply_aggression_adjustments(risk_parameters(market), market)

        exits = manage_exits(params, market)
        equity = calculate_equity(refresh_prices=True)
        rc = update_daily_risk_controls(equity)
        prune_cooldowns()
        feedback = feedback_loop_status(market=market, params=params, risk_controls=rc, clock=clock, persist=True)

        long_signals, short_signals, rejected = scan_signals(market)

        warmup = opening_warmup_status(clock)
        entry_block_reasons = []
        if bool(rc.get("halted", False)):
            entry_block_reasons.append("risk_halted")
        if bool(rc.get("profit_guard_active", False)):
            entry_block_reasons.append("profit_guard_active")
        if bool(warmup.get("active", False)):
            entry_block_reasons.append("opening_warmup_active")
        if bool(feedback.get("block_new_entries", False)):
            entry_block_reasons.append("self_defense_feedback_loop")
        if bool(feedback.get("late_day_entry_cutoff", False)):
            entry_block_reasons.append("late_day_entry_cutoff")

        new_entries_allowed = len(entry_block_reasons) == 0
        entry_block_reason = ",".join(entry_block_reasons) if entry_block_reasons else None

        entries, rotations, blocked_entries = try_entries_and_rotations(
            long_signals,
            short_signals,
            params,
            market,
            new_entries_allowed=new_entries_allowed,
            entry_block_reason=entry_block_reason
        )

        equity = calculate_equity(refresh_prices=True)
        rc = update_daily_risk_controls(equity)
        feedback = feedback_loop_status(market=market, params=params, risk_controls=rc, clock=clock, persist=True)
        perf = performance_snapshot()
        controls = entry_controls_snapshot(clock=clock, market=market, params=params, risk_controls=rc)
        compiled_report = store_compiled_report("intraday", market=market, params=params, risk_controls=rc, clock=clock)

        result = {
            **market,
            "cash": round(float(portfolio.get("cash", 0.0)), 2),
            "equity": round(float(portfolio.get("equity", 0.0)), 2),
            "positions": list(portfolio.get("positions", {}).keys()),
            "risk_parameters": params,
            "risk_controls": rc,
            "new_entries_allowed": bool(new_entries_allowed),
            "entry_block_reason": entry_block_reason,
            "entry_quality_controls": controls,
            "feedback_loop": feedback,
            "compiled_report": compiled_report,
            "entries": entries,
            "exits": exits,
            "rotations": rotations,
            "blocked_entries": blocked_entries[:15],
            "rejected_signals": rejected[:15],
            "long_signals": [s["symbol"] for s in long_signals[:10]],
            "short_signals": [s["symbol"] for s in short_signals[:10]],
            "signals_found": len(long_signals) + len(short_signals),
            "performance": perf,
            "market_clock": clock,
            "market_open_now": bool(clock.get("is_open", False))
        }

        portfolio["last_market"] = market
        set_auto_success(source, result, clock)
        save_state(portfolio)
        return result


def auto_runner_loop():
    while True:
        try:
            if AUTO_RUN_ENABLED:
                run_cycle(source="auto", allow_after_hours=False)
        except Exception as exc:
            set_auto_error(exc)
            try:
                save_state(portfolio)
            except Exception:
                pass

        time.sleep(max(30, AUTO_RUN_INTERVAL_SECONDS))


def ensure_auto_thread():
    global AUTO_THREAD_STARTED
    if AUTO_THREAD_STARTED:
        return

    AUTO_THREAD_STARTED = True
    portfolio.setdefault("auto_runner", default_auto_runner())["thread_started"] = True

    t = threading.Thread(target=auto_runner_loop, daemon=True)
    t.start()



# ============================================================
# DECISION SUPPORT / REVIEW LAYER
# ============================================================
def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def pct(value):
    return round(float(value) * 100, 2)


def money(value):
    return round(float(value), 2)


def _count_by(items, key, default="UNKNOWN"):
    counts = {}
    for item in items:
        value = item.get(key, default) if isinstance(item, dict) else default
        if value in [None, ""]:
            value = default
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


def _sum_by(items, key, value_key):
    totals = {}
    for item in items:
        bucket = item.get(key, "UNKNOWN") if isinstance(item, dict) else "UNKNOWN"
        if bucket in [None, ""]:
            bucket = "UNKNOWN"
        totals[bucket] = totals.get(bucket, 0.0) + safe_float(item.get(value_key, 0.0))
    return dict(sorted(((k, round(v, 2)) for k, v in totals.items()), key=lambda x: abs(x[1]), reverse=True))


def local_date_from_ts(ts):
    try:
        return datetime.datetime.fromtimestamp(float(ts), MARKET_TZ).strftime("%Y-%m-%d")
    except Exception:
        return today_key()


def trades_for_date(date_key=None):
    date_key = date_key or today_key()
    return [t for t in portfolio.get("trades", []) if local_date_from_ts(t.get("time", 0)) == date_key]


def minutes_to_regular_close(clock=None):
    clock = clock or market_clock()
    try:
        now = now_local()
        close_dt = now.replace(
            hour=REGULAR_CLOSE_HOUR,
            minute=REGULAR_CLOSE_MINUTE,
            second=0,
            microsecond=0
        )
        return max(0.0, (close_dt - now).total_seconds() / 60.0)
    except Exception:
        return None


def late_day_cutoff_status(clock=None):
    clock = clock or market_clock()
    minutes_left = minutes_to_regular_close(clock)
    active = bool(clock.get("is_open")) and minutes_left is not None and minutes_left <= LATE_DAY_ENTRY_CUTOFF_MINUTES
    return {
        "active": bool(active),
        "minutes_to_close": round(float(minutes_left or 0.0), 2),
        "cutoff_minutes": LATE_DAY_ENTRY_CUTOFF_MINUTES,
        "reason": "late_day_entry_cutoff" if active else "ok"
    }


def feedback_loop_status(market=None, params=None, risk_controls=None, clock=None, persist=True):
    market = market or (portfolio.get("last_market") or market_status(force=False))
    params = params or apply_aggression_adjustments(risk_parameters(market), market)
    risk_controls = risk_controls or get_risk_controls()
    clock = clock or market_clock()

    rp = get_realized_pnl()
    trades_today = trades_for_date(today_key())
    stop_losses_today = sum(
        1 for t in trades_today
        if t.get("action") == "exit" and t.get("exit_reason") == "stop_loss"
    )
    trailing_exits_today = sum(
        1 for t in trades_today
        if t.get("action") == "exit" and str(t.get("exit_reason", "")).startswith("trailing")
    )

    start_equity = max(float(risk_controls.get("day_start_equity", portfolio.get("equity", 10000.0))), 0.01)
    realized_today = float(rp.get("today", 0.0))
    realized_loss_pct = max(0.0, -realized_today / start_equity)
    late_day = late_day_cutoff_status(clock)
    vix_rising = float(market.get("vix_5d_pct", 0.0) or 0.0) > 0
    rates_rising = float(market.get("rates_5d_pct", 0.0) or 0.0) > 1.0

    reasons = []
    actions = []
    block_new_entries = False
    hard_halt = False

    if stop_losses_today >= SELF_DEFENSE_STOP_LOSS_LIMIT:
        block_new_entries = True
        reasons.append(f"{stop_losses_today} stop-loss exits today")
        actions.append("block_new_entries_after_loss_streak")

    if realized_loss_pct >= SELF_DEFENSE_REALIZED_LOSS_PAUSE_PCT:
        block_new_entries = True
        reasons.append(f"realized daily loss {realized_loss_pct * 100:.2f}% reached soft pause")
        actions.append("pause_new_entries_after_soft_loss")

    if realized_loss_pct >= SELF_DEFENSE_HARD_DAILY_LOSS_PCT:
        block_new_entries = True
        hard_halt = True
        reasons.append(f"realized daily loss {realized_loss_pct * 100:.2f}% reached hard halt")
        actions.append("hard_halt_after_realized_loss")

    if late_day.get("active"):
        block_new_entries = True
        reasons.append(f"inside final {LATE_DAY_ENTRY_CUTOFF_MINUTES} minutes before close")
        actions.append("late_day_manage_only")

    if vix_rising:
        actions.append("raise_score_floor_for_rising_vix")
    if rates_rising:
        actions.append("reduce_aggression_for_rising_rates")

    futures = market.get("futures_bias", {}) or {}
    if futures.get("action") in ["reduce_aggression", "tech_caution", "gap_chase_protection", "block_opening_longs"]:
        actions.append(f"futures_bias_{futures.get('action')}")

    breadth = market.get("breadth", {}) or {}
    if breadth.get("action") in ["reduce_aggression", "tech_caution", "risk_off_confirmation"]:
        actions.append(f"breadth_{breadth.get('action')}")

    metals = market.get("precious_metals", {}) or {}
    if metals.get("action") in ["allow_defensive_metals", "allow_metals_momentum"]:
        actions.append(f"precious_metals_{metals.get('state')}")

    if not reasons:
        reasons.append("feedback loop clear")

    feedback = {
        "date": today_key(),
        "updated_local": local_ts_text(),
        "self_defense_mode": bool(block_new_entries or hard_halt),
        "block_new_entries": bool(block_new_entries),
        "hard_halt": bool(hard_halt),
        "late_day_entry_cutoff": bool(late_day.get("active")),
        "late_day_status": late_day,
        "reasons": reasons,
        "actions": actions,
        "stop_losses_today": int(stop_losses_today),
        "trailing_exits_today": int(trailing_exits_today),
        "realized_pnl_today": round(realized_today, 2),
        "realized_loss_pct": round(realized_loss_pct * 100, 3),
        "dynamic_min_long_score": min_entry_score_for_market(market, "long"),
        "base_min_long_score": (
            MIN_ENTRY_SCORE_RISK_ON if market.get("market_mode") == "risk_on" else
            MIN_ENTRY_SCORE_CONSTRUCTIVE if market.get("market_mode") == "constructive" else
            MIN_ENTRY_SCORE_NEUTRAL if market.get("market_mode") == "neutral" else
            MIN_ENTRY_SCORE_DEFENSIVE
        ),
        "vix_rising": bool(vix_rising),
        "rates_rising": bool(rates_rising),
        "aggression_reduced": bool(params.get("aggression_reduced", False)),
        "aggression_reduction_reason": params.get("aggression_reduction_reason", ""),
        "aggression_reduction_factor": params.get("aggression_reduction_factor", 1.0),
        "futures_bias": futures,
        "breadth": breadth,
        "tech_leadership": tech_leadership_status(market)
    }

    if persist:
        portfolio["feedback_loop"] = feedback
        risk_controls["self_defense_active"] = bool(feedback["self_defense_mode"])
        risk_controls["self_defense_reason"] = "; ".join(feedback["reasons"])
        if hard_halt:
            risk_controls["halted"] = True
            risk_controls["halt_reason"] = "self-defense hard daily realized loss halt"

    return feedback


def compile_trading_report(report_type="intraday", market=None, params=None, risk_controls=None, clock=None):
    try:
        calculate_equity(refresh_prices=False)
    except Exception:
        pass

    market = market or (portfolio.get("last_market") or market_status(force=False))
    params = params or apply_aggression_adjustments(risk_parameters(market), market)
    risk_controls = risk_controls or get_risk_controls()
    clock = clock or market_clock()
    perf = performance_snapshot()
    feedback = feedback_loop_status(market=market, params=params, risk_controls=risk_controls, clock=clock, persist=True)
    journal = analyze_trading_journal(limit=50)
    risk_review = portfolio_risk_review()

    report = {
        "type": report_type,
        "date": today_key(),
        "generated_local": local_ts_text(),
        "market_clock": clock,
        "headline": {
            "equity": round(float(portfolio.get("equity", 0.0)), 2),
            "cash": round(float(portfolio.get("cash", 0.0)), 2),
            "day_pnl_pct": risk_controls.get("day_pnl_pct"),
            "daily_loss_pct": risk_controls.get("daily_loss_pct"),
            "intraday_drawdown_pct": risk_controls.get("intraday_drawdown_pct"),
            "realized_pnl_today": perf.get("realized_pnl_today"),
            "unrealized_pnl": perf.get("unrealized_pnl"),
            "open_positions": list(portfolio.get("positions", {}).keys())
        },
        "market": market,
        "risk_controls": risk_controls,
        "feedback_loop": feedback,
        "journal_summary": journal.get("summary", {}),
        "journal_diagnosis": journal.get("diagnosis", []),
        "risk_vulnerabilities": risk_review.get("vulnerabilities", []),
        "risk_recommendations": risk_review.get("recommendations", []),
        "entry_quality_controls": entry_controls_snapshot(clock=clock, market=market, params=params, risk_controls=risk_controls),
        "recent_trades": journal.get("recent_trades", [])[-20:]
    }

    report["plain_english"] = generate_report_plain_english(report)
    return report


def generate_report_plain_english(report):
    h = report.get("headline", {})
    fb = report.get("feedback_loop", {})
    lines = []
    lines.append(
        f"{report.get('type', 'report')} report: equity ${h.get('equity')}, day P/L {h.get('day_pnl_pct')}%, realized ${h.get('realized_pnl_today')}."
    )
    if fb.get("self_defense_mode"):
        lines.append("Self-defense mode is active: " + "; ".join(fb.get("reasons", [])))
    else:
        lines.append("Self-defense mode is not active.")
    if report.get("journal_summary", {}).get("profit_factor") == 0 and report.get("journal_summary", {}).get("losses", 0) > 0:
        lines.append("Trade quality is weak: losses exist and no realized wins are present in the reviewed sample.")
    for vuln in report.get("risk_vulnerabilities", [])[:2]:
        lines.append("Risk note: " + str(vuln))
    return lines


def store_compiled_report(report_type="intraday", market=None, params=None, risk_controls=None, clock=None):
    reports = portfolio.setdefault("reports", default_reports())
    if reports.get("date") != today_key():
        reports["date"] = today_key()
        reports["last_intraday_report"] = None
        reports["last_end_of_day_report"] = None

    report = compile_trading_report(report_type, market=market, params=params, risk_controls=risk_controls, clock=clock)

    if report_type == "end_of_day":
        reports["last_end_of_day_report"] = report
        history = reports.setdefault("daily_history", [])
        # Replace same-date EOD report if present.
        history = [r for r in history if r.get("date") != report.get("date") or r.get("type") != "end_of_day"]
        history.append(report)
        reports["daily_history"] = history[-MAX_REPORTS_STORED:]
    else:
        reports["last_intraday_report"] = report
        history = reports.setdefault("intraday_history", [])
        history.append(report)
        reports["intraday_history"] = history[-MAX_REPORTS_STORED:]

    portfolio["reports"] = reports
    return report


def analyze_trading_journal(limit=20):
    limit = max(5, min(int(limit), 100))
    trades = list(portfolio.get("trades", []))[-limit:]
    exits = [t for t in trades if t.get("action") in ["exit", "rotation_exit"] or "pnl_dollars" in t]
    entries = [t for t in trades if t.get("action") == "entry"]
    rotations = [t for t in trades if t.get("action") == "rotation_exit"]
    stop_losses = [t for t in trades if t.get("exit_reason") == "stop_loss"]
    trailing_exits = [t for t in trades if str(t.get("exit_reason", "")).startswith("trailing_stop")]

    realized = [safe_float(t.get("pnl_dollars", 0.0)) for t in exits if "pnl_dollars" in t]
    wins = [x for x in realized if x >= 0]
    losses = [x for x in realized if x < 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None
    win_rate = round((len(wins) / len(realized)) * 100, 2) if realized else 0.0
    avg_win = round(sum(wins) / len(wins), 2) if wins else 0.0
    avg_loss = round(sum(losses) / len(losses), 2) if losses else 0.0

    hold_values = [safe_float(t.get("held_seconds"), None) for t in exits if t.get("held_seconds") is not None]
    avg_hold_minutes = round((sum(hold_values) / len(hold_values)) / 60, 1) if hold_values else None

    warnings = []
    if realized and len(losses) > len(wins):
        warnings.append("Loss count is higher than win count in the reviewed sample; tighten entry quality and avoid low-edge rotations.")
    if exits and len(rotations) / max(len(exits), 1) >= 0.35:
        warnings.append("Rotation exits make up a large share of exits; the system may still be churning positions too often.")
    if len(stop_losses) >= max(2, len(exits) * 0.30):
        warnings.append("Stop-loss exits are recurring; entries may be late, too extended, or stops may be too tight for current volatility.")
    if avg_win > 0 and avg_loss < 0 and abs(avg_loss) > avg_win:
        warnings.append("Average loss is larger than average win; focus on earlier invalidation or better profit protection.")
    if not warnings:
        warnings.append("No major recurring execution problem detected from the reviewed sample.")

    last_result = portfolio.get("auto_runner", {}).get("last_result") or {}
    blocked = last_result.get("blocked_entries", []) if isinstance(last_result, dict) else []
    rejected = last_result.get("rejected_signals", []) if isinstance(last_result, dict) else []

    missed_opportunities = []
    for item in blocked[:5]:
        missed_opportunities.append({
            "symbol": item.get("symbol"),
            "side": item.get("side"),
            "reason": item.get("reason"),
            "score": item.get("score"),
            "rotation_info": item.get("rotation_info")
        })
    for item in rejected[:5]:
        missed_opportunities.append({
            "symbol": item.get("symbol"),
            "side": item.get("side"),
            "reason": item.get("reason"),
            "score": item.get("score")
        })

    rules = [
        "Do not rotate unless the new setup clears both the score multiplier and minimum score-edge guard.",
        "Do not add fresh risk when profit guard is active; manage existing positions only.",
        "Treat repeated stop-loss exits in the same symbol as a cooldown problem, not a reason to re-enter faster."
    ]

    if len(rotations) >= 3:
        rules.insert(0, "Cut rotation frequency first; prefer holding the strongest confirmed positions over constantly replacing marginal signals.")
    if len(stop_losses) >= 3:
        rules.insert(0, "After two stop-loss exits in the reviewed sample, require stronger sector alignment before new entries.")

    return {
        "reviewed_trades": len(trades),
        "entries_reviewed": len(entries),
        "exits_reviewed": len(exits),
        "summary": {
            "sample_realized_pnl": money(sum(realized)),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": win_rate,
            "gross_profit": money(gross_profit),
            "gross_loss": money(gross_loss),
            "profit_factor": profit_factor,
            "average_win": avg_win,
            "average_loss": avg_loss,
            "average_hold_minutes": avg_hold_minutes
        },
        "breakdowns": {
            "actions": _count_by(trades, "action"),
            "exit_reasons": _count_by(exits, "exit_reason", default="unknown_exit"),
            "symbols": _count_by(trades, "symbol"),
            "sides": _count_by(trades, "side")
        },
        "diagnosis": warnings,
        "missed_or_blocked_recent_setups": missed_opportunities[:10],
        "rules_to_apply_now": rules[:5],
        "recent_trades": trades
    }


def portfolio_risk_review():
    try:
        calculate_equity(refresh_prices=False)
    except Exception:
        pass

    equity = max(float(portfolio.get("equity", 0.0)), 0.01)
    cash = float(portfolio.get("cash", 0.0))
    positions = portfolio.get("positions", {}) or {}
    perf = performance_snapshot()
    rc = get_risk_controls()
    market = portfolio.get("last_market") or market_status(force=False)

    rows = []
    sector_exposure = {}
    bucket_exposure = {}
    side_exposure = {}
    total_position_value = 0.0
    open_losers = 0
    open_winners = 0

    for symbol, pos in positions.items():
        px = safe_float(pos.get("last_price", pos.get("entry", 0.0)))
        value = position_value(pos, px)
        pnl_dollars = position_pnl_dollars(pos, px)
        pnl_pct = position_pnl_pct(pos, px)
        sector = pos.get("sector", SYMBOL_SECTOR.get(symbol, "UNKNOWN"))
        bucket = pos.get("bucket") or symbol_bucket(symbol)
        side = pos.get("side", "long")
        total_position_value += value
        sector_exposure[sector] = sector_exposure.get(sector, 0.0) + value
        bucket_exposure[bucket] = bucket_exposure.get(bucket, 0.0) + value
        side_exposure[side] = side_exposure.get(side, 0.0) + value
        if pnl_dollars >= 0:
            open_winners += 1
        else:
            open_losers += 1
        rows.append({
            "symbol": symbol,
            "side": side,
            "sector": sector,
            "bucket": bucket,
            "position_value": money(value),
            "position_pct_of_equity": pct(value / equity),
            "pnl_dollars": money(pnl_dollars),
            "pnl_pct": round(pnl_pct * 100, 2),
            "score": round(safe_float(pos.get("score")), 6)
        })

    rows = sorted(rows, key=lambda r: r["position_pct_of_equity"], reverse=True)
    sector_pct = {k: pct(v / equity) for k, v in sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True)}
    bucket_pct = {k: pct(v / equity) for k, v in sorted(bucket_exposure.items(), key=lambda x: x[1], reverse=True)}
    side_pct = {k: pct(v / equity) for k, v in sorted(side_exposure.items(), key=lambda x: x[1], reverse=True)}
    cash_pct = pct(cash / equity)
    invested_pct = pct(total_position_value / equity)

    growth_sectors = ["XLK", "XLY", "XLF"]
    defensive_sectors = ["XLV", "XLP", "XLU"]
    growth_pct = pct(sum(sector_exposure.get(s, 0.0) for s in growth_sectors) / equity)
    defensive_pct = pct(sum(sector_exposure.get(s, 0.0) for s in defensive_sectors) / equity)
    energy_pct = pct(sector_exposure.get("XLE", 0.0) / equity)
    unknown_pct = pct(sector_exposure.get("UNKNOWN", 0.0) / equity)

    vulnerabilities = []
    if rows and rows[0]["position_pct_of_equity"] >= 25:
        vulnerabilities.append(f"Largest position is {rows[0]['symbol']} at {rows[0]['position_pct_of_equity']}% of equity.")
    for sector, value_pct in sector_pct.items():
        cap_pct = round(effective_sector_exposure_cap(market, sector) * 100, 2)
        if value_pct >= cap_pct:
            vulnerabilities.append(
                f"Sector concentration is high in {sector} at {value_pct}% of equity; adaptive cap is {cap_pct}%."
            )

    sector_counts = _count_by(rows, "sector")
    for sector, count in sector_counts.items():
        max_count = effective_max_positions_per_sector(market, sector)
        if sector not in [None, "", "UNKNOWN"] and count > max_count:
            vulnerabilities.append(
                f"Too many open positions in {sector}: {count}; adaptive limit is {max_count}."
            )
    bucket_counts = _count_by(rows, "bucket")
    for bucket, count in bucket_counts.items():
        cfg = bucket_config(bucket)
        if count > int(cfg.get("max_positions", 99)):
            vulnerabilities.append(f"Too many open positions in bucket {bucket}: {count}; limit is {int(cfg.get('max_positions', 99))}.")
    for bucket, value_pct in bucket_pct.items():
        cfg = bucket_config(bucket)
        cap = round(float(cfg.get("max_exposure_pct", 1.0)) * 100, 2)
        if value_pct >= cap:
            vulnerabilities.append(f"Bucket exposure is high in {bucket} at {value_pct}% of equity; cap is {cap}%.")
    if cash_pct < 15:
        vulnerabilities.append(f"Cash buffer is low at {cash_pct}% of equity.")
    if unknown_pct >= 10:
        vulnerabilities.append(f"Unknown/unmapped sector exposure is {unknown_pct}%; map those tickers before relying on sector controls.")
    if rc.get("profit_guard_active"):
        vulnerabilities.append(f"Profit guard is active: {rc.get('profit_guard_reason', '')}")
    if safe_float(rc.get("intraday_drawdown_pct")) >= 1.0:
        vulnerabilities.append(f"Intraday drawdown is elevated at {rc.get('intraday_drawdown_pct')}% from the day peak.")
    if open_losers > open_winners and len(rows) >= 3:
        vulnerabilities.append("More open positions are losing than winning; avoid adding risk until the open book improves.")
    if not vulnerabilities:
        vulnerabilities.append("No major concentration or drawdown vulnerability detected from current paper state.")

    recommendations = []
    if market.get("bear_confirmed"):
        recommendations.append("Bear confirmation is active; longs should remain blocked and shorts may be allowed only under the short-bias rules.")
    elif market.get("market_mode") in ["risk_on", "constructive"]:
        recommendations.append("Market mode supports long bias, but position additions should still respect profit guard, sector alignment, and max-position limits.")
    else:
        recommendations.append("Market mode is not strongly risk-on; reduce fresh entries and prioritize preserving cash.")

    if growth_pct >= 50:
        tech = tech_leadership_status(market)
        if tech.get("active"):
            recommendations.append("Growth/tech exposure is elevated, but adaptive tech leadership mode allows higher XLK/XLY exposure while leadership remains confirmed; keep entries staggered and scores strong.")
        else:
            recommendations.append("Growth exposure is heavy; avoid adding more XLK/XLY/XLF names unless they clearly outrank existing holdings.")
    if cash_pct < 20:
        recommendations.append("Keep a cash reserve; do not force full deployment just because signals are available.")
    if safe_float(perf.get("unrealized_pnl")) > 0 and safe_float(rc.get("intraday_drawdown_pct")) > 0.75:
        recommendations.append("Open gains exist but intraday giveback is visible; prioritize trailing stops and avoid discretionary re-entry.")

    return {
        "equity": money(equity),
        "cash": money(cash),
        "cash_pct": cash_pct,
        "invested_pct": invested_pct,
        "market_mode": market.get("market_mode"),
        "regime": market.get("regime"),
        "risk_score": market.get("risk_score"),
        "futures_bias": market.get("futures_bias", {}),
        "breadth": market.get("breadth", {}),
        "precious_metals": market.get("precious_metals", {}),
        "tech_leadership": tech_leadership_status(market),
        "risk_controls": rc,
        "performance": perf,
        "exposures": {
            "by_sector_pct": sector_pct,
            "by_side_pct": side_pct,
            "growth_pct": growth_pct,
            "defensive_pct": defensive_pct,
            "energy_pct": energy_pct,
            "precious_metals_pct": round(sum(r["position_pct_of_equity"] for r in rows if r.get("bucket") == "precious_metals"), 2),
            "unknown_pct": unknown_pct,
            "sector_position_counts": _count_by(rows, "sector")
        },
        "entry_quality_controls": entry_controls_snapshot(market=market, risk_controls=rc),
        "feedback_loop": feedback_loop_status(market=market, risk_controls=rc, persist=False),
        "positions": rows,
        "vulnerabilities": vulnerabilities,
        "recommendations": recommendations
    }


def explain_current_system(force_market=False):
    try:
        calculate_equity(refresh_prices=False)
    except Exception:
        pass

    market = market_status(force=force_market) if force_market else (portfolio.get("last_market") or market_status(force=False))
    params = apply_aggression_adjustments(risk_parameters(market), market)
    rc = get_risk_controls()
    clock = market_clock()
    ar = portfolio.setdefault("auto_runner", default_auto_runner())
    last_result = ar.get("last_result") or {}

    reasons = []
    if market.get("risk_score", 0) >= 70:
        reasons.append("Risk score is high enough for a long-biased risk-on posture.")
    elif market.get("risk_score", 0) >= 55:
        reasons.append("Risk score is constructive but not fully aggressive.")
    else:
        reasons.append("Risk score is not strong enough for aggressive long exposure.")

    if market.get("bear_confirmed"):
        reasons.append("Bear confirmation is active, so long entries should be blocked and short rules may activate.")
    else:
        reasons.append("Bear confirmation is not active, so shorts remain disabled by design.")

    if rc.get("halted"):
        reasons.append(f"Trading is halted by risk control: {rc.get('halt_reason')}")
    elif rc.get("profit_guard_active"):
        reasons.append(f"Fresh entries are restricted by profit guard: {rc.get('profit_guard_reason')}")
    elif not clock.get("is_open"):
        reasons.append(f"Market is currently closed: {clock.get('reason')}. Manual /paper/run will not trade unless after-hours trading is explicitly enabled.")
    elif opening_warmup_status(clock).get("active"):
        warmup = opening_warmup_status(clock)
        reasons.append(
            f"Opening warm-up is active: fresh entries are paused until {OPENING_WARMUP_MINUTES} minutes after regular open."
        )
    else:
        reasons.append("Market is open and risk controls are not halted.")

    long_allowed = bool(params.get("allow_longs")) and not rc.get("halted")
    short_allowed = bool(params.get("allow_shorts")) and not rc.get("halted")
    new_entries_allowed = bool(last_result.get("new_entries_allowed", not rc.get("halted") and not rc.get("profit_guard_active")))

    return {
        "market_clock": clock,
        "market": market,
        "risk_parameters": params,
        "risk_controls": rc,
        "entry_quality_controls": entry_controls_snapshot(clock=clock, market=market, params=params, risk_controls=rc),
        "feedback_loop": feedback_loop_status(market=market, params=params, risk_controls=rc, clock=clock, persist=False),
        "current_permission": {
            "longs_allowed_by_regime": bool(params.get("allow_longs")),
            "shorts_allowed_by_regime": bool(params.get("allow_shorts")),
            "longs_allowed_now": long_allowed,
            "shorts_allowed_now": short_allowed,
            "new_entries_allowed_last_cycle": new_entries_allowed,
            "max_positions": params.get("max_positions"),
            "max_new_entries_per_cycle": MAX_NEW_ENTRIES_PER_CYCLE,
            "max_positions_per_sector": MAX_POSITIONS_PER_SECTOR,
            "max_sector_exposure_pct": round(MAX_SECTOR_EXPOSURE_PCT * 100, 2),
            "active_min_entry_score": min_entry_score_for_market(market, "long")
        },
        "last_cycle": {
            "last_run_local": ar.get("last_run_local"),
            "last_skip_reason": ar.get("last_skip_reason"),
            "long_signals": last_result.get("long_signals", []),
            "short_signals": last_result.get("short_signals", []),
            "blocked_entries": last_result.get("blocked_entries", [])[:10],
            "rotations": last_result.get("rotations", [])[:10],
            "entries": last_result.get("entries", [])[:10],
            "exits": last_result.get("exits", [])[:10]
        },
        "plain_english": reasons
    }


def daily_trading_plan():
    market = portfolio.get("last_market") or market_status(force=False)
    params = apply_aggression_adjustments(risk_parameters(market), market)
    rc = get_risk_controls()
    clock = market_clock()

    stance = "balanced / reduced"
    if market.get("bear_confirmed"):
        stance = "defensive / short-bias only"
    elif market.get("market_mode") == "risk_on":
        stance = "long-biased risk-on"
    elif market.get("market_mode") == "constructive":
        stance = "selective long-biased"
    elif market.get("market_mode") in ["risk_off", "defensive_rotation", "crash_warning"]:
        stance = "capital preservation"

    guardrails = [
        f"Max positions: {params.get('max_positions')}",
        f"Longs allowed: {bool(params.get('allow_longs'))}",
        f"Shorts allowed: {bool(params.get('allow_shorts'))}",
        f"Stop loss: {round(abs(float(params.get('stop_loss', 0))) * 100, 2)}%",
        f"Profit guard active: {bool(rc.get('profit_guard_active'))}",
        f"Opening warm-up: {OPENING_WARMUP_MINUTES} minutes",
        f"Max new entries per cycle: {MAX_NEW_ENTRIES_PER_CYCLE}",
        f"Minimum active long score: {min_entry_score_for_market(market, 'long')}",
        f"Max sector exposure: {round(MAX_SECTOR_EXPOSURE_PCT * 100, 2)}%",
        f"Max positions per sector: {MAX_POSITIONS_PER_SECTOR}",
        f"Self-defense stop-loss limit: {SELF_DEFENSE_STOP_LOSS_LIMIT}",
        f"Soft realized-loss pause: {round(SELF_DEFENSE_REALIZED_LOSS_PAUSE_PCT * 100, 2)}%",
        f"Hard realized-loss halt: {round(SELF_DEFENSE_HARD_DAILY_LOSS_PCT * 100, 2)}%",
        f"Trailing stop activates after: {round(TRAIL_ACTIVATION_PROFIT_PCT * 100, 2)}% profit",
        f"Late-day entry cutoff: final {LATE_DAY_ENTRY_CUTOFF_MINUTES} minutes"
    ]

    if rc.get("profit_guard_active"):
        guardrails.append(f"Profit guard reason: {rc.get('profit_guard_reason')}")
    if rc.get("halted"):
        guardrails.append(f"Risk halt reason: {rc.get('halt_reason')}")

    return {
        "date": today_key(),
        "clock": clock,
        "market_stance": stance,
        "market_mode": market.get("market_mode"),
        "regime": market.get("regime"),
        "risk_score": market.get("risk_score"),
        "sector_leaders": market.get("sector_leaders", []),
        "guardrails": guardrails,
        "checklist": [
            {
                "phase": "Pre-market",
                "time": "Before regular open",
                "steps": [
                    "Open /paper/market?force=1 and confirm market mode, risk score, QQQ/SPY trend, VIX direction, and sector leaders.",
                    "Open /paper/risk-review and verify cash buffer, sector concentration, and open-position P/L.",
                    "Do not override the bot into longs if bear_confirmed is true."
                ]
            },
            {
                "phase": "Opening window",
                "time": "First 30-60 minutes",
                "steps": [
                    f"Wait through the {OPENING_WARMUP_MINUTES}-minute opening warm-up before fresh entries are allowed.",
                    f"Limit new positions to {MAX_NEW_ENTRIES_PER_CYCLE} per cycle; do not fill the whole book from one scan.",
                    "Reject entries that are extended above the 5-minute MA20 or too close to the intraday high after a big move.",
                    f"Reject low-score entries below the active floor of {min_entry_score_for_market(market, 'long')}.",
                    f"Keep sector exposure under {round(MAX_SECTOR_EXPOSURE_PCT * 100, 2)}% and positions per sector at or below {MAX_POSITIONS_PER_SECTOR}.",
                    "Avoid rotation unless the new score clearly beats the weakest holding by the configured rotation guard."
                ]
            },
            {
                "phase": "Midday management",
                "time": "Late morning to early afternoon",
                "steps": [
                    "Use /paper/explain to confirm why entries, exits, blocks, or rotations happened.",
                    "If profit guard is active, manage existing positions only and do not open fresh risk.",
                    "If losses cluster in the same symbol or sector, respect cooldowns and stop re-entry churn."
                ]
            },
            {
                "phase": "Closing routine",
                "time": "Final 30-45 minutes",
                "steps": [
                    "Review /paper/journal for stop-loss clusters, rotation churn, and average win/loss quality.",
                    "Check whether open winners need trailing-stop protection into the close.",
                    "Do not use /paper/run after close expecting trades; it is blocked by default after regular session."
                ]
            }
        ]
    }

# ============================================================
# HTML DASHBOARD
# ============================================================
DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Scanner + Long/Short Paper System</title>
    <style>
        body {
            background: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif;
            padding: 22px;
            line-height: 1.35;
        }
        h1 { font-size: 32px; margin-bottom: 20px; }
        .hero { font-size: 24px; font-weight: 800; margin-bottom: 18px; }
        .grid { display: grid; gap: 14px; }
        .card {
            border: 1px solid #1e293b;
            background: #111c31;
            border-radius: 16px;
            padding: 18px;
        }
        .label { color: #94a3b8; letter-spacing: 2px; font-size: 14px; text-transform: uppercase; }
        .value { font-size: 28px; font-weight: 800; margin-top: 8px; }
        .small { font-size: 15px; color: #cbd5e1; }
        a { color: #38bdf8; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        td, th { border-bottom: 1px solid #1e293b; padding: 8px; text-align: left; }
        .good { color: #22c55e; }
        .bad { color: #ef4444; }
        .warn { color: #f59e0b; }
    </style>
</head>
<body>
    <h1>Scanner + Long/Short Paper System</h1>
    <div class="hero">
        Market: {{ market.market_mode }} |
        Risk: {{ market.risk_score }} |
        Regime: {{ market.regime }} |
        Leaders: {{ ", ".join(market.sector_leaders or []) }}
    </div>

    <div class="hero">
        Trading Halted: {{ "YES" if risk.halted else "NO" }} |
        Day P/L: {{ risk.day_pnl_pct }}% |
        Daily Loss: {{ risk.daily_loss_pct }}% |
        Intraday DD: {{ risk.intraday_drawdown_pct }}% |
        Profit Guard: {{ "ON" if risk.profit_guard_active else "OFF" }}
    </div>

    {% if risk.profit_guard_active %}
    <div class="hero warn">Profit Guard Reason: {{ risk.profit_guard_reason }}</div>
    {% endif %}

    <div class="hero">
        Entry Guard: Warm-up {{ entry_controls.opening_warmup.required_warmup_minutes }} min |
        Max Entries/Cycle: {{ entry_controls.max_new_entries_per_cycle }} |
        Active Min Score: {{ entry_controls.min_entry_score.active_long_floor }} |
        Sector Cap: {{ entry_controls.sector_controls.max_sector_exposure_pct }}% |
        Max/Sector: {{ entry_controls.sector_controls.max_positions_per_sector }}
    </div>

    <div class="hero {{ 'warn' if entry_controls.feedback_loop.self_defense_mode else '' }}">
        Feedback Loop: {{ "SELF-DEFENSE" if entry_controls.feedback_loop.self_defense_mode else "CLEAR" }} |
        Stop Losses Today: {{ entry_controls.feedback_loop.stop_losses_today }} |
        Realized Loss: {{ entry_controls.feedback_loop.realized_loss_pct }}% |
        Late Cutoff: {{ "ON" if entry_controls.feedback_loop.late_day_entry_cutoff else "OFF" }}
    </div>

    <div class="hero">
        Auto Runner: {{ "ON" if auto.enabled else "OFF" }} |
        Thread: {{ "RUNNING" if auto.thread_started else "OFF" }} |
        Market Open: {{ "YES" if auto.market_open_now else "NO" }} |
        Last Run: {{ auto.last_run_local or "never" }} |
        Last Skip: {{ auto.last_skip_reason or "none" }} |
        Error: {{ auto.last_error or "none" }}
    </div>

    <div class="grid">
        <div class="card">
            <div class="label">Equity</div>
            <div class="value">${{ "%.2f"|format(equity) }}</div>
        </div>
        <div class="card">
            <div class="label">Cash</div>
            <div class="value">${{ "%.2f"|format(cash) }}</div>
        </div>
        <div class="card">
            <div class="label">Realized Today</div>
            <div class="value">${{ "%.2f"|format(performance.realized_pnl_today) }}</div>
        </div>
        <div class="card">
            <div class="label">Unrealized</div>
            <div class="value">${{ "%.2f"|format(performance.unrealized_pnl) }}</div>
        </div>
    </div>

    <h2>Open Positions</h2>
    <div class="card">
        <table>
            <tr><th>Symbol</th><th>Side</th><th>Entry</th><th>Last</th><th>P/L $</th><th>P/L %</th><th>Score</th></tr>
            {% for sym, p in performance.open_positions.items() %}
            <tr>
                <td>{{ sym }}</td>
                <td>{{ p.side }}</td>
                <td>{{ p.entry }}</td>
                <td>{{ p.last_price }}</td>
                <td class="{{ 'good' if p.pnl_dollars >= 0 else 'bad' }}">{{ p.pnl_dollars }}</td>
                <td class="{{ 'good' if p.pnl_pct >= 0 else 'bad' }}">{{ p.pnl_pct }}%</td>
                <td>{{ p.score }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <p class="small">
        JSON: <a href="/paper/status">/paper/status</a> Â·
        Market: <a href="/paper/market?force=1">/paper/market?force=1</a> Â·
        Explain: <a href="/paper/explain">/paper/explain</a> Â·
        Journal: <a href="/paper/journal">/paper/journal</a> Â·
        Risk Review: <a href="/paper/risk-review">/paper/risk-review</a> Â·
        Daily Plan: <a href="/paper/daily-plan">/paper/daily-plan</a> Â·
        Feedback: <a href="/paper/feedback-loop">/paper/feedback-loop</a> Â·
        Intraday Report: <a href="/paper/intraday-report">/paper/intraday-report</a> Â·
        EOD Report: <a href="/paper/end-of-day-report">/paper/end-of-day-report</a> Â·
        Run once: <a href="/paper/run">/paper/run</a> Â·
        Auth Help: <a href="/paper/auth-help">/paper/auth-help</a>
    </p>
</body>
</html>
"""


# ============================================================
# API VISIBILITY / SAFE JSON HELPERS
# ============================================================
def to_jsonable(value):
    """Convert numpy/datetime/sets and nested objects into JSON-safe primitives."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.ndarray,)):
        return [to_jsonable(v) for v in value.tolist()]
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    try:
        return float(value)
    except Exception:
        return str(value)


def add_endpoint_meta(payload, endpoint, ok=True, warning=None, error=None):
    meta = {
        "ok": bool(ok),
        "endpoint": endpoint,
        "generated_local": local_ts_text(),
        "market_clock": market_clock(),
        "payload_present": payload is not None,
        "content_type": "application/json",
        "version": "metals-scanner-2026-05-07"
    }
    if warning:
        meta["warning"] = str(warning)
    if error:
        meta["error"] = str(error)

    if isinstance(payload, dict):
        result = dict(payload)
        result["_endpoint_health"] = meta
        return result

    return {"_endpoint_health": meta, "data": payload}


def json_response(payload, endpoint="unknown", status=200, ok=True, warning=None, error=None):
    body = add_endpoint_meta(payload, endpoint=endpoint, ok=ok, warning=warning, error=error)
    resp = jsonify(to_jsonable(body))
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["X-Bot-Endpoint"] = endpoint
    return resp


def state_file_diagnostic():
    try:
        exists = os.path.exists(STATE_FILE)
        size = os.path.getsize(STATE_FILE) if exists else 0
    except Exception:
        exists = False
        size = 0
    return {
        "state_file": STATE_FILE,
        "exists": bool(exists),
        "size_bytes": int(size),
        "positions_count": len(portfolio.get("positions", {}) or {}),
        "trades_count": len(portfolio.get("trades", []) or []),
        "history_count": len(portfolio.get("history", []) or []),
        "reports_present": bool(portfolio.get("reports")),
        "feedback_loop_present": bool(portfolio.get("feedback_loop")),
        "pullback_watchlist_count": len(portfolio.get("pullback_watchlist", {}) or {})
    }


def compact_report(report):
    if not isinstance(report, dict):
        return report
    return {
        "type": report.get("type"),
        "date": report.get("date"),
        "generated_local": report.get("generated_local"),
        "headline": report.get("headline", {}),
        "feedback_loop": report.get("feedback_loop", {}),
        "journal_summary": report.get("journal_summary", {}),
        "journal_diagnosis": report.get("journal_diagnosis", []),
        "risk_vulnerabilities": report.get("risk_vulnerabilities", []),
        "risk_recommendations": report.get("risk_recommendations", []),
        "plain_english": report.get("plain_english", []),
        "recent_trades": (report.get("recent_trades", []) or [])[-12:]
    }


def reports_snapshot(full=False):
    reports = portfolio.setdefault("reports", default_reports())
    if full:
        return reports
    return {
        "date": reports.get("date"),
        "last_intraday_report": compact_report(reports.get("last_intraday_report")),
        "last_end_of_day_report": compact_report(reports.get("last_end_of_day_report")),
        "intraday_history_count": len(reports.get("intraday_history", []) or []),
        "daily_history_count": len(reports.get("daily_history", []) or []),
        "latest_intraday_times": [
            r.get("generated_local") for r in (reports.get("intraday_history", []) or [])[-5:]
            if isinstance(r, dict)
        ],
        "latest_daily_dates": [
            r.get("date") for r in (reports.get("daily_history", []) or [])[-5:]
            if isinstance(r, dict)
        ]
    }


def config_snapshot():
    return {
        "auto_run_enabled": AUTO_RUN_ENABLED,
        "auto_run_interval_seconds": AUTO_RUN_INTERVAL_SECONDS,
        "auto_run_market_only": AUTO_RUN_MARKET_ONLY,
        "allow_manual_after_hours_trading": ALLOW_MANUAL_AFTER_HOURS_TRADING,
        "auth": {
            "preferred_auth": "X-Run-Key header",
            "query_key_auth_allowed_temporarily": bool(ALLOW_QUERY_KEY_AUTH),
            "query_key_auth_deprecated": True,
            "run_key_is_default": SECRET_KEY == "changeme",
            "rotate_run_key_recommended_if_exposed": True,
            "note": "Do not send RUN_KEY in the URL; Railway/Gunicorn access logs can expose full request URLs."
        },
        "max_daily_loss_pct": MAX_DAILY_LOSS_PCT,
        "max_intraday_drawdown_pct": MAX_INTRADAY_DRAWDOWN_PCT,
        "rotation_score_multiplier": ROTATION_SCORE_MULTIPLIER,
        "rotation_min_score_edge": ROTATION_MIN_SCORE_EDGE,
        "rotation_min_hold_seconds": ROTATION_MIN_HOLD_SECONDS,
        "rotation_keep_winner_pct": ROTATION_KEEP_WINNER_PCT,
        "day_profit_pause_new_entries_pct": DAY_PROFIT_PAUSE_NEW_ENTRIES_PCT,
        "day_profit_hard_lock_pct": DAY_PROFIT_HARD_LOCK_PCT,
        "day_profit_giveback_lock_pct": DAY_PROFIT_GIVEBACK_LOCK_PCT,
        "opening_warmup_minutes": OPENING_WARMUP_MINUTES,
        "max_new_entries_per_cycle": MAX_NEW_ENTRIES_PER_CYCLE,
        "min_entry_score_risk_on": MIN_ENTRY_SCORE_RISK_ON,
        "min_entry_score_constructive": MIN_ENTRY_SCORE_CONSTRUCTIVE,
        "min_entry_score_neutral": MIN_ENTRY_SCORE_NEUTRAL,
        "min_entry_score_defensive": MIN_ENTRY_SCORE_DEFENSIVE,
        "min_short_entry_score": MIN_SHORT_ENTRY_SCORE,
        "max_sector_exposure_pct": MAX_SECTOR_EXPOSURE_PCT,
        "max_positions_per_sector": MAX_POSITIONS_PER_SECTOR,
        "tech_leadership_mode_enabled": TECH_LEADERSHIP_MODE_ENABLED,
        "tech_leadership_sectors": TECH_LEADERSHIP_SECTORS,
        "tech_leadership_min_risk_score": TECH_LEADERSHIP_MIN_RISK_SCORE,
        "tech_leadership_max_exposure_pct": TECH_LEADERSHIP_MAX_EXPOSURE_PCT,
        "tech_leadership_caution_exposure_pct": TECH_LEADERSHIP_CAUTION_EXPOSURE_PCT,
        "tech_leadership_max_positions_per_sector": TECH_LEADERSHIP_MAX_POSITIONS_PER_SECTOR,
        "tech_leadership_score_relief": TECH_LEADERSHIP_SCORE_RELIEF,
        "tech_leadership_breadth_score_bump": TECH_LEADERSHIP_BREADTH_SCORE_BUMP,
        "tech_leadership_breadth_alloc_reduction": TECH_LEADERSHIP_BREADTH_ALLOC_REDUCTION,
        "self_defense_stop_loss_limit": SELF_DEFENSE_STOP_LOSS_LIMIT,
        "self_defense_realized_loss_pause_pct": SELF_DEFENSE_REALIZED_LOSS_PAUSE_PCT,
        "self_defense_hard_daily_loss_pct": SELF_DEFENSE_HARD_DAILY_LOSS_PCT,
        "trail_activation_profit_pct": TRAIL_ACTIVATION_PROFIT_PCT,
        "late_day_entry_cutoff_minutes": LATE_DAY_ENTRY_CUTOFF_MINUTES,
        "entry_score_loss_step": ENTRY_SCORE_LOSS_STEP,
        "vix_rising_score_bump": VIX_RISING_SCORE_BUMP,
        "rates_rising_score_bump": RATES_RISING_SCORE_BUMP,
        "vix_rising_alloc_reduction": VIX_RISING_ALLOC_REDUCTION,
        "futures_bias_enabled": FUTURES_BIAS_ENABLED,
        "futures_es_symbol": FUTURES_ES_SYMBOL,
        "futures_nq_symbol": FUTURES_NQ_SYMBOL,
        "futures_bullish_nq_pct": FUTURES_BULLISH_NQ_PCT,
        "futures_bullish_es_pct": FUTURES_BULLISH_ES_PCT,
        "futures_bearish_nq_pct": FUTURES_BEARISH_NQ_PCT,
        "futures_bearish_es_pct": FUTURES_BEARISH_ES_PCT,
        "futures_gap_up_chase_pct": FUTURES_GAP_UP_CHASE_PCT,
        "futures_score_bump_caution": FUTURES_SCORE_BUMP_CAUTION,
        "futures_score_bump_bearish": FUTURES_SCORE_BUMP_BEARISH,
        "futures_alloc_reduction_caution": FUTURES_ALLOC_REDUCTION_CAUTION,
        "futures_alloc_reduction_bearish": FUTURES_ALLOC_REDUCTION_BEARISH,
        "breadth_confirmation_enabled": BREADTH_CONFIRMATION_ENABLED,
        "breadth_score_bump_narrow": BREADTH_SCORE_BUMP_NARROW,
        "breadth_alloc_reduction_narrow": BREADTH_ALLOC_REDUCTION_NARROW,
        "relative_strength_score_bonus": RELATIVE_STRENGTH_SCORE_BONUS,
        "relative_strength_score_penalty": RELATIVE_STRENGTH_SCORE_PENALTY,
        "partial_profit_enabled": PARTIAL_PROFIT_ENABLED,
        "partial_profit_trigger_pct": PARTIAL_PROFIT_TRIGGER_PCT,
        "partial_profit_fraction": PARTIAL_PROFIT_FRACTION,
        "profit_lock_level_1_pct": PROFIT_LOCK_LEVEL_1_PCT,
        "profit_lock_level_2_pct": PROFIT_LOCK_LEVEL_2_PCT,
        "profit_lock_level_3_pct": PROFIT_LOCK_LEVEL_3_PCT,
        "profit_lock_breakeven_pct": PROFIT_LOCK_BREAKEVEN_PCT,
        "profit_lock_level_3_floor_pct": PROFIT_LOCK_LEVEL_3_FLOOR_PCT,
        "post_stop_score_bump": POST_STOP_SCORE_BUMP,
        "post_stop_require_sector_leader": POST_STOP_REQUIRE_SECTOR_LEADER,
        "post_stop_exceptional_score": POST_STOP_EXCEPTIONAL_SCORE,
        "pullback_reclaim_enabled": PULLBACK_RECLAIM_ENABLED,
        "pullback_watch_ttl_seconds": PULLBACK_WATCH_TTL_SECONDS,
        "pullback_max_above_ma20": PULLBACK_MAX_ABOVE_MA20,
        "pullback_reclaim_score_bonus": PULLBACK_RECLAIM_SCORE_BONUS,
        "controlled_pullback_entry_enabled": CONTROLLED_PULLBACK_ENTRY_ENABLED,
        "controlled_pullback_min_score": CONTROLLED_PULLBACK_MIN_SCORE,
        "controlled_pullback_score_discount": CONTROLLED_PULLBACK_SCORE_DISCOUNT,
        "controlled_pullback_minutes_after_open": CONTROLLED_PULLBACK_MINUTES_AFTER_OPEN,
        "controlled_pullback_no_entry_last_minutes": CONTROLLED_PULLBACK_NO_ENTRY_LAST_MINUTES,
        "controlled_pullback_max_entries_per_day": CONTROLLED_PULLBACK_MAX_ENTRIES_PER_DAY,
        "controlled_pullback_alloc_factor": CONTROLLED_PULLBACK_ALLOC_FACTOR,
        "controlled_pullback_require_caution_context": CONTROLLED_PULLBACK_REQUIRE_CAUTION_CONTEXT,
        "controlled_pullback_require_sector_leader": CONTROLLED_PULLBACK_REQUIRE_SECTOR_LEADER,
        "controlled_pullback_allow_empty_book_only": CONTROLLED_PULLBACK_ALLOW_EMPTY_BOOK_ONLY,
        "expanded_scanner_enabled": EXPANDED_SCANNER_ENABLED,
        "precious_metals_alloc_factor": PRECIOUS_METALS_ALLOC_FACTOR,
        "precious_metals_max_exposure_pct": PRECIOUS_METALS_MAX_EXPOSURE_PCT,
        "precious_metals_max_positions": PRECIOUS_METALS_MAX_POSITIONS,
        "precious_metals_safe_haven_score_bonus": PRECIOUS_METALS_SAFE_HAVEN_SCORE_BONUS,
        "precious_metals_trend_score_bonus": PRECIOUS_METALS_TREND_SCORE_BONUS,
        "precious_metals_weak_dollar_score_bonus": PRECIOUS_METALS_WEAK_DOLLAR_SCORE_BONUS,
        "scanner_universe_count": len(UNIVERSE),
        "scanner_universe": UNIVERSE,
        "scanner_buckets": {k: [sym for sym, b in SYMBOL_BUCKET.items() if b == k] for k in sorted(set(SYMBOL_BUCKET.values()))},
        "bucket_config": BUCKET_CONFIG,
        "catalyst_momentum_enabled": CATALYST_MOMENTUM_ENABLED,
        "catalyst_min_intraday_move_pct": CATALYST_MIN_INTRADAY_MOVE_PCT,
        "catalyst_volume_surge_ratio": CATALYST_VOLUME_SURGE_RATIO,
        "catalyst_score_bonus": CATALYST_SCORE_BONUS,
        "catalyst_strong_score_bonus": CATALYST_STRONG_SCORE_BONUS,
        "theme_confirmation_enabled": THEME_CONFIRMATION_ENABLED,
        "theme_confirmation_min_signals": THEME_CONFIRMATION_MIN_SIGNALS,
        "theme_confirmation_score_bonus": THEME_CONFIRMATION_SCORE_BONUS,
        "max_reports_stored": MAX_REPORTS_STORED
    }


def compact_status_snapshot(include_last_result=True):
    clock = market_clock()
    auto = portfolio.setdefault("auto_runner", default_auto_runner())
    auto["market_clock"] = clock
    auto["market_open_now"] = bool(clock.get("is_open", False))

    perf = performance_snapshot()
    rc = get_risk_controls()
    market = portfolio.get("last_market") or {}
    feedback = portfolio.get("feedback_loop") or default_feedback_loop()
    reports = reports_snapshot(full=False)

    last_result = auto.get("last_result") if include_last_result else None
    if isinstance(last_result, dict):
        last_result = {
            "market_mode": last_result.get("market_mode"),
            "regime": last_result.get("regime"),
            "risk_score": last_result.get("risk_score"),
            "trade_permission": last_result.get("trade_permission"),
            "futures_bias": last_result.get("futures_bias", {}),
            "breadth": last_result.get("breadth", {}),
            "precious_metals": last_result.get("precious_metals", {}),
            "entries": last_result.get("entries", []),
            "exits": last_result.get("exits", []),
            "rotations": last_result.get("rotations", []),
            "blocked_entries": (last_result.get("blocked_entries", []) or [])[:12],
            "rejected_signals": (last_result.get("rejected_signals", []) or [])[:12],
            "long_signals": last_result.get("long_signals", []),
            "short_signals": last_result.get("short_signals", []),
            "entry_block_reason": last_result.get("entry_block_reason"),
            "new_entries_allowed": last_result.get("new_entries_allowed"),
            "feedback_loop": last_result.get("feedback_loop")
        }

    return {
        "status": "running",
        "time": local_ts_text(),
        "market_clock": clock,
        "cash": round(float(portfolio.get("cash", 0.0)), 2),
        "equity": round(float(portfolio.get("equity", 0.0)), 2),
        "peak": round(float(portfolio.get("peak", portfolio.get("equity", 0.0))), 2),
        "positions": portfolio.get("positions", {}),
        "position_symbols": list((portfolio.get("positions", {}) or {}).keys()),
        "performance": perf,
        "realized_pnl": portfolio.get("realized_pnl", default_realized_pnl()),
        "risk_controls": rc,
        "feedback_loop": feedback,
        "last_market": market,
        "futures_bias": market.get("futures_bias", {}) if isinstance(market, dict) else {},
        "breadth": market.get("breadth", {}) if isinstance(market, dict) else {},
        "precious_metals": market.get("precious_metals", {}) if isinstance(market, dict) else {},
        "pullback_watchlist": portfolio.get("pullback_watchlist", {}),
        "auto_runner": {
            "enabled": auto.get("enabled"),
            "market_only": auto.get("market_only"),
            "interval_seconds": auto.get("interval_seconds"),
            "market_open_now": auto.get("market_open_now"),
            "market_clock": auto.get("market_clock"),
            "thread_started": auto.get("thread_started"),
            "last_run_local": auto.get("last_run_local"),
            "last_run_source": auto.get("last_run_source"),
            "last_successful_run_local": auto.get("last_successful_run_local"),
            "last_skip_local": auto.get("last_skip_local"),
            "last_skip_reason": auto.get("last_skip_reason"),
            "last_error": auto.get("last_error"),
            "last_error_trace": auto.get("last_error_trace"),
            "last_result": last_result
        },
        "recent_trades": (portfolio.get("trades", []) or [])[-20:],
        "history_tail": (portfolio.get("history", []) or [])[-30:],
        "reports": reports,
        "state_diagnostic": state_file_diagnostic()
    }


def build_checkup_snapshot(force_market=False, compile_report=False):
    ensure_auto_thread()
    try:
        calculate_equity(refresh_prices=False)
    except Exception:
        pass

    clock = market_clock()
    market = portfolio.get("last_market") or {}
    if force_market:
        try:
            market = market_status(force=True)
            portfolio["last_market"] = market
        except Exception:
            market = portfolio.get("last_market") or {}

    params = apply_aggression_adjustments(risk_parameters(market), market)
    rc = get_risk_controls()
    feedback = feedback_loop_status(market=market, params=params, risk_controls=rc, clock=clock, persist=True)
    perf = performance_snapshot()
    journal = analyze_trading_journal(limit=30)
    risk = portfolio_risk_review()

    report = None
    if compile_report:
        try:
            report = store_compiled_report("intraday", market=market, params=params, risk_controls=rc, clock=clock)
        except Exception as exc:
            report = {"error": str(exc), "fallback": "report_compile_failed"}

    save_state(portfolio)

    plain_english = []
    if feedback.get("self_defense_mode"):
        plain_english.append("Self-defense mode is active: " + "; ".join(feedback.get("reasons", [])))
    else:
        plain_english.append("Self-defense mode is not active.")
    plain_english.append(
        f"Equity ${round(float(portfolio.get('equity', 0.0)), 2)}, realized today ${perf.get('realized_pnl_today')}, unrealized ${perf.get('unrealized_pnl')}."
    )
    if market:
        plain_english.append(
            f"Market mode {market.get('market_mode')} / regime {market.get('regime')} / risk score {market.get('risk_score')}."
        )
    if risk.get("vulnerabilities"):
        plain_english.append("Top risk: " + str(risk.get("vulnerabilities", [])[0]))

    return {
        "status": "ok",
        "summary": plain_english,
        "market_clock": clock,
        "health": {"status": "running", "time": local_ts_text()},
        "compact_status": compact_status_snapshot(),
        "feedback_loop": feedback,
        "intraday_report": compact_report(report) if report else reports_snapshot(full=False).get("last_intraday_report"),
        "risk_review": risk,
        "journal": journal,
        "explain": explain_current_system(force_market=False),
        "config": config_snapshot(),
        "state_diagnostic": state_file_diagnostic(),
        "links": {
            "health": "/health",
            "compact_status": "/paper/status",
            "full_status": "/paper/status?full=1",
            "checkup": "/paper/checkup",
            "feedback_loop": "/paper/feedback-loop",
            "intraday_report": "/paper/intraday-report",
            "risk_review": "/paper/risk-review",
            "journal": "/paper/journal",
            "explain": "/paper/explain"
        }
    }


def safe_route(endpoint, builder, status=200, fallback_builder=None):
    try:
        payload = builder()
        return json_response(payload, endpoint=endpoint, status=status, ok=True)
    except Exception as exc:
        error_payload = None
        if fallback_builder:
            try:
                error_payload = fallback_builder()
            except Exception:
                error_payload = None
        if error_payload is None:
            error_payload = compact_status_snapshot(include_last_result=False)
        error_payload["route_error"] = {
            "message": str(exc),
            "trace": traceback.format_exc()[-4000:]
        }
        return json_response(error_payload, endpoint=endpoint, status=500, ok=False, error=exc)


# ============================================================
# ROUTES
# ============================================================
@app.route("/")
def home():
    ensure_auto_thread()
    try:
        calculate_equity(refresh_prices=False)
    except Exception:
        pass

    return render_template_string(
        DASHBOARD,
        cash=float(portfolio.get("cash", 0.0)),
        equity=float(portfolio.get("equity", 0.0)),
        market=portfolio.get("last_market") or market_status(force=False),
        risk=get_risk_controls(),
        auto=portfolio.setdefault("auto_runner", default_auto_runner()),
        performance=performance_snapshot(),
        entry_controls=entry_controls_snapshot()
    )


@app.route("/health")
def health():
    return json_response({
        "status": "running",
        "time": local_ts_text(),
        "market_clock": market_clock(),
        "state_diagnostic": state_file_diagnostic(),
        "important_links": {
            "checkup": "/paper/checkup",
            "auth_help": "/paper/auth-help",
            "status": "/paper/status",
            "full_status": "/paper/status?full=1",
            "feedback_loop": "/paper/feedback-loop",
            "intraday_report": "/paper/intraday-report"
        }
    }, endpoint="health")


@app.route("/paper/checkup")
def paper_checkup():
    force = request.args.get("force", "0").lower() in ["1", "true", "yes", "on"]
    compile_report = request.args.get("compile", "0").lower() in ["1", "true", "yes", "on"]
    return safe_route(
        "paper_checkup",
        lambda: build_checkup_snapshot(force_market=force, compile_report=compile_report),
        fallback_builder=lambda: compact_status_snapshot(include_last_result=True)
    )


@app.route("/paper/heartbeat")
def paper_heartbeat():
    return safe_route("paper_heartbeat", lambda: {
        "status": "running",
        "time": local_ts_text(),
        "market_clock": market_clock(),
        "compact_status": compact_status_snapshot(include_last_result=False),
        "state_diagnostic": state_file_diagnostic()
    })


@app.route("/paper/status")
def paper_status():
    def build():
        ensure_auto_thread()
        calculate_equity(refresh_prices=False)
        portfolio.setdefault("auto_runner", default_auto_runner())["market_clock"] = market_clock()
        portfolio["auto_runner"]["market_open_now"] = bool(portfolio["auto_runner"]["market_clock"].get("is_open", False))
        performance_snapshot()
        save_state(portfolio)
        full = request.args.get("full", "0").lower() in ["1", "true", "yes", "on"]
        if full:
            payload = dict(portfolio)
            payload["state_diagnostic"] = state_file_diagnostic()
            payload["note"] = "Full status requested. For scheduled check-ins use /paper/status or /paper/checkup."
            return payload
        return compact_status_snapshot(include_last_result=True)
    return safe_route("paper_status", build, fallback_builder=lambda: compact_status_snapshot(include_last_result=True))


@app.route("/paper/market")
def paper_market():
    def build():
        force = request.args.get("force", "0").lower() in ["1", "true", "yes", "on"]
        market = market_status(force=force)
        portfolio["last_market"] = market
        save_state(portfolio)
        return market
    return safe_route("paper_market", build, fallback_builder=lambda: portfolio.get("last_market") or {"market_mode": "unknown", "warning": "market unavailable"})


@app.route("/paper/auth-help")
def paper_auth_help():
    return json_response({
        "status": "ok",
        "preferred_auth": "X-Run-Key header",
        "why": "URL query parameters can be written to Railway/Gunicorn access logs, which can expose secrets.",
        "recommended_steps": [
            "Rotate RUN_KEY in Railway if the old key appeared in logs or screenshots.",
            "Call /paper/run with the X-Run-Key header instead of ?key=...",
            "Remove old URLs containing ?key=... from bookmarks, screenshots, notes, and automations."
        ],
        "curl_example": 'curl -H "X-Run-Key: YOUR_RUN_KEY" https://trading-bot-clean.up.railway.app/paper/run',
        "backward_compatibility": {
            "query_key_auth_allowed_temporarily": bool(ALLOW_QUERY_KEY_AUTH),
            "disable_with_env": "ALLOW_QUERY_KEY_AUTH=false"
        }
    }, endpoint="paper_auth_help")


@app.route("/paper/run")
def paper_run():
    if not key_ok():
        return json_response(auth_failed_payload(), endpoint="paper_run", status=401, ok=False)

    force_after_hours = request.args.get("after_hours", "0").lower() in ["1", "true", "yes", "on"]
    allow_after_hours = ALLOW_MANUAL_AFTER_HOURS_TRADING and force_after_hours

    def build():
        return attach_auth_warning(run_cycle(source="manual", allow_after_hours=allow_after_hours))

    return safe_route("paper_run", build, fallback_builder=lambda: compact_status_snapshot(include_last_result=True))


@app.route("/paper/reset")
def paper_reset():
    if not key_ok():
        return json_response(auth_failed_payload(), endpoint="paper_reset", status=401, ok=False)
    cash = float(request.args.get("cash", "10000"))
    reset_state(cash)
    return json_response(attach_auth_warning({"status": "reset", "cash": cash, "equity": cash}), endpoint="paper_reset")


@app.route("/paper/close_all")
def close_all():
    if not key_ok():
        return json_response(auth_failed_payload(), endpoint="paper_close_all", status=401, ok=False)

    def build():
        clock = market_clock()
        if not clock["is_open"] and not ALLOW_MANUAL_AFTER_HOURS_TRADING:
            return attach_auth_warning({
                "blocked": True,
                "reason": f"market closed: {clock['reason']}",
                "market_clock": clock
            })

        exits = []
        mode = portfolio.get("last_market", {}).get("market_mode", "manual_close")
        for symbol, pos in list(portfolio.get("positions", {}).items()):
            px = latest_price(symbol) or float(pos.get("last_price", pos.get("entry", 0)))
            result = exit_position(symbol, px, "manual_close_all", market_mode=mode)
            if result:
                exits.append(result)

        calculate_equity(refresh_prices=True)
        save_state(portfolio)
        return attach_auth_warning({"closed": exits, "cash": portfolio["cash"], "equity": portfolio["equity"]})
    return safe_route("paper_close_all", build, fallback_builder=lambda: compact_status_snapshot())


@app.route("/paper/journal")
def paper_journal():
    def build():
        ensure_auto_thread()
        limit = request.args.get("limit", "30")
        try:
            limit = int(limit)
        except Exception:
            limit = 30
        journal = analyze_trading_journal(limit=limit)
        if not journal.get("recent_trades"):
            journal["note"] = "No recent trades found. Endpoint is working and returning an empty journal safely."
        return journal
    return safe_route("paper_journal", build, fallback_builder=lambda: {"recent_trades": [], "summary": {}, "diagnosis": ["journal unavailable fallback"]})


@app.route("/paper/risk-review")
def paper_risk_review():
    return safe_route("paper_risk_review", lambda: portfolio_risk_review(), fallback_builder=lambda: {
        "cash": round(float(portfolio.get("cash", 0.0)), 2),
        "equity": round(float(portfolio.get("equity", 0.0)), 2),
        "positions": list((portfolio.get("positions", {}) or {}).keys()),
        "risk_controls": get_risk_controls(),
        "vulnerabilities": ["risk review fallback returned because full risk review failed"]
    })


@app.route("/paper/explain")
def paper_explain():
    def build():
        ensure_auto_thread()
        force = request.args.get("force", "0").lower() in ["1", "true", "yes", "on"]
        return explain_current_system(force_market=force)
    return safe_route("paper_explain", build, fallback_builder=lambda: {
        "plain_english": ["Explain endpoint fallback: bot is running, but full explanation failed."],
        "compact_status": compact_status_snapshot(include_last_result=True)
    })


@app.route("/paper/daily-plan")
def paper_daily_plan():
    return safe_route("paper_daily_plan", lambda: daily_trading_plan(), fallback_builder=lambda: {
        "date": today_key(),
        "market_clock": market_clock(),
        "checklist": [],
        "guardrails": [],
        "warning": "daily plan fallback returned because full plan failed"
    })


@app.route("/paper/feedback-loop")
def paper_feedback_loop():
    def build():
        ensure_auto_thread()
        market = portfolio.get("last_market") or market_status(force=False)
        params = apply_aggression_adjustments(risk_parameters(market), market)
        rc = get_risk_controls()
        clock = market_clock()
        feedback = feedback_loop_status(market=market, params=params, risk_controls=rc, clock=clock, persist=True)
        save_state(portfolio)
        return feedback
    return safe_route("paper_feedback_loop", build, fallback_builder=lambda: portfolio.get("feedback_loop") or default_feedback_loop())


@app.route("/paper/intraday-report")
def paper_intraday_report():
    def build():
        ensure_auto_thread()
        market = portfolio.get("last_market") or market_status(force=False)
        params = apply_aggression_adjustments(risk_parameters(market), market)
        rc = get_risk_controls()
        clock = market_clock()
        report = store_compiled_report("intraday", market=market, params=params, risk_controls=rc, clock=clock)
        save_state(portfolio)
        return compact_report(report) if request.args.get("full", "0").lower() not in ["1", "true", "yes", "on"] else report
    return safe_route("paper_intraday_report", build, fallback_builder=lambda: reports_snapshot(full=False).get("last_intraday_report") or {"note": "no intraday report yet"})


@app.route("/paper/end-of-day-report")
def paper_end_of_day_report():
    def build():
        ensure_auto_thread()
        market = portfolio.get("last_market") or market_status(force=False)
        params = apply_aggression_adjustments(risk_parameters(market), market)
        rc = get_risk_controls()
        clock = market_clock()
        report = store_compiled_report("end_of_day", market=market, params=params, risk_controls=rc, clock=clock)
        save_state(portfolio)
        return compact_report(report) if request.args.get("full", "0").lower() not in ["1", "true", "yes", "on"] else report
    return safe_route("paper_end_of_day_report", build, fallback_builder=lambda: reports_snapshot(full=False).get("last_end_of_day_report") or {"note": "no end-of-day report yet"})


@app.route("/paper/reports")
def paper_reports():
    full = request.args.get("full", "0").lower() in ["1", "true", "yes", "on"]
    return safe_route("paper_reports", lambda: reports_snapshot(full=full), fallback_builder=lambda: default_reports())


@app.route("/paper/report/today")
def paper_report_today():
    def build():
        ensure_auto_thread()
        reports = portfolio.setdefault("reports", default_reports())
        report = reports.get("last_end_of_day_report") or reports.get("last_intraday_report")
        if not report:
            report = store_compiled_report("intraday")
            save_state(portfolio)
        full = request.args.get("full", "0").lower() in ["1", "true", "yes", "on"]
        return report if full else compact_report(report)
    return safe_route("paper_report_today", build, fallback_builder=lambda: {"note": "no report available yet", "compact_status": compact_status_snapshot()})


@app.route("/paper/config")
def paper_config():
    return safe_route("paper_config", lambda: config_snapshot())


@app.route("/paper/state-diagnostic")
def paper_state_diagnostic():
    return safe_route("paper_state_diagnostic", lambda: {
        "state_diagnostic": state_file_diagnostic(),
        "compact_status": compact_status_snapshot(include_last_result=False),
        "reports": reports_snapshot(full=False),
        "config": config_snapshot()
    })


ensure_auto_thread()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
