"""Shared helpers for reading Oracle LOB values.

Centralizes the "read a LOB to a Python value" dance that the memory,
session, and transcript services previously each copy-pasted. Keeping a
single implementation avoids the silent behavioral drift that crept in
between the copies.
"""

import json

import oracledb


async def read_lob(val):
    """Read a LOB value to a string, or return as-is if already materialized."""
    if val is None:
        return None
    if isinstance(val, (oracledb.AsyncLOB,)):
        return await val.read()
    if hasattr(val, "read") and not isinstance(val, str):
        result = val.read()
        if hasattr(result, "__await__"):
            return await result
        return result
    return val


async def read_json_lob(val) -> dict:
    """Read a LOB (or already-materialized value) and decode it as a JSON object.

    Returns an empty dict for null/unparseable values, and passes through
    values that are already dicts (e.g. Oracle JSON columns decoded by the
    driver).
    """
    raw = await read_lob(val)
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return raw
