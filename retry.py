"""Retry utilities module."""

from functools import wraps
from typing import Callable

from tenacity import retry

from kytos.core import log


def before_fn(state) -> None:
    """Before function for tenacity to also logs args and kwargs."""
    log.warning(
        f"Retry #{state.attempt_number} for {state.fn.__name__}, "
        f"args: {state.args}, kwargs: {state.kwargs}, "
        f"seconds since start: {state.seconds_since_start:.2f}",
    )


def retries(func: Callable, **tenacity_kwargs) -> Callable:
    """Retries decorator."""
    @retry(**tenacity_kwargs)
    @wraps(func)
    def decorated(*args, **kwargs):
        return func(*args, **kwargs)

    return decorated


def for_all_methods(decorator: Callable, **kwargs) -> Callable:
    """Decorator for all methods."""

    def decorated(cls):
        for attr in [
            name
            for name in dir(cls)
            if callable(getattr(cls, name))
            and not name.startswith("_")
            and not hasattr(getattr(cls, name), "__wrapped__")
        ]:
            setattr(cls, attr, decorator(getattr(cls, attr), **kwargs))
        return cls

    return decorated
