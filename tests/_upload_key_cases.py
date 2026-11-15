"""The upload-key cases that both copies of the ownership rule are tested with."""

from __future__ import annotations

OWN_KEY = "uploads/user_a/abc_cv.pdf"

NOT_OWNED_KEYS: list[object] = [
    "uploads/user_b/abc_cv.pdf",
    "uploads/user_ab/x.pdf",
    "/tmp/whitespace/x.pdf",
    "/tmp/whitespace/user_a/x.pdf",
    "/etc/passwd",
    "uploads/user_a/../user_b/x.pdf",
    "uploads/user_a/",
    "uploads/user_a//x.pdf",
    "",
    "results/j1.json",
    "Uploads/user_a/x.pdf",
    None,
    7,
]

NOT_A_LIST: list[object] = ["uploads/user_a/x.pdf", None]
