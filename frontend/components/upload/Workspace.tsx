"use client";

import { useCallback, useState } from "react";
import type {
  GapAnalysisResponse,
  IdeationProposal,
  IdeationResponse,
  JobResult,
  UnmetNeed,
  UploadedFile,
} from "@/types";
import { useCredentials } from "@/context/CredentialsContext";
import {
  triggerGapAnalysis,
  triggerIdeation,
  triggerIngest,
} from "@/lib/api";
import DropZone, { nextId } from "./DropZone";
import SearchPanel from "@/components/search/SearchPanel";
import JobProgress from "@/components/jobs/JobProgress";
import GapResults from "@/components/gaps/GapResults";
import IdeationResults from "@/components/ideation/IdeationResults";

type Phase =
  | "input"
  | "ingesting"
  | "gap-running"
  | "gap-results"
  | "ideation-running"
  | "ideation-results";

function toUploadedFile(file: File): UploadedFile {
  return { id: nextId(), file, name: file.name, size: file.size };
}

export default function Workspace() {
  const { credentials } = useCredentials();
  const byok = credentials?.byok ?? null;

  const [profileFiles, setProfileFiles] = useState<UploadedFile[]>([]);
  const [domainFiles, setDomainFiles] = useState<UploadedFile[]>([]);
  const [domain, setDomain] = useState("");
  const [cpcClass, setCpcClass] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [phase, setPhase] = useState<Phase>("input");
  const [jobId, setJobId] = useState("");
  const [needs, setNeeds] = useState<UnmetNeed[]>([]);
  const [proposals, setProposals] = useState<IdeationProposal[]>([]);
  const [ideateSubmitting, setIdeateSubmitting] = useState(false);

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
        byok,
        domain,
        cpcClass,
        profileFiles.map((f) => f.file),
        domainFiles.map((f) => f.file),
      );
      setJobId(result.job_id);
      setPhase("ingesting");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }, [byok, domain, cpcClass, profileFiles, domainFiles]);

  const handleIngestComplete = useCallback(async () => {
    try {
      const gapJob = await triggerGapAnalysis(byok);
      setJobId(gapJob.job_id);
      setPhase("gap-running");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start gap analysis.");
      setPhase("input");
    }
  }, [byok]);

  const handleGapComplete = useCallback((result: JobResult) => {
    const data = result.result as GapAnalysisResponse | null;
    setNeeds(data?.needs ?? []);
    setPhase("gap-results");
  }, []);

  const handleIdeate = useCallback(async (selectedTitles: string[]) => {
    setIdeateSubmitting(true);
    try {
      const job = await triggerIdeation(byok, selectedTitles);
      setJobId(job.job_id);
      setPhase("ideation-running");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start ideation.");
    } finally {
      setIdeateSubmitting(false);
    }
  }, [byok]);

  const handleIdeationComplete = useCallback((result: JobResult) => {
    const data = result.result as IdeationResponse | null;
    setProposals(data?.proposals ?? []);
    setPhase("ideation-results");
  }, []);

  const handleRetryIngest = useCallback(() => {
    setPhase("input");
    setJobId("");
  }, []);

  const handleRetryGaps = useCallback(async () => {
    try {
      const gapJob = await triggerGapAnalysis(byok);
      setJobId(gapJob.job_id);
      setPhase("gap-running");
    } catch {
      setPhase("input");
    }
  }, [byok]);

  const handleRetryIdeation = useCallback(() => {
    setPhase("gap-results");
    setJobId("");
  }, []);

  if (phase === "ingesting") {
    return (
      <JobProgress
        jobId={jobId}
        jobType="ingest"
        onComplete={handleIngestComplete}
        onRetry={handleRetryIngest}
      />
    );
  }

  if (phase === "gap-running") {
    return (
      <JobProgress
        jobId={jobId}
        jobType="gaps"
        onComplete={handleGapComplete}
        onRetry={handleRetryGaps}
      />
    );
  }

  if (phase === "gap-results") {
    return (
      <GapResults
        needs={needs}
        onIdeate={handleIdeate}
        submitting={ideateSubmitting}
      />
    );
  }

  if (phase === "ideation-running") {
    return (
      <JobProgress
        jobId={jobId}
        jobType="ideation"
        onComplete={handleIdeationComplete}
        onRetry={handleRetryIdeation}
      />
    );
  }

  if (phase === "ideation-results") {
    return <IdeationResults proposals={proposals} />;
  }

  return (
    <section className="workspace">
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
        onDomainChange={setDomain}
        onCpcChange={setCpcClass}
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
