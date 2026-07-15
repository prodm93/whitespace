export type DeploymentMode = "byok" | "saas";

export interface AuraCreds {
  neo4jUri: string;
  neo4jUsername: string;
  neo4jPassword: string;
  neo4jDatabase: string;
  auraInstanceId: string;
  auraInstanceName: string;
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

export interface CredentialsResult {
  status: string;
  openrouter_ok: boolean;
  neo4j_ok: boolean;
  openrouter_error: string | null;
  neo4j_error: string | null;
}

export interface UnmetNeed {
  title: string;
  description: string;
  current_state: string;
  why_unmet: string;
  matching_skills: string[];
  provenance: string[];
  scores: Record<string, number>;
  contributing_models: string[];
  critique_notes: string | null;
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
  scores: Record<string, number>;
  contributing_models: string[];
  critique_notes: string | null;
}

export interface OrchestrateResult {
  needs: UnmetNeed[];
  proposals: IdeationProposal[];
  status: "done" | "awaiting_selection" | "blocked";
  reason: string | null;
}

export interface GapRun {
  run_id: string;
  timestamp: string;
  needs: UnmetNeed[];
}

export interface IdeaRun {
  run_id: string;
  gap_run_id: string;
  selected_need_titles: string[];
  timestamp: string;
  proposals: IdeationProposal[];
}

export interface LatestRunsResponse {
  gap_run: GapRun | null;
  idea_runs: IdeaRun[];
}

export type JobType = "ingest" | "orchestrate";
