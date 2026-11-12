import type { PendingQuestion } from "@/types";

interface QuestionCardProps {
  question: PendingQuestion;
  answer: string;
  skipped: boolean;
  editable: boolean;
  onAnswer: (text: string) => void;
  onSkip: () => void;
  onUndo: () => void;
}

export default function QuestionCard({
  question,
  answer,
  skipped,
  editable,
  onAnswer,
  onSkip,
  onUndo,
}: QuestionCardProps) {
  const dim = skipped || !editable;
  return (
    <article className={`question-card${dim ? " question-card--dim" : ""}`}>
      <h3 className="question-card__question">{question.question}</h3>
      <p className="question-card__label">Our guess</p>
      <p className="question-card__text">{question.hypothesis}</p>
      <p className="question-card__label">Why we ask</p>
      <p className="question-card__text">{question.rationale}</p>
      {skipped ? (
        <div className="question-card__skipped">
          <span>Skipped</span>
          <button
            className="question-card__link"
            onClick={onUndo}
            disabled={!editable}
            type="button"
          >
            Undo
          </button>
        </div>
      ) : (
        <>
          <textarea
            className="question-card__answer"
            placeholder="Your answer"
            value={answer}
            onChange={(e) => onAnswer(e.target.value)}
            disabled={!editable}
            rows={3}
          />
          <button
            className="question-card__link"
            onClick={onSkip}
            disabled={!editable}
            type="button"
          >
            Skip this question
          </button>
        </>
      )}
      <style jsx>{`
        .question-card {
          padding: 24px 32px;
          border: 1px solid var(--stroke-lavender);
          border-radius: var(--radius-lg);
          background: rgba(18, 16, 42, 0.3);
          display: flex;
          flex-direction: column;
          gap: 8px;
          transition: opacity 0.2s var(--ease-out);
        }
        .question-card--dim {
          opacity: 0.5;
        }
        .question-card__question {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h2);
          font-weight: 400;
          color: var(--text-primary);
          margin-bottom: 8px;
        }
        .question-card__label {
          font-size: var(--text-caption);
          color: var(--text-secondary);
          letter-spacing: 0.03em;
          text-transform: uppercase;
        }
        .question-card__text {
          font-size: var(--text-body);
          color: var(--text-primary);
          margin-bottom: 8px;
        }
        .question-card__answer {
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
          resize: vertical;
          transition: border-color 0.2s var(--ease-out);
        }
        .question-card__answer::placeholder {
          color: var(--text-muted);
        }
        .question-card__answer:focus {
          border-color: var(--accent);
        }
        .question-card__skipped {
          display: flex;
          gap: 12px;
          align-items: baseline;
          font-size: var(--text-caption);
          color: var(--text-secondary);
        }
        .question-card__link {
          align-self: flex-start;
          margin-top: 4px;
          font-size: var(--text-caption);
          color: var(--text-muted);
          text-decoration: underline;
          text-underline-offset: 3px;
          transition: color 0.2s var(--ease-out);
        }
        .question-card__link:hover:not(:disabled) {
          color: var(--text-secondary);
        }
        .question-card__link:disabled {
          cursor: not-allowed;
        }
      `}</style>
    </article>
  );
}
