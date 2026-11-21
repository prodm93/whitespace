"""A recording stand-in for the two Bedrock boto3 clients, and the errors they raise."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any

from botocore.exceptions import ClientError


def client_error(code: str, operation: str = "Converse") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "refused"}}, operation)


class StandInBody:
    """The streamed body of an ``invoke_model`` answer.

    ``read`` records its thread, waits ``delay`` seconds, then returns the text or raises
    the error it was given. ``close`` is counted.
    """

    def __init__(self, content: bytes | BaseException, delay: float = 0.0) -> None:
        self._content = content
        self._delay = delay
        self.read_threads: list[int] = []
        self.closes = 0

    def read(self) -> bytes:
        self.read_threads.append(threading.get_ident())
        if self._delay:
            time.sleep(self._delay)
        if isinstance(self._content, BaseException):
            raise self._content
        return self._content

    def close(self) -> None:
        self.closes += 1


Answer = Any | BaseException | Callable[[dict[str, Any]], Any]


class StandInBedrock:
    """Answers ``invoke_model``, ``rerank`` and ``converse`` from a queue of answers.

    Answers are given in turn and the last one repeats. An answer is a value, an error to
    raise, or a function of the call's keyword arguments. For ``invoke_model`` a value that
    is not a ``StandInBody`` is sent as the JSON text of a new body.
    """

    def __init__(self, *answers: Answer) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.bodies: list[StandInBody] = []

    def _answer(self, operation: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((operation, kwargs))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, BaseException):
            raise answer
        return answer(kwargs) if callable(answer) else answer

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        answer = self._answer("invoke_model", kwargs)
        if isinstance(answer, StandInBody):
            body = answer
        else:
            body = StandInBody(json.dumps(answer).encode())
        self.bodies.append(body)
        return {"body": body, "contentType": "application/json"}

    def rerank(self, **kwargs: Any) -> Any:
        return self._answer("rerank", kwargs)

    def converse(self, **kwargs: Any) -> Any:
        return self._answer("converse", kwargs)
