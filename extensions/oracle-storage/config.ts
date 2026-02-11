export type OracleStorageConfig = {
  serviceUrl: string;
  serviceToken?: string;
  autoCapture: boolean;
  autoRecall: boolean;
  hybridSearch: boolean;
  maxResults: number;
  minScore: number;
};

export const MEMORY_CATEGORIES = ["preference", "fact", "decision", "entity", "other"] as const;

export type MemoryCategory = (typeof MEMORY_CATEGORIES)[number];

function resolveEnvVars(value: string): string {
  return value.replace(/\$\{([^}]+)\}/g, (_, envVar) => {
    const envValue = process.env[envVar];
    if (!envValue) {
      throw new Error(`Environment variable ${envVar} is not set`);
    }
    return envValue;
  });
}

export function parseConfig(raw: Record<string, unknown>): OracleStorageConfig {
  const serviceUrl = typeof raw.serviceUrl === "string" ? raw.serviceUrl : "http://localhost:8100";
  const serviceToken =
    typeof raw.serviceToken === "string" ? resolveEnvVars(raw.serviceToken) : undefined;

  return {
    serviceUrl,
    serviceToken,
    autoCapture: raw.autoCapture !== false,
    autoRecall: raw.autoRecall !== false,
    hybridSearch: raw.hybridSearch !== false,
    maxResults: typeof raw.maxResults === "number" ? raw.maxResults : 6,
    minScore: typeof raw.minScore === "number" ? raw.minScore : 0.3,
  };
}

export const oracleConfigSchema = {
  parse(value: unknown): OracleStorageConfig {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      return parseConfig({});
    }
    return parseConfig(value as Record<string, unknown>);
  },
  uiHints: {
    serviceUrl: {
      label: "Service URL",
      placeholder: "http://localhost:8100",
      help: "URL of the OracLaw Python sidecar service",
    },
    serviceToken: {
      label: "Service Token",
      sensitive: true,
      placeholder: "bearer-token-...",
      help: "Bearer token for authenticating with the sidecar service",
    },
    autoCapture: {
      label: "Auto-Capture",
      help: "Automatically capture important information from conversations",
    },
    autoRecall: {
      label: "Auto-Recall",
      help: "Automatically inject relevant memories into context",
    },
    hybridSearch: {
      label: "Hybrid Search",
      help: "Use hybrid keyword+vector search (vs pure vector)",
    },
    maxResults: {
      label: "Max Results",
      placeholder: "6",
      advanced: true,
    },
    minScore: {
      label: "Min Score",
      placeholder: "0.3",
      advanced: true,
    },
  },
};
