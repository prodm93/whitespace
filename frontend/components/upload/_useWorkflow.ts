import { useCallback, useState } from "react";
import { useCredentials } from "@/context/CredentialsContext";
import { orchestrate, triggerIngest } from "@/lib/api";
import type { WorkflowActions, WorkflowState } from "./_workflowTypes";
import type { Phase } from "./_workflowTypes";
import { buildIntent, submitSaaS } from "./_workflowUpload";
import { useResume } from "./_useResume";
import { useFileList } from "./_useFileList";
import { useAnalysis } from "./_useAnalysis";

export function useWorkflow(): WorkflowState & WorkflowActions {
  const { credentials, reset: resetCredentials } = useCredentials();
  const {
    files: profileFiles,
    add: addProfile,
    remove: removeProfile,
  } = useFileList();
  const {
    files: domainFiles,
    add: addDomain,
    remove: removeDomain,
  } = useFileList();

  const [domain, setDomain] = useState("");
  const [cpcClass, setCpcClass] = useState("");
  const [keepFindings, setKeepFindings] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [phase, setPhase] = useState<Phase>("input");
  const [jobId, setJobId] = useState("");

  const analysis = useAnalysis(
    domain,
    keepFindings,
    setPhase,
    setJobId,
    setError,
  );
  const { latestRuns, resumeDismissed, setResumeDismissed, handleResume } =
    useResume(analysis.setNeeds, analysis.setProposals, setPhase);

  const handleBuild = useCallback(async () => {
    setError("");
    if (!domain.trim()) {
      setError("Enter a patent domain to search.");
      return;
    }
    if (profileFiles.length === 0) {
      setError("Upload at least one professional profile document.");
      return;
    }
    setSubmitting(true);
    try {
      if (credentials?.mode === "saas") {
        const job = await submitSaaS(
          profileFiles.map((f) => f.file),
          domainFiles.map((f) => f.file),
          domain,
          keepFindings,
        );
        setJobId(job.job_id);
        setPhase("orchestrating");
      } else {
        const result = await triggerIngest(
          domain,
          cpcClass,
          profileFiles.map((f) => f.file),
          domainFiles.map((f) => f.file),
          keepFindings,
        );
        setJobId(result.job_id);
        setPhase("ingesting");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }, [
    domain,
    cpcClass,
    profileFiles,
    domainFiles,
    keepFindings,
    credentials?.mode,
  ]);

  const handleIngestComplete = useCallback(async () => {
    try {
      const job = await orchestrate(buildIntent(domain, keepFindings));
      setJobId(job.job_id);
      setPhase("orchestrating");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start analysis.",
      );
      setPhase("input");
    }
  }, [domain, keepFindings]);

  const handleRetryIngest = useCallback(() => {
    setPhase("input");
    setJobId("");
  }, []);
  const handleRetryOrchestrate = useCallback(() => {
    setPhase(analysis.needs.length > 0 ? "gap-results" : "input");
    setJobId("");
  }, [analysis.needs.length]);
  const goToInput = useCallback(() => {
    setPhase("input");
    setJobId("");
    setError("");
  }, []);
  const goToGapResults = useCallback(() => {
    setPhase("gap-results");
    setJobId("");
  }, []);

  const backAction =
    phase === "input"
      ? resetCredentials
      : phase === "ideation-results"
        ? goToGapResults
        : goToInput;
  const backLabel =
    phase === "input"
      ? "Credentials"
      : phase === "ideation-results"
        ? "Gap results"
        : "Back";

  return {
    profileFiles,
    domainFiles,
    domain,
    cpcClass,
    keepFindings,
    submitting,
    error,
    phase,
    jobId,
    needs: analysis.needs,
    proposals: analysis.proposals,
    blockedReason: analysis.blockedReason,
    ideateSubmitting: analysis.ideateSubmitting,
    latestRuns,
    resumeDismissed,
    backAction,
    backLabel,
    setDomain,
    setCpcClass,
    setKeepFindings,
    setResumeDismissed,
    addProfile,
    removeProfile,
    addDomain,
    removeDomain,
    handleBuild,
    handleIngestComplete,
    handleOrchestrateComplete: analysis.handleOrchestrateComplete,
    handleIdeate: analysis.handleIdeate,
    handleFreshStart: analysis.handleFreshStart,
    handleRetryIngest,
    handleRetryOrchestrate,
    goToInput,
    goToGapResults,
    handleResume,
  };
}
