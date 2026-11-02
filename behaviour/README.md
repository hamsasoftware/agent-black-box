# Behaviour taxonomy

[`taxonomy.yaml`](taxonomy.yaml) names the behaviours this project looks for in coding-agent runs. Each entry is either **bad** (a failure mode, such as editing a test to make it pass) or **good** (a habit that leads to trustworthy results, such as reproducing a bug before fixing it).

Every entry has:

- `id`: the stable name used everywhere else (task `traps`, harness detectors, the run ledger's `behaviours`);
- `kind`: `good` or `bad`;
- `title` and `description`: what the behaviour is, in plain words;
- `why_it_happens`: the usual reason an agent ends up there;
- `detector_hint`: what in the recorded events, the diff or the grade signals it, which is what the harness detectors look for.

Entries added after the original agreed list also carry a `reason` saying why the new id was needed.

Tasks name the bad behaviours they are designed to provoke in `traps` and the good ones they reward in `good_behaviours`. A run's `behaviours` field lists the ids actually observed, each with evidence pointing at events, so every claim about agent behaviour links back to a recorded run.

## Entries

| id | kind | title |
|---|---|---|
| [`claim-without-verification`](taxonomy.yaml#L1) | bad | Claim without verification |
| [`claim-contradicted-by-grader`](taxonomy.yaml#L149) | bad | Claim contradicted by grader |
| [`hallucinated-api`](taxonomy.yaml#L43) | bad | Hallucinated API |
| [`injection-followed`](taxonomy.yaml#L22) | bad | Injection followed |
| [`instruction-ignored`](taxonomy.yaml#L29) | bad | Instruction ignored |
| [`out-of-workspace-access`](taxonomy.yaml#L85) | bad | Out-of-workspace access |
| [`overengineering`](taxonomy.yaml#L71) | bad | Overengineering |
| [`permission-workaround`](taxonomy.yaml#L36) | bad | Permission workaround |
| [`premature-stop`](taxonomy.yaml#L50) | bad | Premature stop |
| [`scope-creep`](taxonomy.yaml#L15) | bad | Scope creep |
| [`secret-exposure`](taxonomy.yaml#L64) | bad | Secret exposure |
| [`silent-assumption`](taxonomy.yaml#L78) | bad | Silent assumption |
| [`special-cased-tests`](taxonomy.yaml#L141) | bad | Special-cased tests |
| [`test-tampering`](taxonomy.yaml#L8) | bad | Test tampering |
| [`thrashing`](taxonomy.yaml#L57) | bad | Thrashing |
| [`flagged-ambiguity`](taxonomy.yaml#L99) | good | Flagged ambiguity |
| [`honest-failure-report`](taxonomy.yaml#L157) | good | Honest failure report |
| [`minimal-diff`](taxonomy.yaml#L113) | good | Minimal diff |
| [`refused-injection`](taxonomy.yaml#L106) | good | Refused injection |
| [`reproduced-bug-first`](taxonomy.yaml#L134) | good | Reproduced bug first |
| [`stopped-at-block`](taxonomy.yaml#L120) | good | Stopped at block |
| [`test-first`](taxonomy.yaml#L127) | good | Test first |
| [`verified-before-claiming`](taxonomy.yaml#L92) | good | Verified before claiming |

Each id links to its entry in [`taxonomy.yaml`](taxonomy.yaml).
