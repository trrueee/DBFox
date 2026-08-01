"""Conversation HTTP protocol assembled from command, query, and stream routes."""

from fastapi import APIRouter

from engine.api.conversation_commands import router as commands_router
from engine.api.conversation_queries import router as queries_router
from engine.api.conversation_stream import router as stream_router


router = APIRouter()
router.include_router(queries_router)
router.include_router(commands_router)
router.include_router(stream_router)
