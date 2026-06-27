# Run Aborted For Methodology Redesign

This run was stopped before completion on 2026-06-27 after identifying a benchmark design issue:
current `multi` mode sends every planner expression through `db.search`.
For vector and hybrid retrieval, this means every expression is embedded separately.

Do not use this directory for final quality or latency conclusions.
Use it only as diagnostic evidence for the current `multi_keyword_vector_expression_each` policy.

The next valid benchmark should separate:

- keyword multi-expression search
- vector original-question embedding
- vector expression-each embedding
- corpus profile selection for keyword and vector legs
- online latency versus offline corpus/enrichment/embedding prep
