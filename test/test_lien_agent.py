"""Tests for page-level lien signature validation."""

import pytest

from app.agents.lien_agent import _split_has_required_signature


@pytest.mark.parametrize(
    ("split_signature_type", "required_signature_type"),
    [
        ("ASL", "ASL"),
        ("PSL", "PSL"),
        ("asl", "ASL"),
        ("psl", "PSL"),
    ],
)
def test_split_has_required_signature_accepts_only_matching_type(
    split_signature_type,
    required_signature_type,
):
    assert _split_has_required_signature(split_signature_type, required_signature_type)


@pytest.mark.parametrize(
    ("split_signature_type", "required_signature_type"),
    [
        ("PSL", "ASL"),
        ("ASL", "PSL"),
        ("UNKNOWN", "ASL"),
        ("UNKNOWN", "PSL"),
        ("", "ASL"),
        (None, "PSL"),
    ],
)
def test_split_has_required_signature_rejects_missing_or_mismatched_type(
    split_signature_type,
    required_signature_type,
):
    assert not _split_has_required_signature(split_signature_type, required_signature_type)
