# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Personal script that logs into the Dietly/OptiDiet catering panel and automatically swaps meals for upcoming deliveries to maximise protein and carbs while minimising fat. All changes are dry-run by default; `--apply` is required to actually save.

## Running the script

```bash
# Dry-run preview (default 3 days)
.venv/bin/python main.py --days 3

# Apply changes with confirmation per day
.venv/bin/python main.py --days 3 --apply

# Apply all future deliveries without prompting (cron-safe)
.venv/bin/python main.py --all --apply --yes
```

Exit code is 0 on clean run, 1 if any PUT failed.

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
cp .env.example .env  # then fill in values
```

All required `.env` variables (script will fail-fast with a named error if any are missing):

```
OPTIDIET_EMAIL
OPTIDIET_PASSWORD
OPTIDIET_BODY_WEIGHT_KG
OPTIDIET_PROTEIN_MIN_G_PER_KG
OPTIDIET_CALORIES_TARGET
OPTIDIET_CARBS_MIN_G
OPTIDIET_CARBS_TARGET
OPTIDIET_FAT_TARGET
```

Optional:

```
OPTIDIET_ORDER_ID   # jeśli pominięte, skrypt wykrywa zamówienie automatycznie po OPTIDIET_CALORIES_TARGET
```

## Architecture

```
main.py          — CLI, orchestration, logging setup
config.py        — loads and validates all env vars; computes DAILY_MIN_PROTEIN
dietly_api.py    — HTTP client (Playwright APIRequestContext); all API calls live here
selector.py      — meal scoring and selection logic; no I/O
```

**Data flow**: `main.py` drives the loop. For each delivery it calls `get_delivery_slots()` which fetches the menu and then fetches switch-options for each switchable slot. `select_best_meal()` in `selector.py` picks the winner. If `--apply`, `save_meal_selection()` sends a PUT.

**HTTP layer** (`dietly_api.py`): Uses Playwright's `APIRequestContext` (not `requests`/`httpx`) so session cookies from the login POST are automatically carried forward. All requests go through `_request()` which retries up to 3× with exponential backoff (1.5 s base) on 429/5xx and `PlaywrightError` (network/timeout failures). `ApiError` carries `status: int` for structured error handling — use `e.status` not string matching.

**Scoring** (`selector.py`): `select_best_meal()` filters out meals matching `BLOCKED_KEYWORDS` (soup/liquid dishes) and returns `None` if every candidate is blocked. Matching is whole-word (`_BLOCKED_RE` wraps each keyword in `\b`), so `kawa` does not catch `kawałki` and `koktajl` does not catch `sosem koktajlowym`; add keywords in their natural base form, without padding spaces. Inflected forms are deliberately not matched — `nutą kawy`, `na napoju owsianym` and `Kawowa owsianka` are real dishes, not drinks. Among candidates, `_quality_score()` scores: carbs (weight 0.40, maximise), protein (0.30, maximise), calories (0.25, maximise), healthy-ingredient bonus (0.05). Fat and protein floors have no score weight — they are handled exclusively via greedy-fix thresholds in `main.py` (`CARBS_MIN_G`, `DAILY_MIN_PROTEIN`, `FAT_SOFT_G`, `FAT_HARD_G`). Scores are normalised against per-meal share of daily targets (`DAILY_TARGETS[x] / MEALS_PER_DAY`). `MEALS_PER_DAY = 5` — must match actual slot count in deliveries.

**Logging**: Output is set up in `_setup_output()`, called from `__main__` after argument validation — no log file is created for `--help` or validation failures. Log files land in `logs/` with mode 0o600; at most 30 files are kept (oldest deleted on startup). `config.py` auto-corrects `.env` permissions to 0o600 on every run.

**Error isolation**: slot-level PUT errors are caught and counted; delivery-level errors are caught and counted. `sys.exit(1)` fires at the end if `total_errors > 0`, leaving the log with a `BŁĘDY: N operacji nie powiodło się.` line.

## Key constraints

- API HTTP 490 = delivery locked (too close to delivery date) — not an error, shown as `⏸`.
- `OPTIDIET_ORDER_ID` scopes all calls to a single order. Without it the script would touch all active orders.
- Delivery data comes from `GET /company/customer/order/{id}` which returns the full order including all deliveries; `get_upcoming_deliveries()` filters client-side.
