"use client";

import { useWorkflow } from "./_useWorkflow";
import InputPhase from "./_InputPhase";
import BlockedPhase from "./_BlockedPhase";
import JobProgress from "@/components/jobs/JobProgress";
import GapResults from "@/components/gaps/GapResults";
import IdeationResults from "@/components/ideation/IdeationResults";

export default function Workspace() {
  const workflow = useWorkflow();

  let content: React.ReactNode;

  if (workflow.phase === "ingesting") {
    content = (
      <JobProgress
        jobId={workflow.jobId}
        jobType="ingest"
        onComplete={workflow.handleIngestComplete}
        onRetry={workflow.handleRetryIngest}
      />
    );
  } else if (workflow.phase === "orchestrating") {
    content = (
      <JobProgress
        jobId={workflow.jobId}
        jobType="orchestrate"
        onComplete={workflow.handleOrchestrateComplete}
        onRetry={workflow.handleRetryOrchestrate}
      />
    );
  } else if (workflow.phase === "gap-results") {
    content = (
      <GapResults
        needs={workflow.needs}
        onIdeate={workflow.handleIdeate}
        onFreshStart={workflow.handleFreshStart}
        submitting={workflow.ideateSubmitting}
      />
    );
  } else if (workflow.phase === "ideation-results") {
    content = <IdeationResults proposals={workflow.proposals} />;
  } else if (workflow.phase === "blocked") {
    content = (
      <BlockedPhase
        reason={workflow.blockedReason}
        onBack={workflow.goToInput}
      />
    );
  } else {
    content = (
      <InputPhase
        latestRuns={workflow.latestRuns}
        resumeDismissed={workflow.resumeDismissed}
        handleResume={workflow.handleResume}
        setResumeDismissed={workflow.setResumeDismissed}
        profileFiles={workflow.profileFiles}
        addProfile={workflow.addProfile}
        removeProfile={workflow.removeProfile}
        domainFiles={workflow.domainFiles}
        addDomain={workflow.addDomain}
        removeDomain={workflow.removeDomain}
        domain={workflow.domain}
        cpcClass={workflow.cpcClass}
        keepFindings={workflow.keepFindings}
        setDomain={workflow.setDomain}
        setCpcClass={workflow.setCpcClass}
        setKeepFindings={workflow.setKeepFindings}
        error={workflow.error}
        handleBuild={workflow.handleBuild}
        submitting={workflow.submitting}
      />
    );
  }

  return (
    <>
      <button
        className="workspace__back"
        onClick={workflow.backAction}
        type="button"
      >
        &larr; {workflow.backLabel}
      </button>
      {content}
      <style jsx>{`
        .workspace__back {
          position: fixed;
          top: 80px;
          left: var(--margin);
          font-family: "Inter", sans-serif;
          font-size: var(--text-caption);
          color: var(--text-muted);
          background: none;
          border: none;
          cursor: pointer;
          z-index: 10;
          transition: color 0.2s var(--ease-out);
        }
        .workspace__back:hover {
          color: var(--text-primary);
        }
      `}</style>
    </>
  );
}
