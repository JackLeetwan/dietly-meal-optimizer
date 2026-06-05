import os, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

# Dummy values so config.py doesn't fail-fast during unit tests (no .env needed)
_DEFAULTS = {
    "OPTIDIET_EMAIL":                "test@example.com",
    "OPTIDIET_PASSWORD":             "test",
    "OPTIDIET_ORDER_ID":             "1",
    "OPTIDIET_BODY_WEIGHT_KG":       "80",
    "OPTIDIET_PROTEIN_MIN_G_PER_KG": "1.8",
    "OPTIDIET_CALORIES_TARGET":      "3000",
    "OPTIDIET_CARBS_MIN_G":          "300",
    "OPTIDIET_CARBS_TARGET":         "350",
    "OPTIDIET_FAT_TARGET":           "85",
}
for k, v in _DEFAULTS.items():
    os.environ.setdefault(k, v)
