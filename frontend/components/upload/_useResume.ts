import { useCallback, useEffect, useState } from "react";
import type { IdeationProposal, LatestRunsResponse, UnmetNeed } from "@/types";
import { getLatestRuns } from "@/lib/api";
import type { Phase } from "./_workflowTypes";

interface ResumeResult {
  latestRuns: LatestRunsResponse | null;
  resumeDismissed: boolean;
  setResumeDismissed: (v: boolean) => void;
  handleResume: () => void;
}

export function useResume(
  setNeeds: (n: UnmetNeed[]) => void,
  setProposals: (p: IdeationProposal[]) => void,
  setPhase: (p: Phase) => void,
): ResumeResult {
  const [latestRuns, setLatestRuns] = useState<LatestRunsResponse | null>(null);
  const [resumeDismissed, setResumeDismissed] = useState(false);

  useEffect(() => {
    getLatestRuns()
      .then(setLatestRuns)
      .catch(() => {});
  }, []);

  const handleResume = useCallback(() => {
    if (!latestRuns?.gap_run) return;
    setNeeds(latestRuns.gap_run.needs);
    const latestIdea = latestRuns.idea_runs[0];
    if (latestIdea) {
      setProposals(latestIdea.proposals);
      setPhase("ideation-results");
    } else {
      setPhase("gap-results");
    }
    setResumeDismissed(true);
  }, [latestRuns, setNeeds, setProposals, setPhase]);

  return { latestRuns, resumeDismissed, setResumeDismissed, handleResume };
}
