"""Per-call cancellation, including between solves inside a fallback horizon."""

from contextvars import ContextVar

predicate = ContextVar("dispatch_cancelled", default=None)


class CancelledOperation(Exception):
    pass


def checkpoint():
    callback = predicate.get()
    if callback and callback():
        raise CancelledOperation()
