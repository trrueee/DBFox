"""Single source of truth for bounded SQL result transport."""

MAX_ROWS = 1000
MAX_COLUMNS = 100
MAX_CELL_CHARS = 5000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
QUERY_TIMEOUT_MS = 30_000
