from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    collector = request.app.state.rate_limit_metrics
    return Response(
        content=collector.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
