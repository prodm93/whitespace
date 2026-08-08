import DropZone from "./DropZone";
import type { WorkflowActions, WorkflowState } from "./_workflowTypes";
import SearchPanel from "@/components/search/SearchPanel";

type Props = Pick<
  WorkflowState & WorkflowActions,
  | "latestRuns" | "resumeDismissed" | "handleResume" | "setResumeDismissed"
  | "profileFiles" | "addProfile" | "removeProfile"
  | "domainFiles" | "addDomain" | "removeDomain"
  | "domain" | "cpcClass" | "keepFindings"
  | "setDomain" | "setCpcClass" | "setKeepFindings"
  | "error" | "handleBuild" | "submitting"
>;

export default function InputPhase({
  latestRuns,
  resumeDismissed,
  handleResume,
  setResumeDismissed,
  profileFiles,
  addProfile,
  removeProfile,
  domainFiles,
  addDomain,
  removeDomain,
  domain,
  cpcClass,
  keepFindings,
  setDomain,
  setCpcClass,
  setKeepFindings,
  error,
  handleBuild,
  submitting,
}: Props) {
  return (
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
