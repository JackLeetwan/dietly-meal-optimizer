import pytest
from selector import Meal, select_best_meal, best_for_macro


def meal(name, *, protein=30.0, carbs=50.0, fat=20.0, calories=500.0):
    return Meal(
        id="1", name=name, category="X",
        calories=calories, protein=protein, carbs=carbs, fat=fat,
    )


BLOCKED = [
    meal("Koktajl truskawkowy"),
    meal("Zupa pomidorowa"),
    meal("Smoothie bananowe"),
]

MIXED = [
    meal("Koktajl truskawkowy", carbs=20.0),
    meal("Kurczak z ryżem", protein=50.0, carbs=80.0),
    meal("Zupa jarzynowa", carbs=15.0),
    meal("Makaron z warzywami", carbs=90.0),
]


class TestSelectBestMeal:
    def test_empty_list_returns_none(self):
        assert select_best_meal([]) is None

    def test_all_blocked_returns_none(self):
        assert select_best_meal(BLOCKED) is None

    def test_mixed_returns_only_from_allowed(self):
        result = select_best_meal(MIXED)
        assert result is not None
        assert "koktajl" not in result.name.lower()
        assert "zupa" not in result.name.lower()

    def test_picks_highest_scoring_among_allowed(self):
        # Jeden posiłek dominuje we wszystkich makrach → musi wygrać niezależnie od wag
        meals = [
            meal("Zupa warzywna", protein=5.0, carbs=10.0, calories=100.0),
            meal("Ryż z kurczakiem", protein=60.0, carbs=100.0, calories=700.0),
            meal("Smoothie owocowe", protein=50.0, carbs=90.0, calories=600.0),
        ]
        result = select_best_meal(meals)
        assert result.name == "Ryż z kurczakiem"

    def test_single_allowed_meal_is_chosen(self):
        meals = [meal("Koktajl"), meal("Kotlet schabowy", carbs=60.0)]
        result = select_best_meal(meals)
        assert result.name == "Kotlet schabowy"


class TestBestForMacro:
    def test_empty_list_returns_none(self):
        assert best_for_macro([], "protein") is None

    def test_all_blocked_returns_none(self):
        assert best_for_macro(BLOCKED, "carbs") is None

    def test_maximize_returns_highest_from_allowed(self):
        result = best_for_macro(MIXED, "carbs")
        assert result is not None
        assert result.name == "Makaron z warzywami"

    def test_minimize_returns_lowest_from_allowed(self):
        result = best_for_macro(MIXED, "carbs", minimize=True)
        assert result is not None
        # Kurczak z ryżem ma carbs=80, Makaron=90 — najniższy dozwolony to Kurczak
        assert result.name == "Kurczak z ryżem"

    def test_blocked_meals_excluded_from_maximize(self):
        # Koktajl ma carbs=20, Zupa carbs=15 — oba zablokowane
        # Makaron (90) > Kurczak (80) — powinien wybrać Makaron
        result = best_for_macro(MIXED, "carbs")
        assert result.name == "Makaron z warzywami"
