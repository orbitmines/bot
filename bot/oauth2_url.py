import asyncio

from Client import oauth2_url

async def generate():
    print(await oauth2_url())

asyncio.run(generate())