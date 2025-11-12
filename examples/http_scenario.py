import asyncio

from ironswarm.journey.http import http_session
from ironswarm.journey.log import log_output
from ironswarm.scenario import Journey, Scenario
from ironswarm.volumemodel import VolumeModel

scenario = Scenario(
    journeys=[
        Journey("http_scenario:head", None, VolumeModel(target=1, duration=60)),
        Journey("http_scenario:get", None, VolumeModel(target=3, duration=60)),
    ],
    delay=2,
)


base_url = "https://example.com/"

@http_session()
@log_output
async def head(context):
    async with context.session.head(base_url) as resp:
        context.log(f"HEAD {base_url} - Status: {resp.status}")
        context.log(f"{asyncio.get_event_loop().time()},{resp.elapsed}")


@http_session()
@log_output
async def get(context):
    async with context.session.get(base_url) as resp:
        context.log(f"GET {base_url} - Status: {resp.status}")
        context.log(f"{asyncio.get_event_loop().time()},{resp.elapsed}")
