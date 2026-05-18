"""
Ocenia wszystkie dostarczone posiłki ze wszystkich diet na koncie — maksymalna liczba gwiazdek.
Uruchom: python rate_meals.py
"""

import asyncio
import sys
from datetime import date
from playwright.async_api import async_playwright
from rich.console import Console
from rich.markup import escape

from dietly_api import DietlyClient, ApiError
from playwright.async_api import Error as PlaywrightError
import config

_MAX_SCORE = 1  # API: 0 = negatywna, 1 = pozytywna

con = Console(highlight=False)


def _extract_menu_meal_id(item: dict) -> int | None:
    mid = item.get("menuMealId") or (item.get("menuMealDetails") or {}).get("menuMealId")
    return int(mid) if mid else None


async def run() -> None:
    today = date.today()
    async with async_playwright() as p:
        client = await DietlyClient.login(p)
        con.print(f"[green]✓[/green] Zalogowano jako [bold]{escape(config.EMAIL)}[/bold]")
        try:
            order_ids = await client.get_active_order_ids()
            rated = skipped = errors = 0

            for oid in order_ids:
                order = await client.get_order(oid)
                past = [d for d in order.get("deliveries", [])
                        if date.fromisoformat(d["date"]) <= today]
                for delivery in past:
                    did = delivery["deliveryId"]
                    day = delivery["date"]
                    try:
                        menu = await client.get_delivery_menu(did)
                    except (ApiError, PlaywrightError) as e:
                        con.print(f"  [red]✗[/red]  {day}: {e}")
                        con.print_exception()
                        errors += 1
                        continue

                    items = [i for i in menu.get("deliveryMenuMeal", []) if _extract_menu_meal_id(i)]
                    if not items:
                        continue

                    con.rule(f"[bold]{day}[/bold]", style="dim")

                    for item in items:
                        mid = _extract_menu_meal_id(item)
                        name = item.get("menuMealName") or item.get("mealName") or f"#{mid}"
                        try:
                            ok = await client.rate_meal(mid, _MAX_SCORE)
                            if ok:
                                con.print(f"  [yellow]★[/yellow]  {escape(name)}")
                                rated += 1
                            else:
                                con.print(f"  [dim]–  {escape(name)}[/dim]")
                                skipped += 1
                        except (ApiError, PlaywrightError) as e:
                            con.print(f"  [red]✗  {escape(name)}: {e}[/red]")
                            con.print_exception()
                            errors += 1

            con.print()
            con.rule(style="dim")
            con.print(
                f"[bold green]Oceniono: {rated}[/bold green]   "
                f"[dim]Pominięto: {skipped}[/dim]   "
                f"{'[bold red]' if errors else '[dim]'}Błędy: {errors}{'[/bold red]' if errors else '[/dim]'}"
            )
            if errors:
                sys.exit(1)
        finally:
            await client.close()


if __name__ == "__main__":
    asyncio.run(run())
