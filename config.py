import os
import stat
from pathlib import Path
from dotenv import load_dotenv

_env = Path(".env")
if _env.exists():
    _mode = _env.stat().st_mode & 0o777
    if _mode & (stat.S_IRWXG | stat.S_IRWXO):
        _env.chmod(0o600)

load_dotenv()

EMAIL    = os.getenv("OPTIDIET_EMAIL")
PASSWORD = os.getenv("OPTIDIET_PASSWORD")

def _require_int(name: str, min_val: int = 1) -> int:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Brak {name} w pliku .env")
    result = int(v)
    if result < min_val:
        raise RuntimeError(f"{name}={result} musi być >= {min_val}")
    return result

def _require_float(name: str, min_val: float = 0.0) -> float:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Brak {name} w pliku .env")
    result = float(v)
    if result < min_val:
        raise RuntimeError(f"{name}={result} musi być >= {min_val}")
    return result

def _optional_int(name: str) -> int | None:
    v = (os.getenv(name) or "").strip()
    if not v or v.startswith("#"):
        return None
    try:
        return int(v)
    except ValueError:
        raise RuntimeError(f"{name}={v!r} — oczekiwano liczby całkowitej lub pustej wartości")

MY_ORDER_ID          = _optional_int("OPTIDIET_ORDER_ID")
BODY_WEIGHT_KG       = _require_float("OPTIDIET_BODY_WEIGHT_KG", min_val=1.0)
PROTEIN_MIN_G_PER_KG = _require_float("OPTIDIET_PROTEIN_MIN_G_PER_KG", min_val=0.1)

DAILY_MIN_PROTEIN = round(BODY_WEIGHT_KG * PROTEIN_MIN_G_PER_KG)
if DAILY_MIN_PROTEIN <= 0:
    raise RuntimeError("DAILY_MIN_PROTEIN <= 0: sprawdź OPTIDIET_BODY_WEIGHT_KG i OPTIDIET_PROTEIN_MIN_G_PER_KG")

MEALS_PER_DAY = 5  # liczba slotów w dostawie — stała serwisu

# Cele dzienne — używane do normalizacji w scoringu
DAILY_TARGETS = {
    "calories": _require_int("OPTIDIET_CALORIES_TARGET"),
    "protein":  DAILY_MIN_PROTEIN,
    "carbs":    _require_int("OPTIDIET_CARBS_TARGET"),
}

# Wagi scoringu — tłuszcz nie jest składnikiem scoringu, ma osobne limity
SCORE_WEIGHTS = {
    "carbs":    0.50,
    "protein":  0.15,
    "healthy":  0.05,
    "calories": 0.30,
}

# Progi greedy fix — wyzwalają podmianę posiłku jeśli cel nie osiągnięty
CARBS_MIN_G  = _require_int("OPTIDIET_CARBS_MIN_G")   # twarde minimum węglowodanów
# DAILY_MIN_PROTEIN pełni tę samą rolę dla białka (już zdefiniowane wyżej)
FAT_SOFT_G   = _require_int("OPTIDIET_FAT_TARGET")     # powyżej: greedy fix próbuje zejść niżej
FAT_HARD_G   = FAT_SOFT_G + 30                         # powyżej: mocne ostrzeżenie w logu

# Posiłki z tymi słowami w nazwie są odrzucane przed scoringiem (płynne/zupowe dania)
BLOCKED_KEYWORDS = {
    "zupa", "krem z", "krem ", "rosół", "bulion",
    "smoothie", "koktajl", "shake", "napój",
    "herbata", "matcha", "sok ", "latte", "cappuccino",
}
