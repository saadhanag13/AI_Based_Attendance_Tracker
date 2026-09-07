"""Abstract interface for face detection/embedding models.

Any face model (insightface, face_recognition, etc.) can be adapted by
implementing :class:`FaceEncoder`. The rest of the application only depends on
this interface, which is what makes the model layer swappable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


class FaceModelError(Exception):
    """Raised for model initialisation or runtime errors."""


@dataclass(frozen=True)
class DetectedFace:
    """A single detected face with its bounding box, confidence and embedding."""

    box: tuple[int, int, int, int]
    confidence: float
    embedding: np.ndarray


class FaceEncoder(ABC):
    """Detect faces and produce normalized face embeddings from images."""

    @staticmethod
    @abstractmethod
    def model_name() -> str:
        """Stable identifier used to persist/select this model."""

    @abstractmethod
    def load(self) -> None:
        """Initialise the underlying model. May download assets on first run."""

    @abstractmethod
    def detect_and_embed(self, image: np.ndarray) -> list[DetectedFace]:
        """Return one :class:`DetectedFace` per face found in the RGB image."""

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two normalized embeddings (default impl)."""
        a = np.asarray(a, dtype=np.float32).ravel()
        b = np.asarray(b, dtype=np.float32).ravel()
        return float(a @ b)
