PY   = .venv/bin/python

.PHONY: sprawdź wszystko oceń-posiłki oceń-zamówienia

sprawdź:
	read -r -p "Ile dni sprawdzić? [3] " days; \
	days=$${days:-3}; \
	$(PY) main.py --days $$days; \
	read -r -p "Czy zatwierdzić zmiany? [t/N] " ans; \
	case "$$ans" in [tT]*) $(PY) main.py --days $$days --apply;; *) echo "Anulowano.";; esac

wszystko:
	$(PY) main.py --all --apply --yes

oceń-posiłki:
	$(PY) rate_meals.py

oceń-zamówienia:
	$(PY) main.py --days 0 --apply --review
