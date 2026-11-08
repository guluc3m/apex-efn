"""API routes."""

from fastapi import APIRouter

from trato.api.missions import router as missions_router
from trato.api.sellers import router as sellers_router
from trato.api.signing import router as signing_router
from trato.api.dashboard import router as dashboard_router
from trato.api.gate import router as gate_router

router = APIRouter()

router.include_router(missions_router, prefix="/missions", tags=["missions"])
router.include_router(sellers_router, prefix="/sellers", tags=["sellers"])
router.include_router(signing_router, prefix="/signing-sessions", tags=["signing"])
router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
router.include_router(gate_router, prefix="/gate", tags=["gate"])
