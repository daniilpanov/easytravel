import { tool } from "@opencode-ai/plugin";

/**
 * Ostrovok hotel search — opencode plugin.
 * Wraps ostrovok_search.py (no deps, stdlib only) as custom tools.
 * Auto-loaded from .opencode/plugins/.
 * Tools:
 *  - ostrovok_search: тарифы по датам
 *  - ostrovok_resolve_region: region_id по path/URL отеля
 */
export default async ({ directory }) => {
  const runScript = (root, argv) => {
    const cmd = ["python3", JSON.stringify(`${root}/ostrovok_search.py`), ...argv].join(" ");
    const proc = Bun.spawnSync(["sh", "-c", cmd], { cwd: root });
    const out = proc.stdout ? proc.stdout.toString() : "";
    const err = proc.stderr ? proc.stderr.toString() : "";
    const text = (out + (err ? "\nSTDERR:\n" + err : "")).trim();
    return text.slice(0, 12000) || "(пустой вывод скрипта)";
  };
  return {
    tool: {
      ostrovok_search: tool({
        description:
          "Проверить тарифы Островка на даты: питание, итого в рублях, онлайн-оплата картой РФ. Если region неизвестен — передай path, region резолвится автоматически. Rates=null значит нет сквозной доступности.",
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
          const presetDefault = `${root}/hotels.json`;
          const parts = [
            "--arrival", JSON.stringify(args.arrival),
            "--departure", JSON.stringify(args.departure),
          ];
          if (args.hotel) parts.push("--hotel", JSON.stringify(args.hotel));
          else parts.push("--preset", JSON.stringify(args.preset ?? presetDefault));
          if (args.path) parts.push("--path", JSON.stringify(args.path));
          if (args.region) parts.push("--region", String(args.region));
          parts.push("--meals", JSON.stringify(args.meals ?? "half-board,full-board,half-board-dinner,all-inclusive,ultra-all-inclusive"));
          if (args.maxTotal) parts.push("--max-total", String(args.maxTotal));
          if (args.adults) parts.push("--adults", String(args.adults));
          try {
            return runScript(root, parts);
          } catch (e) {
            return `Ошибка запуска скрипта: ${e?.message ?? e}`;
          }
        },
      }),
      ostrovok_resolve_region: tool({
        description:
          "Найти region_id отеля на Островке по path или URL его страницы. Вернет region_id + кандидатов и готовый фрагмент для hotels.json. Пример path: turkey/kemer/mid7354304/ozkaymak_marina_hotel_3/",
        args: {
          pathOrUrl: tool.schema.string(),
        },
        async execute(args, context) {
          const root = context?.directory ?? directory;
          try {
            return runScript(root, ["--resolve", JSON.stringify(args.pathOrUrl)]);
          } catch (e) {
            return `Ошибка резолва region_id: ${e?.message ?? e}`;
          }
        },
      }),
    },
  };
};
