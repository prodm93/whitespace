"use client";

import type { DeploymentMode } from "@/types";

interface ModeToggleProps {
  onSelect: (mode: DeploymentMode) => void;
}

export default function ModeToggle({ onSelect }: ModeToggleProps) {
  return (
    <section className="mode-toggle">
      <h2 className="mode-toggle__heading">Choose your path</h2>
      <p className="mode-toggle__sub">
        Run locally with your own API keys, or use our hosted infrastructure.
      </p>

      <div className="mode-toggle__cards">
        <button
          className="mode-card"
          onClick={() => onSelect("byok")}
          type="button"
        >
          <div className="mode-card__icon">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
              <path
                d="M16 3L16 12M16 12L21 7M16 12L11 7"
                stroke="var(--text-primary)"
                strokeWidth="1.2"
                strokeLinecap="round"
              />
              <rect
                x="6" y="14" width="20" height="14" rx="3"
                stroke="var(--accent)"
                strokeWidth="1.2"
                fill="none"
              />
              <circle cx="16" cy="21" r="2" stroke="var(--text-primary)" strokeWidth="1" fill="none" />
            </svg>
          </div>
          <h3 className="mode-card__title">Bring Your Own Key</h3>
          <p className="mode-card__desc">
            Run locally via Docker. Use your OpenRouter API key for inference and
            Neo4j Aura for the knowledge graph. No account needed.
          </p>
          <span className="mode-card__tag">Self-hosted</span>
        </button>

        <button
          className="mode-card"
          onClick={() => onSelect("saas")}
          type="button"
        >
          <div className="mode-card__icon">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
              <path
                d="M8 24C5.2 24 3 21.8 3 19C3 16.5 4.8 14.5 7.1 14.1C7 13.7 7 13.4 7 13C7 9.7 9.7 7 13 7C15.4 7 17.4 8.5 18.3 10.6C18.9 10.2 19.6 10 20.5 10C22.7 10 24.5 11.8 24.5 14C24.5 14.2 24.5 14.4 24.4 14.6C26.5 15.1 28 17 28 19.2C28 21.9 25.9 24 23.2 24H8Z"
                stroke="var(--accent)"
                strokeWidth="1.2"
                fill="none"
              />
              <path
                d="M13 20L16 17L19 20"
                stroke="var(--text-primary)"
                strokeWidth="1"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <line x1="16" y1="17" x2="16" y2="25" stroke="var(--text-primary)" strokeWidth="1" strokeLinecap="round" />
            </svg>
          </div>
          <h3 className="mode-card__title">Hosted</h3>
          <p className="mode-card__desc">
            Sign in, pick a plan, and go. We handle infrastructure, models, and
            scaling. Built on AWS with Bedrock inference.
          </p>
          <span className="mode-card__tag">Managed</span>
        </button>
      </div>

      <style jsx>{`
        .mode-toggle {
          padding: 0 var(--margin) 96px;
          max-width: 880px;
          margin: 0 auto;
          text-align: center;
        }
        .mode-toggle__heading {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h1);
          font-weight: 400;
          color: var(--text-primary);
          margin-bottom: 12px;
        }
        .mode-toggle__sub {
          font-size: var(--text-body);
          color: var(--text-secondary);
          margin-bottom: 48px;
        }
        .mode-toggle__cards {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: var(--gutter);
        }
        .mode-card {
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          text-align: left;
          padding: 36px 32px 32px;
          border-radius: var(--radius-lg);
          border: 1px solid var(--stroke-lavender);
          background: rgba(18, 16, 42, 0.4);
          transition: border-color 0.3s var(--ease-out),
            background 0.3s var(--ease-out),
            box-shadow 0.3s var(--ease-out);
          cursor: pointer;
        }
        .mode-card:hover {
          border-color: var(--accent);
          background: rgba(18, 16, 42, 0.65);
          box-shadow: 0 0 32px var(--accent-glow);
        }
        .mode-card__icon {
          margin-bottom: 20px;
        }
        .mode-card__title {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h2);
          font-weight: 500;
          color: var(--text-primary);
          margin-bottom: 12px;
        }
        .mode-card__desc {
          font-size: var(--text-body);
          font-weight: 300;
          color: var(--text-secondary);
          line-height: 1.6;
          flex: 1;
        }
        .mode-card__tag {
          display: inline-block;
          margin-top: 20px;
          padding: 4px 12px;
          font-size: var(--text-caption);
          font-weight: 400;
          color: var(--accent);
          border: 1px solid var(--accent-dim);
          border-radius: var(--radius-sm);
          letter-spacing: 0.04em;
          text-transform: uppercase;
        }

        @media (max-width: 600px) {
          .mode-toggle__cards {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </section>
  );
}
