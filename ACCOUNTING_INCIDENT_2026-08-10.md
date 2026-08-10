# Accounting integrity incident — 2026-08-10

Observed daily audit reconstructed negative cash and economically implausible legacy position basis while `paper_accounting_integrity` still reported pass. This demonstrates that syntactic ledger coverage is insufficient; reconciliation must also require economic plausibility.

Do not clear the current hard risk halt automatically. Treat today's P&L, win/loss evidence, and MAE/MFE forward-evidence promotion as untrusted until ledger economics reconcile.

Required guards:
- reconstructed cash may not go materially negative for this cash-only paper account;
- each buy row must not exceed cash available immediately before that row;
- reconstructed initial cash/baseline must be provenance-safe;
- implausible ledger rows must be identified and quarantine promotion evidence rather than being silently blessed;
- status reads remain observational;
- no strategy, threshold, sizing policy, live authority, or ML authority changes.
