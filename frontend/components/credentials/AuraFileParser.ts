import type { AuraCreds } from "@/types";

const REQUIRED_KEYS = [
  "NEO4J_URI",
  "NEO4J_USERNAME",
  "NEO4J_PASSWORD",
  "NEO4J_DATABASE",
] as const;

export function parseAuraFile(text: string): AuraCreds {
  const entries: Record<string, string> = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (line === "" || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim();
    if (key.length === 0) continue;
    entries[key] = value;
  }
  for (const key of REQUIRED_KEYS) {
    if (!entries[key] || entries[key].length === 0) {
      throw new Error(`Aura file missing required key: ${key}`);
    }
  }
  return {
    neo4jUri: entries["NEO4J_URI"],
    neo4jUsername: entries["NEO4J_USERNAME"],
    neo4jPassword: entries["NEO4J_PASSWORD"],
    neo4jDatabase: entries["NEO4J_DATABASE"],
    auraInstanceId: entries["AURA_INSTANCEID"] ?? "",
    auraInstanceName: entries["AURA_INSTANCENAME"] ?? "",
  };
}
