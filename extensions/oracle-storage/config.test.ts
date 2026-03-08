/**
 * Tests for the Oracle storage config module.
 */

import { describe, test, expect } from "vitest";
import { parseConfig, oracleConfigSchema, MEMORY_CATEGORIES } from "./config.js";

describe("parseConfig", () => {
  test("returns defaults for empty input", () => {
    const config = parseConfig({});
    expect(config.serviceUrl).toBe("http://localhost:8100");
    expect(config.serviceToken).toBeUndefined();
    expect(config.autoCapture).toBe(true);
    expect(config.autoRecall).toBe(true);
    expect(config.hybridSearch).toBe(true);
    expect(config.maxResults).toBe(6);
    expect(config.minScore).toBe(0.3);
  });

  test("respects explicit values", () => {
    const config = parseConfig({
      serviceUrl: "http://custom:9999",
      autoCapture: false,
      autoRecall: false,
      hybridSearch: false,
      maxResults: 20,
      minScore: 0.8,
    });
    expect(config.serviceUrl).toBe("http://custom:9999");
    expect(config.autoCapture).toBe(false);
    expect(config.autoRecall).toBe(false);
    expect(config.hybridSearch).toBe(false);
    expect(config.maxResults).toBe(20);
    expect(config.minScore).toBe(0.8);
  });

  test("resolves environment variables in serviceToken", () => {
    process.env.TEST_TOKEN_VAR = "resolved-secret";
    const config = parseConfig({ serviceToken: "${TEST_TOKEN_VAR}" });
    expect(config.serviceToken).toBe("resolved-secret");
    delete process.env.TEST_TOKEN_VAR;
  });

  test("throws on unset env var in serviceToken", () => {
    delete process.env.NONEXISTENT_TOKEN_VAR;
    expect(() => parseConfig({ serviceToken: "${NONEXISTENT_TOKEN_VAR}" })).toThrow(
      "Environment variable NONEXISTENT_TOKEN_VAR is not set",
    );
  });

  test("handles non-string serviceUrl gracefully", () => {
    const config = parseConfig({ serviceUrl: 12345 as unknown as string });
    expect(config.serviceUrl).toBe("http://localhost:8100");
  });

  test("handles non-number maxResults gracefully", () => {
    const config = parseConfig({ maxResults: "ten" as unknown as number });
    expect(config.maxResults).toBe(6);
  });
});

describe("oracleConfigSchema", () => {
  test("parse handles null", () => {
    const config = oracleConfigSchema.parse(null);
    expect(config.serviceUrl).toBe("http://localhost:8100");
  });

  test("parse handles undefined", () => {
    const config = oracleConfigSchema.parse(undefined);
    expect(config.serviceUrl).toBe("http://localhost:8100");
  });

  test("parse handles array (invalid)", () => {
    const config = oracleConfigSchema.parse([1, 2, 3]);
    expect(config.serviceUrl).toBe("http://localhost:8100");
  });

  test("parse handles valid object", () => {
    const config = oracleConfigSchema.parse({ maxResults: 3 });
    expect(config.maxResults).toBe(3);
  });

  test("uiHints are defined for all config fields", () => {
    const hints = oracleConfigSchema.uiHints;
    expect(hints.serviceUrl).toBeDefined();
    expect(hints.serviceToken).toBeDefined();
    expect(hints.autoCapture).toBeDefined();
    expect(hints.autoRecall).toBeDefined();
    expect(hints.hybridSearch).toBeDefined();
    expect(hints.maxResults).toBeDefined();
    expect(hints.minScore).toBeDefined();
  });

  test("serviceToken is marked sensitive", () => {
    expect(oracleConfigSchema.uiHints.serviceToken.sensitive).toBe(true);
  });
});

describe("MEMORY_CATEGORIES", () => {
  test("contains all expected categories", () => {
    expect(MEMORY_CATEGORIES).toContain("preference");
    expect(MEMORY_CATEGORIES).toContain("fact");
    expect(MEMORY_CATEGORIES).toContain("decision");
    expect(MEMORY_CATEGORIES).toContain("entity");
    expect(MEMORY_CATEGORIES).toContain("other");
  });

  test("has exactly 5 categories", () => {
    expect(MEMORY_CATEGORIES.length).toBe(5);
  });
});
