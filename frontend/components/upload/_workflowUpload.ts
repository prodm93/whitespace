import { orchestrate, requestUploadUrl, uploadToS3 } from "@/lib/api";

export function buildIntent(
  domain: string,
  keepFindings: boolean,
  fresh = false,
): string {
  const base =
    `Profile and domain documents uploaded. Domain is '${domain}'. ` +
    `keep_findings is ${keepFindings}. Run gap analysis.`;
  return fresh ? `${base}, ignoring prior memory.` : base;
}

export async function uploadFilesSequentially(
  files: File[],
): Promise<string[]> {
  const keys: string[] = [];
  for (const f of files) {
    const resp = await requestUploadUrl(f.name, f.size);
    await uploadToS3(f, resp);
    keys.push(resp.s3_key);
  }
  return keys;
}

export async function submitSaaS(
  profileRawFiles: File[],
  domainRawFiles: File[],
  domain: string,
  keepFindings: boolean,
) {
  const profileKeys = await uploadFilesSequentially(profileRawFiles);
  const docKeys = await uploadFilesSequentially(domainRawFiles);
  return orchestrate(buildIntent(domain, keepFindings), [], false, {
    profile_paths: profileKeys,
    doc_paths: docKeys,
    domain,
    keep_findings: keepFindings,
  });
}
