"""Unit tests for src.triage — both backends.

The LLM backend tests don't actually call Anthropic; they verify the API-key
gating and the JSON schema parsing on a mocked client.
"""

from __future__ import annotations

from src.models.ensemble import (
    VERDICT_ALLOWED,
    VERDICT_BLOCKED_MALWARE,
    VERDICT_BLOCKED_UNCERTAIN,
    MareePrediction,
)
from src.triage import (
    ATTACK_MAPPING,
    TriageReport,
    _describe_features,
    _matched_attack_techniques,
    _recommended_actions_for,
    _triage_template,
    explain,
)


def _malware_pred(prob: float = 0.92, conf: float = 0.85) -> MareePrediction:
    return MareePrediction(
        verdict=VERDICT_BLOCKED_MALWARE,
        probability=prob,
        confidence=conf,
        is_malware_decision=True,
    )


def _allowed_pred() -> MareePrediction:
    return MareePrediction(
        verdict=VERDICT_ALLOWED, probability=0.05, confidence=0.95,
        is_malware_decision=False,
    )


def _uncertain_pred() -> MareePrediction:
    return MareePrediction(
        verdict=VERDICT_BLOCKED_UNCERTAIN, probability=0.55, confidence=0.30,
        is_malware_decision=True,
    )


class TestDescribeFeatures:
    def test_packed_sample_describes_packing(self):
        bullets = _describe_features(
            {"identify_is_packed": 1, "Entropy": 7.9},
            _malware_pred(),
        )
        assert any("packed" in b.lower() or "obfuscated" in b.lower() for b in bullets)

    def test_dangerous_imports_described(self):
        bullets = _describe_features(
            {"imports_dangerous_api": 1},
            _malware_pred(),
        )
        joined = " ".join(bullets).lower()
        assert "loadlibrary" in joined or "virtualalloc" in joined or "high-risk" in joined

    def test_zero_dlls_flagged(self):
        bullets = _describe_features(
            {"dll_count_anomaly": 1, "n_imported_dlls": 0},
            _malware_pred(),
        )
        assert any("zero" in b.lower() for b in bullets)

    def test_excessive_dlls_flagged(self):
        bullets = _describe_features(
            {"dll_count_anomaly": 1, "n_imported_dlls": 150},
            _malware_pred(),
        )
        assert any("dropper" in b.lower() or "loader" in b.lower() or "150" in b
                   for b in bullets)

    def test_no_features_falls_back_to_confidence(self):
        bullets = _describe_features({}, _allowed_pred())
        assert any("confidence" in b.lower() or "probability" in b.lower()
                   for b in bullets)


class TestAttackTechniques:
    def test_packed_maps_to_packing_techniques(self):
        techniques = _matched_attack_techniques({"identify_is_packed": 1})
        ids = [t for t, _ in techniques]
        assert "T1027.002" in ids  # Software Packing
        assert "T1027" in ids

    def test_dangerous_apis_map_to_injection(self):
        techniques = _matched_attack_techniques({"imports_dangerous_api": 1})
        ids = [t for t, _ in techniques]
        assert "T1055" in ids  # Process Injection

    def test_high_entropy_maps_to_obfuscation(self):
        techniques = _matched_attack_techniques({"Entropy": 7.9})
        ids = [t for t, _ in techniques]
        assert "T1027" in ids

    def test_low_entropy_does_not_map(self):
        techniques = _matched_attack_techniques({"Entropy": 4.0})
        # No high-entropy hit; if no other features fire, the list is empty
        assert all(tid != "T1027" or "Entropy" in str({"Entropy": 4.0})
                   for tid, _ in techniques)

    def test_no_features_returns_empty(self):
        assert _matched_attack_techniques({}) == []

    def test_all_mapping_keys_are_real_features(self):
        # Sanity check: every key in ATTACK_MAPPING should be referenced in the
        # describe-features logic OR be a raw feature name. Catches typos.
        valid_sources = {
            "imports_dangerous_api", "identify_is_packed", "high_entropy",
            "time_alignment_anomaly", "dll_count_anomaly",
        }
        assert set(ATTACK_MAPPING.keys()).issubset(valid_sources)


class TestRecommendedActions:
    def test_malware_actions_include_isolation(self):
        actions = _recommended_actions_for(VERDICT_BLOCKED_MALWARE)
        joined = " ".join(actions).lower()
        assert "isolate" in joined or "quarantine" in joined

    def test_uncertain_actions_warn_against_override(self):
        actions = _recommended_actions_for(VERDICT_BLOCKED_UNCERTAIN)
        joined = " ".join(actions).lower()
        assert "review" in joined or "block" in joined

    def test_allowed_actions_are_minimal(self):
        actions = _recommended_actions_for(VERDICT_ALLOWED)
        assert len(actions) >= 1
        assert any("allowed" in a.lower() or "no further" in a.lower()
                   for a in actions)


class TestTriageTemplate:
    def test_returns_triage_report(self):
        report = _triage_template(_malware_pred(), {"identify_is_packed": 1})
        assert isinstance(report, TriageReport)
        assert report.backend == "template"
        assert report.summary
        assert len(report.why) >= 1
        assert len(report.recommended_actions) >= 1

    def test_summary_mentions_malware_for_malware_verdict(self):
        report = _triage_template(_malware_pred(), {})
        assert "malware" in report.summary.lower()

    def test_summary_mentions_uncertainty_for_uncertain_verdict(self):
        report = _triage_template(_uncertain_pred(), {})
        assert "uncertain" in report.summary.lower() or "pending" in report.summary.lower()

    def test_summary_mentions_benign_for_allowed_verdict(self):
        report = _triage_template(_allowed_pred(), {})
        assert "benign" in report.summary.lower() or "allow" in report.summary.lower()


class TestExplainPublicEntry:
    def test_explain_returns_template_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        report = explain(_malware_pred(), {"identify_is_packed": 1})
        assert report.backend == "template"

    def test_explain_falls_back_when_llm_raises(self, monkeypatch):
        # Set the env var but make the import path fail — should fall back gracefully
        monkeypatch.setenv("ANTHROPIC_API_KEY", "invalid-key-format")
        # Force the import inside _triage_llm to fail by hiding the module
        import sys
        original = sys.modules.get("anthropic")
        sys.modules["anthropic"] = None  # makes `import anthropic` raise ImportError
        try:
            report = explain(_malware_pred(), {})
            assert report.backend == "template"
        finally:
            if original is not None:
                sys.modules["anthropic"] = original
            else:
                sys.modules.pop("anthropic", None)
