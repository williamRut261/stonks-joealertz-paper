# STONKS JoeAlerts — PUBLIC capture-only prototype

**Source:** https://x.com/joealertz · **Status:** GitHub Actions capture-only research. **NO BROKER, NO ORDERS, NO PAPER FILLS.** The author of the X account describes his ideas as educational, not actionable buy/sell instructions. This project is unaffiliated.

## How it works

The scheduled workflow runs on a standard GitHub Actions Ubuntu runner every five minutes (best-effort; runs can be late or dropped). It queries official X API v2 endpoints for @joealertz using your own authorized X developer application's `X_BEARER_TOKEN` repository secret. **X API access and read volume can cost money even when GitHub's runner minutes are free.**

It checks author identity and new post IDs. The first successful run **baselines without replaying older posts**. Later runs classify new public posts as `candidate_stock`, `candidate_option`, or `ignored` based on a strict, deterministic grammar. Candidate means text resembles a syntactically explicit trade, not that Joe made a trade or that an automated follower should do so. Most natural-language commentary is ignored.

State is restored between jobs using a short-lived Actions artifact. It contains **ONLY public post IDs, classification labels, and an X cursor**, never raw post text, account information, API tokens, or broker order data. **All logs and artifacts may be publicly accessible** because this repo is public. A missing/expired artifact causes a fresh baseline, losing continuity rather than replaying old posts. On a malformed state, API error, or pagination overflow, the scan fails closed.

## Enable capture

1. Go to **Settings → Secrets and variables → Actions → New repository secret**.
2. Add the secret **`X_BEARER_TOKEN`** using a bearer token authorized for `GET /2/users/by/username/:username` and `GET /2/users/:id/tweets`. Never commit the token or paste it into chat. Review X API pricing before enabling repeated 5-minute calls.
3. Go to **Actions → JoeAlerts capture-only (NO BROKER / NO ORDERS) → Run workflow**. The first successful X poll only starts the cursor.
4. Future scheduled logs show public post IDs and classifications; no orders will be placed.

Run offline tests locally with `python -m unittest discover -s tests -v`.

## Next phase—not deployed

Before using Alpaca PAPER, independently validate actual Joe post formats, feed latency, official X usage costs, paper-account isolation, exact options expiry/strike and order lifecycle, realistic fills, stops and exits, and replay protection. GitHub's schedule is **not suitable for fast options copying**. Do not add Alpaca credentials to this public repository's workflows. Existing STONKS/A15/CAND-80 systems are untouched.
