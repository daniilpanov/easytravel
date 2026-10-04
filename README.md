# Ostrovok Hotel Search — полностью без ручных файлов

Скрипт `ostrovok_search.py` + плагин `.opencode/plugins/ostrovok-hotels.js`.
Только стандартная библиотека Python 3. Никакого редактирования JSON/кода вручную —
всё через флаги или через tools.

## Tools (opencode, без файлов)

- `ostrovok_smart_search` — ГЛАВНЫЙ. `arrival/departure` + (`area` | `hotel+path` | `preset`) + `meals/maxTotal/adults/limit/split/alfa/top`.
  `area`: одна (`сиде`) или СРАЗУ НЕСКОЛЬКО через запятую (`сиде, кемер, анталия`). `split=true` — при rates=null сам проверит две половины. `alfa=true` — цена с кэшбэком 10%.
- `ostrovok_resolve_region(pathOrUrl)` — region_id по ссылке/пути отеля.
- `ostrovok_discover(area, limit)` — список отелей ОДНОГО или НЕСКОЛЬКИХ районов без тарифов (`limit` — на каждый район).
- `ostrovok_nearby(pathOrUrl, limit)` — соседи отеля без тарифов.
- `ostrovok_preset(action=list|add|remove)` — пресет без редактора.
- `ostrovok_search` — legacy-алиас, работает как раньше.

## CLI без файлов

```bash
cd ostrovok-hotel-search
# discover / nearby — без дат и тарифов
python3 ostrovok_search.py --discover сиде --limit 10
python3 ostrovok_search.py --nearby turkey/side/mid10216682/side_win_otel_spa_all_inclusive/ --limit 8
python3 ostrovok_search.py --resolve turkey/kemer/mid7354304/ozkaymak_marina_hotel_3/

# умный поиск по району сразу с тарифами (preset не нужен)
python3 ostrovok_search.py --arrival 2026-10-05 --departure 2026-10-11 --area сиде --limit 8 \
  --meals half-board,all-inclusive --max-total 110000 --split --alfa

# СРАЗУ НЕСКОЛЬКО ЛОКАЦИЙ (limit — на каждый район, дедуп по mid)
python3 ostrovok_search.py --discover "сиде, кемер" --limit 5
python3 ostrovok_search.py --arrival 2026-10-05 --departure 2026-10-11 --area "сиде, кемер" --limit 5 --split --alfa
python3 ostrovok_search.py --arrival 2026-10-05 --departure 2026-10-11 --area сиде --area кемер --limit 5

# один отель: path достаточно, region сам
python3 ostrovok_search.py --arrival 2026-10-05 --departure 2026-10-19 \
  --hotel side_win_otel_spa_all_inclusive --path turkey/side/mid10216682/side_win_otel_spa_all_inclusive/

# пресет без редактора
python3 ostrovok_search.py --preset-list
python3 ostrovok_search.py --preset-list кемер
python3 ostrovok_search.py --preset-add turkey/side/mid10216682/side_win_otel_spa_all_inclusive/ --add-name "Art Poseidon Side 4*"
python3 ostrovok_search.py --preset-remove side_win_otel_spa_all_inclusive
```

## Параметры тарифов

| Флаг | Что делает |
|---|---|
| `--arrival / --departure` | `YYYY-MM-DD`. Ночной прилет 06.10 в 01:00 = заезд с 05.10 |
| `--area` | Одна или СРАЗУ НЕСКОЛЬКО локаций: `--area сиде`, `--area "сиде, кемер"`, `--area сиде --area кемер`. Районы: сиде/кемер/анталия/лара/кунду/чолаклы. Discover + тарифы в один проход, preset-файл не нужен |
| `--hotel / --path / --region` | Слаг + path после `/hotel/`. Если `--region` нет — авто-резолв по `--path`, эвристика по path как fallback |
| `--preset` | По умолч. `hotels.json` рядом со скриптом. Можно не указывать вообще |
| `--limit` | Сколько отелей на КАЖДЫЙ район для `--discover/--nearby/--area` (по умолч. 12). Напр. `--area "сиде, кемер" --limit 5` = до 10 отелей |
| `--meals` | `breakfast,half-board,half-board-dinner,half-board-lunch,full-board,soft-all-inclusive,all-inclusive,ultra-all-inclusive,nomeal`. Понимает UI-имена и точки |
| `--max-total` | Потолок итого в рублях, `0` = без лимита |
| `--online-only / --no-online-only` | По умолч. вкл — только `now by credit_card/sbp` (Мир/Visa РФ). Выкл — показать и `в отеле` (там TRY, Мир не сработает) |
| `--split` | При `rates=null` авто-проверить `arrival/mid` + `mid/departure` и показать лучшее |
| `--alfa` | Кэшбэк Alfa Travel 10% + ссылка `https://travel.alfabank.ru/` (провайдер Ostrovok) |
| `--top` | Сколько лучших тарифов на отель (по умолч. 3) |
| `--json-out` | Сохранить сырой результат |

## Районы и region_id

Анталия-город `481`, Кунду `6054866`, Лара `6054878` (listing `turkey/antalya/`),
Кемер `8281`, Сиде `4931`, Сиде/Кумкой исключение `4218` (Art Poseidon).
Резолв: первое `regionId` с повтором ×3 в HTML страницы отеля.

## Как читать вывод

- `rates=null` — нет сквозной доступности. С `--split` сразу видишь половины (напр. 05–08 пусто, 08–11 AI 22 556 ₽).
- `ИТОГ: N отелей, в фильтр прошло M` — сводка в конце всегда.
- `Alfa -10%: ~X` — эффективная цена с кэшбэком.
- `Ссылка Островок` — с датами/гостями/meal_types. `Alfa Travel` — тот же отель/даты искать на `travel.alfabank.ru`.

## Оплата российской картой

- Бери `Оплата сейчас в рублях` (`payment type: now`).
- Мир / Visa / MC РФ + СБП проходят.
- Не бери `оплата в отеле` — там TRY, Мир не примут.
- В коммент к брони: `late arrival 01:00 06.10, room needed from 05.10`.
- Checkout обычно 12:00.
