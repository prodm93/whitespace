"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { JobResult, JobStatusValue, JobType } from "@/types";
import { useCredentials } from "@/context/CredentialsContext";
import { pollJob } from "@/lib/api";
import { useGraphAnimation } from "@/animations/useGraphAnimation";

const STATUS_LABELS: Record<JobType, Record<JobStatusValue, string>> = {
  ingest: {
    pending: "Preparing…",
    running: "Building knowledge graph…",
    completed: "Graph built",
    failed: "Build failed",
  },
  gaps: {
    pending: "Preparing council…",
    running: "Analysing gaps…",
    completed: "Analysis complete",
    failed: "Analysis failed",
  },
  ideation: {
    pending: "Preparing council…",
    running: "Generating ideas…",
    completed: "Ideas ready",
    failed: "Generation failed",
  },
};

interface JobProgressProps {
  jobId: string;
  jobType: JobType;
  onComplete: (result: JobResult) => void;
  onRetry: () => void;
}

export default function JobProgress({
  jobId,
  jobType,
  onComplete,
  onRetry,
}: JobProgressProps) {
  const { credentials } = useCredentials();
  const [status, setStatus] = useState<JobStatusValue>("pending");
  const [error, setError] = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const svgRef = useGraphAnimation();

  const doPoll = useCallback(async () => {
    try {
      const result = await pollJob(credentials?.byok ?? null, jobId);
      setStatus(result.status);

      if (result.status === "completed") {
        if (intervalRef.current) clearInterval(intervalRef.current);
        onComplete(result);
      } else if (result.status === "failed") {
        if (intervalRef.current) clearInterval(intervalRef.current);
        setError(result.error ?? "Job failed unexpectedly.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Polling error");
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
  }, [credentials, jobId, onComplete]);

  useEffect(() => {
    doPoll();
    intervalRef.current = setInterval(doPoll, 2000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [doPoll]);

  const label = STATUS_LABELS[jobType][status];

  return (
    <section className="job-progress">
      <svg
        ref={svgRef}
        className="job-progress__svg"
        viewBox="0 0 200 120"
        aria-hidden="true"
      >
        {/* Nodes */}
        <circle className="graph-dot" cx="30" cy="60" r="3.5" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="100" cy="28" r="3" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="100" cy="92" r="3" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="170" cy="60" r="3.5" fill="var(--text-primary)" />

        {/* Edges */}
        <path
          className="graph-edge"
          d="M 30,60 C 55,30 75,28 100,28"
          fill="none"
          stroke="var(--stroke-cream)"
          strokeWidth="1"
        />
        <path
          className="graph-edge"
          d="M 30,60 C 55,90 75,92 100,92"
          fill="none"
          stroke="var(--stroke-cream)"
          strokeWidth="1"
        />
        <path
          className="graph-edge"
          d="M 100,28 C 125,28 145,40 170,60"
          fill="none"
          stroke="var(--stroke-cream)"
          strokeWidth="1"
        />
        <path
          className="graph-edge"
          d="M 100,92 C 125,92 145,80 170,60"
          fill="none"
          stroke="var(--stroke-cream)"
          strokeWidth="1"
        />

        {/* Travelling dots */}
        <circle className="graph-traveller" r="2" fill="var(--accent)" opacity="0" />
        <circle className="graph-traveller" r="2" fill="var(--accent)" opacity="0" />
        <circle className="graph-traveller" r="2" fill="var(--accent)" opacity="0" />
        <circle className="graph-traveller" r="2" fill="var(--accent)" opacity="0" />
      </svg>

      <p className="job-progress__label">{label}</p>

      {(status === "pending" || status === "running") && (
        <p className="job-progress__hint">This may take a few minutes.</p>
      )}

      {status === "failed" && (
        <div className="job-progress__failure">
          <p className="job-progress__error">{error}</p>
          <button
            className="job-progress__retry"
            onClick={onRetry}
            type="button"
          >
            Retry
          </button>
        </div>
      )}

      <style jsx>{`
        .job-progress {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 20px;
          padding: 64px var(--margin);
          max-width: 480px;
          margin: 0 auto;
          text-align: center;
        }
        .job-progress__svg {
          width: 200px;
          height: 120px;
        }
        .job-progress__label {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h2);
          font-weight: 400;
          color: var(--text-primary);
        }
        .job-progress__hint {
          font-size: var(--text-caption);
          color: var(--text-muted);
        }
        .job-progress__failure {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 16px;
        }
        .job-progress__error {
          font-size: var(--text-caption);
          color: #c25a5a;
          max-width: 360px;
        }
        .job-progress__retry {
          padding: 10px 32px;
          font-family: "Inter", sans-serif;
          font-size: var(--text-body);
          font-weight: 400;
          color: var(--text-primary);
          background: var(--accent);
          border-radius: var(--radius-md);
          transition: box-shadow 0.2s var(--ease-out);
        }
        .job-progress__retry:hover {
          box-shadow: 0 0 24px var(--accent-glow);
        }
      `}</style>
    </section>
  );
}
