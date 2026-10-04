#!/usr/bin/env python3
"""Поиск номеров на Островке через приватный эндпоинт hp/search.

Пример:
  python3 ostrovok_search.py --arrival 2026-10-05 --departure 2026-10-19 --hotel dinc_hotel --region 481
  python3 ostrovok_search.py --arrival 2026-10-05 --departure 2026-10-19 --preset hotels.json --meals half-board,all-inclusive,ultra-all-inclusive --max-total 110000
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter

API = "https://ostrovok.ru/hotel/search/v1/site/hp/search"

# Маппинг UI-фильтра meal_types (из URL) -> коды meal в API
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

# Известные region_id (пополняется через --resolve):
# Анталия-город 481, Кунду 6054866, Лара 6054878,
# Кемер 8281, Сиде 4931 (Turquoise 4218 — исключение).
KNOWN_REGIONS = {
    481: "Анталия-город",
    6054866: "Кунду",
    6054878: "Лара",
    8281: "Кемер",
    4931: "Сиде",
    4218: "Сиде/Кумкой (Turquoise)",
}


def extract_region_candidates(html: str, top_n: int = 10) -> list:
    ids = re.findall(r'regionId\"?:\s*(\d+)', html)
    return Counter(ids).most_common(top_n)


def fetch_html(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={
        "accept": "text/html,*/*",
        "accept-language": "ru-RU,ru;q=0.9",
        "Referer": "https://ostrovok.ru/",
        "User-Agent": "Mozilla/5.0",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    # пробуем utf-8, иначе latin
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="ignore")


def normalize_hotel_path(raw: str) -> str:
    """Принимает path, полный URL или слаг; возвращает path вида turkey/.../mid.../slug/."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    # полный URL
    m = re.search(r"ostrovok\.ru/hotel/([^?#]+)", raw)
    if m:
        raw = m.group(1)
    raw = raw.lstrip("/")
    if raw.startswith("hotel/"):
        raw = raw[len("hotel/"):]
    if not raw.endswith("/"):
        raw += "/"
    return raw


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
    # по README: первое вхождение с повтором x3 — это и есть регион
    best = None
    for rid, cnt in cands:
        if cnt >= 3:
            best = int(rid)
            break
    if best is None:
        best = int(cands[0][0])
    label = KNOWN_REGIONS.get(best, "")
    return {"ok": True, "path": path, "url": url,
            "region_id": best, "label": label,
            "candidates": [{"region_id": int(r), "count": c,
                            "label": KNOWN_REGIONS.get(int(r), "")} for r, c in cands[:8]]}


def normalize_meals(raw: str) -> set:
    out = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip().strip(".")
        if not part:
            continue
        out.add(MEAL_ALIASES.get(part, part))
        # точки вида "halfBoard.fullBoard" тоже поддерживаем
        for sub in part.split("."):
            sub = sub.strip()
            if sub:
                out.add(MEAL_ALIASES.get(sub, sub))
    return out


def fetch_rates(hotel: str, region_id: int, arrival: str, departure: str, adults: int = 2,
                currency: str = "RUB", timeout: int = 30) -> dict:
    body = {
        "arrival_date": arrival,
        "departure_date": departure,
        "hotel": hotel,
        "currency": currency,
        "lang": "ru",
        "region_id": int(region_id),
        "paxes": [{"adults": int(adults)}],
    }
    enc = urllib.parse.quote(json.dumps(body, separators=(",", ":")))
    url = f"{API}?body={enc}"
    req = urllib.request.Request(url, headers={
        "accept": "*/*",
        "accept-language": "ru-RU,ru;q=0.9",
        "Referer": "https://ostrovok.ru/",
        "User-Agent": "Mozilla/5.0",
    })
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
    return {
        "meal": tuple(r.get("meal") or []),
        "total": total,
        "per_day": per_day,
        "room": r.get("room_name") or "",
        "online_pay": online,
        "currency": pay.get("show_currency_code") or "RUB",
    }


def booking_link(base_path: str, arrival: str, departure: str, adults: int, meals_ui: str) -> str:
    # arrival/departure: YYYY-MM-DD -> DD.MM.YYYY
    def fmt(d):
        y, m, dd = d.split("-")
        return f"{dd}.{m}.{y}"
    link = f"https://ostrovok.ru/hotel/{base_path}?dates={fmt(arrival)}-{fmt(departure)}&guests={adults}"
    if meals_ui:
        link += f"&meal_types={meals_ui}"
    return link


def main() -> int:
    ap = argparse.ArgumentParser(description="Островок: проверка тарифов hp/search + резолв region_id")
    ap.add_argument("--arrival", help="YYYY-MM-DD (не нужен с --resolve)")
    ap.add_argument("--departure", help="YYYY-MM-DD (не нужен с --resolve)")
    ap.add_argument("--hotel", help="слаг отеля, напр. dinc_hotel")
    ap.add_argument("--path", help="path после /hotel/, напр. turkey/kemer/mid7354304/ozkaymak_marina_hotel_3/ — нужен для авто-region и ссылки")
    ap.add_argument("--region", type=int, default=None, help="region_id (Анталия-город 481, Кунду 6054866, Лара 6054878, Кемер 8281, Сиде 4931). Если не задан и есть --path — резолвится автоматически")
    ap.add_argument("--resolve", help="только найти region_id для path/URL отеля, без поиска тарифов. Пример: --resolve turkey/kemer/mid7354304/ozkaymak_marina_hotel_3/")
    ap.add_argument("--no-auto-region", dest="auto_region", action="store_false", default=True,
                    help="не резолвить region_id автоматически, требовать --region")
    ap.add_argument("--preset", help="JSON со списком отелей: [{name,hotel,region_id,path}]")
    ap.add_argument("--adults", type=int, default=2)
    ap.add_argument("--meals", default=GOOD_FOOD_DEFAULT,
                    help="фильтр питания, напр. 'half-board,all-inclusive,ultra-all-inclusive'")
    ap.add_argument("--max-total", type=float, default=0, help="максимум итого в рублях, 0 = без лимита")
    ap.add_argument("--online-only", action="store_true", default=True,
                    help="только тарифы с онлайн-оплатой картой (Мир/Visa РФ)")
    ap.add_argument("--json-out", help="сохранить сырой результат в файл")
    args = ap.parse_args()

    # Режим резолва region_id — без дат и тарифов
    if args.resolve:
        try:
            res = resolve_region_id(args.resolve)
        except Exception as e:
            print(f"ОШИБКА РЕЗОЛВА: {e}", file=sys.stderr)
            return 1
        print(json.dumps(res, ensure_ascii=False, indent=1))
        if res.get("ok"):
            print(f"\nГотовый фрагмент для hotels.json: hotel=<slug>, region_id={res['region_id']}, path={res['path']}")
        return 0

    if not args.arrival or not args.departure:
        print("Нужно --arrival и --departure (или используй --resolve для поиска region_id)", file=sys.stderr)
        return 2

    want = normalize_meals(args.meals)
    # UI-строка для ссылок: оставляем как ввел пользователь
    meals_ui = args.meals.replace(",", ".")

    targets = []
    if args.preset:
        with open(args.preset, encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else data.get("hotels", [])
        for it in items:
            slug = it["hotel"]
            path = it.get("path", "") or args.path or ""
            rid = it.get("region_id", args.region)
            if not rid and args.auto_region and path:
                try:
                    res = resolve_region_id(path)
                    if res.get("ok"):
                        rid = res["region_id"]
                        print(f"{it.get('name') or slug}: region_id авто-резолв -> {rid} ({res.get('label')})")
                except Exception as e:
                    print(f"{it.get('name') or slug}: авто-резолв не удался: {e}")
            if not rid:
                print(f"{it.get('name') or slug}: нет region_id — укажи --region или добавь region_id в пресет (подсказка: --resolve {path})")
                continue
            targets.append({
                "name": it.get("name") or slug,
                "hotel": slug,
                "region_id": int(rid),
                "path": path,
            })
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
            print("Нужно --region или --path для авто-резолва (пример: --path turkey/kemer/mid7354304/ozkaymak_marina_hotel_3/)", file=sys.stderr)
            return 2
        targets.append({"name": slug, "hotel": slug,
                        "region_id": int(rid), "path": path})
    else:
        print("Нужно --hotel или --preset", file=sys.stderr)
        return 2

    all_results = []
    for t in targets:
        try:
            data = fetch_rates(t["hotel"], t["region_id"], args.arrival, args.departure, args.adults)
        except Exception as e:
            print(f"{t['name']}: ОШИБКА ЗАПРОСА: {e}")
            continue
        rates = data.get("rates")
        if not rates:
            print(f"{t['name']}: rates=null — нет сквозной доступности на весь период "
                  f"(проверь разбивку 05-12 / 12-19 или другой ресурс)")
            all_results.append({"hotel": t, "rates": [], "filtered": []})
            continue
        rows = [summarize_rate(r) for r in rates]
        filt = [r for r in rows if (not want or set(r["meal"]) & want)]
        if args.online_only:
            filt = [r for r in filt if r["online_pay"]]
        if args.max_total:
            filt = [r for r in filt if r["total"] and r["total"] <= args.max_total]
        filt.sort(key=lambda r: r["total"])
        print(f"\n== {t['name']} ({t['hotel']}) — всего тарифов: {len(rows)}, "
              f"под фильтр: {len(filt)} ==")
        if not filt:
            meals_found = sorted({m for r in rows for m in r["meal"]})
            print(f"   Нет тарифов под фильтр. Найденные meal: {meals_found}")
            cheapest = min(rows, key=lambda r: r["total"] or 1e18)
            print(f"   Самый дешевый вообще: {cheapest['meal']} {cheapest['total']:.0f} RUB | {cheapest['room'][:70]}")
        for r in filt[:5]:
            print(f"   {','.join(r['meal'])} {r['total']:.0f} {r['currency']} "
                  f"(~{r['per_day']:.0f}/ночь) | {r['room'][:70]}")
        if t.get("path"):
            print("   Ссылка: " + booking_link(t["path"], args.arrival, args.departure,
                                               args.adults, meals_ui))
        all_results.append({"hotel": t, "rates": rows, "filtered": filt})

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=1)
        print(f"\nСырой результат сохранен в {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
