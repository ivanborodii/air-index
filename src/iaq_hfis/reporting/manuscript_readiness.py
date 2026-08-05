"""``manuscript_readiness.json`` / ``.md``: standalone, prominent artifacts
(spec section 15's required file list) that surface
``summary["readiness"]["manuscript_readiness"]`` -- and its sibling
``artifact_readiness`` for context -- without requiring a reader to dig
through the full ``run_summary.json``. Written verbatim from
:func:`iaq_hfis.provenance.assess_readiness`'s output -- never
independently recomputed here.
"""

from __future__ import annotations

import json

MANUSCRIPT_READINESS_JSON = "manuscript_readiness.json"
MANUSCRIPT_READINESS_MD = "manuscript_readiness.md"


def build_manuscript_readiness_json(readiness: dict) -> str:
    return json.dumps(
        {
            "artifact_readiness": readiness.get("artifact_readiness"),
            "manuscript_readiness": readiness.get("manuscript_readiness"),
            "scientific_blockers": readiness.get("scientific_blockers"),
            "unsupported_claims": readiness.get("unsupported_claims"),
        },
        indent=2,
    )


def build_manuscript_readiness_markdown(readiness: dict) -> str:
    ar = readiness.get("artifact_readiness") or {}
    mr = readiness.get("manuscript_readiness") or {}
    lines: list[str] = [
        "# Manuscript Readiness",
        "",
        "> Software-generated from `iaq_hfis.provenance.assess_readiness` -- not hand-maintained.",
        "",
        "**`artifact_readiness`** means only that the computational artifacts (pipeline run, evaluation, "
        "`iaq_hfis validate-artifacts`, the test suite) are internally complete and consistent. It says nothing "
        "about whether this run's result is eligible to be described as the manuscript's complete proposed "
        "method -- that is `manuscript_readiness`, below, which may be `true` only when the temperature profile "
        "is directly DBN-supported, the run was executed in `mode=publication`, and a full A/V/M/I "
        "(`completeness_status=OK`) result actually exists.",
        "",
        f"## Artifact readiness: {'READY' if ar.get('ready') else 'NOT READY'}",
        "",
    ]
    for issue in ar.get("blocking_issues") or []:
        lines.append(f"- Blocking: {issue}")
    for warning in ar.get("warnings") or []:
        lines.append(f"- Warning: {warning}")
    if not (ar.get("blocking_issues") or ar.get("warnings")):
        lines.append("- No issues.")
    lines += ["", f"## Manuscript readiness: {'READY' if mr.get('ready') else 'NOT READY'}", ""]
    for issue in mr.get("blocking_issues") or []:
        lines.append(f"- Blocking: {issue}")
    for warning in mr.get("warnings") or []:
        lines.append(f"- Warning: {warning}")
    if not (mr.get("blocking_issues") or mr.get("warnings")):
        lines.append("- No issues.")
    lines += ["", "## Unsupported claims", ""]
    unsupported = readiness.get("unsupported_claims") or []
    if unsupported:
        for claim in unsupported:
            lines.append(f"- {claim}")
    else:
        lines.append("None -- every manuscript claim this run could make is currently supported by its own artifacts.")
    lines += ["", "## Scientific blockers", ""]
    blockers = readiness.get("scientific_blockers") or []
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)
