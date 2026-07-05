import type {
  ByokCredentials,
  CredentialsResult,
  JobResponse,
  JobResult,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function submitCredentials(
  creds: ByokCredentials,
): Promise<CredentialsResult> {
  const res = await fetch(`${API_BASE}/api/credentials`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      openrouter_api_key: creds.openrouterApiKey,
      neo4j_uri: creds.aura?.neo4jUri ?? "",
      neo4j_username: creds.aura?.neo4jUsername ?? "",
      neo4j_password: creds.aura?.neo4jPassword ?? "",
      neo4j_database: creds.aura?.neo4jDatabase ?? "",
      aura_instanceid: creds.aura?.auraInstanceId ?? "",
      aura_instancename: creds.aura?.auraInstanceName ?? "",
      exa_api_key: creds.exaApiKey,
      firecrawl_api_key: creds.firecrawlApiKey,
    }),
  });
  if (!res.ok) {
    const detail = await res.text();
    return {
      status: "error",
      openrouter_ok: false,
      neo4j_ok: false,
      openrouter_error: detail,
      neo4j_error: null,
    };
  }
  return res.json();
}

export async function triggerIngest(
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
    body: form,
  });
  if (!res.ok) {
    throw new Error(`Ingest failed: ${res.status}`);
  }
  return res.json();
}

export async function pollJob(jobId: string): Promise<JobResult> {
  const res = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}`);
  if (!res.ok) {
    throw new Error(`Poll failed: ${res.status}`);
  }
  return res.json();
}

export async function triggerGapAnalysis(): Promise<JobResponse> {
  const res = await fetch(`${API_BASE}/api/gaps`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    throw new Error(`Gap analysis failed: ${res.status}`);
  }
  return res.json();
}

export async function triggerIdeation(
  selectedNeeds: string[],
): Promise<JobResponse> {
  const res = await fetch(`${API_BASE}/api/ideate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selected_needs: selectedNeeds }),
  });
  if (!res.ok) {
    throw new Error(`Ideation failed: ${res.status}`);
  }
  return res.json();
}
