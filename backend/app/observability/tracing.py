from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4


request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
session_id_context: ContextVar[str | None] = ContextVar("session_id", default=None)


def get_request_id() -> str:
    current = request_id_context.get()
    if current:
        return current
    generated = str(uuid4())
    request_id_context.set(generated)
    return generated


def get_trace_context() -> dict:
    return {
        "request_id": request_id_context.get(),
        "session_id": session_id_context.get(),
    }


@contextmanager
def trace_context(request_id: str | None = None, session_id: str | None = None):
    request_token = request_id_context.set(request_id or str(uuid4()))
    session_token = session_id_context.set(session_id)
    try:
        yield
    finally:
        request_id_context.reset(request_token)
        session_id_context.reset(session_token)

