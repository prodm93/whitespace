"use client";

import { useCallback, useEffect, useState } from "react";
import { useCredentials } from "@/context/CredentialsContext";
import type {
  IdeationProposal,
  JobResult,
  LatestRunsResponse,
  OrchestrateResult,
  UnmetNeed,
  UploadedFile,
} from "@/types";
import { getLatestRuns, orchestrate, triggerIngest } from "@/lib/api";
import DropZone, { nextId } from "./DropZone";
import SearchPanel from "@/components/search/SearchPanel";
import JobProgress from "@/components/jobs/JobProgress";
import GapResults from "@/components/gaps/GapResults";
import IdeationResults from "@/components/ideation/IdeationResults";

type Phase =
  | "input"
  | "ingesting"
  | "orchestrating"
  | "gap-results"
  | "ideation-results"
  | "blocked";

function toUploadedFile(file: File): UploadedFile {
  return { id: nextId(), file, name: file.name, size: file.size };
}

export default function Workspace() {
  const { reset: resetCredentials } = useCredentials();
  const [profileFiles, setProfileFiles] = useState<UploadedFile[]>([]);
  const [domainFiles, setDomainFiles] = useState<UploadedFile[]>([]);
  const [domain, setDomain] = useState("");
  const [cpcClass, setCpcClass] = useState("");
  const [keepFindings, setKeepFindings] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [phase, setPhase] = useState<Phase>("input");
  const [jobId, setJobId] = useState("");
  const [needs, setNeeds] = useState<UnmetNeed[]>([]);
  const [proposals, setProposals] = useState<IdeationProposal[]>([]);
  const [blockedReason, setBlockedReason] = useState("");
  const [ideateSubmitting, setIdeateSubmitting] = useState(false);
  const [latestRuns, setLatestRuns] = useState<LatestRunsResponse | null>(null);
  const [resumeDismissed, setResumeDismissed] = useState(false);

  useEffect(() => {
    getLatestRuns()
      .then(setLatestRuns)
      .catch(() => {
        // Rehydration is best-effort: no prior run, or the store isn't
        // reachable yet. Either way the guided flow below still works.
      });
  }, []);

  const addProfile = useCallback((files: File[]) => {
    setProfileFiles((prev) => [...prev, ...files.map(toUploadedFile)]);
  }, []);
  const removeProfile = useCallback((id: string) => {
    setProfileFiles((prev) => prev.filter((f) => f.id !== id));
  }, []);
  const addDomain = useCallback((files: File[]) => {
    setDomainFiles((prev) => [...prev, ...files.map(toUploadedFile)]);
  }, []);
  const removeDomain = useCallback((id: string) => {
    setDomainFiles((prev) => prev.filter((f) => f.id !== id));
  }, []);

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
      const result = await triggerIngest(
        domain,
        cpcClass,
        profileFiles.map((f) => f.file),
        domainFiles.map((f) => f.file),
        keepFindings,
      );
      setJobId(result.job_id);
      setPhase("ingesting");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }, [domain, cpcClass, profileFiles, domainFiles, keepFindings]);

  const handleIngestComplete = useCallback(async () => {
    const intent =
      `Profile and domain documents uploaded. Domain is '${domain}'. ` +
      `keep_findings is ${keepFindings}. Run gap analysis.`;
    try {
      const job = await orchestrate(intent);
      setJobId(job.job_id);
      setPhase("orchestrating");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start analysis.");
      setPhase("input");
    }
  }, [domain, keepFindings]);

  const handleOrchestrateComplete = useCallback((result: JobResult) => {
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
  }, []);

  const handleIdeate = useCallback(async (selectedTitles: string[]) => {
    setIdeateSubmitting(true);
    try {
      const job = await orchestrate("Run ideation on my selected gaps.", selectedTitles);
      setJobId(job.job_id);
      setPhase("orchestrating");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start ideation.");
    } finally {
      setIdeateSubmitting(false);
    }
  }, []);

  const handleFreshStart = useCallback(async () => {
    const intent =
      `Profile and domain documents uploaded. Domain is '${domain}'. ` +
      `keep_findings is ${keepFindings}. Run gap analysis., ignoring prior memory.`;
    try {
      const job = await orchestrate(intent, [], true);
      setJobId(job.job_id);
      setPhase("orchestrating");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start fresh.");
    }
  }, [domain, keepFindings]);

  const handleRetryIngest = useCallback(() => {
    setPhase("input");
    setJobId("");
  }, []);

  const handleRetryOrchestrate = useCallback(() => {
    if (needs.length > 0) {
      setPhase("gap-results");
    } else {
      setPhase("input");
    }
    setJobId("");
  }, [needs.length]);

  const goToInput = useCallback(() => {
    setPhase("input");
    setJobId("");
    setError("");
  }, []);

  const goToGapResults = useCallback(() => {
    setPhase("gap-results");
    setJobId("");
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
  }, [latestRuns]);

  let backAction: () => void;
  let backLabel: string;

  if (phase === "input") {
    backAction = resetCredentials;
    backLabel = "Credentials";
  } else if (phase === "ideation-results") {
    backAction = goToGapResults;
    backLabel = "Gap results";
  } else if (phase === "blocked") {
    backAction = goToInput;
    backLabel = "Back";
  } else {
    backAction = goToInput;
    backLabel = "Back";
  }

  let content: React.ReactNode;

  if (phase === "ingesting") {
    content = (
      <JobProgress
        jobId={jobId}
        jobType="ingest"
        onComplete={handleIngestComplete}
        onRetry={handleRetryIngest}
      />
    );
  } else if (phase === "orchestrating") {
    content = (
      <JobProgress
        jobId={jobId}
        jobType="orchestrate"
        onComplete={handleOrchestrateComplete}
        onRetry={handleRetryOrchestrate}
      />
    );
  } else if (phase === "gap-results") {
    content = (
      <GapResults
        needs={needs}
        onIdeate={handleIdeate}
        onFreshStart={handleFreshStart}
        submitting={ideateSubmitting}
      />
    );
  } else if (phase === "ideation-results") {
    content = <IdeationResults proposals={proposals} />;
  } else if (phase === "blocked") {
    content = (
      <section className="workspace-blocked">
        <p className="workspace-blocked__reason">{blockedReason}</p>
        <button
          className="workspace-blocked__back"
          onClick={goToInput}
          type="button"
        >
          Back to start
        </button>
        <style jsx>{`
          .workspace-blocked {
            padding: 96px var(--margin);
            max-width: 560px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 28px;
            text-align: center;
          }
          .workspace-blocked__reason {
            font-size: var(--text-body);
            color: var(--text-secondary);
            line-height: 1.6;
          }
          .workspace-blocked__back {
            padding: 12px 36px;
            font-family: "Inter", sans-serif;
            font-size: var(--text-body);
            font-weight: 400;
            color: var(--text-primary);
            background: var(--accent);
            border-radius: var(--radius-md);
            transition: box-shadow 0.2s var(--ease-out);
          }
          .workspace-blocked__back:hover {
            box-shadow: 0 0 24px var(--accent-glow);
          }
        `}</style>
      </section>
    );
  } else {
    content = (
      <section className="workspace">
        {latestRuns?.gap_run && !resumeDismissed && (
          <div className="workspace__resume">
            <span className="workspace__resume-text">
              You have a previous analysis from{" "}
              {new Date(latestRuns.gap_run.timestamp).toLocaleString()}.
            </span>
            <div className="workspace__resume-actions">
              <button
                className="workspace__resume-yes"
                onClick={handleResume}
                type="button"
              >
                Resume where you left off
              </button>
              <button
                className="workspace__resume-dismiss"
                onClick={() => setResumeDismissed(true)}
                type="button"
              >
                Start fresh
              </button>
            </div>
          </div>
        )}

        <div className="workspace__zones">
          <DropZone
            label="Your professional profile"
            description="Upload your resume, CV, publications, or project descriptions. Multiple files build a richer profile."
            files={profileFiles}
            onAdd={addProfile}
            onRemove={removeProfile}
          />
          <DropZone
            label="Domain documents"
            description="Optional. Patent PDFs, technical papers, or discovery write-ups to supplement the automated search."
            files={domainFiles}
            onAdd={addDomain}
            onRemove={removeDomain}
          />
        </div>

        <SearchPanel
          domain={domain}
          cpcClass={cpcClass}
          keepFindings={keepFindings}
          onDomainChange={setDomain}
          onCpcChange={setCpcClass}
          onKeepFindingsChange={setKeepFindings}
        />

        {error && <p className="workspace__error">{error}</p>}

        <button
          className="workspace__build"
          onClick={handleBuild}
          disabled={submitting}
          type="button"
        >
          {submitting ? "Building…" : "Build knowledge graph"}
        </button>

        <style jsx>{`
          .workspace {
            padding: 48px var(--margin) 96px;
            max-width: 960px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 36px;
          }
          .workspace__resume {
            padding: 20px 24px;
            border: 1px solid var(--accent-dim);
            border-radius: var(--radius-md);
            background: rgba(138, 69, 112, 0.06);
            display: flex;
            flex-direction: column;
            gap: 14px;
            align-items: center;
            text-align: center;
          }
          .workspace__resume-text {
            font-size: var(--text-caption);
            color: var(--text-secondary);
          }
          .workspace__resume-actions {
            display: flex;
            gap: 12px;
          }
          .workspace__resume-yes {
            padding: 8px 20px;
            font-size: var(--text-caption);
            color: var(--text-primary);
            background: var(--accent);
            border-radius: var(--radius-md);
            transition: box-shadow 0.2s var(--ease-out);
          }
          .workspace__resume-yes:hover {
            box-shadow: 0 0 24px var(--accent-glow);
          }
          .workspace__resume-dismiss {
            padding: 8px 20px;
            font-size: var(--text-caption);
            color: var(--text-secondary);
            border: 1px solid var(--stroke-lavender);
            border-radius: var(--radius-md);
            transition: border-color 0.2s var(--ease-out);
          }
          .workspace__resume-dismiss:hover {
            border-color: var(--accent);
          }
          .workspace__zones {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: var(--gutter);
          }
          .workspace__error {
            font-size: var(--text-caption);
            color: #c25a5a;
            text-align: center;
          }
          .workspace__build {
            align-self: center;
            padding: 16px 48px;
            font-family: "Inter", sans-serif;
            font-size: var(--text-body);
            font-weight: 400;
            color: var(--text-primary);
            background: var(--accent);
            border-radius: var(--radius-md);
            transition: opacity 0.2s var(--ease-out),
              box-shadow 0.2s var(--ease-out);
          }
          .workspace__build:hover:not(:disabled) {
            box-shadow: 0 0 24px var(--accent-glow);
          }
          .workspace__build:disabled {
            opacity: 0.5;
            cursor: not-allowed;
          }
          @media (max-width: 600px) {
            .workspace__zones {
              grid-template-columns: 1fr;
            }
          }
        `}</style>
      </section>
    );
  }

  return (
    <>
      <button
        className="workspace__back"
        onClick={backAction}
        type="button"
      >
        &larr; {backLabel}
      </button>
      {content}
      <style jsx>{`
        .workspace__back {
          position: fixed;
          top: 80px;
          left: var(--margin);
          font-family: "Inter", sans-serif;
          font-size: var(--text-caption);
          color: var(--text-muted);
          background: none;
          border: none;
          cursor: pointer;
          z-index: 10;
          transition: color 0.2s var(--ease-out);
        }
        .workspace__back:hover {
          color: var(--text-primary);
        }
      `}</style>
    </>
  );
}
