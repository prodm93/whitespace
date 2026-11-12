interface QuestionNoticesProps {
  hasPendingQuestions: boolean;
  onOpen: () => void;
  keysWaiting: boolean;
}

export default function QuestionNotices({
  hasPendingQuestions,
  onOpen,
  keysWaiting,
}: QuestionNoticesProps) {
  if (!hasPendingQuestions && !keysWaiting) return null;
  return (
    <>
      {keysWaiting && (
        <div className="workspace__resume">
          <span className="workspace__resume-text">
            Your new keys are saved. They take effect when the running analysis
            finishes.
          </span>
        </div>
      )}
      {hasPendingQuestions && (
        <div className="workspace__resume">
          <span className="workspace__resume-text">
            A run is waiting for your answers.
          </span>
          <button className="workspace__resume-yes" onClick={onOpen} type="button">
            Answer the questions
          </button>
        </div>
      )}
      <style jsx>{`
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
      `}</style>
    </>
  );
}
