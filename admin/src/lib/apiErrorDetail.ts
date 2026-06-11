/** Карта имён полей на русский для читаемых сообщений о валидации. */
const FIELD_NAMES: Record<string, string> = {
  email: "Email",
  password: "Пароль",
  title: "Заголовок",
  slug: "Slug",
  excerpt: "Краткое описание",
  content_html: "Текст статьи",
  status: "Статус",
  category_id: "Категория",
  name: "Название",
  description: "Описание",
  topic: "Тема",
  prompt: "Промпт",
  text: "Текст",
  message: "Сообщение",
  author_name: "Автор",
  body: "Текст",
  days: "Количество дней",
  ids: "Список идентификаторов",
  role: "Роль",
  field: "Поле",
  requirements: "Требования",
  meta_title: "Meta-заголовок",
  meta_description: "Meta-описание",
  meta_keywords: "Ключевые слова",
  og_title: "OG-заголовок",
  og_description: "OG-описание",
  public_path: "Путь документа",
  post_id: "Идентификатор статьи",
  comment_id: "Идентификатор комментария",
  category_id_path: "Идентификатор категории",
};

/**
 * Переводит технические сообщения Pydantic v2 на читаемый русский.
 * Работает по type-полю из 422-ответа и по тексту msg как запасной вариант.
 */
function translatePydanticMsg(type: string, msg: string, ctx?: Record<string, unknown>): string {
  switch (type) {
    case "missing":
    case "value_error.missing":
      return "Поле обязательно для заполнения";
    case "string_too_short":
      return `Слишком короткое значение (минимум ${ctx?.min_length ?? "?"} симв.)`;
    case "string_too_long":
      return `Слишком длинное значение (максимум ${ctx?.max_length ?? "?"} симв.)`;
    case "string_pattern_mismatch":
      return "Недопустимое значение";
    case "value_error":
      if (msg.toLowerCase().includes("email")) return "Некорректный email";
      if (msg.toLowerCase().includes("uuid")) return "Некорректный идентификатор";
      break;
    case "uuid_parsing":
    case "uuid_type":
      return "Некорректный идентификатор (ожидается UUID)";
    case "int_parsing":
    case "int_type":
      return "Ожидается целое число";
    case "float_parsing":
    case "float_type":
      return "Ожидается число";
    case "bool_parsing":
    case "bool_type":
      return "Ожидается логическое значение";
    case "too_short":
      return `Слишком мало элементов (минимум ${ctx?.min_length ?? "?"})`;
    case "too_long":
      return `Слишком много элементов (максимум ${ctx?.max_length ?? "?"})`;
    case "greater_than_equal":
      return `Значение должно быть не менее ${ctx?.ge ?? "?"}`;
    case "less_than_equal":
      return `Значение должно быть не более ${ctx?.le ?? "?"}`;
    case "greater_than":
      return `Значение должно быть больше ${ctx?.gt ?? "?"}`;
    case "less_than":
      return `Значение должно быть меньше ${ctx?.lt ?? "?"}`;
    case "enum":
      return `Недопустимое значение`;
    case "literal_error":
      return `Недопустимое значение`;
    case "json_invalid":
      return "Некорректный формат данных";
  }
  // Эвристика по тексту msg (если type не совпал)
  if (/at least (\d+) char/i.test(msg)) {
    const m = msg.match(/at least (\d+)/i);
    return `Слишком короткое значение (минимум ${m?.[1] ?? "?"} симв.)`;
  }
  if (/at most (\d+) char/i.test(msg)) {
    const m = msg.match(/at most (\d+)/i);
    return `Слишком длинное значение (максимум ${m?.[1] ?? "?"} симв.)`;
  }
  if (/valid email/i.test(msg)) return "Некорректный email";
  if (/valid uuid/i.test(msg)) return "Некорректный идентификатор";
  if (/match pattern/i.test(msg)) return "Недопустимое значение";
  if (/greater than or equal to (\d+)/i.test(msg)) {
    const m = msg.match(/greater than or equal to (\d+)/i);
    return `Значение должно быть не менее ${m?.[1] ?? "?"}`;
  }
  if (/less than or equal to (\d+)/i.test(msg)) {
    const m = msg.match(/less than or equal to (\d+)/i);
    return `Значение должно быть не более ${m?.[1] ?? "?"}`;
  }
  if (/at least (\d+) item/i.test(msg)) {
    const m = msg.match(/at least (\d+)/i);
    return `Список должен содержать не менее ${m?.[1] ?? "?"} элементов`;
  }
  if (/at most (\d+) item/i.test(msg)) {
    const m = msg.match(/at most (\d+)/i);
    return `Список должен содержать не более ${m?.[1] ?? "?"} элементов`;
  }
  if (/field required/i.test(msg)) return "Поле обязательно для заполнения";
  if (/input should be/i.test(msg)) return "Недопустимое значение";
  return msg;
}

function translateFieldName(raw: string): string {
  return FIELD_NAMES[raw] ?? raw;
}

/** Текст ошибки из ответа FastAPI (detail: string | object[]). */
export function formatApiErrorDetail(body: unknown, fallback: string): string {
  if (typeof body === "string" && body.trim()) return body.trim();
  if (!body || typeof body !== "object") return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const msg = (detail as { message?: string }).message;
    if (typeof msg === "string" && msg.trim()) return msg;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (!item || typeof item !== "object") return "";
        const row = item as { msg?: string; loc?: unknown[]; type?: string; ctx?: Record<string, unknown> };
        const rawMsg = typeof row.msg === "string" ? row.msg : "";
        if (!rawMsg) return "";
        const translated = translatePydanticMsg(row.type ?? "", rawMsg, row.ctx);
        const loc = Array.isArray(row.loc)
          ? row.loc.filter((x) => x !== "body").map((x) => (typeof x === "string" ? translateFieldName(x) : x)).join(".")
          : "";
        return loc ? `${loc}: ${translated}` : translated;
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return fallback;
}
