"""Factories for the external services. Tests replace them with fakes."""
from app.llm.client import LLMClient
from app.research.adapter import TinyFishAdapter

_adapter_factory = lambda: TinyFishAdapter()  # noqa: E731
_llm_factory = lambda: LLMClient()            # noqa: E731


def get_adapter():
    return _adapter_factory()


def get_llm():
    return _llm_factory()


def override(adapter_factory=None, llm_factory=None):
    global _adapter_factory, _llm_factory
    if adapter_factory:
        _adapter_factory = adapter_factory
    if llm_factory:
        _llm_factory = llm_factory
