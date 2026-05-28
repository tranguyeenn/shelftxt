from fastapi import APIRouter

router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {
        "status": "healthy",
        "service": "ShelfTxt",
    }