/** Когда в треде агента запрос идёт в поисковый SSE (документы), а не в onboarding API. */

const AGENT_SETUP_RE =
  /(?:напомин|уведом|агент|max\b|бот\b|групп|модерац|faq|база\s+знан|поддержк|расписан|часовой\s+пояс|запусти|подтверж)/i;

const IN_CHAT_RE =
  /\b(?:в\s+чат(?:е)?|в\s+ответ(?:е)?|текстом|без\s+(?:файл|документ)|не\s+(?:делай|создавай|генерируй)?\s*(?:файл|документ))\b/i;

const CONVERT_TO_DOC_RE =
  /(?:составь|оформи|подготовь|сгенерируй|сделай|напиши|сформируй|создай|преобразуй|экспортируй)(?:\s+\S+){0,8}?\b(?:в\s+)?(?:документ|docx|word|ворд)\b/i;

const ACTION_DOCUMENT_RE =
  /(?:составь|оформи|подготовь|сгенерируй|сделай|напиши|сформируй|создай)(?:\s+(?:мне|пожалуйста))?\s+(?:документ|docx|word|ворд)\b/i;

const INTO_DOCUMENT_RE = /\b(?:в|как)\s+(?:файл\s+)?(?:документ|docx|word|ворд)\b/i;

const DOC_COLON_RE = /^(?:документ|docx|word|ворд)\s*[:—-]\s*.+/i;

const PRIOR_EXPLICIT_RE =
  /(?:из\s+текста\s+выше|из\s+ответа\s+выше|по\s+тексту\s+выше|(?:текст|ответ|материал)\s+выше|выше\s+в\s+документ|на\s+основе\s+(?:текста|ответа|материала)\s+выше|из\s+предыдущ|из\s+диалог|из\s+чата|оформи\s+(?:ответ|текст|материал)\s+выше|оформи\s+выше|(?:сгенерируй|сделай)\s+(?:текст|ответ|материал)\s+выше|(?:текст|ответ)\s+выше\s+в\s+)/i;

const LEGAL_DOC_RE = /(?:оферт|договор|соглашен|заявлен|политик|регламент|устав|приказ)/i;

const DOC_CHAT_RE =
  /(?:(?:напиши|создай|составь|сформируй|подготовь|сделай|разработай)(?:\s+\S+){0,6}\s+(?:оферт|договор|соглашен|заявлен|политик|регламент|устав|приказ|документ)|(?:оферт|договор|заявлен|политик)\s+(?:для|на|по)\b)/i;

export function wantsDocumentGeneration(query: string): boolean {
  const text = (query || "").trim();
  if (text.length < 6 || IN_CHAT_RE.test(text)) return false;
  if (DOC_COLON_RE.test(text)) return true;
  if (CONVERT_TO_DOC_RE.test(text)) return true;
  if (ACTION_DOCUMENT_RE.test(text)) return true;
  if (INTO_DOCUMENT_RE.test(text)) return true;
  return false;
}

export function refersToPriorAnswer(query: string): boolean {
  return PRIOR_EXPLICIT_RE.test(query || "");
}

export function isAgentSetupQuery(query: string): boolean {
  const text = (query || "").trim();
  if (!text) return false;
  return AGENT_SETUP_RE.test(text);
}

export function agentMessageUsesSearchFlow(query: string, attachmentIds: string[]): boolean {
  const text = (query || "").trim();
  if (attachmentIds.length > 0) {
    if (!text || text.startsWith("[Загружено документов")) return false;
    return !isAgentSetupQuery(text);
  }
  if (wantsDocumentGeneration(text)) return true;
  if (refersToPriorAnswer(text)) return true;
  if (LEGAL_DOC_RE.test(text) && DOC_CHAT_RE.test(text)) return true;
  if (DOC_CHAT_RE.test(text)) return true;
  return false;
}
