# Error Boundary Contract

## Goal

No untrusted exception text may cross into an HTTP/SSE response, browser
projection, Responses Item, Tool Observation, persistence record, or log. This
includes provider, driver, tunnel, vault, user-input, and chained exception
text.

## Authoritative implementation

`engine/app/safe_errors.py` is the single public-error catalog. Boundary code
accepts `FixedErrorCode` members and renders them through
`fixed_error_detail()` or `fixed_error_message()`. Unknown values fall back to
`INTERNAL_ERROR`; arbitrary caller text never becomes a public code or message.

`log_unexpected_exception()` records only a finite `SafeLogOperation`, the
exception type, and an opaque diagnostic fingerprint. It never logs
`str(exc)`, exception arguments, causes, tracebacks, credentials, SQL results,
or provider response bodies.

## Rules

- API handlers may propagate deliberately typed, static domain errors. Catch-all
  paths must map to a `FixedErrorCode` before creating a response.
- Runtime events, Run Items, Tool Observations, Artifact metadata, datasource
  health, and persisted failure records contain cataloged codes and bounded
  public summaries only.
- Provider and database failures are converted before they enter the durable
  Agent transcript. Recovery reads the already-sanitized persisted record; it
  does not reconstruct a message from an exception.
- Frontend projections render public codes/messages and keep transport or stack
  diagnostics out of Zustand state.
- Do not add an error facade, alias map, or compatibility wrapper around
  `safe_errors.py`; callers import the authoritative helpers directly.

## Verification

Every new trust boundary needs a sentinel regression proving the sentinel is
absent from logs, HTTP/SSE responses, Run Items, Tool Observations, and database
records. Architecture tests must also reject raw exception formatting and
traceback logging in boundary modules.
