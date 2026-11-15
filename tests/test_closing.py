"""``close_all``: every close is attempted, within its time limit, whatever the others do."""

from __future__ import annotations

import asyncio

import pytest
from _loop_helpers import Stubborn, drive, drive_timed

from whitespace.closing import Closer, close_all

_LIMIT = 0.05


def _closer(names: list[str], name: str, error: BaseException | None = None) -> Closer:
    async def close() -> None:
        names.append(name)
        if error is not None:
            raise error

    return (name, close)


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_an_ordinary_error_does_not_stop_the_later_closes() -> None:
    names: list[str] = []
    closers = [
        _closer(names, "a"),
        _closer(names, "b", ValueError("broken")),
        _closer(names, "c"),
        _closer(names, "d"),
    ]

    drive(lambda: close_all(closers, seconds=_LIMIT))

    assert names == ["a", "b", "c", "d"]


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_a_cancelled_close_is_raised_after_the_later_closes() -> None:
    names: list[str] = []
    closers = [
        _closer(names, "a", asyncio.CancelledError()),
        _closer(names, "b"),
        _closer(names, "c"),
        _closer(names, "d"),
    ]
    seen_at_raise: list[str] = []

    try:
        drive(lambda: close_all(closers, seconds=_LIMIT))
    except asyncio.CancelledError:
        seen_at_raise = list(names)

    assert seen_at_raise == ["a", "b", "c", "d"]


@pytest.mark.parametrize("interruption", [KeyboardInterrupt(), SystemExit(1)], ids=repr)
@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_an_interrupting_close_is_raised_after_the_later_closes(
    interruption: BaseException,
) -> None:
    names: list[str] = []
    closers = [_closer(names, "a", interruption)] + [_closer(names, n) for n in "bcd"]
    seen_at_raise: list[str] = []

    with pytest.raises(type(interruption)) as raised:
        try:
            drive(lambda: close_all(closers, seconds=_LIMIT))
        except BaseException:
            seen_at_raise = list(names)
            raise

    assert raised.value is interruption
    assert seen_at_raise == ["a", "b", "c", "d"]


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_the_first_of_two_interruptions_is_raised() -> None:
    names: list[str] = []
    closers = [
        _closer(names, "a", KeyboardInterrupt()),
        _closer(names, "b"),
        _closer(names, "c", SystemExit(1)),
        _closer(names, "d"),
    ]

    with pytest.raises(KeyboardInterrupt):
        drive(lambda: close_all(closers, seconds=_LIMIT))

    assert names == ["a", "b", "c", "d"]


@pytest.mark.parametrize("interruption", [KeyboardInterrupt(), SystemExit(1)], ids=repr)
@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_an_interruption_inside_a_nested_close_all_still_lets_every_close_run(
    interruption: BaseException,
) -> None:
    names: list[str] = []
    inner = [_closer(names, "inner-a", interruption)] + [
        _closer(names, f"inner-{n}") for n in "bcd"
    ]

    async def close_inner() -> None:
        await close_all(inner, seconds=_LIMIT)

    outer = [("inner", close_inner), _closer(names, "outer-b")]

    with pytest.raises(type(interruption)):
        drive(lambda: close_all(outer, seconds=None))

    assert names == ["inner-a", "inner-b", "inner-c", "inner-d", "outer-b"]


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
def test_a_close_that_never_ends_is_left_behind_at_the_limit() -> None:
    names: list[str] = []
    work = Stubborn()

    async def stubborn() -> None:
        names.append("c")
        await work.run()

    closers = [_closer(names, "a"), _closer(names, "b"), ("c", stubborn), _closer(names, "d")]

    elapsed = drive_timed(lambda: close_all(closers, seconds=_LIMIT), work)

    assert names == ["a", "b", "c", "d"]
    assert elapsed < 1.0


@pytest.mark.protects("interrupted-close-finishes-the-cleanup")
async def test_a_cancelled_caller_still_attempts_the_later_closes() -> None:
    names: list[str] = []
    started = asyncio.Event()

    async def slow() -> None:
        names.append("a")
        started.set()
        await asyncio.sleep(10)

    closers = [("a", slow)] + [_closer(names, n) for n in "bcd"]
    caller = asyncio.ensure_future(close_all(closers, seconds=_LIMIT))
    await started.wait()

    caller.cancel()

    with pytest.raises(asyncio.CancelledError):
        await caller
    assert names == ["a", "b", "c", "d"]


def test_with_no_limit_a_slow_close_is_awaited_to_its_end() -> None:
    names: list[str] = []

    async def slow() -> None:
        await asyncio.sleep(0.1)
        names.append("slow")

    drive(lambda: close_all([("slow", slow), _closer(names, "next")], seconds=None))

    assert names == ["slow", "next"]
