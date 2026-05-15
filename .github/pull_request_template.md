## Summary

<!-- One or two sentences on what this PR changes and why. -->

## Related

<!-- Link any related issue: closes #N / refs #N. -->

## Test plan

<!--
- [ ] `pytest` passes locally (mention test count if you added new ones)
- [ ] `ruff check .` clean
- [ ] If you touched hook scripts: ran a session end-to-end on a real
      Claude Code / Codex install and confirmed events.jsonl looks right
- [ ] If you touched the redactor: secret patterns still mask cleanly
-->

## Design compatibility

<!--
Tick what applies. Anything unticked is fine — call it out so it can
be discussed before merge.
-->

- [ ] Issue-agnostic (doesn't classify rot vs hallucination etc.)
- [ ] User-driven (no proactive alerts / background daemon work)
- [ ] Observation-only (no agent intervention, hooks still exit 0)
- [ ] Writes only to the plugin data dir
- [ ] Engine-agnostic at the core
