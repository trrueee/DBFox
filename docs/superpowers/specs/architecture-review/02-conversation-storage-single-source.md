# Conversation Storage Single Source Spec

Date: 2026-06-15
Priority: P0/P1
Area: Local-first persistence

## Corrected Judgment

This is a real consistency risk. The production Tauri path and the browser/dev fallback can persist conversation history to different SQLite databases with parallel schemas.

## Code Evidence

- `desktop/src/features/conversation/conversationRepository.ts:44-65` routes to Tauri commands when `__TAURI_INTERNALS__` exists, otherwise to engine HTTP APIs.
- `desktop/src-tauri/src/lib.rs:58-148` stores conversations in an app-data `dbfox.sqlite3` through `rusqlite`.
- `engine/api/conversations.py:23-77` stores the same logical records through FastAPI and SQLAlchemy `ChatConversation`.
- `engine/db.py:36-39` uses the engine metastore database path, currently `dbfox_local.db` in development.

## Problem

The app has two conversation storage authorities:

- Tauri production runtime: `dbfox.sqlite3`.
- Engine/browser fallback: `dbfox_local.db` table `chat_conversations`.

This creates different histories depending on entry point, duplicates schema evolution work in Rust and Python, and makes migration/backup semantics unclear.

## Goals

- Pick one conversation persistence authority.
- Make Tauri production and browser/dev show the same conversation history.
- Keep local-first behavior.
- Preserve existing conversation record shape during migration.
- Remove or quarantine the non-authoritative path.

## Non-Goals

- Do not redesign Agent runtime event persistence.
- Do not merge conversation history with long-term memory in this spec.
- Do not add cloud sync.

## Proposed Design

Use the Python engine API as the single source of truth:

- Keep `engine/api/conversations.py` as the canonical CRUD surface.
- Keep `ChatConversation` in the engine metastore as the canonical schema.
- Change `conversationRepository.ts` to use engine HTTP APIs in both browser and Tauri runtime.
- Remove Tauri conversation commands from production use, or leave them as a migration-only compatibility layer.

Migration path:

1. On startup, detect whether the old Tauri `dbfox.sqlite3` contains conversations.
2. If present, read records once through a migration command and upsert them through `/api/v1/conversations`.
3. Write a local migration marker after successful import.
4. Stop writing new conversations to the Tauri-side database.

If product direction later chooses Rust-side storage instead, then the inverse must happen: remove engine conversation APIs from app use and make browser/dev use the same Rust-backed abstraction. The key requirement is one authority, not two.

## Acceptance Criteria

- Tauri and browser/dev use one repository path for normal list/save/delete operations.
- Conversation history appears identical after switching entry points.
- Existing Tauri-side records are migrated once without duplicates.
- New conversations are written only to the canonical store.
- Deleting a conversation removes it from the canonical store and from any open tabs.

## Test Plan

- Unit test `conversationRepository` uses the canonical API regardless of Tauri runtime after migration.
- Backend API tests for list/save/delete conversation records.
- Migration test with a sample Tauri SQLite file and duplicate IDs.
- Manual verification in Tauri: ask a question, restart, verify history persists.
