import httpx
from collectors.app_store import resolve_app_store_id

async def test_resolver_unresolved_graceful():
    def handler(request):
        return httpx.Response(200, json={"results":[]})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await resolve_app_store_id(client, "Unknown Wallet XYZ", None)
        assert res["resolved"] == False
