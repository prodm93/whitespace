"use client";

interface SearchPanelProps {
  domain: string;
  cpcClass: string;
  keepFindings: boolean;
  onDomainChange: (v: string) => void;
  onCpcChange: (v: string) => void;
  onKeepFindingsChange: (v: boolean) => void;
}

export default function SearchPanel({
  domain,
  cpcClass,
  keepFindings,
  onDomainChange,
  onCpcChange,
  onKeepFindingsChange,
}: SearchPanelProps) {
  return (
    <section className="search-panel">
      <h3 className="search-panel__heading">Patent domain</h3>
      <p className="search-panel__desc">
        Describe the technical domain to search. We query USPTO, semantic web
        search, and academic databases.
      </p>

      <div className="search-panel__fields">
        <div className="search-panel__field">
          <label className="search-panel__label" htmlFor="domain-input">
            Domain keywords
          </label>
          <input
            id="domain-input"
            className="search-panel__input"
            type="text"
            placeholder='e.g. "solid-state battery electrolyte membranes"'
            value={domain}
            onChange={(e) => onDomainChange(e.target.value)}
          />
        </div>

        <div className="search-panel__field search-panel__field--narrow">
          <label className="search-panel__label" htmlFor="cpc-input">
            CPC Class <span className="search-panel__optional">(optional)</span>
          </label>
          <input
            id="cpc-input"
            className="search-panel__input"
            type="text"
            placeholder="e.g. H01M"
            value={cpcClass}
            onChange={(e) => onCpcChange(e.target.value)}
          />
        </div>
      </div>

      <label className="search-panel__keep-findings">
        <input
          type="checkbox"
          checked={keepFindings}
          onChange={(e) => onKeepFindingsChange(e.target.checked)}
          className="search-panel__checkbox"
        />
        <span className="search-panel__checkmark" />
        <span className="search-panel__keep-findings-text">
          Store dated research findings for future runs
        </span>
      </label>

      <style jsx>{`
        .search-panel {
          padding: 32px;
          border: 1px solid var(--stroke-lavender);
          border-radius: var(--radius-lg);
          background: rgba(18, 16, 42, 0.3);
        }
        .search-panel__heading {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h2);
          font-weight: 400;
          color: var(--text-primary);
          margin-bottom: 8px;
        }
        .search-panel__desc {
          font-size: var(--text-caption);
          color: var(--text-secondary);
          margin-bottom: 24px;
          line-height: 1.5;
        }
        .search-panel__fields {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: var(--gutter);
          align-items: end;
        }
        .search-panel__field--narrow {
          width: 160px;
        }
        .search-panel__label {
          display: block;
          font-size: var(--text-caption);
          font-weight: 400;
          color: var(--text-secondary);
          margin-bottom: 8px;
          letter-spacing: 0.03em;
          text-transform: uppercase;
        }
        .search-panel__optional {
          text-transform: none;
          color: var(--text-muted);
        }
        .search-panel__input {
          width: 100%;
          padding: 12px 16px;
          font-family: "Inter", sans-serif;
          font-size: var(--text-body);
          font-weight: 300;
          color: var(--text-primary);
          background: rgba(18, 16, 42, 0.5);
          border: 1px solid var(--stroke-lavender);
          border-radius: var(--radius-md);
          outline: none;
          transition: border-color 0.2s var(--ease-out);
        }
        .search-panel__input::placeholder {
          color: var(--text-muted);
        }
        .search-panel__input:focus {
          border-color: var(--accent);
        }
        .search-panel__keep-findings {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-top: var(--gutter);
          cursor: pointer;
          width: fit-content;
        }
        .search-panel__checkbox {
          position: absolute;
          opacity: 0;
          width: 0;
          height: 0;
        }
        .search-panel__checkmark {
          display: block;
          flex-shrink: 0;
          width: 16px;
          height: 16px;
          border: 1.5px solid var(--stroke-lavender);
          border-radius: var(--radius-sm);
          background: transparent;
          transition: border-color 0.2s var(--ease-out),
            background 0.2s var(--ease-out);
        }
        .search-panel__checkbox:checked + .search-panel__checkmark {
          border-color: var(--accent);
          background: var(--accent);
        }
        .search-panel__checkbox:checked + .search-panel__checkmark::after {
          content: "";
          display: block;
          width: 4px;
          height: 8px;
          margin: 1px auto 0;
          border: solid var(--text-primary);
          border-width: 0 1.5px 1.5px 0;
          transform: rotate(45deg);
        }
        .search-panel__checkbox:focus-visible + .search-panel__checkmark {
          outline: 2px solid var(--accent);
          outline-offset: 2px;
        }
        .search-panel__keep-findings-text {
          font-size: var(--text-caption);
          color: var(--text-secondary);
        }

        @media (max-width: 600px) {
          .search-panel__fields {
            grid-template-columns: 1fr;
          }
          .search-panel__field--narrow {
            width: 100%;
          }
        }
      `}</style>
    </section>
  );
}
