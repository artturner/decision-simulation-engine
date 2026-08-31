"""Unit tests for student-name whitespace normalization."""

from __future__ import annotations

from app.services.names import normalize_student_name


class TestNormalizeStudentName:
    def test_collapses_internal_runs_of_spaces(self):
        assert (
            normalize_student_name("Jalen  Anguiano-Bonsignore")
            == "Jalen Anguiano-Bonsignore"
        )

    def test_trims_leading_and_trailing_whitespace(self):
        assert normalize_student_name("  Alice Adams \t") == "Alice Adams"

    def test_collapses_tabs_and_newlines(self):
        assert normalize_student_name("Alice\t\nAdams") == "Alice Adams"

    def test_already_normalized_is_unchanged(self):
        assert normalize_student_name("Alice Adams") == "Alice Adams"

    def test_none_and_empty_return_empty_string(self):
        assert normalize_student_name(None) == ""
        assert normalize_student_name("") == ""
        assert normalize_student_name("   ") == ""
