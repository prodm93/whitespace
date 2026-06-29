import type {
  ByokCredentials,
  JobResponse,
  JobResult,
  ValidationResult,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function credentialHeaders(creds: ByokCredentials): Record<string, string> {
  return {
    "X-OpenRouter-Key": creds.openrouterApiKey,
    ...(creds.aura
      ? {
          "X-Neo4j-Uri": creds.aura.neo4jUri,
          "X-Neo4j-Username": creds.aura.neo4jUsername,
          "X-Neo4j-Password": creds.aura.neo4jPassword,
          "X-Neo4j-Database": creds.aura.neo4jDatabase,
        }
      : {}),
  };
}

function authHeaders(creds: ByokCredentials | null): Record<string, string> {
  return creds ? credentialHeaders(creds) : {};
}

export async function validateCredentials(
  creds: ByokCredentials,
): Promise<ValidationResult> {
  const res = await fetch(`${API_BASE}/api/credentials/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...credentialHeaders(creds) },
    body: JSON.stringify({
      openrouter_api_key: creds.openrouterApiKey,
      neo4j_uri: creds.aura?.neo4jUri ?? "",
      neo4j_username: creds.aura?.neo4jUsername ?? "",
      neo4j_password: creds.aura?.neo4jPassword ?? "",
      neo4j_database: creds.aura?.neo4jDatabase ?? "",
      exa_api_key: creds.exaApiKey,
      firecrawl_api_key: creds.firecrawlApiKey,
    }),
  });
  if (!res.ok) {
    return { valid: false, error: `Server error: ${res.status}` };
  }
  return res.json();
}

export async function triggerIngest(
  creds: ByokCredentials | null,
  domain: string,
  cpcClass: string,
  profileFiles: File[],
  domainFiles: File[],
): Promise<JobResponse> {
  const form = new FormData();
  form.append("domain", domain);
  if (cpcClass) form.append("cpc_class", cpcClass);
  profileFiles.forEach((f) => form.append("profile_files", f));
  domainFiles.forEach((f) => form.append("domain_files", f));

  const res = await fetch(`${API_BASE}/api/ingest`, {
    method: "POST",
    headers: authHeaders(creds),
    body: form,
  });
  if (!res.ok) {
    throw new Error(`Ingest failed: ${res.status}`);
  }
  return res.json();
}

export async function pollJob(
  creds: ByokCredentials | null,
  jobId: string,
): Promise<JobResult> {
  const res = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}`, {
    headers: authHeaders(creds),
  });
  if (!res.ok) {
    throw new Error(`Poll failed: ${res.status}`);
  }
  return res.json();
}

export async function triggerGapAnalysis(
  creds: ByokCredentials | null,
): Promise<JobResponse> {
  const res = await fetch(`${API_BASE}/api/gaps`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(creds) },
    body: JSON.stringify({ credentials: creds }),
  });
  if (!res.ok) {
    throw new Error(`Gap analysis failed: ${res.status}`);
  }
  return res.json();
}

export async function triggerIdeation(
  creds: ByokCredentials | null,
  selectedNeeds: string[],
): Promise<JobResponse> {
  const res = await fetch(`${API_BASE}/api/ideate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(creds) },
    body: JSON.stringify({
      selected_needs: selectedNeeds,
      credentials: creds,
    }),
  });
  if (!res.ok) {
    throw new Error(`Ideation failed: ${res.status}`);
  }
  return res.json();
}
