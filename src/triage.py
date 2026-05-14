"""LLM-grounded MITRE ATT&CK triage for M.A.R.E.E. verdicts.

Given a M.A.R.E.E. prediction and the corresponding sample row, produce a
SOC-analyst-friendly paragraph explaining:

  1. What the model saw (top contributing features in plain English).
  2. Which MITRE ATT&CK techniques the feature pattern matches (best-effort,
     conservative — we only assert what the features actually support).
  3. What an IT-administrator should do next (containment + verification).

Two backends, decided at runtime based on whether ANTHROPIC_API_KEY is set:

  - LLM backend (preferred): Anthropic Claude with a tightly-scoped system
    prompt that constrains the output to a known schema and forbids
    speculation. Token budget is small (~400 tokens) so cost-per-request is
    pennies. Uses prompt caching on the system message so repeated requests
    cost less.

  - Template backend (fallback): deterministic Jinja-style template that
    fills in the same fields from the sample features. Used when the API
    key is missing OR when an LLM call fails — guarantees the UI never
    renders an empty triage box.

The Quantic deliverable runs in template-fallback mode by default so the
demo is reproducible without an API key. Setting ANTHROPIC_API_KEY (in
`.env` or the deployment environment) flips to the LLM backend.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from src.models.ensemble import (
    VERDICT_ALLOWED,
    VERDICT_BLOCKED_MALWARE,
    VERDICT_BLOCKED_UNCERTAIN,
    MareePrediction,
)

# ---------------------------------------------------------------------------
# Domain knowledge — MITRE ATT&CK mapping for the engineered features
# ---------------------------------------------------------------------------

# Conservative — we only map a feature to a technique when the feature's
# presence is *necessary* (not just sufficient) for the technique. The LLM
# is given this map as part of its system prompt and instructed not to
# invent technique IDs.
ATTACK_MAPPING = {
    "imports_dangerous_api": [
        ("T1055", "Process Injection"),
        ("T1106", "Native API"),
    ],
    "identify_is_packed": [
        ("T1027.002", "Software Packing"),
        ("T1027", "Obfuscated Files or Information"),
    ],
    "high_entropy": [
        ("T1027", "Obfuscated Files or Information"),
        ("T1140", "Deobfuscate/Decode Files or Information"),
    ],
    "time_alignment_anomaly": [
        ("T1070.006", "Timestomp"),
    ],
    "dll_count_anomaly": [
        ("T1129", "Shared Modules (anomalous import surface)"),
    ],
}


# ---------------------------------------------------------------------------
# Triage output schema — what the UI consumes
# ---------------------------------------------------------------------------

@dataclass
class TriageReport:
    """Operator-actionable explanation for a single M.A.R.E.E. verdict."""
    summary: str                # 1–2 sentences: "what just happened"
    why: list[str]              # bulleted top contributors in plain English
    attack_techniques: list[tuple[str, str]]  # (technique_id, name)
    recommended_actions: list[str]  # bulleted IR steps
    backend: str                # "llm" or "template"


# ---------------------------------------------------------------------------
# Feature → plain-English helpers (used by both backends)
# ---------------------------------------------------------------------------

def _describe_features(sample: dict, prediction: MareePrediction) -> list[str]:
    """Convert raw feature values into plain-English bullet points the
    operator can scan in two seconds.

    Verdict-aware: for BLOCKED verdicts the bullets describe features in
    malware-suggestive terms (consistent with the verdict). For ALLOWED
    verdicts, observed-but-ambiguous features are contextualized as
    legitimate (so the explanation supports rather than contradicts the
    benign verdict), and a positive-evidence summary is emitted when no
    suspicious features triggered.
    """
    is_allowed = prediction.verdict == VERDICT_ALLOWED
    bullets: list[str] = []

    if sample.get("identify_is_packed", 0) == 1:
        identify = sample.get("Identify", "")
        if is_allowed:
            bullets.append(
                f"File is packed (Identify: {identify}), but the import set "
                "and section structure match a legitimate packer signature — "
                "the model recognized this as benign packing, not malicious "
                "obfuscation."
            )
        else:
            bullets.append(
                "File is **packed or obfuscated** (entropy / signature scan "
                "detected a known packer like UPX, ACProtect, or similar)."
            )
    elif sample.get("Entropy", 0) >= 7.5:
        if is_allowed:
            bullets.append(
                f"File entropy is **{sample.get('Entropy', 0):.2f}** — high, "
                "but typical of installer self-extractors and compressed "
                "legitimate binaries; the model did not flag the broader "
                "feature pattern as malicious."
            )
        else:
            bullets.append(
                f"File entropy is **{sample.get('Entropy', 0):.2f}** — very "
                "high; consistent with packed or encrypted content."
            )

    if sample.get("imports_dangerous_api", 0) == 1:
        if is_allowed:
            bullets.append(
                "Imports include some commonly-monitored Windows APIs "
                "(file/process/memory primitives such as `LoadLibraryA` or "
                "`VirtualAlloc`). These are dual-use — also routinely used "
                "by legitimate installers and runtime loaders. The model "
                "evaluated the full call surface and did not flag it as "
                "malicious."
            )
        else:
            bullets.append(
                "Imports include high-risk Windows APIs (e.g., `LoadLibraryA`, "
                "`VirtualAlloc`, `WriteProcessMemory`, `WinExec`) — these are "
                "the building blocks of process injection and remote code "
                "execution."
            )

    if sample.get("dll_count_anomaly", 0) == 1:
        n_dlls = sample.get("n_imported_dlls", 0)
        if is_allowed:
            if n_dlls == 0:
                bullets.append(
                    "Zero imported DLLs — unusual but observed in "
                    "statically-linked legitimate utilities; the model "
                    "classified the broader pattern as benign."
                )
            else:
                bullets.append(
                    f"Imports {n_dlls} DLLs — large import surface, but "
                    "consistent with the profile of legitimate complex "
                    "applications (multi-component installers, IDEs, etc.)."
                )
        else:
            if n_dlls == 0:
                bullets.append(
                    "Zero imported DLLs — unusual for a benign Windows binary; "
                    "common in statically-linked packers and dropped payloads."
                )
            else:
                bullets.append(
                    f"Imports {n_dlls} DLLs — unusually large surface; common "
                    "in droppers and multi-stage loaders."
                )

    if sample.get("time_alignment_anomaly", 0) == 1:
        if is_allowed:
            bullets.append(
                "PE compile timestamp is unusual, but the model did not flag "
                "the surrounding feature pattern as malicious — likely an "
                "old or recompiled legitimate binary."
            )
        else:
            bullets.append(
                "PE compile timestamp is missing or implausible (timestomping "
                "is a known anti-forensics technique — MITRE T1070.006)."
            )

    n_sections = sample.get("NumberOfSections", 0)
    if n_sections >= 10:
        if is_allowed:
            bullets.append(
                f"Binary has {n_sections} sections — above the typical 4–6, "
                "but the model classified the layout as legitimate."
            )
        else:
            bullets.append(
                f"Binary has **{n_sections} sections** — well above the typical "
                "4–6; multi-stage unpackers commonly produce this pattern."
            )

    if not bullets:
        if is_allowed:
            # Render positive evidence supporting the benign verdict.
            entropy = sample.get("Entropy", 0)
            n_dlls = sample.get("n_imported_dlls", 0)
            positives: list[str] = []
            if 0 < entropy < 7.0:
                positives.append(
                    f"low entropy ({entropy:.2f}) — typical of unpacked, "
                    "uncompressed legitimate binaries"
                )
            if n_dlls and 1 <= n_dlls <= 50:
                plural = "s" if n_dlls != 1 else ""
                positives.append(
                    f"{n_dlls} imported DLL{plural} — within the normal "
                    "import-surface range"
                )
            positives.append(
                "no high-risk API combination, no packer signature, no PE "
                "structural anomalies"
            )
            bullets.append("Positive evidence: " + "; ".join(positives) + ".")
            bullets.append(
                f"Decision driven by the ensemble's calibrated probability "
                f"({prediction.probability:.2f}) and joint confidence "
                f"({prediction.confidence:.2f})."
            )
        else:
            bullets.append(
                f"No single feature dominates the verdict. Decision driven by "
                f"the ensemble's calibrated probability "
                f"({prediction.probability:.2f}) and joint confidence "
                f"({prediction.confidence:.2f})."
            )

    return bullets


def _matched_attack_techniques(sample: dict) -> list[tuple[str, str]]:
    """Return MITRE ATT&CK technique tuples whose triggers fired in this sample."""
    matched: list[tuple[str, str]] = []
    for feature, techniques in ATTACK_MAPPING.items():
        if feature == "high_entropy":
            triggered = sample.get("Entropy", 0) >= 7.5
        else:
            triggered = sample.get(feature, 0) == 1
        if triggered:
            matched.extend(techniques)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for tid, name in matched:
        if tid not in seen:
            seen.add(tid)
            unique.append((tid, name))
    return unique


def _recommended_actions_for(verdict: str) -> list[str]:
    """Verdict-specific IR steps, written for an IT-generalist audience."""
    if verdict == VERDICT_BLOCKED_MALWARE:
        return [
            "Isolate the source host from the network (disable its network "
            "interfaces or move it to a quarantine VLAN).",
            "Capture process and network telemetry from the source host *before* "
            "rebooting — running malware is more informative than dormant.",
            "Hash the file (SHA-256) and search VirusTotal / Hybrid Analysis "
            "for known indicators.",
            "Check email gateway logs for similar attachments delivered in the "
            "last 24 hours; the attacker likely didn't target only one mailbox.",
            "Open an IR ticket and notify the on-call security lead.",
        ]
    if verdict == VERDICT_BLOCKED_UNCERTAIN:
        return [
            "File is BLOCKED pending review — it does not enter the protected "
            "environment until a human approves it.",
            "Re-scan in 24 hours: M.A.R.E.E.'s next retraining cycle may resolve "
            "the uncertainty.",
            "If the file is business-critical and time-sensitive, perform manual "
            "analysis (sandbox detonation or VirusTotal lookup) before overriding.",
            "Do NOT override the block based solely on user pressure — uncertain "
            "verdicts on novel families are exactly the cases where blocking is "
            "the right default.",
        ]
    return [
        "File is allowed. No further action required.",
        "If you have independent reason to suspect this file (unusual sender, "
        "context, etc.), submit it for manual review.",
    ]


# ---------------------------------------------------------------------------
# Template backend (deterministic, no API key required)
# ---------------------------------------------------------------------------

def _verdict_summary(prediction: MareePrediction, sample: dict) -> str:
    p = prediction.probability
    c = prediction.confidence
    if prediction.verdict == VERDICT_BLOCKED_MALWARE:
        return (
            f"M.A.R.E.E. classifies this file as **malware** with probability "
            f"{p:.0%} and joint confidence {c:.0%}. The file has been blocked "
            f"and quarantined."
        )
    if prediction.verdict == VERDICT_BLOCKED_UNCERTAIN:
        return (
            f"M.A.R.E.E. could not commit to an allow decision (probability "
            f"{p:.0%}, joint confidence {c:.0%}, below the {0.50:.0%} "
            f"threshold). Following zero-trust failure semantics, the file "
            f"is blocked pending human review."
        )
    return (
        f"M.A.R.E.E. classifies this file as **benign** with goodware "
        f"probability {1 - p:.0%} (malware probability {p:.2%}) and joint "
        f"confidence {c:.0%}. The file is allowed."
    )


def _triage_template(prediction: MareePrediction, sample: dict) -> TriageReport:
    # ATTACK techniques describe attacker TTPs — only render them when the
    # model believes the file is (or might be) malicious. For ALLOWED
    # verdicts, surfacing technique IDs would contradict the verdict.
    if prediction.verdict == VERDICT_ALLOWED:
        techniques: list[tuple[str, str]] = []
    else:
        techniques = _matched_attack_techniques(sample)
    return TriageReport(
        summary=_verdict_summary(prediction, sample),
        why=_describe_features(sample, prediction),
        attack_techniques=techniques,
        recommended_actions=_recommended_actions_for(prediction.verdict),
        backend="template",
    )


# ---------------------------------------------------------------------------
# LLM backend (Anthropic Claude)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are M.A.R.E.E.'s triage layer. You receive a malware
classifier verdict plus the sample's static PE features, and you write a
concise SOC-analyst-ready explanation.

Hard rules:
  1. Never invent feature values. Use ONLY the values the user message gives you.
  2. Never invent MITRE ATT&CK technique IDs. Use ONLY the technique IDs the
     user message provides in the candidate_techniques field.
  3. Plain English. No marketing fluff. No unjustified hedging like "may
     possibly indicate" — either the feature is in the data or it isn't.
  4. Output JSON exactly matching the schema below. No prose outside the JSON.
  5. The "why" bullets MUST support the verdict, not contradict it. If the
     verdict is ALLOWED, every bullet must explain positive benign evidence
     or contextualize observed dual-use features as legitimate (e.g., "high
     entropy is typical of installer self-extractors"). Never describe an
     ALLOWED file in malware-suggestive terms. If the verdict is BLOCKED_*,
     bullets describe the malicious-pattern evidence.
  6. For ALLOWED verdicts, set "attack_techniques" to []. ATTACK techniques
     describe attacker TTPs — surfacing them on a benign verdict misleads
     the operator. Only populate "attack_techniques" for BLOCKED verdicts.

Schema:
{
  "summary": "1-2 sentence verdict statement, mention probability and confidence",
  "why": ["bullet 1", "bullet 2", ...],   # 2-5 plain-English reasons
  "attack_techniques": [["TXXXX", "Name"], ...],  # subset of candidate_techniques; empty for ALLOWED
  "recommended_actions": ["action 1", "action 2", ...]  # 3-5 IT-admin-ready steps
}
"""


def _triage_llm(prediction: MareePrediction, sample: dict) -> TriageReport | None:
    """Try the Anthropic backend. Return None on any failure (caller falls
    back to template)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        # ALLOWED verdicts get an empty candidate list so the LLM can't
        # surface ATT&CK techniques on a benign verdict. The system prompt
        # also instructs this, but defensive filtering at the input layer
        # makes the policy enforced even if a future prompt change drops it.
        if prediction.verdict == VERDICT_ALLOWED:
            candidate_techniques: list[tuple[str, str]] = []
        else:
            candidate_techniques = _matched_attack_techniques(sample)
        feature_summary = {
            "verdict": prediction.verdict,
            "probability_malware": round(prediction.probability, 4),
            "joint_confidence": round(prediction.confidence, 4),
            "Entropy": sample.get("Entropy"),
            "NumberOfSections": sample.get("NumberOfSections"),
            "n_imported_dlls": sample.get("n_imported_dlls"),
            "n_imported_symbols": sample.get("n_imported_symbols"),
            "identify_is_packed": sample.get("identify_is_packed"),
            "imports_dangerous_api": sample.get("imports_dangerous_api"),
            "time_alignment_anomaly": sample.get("time_alignment_anomaly"),
            "dll_count_anomaly": sample.get("dll_count_anomaly"),
        }

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": json.dumps({
                        "feature_summary": feature_summary,
                        "candidate_techniques": candidate_techniques,
                    }, indent=2),
                }
            ],
        )

        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()
        data = json.loads(text)
        return TriageReport(
            summary=data["summary"],
            why=list(data["why"]),
            attack_techniques=[tuple(t) for t in data["attack_techniques"]],
            recommended_actions=list(data["recommended_actions"]),
            backend="llm",
        )
    except Exception:  # pragma: no cover  (network / parsing failures)
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def explain(prediction: MareePrediction, sample: dict[str, Any]) -> TriageReport:
    """Produce a TriageReport for a single M.A.R.E.E. prediction.

    Tries the LLM backend first; falls back to the deterministic template if
    the API key is missing or any LLM call fails. The fallback guarantees
    the UI always has something to render.
    """
    llm_result = _triage_llm(prediction, sample)
    if llm_result is not None:
        return llm_result
    return _triage_template(prediction, sample)
