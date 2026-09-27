"""Bounded live planning route, with no silent mock fallback."""

import asyncio

from fastapi import APIRouter
from pydantic import Field, StrictInt

from trippilot.domain.live_constraints import (
    MAX_ESTIMATE_MINOR,
    check_entered_estimates,
)
from trippilot.providers.geoapify import GeoapifyProvider, load_geoapify_key
from trippilot.services.live_inputs import BudgetEstimate, EnteredCosts, TravelTimes
from trippilot.services.live_planner import LiveDraft, LocalAllowance, build_live_draft

from .schemas import TripPlanRequest

router = APIRouter()
allowance = LocalAllowance()


class LivePlanRequest(TripPlanRequest):
    total_budget_minor: StrictInt = Field(gt=0, le=MAX_ESTIMATE_MINOR)
    travel_times: TravelTimes | None = None
    cost_estimates: EnteredCosts | None = None


@router.post("/api/v1/itineraries/live-plan", response_model=LiveDraft)
async def live_plan(body: LivePlanRequest) -> LiveDraft:
    estimate = None
    if body.cost_estimates is not None:
        check = check_entered_estimates(
            body.cost_estimates.values_in_order(), body.total_budget_minor
        )
        estimate = BudgetEstimate(
            currency=body.currency,
            budget_minor=body.total_budget_minor,
            categories=body.cost_estimates,
            status=check.status,
            known_subtotal_minor=check.known_subtotal_minor,
            estimated_total_minor=check.estimated_total_minor,
            remaining_minor=check.remaining_minor,
            missing_categories=check.missing_categories,
        )
        if check.status == "over_entered_estimate":
            return LiveDraft(
                status="budget_exceeded",
                budget_estimate=estimate,
                notice=(
                    "Your entered costs already exceed the all-in budget. Revise costs "
                    "or budget before generating a draft. No provider calls were made."
                ),
            )
    result = await _fetch_draft(body)
    return result.model_copy(update={"budget_estimate": estimate})


async def _fetch_draft(body: LivePlanRequest) -> LiveDraft:
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
                    body.to_domain("UTC"),
                    GeoapifyProvider(key),
                    travel_times=body.travel_times,
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
