import { useCallback, useEffect, useState } from "react";
import { getLatestRuns, orchestrate } from "@/lib/api";
import type {
  JobResult,
  LatestRunsResponse,
  OrchestrateResult,
  PendingQuestion,
  QuestionAnswerIn,
  UnmetNeed,
} from "@/types";
import type { Phase } from "./_workflowTypes";

const ASK_QUESTIONS_KEY = "whitespace.askQuestions";
const SUBMIT_INTENT = "Continue the analysis with my answers.";
const SUBMIT_FAILED = "Your answers could not be sent. Try again.";

export function useAskQuestions(): [boolean, (v: boolean) => void] {
  const [askQuestions, setAsk] = useState(true);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(ASK_QUESTIONS_KEY);
      if (stored !== null) setAsk(stored === "true");
    } catch {
      setAsk(true);
    }
  }, []);

  const setAskQuestions = useCallback((v: boolean) => {
    setAsk(v);
    try {
      window.localStorage.setItem(ASK_QUESTIONS_KEY, String(v));
    } catch {
      // The choice stays in page memory when storage is unavailable.
    }
  }, []);

  return [askQuestions, setAskQuestions];
}

export interface QuestionsResult {
  questions: PendingQuestion[];
  questionsEditable: boolean;
  answersSubmitting: boolean;
  submitError: string;
  pendingRun: LatestRunsResponse | null;
  refreshPending: () => Promise<LatestRunsResponse | null>;
  handleOpenQuestions: (run?: LatestRunsResponse | null) => void;
  handleOrchestrateComplete: (result: JobResult) => void;
  retryOrchestrate: (fallback: () => void) => Promise<void>;
  handleSubmitAnswers: (answers: QuestionAnswerIn[]) => Promise<void>;
}

export function useQuestions(
  setNeeds: (n: UnmetNeed[]) => void,
  setPhase: (p: Phase) => void,
  setJobId: (id: string) => void,
  onOtherResult: (result: JobResult) => void,
): QuestionsResult {
  const [questions, setQuestions] = useState<PendingQuestion[]>([]);
  const [questionsEditable, setQuestionsEditable] = useState(true);
  const [answersSubmitting, setAnswersSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [pendingRun, setPendingRun] = useState<LatestRunsResponse | null>(null);

  const refreshPending = useCallback(async () => {
    try {
      const response = await getLatestRuns();
      setPendingRun(response.pending_questions ? response : null);
      return response;
    } catch {
      return null;
    }
  }, []);

  const handleOpenQuestions = useCallback(
    (run: LatestRunsResponse | null = pendingRun) => {
      const pending = run?.pending_questions;
      if (!run || !pending) return;
      setQuestions(pending.questions);
      setQuestionsEditable(pending.editable);
      if (pending.stage === "ideation" && run.gap_run) {
        setNeeds(run.gap_run.needs);
      }
      setPhase("questions");
    },
    [pendingRun, setNeeds, setPhase],
  );

  const handleOrchestrateComplete = useCallback(
    (result: JobResult) => {
      const data = result.result as OrchestrateResult | null;
      if (data?.status === "awaiting_answers") {
        setQuestions(data.questions ?? []);
        setQuestionsEditable(true);
        setPhase("questions");
        return;
      }
      onOtherResult(result);
    },
    [onOtherResult, setPhase],
  );

  const retryOrchestrate = useCallback(
    async (fallback: () => void) => {
      const run = await refreshPending();
      if (run?.pending_questions) {
        handleOpenQuestions(run);
      } else {
        fallback();
      }
    },
    [refreshPending, handleOpenQuestions],
  );

  const handleSubmitAnswers = useCallback(
    async (answers: QuestionAnswerIn[]) => {
      setSubmitError("");
      setAnswersSubmitting(true);
      try {
        const job = await orchestrate(SUBMIT_INTENT, [], false, undefined, {
          questionAnswers: answers,
        });
        setJobId(job.job_id);
        setPhase("orchestrating");
      } catch {
        setSubmitError(SUBMIT_FAILED);
      } finally {
        setAnswersSubmitting(false);
      }
    },
    [setJobId, setPhase],
  );

  return {
    questions,
    questionsEditable,
    answersSubmitting,
    submitError,
    pendingRun,
    refreshPending,
    handleOpenQuestions,
    handleOrchestrateComplete,
    retryOrchestrate,
    handleSubmitAnswers,
  };
}
