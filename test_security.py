"""Tests for security features: path traversal protection, PHI guard, and input validation."""

import os
import sys
import tempfile
import pytest

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.base import PHIGuard, SecurityException, assert_no_phi
from reference_interval_builder import _safe_resolve_path


class TestPathTraversalProtection:
    """Tests for safe path resolution."""

    def test_rejects_dotdot_components(self):
        with pytest.raises(ValueError, match="traversal"):
            _safe_resolve_path("../etc/passwd")

    def test_rejects_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            _safe_resolve_path("nonexistent_file_12345.csv")

    def test_accepts_existing_file(self, tmp_path):
        test_file = tmp_path / "test.csv"
        test_file.write_text("col1,col2\n1,2\n")
        result = _safe_resolve_path(str(test_file))
        assert result.exists()
        assert result.is_file()

    def test_rejects_directory(self, tmp_path):
        with pytest.raises(ValueError, match="not a regular file"):
            _safe_resolve_path(str(tmp_path))


class TestPHIGuard:
    """Tests for the PHI outbound guard."""

    def test_allows_clean_text(self):
        assert_no_phi("glucose level is 100 mg/dL")

    def test_blocks_ssn_pattern(self):
        with pytest.raises(SecurityException, match="PHI Outbound Guard Violation"):
            assert_no_phi("Patient SSN: 123-45-6789")

    def test_blocks_mrn_pattern(self):
        with pytest.raises(SecurityException, match="PHI Outbound Guard Violation"):
            assert_no_phi("MRN-12345678")

    def test_blocks_phone_number(self):
        with pytest.raises(SecurityException, match="PHI Outbound Guard Violation"):
            assert_no_phi("Call 555-123-4567")

    def test_blocks_email(self):
        with pytest.raises(SecurityException, match="PHI Outbound Guard Violation"):
            assert_no_phi("Email: patient@example.com")

    def test_blocks_dob_pattern(self):
        with pytest.raises(SecurityException, match="PHI Outbound Guard Violation"):
            assert_no_phi("DOB: 01/15/1990")

    def test_blocks_patient_name(self):
        with pytest.raises(SecurityException, match="PHI Outbound Guard Violation"):
            assert_no_phi("Patient Name: John Smith")

    def test_empty_string_is_safe(self):
        assert_no_phi("")

    def test_none_is_safe(self):
        assert_no_phi(None)

    def test_phi_message_does_not_leak_pattern(self):
        """Ensure the exception message doesn't reveal the regex pattern."""
        try:
            assert_no_phi("SSN: 123-45-6789")
            assert False, "Should have raised SecurityException"
        except SecurityException as e:
            # The message should NOT contain the regex pattern
            assert "123-45-6789" not in str(e)
            assert "\\d{3}" not in str(e)
            assert "pattern" not in str(e).lower() or "sensitive identifier" in str(e).lower()

    def test_redact_phi_replaces_sensitive_data(self):
        text = "Patient John Smith, SSN: 123-45-6789"
        redacted = PHIGuard.redact_phi(text)
        assert "123-45-6789" not in redacted
        assert "REDACTED" in redacted


class TestInputValidation:
    """Tests for CLI input validation."""

    def test_ci_level_below_half_rejected(self):
        from reference_interval_builder import main
        with pytest.raises(SystemExit):
            main(["--input", "sample_data.csv", "--value-column", "glucose", "--ci", "0.3"])

    def test_ci_level_above_one_rejected(self):
        from reference_interval_builder import main
        with pytest.raises(SystemExit):
            main(["--input", "sample_data.csv", "--value-column", "glucose", "--ci", "1.5"])

    def test_nonexistent_input_file_handled_gracefully(self):
        from reference_interval_builder import main
        result = main(["--input", "nonexistent.csv", "--value-column", "glucose"])
        assert result == 1  # Should return error code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
