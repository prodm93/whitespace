"use client";

import { useCallback, useState } from "react";
import type { UnmetNeed } from "@/types";
import NeedCard from "./NeedCard";

interface GapResultsProps {
  needs: UnmetNeed[];
  onIdeate: (selectedTitles: string[]) => void;
  onFreshStart: () => void;
  submitting: boolean;
}

export default function GapResults({
  needs,
  onIdeate,
  onFreshStart,
  submitting,
}: GapResultsProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmingFreshStart, setConfirmingFreshStart] = useState(false);

  const toggle = useCallback((title: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(title)) {
        next.delete(title);
      } else {
        next.add(title);
      }
      return next;
    });
  }, []);

  const handleIdeate = () => {
    onIdeate(Array.from(selected));
  };

  return (
    <section className="gap-results">
      <div className="gap-results__header">
        <h2 className="gap-results__heading">Unmet needs</h2>
        <p className="gap-results__sub">
          {needs.length} gap{needs.length !== 1 ? "s" : ""} identified. Select
          the needs you want to develop into full patentable ideas.
        </p>

        {confirmingFreshStart ? (
          <div className="gap-results__fresh-confirm">
            <span>
              This ignores every previous run&rsquo;s memory and re-analyses
              from scratch. Continue?
            </span>
            <div className="gap-results__fresh-confirm-actions">
              <button
                className="gap-results__fresh-confirm-yes"
                onClick={onFreshStart}
                type="button"
              >
                Yes, start fresh
              </button>
              <button
                className="gap-results__fresh-confirm-cancel"
                onClick={() => setConfirmingFreshStart(false)}
                type="button"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            className="gap-results__fresh-start"
            onClick={() => setConfirmingFreshStart(true)}
            type="button"
          >
            Start fresh, ignoring prior runs
          </button>
        )}
      </div>

      <div className="gap-results__list">
        {needs.map((need) => (
          <NeedCard
            key={need.title}
            need={need}
            selected={selected.has(need.title)}
            onToggle={() => toggle(need.title)}
          />
        ))}
      </div>

      <div className="gap-results__actions">
        <span className="gap-results__count">
          {selected.size} selected
        </span>
        <button
          className="gap-results__ideate"
          onClick={handleIdeate}
          disabled={selected.size === 0 || submitting}
          type="button"
        >
          {submitting
            ? "Submitting…"
            : "Generate ideas for selected needs"}
        </button>
      </div>

      <style jsx>{`
        .gap-results {
          padding: 48px var(--margin) 96px;
          max-width: 800px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 32px;
        }
        .gap-results__header {
          text-align: center;
        }
        .gap-results__heading {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h1);
          font-weight: 400;
          color: var(--text-primary);
          margin-bottom: 8px;
        }
        .gap-results__sub {
          font-size: var(--text-body);
          color: var(--text-secondary);
        }
        .gap-results__fresh-start {
          margin-top: 12px;
          font-size: var(--text-caption);
          color: var(--text-muted);
          text-decoration: underline;
          text-underline-offset: 3px;
          transition: color 0.2s var(--ease-out);
        }
        .gap-results__fresh-start:hover {
          color: var(--text-secondary);
        }
        .gap-results__fresh-confirm {
          margin-top: 12px;
          padding: 16px 20px;
          border: 1px solid var(--accent-dim);
          border-radius: var(--radius-md);
          background: rgba(138, 69, 112, 0.06);
          display: flex;
          flex-direction: column;
          gap: 12px;
          font-size: var(--text-caption);
          color: var(--text-secondary);
        }
        .gap-results__fresh-confirm-actions {
          display: flex;
          justify-content: center;
          gap: 12px;
        }
        .gap-results__fresh-confirm-yes {
          padding: 8px 20px;
          font-size: var(--text-caption);
          color: var(--text-primary);
          background: var(--accent);
          border-radius: var(--radius-md);
          transition: box-shadow 0.2s var(--ease-out);
        }
        .gap-results__fresh-confirm-yes:hover {
          box-shadow: 0 0 24px var(--accent-glow);
        }
        .gap-results__fresh-confirm-cancel {
          padding: 8px 20px;
          font-size: var(--text-caption);
          color: var(--text-secondary);
          border: 1px solid var(--stroke-lavender);
          border-radius: var(--radius-md);
          transition: border-color 0.2s var(--ease-out);
        }
        .gap-results__fresh-confirm-cancel:hover {
          border-color: var(--accent);
        }
        .gap-results__list {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .gap-results__actions {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 20px;
          padding-top: 8px;
        }
        .gap-results__count {
          font-size: var(--text-caption);
          color: var(--text-muted);
        }
        .gap-results__ideate {
          padding: 14px 36px;
          font-family: "Inter", sans-serif;
          font-size: var(--text-body);
          font-weight: 400;
          color: var(--text-primary);
          background: var(--accent);
          border-radius: var(--radius-md);
          transition: opacity 0.2s var(--ease-out),
            box-shadow 0.2s var(--ease-out);
        }
        .gap-results__ideate:hover:not(:disabled) {
          box-shadow: 0 0 24px var(--accent-glow);
        }
        .gap-results__ideate:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }
      `}</style>
    </section>
  );
}
