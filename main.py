"""
Automatyczny wybór posiłków na nadchodzące dostawy.

Uruchom: python main.py [--days N | --all] [--apply] [--yes]
  --days N   ile dni do przodu (domyślnie 3)
  --all      do końca aktywnego zamówienia
  --apply    zapisz wybór w panelu (domyślnie tylko podgląd)
  --yes      zatwierdź wszystkie dni bez pytania (wymaga --apply)
"""

import asyncio
import argparse
import sys
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table
from rich.rule import Rule  # noqa: F401 — used via _con.rule / _log.rule
from rich import box
from rich.markup import escape

from dietly_api import DietlyClient, MealSlot, ApiError
from playwright.async_api import Error as PlaywrightError
from selector import select_best_meal, score_meal, best_for_macro
import config

_con: Console | None = None
_log: Console | None = None
_log_fh = None
_log_file: Path | None = None


def _setup_output() -> None:
    global _con, _log, _log_fh, _log_file
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    _log_file = log_dir / f"zmiany_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    _log_file.touch(mode=0o600)
    _log_fh = open(_log_file, "w", encoding="utf-8")
    _con = Console(highlight=False)
    _log = Console(file=_log_fh, no_color=True, highlight=False, width=79)
    existing = sorted(log_dir.glob("zmiany_*.log"))
    for old in existing[:-30]:
        old.unlink(missing_ok=True)


def _p(msg: str = "") -> None:
    _con.print(msg, markup=False)
    _log.print(msg, markup=False)


def _pm(msg: str = "") -> None:
    _con.print(msg)
    _log.print(msg)


def _greedy_fix(
    chosen_by_slot: list[tuple[MealSlot, object]],
    macro: str,
    target: float,
    minimize: bool = False,
    protect: dict[str, float] | None = None,
) -> tuple[list[tuple[MealSlot, object]], list[str]]:
    """Zamienia minimalną liczbę slotów żeby osiągnąć `target` dla `macro`.
    protect: słownik {makro: min_wartość} — swap jest pomijany jeśli naruszyłby te limity."""
    current = sum(getattr(m, macro) for _, m in chosen_by_slot)
    if (minimize and current <= target) or (not minimize and current >= target):
        return chosen_by_slot, []

    result = list(chosen_by_slot)
    running = {p: sum(getattr(m, p) for _, m in result) for p in (protect or {})}

    candidates = []
    for i, (slot, cur_meal) in enumerate(result):
        best = best_for_macro(slot.options, macro, minimize)
        if best is None:
            continue
        if minimize:
            gain = getattr(cur_meal, macro) - getattr(best, macro)
        else:
            gain = getattr(best, macro) - getattr(cur_meal, macro)
        if gain > 0:
            candidates.append((i, gain, best, slot, cur_meal))
    candidates.sort(key=lambda x: x[1], reverse=True)

    label = {"carbs": "W", "protein": "B", "fat": "T"}.get(macro, macro)
    sign = "-" if minimize else "+"
    remaining = abs(target - current)
    log_lines = []
    for i, gain, best, slot, old_meal in candidates:
        if remaining <= 0:
            break
        if protect:
            if any(
                running[p] - getattr(old_meal, p) + getattr(best, p) < min_val
                for p, min_val in protect.items()
            ):
                continue
        result[i] = (slot, best)
        remaining -= gain
        for p in running:
            running[p] += getattr(best, p) - getattr(old_meal, p)
        log_lines.append(
            f"    [{slot.category}] {old_meal.name[:45]}"
            f"\n      → {best.name[:45]}  ({sign}{gain:.0f}g {label})"
        )

    return result, log_lines


def _print_greedy_fix(label: str, swaps: list[str]) -> None:
    _pm(f"  [yellow]{escape(label)}[/yellow]")
    for line in swaps:
        _pm(f"[yellow]{escape(line)}[/yellow]")


def print_slot_selection(slot: MealSlot, chosen) -> None:
    ranked = sorted(slot.options, key=score_meal, reverse=True)
    _p(f"\n  [{slot.category}]")
    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column(ratio=3)
    table.add_column()
    for meal in ranked:
        is_chosen = meal.diet_calories_meal_id == chosen.diet_calories_meal_id
        marker = "★" if is_chosen else " "
        macro = (f"Kcal:{meal.calories:.0f}  B:{meal.protein:.1f}g  "
                 f"W:{meal.carbs:.1f}g  T:{meal.fat:.1f}g  "
                 f"(score:{score_meal(meal):+.2f})")
        if is_chosen:
            name_cell = f"[bold green]{marker}  {escape(meal.name)}[/bold green]"
            macro_cell = f"[bold green]{macro}[/bold green]"
        else:
            name_cell = f"[dim]{marker}  {escape(meal.name)}[/dim]"
            macro_cell = f"[dim]{macro}[/dim]"
        table.add_row(name_cell, macro_cell)
    _con.print(table)
    _log.print(table)


def _print_daily_summary(total, pstatus, wstatus, fstatus) -> None:
    t = config.DAILY_TARGETS
    fat = total["fat"]
    tbl = Table(title="Suma dzienna", box=box.SIMPLE_HEAD, padding=(0, 2))
    tbl.add_column("Kalorie", justify="right")
    tbl.add_column("Białko (B)", justify="right")
    tbl.add_column("Węglowodany (W)", justify="right")
    tbl.add_column("Tłuszcz (T)", justify="right")

    p_col = "[green]OK[/green]" if pstatus == "OK" else f"[red]{escape(pstatus)}[/red]"
    w_col = "[green]OK[/green]" if wstatus == "OK" else f"[red]{escape(wstatus)}[/red]"
    if "PRZEKROCZONO" in fstatus:
        f_col = f"[bold red]{escape(fstatus)}[/bold red]"
    elif "przekroczono" in fstatus:
        f_col = f"[yellow]{escape(fstatus)}[/yellow]"
    else:
        f_col = f"[green]{escape(fstatus)}[/green]"

    tbl.add_row(
        f"{total['calories']:.0f} / {t['calories']}",
        f"{total['protein']:.1f} / {config.DAILY_MIN_PROTEIN}g  {p_col}",
        f"{total['carbs']:.1f} / {config.CARBS_MIN_G}g  {w_col}",
        f"{fat:.1f}g  {f_col}",
    )
    _con.print(tbl)
    _log.print(tbl)


async def process_delivery(
    client: DietlyClient, delivery: dict, apply: bool, yes: bool
) -> int:
    did = delivery["deliveryId"]
    oid = delivery["_orderId"]
    day = delivery["date"]

    _con.rule(f"[bold cyan]{day}  (dostawa {did})[/bold cyan]", style="cyan")
    _log.rule(f"{day}")

    slots, locked_msg = await client.get_delivery_slots(oid, did)
    if locked_msg:
        _p(f"  ⏸ {locked_msg}")
        return 0
    if not slots:
        _p("  Brak edytowalnych slotów.")
        return 0

    active = [s for s in slots if s.options]
    for slot in slots:
        if not slot.options:
            _p(f"  [{slot.category}] brak alternatyw")

    if not active:
        _p("  Menu niedostępne — brak opcji do wyboru we wszystkich slotach.")
        return 0

    def _pick(weights=None):
        result = []
        for s in active:
            meal = select_best_meal(s.options, weights)
            if meal is None:
                _p(f"  [{s.category}] wszystkie opcje zablokowane — slot pominięty")
            else:
                result.append((s, meal))
        return result

    def _sum(chosen):
        t: dict[str, float] = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
        for _, m in chosen:
            for k in t:
                t[k] += getattr(m, k)
        return t

    chosen_by_slot = _pick()
    total = _sum(chosen_by_slot)

    if total["carbs"] < config.CARBS_MIN_G:
        chosen_by_slot, swaps = _greedy_fix(chosen_by_slot, "carbs", config.CARBS_MIN_G)
        _print_greedy_fix(f"↻ greedy fix W ({total['carbs']:.0f}→{config.CARBS_MIN_G}g):", swaps)
        total = _sum(chosen_by_slot)

    if total["protein"] < config.DAILY_MIN_PROTEIN:
        chosen_by_slot, swaps = _greedy_fix(
            chosen_by_slot, "protein", config.DAILY_MIN_PROTEIN,
            protect={"carbs": config.CARBS_MIN_G},
        )
        _print_greedy_fix(f"↻ greedy fix B ({total['protein']:.0f}→{config.DAILY_MIN_PROTEIN}g):", swaps)
        total = _sum(chosen_by_slot)

    if total["fat"] > config.FAT_SOFT_G:
        chosen_by_slot, swaps = _greedy_fix(
            chosen_by_slot, "fat", config.FAT_SOFT_G, minimize=True,
            protect={
                "carbs":    config.CARBS_MIN_G,
                "protein":  config.DAILY_MIN_PROTEIN,
                "calories": config.DAILY_TARGETS["calories"],
            },
        )
        if swaps:
            _print_greedy_fix(f"↻ greedy fix T ({total['fat']:.0f}→{config.FAT_SOFT_G}g):", swaps)
        total = _sum(chosen_by_slot)

    for slot, best in chosen_by_slot:
        print_slot_selection(slot, best)

    t = config.DAILY_TARGETS
    min_p = config.DAILY_MIN_PROTEIN
    fat = total["fat"]
    pstatus = "OK" if total["protein"] >= min_p else f"NIEDOBÓR ({min_p - total['protein']:.0f}g)"
    wstatus = "OK" if total["carbs"]   >= config.CARBS_MIN_G else f"NIEDOBÓR ({config.CARBS_MIN_G - total['carbs']:.0f}g)"
    if fat > config.FAT_HARD_G:
        fstatus = f"⚠ PRZEKROCZONO ({fat - config.FAT_HARD_G:.0f}g ponad limit {config.FAT_HARD_G}g)"
    elif fat > config.FAT_SOFT_G:
        fstatus = f"przekroczono ({fat - config.FAT_SOFT_G:.0f}g ponad {config.FAT_SOFT_G}g)"
    else:
        fstatus = "OK"

    _print_daily_summary(total, pstatus, wstatus, fstatus)

    if not apply:
        return 0

    if not yes:
        confirm = input(f"\n  Zapisać wybór dla {day}? [t/N]: ").strip().lower()
        if confirm != "t":
            _p("  Pominięto.")
            return 0

    changed = 0
    errors = 0
    for slot, meal in chosen_by_slot:
        if meal.diet_calories_meal_id == slot.current_diet_calories_meal_id:
            _p(f"  [{slot.category}] bez zmian")
            continue
        try:
            await client.save_meal_selection(
                slot.order_id, slot.delivery_id,
                slot.delivery_meal_id, meal.diet_calories_meal_id,
            )
            _pm(f"  [{escape(slot.category)}] [green]✓ zapisano[/green] → {meal.name[:55]}")
            changed += 1
        except (ApiError, PlaywrightError) as e:
            _pm(f"  [{escape(slot.category)}] [red]✗ błąd zapisu:[/red] {e}")
            _log.print_exception()
            errors += 1

    if changed:
        _p(f"  Zmieniono {changed}/{len(chosen_by_slot)} posiłków.")
    return errors


async def run(days: int | None, apply: bool, yes: bool, review: bool = False) -> None:
    async with async_playwright() as p:
        client = await DietlyClient.login(p)
        _con.print(f"[green]✓[/green] Zalogowano jako [bold]{escape(config.EMAIL)}[/bold]")
        try:
            order_ids = await client.get_active_order_ids()
            if config.MY_ORDER_ID in order_ids:
                order = await client.get_order(config.MY_ORDER_ID)
                order_end = order.get("dateTo", "?")
                _con.print(f"  Zamówienie {config.MY_ORDER_ID} aktywne do {order_end}")

            total_errors = 0

            if days != 0:
                deliveries = await client.get_upcoming_deliveries(days=days)
                if not deliveries:
                    _p(f"Brak dostaw w ciągu {days} dni." if days is not None else "Brak przyszłych dostaw w zamówieniu.")
                else:
                    _p(f"Znaleziono {len(deliveries)} dostaw.")
                    if apply:
                        mode = "automatycznie" if yes else "z potwierdzeniem każdego dnia"
                        _p(f"Tryb zapisu ({mode}).\n")
                    else:
                        _p("Tryb podglądu — dodaj --apply żeby zapisać.\n")

                    for delivery in deliveries:
                        try:
                            total_errors += await process_delivery(client, delivery, apply=apply, yes=yes)
                        except (ApiError, PlaywrightError) as e:
                            _p(f"  ✗ błąd dostawy {delivery.get('date', '?')}: {e}")
                            _log.print_exception()
                            total_errors += 1

            if review and apply:
                for oid in order_ids:
                    try:
                        rated = await client.submit_order_review(oid)
                        if rated:
                            _pm(f"[green]✓ Ocena 5/5 wystawiona dla zamówienia {oid}[/green]")
                        else:
                            _p(f"  Zamówienie {oid} — ocena już wystawiona, pominięto.")
                    except (ApiError, PlaywrightError) as e:
                        _pm(f"  [red]✗ błąd oceny zamówienia {oid}:[/red] {e}")
                        _log.print_exception()
                        total_errors += 1

            _p(f"\nLog zapisany: {_log_file}")
            if total_errors:
                _p(f"BŁĘDY: {total_errors} operacji nie powiodło się.")
                sys.exit(1)
        finally:
            await client.close()
            if _log_fh:
                _log_fh.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--days", type=int, default=3,
                       help="Liczba najbliższych dni (domyślnie 3, musi być > 0)")
    scope.add_argument("--all", action="store_true",
                       help="Do końca aktywnego zamówienia (wszystkie przyszłe dostawy)")
    parser.add_argument("--apply", action="store_true",
                        help="Zapisz wybór w panelu")
    parser.add_argument("--yes", action="store_true",
                        help="Bez pytania o potwierdzenie każdego dnia (wymaga --apply)")
    parser.add_argument("--review", action="store_true",
                        help="Wystaw publiczną ocenę 5/5 zamówienia (wymaga --apply)")
    args = parser.parse_args()

    if args.days < 0:
        parser.error("--days musi być >= 0 (0 = tylko ocena zamówienia, bez przetwarzania dostaw)")
    if args.days == 0 and not args.review:
        parser.error("--days 0 wymaga --review")
    if args.yes and not args.apply:
        parser.error("--yes wymaga --apply")
    if args.review and not args.apply:
        parser.error("--review wymaga --apply")

    _setup_output()
    days = None if args.all else args.days
    asyncio.run(run(days, args.apply, args.yes, args.review))
