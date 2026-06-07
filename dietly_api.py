"""
Klient HTTP dla API Dietly.
Używa Playwright APIRequestContext — obsługuje cookies automatycznie po logowaniu.

Odkryte endpointy:
  GET  /company/general/menus/delivery/{deliveryId}/new
       → aktualnie przypisane posiłki + metadane slotów (deliveryMealId, switchable)
  GET  /company/customer/order/{orderId}/deliveries/{deliveryId}/delivery-meals/{deliveryMealId}/switch
       → lista dostępnych alternatyw dla slotu
  PUT  /company/customer/order/{orderId}/deliveries/{deliveryId}/delivery-meals/{deliveryMealId}/switch
       ?amount=1&dietCaloriesMealId={targetId}
       → zmiana posiłku na wybraną alternatywę
"""

import asyncio
import json as _json
from datetime import date, timedelta
from dataclasses import dataclass
from playwright.async_api import Playwright, APIRequestContext, Error as PlaywrightError

import config
from selector import Meal

_RETRIES = 3
_BACKOFF  = 1.5   # sekundy; mnożone przez 2^attempt
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: str):
        super().__init__(f"{method} {path} → HTTP {status}: {body}")
        self.status = status

API = "https://panel.dietly.pl/api"
_H = {
    "company-id": "optidiet",
    "x-launcher-type": "BROWSER_PANEL",
    "accept": "application/json",
}


@dataclass
class MealSlot:
    """Jeden slot posiłkowy w danej dostawie (np. Śniadanie, Obiad)."""
    order_id: int
    delivery_id: int
    delivery_meal_id: int
    category: str
    options: list[Meal]        # dostępne alternatywy (z /switch)
    current_diet_calories_meal_id: int


class DietlyClient:
    def __init__(self, ctx: APIRequestContext):
        self._ctx = ctx

    @classmethod
    async def login(cls, playwright: Playwright) -> "DietlyClient":
        if not config.EMAIL or not config.PASSWORD:
            raise RuntimeError("Brak EMAIL lub PASSWORD w pliku .env")
        ctx = await playwright.request.new_context()
        for attempt in range(_RETRIES):
            try:
                r = await ctx.post(
                    f"{API}/auth/login",
                    form={"username": config.EMAIL, "password": config.PASSWORD},
                    headers=_H,
                    timeout=60000,
                )
                if r.ok:
                    return cls(ctx)
                if r.status not in _RETRYABLE or attempt == _RETRIES - 1:
                    raise RuntimeError(f"Logowanie nieudane: HTTP {r.status}")
            except RuntimeError:
                raise
            except PlaywrightError:
                if attempt == _RETRIES - 1:
                    raise
            await asyncio.sleep(_BACKOFF * (2 ** attempt))

    async def _request(self, method: str, path: str, **kwargs):
        url = f"{API}{path}"
        headers = kwargs.pop("headers", _H)
        for attempt in range(_RETRIES):
            try:
                r = await getattr(self._ctx, method)(url, headers=headers, timeout=60000, **kwargs)
                if r.ok:
                    return r
                if r.status not in _RETRYABLE or attempt == _RETRIES - 1:
                    raise ApiError(method.upper(), path, r.status, await r.text())
            except ApiError:
                raise
            except PlaywrightError:
                if attempt == _RETRIES - 1:
                    raise
            await asyncio.sleep(_BACKOFF * (2 ** attempt))

    async def _get(self, path: str):
        r = await self._request("get", path)
        return await r.json()

    async def _put(self, path: str, params: dict):
        r = await self._request("put", path, params=params)
        return await r.json() if r.status != 204 else None

    async def _post_json(self, path: str, payload: dict):
        r = await self._request(
            "post", path,
            headers={**_H, "content-type": "application/json"},
            data=_json.dumps(payload),
        )
        return await r.json() if r.status != 204 else None

    # --- Zamówienia ---

    async def get_active_order_ids(self) -> list[int]:
        return await self._get("/company/customer/order/active-ids")

    async def get_order(self, order_id: int) -> dict:
        return await self._get(f"/company/customer/order/{order_id}")

    async def get_upcoming_deliveries(self, days: int | None = 7) -> list[dict]:
        """Zwraca przyszłe dostawy. days=None oznacza do końca zamówienia (bez limitu)."""
        today = date.today()
        cutoff = today + timedelta(days=days) if days is not None else None
        order_ids = await self.get_active_order_ids()
        if config.MY_ORDER_ID:
            order_ids = [oid for oid in order_ids if oid == config.MY_ORDER_ID]
        else:
            target_cal = config.DAILY_TARGETS["calories"]
            matched = []
            for oid in order_ids:
                o = await self.get_order(oid)
                if o.get("diet", {}).get("calories") == target_cal:
                    matched.append((oid, o.get("dateFrom", "")))
            if not matched:
                raise RuntimeError(
                    f"Nie znaleziono aktywnego zamówienia z kalorycznością {target_cal} kcal — "
                    "ustaw OPTIDIET_ORDER_ID ręcznie w .env"
                )
            if len(matched) > 1:
                matched.sort(key=lambda x: x[1], reverse=True)
                ids_str = ", ".join(str(i) for i, _ in matched)
                import logging
                logging.getLogger(__name__).warning(
                    "Znaleziono %d zamówień z kalorycznością %d kcal (ID: %s) — "
                    "wybieram najnowsze (%d). Ustaw OPTIDIET_ORDER_ID żeby wskazać konkretne.",
                    len(matched), target_cal, ids_str, matched[0][0],
                )
            order_ids = [matched[0][0]]
        result = []
        for oid in order_ids:
            order = await self.get_order(oid)
            for d in order.get("deliveries", []):
                d_date = date.fromisoformat(d["date"])
                if today < d_date and (cutoff is None or d_date <= cutoff):
                    d["_orderId"] = oid
                    result.append(d)
        return sorted(result, key=lambda x: x["date"])

    # --- Menu i alternatywy ---

    async def get_delivery_menu(self, delivery_id: int) -> dict:
        return await self._get(f"/company/general/menus/delivery/{delivery_id}/new")

    async def get_switch_options(
        self, order_id: int, delivery_id: int, delivery_meal_id: int
    ) -> list[Meal]:
        """Pobiera dostępne alternatywy dla jednego slotu posiłkowego."""
        path = (f"/company/customer/order/{order_id}"
                f"/deliveries/{delivery_id}"
                f"/delivery-meals/{delivery_meal_id}/switch")
        data = await self._get(path)
        meals = []
        for option in data.get("mealChangeOptions", []):
            det = option["menuMealDetails"]
            n = det.get("nutrition") or {}
            ingredients = det.get("ingredients", [])
            if isinstance(ingredients, list):
                ingredients = ", ".join(i.get("name", "") for i in ingredients)
            meals.append(Meal(
                id=str(det["menuMealId"]),
                name=det["menuMealName"],
                category="",    # uzupełniane przez get_delivery_slots
                calories=float(n.get("calories") or 0),
                protein=float(n.get("protein") or 0),
                carbs=float(n.get("carbohydrate") or 0),
                fat=float(n.get("fat") or 0),
                ingredients=ingredients,
                tags=[det.get("thermo", "")],
                diet_calories_meal_id=int(det["dietCaloriesMealId"]),
            ))
        return meals

    async def get_delivery_slots(
        self, order_id: int, delivery_id: int
    ) -> tuple[list[MealSlot], str | None]:
        """
        Zwraca (slots, error_message).
        error_message jest ustawiony gdy dostawa jest zablokowana do zmian.
        """
        menu = await self.get_delivery_menu(delivery_id)
        slots = []
        for item in menu.get("deliveryMenuMeal", []):
            if not item.get("switchable"):
                continue
            dmid = item["deliveryMealId"]
            try:
                options = await self.get_switch_options(order_id, delivery_id, dmid)
            except ApiError as e:
                if e.status == 490:
                    return [], "zablokowana (za blisko daty dostawy)"
                raise
            for opt in options:
                opt.category = item["mealName"]
            slots.append(MealSlot(
                order_id=order_id,
                delivery_id=delivery_id,
                delivery_meal_id=dmid,
                category=item["mealName"],
                options=options,
                current_diet_calories_meal_id=item["dietCaloriesMealId"],
            ))
        return slots, None

    # --- Zapis wyboru ---

    async def save_meal_selection(
        self, order_id: int, delivery_id: int, delivery_meal_id: int,
        diet_calories_meal_id: int
    ):
        """Zapisuje wybór posiłku dla danego slotu."""
        path = (f"/company/customer/order/{order_id}"
                f"/deliveries/{delivery_id}"
                f"/delivery-meals/{delivery_meal_id}/switch")
        await self._put(path, {"amount": "1", "dietCaloriesMealId": str(diet_calories_meal_id)})

    # --- Ocenianie posiłków ---

    async def rate_meal(self, menu_meal_id: int, score: int = 1) -> bool:
        """Ocenia posiłek (score: 0 = negatywna, 1 = pozytywna). Zwraca True jeśli oceniono, False jeśli już oceniony lub niedostępny."""
        try:
            await self._post_json("/company/customer/review/", {
                "reviewId": {"menuMealId": menu_meal_id},
                "score": score,
                "text": "",
            })
            return True
        except ApiError as e:
            if e.status in (400, 409, 422):
                return False
            raise

    # --- Ocenianie zamówienia ---

    _REVIEW_TEXT = (
        "Jedzenie jest pyszne, wybór duży i zawsze wystarczający. "
        "Zazwyczaj żałuję, że muszę wybierać, bo chciałbym spróbować wszystkiego!"
    )

    async def submit_order_review(self, order_id: int) -> bool:
        """Wysyła publiczną ocenę 5/5 dla zamówienia (multipart).
        Zwraca True jeśli oceniono, False jeśli już oceniono."""
        order = await self.get_order(order_id)
        if order.get("feedback"):
            return False
        try:
            await self._request("post", "/company/customer/v2/feedback", multipart={
                "orderId":               str(order_id),
                "scoreAesthetics":       "5",
                "scoreDelivery":         "5",
                "scoreIngredientsQuality": "5",
                "scorePackaging":        "5",
                "scoreTaste":            "5",
                "scoreVariety":          "5",
                "text":                  self._REVIEW_TEXT,
                "visible":               "true",
            })
            return True
        except ApiError as e:
            if e.status in (400, 403, 409, 422):
                return False
            raise


    async def close(self):
        await self._ctx.dispose()
