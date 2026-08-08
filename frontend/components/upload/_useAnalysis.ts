import { useCallback, useState } from "react";
import type { IdeationProposal, OrchestrateResult, UnmetNeed } from "@/types";
import type { JobResult } from "@/types";
import { orchestrate } from "@/lib/api";
import { buildIntent } from "./_workflowUpload";
import type { Phase } from "./_workflowTypes";

export interface AnalysisResult {
  needs: UnmetNeed[];
  setNeeds: (n: UnmetNeed[]) => void;
  proposals: IdeationProposal[];
  setProposals: (p: IdeationProposal[]) => void;
  blockedReason: string;
  ideateSubmitting: boolean;
  handleOrchestrateComplete: (result: JobResult) => void;
  handleIdeate: (selectedTitles: string[]) => Promise<void>;
  handleFreshStart: () => Promise<void>;
}

export function useAnalysis(
  domain: string,
  keepFindings: boolean,
  setPhase: (p: Phase) => void,
  setJobId: (id: string) => void,
  setError: (msg: string) => void,
): AnalysisResult {
  const [needs, setNeeds] = useState<UnmetNeed[]>([]);
  const [proposals, setProposals] = useState<IdeationProposal[]>([]);
  const [blockedReason, setBlockedReason] = useState("");
  const [ideateSubmitting, setIdeateSubmitting] = useState(false);

  const handleOrchestrateComplete = useCallback(
    (result: { result: Record<string, unknown> | null }) => {
      const data = result.result as OrchestrateResult | null;
      if (!data) {
        setBlockedReason("No result returned from the analysis.");
        setPhase("blocked");
        return;
      }
      if (data.status === "awaiting_selection") {
        setNeeds(data.needs);
        setPhase("gap-results");
      } else if (data.status === "done" && data.proposals.length > 0) {
        setProposals(data.proposals);
        setPhase("ideation-results");
      } else if (data.status === "blocked") {
        setBlockedReason(data.reason ?? "Analysis could not complete.");
        setPhase("blocked");
      } else {
        setBlockedReason("Analysis complete with no results. Check the logs.");
        setPhase("blocked");
      }
    },
    [setPhase],
  );

  const handleIdeate = useCallback(
    async (selectedTitles: string[]) => {
      setIdeateSubmitting(true);
      try {
        const job = await orchestrate(
          "Run ideation on my selected gaps.",
          selectedTitles,
        );
        setJobId(job.job_id);
        setPhase("orchestrating");
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to start ideation.",
        );
      } finally {
        setIdeateSubmitting(false);
      }
    },
    [setJobId, setPhase, setError],
  );

  const handleFreshStart = useCallback(async () => {
    try {
      const job = await orchestrate(
        buildIntent(domain, keepFindings, true),
        [],
        true,
      );
      setJobId(job.job_id);
      setPhase("orchestrating");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start fresh.",
      );
    }
  }, [domain, keepFindings, setJobId, setPhase, setError]);

  return {
    needs,
    setNeeds,
    proposals,
    setProposals,
    blockedReason,
    ideateSubmitting,
    handleOrchestrateComplete,
    handleIdeate,
    handleFreshStart,
  };
}
