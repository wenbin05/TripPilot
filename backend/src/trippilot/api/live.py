"""Bounded live planning route, with no silent mock fallback."""

import asyncio

from fastapi import APIRouter

from trippilot.providers.geoapify import GeoapifyProvider, load_geoapify_key
from trippilot.services.live_planner import LiveDraft, LocalAllowance, build_live_draft

from .schemas import TripPlanRequest

router = APIRouter()
allowance = LocalAllowance()


@router.post("/api/v1/itineraries/live-plan", response_model=LiveDraft)
async def live_plan(body: TripPlanRequest) -> LiveDraft:
    key = load_geoapify_key()
    if not key:
        return LiveDraft(
            status="unavailable",
            notice=(
                "Live planning is not configured. Add the Geoapify key on the backend."
            ),
        )
    if allowance.lock.locked():
        return LiveDraft(
            status="unavailable", notice="Live planner is busy. Try shortly."
        )
    async with allowance.lock:
        if not allowance.reserve():
            return LiveDraft(
                status="unavailable",
                notice=(
                    "The local daily live-planning allowance is used. Try tomorrow."
                ),
            )
        try:
            async with asyncio.timeout(8):
                # Provider resolves the authoritative city timezone before scheduling.
                return await build_live_draft(
                    body.to_domain("UTC"), GeoapifyProvider(key)
                )
        except Exception:
            # Never log or return provider bodies, headers, key, or exception repr.
            return LiveDraft(
                status="unavailable",
                notice=(
                    "Live data is unavailable. No mock places have been substituted. "
                    "Check the provider configuration or try again later."
                ),
            )
