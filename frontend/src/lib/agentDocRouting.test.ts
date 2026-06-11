import { describe, expect, it } from "vitest";
import { agentMessageUsesSearchFlow, isAgentSetupQuery, wantsDocumentGeneration } from "./agentDocRouting";

describe("agentDocRouting", () => {
  it("routes document file requests to search", () => {
    expect(wantsDocumentGeneration("Создай документ оферту")).toBe(true);
    expect(agentMessageUsesSearchFlow("Создай документ оферту", [])).toBe(true);
  });

  it("keeps agent onboarding in agent API", () => {
    expect(isAgentSetupQuery("напоминай через 2 минуты")).toBe(true);
    expect(agentMessageUsesSearchFlow("напоминай через 2 минуты", [])).toBe(false);
  });

  it("routes export prior to search", () => {
    expect(agentMessageUsesSearchFlow("Оформи текст выше в docx", [])).toBe(true);
  });

  it("routes live internet lookup to search SSE", () => {
    expect(agentMessageUsesSearchFlow("можешь найти курс доллара в интернете", [])).toBe(true);
    expect(agentMessageUsesSearchFlow("найди кое-что в интернете", [])).toBe(true);
  });

  it("keeps agent setup out of search SSE", () => {
    expect(agentMessageUsesSearchFlow("напоминай каждый день в 9:00", [])).toBe(false);
  });
});
