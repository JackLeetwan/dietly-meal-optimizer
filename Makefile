PY   = .venv/bin/python
DAYS ?= 3

.PHONY: sprawdź zastosuj wszystko tydzień miesiąc oceń-posiłki oceń-zamówienia

sprawdź:
	$(PY) main.py --days $(DAYS)

tydzień:
	$(PY) main.py --days 7

miesiąc:
	$(PY) main.py --all

zastosuj:
	$(PY) main.py --days $(DAYS) --apply

wszystko:
	$(PY) main.py --all --apply --yes

oceń-posiłki:
	$(PY) rate_meals.py

oceń-zamówienia:
	$(PY) main.py --days 0 --apply --review
