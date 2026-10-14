# Historical ability levels — parser version 12

Abilities now retain explicitly labelled historical learned levels separately from the current level. A source value such as `8 — now 6` contributes level 8 under its printed year label; it never replaces current level 6. Historical section citations are retained as reported URLs without claiming independent verification. Explicit target labels and alternate recorded names are also preserved.

The immutable cache-only batch `raw/2026-10-13-225120-105226-archive-historical-levels-v12/` contains 488 ability records with historical level observations and historical citation URLs. It reviews only cached ability pages carrying those labels, rather than replaying every unrelated page. The extraction made zero network requests and did not modify previous delivered batches.

For Vexing Strike II, the archive records current level 6 and older level 8 under 2007 and 2007–2008 labels, with the older source URLs preserved separately. This is evidence of different reported rulesets, not a choice of which emulator era to implement.

All 106 tests pass. The regression case confirms that a historical level does not overwrite the current value and that internal navigation links are excluded from historical citations. The live collector was checkpointed and restarted with version 12.
