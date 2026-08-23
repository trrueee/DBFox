from fastapi import APIRouter
from engine.api.projects import router as projects_router
from engine.api.datasources import router as datasources_router
from engine.api.query import router as query_router
from engine.api.agent import router as agent_router
from engine.api.backup import router as backup_router
from engine.api.test_data import router as test_data_router
from engine.api.conversations import router as conversations_router
from engine.api.diagnostics import router as diagnostics_router
from engine.api.credentials import router as credentials_router
from engine.api.dlc_operations import router as dlc_operations_router
from engine.api.dlc_credentials import router as dlc_credentials_router
from engine.api.dlc_activation import router as dlc_activation_router
from engine.api.dlc_lifecycle import router as dlc_lifecycle_router

router = APIRouter(prefix="/api/v1")

router.include_router(projects_router)
router.include_router(datasources_router)
router.include_router(query_router)
router.include_router(agent_router)
router.include_router(backup_router)
router.include_router(test_data_router)
router.include_router(conversations_router)
router.include_router(diagnostics_router)
router.include_router(credentials_router)
router.include_router(dlc_operations_router)
router.include_router(dlc_credentials_router)
router.include_router(dlc_activation_router)
router.include_router(dlc_lifecycle_router)


__all__ = ["router"]
