#!/usr/bin/env python3
"""Агрегатор отзывов об отелях из разных источников (stdlib only).

Логика: DuckDuckGo HTML (без JS) находит страницы отзывов ->
качаем Server-Side страницы (Ostrovok, TopHotels) и парсим рейтинги ->
остальные источники отдаем ссылками + сниппетами из поиска.

Примеры (ничего править вручную не надо):
  python3 reviews_search.py --hotel "Art Poseidon Side" --area сиде
  python3 reviews_search.py --hotel "Britannia Hotel" --area кемер --path turkey/kemer/mid8574631/britannia_hotel_4/
  python3 reviews_search.py --preset hotels.json --filter кемер --top-reviews 3
  python3 reviews_search.py --hotel "Esperanza Boutique" --area лара --json-out reviews.json
"""
import argparse
import html as ihtml
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PRESET = os.path.join(SCRIPT_DIR, "hotels.json")

UA = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ru-RU,ru;q=0.9"}

SOURCE_LABELS = {
    "tophotels.ru": "TopHotels",
    "tripadvisor": "TripAdvisor",
    "ostrovok.ru": "Ostrovok",
    "1001tur.ru": "1001tur",
    "level.travel": "Level.Travel",
    "travelask.ru": "TravelAsk",
    "otzyv.ru": "Otzyv.ru",
    "biblioglobus": "Библио-Глобус",
    "coral": "Coral",
    "onlinetours.ru": "OnlineTours",
    "poehalisnami": "Поехали с нами",
    "turpravda": "ТурПравда",
    "russiatourism": "Русский Экспресс",
    "artposeidonside.com": "Официалка",
}

# ключевые темы для сигналов (встречаемость в сниппетах+страницах)
TOPIC_WORDS = {
    "питание/еда": ["питан", "еда", "шведск", "ресторан", "голодн", "вкусн", "однообраз"],
    "пляж/море": ["пляж", "море", "шезлонг", "галька", "песок", "заход"],
    "номер": ["номер", "уборк", "полотенц", "белье", "кондиционер", "ремонт", "грязн", "тарак"],
    "персонал": ["персонал", "ресепшн", "хам", "вежлив", "приветлив"],
    "шум/сон": ["шум", "музык", "слышим", "самолет"],
    "анимация": ["анимац", "диско", "шоу"],
    "wifi": ["wi-fi", "wifi", "вай-фай", "интернет"],
    "расположение": ["расположен", "центр", "рядом", "далеко", "трансфер", "шаттл"],
}


def fetch(url: str, timeout: int = 25, data: bytes | None = None) -> str:
    headers = dict(UA)
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Referer"] = "https://html.duckduckgo.com/"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="ignore")


def _parse_ddg_html(html: str, max_results: int) -> list:
    out = []
    for m in re.finditer(r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a', html, re.S):
        url = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2))
        title = ihtml.unescape(re.sub(r"\s+", " ", title)).strip()
        um = re.search(r"uddg=([^&]+)", url)
        if um:
            try:
                url = urllib.parse.unquote(um.group(1))
            except Exception:
                pass
        out.append({"url": url, "title": title})
        if len(out) >= max_results:
            break
    snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</', html, re.S)
    for i, s in enumerate(snips[: len(out)]):
        t = ihtml.unescape(re.sub(r"<[^>]+>", "", s))
        out[i]["snippet"] = re.sub(r"\s+", " ", t).strip()[:400]
    return out


def _parse_ddg_lite(html: str, max_results: int) -> list:
    out = []
    links = re.findall(r'href="([^"]+)" class=\'result-link\'>(.*?)</a', html, re.S)
    snips = re.findall(r"class='result-snippet'[^>]*>(.*?)</td", html, re.S)
    for i, (url, title) in enumerate(links[:max_results]):
        t = ihtml.unescape(re.sub(r"<[^>]+>", "", title))
        item = {"url": url.strip(), "title": re.sub(r"\s+", " ", t).strip()[:140]}
        if i < len(snips):
            s = ihtml.unescape(re.sub(r"<[^>]+>", "", snips[i]))
            item["snippet"] = re.sub(r"\s+", " ", s).strip()[:400]
        out.append(item)
    return out


def ddg_search(query: str, max_results: int = 12) -> list:
    body = urllib.parse.urlencode({"q": query}).encode()
    # 1) основной endpoint
    try:
        html = fetch("https://html.duckduckgo.com/html/", data=body)
        res = _parse_ddg_html(html, max_results)
        if res:
            return res
    except Exception:
        pass
    # 2) fallback lite (менее строгий рейт-лимит)
    try:
        html = fetch("https://lite.duckduckgo.com/lite/", data=body)
        res = _parse_ddg_lite(html, max_results)
        if res:
            return res
    except Exception as e:
        return [{"error": f"ddg+lite: {e}"}]
    return []


def classify(url: str) -> str:
    u = url.lower()
    for dom, label in SOURCE_LABELS.items():
        if dom in u:
            return label
    m = re.search(r"https?://([^/]+)/", url)
    return m.group(1) if m else url[:40]


def parse_ostrovok(html: str) -> dict:
    d: dict = {"scale": "0-10"}
    for m in re.finditer(r'"ratingValue":\s*([\d.]+)', html):
        try:
            d["rating"] = round(float(m.group(1)), 1)
            break
        except ValueError:
            pass
    if "rating" not in d:
        for m in re.finditer(r'"rating"?:\s*"?([\d.]+)', html):
            try:
                v = float(m.group(1))
                if 0 < v <= 10:
                    d["rating"] = round(v, 1)
                    break
            except ValueError:
                pass
    m = re.search(r'"reviewCount":\s*(\d+)', html)
    if m:
        d["reviews_count"] = int(m.group(1))
    else:
        m2 = re.search(r"(\d+)\s*отзыв", html, re.I)
        if m2:
            d["reviews_count_hint"] = int(m2.group(1))
    t = re.search(r"<title>(.*?)</title>", html, re.S)
    if t:
        d["title"] = re.sub(r"\s+", " ", t.group(1)).strip()[:140]
    return d


def parse_tophotels(html: str) -> dict:
    d: dict = {"scale": "0-5"}
    m = re.search(r'"aggregateRating":\s*\{\s*"@type":\s*"AggregateRating",\s*"ratingValue":\s*([\d.]+)'
                  r'.*?"reviewCount":\s*(\d+)', html, re.S)
    if m:
        d["rating"] = round(float(m.group(1)), 2)
        d["reviews_count"] = int(m.group(2))
    # проценты рекомендуют: вида "161 (15%)" рядом с рекомендуют — берем все пары
    pairs = re.findall(r"(\d+)\s*\((\d+)%\)", html)
    if pairs:
        d["vote_pairs"] = pairs[:6]
    return d


def topic_signals(texts: list) -> dict:
    blob = " ".join(texts).lower()
    sig = {}
    for topic, words in TOPIC_WORDS.items():
        c = sum(blob.count(w) for w in words)
        if c:
            sig[topic] = c
    return sig


def collect_hotel(name: str, area: str = "", ostrovok_path: str = "",
                  limit_sources: int = 10, top_snippets: int = 6) -> dict:
    queries = [f"{name} {area} отзывы".strip(), f"{name} tophotels"]
    if ostrovok_path:
        queries.append(f"site:ostrovok.ru {name}")
    seen, results = set(), []
    for q in queries:
        for r in ddg_search(q, max_results=limit_sources):
            u = r.get("url", "")
            if not u or u in seen or u.startswith("//duckduckgo"):
                continue
            seen.add(u)
            results.append(r)
            if len(results) >= limit_sources * 2:
                break
    # группируем по источникам, предпочитаем первый URL каждого
    by_src, order = {}, []
    for r in results:
        s = classify(r["url"])
        if s not in by_src:
            by_src[s] = r
            order.append(s)
    parsed, texts = {}, []
    for r in results:
        if r.get("snippet"):
            texts.append(r["snippet"])
    # Ostrovok: известный path ИЛИ найденный в выдаче
    ost_url = None
    if ostrovok_path:
        p = ostrovok_path.strip().lstrip("/")
        ost_url = f"https://ostrovok.ru/hotel/{p}" if not p.startswith("http") else p
    else:
        for r in results:
            if "ostrovok.ru/hotel/" in r["url"]:
                ost_url = r["url"]
                break
    if ost_url:
        try:
            parsed["Ostrovok"] = {"url": ost_url, **parse_ostrovok(fetch(ost_url))}
            texts.append(json.dumps(parsed["Ostrovok"], ensure_ascii=False))
        except Exception as e:
            parsed["Ostrovok"] = {"url": ost_url, "error": str(e)[:160]}
    # TopHotels: первый tophotels-URL из выдачи
    th_url = next((r["url"] for r in results if "tophotels.ru/hotel/al" in r["url"]), None)
    if th_url:
        try:
            parsed["TopHotels"] = {"url": th_url, **parse_tophotels(fetch(th_url))}
        except Exception as e:
            parsed["TopHotels"] = {"url": th_url, "error": str(e)[:160]}
    links = [{"source": s, "url": by_src[s]["url"], "title": by_src[s].get("title", "")[:110]}
             for s in order[:limit_sources]]
    return {"hotel": name, "area": area, "ostrovok_path": ostrovok_path,
            "sources_found": len(results), "links": links,
            "parsed": parsed, "top_snippets": [r for r in results[:top_snippets]],
            "topics": topic_signals(texts)}


def fmt_report(h: dict) -> str:
    L = [f"== {h['hotel']} ({h.get('area','')}) — источников: {h['sources_found']} =="]
    p = h.get("parsed", {})
    if "Ostrovok" in p:
        o = p["Ostrovok"]
        L.append(f"   Ostrovok: {o.get('rating','?')} /10, отзывов {o.get('reviews_count', o.get('reviews_count_hint','?'))} | {o.get('url')}")
    if "TopHotels" in p:
        t = p["TopHotels"]
        L.append(f"   TopHotels: {t.get('rating','?')} /5, отзывов {t.get('reviews_count','?')} | {t.get('url')}")
    L.append("   Ссылки:")
    for l in h.get("links", [])[:10]:
        L.append(f"    - {l['source']}: {l['url']}")
    if h.get("topics"):
        top = sorted(h["topics"].items(), key=lambda x: -x[1])[:6]
        L.append("   О чем чаще пишут: " + ", ".join(f"{k}×{v}" for k, v in top))
    L.append("   Цитаты из выдачи:")
    for s in h.get("top_snippets", [])[:4]:
        sn = s.get("snippet", "")
        if sn:
            L.append(f"    · [{classify(s['url'])}] {sn[:220]}")
    return "\n".join(L)


def load_preset(path: str) -> list:
    with open(path or DEFAULT_PRESET, encoding="utf-8") as f:
        d = json.load(f)
    return d if isinstance(d, list) else d.get("hotels", [])


def main() -> int:
    ap = argparse.ArgumentParser(description="Отзывы из разных источников без ручной работы")
    ap.add_argument("--hotel", help="название отеля, напр. 'Art Poseidon Side'")
    ap.add_argument("--area", default="", help="район словами: сиде/кемер/анталия...")
    ap.add_argument("--path", default="", help="ostrovok path для точного рейтинга")
    ap.add_argument("--preset", nargs="?", const="PRESET", default=None, help="прогнать весь пресет (опц. файл)")
    ap.add_argument("--filter", default="", help="фильтр по пресету (напр. кемер)")
    ap.add_argument("--limit-sources", type=int, default=10)
    ap.add_argument("--top-reviews", type=int, default=5)
    ap.add_argument("--json-out", help="сохранить JSON")
    args = ap.parse_args()

    targets = []
    if args.preset:
        pf = DEFAULT_PRESET if args.preset == "PRESET" else args.preset
        items = load_preset(pf)
        f = args.filter.lower()
        for it in items:
            blob = f"{it.get('name','')} {it.get('hotel','')}".lower()
            if f and f not in blob:
                continue
            # имя без звезд/города для поиска
            nm = re.sub(r"\d\*.*", "", it.get("name") or it.get("hotel", "")).strip(" -,")
            targets.append({"name": nm or it["hotel"], "area": "", "path": it.get("path", "")})
        if not targets:
            print(f"Пресет {pf}: ничего по фильтру '{args.filter}'", file=sys.stderr)
            return 1
    elif args.hotel:
        targets.append({"name": args.hotel, "area": args.area, "path": args.path})
    else:
        print("Нужно --hotel или --preset", file=sys.stderr)
        return 2

    all_out = []
    for t in targets:
        try:
            h = collect_hotel(t["name"], t.get("area", ""), t.get("path", ""),
                              args.limit_sources, args.top_reviews)
        except Exception as e:
            print(f"{t['name']}: ОШИБКА: {e}", file=sys.stderr)
            continue
        print(fmt_report(h) + "\n")
        all_out.append(h)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(all_out, f, ensure_ascii=False, indent=1)
        print(f"Сохранено в {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
