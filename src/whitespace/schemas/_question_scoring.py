from __future__ import annotations

from whitespace.schemas.question import QuestionRecord

# REVISIT: tune if results suggest.
ANSWERED_BONUS = 1.0
SKIP_PENALTY = -0.3
EXPIRED_SIGNAL = 0.0
SELECTION_BONUS = 2.0
SURVIVAL_BONUS_MAX = 0.25
RERUN_PENALTY = -0.3
EXACT_DUPLICATE_THRESHOLD = 0.95
QUESTION_CAP = 3
ENGAGEMENT_DIGEST_SIZE = 12


def compute_outcome_score(record: QuestionRecord) -> float:
    status_signal = {
        "pending": 0.0,
        "answered": ANSWERED_BONUS,
        "skipped": SKIP_PENALTY,
        "expired": EXPIRED_SIGNAL,
    }[record.status]
    score = status_signal + record.survival_bonus + record.selection_bonus + record.rerun_penalty
    if record.status == "answered" and not record.survival_bonus and not record.selection_bonus:
        return min(score, 0.0)
    return score
