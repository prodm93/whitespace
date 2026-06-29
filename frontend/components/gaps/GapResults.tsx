"use client";

import { useCallback, useState } from "react";
import type { UnmetNeed } from "@/types";
import NeedCard from "./NeedCard";

interface GapResultsProps {
  needs: UnmetNeed[];
  onIdeate: (selectedTitles: string[]) => void;
  submitting: boolean;
}

export default function GapResults({
  needs,
  onIdeate,
  submitting,
}: GapResultsProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

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
