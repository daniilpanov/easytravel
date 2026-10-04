#!/usr/bin/env python3
"""Островок: поиск тарифов + discover + preset-менеджмент + split + Alfa.

Всё без ручной правки файлов — все действия через флаги (см. --help),
а из opencode — через tools в .opencode/plugins/ostrovok-hotels.js.

Примеры:
  # резолв region_id по URL/path
  python3 ostrovok_search.py --resolve turkey/kemer/mid7354304/ozkaymak_marina_hotel_3/
  # discover: что есть в Сиде (без тарифов)
  python3 ostrovok_search.py --discover сиде --limit 10
  # соседи отеля (без тарифов)
  python3 ostrovok_search.py --nearby turkey/side/mid10216682/side_win_otel_spa_all_inclusive/ --limit 8
  # умный поиск по району сразу с тарифами (без preset-файла)
  python3 ostrovok_search.py --arrival 2026-10-05 --departure 2026-10-11 --area сиде --limit 8 --meals half-board,all-inclusive --max-total 110000 --split --alfa
  # СРАЗУ НЕСКОЛЬКО ЛОКАЦИЙ: через запятую или повтором флага (limit — на каждый район)
  python3 ostrovok_search.py --arrival 2026-10-05 --departure 2026-10-11 --area "сиде, кемер" --limit 5 --split --alfa
  python3 ostrovok_search.py --discover "сиде, кемер, анталия" --limit 5
  # один отель: path достаточно, region резолвится сам
  python3 ostrovok_search.py --arrival 2026-10-05 --departure 2026-10-19 --hotel side_win_otel_spa_all_inclusive --path turkey/side/mid10216682/side_win_otel_spa_all_inclusive/
  # preset-менеджмент без редактора
  python3 ostrovok_search.py --preset-list
  python3 ostrovok_search.py --preset-list кемер
  python3 ostrovok_search.py --preset-add turkey/side/mid10216682/side_win_otel_spa_all_inclusive/ --add-name "Art Poseidon Side 4*"
  python3 ostrovok_search.py --preset-remove side_win_otel_spa_all_inclusive
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter

API = "https://ostrovok.ru/hotel/search/v1/site/hp/search"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PRESET = os.path.join(SCRIPT_DIR, "hotels.json")

MEAL_ALIASES = {
    "halfboard": "half-board",
    "halfBoard": "half-board",
    "fullboard": "full-board",
    "fullBoard": "full-board",
    "lunchanddinner": "half-board-dinner",
    "lunchAndDinner": "half-board-dinner",
    "allinclusive": "all-inclusive",
    "allInclusive": "all-inclusive",
    "ultraallinclusive": "ultra-all-inclusive",
    "ultraAllInclusive": "ultra-all-inclusive",
    "breakfast": "breakfast",
    "nomeal": "nomeal",
    "softallinclusive": "soft-all-inclusive",
}

GOOD_FOOD_DEFAULT = "half-board,full-board,half-board-dinner,all-inclusive,ultra-all-inclusive"

KNOWN_REGIONS = {
    481: "Анталия-город",
    6054866: "Кунду",
    6054878: "Лара",
    8281: "Кемер",
    4931: "Сиде",
    4218: "Сиде/Кумкой (Turquoise)",
}

# Человекопонятное имя района -> listing на Островке + дефолтный region
AREA_INDEX = {
    "сиде": {"listing": "turkey/side/", "region": 4931, "label": "Сиде"},
    "side": {"listing": "turkey/side/", "region": 4931, "label": "Сиде"},
    "кемер": {"listing": "turkey/kemer/", "region": 8281, "label": "Кемер"},
    "kemer": {"listing": "turkey/kemer/", "region": 8281, "label": "Кемер"},
    "анталия": {"listing": "turkey/antalya/", "region": 481, "label": "Анталия"},
    "antalya": {"listing": "turkey/antalya/", "region": 481, "label": "Анталия"},
    "лара": {"listing": "turkey/antalya/", "region": 481, "label": "Лара (Анталия)"},
    "lara": {"listing": "turkey/antalya/", "region": 481, "label": "Лара"},
    "кунду": {"listing": "turkey/kundu/", "region": 6054866, "label": "Кунду"},
    "kundu": {"listing": "turkey/kundu/", "region": 6054866, "label": "Кунду"},
    "чолаклы": {"listing": "turkey/side_colakli_neighborhood/", "region": 4931, "label": "Чолаклы"},
    "colakli": {"listing": "turkey/side_colakli_neighborhood/", "region": 4931, "label": "Чолаклы"},
    "эвренсеки": {"listing": "turkey/side_colakli_neighborhood/", "region": 4931, "label": "Эвренсеки/Чолаклы"},
    "evrenseki": {"listing": "turkey/side_colakli_neighborhood/", "region": 4931, "label": "Эвренсеки"},
    "коньяалты": {"listing": "turkey/antalya/", "region": 481, "label": "Коньяалты"},
    "коньяалти": {"listing": "turkey/antalya/", "region": 481, "label": "Коньяалты"},
}


def normalize_meals(raw: str) -> set:
    out = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip().strip(".")
        if not part:
            continue
        out.add(MEAL_ALIASES.get(part, part))
        for sub in part.split("."):
            sub = sub.strip()
            if sub:
                out.add(MEAL_ALIASES.get(sub, sub))
    return out


def fetch_html(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={
        "accept": "text/html,*/*",
        "accept-language": "ru-RU,ru;q=0.9",
        "Referer": "https://ostrovok.ru/",
        "User-Agent": "Mozilla/5.0",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="ignore")


def extract_region_candidates(html: str, top_n: int = 10) -> list:
    ids = re.findall(r'regionId\"?:\s*(\d+)', html)
    return Counter(ids).most_common(top_n)


def normalize_hotel_path(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    m = re.search(r"ostrovok\.ru/hotel/([^?#]+)", raw)
    if m:
        raw = m.group(1)
    raw = raw.lstrip("/")
    if raw.startswith("hotel/"):
        raw = raw[len("hotel/"):]
    if not raw.endswith("/"):
        raw += "/"
    return raw


def slug_from_path(path: str) -> str:
    path = normalize_hotel_path(path).strip("/")
    parts = path.split("/")
    return parts[-1] if parts else ""


def pretty_name(slug: str) -> str:
    return slug.replace("_", " ").title()


def resolve_region_id(path_or_url: str, timeout: int = 30) -> dict:
    path = normalize_hotel_path(path_or_url)
    if not path or "/" not in path:
        return {"ok": False, "error": "не похож на path отеля, пример: turkey/kemer/mid7354304/ozkaymak_marina_hotel_3/",
                "path": path}
    url = f"https://ostrovok.ru/hotel/{path}"
    html = fetch_html(url, timeout=timeout)
    cands = extract_region_candidates(html)
    if not cands:
        return {"ok": False, "error": "regionId не найден в HTML", "url": url, "path": path}
    best = None
    for rid, cnt in cands:
        if cnt >= 3:
            best = int(rid)
            break
    if best is None:
        best = int(cands[0][0])
    label = KNOWN_REGIONS.get(best, "")
    # пробуем вытащить реальное название из <title>
    title = ""
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()[:120]
    return {"ok": True, "path": path, "url": url, "hotel": slug_from_path(path),
            "title": title, "region_id": best, "label": label,
            "candidates": [{"region_id": int(r), "count": c,
                            "label": KNOWN_REGIONS.get(int(r), "")} for r, c in cands[:8]]}


def resolve_area_key(raw: str) -> dict | None:
    if not raw:
        return None
    key = raw.strip().lower()
    # убираем лишнее: "отели сиде", "side hotels"
    for k in sorted(AREA_INDEX.keys(), key=len, reverse=True):
        if k in key:
            return {"key": k, **AREA_INDEX[k]}
    return None


def parse_area_list(values) -> list:
    """Мультилокации: --area сиде --area кемер ИЛИ --area 'сиде, кемер; анталия'.
    Принимает str | list[str] | None, возвращает список сырых названий."""
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    out = []
    for v in values:
        for part in re.split(r"[,;+|/]+", v or ""):
            part = part.strip()
            if part:
                out.append(part)
    # убираем дубли, сохраняем порядок
    return list(dict.fromkeys(out))


def discover_areas(areas: list, limit: int = 12, timeout: int = 30) -> dict:
    """Discover сразу по нескольким районам. limit — на каждый район.
    Возвращает merged список с дедупом по mid."""
    if not areas:
        return {"ok": False, "error": "пустой список районов"}
    per_area = []
    merged = {}
    errors = []
    for a in areas:
        try:
            res = discover_area(a, limit=limit, timeout=timeout)
        except Exception as e:
            errors.append(f"{a}: {e}")
            continue
        if not res.get("ok"):
            errors.append(f"{a}: {res.get('error')}")
            continue
        per_area.append({"area": res["area"], "count": len(res["hotels"])})
        for h in res["hotels"]:
            m = re.search(r"(mid\d+)", h.get("path", ""))
            mid = m.group(1) if m else h.get("hotel")
            if mid not in merged:
                merged[h["hotel"]] = h
            # один и тот же mid в двух районах (side + чолаклы) — оставляем первый
    hotels = list(merged.values())
    ok = bool(hotels)
    out = {"ok": ok, "areas": per_area, "hotels": hotels,
           "total": len(hotels), "limit_per_area": limit}
    if errors:
        out["errors"] = errors
    if not ok:
        out["error"] = f"ничего не найдено: {'; '.join(errors)}" if errors else "ничего не найдено"
    return out


def discover_area(area: str, limit: int = 12, timeout: int = 30) -> dict:
    meta = resolve_area_key(area)
    if not meta:
        return {"ok": False, "error": f"район '{area}' не распознан. Попробуй: сиде, кемер, анталия, лара, кунду, чолаклы",
                "known": sorted(set(v["label"] for v in AREA_INDEX.values()))}
    url = f"https://ostrovok.ru/hotel/{meta['listing']}"
    html = fetch_html(url, timeout=timeout)
    paths = re.findall(r"/hotel/(turkey/[a-z_]+/mid\d+/[a-z0-9_]+/)", html)
    uniq = list(dict.fromkeys(paths))[: max(1, limit * 2)]
    # отфильтровываем дубли manavgat-алиасы: предпочитаем короткие side/kemer пути
    seen_mid = {}
    for p in uniq:
        m = re.search(r"(mid\d+)", p)
        mid = m.group(1) if m else p
        # предпочитаем path без manavgat
        if mid not in seen_mid or "manavgat" not in p and "manavgat" in seen_mid[mid]:
            seen_mid[mid] = p
    items = []
    for p in list(seen_mid.values())[:limit]:
        slug = slug_from_path(p)
        items.append({"hotel": slug, "path": p, "region_id": meta["region"],
                      "area": meta["label"], "name": f"{pretty_name(slug)}, {meta['label']}"})
    return {"ok": True, "area": meta["label"], "listing": meta["listing"],
            "url": url, "region_id": meta["region"], "hotels": items}


def nearby_hotels(hotel_path_or_url: str, limit: int = 8, timeout: int = 30) -> dict:
    path = normalize_hotel_path(hotel_path_or_url)
    low = path.lower()
    if "colakli" in low or "evrenseki" in low or "side_win" in low:
        area = "чолаклы"
    elif "kemer" in low:
        area = "кемер"
    elif "side" in low or "manavgat" in low:
        area = "сиде"
    elif "kundu" in low:
        area = "кунду"
    else:
        area = "анталия"
    res = discover_area(area, limit=limit + 5, timeout=timeout)
    if not res.get("ok"):
        return res
    me = slug_from_path(path)
    filtered = [h for h in res["hotels"] if h["hotel"] != me][:limit]
    res["hotels"] = filtered
    res["base_hotel"] = me
    res["base_path"] = path
    return res


# ---------- preset ----------
def load_preset(preset_path: str) -> list:
    p = preset_path or DEFAULT_PRESET
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("hotels", [])


def save_preset(preset_path: str, items: list) -> str:
    p = preset_path or DEFAULT_PRESET
    with open(p, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return p


def preset_add(preset_path: str, path_or_url: str, name: str = "") -> dict:
    items = load_preset(preset_path)
    slugs = {d.get("hotel") for d in items}
    res = resolve_region_id(path_or_url)
    if not res.get("ok"):
        return res
    slug = res["hotel"]
    if slug in slugs:
        return {"ok": False, "error": f"уже в пресете: {slug}", "hotel": slug}
    entry = {"name": name or res.get("title") or f"{pretty_name(slug)}, {res.get('label','')}",
             "hotel": slug, "region_id": res["region_id"], "path": res["path"]}
    items.append(entry)
    save_preset(preset_path, items)
    return {"ok": True, "added": entry, "total": len(items), "preset": preset_path or DEFAULT_PRESET}


def preset_remove(preset_path: str, slug: str) -> dict:
    items = load_preset(preset_path)
    n0 = len(items)
    items = [d for d in items if d.get("hotel") != slug]
    if len(items) == n0:
        return {"ok": False, "error": f"не найден в пресете: {slug}", "total": n0}
    save_preset(preset_path, items)
    return {"ok": True, "removed": slug, "total": len(items)}


# ---------- rates ----------
def fetch_rates(hotel: str, region_id: int, arrival: str, departure: str, adults: int = 2,
                currency: str = "RUB", timeout: int = 30) -> dict:
    body = {"arrival_date": arrival, "departure_date": departure, "hotel": hotel,
            "currency": currency, "lang": "ru", "region_id": int(region_id),
            "paxes": [{"adults": int(adults)}]}
    enc = urllib.parse.quote(json.dumps(body, separators=(",", ":")))
    url = f"{API}?body={enc}"
    req = urllib.request.Request(url, headers={
        "accept": "*/*", "accept-language": "ru-RU,ru;q=0.9",
        "Referer": "https://ostrovok.ru/", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def summarize_rate(r: dict) -> dict:
    pay_types = (r.get("payment_options") or {}).get("payment_types") or [{}]
    pay = pay_types[0]
    try:
        total = float(pay.get("show_amount") or 0)
    except (TypeError, ValueError):
        total = 0.0
    try:
        per_day = float(pay.get("average_show_price_per_day") or 0)
    except (TypeError, ValueError):
        per_day = 0.0
    allowed = (r.get("payment_options") or {}).get("allowed_payment_types") or []
    online = any(p.get("type") == "now" for p in allowed)
    return {"meal": tuple(r.get("meal") or []), "total": total, "per_day": per_day,
            "room": r.get("room_name") or "", "online_pay": online,
            "currency": pay.get("show_currency_code") or "RUB"}


def booking_link(base_path: str, arrival: str, departure: str, adults: int, meals_ui: str) -> str:
    def fmt(d):
        y, m, dd = d.split("-")
        return f"{dd}.{m}.{y}"
    link = f"https://ostrovok.ru/hotel/{base_path}?dates={fmt(arrival)}-{fmt(departure)}&guests={adults}"
    if meals_ui:
        link += f"&meal_types={meals_ui}"
    return link


def alfa_hint(total_rub: float) -> dict:
    cashback = round((total_rub or 0) * 0.10)
    return {"cashback_10pct_rub": cashback, "effective_rub": round((total_rub or 0) - cashback),
            "search": "https://travel.alfabank.ru/ (Отели -> тот же отель/даты; провайдер Ostrovok, оплата Альфа-картой)",
            "note": "Альфа Тревел показывает те же квоты Ostrovok (provider=ostrovok). Кэшбэк рублями на Альфа-карту, милями на Alfa Travel."}


def split_mid(arrival: str, departure: str) -> str:
    a = datetime.date.fromisoformat(arrival)
    d = datetime.date.fromisoformat(departure)
    mid = a + (d - a) / 2
    # округляем до целого дня
    delta = (d - a).days
    return (a + datetime.timedelta(days=delta // 2)).isoformat()


def check_target(t: dict, arrival: str, departure: str, adults: int, want: set,
                 max_total: float, online_only: bool, meals_ui: str, top: int,
                 do_split: bool, do_alfa: bool) -> dict:
    try:
        data = fetch_rates(t["hotel"], t["region_id"], arrival, departure, adults)
    except Exception as e:
        print(f"{t['name']}: ОШИБКА ЗАПРОСА: {e}")
        return {"hotel": t, "rates": [], "filtered": [], "error": str(e)}
    rates = data.get("rates")
    if not rates:
        line = (f"{t['name']}: rates=null — нет сквозной доступности "
                f"(попробуй split {arrival}/{split_mid(arrival, departure)}/{departure})")
        print(line)
        out = {"hotel": t, "rates": [], "filtered": [], "rates_null": True}
        if do_split:
            mid = split_mid(arrival, departure)
            for a, d in ((arrival, mid), (mid, departure)):
                try:
                    dd = fetch_rates(t["hotel"], t["region_id"], a, d, adults)
                    rr = dd.get("rates") or []
                    rows = [summarize_rate(r) for r in rr]
                    fl = [r for r in rows if (not want or set(r["meal"]) & want)]
                    if online_only:
                        fl = [r for r in fl if r["online_pay"]]
                    if max_total:
                        fl = [r for r in fl if r["total"] and r["total"] <= max_total]
                    fl.sort(key=lambda r: r["total"])
                    if fl:
                        print(f"   split {a}-{d}: {','.join(fl[0]['meal'])} {fl[0]['total']:.0f} RUB | {fl[0]['room'][:60]}")
                        out.setdefault("split", []).append({"dates": f"{a}-{d}", "best": fl[0], "count": len(fl)})
                    else:
                        print(f"   split {a}-{d}: тоже пусто/мимо фильтра")
                        out.setdefault("split", []).append({"dates": f"{a}-{d}", "best": None, "count": 0})
                except Exception as e:
                    print(f"   split {a}-{d}: ошибка {e}")
        return out
    rows = [summarize_rate(r) for r in rates]
    filt = [r for r in rows if (not want or set(r["meal"]) & want)]
    if online_only:
        filt = [r for r in filt if r["online_pay"]]
    if max_total:
        filt = [r for r in filt if r["total"] and r["total"] <= max_total]
    filt.sort(key=lambda r: r["total"])
    print(f"\n== {t['name']} ({t['hotel']}) — всего: {len(rows)}, под фильтр: {len(filt)} ==")
    if not filt:
        meals_found = sorted({m for r in rows for m in r["meal"]})
        print(f"   Нет под фильтр. Найденные meal: {meals_found}")
        cheapest = min(rows, key=lambda r: r["total"] or 1e18)
        print(f"   Самый дешевый: {cheapest['meal']} {cheapest['total']:.0f} RUB | {cheapest['room'][:70]}")
    for r in filt[:top]:
        line = f"   {','.join(r['meal'])} {r['total']:.0f} {r['currency']} (~{r['per_day']:.0f}/ночь) | {r['room'][:70]}"
        if do_alfa and r["total"]:
            h = alfa_hint(r["total"])
            line += f" | Alfa -10%: ~{h['effective_rub']:.0f}"
        print(line)
    if t.get("path"):
        print("   Островок: " + booking_link(t["path"], arrival, departure, adults, meals_ui))
        if do_alfa:
            print("   Alfa Travel: https://travel.alfabank.ru/ (тот же отель/даты, кэшбэк 10%)")
    return {"hotel": t, "rates": rows, "filtered": filt}


def main() -> int:
    ap = argparse.ArgumentParser(description="Островок без ручных файлов: discover/nearby/preset/split/alfa")
    # действия без дат
    ap.add_argument("--resolve", help="region_id по path/URL отеля")
    ap.add_argument("--discover", action="append", default=None,
                    help="район(ы): сиде/кемер/анталия/лара/кунду/чолаклы. Можно несколько: --discover сиде --discover кемер или --discover 'сиде, кемер' (список без тарифов)")
    ap.add_argument("--nearby", help="соседи отеля по path/URL (без тарифов)")
    ap.add_argument("--limit", type=int, default=12, help="сколько отелей на КАЖДЫЙ район для discover/nearby/area")
    ap.add_argument("--preset-list", nargs="?", const="", default=None, help="показать пресет, опц. фильтр-строка")
    ap.add_argument("--preset-add", help="добавить отель в пресет по path/URL (region сам). Пример: turkey/side/mid.../slug/")
    ap.add_argument("--add-name", default="", help="имя для --preset-add")
    ap.add_argument("--preset-remove", help="удалить слаг из пресета")
    ap.add_argument("--preset", default=None, help="preset-файл (по умолч. hotels.json рядом со скриптом)")
    # поиск тарифов
    ap.add_argument("--arrival", help="YYYY-MM-DD")
    ap.add_argument("--departure", help="YYYY-MM-DD")
    ap.add_argument("--area", action="append", default=None,
                    help="тарифы сразу по району(ам) без preset-файла. Можно несколько: --area сиде --area кемер или --area 'сиде, кемер'")
    ap.add_argument("--hotel", help="слаг отеля")
    ap.add_argument("--path", help="path после /hotel/ (для авто-region и ссылки)")
    ap.add_argument("--region", type=int, default=None, help="region_id (если нет --path, резолвится сам)")
    ap.add_argument("--no-auto-region", dest="auto_region", action="store_false", default=True)
    ap.add_argument("--adults", type=int, default=2)
    ap.add_argument("--meals", default=GOOD_FOOD_DEFAULT)
    ap.add_argument("--max-total", type=float, default=0)
    ap.add_argument("--online-only", action="store_true", default=True)
    ap.add_argument("--no-online-only", dest="online_only", action="store_false")
    ap.add_argument("--split", action="store_true", default=False, help="при rates=null авто-проверить две половины периода")
    ap.add_argument("--alfa", action="store_true", default=False, help="показать цену с кэшбэком Alfa Travel 10%% и ссылку")
    ap.add_argument("--top", type=int, default=3, help="сколько лучших тарифов показывать на отель")
    ap.add_argument("--json-out", help="сохранить результат в файл")
    args = ap.parse_args()
    preset_path = args.preset or DEFAULT_PRESET

    if args.resolve:
        try:
            res = resolve_region_id(args.resolve)
        except Exception as e:
            print(f"ОШИБКА РЕЗОЛВА: {e}", file=sys.stderr)
            return 1
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0

    if args.discover:
        areas = parse_area_list(args.discover)
        try:
            if len(areas) <= 1:
                res = discover_area(areas[0] if areas else "", limit=args.limit)
            else:
                res = discover_areas(areas, limit=args.limit)
        except Exception as e:
            print(f"ОШИБКА DISCOVER: {e}", file=sys.stderr)
            return 1
        print(json.dumps(res, ensure_ascii=False, indent=1))
        if res.get("ok"):
            n = len(res.get("hotels", []))
            alabel = res.get("area") or "+".join(a.get("area", "") for a in res.get("areas", []))
            print(f"\nНашел {n} ({alabel}): для тарифов запусти с --area '{','.join(areas)}' --arrival YYYY-MM-DD --departure YYYY-MM-DD")
        return 0

    if args.nearby:
        try:
            res = nearby_hotels(args.nearby, limit=args.limit)
        except Exception as e:
            print(f"ОШИБКА NEARBY: {e}", file=sys.stderr)
            return 1
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0

    if args.preset_list is not None:
        items = load_preset(preset_path)
        f = (args.preset_list or "").lower()
        shown = [d for d in items if not f or f in (d.get("name","")+d.get("hotel","")).lower()]
        print(f"Пресет {preset_path}: {len(shown)}/{len(items)}")
        for d in shown:
            print(f" - {d.get('name')} | {d.get('hotel')} | {d.get('region_id')} | {d.get('path')}")
        return 0

    if args.preset_add:
        try:
            res = preset_add(preset_path, args.preset_add, args.add_name)
        except Exception as e:
            print(f"ОШИБКА PRESET-ADD: {e}", file=sys.stderr)
            return 1
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0 if res.get("ok") else 1

    if args.preset_remove:
        res = preset_remove(preset_path, args.preset_remove)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0 if res.get("ok") else 1

    # дальше нужен поиск тарифов
    if not args.arrival or not args.departure:
        print("Нужно --arrival и --departure (или --resolve/--discover/--nearby/--preset-list/--preset-add)", file=sys.stderr)
        return 2

    want = normalize_meals(args.meals)
    meals_ui = (args.meals or "").replace(",", ".")

    targets = []
    if args.area:
        areas = parse_area_list(args.area)
        try:
            if len(areas) <= 1:
                res = discover_area(areas[0], limit=args.limit)
                hotels = res.get("hotels", []) if res.get("ok") else []
                alabel = res.get("area", areas[0] if areas else "")
                if not res.get("ok"):
                    print(json.dumps(res, ensure_ascii=False, indent=1))
                    return 1
            else:
                res = discover_areas(areas, limit=args.limit)
                if not res.get("ok"):
                    print(json.dumps(res, ensure_ascii=False, indent=1))
                    return 1
                hotels = res["hotels"]
                alabel = "+".join(a.get("area", "") for a in res.get("areas", [])) or ",".join(areas)
        except Exception as e:
            print(f"ОШИБКА AREA: {e}", file=sys.stderr)
            return 1
        print(f"Areas {alabel}: беру {len(hotels)} отелей в работу (без ручного preset, limit {args.limit} на район)")
        for it in hotels:
            targets.append({"name": f"{it['name']}", "hotel": it["hotel"],
                            "region_id": it["region_id"], "path": it["path"]})
    elif args.preset and os.path.exists(args.preset):
        items = load_preset(args.preset)
        for it in items:
            slug = it["hotel"]
            path = it.get("path", "") or args.path or ""
            rid = it.get("region_id", args.region)
            if not rid and args.auto_region and path:
                try:
                    res = resolve_region_id(path)
                    if res.get("ok"):
                        rid = res["region_id"]
                        print(f"{it.get('name') or slug}: авто-region -> {rid}")
                except Exception as e:
                    print(f"{it.get('name') or slug}: авто-резолв не удался: {e}")
            if not rid:
                print(f"{it.get('name') or slug}: нет region_id (подсказка: --resolve {path})")
                continue
            targets.append({"name": it.get("name") or slug, "hotel": slug,
                            "region_id": int(rid), "path": path})
    elif args.preset and not os.path.exists(args.preset):
        print(f"preset-файл не найден: {args.preset}", file=sys.stderr)
        return 2
    elif args.hotel:
        slug = args.hotel
        path = args.path or ""
        rid = args.region
        if not rid and args.auto_region and path:
            res = resolve_region_id(path)
            print(json.dumps(res, ensure_ascii=False, indent=1))
            if res.get("ok"):
                rid = res["region_id"]
        if not rid:
            # пробуем угадать регион по path
            if "kemer" in path:
                rid = 8281
            elif "kundu" in path:
                rid = 6054866
            elif "colakli" in path or "/side" in path:
                rid = 4931
            else:
                rid = 481
            print(f"region не задан — беру по эвристике path -> {rid} (проверь через --resolve)")
        targets.append({"name": slug, "hotel": slug, "region_id": int(rid), "path": path})
    else:
        # по умолчанию — дефолтный пресет, чтобы вообще не трогать файлы
        if os.path.exists(preset_path):
            print(f"preset не указан — беру дефолт {preset_path}")
            items = load_preset(preset_path)
            for it in items:
                targets.append({"name": it.get("name") or it["hotel"], "hotel": it["hotel"],
                                "region_id": int(it.get("region_id") or 481), "path": it.get("path", "")})
        else:
            print("Нужно --hotel или --area или --preset (файл не найден)", file=sys.stderr)
            return 2

    all_results = []
    for t in targets:
        r = check_target(t, args.arrival, args.departure, args.adults, want,
                         args.max_total, args.online_only, meals_ui, args.top,
                         args.split, args.alfa)
        all_results.append(r)

    # сводка в бюджет
    hits = [(r["hotel"]["name"], len(r.get("filtered", []))) for r in all_results]
    ok = [(n, c) for n, c in hits if c > 0]
    print(f"\nИТОГ: {len(targets)} отелей, в фильтр прошло {len(ok)}: {ok}")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=1)
        print(f"Сохранено в {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
