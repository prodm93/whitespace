"""The final status and result shape that the SaaS pipeline function publishes."""

from __future__ import annotations

import _saas_helpers  # noqa: F401  (puts the pipeline function folder on the import path)
import pytest


@pytest.mark.protects("job-status-shape")
def test_final_result_done_when_proposals() -> None:
    from _loop import _compute_final_result

    r = _compute_final_result({"proposals": [{"title": "x"}], "needs": [], "blocked_reason": None})
    assert r["status"] == "done"


@pytest.mark.protects("job-status-shape")
def test_final_result_blocked_beats_awaiting() -> None:
    from _loop import _compute_final_result

    r = _compute_final_result(
        {
            "proposals": [],
            "needs": [{"title": "x"}],
            "blocked_reason": "need profile",
        }
    )
    assert r["status"] == "blocked"
    assert r["reason"] == "need profile"


@pytest.mark.protects("job-status-shape")
def test_final_result_awaiting_when_needs_no_proposals() -> None:
    from _loop import _compute_final_result

    r = _compute_final_result({"proposals": [], "needs": [{"title": "x"}], "blocked_reason": None})
    assert r["status"] == "awaiting_selection"


@pytest.mark.protects("job-status-shape")
def test_final_result_done_when_nothing() -> None:
    from _loop import _compute_final_result

    r = _compute_final_result({"proposals": [], "needs": [], "blocked_reason": None})
    assert r["status"] == "done"
