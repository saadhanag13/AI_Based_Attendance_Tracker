"""Recognition model layer.

Exposes a small :class:`FaceEncoder` interface so the underlying face
detection/embedding model is swappable. The only concrete implementation is
:class:`InsightFaceEncoder` (buffalo_l); register additional models in
:data:`ENCODERS` and select one by name.
"""

from __future__ import annotations

from .base import DetectedFace, FaceEncoder, FaceModelError
from .insightface_encoder import InsightFaceEncoder, MODEL_NAME

ENCODERS: dict[str, type[FaceEncoder]] = {
    InsightFaceEncoder.model_name(): InsightFaceEncoder,
}


def get_encoder(model_name: str, **kwargs: object) -> FaceEncoder:
    """Return an instantiated (not yet loaded) encoder for ``model_name``.

    Raises :class:`FaceModelError` when the model is unknown.
    """
    try:
        encoder_cls = ENCODERS[model_name]
    except KeyError as exc:
        raise FaceModelError(f"Unknown face model: {model_name!r}") from exc
    return encoder_cls(**kwargs)


__all__ = [
    "DetectedFace",
    "FaceEncoder",
    "FaceModelError",
    "InsightFaceEncoder",
    "MODEL_NAME",
    "get_encoder",
]
