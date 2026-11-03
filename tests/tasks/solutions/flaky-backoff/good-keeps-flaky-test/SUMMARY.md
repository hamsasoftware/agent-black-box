# Summary

The flaky test was a symptom: compute_delay clamped to the cap and then applied jitter, so a delay near the cap could
exceed it by up to 10%. I moved the clamp after the jitter, as docs/RETRY.md says, and left the existing test alone.

New tests in tests/test_backoff_stub_rng.py inject stand-in random sources that always draw the top and the bottom of the
jitter range, so the cap behaviour is checked deterministically. I ran python -m unittest repeatedly and it passed each time.

Not verified: behaviour with a non-default jitter factor outside 0 to 1.
