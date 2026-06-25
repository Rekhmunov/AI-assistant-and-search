export const PRO_BENEFIT_KEYS = [
  "proBenefitAiModels",
  "proBenefitMoreLimits",
  "proBenefitFullHistory",
  "proBenefitSearchPriority",
  "proBenefitVoiceInput",
  "proBenefitMultiFile",
  "proBenefitCoffeePrice",
] as const;

export type ProBenefitKey = (typeof PRO_BENEFIT_KEYS)[number];
