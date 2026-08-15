# Artifacts

This directory keeps checked-in Spider evaluation snapshots only.

The `spider_*.json` files are intentional benchmark/reference outputs and are
explicitly unignored in the root `.gitignore`. Runtime logs and ad hoc generated
artifacts should stay ignored and should not be committed here.

`spider_tiny_execute.json` is the reference snapshot for the tiny Spider subset.
The execute and no-execute variants produced byte-identical outputs for this
subset, so only one copy is tracked; the historical duplicate remains available
in Git history.
