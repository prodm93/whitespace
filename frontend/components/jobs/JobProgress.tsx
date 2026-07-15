"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { JobResult, JobStatusValue, JobType } from "@/types";
import { pollJob } from "@/lib/api";
import { useGraphAnimation } from "@/animations/useGraphAnimation";

const STATUS_LABELS: Record<JobType, Record<JobStatusValue, string>> = {
  ingest: {
    pending: "Preparing…",
    running: "Building knowledge graph…",
    completed: "Graph built",
    failed: "Build failed",
  },
  orchestrate: {
    pending: "Preparing…",
    running: "Analysing…",
    completed: "Done",
    failed: "Analysis failed",
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
  const [status, setStatus] = useState<JobStatusValue>("pending");
  const [error, setError] = useState("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const svgRef = useGraphAnimation();

  const doPoll = useCallback(async () => {
    try {
      const result = await pollJob(jobId);
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
  }, [jobId, onComplete]);

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
        viewBox="0 0 400 240"
        aria-hidden="true"
      >
        {/* Edges */}
        <path className="graph-edge" d="M 52,108 L 108,45" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 52,108 L 85,162" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 52,108 L 160,72" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 52,108 L 168,138" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 108,45 L 160,72" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 85,162 L 168,138" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 85,162 L 125,192" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 160,72 L 168,138" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 160,72 L 228,48" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 168,138 L 125,192" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 168,138 L 242,118" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 168,138 L 205,182" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 228,48 L 242,118" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 228,48 L 302,78" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 242,118 L 302,78" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 242,118 L 205,182" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 205,182 L 125,192" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 302,78 L 348,48" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 302,78 L 352,135" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />
        <path className="graph-edge" d="M 348,48 L 352,135" fill="none" stroke="var(--stroke-cream)" strokeWidth="1" />

        {/* Nodes */}
        <circle className="graph-dot" cx="52" cy="108" r="3.5" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="108" cy="45" r="3" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="85" cy="162" r="3" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="160" cy="72" r="3" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="168" cy="138" r="3.5" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="125" cy="192" r="3" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="228" cy="48" r="3" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="242" cy="118" r="3" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="205" cy="182" r="3" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="302" cy="78" r="3.5" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="348" cy="48" r="3" fill="var(--text-primary)" />
        <circle className="graph-dot" cx="352" cy="135" r="3" fill="var(--text-primary)" />

        {/* Hidden route paths — travellers circulate across multiple edges */}
        <path className="graph-route" d="M 52,108 L 108,45 L 160,72 L 228,48 L 302,78 L 348,48" fill="none" stroke="none" />
        <path className="graph-route" d="M 52,108 L 85,162 L 125,192 L 205,182 L 242,118 L 302,78 L 352,135" fill="none" stroke="none" />
        <path className="graph-route" d="M 52,108 L 160,72 L 168,138 L 242,118 L 228,48 L 302,78" fill="none" stroke="none" />
        <path className="graph-route" d="M 168,138 L 125,192 L 85,162 L 52,108 L 108,45 L 160,72" fill="none" stroke="none" />
        <path className="graph-route" d="M 168,138 L 205,182 L 242,118 L 302,78 L 348,48 L 352,135" fill="none" stroke="none" />
        <path className="graph-route" d="M 52,108 L 168,138 L 242,118 L 205,182 L 125,192 L 85,162" fill="none" stroke="none" />

        {/* Travelling dots */}
        <circle className="graph-traveller" r="2" fill="var(--accent)" opacity="0" />
        <circle className="graph-traveller" r="2" fill="var(--accent)" opacity="0" />
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
          padding: 32px var(--margin);
          max-width: 480px;
          margin: 0 auto;
          text-align: center;
        }
        .job-progress__svg {
          width: 400px;
          height: 240px;
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
