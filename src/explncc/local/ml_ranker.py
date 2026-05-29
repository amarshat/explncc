"""Optional trained-model ranker hook (LocalRankerV2).

This is an extension point only. No model is trained or bundled, and no ML
dependency is imported at module load. A future trained ranker (sklearn / BERT
/ ONNX) can implement :class:`LocalModelRanker` behind the optional ``[ml]``
extra and be selected with ``--ranker model --model-path PATH``.

Until a model exists, requesting ``--ranker model`` fails clearly.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from explncc.local.ranker import RankedFinding
from explncc.models import OptimizationRecord


class ModelRankerUnavailable(RuntimeError):
    """Raised when a model ranker is requested but cannot be loaded."""


class LocalModelRanker:
    """Interface for a future trained local ranker.

    Concrete implementations load a serialized model and produce the same
    :class:`RankedFinding` outputs as the heuristic ranker, so callers can swap
    rankers without changing downstream rendering.
    """

    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path

    @classmethod
    def load(cls, path: Path) -> LocalModelRanker:
        """Load a model from ``path``.

        No trained artifact format is defined yet, so this always raises
        :class:`ModelRankerUnavailable`. The signature is stable so a future
        implementation can plug in without changing the CLI.
        """

        raise ModelRankerUnavailable(
            "the trained model ranker is not implemented yet; install the optional "
            "'ml' extra and provide a supported model, or use --ranker heuristic. "
            f"(requested model path: {path})"
        )

    def rank(self, records: Sequence[OptimizationRecord]) -> list[RankedFinding]:
        """Rank records using the loaded model (not implemented)."""

        raise ModelRankerUnavailable("the trained model ranker is not implemented yet")
