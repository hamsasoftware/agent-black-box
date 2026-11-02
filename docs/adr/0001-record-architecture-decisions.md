# 1. Record architecture decisions

Date: 2026-11-02

Status: Accepted

## Context

Several contributors, people and agents, build this repository in parallel, each owning one module. Decisions that cross module boundaries (what the subject model is, how runs are capped, how data is protected) are easy to lose in pull request threads. Readers checking a finding later need to know why the setup looks the way it does, and when that was decided.

## Decision

Record each architecturally significant decision as an Architecture Decision Record in `docs/adr/`, in the short format described by Michael Nygard: title, date, status, context, decision, consequences.

- Files are named `NNNN-short-title.md` with a four-digit sequence number.
- An accepted ADR is not edited in substance. A changed decision gets a new ADR that marks the old one as superseded.
- An ADR is added in the same pull request as the change it explains.

## Consequences

- The reasoning behind the setup is versioned next to the code and the run data.
- Writing an ADR adds a small cost to significant changes.
- Contradictions between ADRs and the code are visible in review.
