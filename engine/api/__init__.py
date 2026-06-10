from fastapi import APIRouter
from engine.api.projects import router as projects_router
from engine.api.datasources import router as datasources_router
from engine.api.query import router as query_router
from engine.api.agent import router as agent_router
from engine.api.backup import router as backup_router
from engine.api.table_design import router as table_design_router
from engine.api.semantic import router as semantic_router
from engine.api.agent_eval import router as agent_eval_router

router = APIRouter(prefix="/api/v1")

router.include_router(projects_router)
router.include_router(datasources_router)
router.include_router(query_router)
router.include_router(agent_router)
router.include_router(backup_router)
router.include_router(table_design_router)
router.include_router(semantic_router)
router.include_router(agent_eval_router)

__all__ = ["router"]
