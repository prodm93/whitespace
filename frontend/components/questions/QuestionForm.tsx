"use client";

import { useState } from "react";
import type { PendingQuestion, QuestionAnswerIn } from "@/types";
import QuestionCard from "./QuestionCard";

interface QuestionFormProps {
  questions: PendingQuestion[];
  editable: boolean;
  submitting: boolean;
  submitError: string;
  onSubmit: (answers: QuestionAnswerIn[]) => Promise<void>;
}

function initialAnswers(questions: PendingQuestion[]): Record<string, string> {
  return Object.fromEntries(
    questions.map((q) => [q.question_id, q.status === "answered" ? (q.answer ?? "") : ""]),
  );
}

function initialSkipped(questions: PendingQuestion[]): Record<string, boolean> {
  return Object.fromEntries(questions.map((q) => [q.question_id, q.status === "skipped"]));
}

export default function QuestionForm({
  questions,
  editable,
  submitting,
  submitError,
  onSubmit,
}: QuestionFormProps) {
  const [answers, setAnswers] = useState(() => initialAnswers(questions));
  const [skipped, setSkipped] = useState(() => initialSkipped(questions));

  const handleSubmit = () => {
    const entries = questions.map((q) => {
      const isSkipped = skipped[q.question_id] === true;
      return {
        question_id: q.question_id,
        answer: isSkipped ? "" : (answers[q.question_id] ?? ""),
        skipped: isSkipped,
      };
    });
    void onSubmit(entries);
  };

  return (
    <section className="question-form">
      <header className="question-form__header">
        <h2 className="question-form__heading">
          {questions.length === 1
            ? "A question before we continue"
            : "A few questions before we continue"}
        </h2>
        <p className="question-form__intro">
          The models paused the analysis to ask you this. Your answers change
          what they look for next. You can skip any question.
        </p>
      </header>
      {questions.map((q) => (
        <QuestionCard
          key={q.question_id}
          question={q}
          answer={answers[q.question_id] ?? ""}
          skipped={skipped[q.question_id] === true}
          editable={editable}
          onAnswer={(text) => setAnswers((prev) => ({ ...prev, [q.question_id]: text }))}
          onSkip={() => setSkipped((prev) => ({ ...prev, [q.question_id]: true }))}
          onUndo={() => setSkipped((prev) => ({ ...prev, [q.question_id]: false }))}
        />
      ))}
      <div className="question-form__footer">
        <button
          className="question-form__submit"
          onClick={handleSubmit}
          disabled={submitting}
          type="button"
        >
          {submitting ? "Submitting…" : "Continue the analysis"}
        </button>
        {submitError && <p className="question-form__error">{submitError}</p>}
      </div>
      <style jsx>{`
        .question-form {
          padding: 48px var(--margin) 96px;
          max-width: 800px;
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 32px;
        }
        .question-form__header {
          text-align: center;
        }
        .question-form__heading {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h1);
          font-weight: 400;
          color: var(--text-primary);
          margin-bottom: 8px;
        }
        .question-form__intro {
          font-size: var(--text-body);
          color: var(--text-secondary);
        }
        .question-form__footer {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
        }
        .question-form__submit {
          padding: 14px 36px;
          font-family: "Inter", sans-serif;
          font-size: var(--text-body);
          font-weight: 400;
          color: var(--text-primary);
          background: var(--accent);
          border-radius: var(--radius-md);
          transition: opacity 0.2s var(--ease-out),
            box-shadow 0.2s var(--ease-out);
        }
        .question-form__submit:hover:not(:disabled) {
          box-shadow: 0 0 24px var(--accent-glow);
        }
        .question-form__submit:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }
        .question-form__error {
          font-size: var(--text-caption);
          color: #c25a5a;
          text-align: center;
        }
      `}</style>
    </section>
  );
}
