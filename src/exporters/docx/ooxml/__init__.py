"""OOXML post-processing of Pandoc's output: what Word styles alone cannot express."""

from .context import PassContext
from .pipeline import DEFAULT_PASSES, PostProcessor

__all__ = ["DEFAULT_PASSES", "PassContext", "PostProcessor"]
