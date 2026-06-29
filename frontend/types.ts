export type DeploymentMode = "byok" | "saas";

export interface AuraCreds {
  neo4jUri: string;
  neo4jUsername: string;
  neo4jPassword: string;
  neo4jDatabase: string;
}

export interface ByokCredentials {
  openrouterApiKey: string;
  aura: AuraCreds | null;
  exaApiKey: string;
  firecrawlApiKey: string;
}

export interface Credentials {
  mode: DeploymentMode;
  byok: ByokCredentials | null;
}

export interface UploadedFile {
  id: string;
  file: File;
  name: string;
  size: number;
}

export type JobStatusValue = "pending" | "running" | "completed" | "failed";

export interface JobResponse {
  job_id: string;
  status: JobStatusValue;
}

export interface JobResult {
  job_id: string;
  status: JobStatusValue;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

export interface UnmetNeed {
  title: string;
  description: string;
  current_state: string;
  why_unmet: string;
  matching_skills: string[];
  provenance: string[];
}

export interface GapAnalysisResponse {
  needs: UnmetNeed[];
}

export interface IdeationProposal {
  title: string;
  problem_statement: string;
  technical_approach: string;
  why_this_person: string;
  differentiation_from_prior_art: string;
  limitations: string;
  provenance: string[];
  prior_art_notes: string | null;
}

export interface IdeationResponse {
  proposals: IdeationProposal[];
}

export type JobType = "ingest" | "gaps" | "ideation";
