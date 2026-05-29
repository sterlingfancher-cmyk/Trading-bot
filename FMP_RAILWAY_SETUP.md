# Financial Modeling Prep API Key Setup

The fundamental / analyst valuation risk layer is already installed in the trading bot, but it remains neutral until a Financial Modeling Prep API key is available in Railway.

## Required Railway variable

Add this variable in Railway:

```text
FMP_API_KEY=<your Financial Modeling Prep API key>
```

Accepted aliases are also supported by the bot:

```text
FINANCIALMODELINGPREP_API_KEY=<your key>
FINANCIAL_MODELING_PREP_API_KEY=<your key>
```

Use **FMP_API_KEY** as the preferred name to keep the deployment clean.

## What this enables

After Railway redeploys, these endpoints should switch from neutral/cache-miss/missing-api-key behavior to real analyst and valuation scoring:

```text
/paper/fundamental-valuation-risk-status
/paper/analyst-valuation-risk-status
```

The layer is intentionally bounded:

- It does **not** raise max positions beyond 14.
- It does **not** force new entries.
- It does **not** bypass halts, stop losses, score floors, or state-journal guards.
- It only adjusts sizing/rotation after a technical signal exists.
- It stays advisory / bounded risk-multiplier logic for ML Phase 2.6.

## Post-deploy checks

After adding the Railway variable and redeploying, check:

```text
https://trading-bot-clean.up.railway.app/paper/fundamental-valuation-risk-status?force=1
https://trading-bot-clean.up.railway.app/paper/analyst-valuation-risk-status?force=1
https://trading-bot-clean.up.railway.app/paper/self-check
```

Expected signs that the provider is working:

```text
provider.configured: true
provider.fetched: > 0
profiles_by_symbol.<SYMBOL>.status: ok
risk_multiplier: may be below/above 1.0 based on valuation and analyst data
```

If `provider.configured` is still false, Railway has not received the key or the service has not redeployed with the new environment variable.
