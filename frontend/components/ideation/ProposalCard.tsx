"use client";

import { useCallback, useState } from "react";
import type { IdeationProposal } from "@/types";

interface ProposalCardProps {
  proposal: IdeationProposal;
}

function formatExport(p: IdeationProposal): string {
  let text = `# ${p.title}\n\n`;
  text += `## Problem Statement\n${p.problem_statement}\n\n`;
  text += `## Technical Approach\n${p.technical_approach}\n\n`;
  text += `## Why This Person\n${p.why_this_person}\n\n`;
  text += `## Differentiation from Prior Art\n${p.differentiation_from_prior_art}\n\n`;
  text += `## Limitations\n${p.limitations}\n\n`;
  if (p.prior_art_notes) {
    text += `## Prior Art Notes\n${p.prior_art_notes}\n\n`;
  }
  if (p.provenance.length > 0) {
    text += `## Provenance\n${p.provenance.map((s) => `- ${s}`).join("\n")}\n`;
  }
  return text;
}

export default function ProposalCard({ proposal }: ProposalCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleExport = useCallback(async () => {
    await navigator.clipboard.writeText(formatExport(proposal));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [proposal]);

  const firstLine = proposal.problem_statement.split(/[.\n]/)[0];

  return (
    <article className="proposal-card">
      <button
        className="proposal-card__header"
        onClick={() => setExpanded(!expanded)}
        type="button"
        aria-expanded={expanded}
      >
        <div className="proposal-card__summary">
          <h3 className="proposal-card__title">{proposal.title}</h3>
          <p className="proposal-card__lead">
            {firstLine.length > 160
              ? firstLine.slice(0, 160) + "…"
              : firstLine}
          </p>
        </div>
        <span className={`proposal-card__chevron ${expanded ? "proposal-card__chevron--open" : ""}`}>
          &#8250;
        </span>
      </button>

      {expanded && (
        <div className="proposal-card__body">
          <Section label="Problem statement" text={proposal.problem_statement} />
          <Section label="Technical approach" text={proposal.technical_approach} />
          <Section label="Why you" text={proposal.why_this_person} />
          <Section
            label="Differentiation from prior art"
            text={proposal.differentiation_from_prior_art}
          />
          <Section label="Limitations" text={proposal.limitations} />

          {proposal.prior_art_notes && (
            <div className="proposal-card__callout">
              <h4 className="proposal-card__callout-label">Prior art note</h4>
              <p className="proposal-card__callout-text">
                {proposal.prior_art_notes}
              </p>
            </div>
          )}

          {proposal.provenance.length > 0 && (
            <div className="proposal-card__provenance">
              <h4 className="proposal-card__section-label">Provenance</h4>
              <ol className="proposal-card__trail">
                {proposal.provenance.map((step, i) => (
                  <li key={i} className="proposal-card__trail-step">
                    <span className="proposal-card__trail-dot" />
                    <span className="proposal-card__trail-text">{step}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {(proposal.contributing_models.length > 0 ||
            Object.keys(proposal.scores).length > 0 ||
            proposal.critique_notes) && (
            <div className="proposal-card__council">
              <h4 className="proposal-card__section-label">Council review</h4>

              {proposal.contributing_models.length > 0 && (
                <div className="proposal-card__models">
                  {proposal.contributing_models.map((model) => (
                    <span key={model} className="proposal-card__model-tag">
                      {model}
                    </span>
                  ))}
                </div>
              )}

              {Object.keys(proposal.scores).length > 0 && (
                <ul className="proposal-card__scores">
                  {Object.entries(proposal.scores).map(([criterion, score]) => (
                    <li key={criterion} className="proposal-card__score-item">
                      <span className="proposal-card__score-criterion">
                        {criterion.replace(/_/g, " ")}
                      </span>
                      <span className="proposal-card__score-value">{score}/10</span>
                    </li>
                  ))}
                </ul>
              )}

              {proposal.critique_notes && (
                <div className="proposal-card__callout">
                  <p className="proposal-card__callout-text">
                    {proposal.critique_notes}
                  </p>
                </div>
              )}
            </div>
          )}

          <button
            className="proposal-card__export"
            onClick={handleExport}
            type="button"
          >
            {copied ? "Copied" : "Export"}
          </button>
        </div>
      )}

      <style jsx>{`
        .proposal-card {
          border: 1px solid var(--stroke-lavender);
          border-radius: var(--radius-lg);
          background: rgba(255, 255, 255, 0.03);
          transition: border-color 0.25s var(--ease-out),
            box-shadow 0.25s var(--ease-out),
            transform 0.25s var(--ease-out);
        }
        .proposal-card:hover {
          border-color: var(--accent-dim);
          box-shadow: 0 2px 16px rgba(0, 0, 0, 0.2);
          transform: translateY(-1px);
        }
        .proposal-card__header {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 24px;
          width: 100%;
          text-align: left;
        }
        .proposal-card__summary {
          flex: 1;
          min-width: 0;
        }
        .proposal-card__title {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h2);
          font-weight: 500;
          color: var(--text-primary);
          margin-bottom: 6px;
          line-height: 1.2;
        }
        .proposal-card__lead {
          font-size: var(--text-caption);
          color: var(--text-secondary);
          line-height: 1.5;
        }
        .proposal-card__chevron {
          flex-shrink: 0;
          font-size: 20px;
          color: var(--text-secondary);
          transition: transform 0.2s var(--ease-out);
          margin-top: 4px;
        }
        .proposal-card__chevron--open {
          transform: rotate(90deg);
        }
        .proposal-card__body {
          display: flex;
          flex-direction: column;
          gap: 20px;
          padding: 0 24px 24px;
          border-top: 1px solid var(--stroke-lavender);
          margin: 0 24px;
          padding-top: 20px;
        }
        .proposal-card__section-label {
          font-size: var(--text-caption);
          font-weight: 400;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.04em;
          margin-bottom: 6px;
        }
        .proposal-card__callout {
          padding: 16px 20px;
          border-left: 3px solid var(--accent);
          background: rgba(138, 69, 112, 0.06);
          border-radius: 0 var(--radius-md) var(--radius-md) 0;
        }
        .proposal-card__callout-label {
          font-size: var(--text-caption);
          font-weight: 400;
          color: var(--accent);
          text-transform: uppercase;
          letter-spacing: 0.04em;
          margin-bottom: 6px;
        }
        .proposal-card__callout-text {
          font-size: var(--text-body);
          font-weight: 300;
          color: var(--text-primary);
          line-height: 1.6;
        }
        .proposal-card__provenance {
          padding-top: 4px;
        }
        .proposal-card__trail {
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 0;
          padding-left: 10px;
        }
        .proposal-card__trail-step {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          position: relative;
          padding-bottom: 12px;
          padding-left: 6px;
        }
        .proposal-card__trail-step:not(:last-child)::before {
          content: "";
          position: absolute;
          left: 8px;
          top: 12px;
          bottom: 0;
          width: 1px;
          background: var(--stroke-lavender);
        }
        .proposal-card__trail-dot {
          flex-shrink: 0;
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: var(--accent-dim);
          margin-top: 5px;
        }
        .proposal-card__trail-text {
          font-size: var(--text-caption);
          color: var(--text-secondary);
          line-height: 1.5;
        }
        .proposal-card__council {
          padding-top: 4px;
        }
        .proposal-card__models {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin-bottom: 10px;
        }
        .proposal-card__model-tag {
          font-size: 11px;
          font-weight: 400;
          color: var(--text-secondary);
          padding: 2px 8px;
          border: 1px solid var(--stroke-lavender);
          border-radius: var(--radius-sm);
          letter-spacing: 0.02em;
        }
        .proposal-card__scores {
          list-style: none;
          display: flex;
          flex-wrap: wrap;
          gap: 8px 20px;
          margin-bottom: 10px;
        }
        .proposal-card__score-item {
          display: flex;
          align-items: baseline;
          gap: 6px;
          font-size: var(--text-caption);
        }
        .proposal-card__score-criterion {
          color: var(--text-muted);
          text-transform: capitalize;
        }
        .proposal-card__score-value {
          color: var(--accent);
          font-weight: 500;
        }
        .proposal-card__export {
          align-self: flex-start;
          padding: 8px 20px;
          font-size: var(--text-caption);
          font-weight: 400;
          color: var(--text-secondary);
          border: 1px solid var(--stroke-lavender);
          border-radius: var(--radius-md);
          transition: border-color 0.2s var(--ease-out),
            color 0.2s var(--ease-out);
        }
        .proposal-card__export:hover {
          border-color: var(--accent);
          color: var(--text-primary);
        }
      `}</style>
    </article>
  );
}

function Section({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <h4
        style={{
          fontSize: "var(--text-caption)",
          fontWeight: 400,
          color: "var(--text-muted)",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          marginBottom: 6,
        }}
      >
        {label}
      </h4>
      <p
        style={{
          fontSize: "var(--text-body)",
          fontWeight: 300,
          color: "var(--text-primary)",
          lineHeight: 1.65,
        }}
      >
        {text}
      </p>
    </div>
  );
}
