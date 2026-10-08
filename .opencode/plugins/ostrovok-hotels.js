import { tool } from "@opencode-ai/plugin";

/**
 * Ostrovok hotel search — максимально автономный плагин.
 * Никаких ручных файлов: discover/preset/split/alfa/reviews — всё через tools.
 *
 * Tools:
 *  - ostrovok_smart_search: главный поиск (area|hotel|preset) + split + alfa, без файлов
 *  - ostrovok_resolve_region: region_id по path/URL
 *  - ostrovok_discover: список отелей района без тарифов
 *  - ostrovok_nearby: соседи отеля без тарифов
 *  - ostrovok_preset: list/add/remove без редактора
 *  - ostrovok_reviews: отзывы из разных источников (Ostrovok+TopHotels парсинг, остальные ссылками)
 */
export default async ({ directory }) => {
  const runScript = (root, script, argv) => {
    const cmd = ["python3", JSON.stringify(`${root}/${script}`), ...argv].join(" ");
    const proc = Bun.spawnSync(["sh", "-c", cmd], { cwd: root });
    const out = proc.stdout ? proc.stdout.toString() : "";
    const err = proc.stderr ? proc.stderr.toString() : "";
    const text = (out + (err ? "\nSTDERR:\n" + err : "")).trim();
    return text.slice(0, 15000) || "(пустой вывод скрипта)";
  };
  const runOstrovok = (root, argv) => runScript(root, "ostrovok_search.py", argv);
  const presetPath = (root, p) => (p ? JSON.stringify(p) : JSON.stringify(`${root}/hotels.json`));

  return {
    tool: {
      ostrovok_smart_search: tool({
        description:
          "ГЛАВНЫЙ поиск отелей Островка без ручных файлов. Area принимает ОДНУ или СРАЗУ НЕСКОЛЬКО локаций через запятую ('сиде, кемер') или повтор флага. Районы: сиде/кемер/анталия/лара/кунду/чолаклы. Сам резолвит region, умеет split при rates=null и считает кэшбэк Alfa Travel.",
        args: {
          arrival: tool.schema.string(),
          departure: tool.schema.string(),
          area: tool.schema.string().optional(),
          hotel: tool.schema.string().optional(),
          path: tool.schema.string().optional(),
          region: tool.schema.number().optional(),
          preset: tool.schema.string().optional(),
          limit: tool.schema.number().optional(),
          meals: tool.schema.string().optional(),
          maxTotal: tool.schema.number().optional(),
          adults: tool.schema.number().optional(),
          split: tool.schema.boolean().optional(),
          alfa: tool.schema.boolean().optional(),
          top: tool.schema.number().optional(),
        },
        async execute(args, context) {
          const root = context?.directory ?? directory;
          const parts = [
            "--arrival", JSON.stringify(args.arrival),
            "--departure", JSON.stringify(args.departure),
          ];
          if (args.area) {
            parts.push("--area", JSON.stringify(args.area));
            parts.push("--limit", String(args.limit ?? 10));
          } else if (args.hotel) {
            parts.push("--hotel", JSON.stringify(args.hotel));
            if (args.path) parts.push("--path", JSON.stringify(args.path));
            if (args.region) parts.push("--region", String(args.region));
          } else {
            parts.push("--preset", presetPath(root, args.preset));
          }
          parts.push("--meals", JSON.stringify(args.meals ?? "half-board,full-board,half-board-dinner,all-inclusive,ultra-all-inclusive"));
          if (args.maxTotal) parts.push("--max-total", String(args.maxTotal));
          if (args.adults) parts.push("--adults", String(args.adults));
          if (args.split) parts.push("--split");
          if (args.alfa) parts.push("--alfa");
          if (args.top) parts.push("--top", String(args.top));
          try {
            return runOstrovok(root, parts);
          } catch (e) {
            return `Ошибка smart_search: ${e?.message ?? e}`;
          }
        },
      }),

      ostrovok_resolve_region: tool({
        description:
          "Найти region_id отеля по path или URL страницы Островка. Ничего править не надо — вернет region_id, название и готовый фрагмент.",
        args: { pathOrUrl: tool.schema.string() },
        async execute(args, context) {
          const root = context?.directory ?? directory;
          try {
            return runOstrovok(root, ["--resolve", JSON.stringify(args.pathOrUrl)]);
          } catch (e) {
            return `Ошибка резолва: ${e?.message ?? e}`;
          }
        },
      }),

      ostrovok_discover: tool({
        description:
          "DISCOVER: список отелей ОДНОГО или СРАЗУ НЕСКОЛЬКИХ районов без тарифов. Area: 'сиде' или 'сиде, кемер, анталия'. Вернет slug/path/region — дальше можно сразу в smart_search.",
        args: {
          area: tool.schema.string(),
          limit: tool.schema.number().optional(),
        },
        async execute(args, context) {
          const root = context?.directory ?? directory;
          try {
            return runOstrovok(root, ["--discover", JSON.stringify(args.area), "--limit", String(args.limit ?? 12)]);
          } catch (e) {
            return `Ошибка discover: ${e?.message ?? e}`;
          }
        },
      }),

      ostrovok_nearby: tool({
        description:
          "NEARBY: соседи заданного отеля (та же зона) без тарифов. Принимает path/URL отеля.",
        args: {
          pathOrUrl: tool.schema.string(),
          limit: tool.schema.number().optional(),
        },
        async execute(args, context) {
          const root = context?.directory ?? directory;
          try {
            return runOstrovok(root, ["--nearby", JSON.stringify(args.pathOrUrl), "--limit", String(args.limit ?? 8)]);
          } catch (e) {
            return `Ошибка nearby: ${e?.message ?? e}`;
          }
        },
      }),

      ostrovok_preset: tool({
        description:
          "PRESET без редактора: list/add/remove. list: показать (опц. фильтр). add: добавить по path/URL (region сам, имя опц). remove: удалить по slug.",
        args: {
          action: tool.schema.string(),
          filter: tool.schema.string().optional(),
          pathOrUrl: tool.schema.string().optional(),
          name: tool.schema.string().optional(),
          slug: tool.schema.string().optional(),
          preset: tool.schema.string().optional(),
        },
        async execute(args, context) {
          const root = context?.directory ?? directory;
          const def = `${root}/hotels.json`;
          const pp = args.preset ?? def;
          try {
            if (args.action === "list")
              return runOstrovok(root, ["--preset-list", JSON.stringify(args.filter ?? ""), "--preset", JSON.stringify(pp)]);
            if (args.action === "add") {
              if (!args.pathOrUrl) return "Для add нужен pathOrUrl";
              const a = ["--preset-add", JSON.stringify(args.pathOrUrl), "--preset", JSON.stringify(pp)];
              if (args.name) a.push("--add-name", JSON.stringify(args.name));
              return runOstrovok(root, a);
            }
            if (args.action === "remove") {
              if (!args.slug) return "Для remove нужен slug";
              return runOstrovok(root, ["--preset-remove", JSON.stringify(args.slug), "--preset", JSON.stringify(pp)]);
            }
            return "action должен быть list|add|remove";
          } catch (e) {
            return `Ошибка preset: ${e?.message ?? e}`;
          }
        },
      }),

      ostrovok_reviews: tool({
        description:
          "Отзывы из РАЗНЫХ источников без ручной работы. Один отель (hotel+area+path) или сразу пачка из пресета (preset+filter). Парсит рейтинги Ostrovok (/10) и TopHotels (/5), остальные (TripAdvisor, Yandex, Otzyv, 1001tur, Level, Coral, Библио-Глобус) отдает ссылками + цитатами из выдачи.",
        args: {
          hotel: tool.schema.string().optional(),
          area: tool.schema.string().optional(),
          path: tool.schema.string().optional(),
          preset: tool.schema.string().optional(),
          filter: tool.schema.string().optional(),
          limitSources: tool.schema.number().optional(),
          topReviews: tool.schema.number().optional(),
        },
        async execute(args, context) {
          const root = context?.directory ?? directory;
          const parts = [];
          if (args.preset || (!args.hotel && !args.path)) {
            parts.push("--preset", presetPath(root, args.preset));
            if (args.filter) parts.push("--filter", JSON.stringify(args.filter));
          } else {
            if (args.hotel) parts.push("--hotel", JSON.stringify(args.hotel));
            if (args.area) parts.push("--area", JSON.stringify(args.area));
            if (args.path) parts.push("--path", JSON.stringify(args.path));
          }
          parts.push("--limit-sources", String(args.limitSources ?? 8));
          parts.push("--top-reviews", String(args.topReviews ?? 3));
          try {
            return runScript(root, "reviews_search.py", parts);
          } catch (e) {
            return `Ошибка reviews: ${e?.message ?? e}`;
          }
        },
      }),

      // legacy-алиас чтобы старые вызовы не ломались
      ostrovok_search: tool({
        description:
          "Legacy-алиас к smart_search: тарифы по датам (preset по умолчанию). Для нового кода используй ostrovok_smart_search.",
        args: {
          arrival: tool.schema.string(),
          departure: tool.schema.string(),
          hotel: tool.schema.string().optional(),
          path: tool.schema.string().optional(),
          region: tool.schema.number().optional(),
          preset: tool.schema.string().optional(),
          meals: tool.schema.string().optional(),
          maxTotal: tool.schema.number().optional(),
          adults: tool.schema.number().optional(),
        },
        async execute(args, context) {
          const root = context?.directory ?? directory;
          const parts = ["--arrival", JSON.stringify(args.arrival), "--departure", JSON.stringify(args.departure)];
          if (args.hotel) parts.push("--hotel", JSON.stringify(args.hotel));
          else parts.push("--preset", presetPath(root, args.preset));
          if (args.path) parts.push("--path", JSON.stringify(args.path));
          if (args.region) parts.push("--region", String(args.region));
          parts.push("--meals", JSON.stringify(args.meals ?? "half-board,full-board,half-board-dinner,all-inclusive,ultra-all-inclusive"));
          if (args.maxTotal) parts.push("--max-total", String(args.maxTotal));
          if (args.adults) parts.push("--adults", String(args.adults));
          try {
            return runOstrovok(root, parts);
          } catch (e) {
            return `Ошибка search: ${e?.message ?? e}`;
          }
        },
      }),
    },
  };
};
