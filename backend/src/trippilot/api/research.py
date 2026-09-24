"""Strict web boundary consuming the same MCP contract as external hosts."""

import asyncio
import json

from fastapi import APIRouter, HTTPException
from mcp import Client

from trippilot.research_mcp import create_research_server
from trippilot.services.research_schemas import ResearchRequest, ResearchResponse

router = APIRouter(prefix="/api/v1/research", tags=["research"])


@router.post("", response_model=ResearchResponse)
async def research(request: ResearchRequest) -> ResearchResponse:
    try:
        async with asyncio.timeout(9), Client(create_research_server()) as client:
            result = await client.call_tool(
                "research_destination", {"request": request.model_dump(mode="json")}
            )
            return ResearchResponse.model_validate_json(
                json.dumps(result.structured_content)
            )
    except Exception:
        raise HTTPException(503, "Research is temporarily unavailable") from None
