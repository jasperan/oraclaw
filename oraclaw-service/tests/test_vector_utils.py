"""Tests for vector utility functions."""

import array

from oraclaw_service.services.memory_service import _to_vector


def test_to_vector_returns_array():
    """_to_vector converts list[float] to array.array('f', ...)."""
    embedding = [0.1, 0.2, 0.3, 0.4]
    result = _to_vector(embedding)
    assert isinstance(result, array.array)
    assert result.typecode == 'f'
    assert len(result) == 4


def test_to_vector_preserves_values():
    """Values are approximately preserved (float32 precision)."""
    embedding = [0.123456789, -0.987654321, 0.0, 1.0]
    result = _to_vector(embedding)
    for orig, converted in zip(embedding, result):
        assert abs(orig - converted) < 1e-6


def test_to_vector_384_dims():
    """Handles full 384-dimension embeddings (MiniLM output size)."""
    embedding = [0.01 * i for i in range(384)]
    result = _to_vector(embedding)
    assert len(result) == 384


def test_to_vector_empty():
    """Handles empty embedding gracefully."""
    result = _to_vector([])
    assert isinstance(result, array.array)
    assert len(result) == 0
