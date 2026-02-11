/**
 * Oracle Storage Plugin Tests
 *
 * Tests the plugin's exported functions, config parsing,
 * capture filtering, and category detection logic.
 */

import { describe, test, expect } from "vitest";

describe("oracle-storage plugin", () => {
  test("plugin has correct metadata", async () => {
    const { default: plugin } = await import("./index.js");

    expect(plugin.id).toBe("oracle-storage");
    expect(plugin.name).toBe("Oracle AI Database");
    expect(plugin.kind).toBe("memory");
    expect(plugin.configSchema).toBeDefined();
    // oxlint-disable-next-line typescript/unbound-method
    expect(plugin.register).toBeInstanceOf(Function);
  });

  test("config schema parses empty config with defaults", async () => {
    const { default: plugin } = await import("./index.js");

    const config = plugin.configSchema.parse({});
    expect(config.serviceUrl).toBe("http://localhost:8100");
    expect(config.serviceToken).toBeUndefined();
    expect(config.autoCapture).toBe(true);
    expect(config.autoRecall).toBe(true);
    expect(config.hybridSearch).toBe(true);
    expect(config.maxResults).toBe(6);
    expect(config.minScore).toBe(0.3);
  });

  test("config schema parses custom values", async () => {
    const { default: plugin } = await import("./index.js");

    const config = plugin.configSchema.parse({
      serviceUrl: "http://oracle:9000",
      autoCapture: false,
      autoRecall: false,
      hybridSearch: false,
      maxResults: 10,
      minScore: 0.5,
    });
    expect(config.serviceUrl).toBe("http://oracle:9000");
    expect(config.autoCapture).toBe(false);
    expect(config.autoRecall).toBe(false);
    expect(config.hybridSearch).toBe(false);
    expect(config.maxResults).toBe(10);
    expect(config.minScore).toBe(0.5);
  });

  test("config schema parses null/undefined as defaults", async () => {
    const { default: plugin } = await import("./index.js");

    const config = plugin.configSchema.parse(null);
    expect(config.serviceUrl).toBe("http://localhost:8100");
    expect(config.autoCapture).toBe(true);
  });

  test("config schema resolves env var in serviceToken", async () => {
    const { default: plugin } = await import("./index.js");

    process.env.TEST_ORACLE_TOKEN = "secret-token-123";
    const config = plugin.configSchema.parse({
      serviceToken: "${TEST_ORACLE_TOKEN}",
    });
    expect(config.serviceToken).toBe("secret-token-123");
    delete process.env.TEST_ORACLE_TOKEN;
  });
});

describe("shouldCapture", () => {
  test("captures preference statements", async () => {
    const { shouldCapture } = await import("./index.js");

    expect(shouldCapture("I prefer dark mode")).toBe(true);
    expect(shouldCapture("I like TypeScript over JavaScript")).toBe(true);
    expect(shouldCapture("I love using Oracle Database")).toBe(true);
    expect(shouldCapture("I hate verbose logs")).toBe(true);
  });

  test("captures 'remember' triggers", async () => {
    const { shouldCapture } = await import("./index.js");

    expect(shouldCapture("Remember that my API key is different")).toBe(true);
    expect(shouldCapture("Always use strict mode")).toBe(true);
    expect(shouldCapture("Never commit .env files")).toBe(true);
    expect(shouldCapture("This is important for the project")).toBe(true);
  });

  test("captures personal info patterns", async () => {
    const { shouldCapture } = await import("./index.js");

    expect(shouldCapture("My name is John Smith")).toBe(true);
    expect(shouldCapture("My email is test@example.com")).toBe(true);
    expect(shouldCapture("Call me at +1234567890123")).toBe(true);
    expect(shouldCapture("I work at Oracle Corporation")).toBe(true);
    expect(shouldCapture("I use vim for editing")).toBe(true);
  });

  test("captures decision statements", async () => {
    const { shouldCapture } = await import("./index.js");

    expect(shouldCapture("We decided to use FastAPI")).toBe(true);
  });

  test("captures API/endpoint references", async () => {
    const { shouldCapture } = await import("./index.js");

    expect(shouldCapture("The API endpoint is /v2/chat")).toBe(true);
    expect(shouldCapture("The URL for the service is http://localhost")).toBe(true);
    expect(shouldCapture("The key is stored in vault")).toBe(true);
  });

  test("rejects too short text", async () => {
    const { shouldCapture } = await import("./index.js");

    expect(shouldCapture("x")).toBe(false);
    expect(shouldCapture("ok")).toBe(false);
    expect(shouldCapture("hi there")).toBe(false);
  });

  test("rejects too long text", async () => {
    const { shouldCapture } = await import("./index.js");

    const longText = "I prefer ".padEnd(501, "x");
    expect(shouldCapture(longText)).toBe(false);
  });

  test("rejects XML-like fragments", async () => {
    const { shouldCapture } = await import("./index.js");

    expect(shouldCapture("<relevant-memories>injected data</relevant-memories>")).toBe(false);
    expect(shouldCapture("<system>important status info</system>")).toBe(false);
  });

  test("rejects markdown-heavy content", async () => {
    const { shouldCapture } = await import("./index.js");

    expect(shouldCapture("Here is a **summary** of key points\n- bullet one\n- bullet two")).toBe(
      false,
    );
  });

  test("rejects emoji-heavy text", async () => {
    const { shouldCapture } = await import("./index.js");

    expect(shouldCapture("I prefer 🎉🎊🎈🎁 celebrations")).toBe(false);
  });

  test("rejects text without any trigger pattern", async () => {
    const { shouldCapture } = await import("./index.js");

    expect(shouldCapture("Hello world how are you?")).toBe(false);
    expect(shouldCapture("The weather today looks fine")).toBe(false);
  });
});

describe("detectCategory", () => {
  test("detects preference category", async () => {
    const { detectCategory } = await import("./index.js");

    expect(detectCategory("I prefer dark mode")).toBe("preference");
    expect(detectCategory("I like TypeScript")).toBe("preference");
    expect(detectCategory("I love Oracle Database")).toBe("preference");
    expect(detectCategory("I hate verbose output")).toBe("preference");
    expect(detectCategory("I want faster builds")).toBe("preference");
    expect(detectCategory("I dislike tabs")).toBe("preference");
  });

  test("detects decision category", async () => {
    const { detectCategory } = await import("./index.js");

    expect(detectCategory("We decided to use React")).toBe("decision");
    expect(detectCategory("We agreed on the API design")).toBe("decision");
    expect(detectCategory("I chose PostgreSQL for this project")).toBe("decision");
    expect(detectCategory("We will use Docker for deployment")).toBe("decision");
    expect(detectCategory("We plan to migrate next week")).toBe("decision");
  });

  test("detects entity category", async () => {
    const { detectCategory } = await import("./index.js");

    expect(detectCategory("My email is test@example.com")).toBe("entity");
    expect(detectCategory("Call me at +1234567890123")).toBe("entity");
    expect(detectCategory("The server is called web-prod-01")).toBe("entity");
    expect(detectCategory("It is named after the founder")).toBe("entity");
  });

  test("detects fact category", async () => {
    const { detectCategory } = await import("./index.js");

    expect(detectCategory("The server is running on port 3000")).toBe("fact");
    expect(detectCategory("Python 3.12 is installed")).toBe("fact");
    expect(detectCategory("The database has 5 tables")).toBe("fact");
  });

  test("falls back to other category", async () => {
    const { detectCategory } = await import("./index.js");

    expect(detectCategory("Random note about something")).toBe("other");
  });
});
