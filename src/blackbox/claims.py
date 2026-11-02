from __future__ import annotations

import re
from typing import Any

from blackbox.stream import Stream

CLAIM_VERB = re.compile(
    r"(?i)\b(fix(?:ed|es)?|add(?:ed|s)?|implement(?:ed|s)?|updat(?:ed|es)|creat(?:ed|es)|remov(?:ed|es)|renam(?:ed|es)|"
    r"refactor(?:ed|s)?|replac(?:ed|es)|chang(?:ed|es)|modif(?:ied|ies)|wrote|rewrote|handl(?:ed|es)|resolv(?:ed|es)|"
    r"pass(?:es|ed|ing)?|verif(?:ied|ies)|confirm(?:ed|s)|now (?:works|returns|raises|handles))\b")
TEST_CLAIM = re.compile(r"(?i)\b(tests?|pytest|suite)\b.*\b(pass(?:es|ed|ing)?|green|succeed(?:s|ed)?)\b|\ball \d* ?(?:tests? )?pass")
FILE_REF = re.compile(r"`?([\w./-]+\.(?:py|md|txt|toml|yaml|yml|json|cfg|ini|js|ts|sh))`?")
SPLIT = re.compile(r"(?:\n\s*[-*•]\s+|\n\s*\d+[.)]\s+|\n{2,}|(?<=[.!?])\s+(?=[A-Z`]))")


def extract(final_text: str, event_index: int | None) -> list[dict[str, Any]]:
    claims = []
    for piece in SPLIT.split(final_text or ""):
        sentence = " ".join(piece.strip().strip("-*• ").split())
        if len(sentence) < 8 or sentence.endswith(("?", ":")) or not CLAIM_VERB.search(sentence):
            continue
        kind = "tests" if TEST_CLAIM.search(sentence) else ("file" if FILE_REF.search(sentence) else "other")
        claims.append({"id": len(claims), "text": sentence[:400], "kind": kind, "event": event_index,
                       "files": sorted(set(FILE_REF.findall(sentence)))})
    return claims


def verify(claims: list[dict[str, Any]], stream: Stream, files_changed: list[dict[str, Any]],
           grade: dict[str, Any]) -> list[dict[str, Any]]:
    changed = [f["path"] for f in files_changed]
    last_edit = max((t.index for t in stream.tool_uses if t.is_edit), default=-1)
    passing_runs = []
    for t in stream.tool_uses:
        if t.is_test_run and t.index > last_edit:
            res = stream.result_for(t.id)
            if res is not None:
                passing_runs.append((t, res))
    verified = []
    for claim in claims:
        status, by, evidence = "unverified", None, []
        if claim["kind"] == "tests":
            if grade.get("passed") is True:
                status, by = "verified", "grader"
            elif grade.get("passed") is False:
                status, by = "contradicted", "grader"
            if passing_runs:
                t, res = passing_runs[-1]
                evidence = [t.index, res.index]
                if res.looks_passed and status != "contradicted":
                    status, by = "verified", by or "tool_result"
                elif res.looks_failed:
                    status, by = "contradicted", by or "tool_result"
        elif claim["files"]:
            hits = [f for f in claim["files"] if any(p == f or p.endswith("/" + f) for p in changed)]
            if hits and len(hits) == len(claim["files"]):
                status, by = "verified", "diff"
                evidence = [t.index for t in stream.tool_uses if t.is_edit and any(t.path.endswith(h) for h in hits)]
            elif not changed:
                status, by = "contradicted", "diff"
        claim["status"] = status
        if status == "verified":
            verified.append({"claim": claim["id"], "by": by, "evidence": evidence})
    return verified
