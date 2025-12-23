"""Smoke tests for structured extraction functions."""

import inspect

from gdd_rag_backbone.gdd import extract_maps, extract_objects, extract_tanks


def _assert_coroutine(fn):
    sig = inspect.signature(fn)
    assert "doc_id" in sig.parameters
    assert inspect.iscoroutinefunction(fn)


def test_extract_tanks_signature():
    _assert_coroutine(extract_tanks)


def test_extract_maps_signature():
    _assert_coroutine(extract_maps)


def test_extract_objects_signature():
    _assert_coroutine(extract_objects)

