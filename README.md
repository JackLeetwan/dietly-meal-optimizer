# Automatyczny wybór posiłków — OptiDiet

Skrypt loguje się do panelu OptiDiet i zamienia posiłki na nadchodzące dni tak, żeby trafić w Twoje cele: dużo białka, dużo węglowodanów, mało tłuszczu.

---

## Użycie

### Podgląd (nic nie zmienia)

```
make sprawdź
```

Pokazuje propozycje na najbliższe 3 dni. Żadnych zmian w panelu.

```
make sprawdź DAYS=7
```

To samo, ale na 7 dni.

---

### Zastosowanie zmian

```
make zastosuj
```

Pyta o potwierdzenie dla każdego dnia (`t` = tak, Enter = pomiń).

```
make zastosuj DAYS=2
```

Tylko najbliższe 2 dni.

```
make wszystko
```

Zamienia posiłki do końca całego zamówienia bez pytania. Używaj rzadko — np. po przedłużeniu diety.

---

### Ocenianie posiłków

```
make oceń-posiłki
```

Wystawia maksymalną (pozytywną) ocenę każdemu posiłkowi ze wszystkich minionych dostaw na koncie.

Skrypt iteruje po **wszystkich zamówieniach** na koncie (nie tylko tym z `OPTIDIET_ORDER_ID`) i ocenia każdy posiłek z dostaw, których data jest ≤ dzisiaj. Posiłki już wcześniej ocenione są pomijane.

Przydatne jednorazowo po założeniu konta lub po dłuższej przerwie — masowo uzupełnia oceny zamiast klikać ręcznie w panelu.

---

### Ocenianie zamówień

```
make oceń-zamówienia
```

Wysyła publiczną recenzję 5/5 dla każdego zamówienia na koncie (estetyka, dostawa, jakość składników, opakowanie, smak, różnorodność). Zamówienia już ocenione są pomijane.

Nie przetwarza żadnych dostaw — działa wyłącznie jako jednorazowe masowe wystawienie recenzji.

---

## Konfiguracja (.env)

Skopiuj `.env.example` do `.env` i uzupełnij:

```
OPTIDIET_EMAIL=twoj@email.pl
OPTIDIET_PASSWORD=twoje_haslo
OPTIDIET_ORDER_ID=
OPTIDIET_BODY_WEIGHT_KG=
OPTIDIET_PROTEIN_MIN_G_PER_KG=1.8
OPTIDIET_CALORIES_TARGET=
OPTIDIET_CARBS_MIN_G=
OPTIDIET_CARBS_TARGET=
OPTIDIET_FAT_TARGET=
```

| Zmienna | Co to znaczy |
|---|---|
| `OPTIDIET_EMAIL` / `PASSWORD` | Login i hasło do panelu OptiDiet |
| `OPTIDIET_ORDER_ID` | Numer zamówienia z panelu — skrypt dotyka tylko tego zamówienia |
| `OPTIDIET_BODY_WEIGHT_KG` | Masa ciała w kg |
| `OPTIDIET_PROTEIN_MIN_G_PER_KG` | Minimalne białko na kg masy ciała (np. `1.8` przy 78 kg = 140 g białka dziennie) |
| `OPTIDIET_CALORIES_TARGET` | Dzienny cel kalorii |
| `OPTIDIET_CARBS_MIN_G` | Twarde minimum węglowodanów (g) — skrypt podmieni posiłek jeśli suma spadnie poniżej |
| `OPTIDIET_CARBS_TARGET` | Optimum węglowodanów (g) — używane do scoringu, powinno być ≥ `CARBS_MIN_G` |
| `OPTIDIET_FAT_TARGET` | Maksimum tłuszczu (g) — skrypt próbuje zejść poniżej; twarde ostrzeżenie przy przekroczeniu o 30 g |

---

## Co oznaczają skróty w wynikach

`B` = białko, `W` = węglowodany, `T` = tłuszcz, `Kcal` = kalorie.
Liczba po `/` to Twój dzienny cel. `★` = wybrany posiłek.

| Symbol | Znaczenie |
|---|---|
| `⏸` | Dzień zablokowany — zbyt blisko dostawy, panel nie pozwala na zmiany |
| `bez zmian` | Posiłek był już optymalnie wybrany |
| `↻ greedy fix` | Skrypt podmienił jeden posiłek, żeby trafić w limit białka / węglowodanów / tłuszczu |

---

## Log zmian

Po każdym uruchomieniu tworzony jest plik w `logs/`, np. `logs/zmiany_20260521_083012.log`. Zawiera pełną historię bez kolorów — można otworzyć zwykłym edytorem.

---

## Częste problemy

**Błąd logowania** — sprawdź `OPTIDIET_PASSWORD` w `.env`.

**„Brak X w pliku .env"** — uzupełnij brakującą zmienną według tabeli powyżej.

**Zmiany nie są zapisywane** — uruchamiasz `make sprawdź` (tryb podglądu). Użyj `make zastosuj`.
