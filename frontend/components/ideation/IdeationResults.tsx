"use client";

import type { IdeationProposal } from "@/types";
import ProposalCard from "./ProposalCard";

interface IdeationResultsProps {
  proposals: IdeationProposal[];
}

export default function IdeationResults({ proposals }: IdeationResultsProps) {
  return (
    <section className="ideation-results">
      <div className="ideation-results__header">
        <h2 className="ideation-results__heading">Ideation proposals</h2>
        <p className="ideation-results__sub">
          {proposals.length} proposal{proposals.length !== 1 ? "s" : ""} generated.
          Expand each card for the full write-up and provenance trail.
        </p>
      </div>

      <div className="ideation-results__list">
        {proposals.map((proposal) => (
          <ProposalCard key={proposal.title} proposal={proposal} />
        ))}
      </div>

      <style jsx>{`
        .ideation-results {
          padding: 48px var(--margin) 96px;
          max-width: 800px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 32px;
        }
        .ideation-results__header {
          text-align: center;
        }
        .ideation-results__heading {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h1);
          font-weight: 400;
          color: var(--text-primary);
          margin-bottom: 8px;
        }
        .ideation-results__sub {
          font-size: var(--text-body);
          color: var(--text-secondary);
        }
        .ideation-results__list {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
      `}</style>
    </section>
  );
}
