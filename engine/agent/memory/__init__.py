"""DataBox Agent Memory Layer.

Three-tier memory architecture:
  ShortTermMemory  — LangGraph thread state (checkpointer-backed)
  SessionMemory    — within-session runs, artifacts, SQL context
  LongTermMemory   — cross-session user prefs, project rules, schema aliases, trajectories
"""
