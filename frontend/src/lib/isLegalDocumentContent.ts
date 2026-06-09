const LEGAL_RE =
  /(?:оферт|договор|соглашен|заявлен|политик|регламент|устав|приказ)/i;

export function isLegalDocumentContent(content: string, titleHint?: string): boolean {
  const sample = `${titleHint ?? ""}\n${content.slice(0, 1200)}`;
  return LEGAL_RE.test(sample);
}
