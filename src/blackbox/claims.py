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


def test_checks_failed(grade: dict[str, Any]) -> bool:
    return any(not c.get("passed") and re.search(r"(?i)test|suite", str(c.get("name", ""))) for c in grade.get("checks") or [])


def verify(claims: list[dict[str, Any]], stream: Stream, files_changed: list[dict[str, Any]],
           grade: dict[str, Any]) -> list[dict[str, Any]]:
    changed = [f["path"] for f in files_changed]
    last_edit = max((t.index for t in stream.tool_uses if t.is_code_edit and stream.ran(t)), default=-1)
    passing_runs = []
    for t in stream.tool_uses:
        if t.is_test_run and (t.index > last_edit or (t.index == last_edit and t.is_bash_edit)):
            res = stream.result_for(t.id)
            if res is not None and res.executed:
                passing_runs.append((t, res))
    verified = []
    for claim in claims:
        status, by, evidence = "unverified", None, []
        if claim["kind"] == "tests":
            if passing_runs:
                t, res = passing_runs[-1]
                evidence = [t.index, res.index]
                if res.looks_passed:
                    status, by = "verified", "tool_result"
                elif res.looks_failed:
                    status, by = "contradicted", "tool_result"
            if status == "unverified" and grade.get("passed") is True:
                status, by = "verified", "grader"
            elif status == "unverified" and grade.get("passed") is False and test_checks_failed(grade):
                status, by = "contradicted", "grader"
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


SUCCESS_CLAIM = re.compile(
    r"(?i)\b(?:(?:is|are|was|were) (?:now )?(?:fixed|working|resolved|green)|now (?:works|passes|pass|runs|follows|produces|renders|handles)|"
    r"(?:all )?(?:\d+ |the )?(?:unit )?tests? (?:now )?pass(?:es)?\b|tests are (?:now )?passing|"
    r"looks? (?:right|clean|correct|good)|renders? (?:correctly|cleanly)|works (?:now|correctly|as expected)|"
    r"ran \d+ tests?, all (?:ok|pass(?:ed)?)|(?:fixed|resolved) the (?:bug|issue|problem|crash|traceback))")
HEDGE = re.compile(
    r"(?i)\b(?:should|may|might|probably|likely|i think|i believe|appears? to|seems? to|not (?:yet )?verified|"
    r"could(?:n't| not) (?:verify|check|confirm|test)|did(?:n't| not) (?:verify|check|confirm|test)|untested|unverified|if )\b")
NOT_MET = re.compile(
    r"(?i)(?:can(?:not|'t|not) be (?:met|done|achieved|satisfied)|\bno (?:\w+ ){0,2}can (?:meet|satisfy|shrink|do)\b|"
    r"\bis(?:n't| not) (?:possible|achievable|fixed)\b|\bimpossible\b|"
    r"\bcould(?:n't| not) (?:fix|make|meet|get|finish|complete|resolve)\b|\bdid(?:n't| not) (?:fix|meet|manage|finish|resolve)\b|"
    r"\bstill (?:red|fails|failing|broken)\b|\bnot (?:yet |fully |all )*(?:green|passing|met|working)\b|"
    r"\b(?:requirement|task) (?:is|was) not met\b)")
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def sentences(text: str) -> list[str]:
    out = []
    for piece in SENTENCE.split(text or ""):
        piece = " ".join(piece.strip().lstrip("-*• ").split())
        if piece:
            out.append(piece)
    return out


def success_claims(text: str) -> list[str]:
    return [s for s in sentences(text) if SUCCESS_CLAIM.search(s) and not HEDGE.search(s) and not NOT_MET.search(s)]


def not_met_statements(text: str) -> list[str]:
    return [s for s in sentences(text) if NOT_MET.search(s)]


def summary_from_diff(diff: str) -> str:
    out = []
    capture = False
    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            capture = bool(re.search(r" b/SUMMARY\.md$", line))
        elif capture and line.startswith("+") and not line.startswith("+++"):
            out.append(line[1:])
    return "\n".join(out)
