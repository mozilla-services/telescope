import aiohttp


async def run(url):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                status = response.status == 200
                return status, await response.json()
        except aiohttp.client_exceptions.ClientError as e:
            return False, str(e)
