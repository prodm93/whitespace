import type {
  IdeationProposal,
  JobResult,
  LatestRunsResponse,
  UnmetNeed,
  UploadedFile,
} from "@/types";

export type Phase =
  | "input"
  | "ingesting"
  | "orchestrating"
  | "gap-results"
  | "ideation-results"
  | "blocked";

export interface WorkflowState {
  profileFiles: UploadedFile[];
  domainFiles: UploadedFile[];
  domain: string;
  cpcClass: string;
  keepFindings: boolean;
  submitting: boolean;
  error: string;
  phase: Phase;
  jobId: string;
  needs: UnmetNeed[];
  proposals: IdeationProposal[];
  blockedReason: string;
  ideateSubmitting: boolean;
  latestRuns: LatestRunsResponse | null;
  resumeDismissed: boolean;
  backAction: () => void;
  backLabel: string;
}

export interface WorkflowActions {
  setDomain: (v: string) => void;
  setCpcClass: (v: string) => void;
  setKeepFindings: (v: boolean) => void;
  setResumeDismissed: (v: boolean) => void;
  addProfile: (files: File[]) => void;
  removeProfile: (id: string) => void;
  addDomain: (files: File[]) => void;
  removeDomain: (id: string) => void;
  handleBuild: () => Promise<void>;
  handleIngestComplete: () => Promise<void>;
  handleOrchestrateComplete: (result: JobResult) => void;
  handleIdeate: (selectedTitles: string[]) => Promise<void>;
  handleFreshStart: () => Promise<void>;
  handleRetryIngest: () => void;
  handleRetryOrchestrate: () => void;
  goToInput: () => void;
  goToGapResults: () => void;
  handleResume: () => void;
}
