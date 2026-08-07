import type {
  ByokCredentials,
  CredentialsResult,
  JobResponse,
  JobResult,
  LatestRunsResponse,
  StagedUpload,
  UploadUrlResponse,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

let getAuthToken: (() => Promise<string | null>) | null = null;

export function setAuthTokenGetter(
  fn: (() => Promise<string | null>) | null,
): void {
  getAuthToken = fn;
}

async function authHeaders(): Promise<Record<string, string>> {
  if (!getAuthToken) return {};
  const token = await getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function submitCredentials(
  creds: ByokCredentials,
): Promise<CredentialsResult> {
  const res = await fetch(`${API_BASE}/api/credentials`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
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
  keepFindings: boolean,
): Promise<JobResponse> {
  const form = new FormData();
  form.append("domain", domain);
  if (cpcClass) form.append("cpc_class", cpcClass);
  form.append("keep_findings", String(keepFindings));
  profileFiles.forEach((f) => form.append("profile_files", f));
  domainFiles.forEach((f) => form.append("domain_files", f));

  const res = await fetch(`${API_BASE}/api/ingest`, {
    method: "POST",
    headers: { ...(await authHeaders()) },
    body: form,
  });
  if (!res.ok) {
    throw new Error(`Ingest failed: ${res.status}`);
  }
  return res.json();
}

export async function orchestrate(
  intent: string,
  selectedTitles: string[] = [],
  freshStart = false,
  staged?: StagedUpload,
): Promise<JobResponse> {
  const body: Record<string, unknown> = {
    intent,
    selected_titles: selectedTitles,
    fresh_start: freshStart,
  };
  if (staged) {
    body.profile_paths = staged.profile_paths;
    body.doc_paths = staged.doc_paths;
    body.domain = staged.domain;
    body.keep_findings = staged.keep_findings;
  }
  const res = await fetch(`${API_BASE}/api/orchestrate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Orchestrate failed: ${res.status}`);
  }
  return res.json();
}

export async function pollJob(jobId: string): Promise<JobResult> {
  const res = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}`, {
    headers: { ...(await authHeaders()) },
  });
  if (!res.ok) {
    throw new Error(`Poll failed: ${res.status}`);
  }
  return res.json();
}

export async function getLatestRuns(): Promise<LatestRunsResponse> {
  const res = await fetch(`${API_BASE}/api/runs/latest`, {
    headers: { ...(await authHeaders()) },
  });
  if (!res.ok) {
    throw new Error(`Fetching latest runs failed: ${res.status}`);
  }
  return res.json();
}

export async function requestUploadUrl(
  filename: string,
  fileSize: number,
): Promise<UploadUrlResponse> {
  const res = await fetch(`${API_BASE}/api/upload-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ filename, file_size: fileSize }),
  });
  if (!res.ok) {
    const text = await res.text();
    let message: string;
    try {
      const body = JSON.parse(text);
      message = body.error ?? text;
    } catch {
      message = text;
    }
    throw new Error(message);
  }
  return res.json();
}

export async function uploadToS3(
  file: File,
  resp: UploadUrlResponse,
): Promise<void> {
  const form = new FormData();
  for (const [key, value] of Object.entries(resp.presigned_post.fields)) {
    form.append(key, value);
  }
  form.append("file", file);

  const res = await fetch(resp.presigned_post.url, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail);
  }
}
