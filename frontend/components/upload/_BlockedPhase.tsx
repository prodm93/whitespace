interface Props {
  reason: string;
  onBack: () => void;
}

export default function BlockedPhase({ reason, onBack }: Props) {
  return (
    <section className="workspace-blocked">
      <p className="workspace-blocked__reason">{reason}</p>
      <button
        className="workspace-blocked__back"
        onClick={onBack}
        type="button"
      >
        Back to start
      </button>
      <style jsx>{`
        .workspace-blocked {
          padding: 96px var(--margin);
          max-width: 560px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 28px;
          text-align: center;
        }
        .workspace-blocked__reason {
          font-size: var(--text-body);
          color: var(--text-secondary);
          line-height: 1.6;
        }
        .workspace-blocked__back {
          padding: 12px 36px;
          font-family: "Inter", sans-serif;
          font-size: var(--text-body);
          font-weight: 400;
          color: var(--text-primary);
          background: var(--accent);
          border-radius: var(--radius-md);
          transition: box-shadow 0.2s var(--ease-out);
        }
        .workspace-blocked__back:hover {
          box-shadow: 0 0 24px var(--accent-glow);
        }
      `}</style>
    </section>
  );
}
