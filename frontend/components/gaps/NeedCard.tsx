"use client";

import { useState } from "react";
import type { UnmetNeed } from "@/types";

interface NeedCardProps {
  need: UnmetNeed;
  selected: boolean;
  onToggle: () => void;
}

export default function NeedCard({ need, selected, onToggle }: NeedCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <article
      className={`need-card ${selected ? "need-card--selected" : ""}`}
    >
      <div className="need-card__header">
        <label className="need-card__check-wrap">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="need-card__checkbox"
          />
          <span className="need-card__checkmark" />
        </label>

        <button
          className="need-card__toggle"
          onClick={() => setExpanded(!expanded)}
          type="button"
          aria-expanded={expanded}
        >
          <div className="need-card__summary">
            <h3 className="need-card__title">{need.title}</h3>
            <p className="need-card__desc-short">
              {need.description.length > 140
                ? need.description.slice(0, 140) + "…"
                : need.description}
            </p>
            {need.matching_skills.length > 0 && (
              <div className="need-card__skills">
                {need.matching_skills.map((skill) => (
                  <span key={skill} className="need-card__skill-tag">
                    {skill}
                  </span>
                ))}
              </div>
            )}
          </div>
          <span className={`need-card__chevron ${expanded ? "need-card__chevron--open" : ""}`}>
            &#8250;
          </span>
        </button>
      </div>

      {expanded && (
        <div className="need-card__body">
          <div className="need-card__section">
            <h4 className="need-card__section-label">Description</h4>
            <p className="need-card__text">{need.description}</p>
          </div>
          <div className="need-card__section">
            <h4 className="need-card__section-label">Current state of the art</h4>
            <p className="need-card__text">{need.current_state}</p>
          </div>
          <div className="need-card__section">
            <h4 className="need-card__section-label">Why this remains unmet</h4>
            <p className="need-card__text">{need.why_unmet}</p>
          </div>
          {need.provenance.length > 0 && (
            <div className="need-card__section">
              <h4 className="need-card__section-label">Provenance</h4>
              <ul className="need-card__provenance">
                {need.provenance.map((p, i) => (
                  <li key={i} className="need-card__prov-item">{p}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <style jsx>{`
        .need-card {
          border: 1px solid var(--stroke-lavender);
          border-radius: var(--radius-lg);
          background: rgba(255, 255, 255, 0.03);
          transition: border-color 0.25s var(--ease-out),
            box-shadow 0.25s var(--ease-out),
            transform 0.25s var(--ease-out);
        }
        .need-card:hover {
          border-color: var(--accent-dim);
          box-shadow: 0 2px 16px rgba(0, 0, 0, 0.2);
          transform: translateY(-1px);
        }
        .need-card--selected {
          border-color: var(--accent);
          box-shadow: 0 0 20px var(--accent-glow);
        }
        .need-card__header {
          display: flex;
          align-items: flex-start;
          gap: 14px;
          padding: 20px 24px;
        }
        .need-card__check-wrap {
          position: relative;
          flex-shrink: 0;
          display: flex;
          align-items: center;
          margin-top: 3px;
          cursor: pointer;
        }
        .need-card__checkbox {
          position: absolute;
          opacity: 0;
          width: 0;
          height: 0;
        }
        .need-card__checkmark {
          display: block;
          width: 18px;
          height: 18px;
          border: 1.5px solid var(--stroke-lavender);
          border-radius: var(--radius-sm);
          background: transparent;
          transition: border-color 0.2s var(--ease-out),
            background 0.2s var(--ease-out);
        }
        .need-card__checkbox:checked + .need-card__checkmark {
          border-color: var(--accent);
          background: var(--accent);
        }
        .need-card__checkbox:checked + .need-card__checkmark::after {
          content: "";
          display: block;
          width: 5px;
          height: 9px;
          margin: 1px auto 0;
          border: solid var(--text-primary);
          border-width: 0 1.5px 1.5px 0;
          transform: rotate(45deg);
        }
        .need-card__checkbox:focus-visible + .need-card__checkmark {
          outline: 2px solid var(--accent);
          outline-offset: 2px;
        }
        .need-card__toggle {
          flex: 1;
          display: flex;
          align-items: flex-start;
          gap: 12px;
          text-align: left;
          min-width: 0;
        }
        .need-card__summary {
          flex: 1;
          min-width: 0;
        }
        .need-card__title {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h2);
          font-weight: 500;
          color: var(--text-primary);
          margin-bottom: 6px;
          line-height: 1.2;
        }
        .need-card__desc-short {
          font-size: var(--text-caption);
          color: var(--text-secondary);
          line-height: 1.5;
          margin-bottom: 10px;
        }
        .need-card__skills {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .need-card__skill-tag {
          font-size: 11px;
          font-weight: 400;
          color: var(--accent);
          padding: 2px 8px;
          border: 1px solid var(--accent-dim);
          border-radius: var(--radius-sm);
          letter-spacing: 0.02em;
        }
        .need-card__chevron {
          flex-shrink: 0;
          font-size: 20px;
          color: var(--text-secondary);
          transition: transform 0.2s var(--ease-out);
          margin-top: 4px;
        }
        .need-card__chevron--open {
          transform: rotate(90deg);
        }
        .need-card__body {
          padding: 0 24px 24px 56px;
          display: flex;
          flex-direction: column;
          gap: 18px;
          border-top: 1px solid var(--stroke-lavender);
          margin-top: 0;
          padding-top: 18px;
          margin-left: 24px;
          margin-right: 24px;
          padding-left: 32px;
          padding-right: 0;
        }
        .need-card__section-label {
          font-size: var(--text-caption);
          font-weight: 400;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.04em;
          margin-bottom: 6px;
        }
        .need-card__text {
          font-size: var(--text-body);
          font-weight: 300;
          color: var(--text-primary);
          line-height: 1.65;
        }
        .need-card__provenance {
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .need-card__prov-item {
          font-size: var(--text-caption);
          color: var(--text-secondary);
          padding-left: 14px;
          position: relative;
        }
        .need-card__prov-item::before {
          content: "";
          position: absolute;
          left: 0;
          top: 7px;
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: var(--accent-dim);
        }
      `}</style>
    </article>
  );
}
