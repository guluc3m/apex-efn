"""API routes."""

from fastapi import APIRouter

from apex.api.dashboard import router as dashboard_router
from apex.api.gate import router as gate_router
from apex.api.missions import router as missions_router
from apex.api.sellers import router as sellers_router
from apex.api.signing import router as signing_router

router = APIRouter()

router.include_router(missions_router, prefix="/missions", tags=["missions"])
router.include_router(sellers_router, prefix="/sellers", tags=["sellers"])
router.include_router(signing_router, prefix="/signing-sessions", tags=["signing"])
router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
router.include_router(gate_router, prefix="/gate", tags=["gate"])
