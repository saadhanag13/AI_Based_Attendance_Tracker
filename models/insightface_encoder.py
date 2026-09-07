"""InsightFace ``buffalo_l`` implementation of :class:`FaceEncoder`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

try:
    from insightface.app import FaceAnalysis
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    FaceAnalysis = None

from .base import DetectedFace, FaceEncoder, FaceModelError

MODEL_NAME = "buffalo_l"
DEFAULT_MODEL_ROOT = Path(__file__).resolve().parent.parent / ".insightface"
DETECTION_THRESHOLD = 0.50
DETECTION_SIZE = (640, 640)
DEFAULT_PROVIDERS = ["CPUExecutionProvider"]


class InsightFaceEncoder(FaceEncoder):
    """Wraps InsightFace's :class:`FaceAnalysis` pipeline for ``buffalo_l``."""

    def __init__(
        self,
        root: Path | str = DEFAULT_MODEL_ROOT,
        providers: list[str] | None = None,
    ) -> None:
        self._root = Path(root)
        self._providers = providers or DEFAULT_PROVIDERS
        self._analyzer = None

    @staticmethod
    def model_name() -> str:
        return MODEL_NAME

    def load(self) -> None:
        if FaceAnalysis is None:
            raise FaceModelError(
                "The 'insightface' package is not installed. "
                "Install it via requirements.txt before using this model."
            )
        if self._analyzer is not None:
            return
        try:
            analyzer = FaceAnalysis(
                name=MODEL_NAME,
                root=str(self._root),
                providers=self._providers,
            )
            analyzer.prepare(
                ctx_id=-1, det_thresh=DETECTION_THRESHOLD, det_size=DETECTION_SIZE
            )
        except Exception as exc:  # pragma: no cover - runtime/network dependent
            raise FaceModelError(
                "InsightFace could not initialize. First run downloads the model "
                "pack, so network access and disk space are required."
            ) from exc
        self._analyzer = analyzer

    def detect_and_embed(self, image: np.ndarray) -> list[DetectedFace]:
        self.load()
        faces = self._analyzer.get(image)
        return [
            DetectedFace(
                box=tuple(int(v) for v in face.bbox),
                confidence=float(face.det_score),
                embedding=np.asarray(face.normed_embedding, dtype=np.float32),
            )
            for face in faces
        ]


@lru_cache(maxsize=1)
def _get_shared_analyzer() -> InsightFaceEncoder:
    encoder = InsightFaceEncoder()
    encoder.load()
    return encoder


def shared_analyzer() -> InsightFaceEncoder:
    """Return a process-wide singleton encoder (reused across requests)."""
    return _get_shared_analyzer()
