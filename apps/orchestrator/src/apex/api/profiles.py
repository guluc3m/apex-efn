"""Ranking profiles (issue #306).

There is no persisted ``UserProfilePreference`` store yet, and weights are business values that must not be
invented here (AGENTS.md rule 0.6), so the honest answer is an empty list.
"""

from fastapi import APIRouter

from apex.contracts.generated.models import ProfileList

router = APIRouter()


@router.get("", response_model=ProfileList, tags=["config"])
async def list_profiles() -> ProfileList:
    return ProfileList(items=[])
