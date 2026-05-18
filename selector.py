"""
Logika wyboru posiłków na podstawie makroskładników.
Cel: budowa masy mięśniowej.

Zasady scoringu:
  1. Białko >= 1.8g/kg masy ciała dziennie (twardy próg — kara za niedobór)
  2. Minimalizuj tłuszcz
  3. Maksymalizuj węglowodany
  4. Maksymalizuj kalorie
  5. Bonus za warzywa i zdrowe składniki
"""

from dataclasses import dataclass, field
from typing import Optional
import config

# Składniki sugerujące wartościowe / warzywne dania
HEALTHY_KEYWORDS = {
    "szpinak", "brokuł", "brokuły", "marchew", "cukinia", "dynia", "jarmuż",
    "rukola", "sałata", "pomidor", "ogórek", "papryka", "burak", "bób",
    "ciecierzyca", "soczewica", "kasza", "quinoa", "owies", "owsianka",
    "ryż brązowy", "bataty", "słodki ziemniak", "łosoś", "tuńczyk",
    "awokado", "oliwa", "siemię", "pestki", "orzechy", "jogurt naturalny",
}


@dataclass
class Meal:
    id: str
    name: str
    category: str           # np. "Śniadanie", "Obiad", "Kolacja"
    calories: float
    protein: float          # g
    carbs: float            # g
    fat: float              # g
    ingredients: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    diet_calories_meal_id: int = 0   # używane w PUT /switch


def _healthy_bonus(meal: Meal) -> float:
    """Zwraca 0–1 na podstawie obecności zdrowych składników."""
    if not meal.ingredients:
        return 0.0
    text = meal.ingredients.lower()
    hits = sum(1 for kw in HEALTHY_KEYWORDS if kw in text)
    return min(hits / 3, 1.0)  # nasycenie przy 3+ trafień


def _quality_score(meal: Meal, weights: dict | None = None) -> float:
    n = config.MEALS_PER_DAY
    t = config.DAILY_TARGETS
    w = weights if weights is not None else config.SCORE_WEIGHTS

    carbs_score   = meal.carbs    / (t["carbs"]               / n)
    protein_score = meal.protein  / (config.DAILY_MIN_PROTEIN / n)
    cal_score     = meal.calories / (t["calories"]            / n)
    healthy       = _healthy_bonus(meal)

    return (
        w["carbs"]    * carbs_score
        + w["protein"]  * protein_score
        + w["healthy"]  * healthy
        + w["calories"] * cal_score
    )


def score_meal(meal: Meal) -> float:
    return _quality_score(meal)


def _is_blocked(meal: Meal) -> bool:
    name = meal.name.lower()
    return any(kw in name for kw in config.BLOCKED_KEYWORDS)


def select_best_meal(meals: list[Meal], weights: dict | None = None) -> Optional[Meal]:
    if not meals:
        return None
    allowed = [m for m in meals if not _is_blocked(m)]
    pool = allowed if allowed else meals
    return max(pool, key=lambda m: _quality_score(m, weights))


def best_for_macro(meals: list[Meal], macro: str, minimize: bool = False) -> Optional[Meal]:
    """Posiłek z najwyższą (lub najniższą) wartością danego makro (po odfiltrowaniu blokowanych)."""
    if not meals:
        return None
    allowed = [m for m in meals if not _is_blocked(m)]
    pool = allowed if allowed else meals
    key = lambda m: getattr(m, macro)
    return min(pool, key=key) if minimize else max(pool, key=key)
