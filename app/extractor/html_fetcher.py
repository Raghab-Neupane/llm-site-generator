import httpx


async def fetch_html(url: str):

    async with httpx.AsyncClient() as client:

        response = await client.get(url)

        return response.text