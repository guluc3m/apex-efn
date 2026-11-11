"""API routes: every §8 router is registered here (one module per owner, AGENTS.md section 2).

Nobody edits this file again to add a route: each router module belongs to its owner lane.
Routes that are not implemented yet answer 501 problem+json.
"""

from fastapi import APIRouter

from apex.api.approvals import router as approvals_router
from apex.api.audit import router as audit_router
from apex.api.config import router as config_router
from apex.api.dashboard import router as dashboard_router
from apex.api.decisions import router as decisions_router
from apex.api.gate import router as gate_router
from apex.api.keys import router as keys_router
from apex.api.missions import router as missions_router
from apex.api.negotiations import router as negotiations_router
from apex.api.onboarding import router as onboarding_router
from apex.api.sellers import router as sellers_router
from apex.api.signing import router as signing_router
from apex.api.sourcing import router as sourcing_router
from apex.api.webhooks import router as webhooks_router

router = APIRouter()

router.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
router.include_router(sourcing_router, prefix="/sourcing-requests", tags=["sourcing"])
router.include_router(missions_router, prefix="/missions", tags=["missions"])
router.include_router(sellers_router, prefix="/sellers", tags=["sellers"])
router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
router.include_router(gate_router, prefix="/gate", tags=["gate"])
router.include_router(config_router, prefix="/config", tags=["config"])
router.include_router(negotiations_router, prefix="/negotiations", tags=["negotiations"])
router.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
router.include_router(signing_router, prefix="/signing-sessions", tags=["signing"])
router.include_router(decisions_router, prefix="/decisions", tags=["decisions"])
router.include_router(keys_router, prefix="/keys", tags=["keys"])
router.include_router(audit_router, prefix="/audit", tags=["audit"])
router.include_router(approvals_router, prefix="/approvals", tags=["approvals"])
