# DBFox Visualization DLC

`dbfox.visualization` owns visual-analysis semantics, the `visualization_create`
Tool, the durable `dbfox.visualization.document` Artifact, and its inline and
workspace Views. Current documents use schema v2. It consumes the generic
`dbfox.dataframe.v1` Representation;
it does not import or require `dbfox.data`.

The stored document uses a bounded Vega-Lite or restricted Vega spec with the
named dataset `dbfox_source`. External URLs, embedded spec data, arbitrary
JavaScript, React code, and custom loaders are rejected. Small model-knowledge
or user-provided inputs are materialized atomically as a separate supporting
`dbfox.visualization.authored_dataset` Artifact. That Artifact exposes the same
DataFrame Representation, retains explicit provenance, and is the sole source
of the derived Visualization document. Inline rows remain readable only in
historical schema-v1 documents.
