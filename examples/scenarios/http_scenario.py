import asyncio
import os
import random

from ironswarm.journey.http import http_session
from ironswarm.scenario import Journey, Scenario
from ironswarm.volumemodel import VolumeModel

SCENARIO_DURATION = 60 * 10

scenario = Scenario(
    journeys=[
        Journey("scenarios.http_scenario:home", None, VolumeModel(target=10, duration=SCENARIO_DURATION)),
        Journey("scenarios.http_scenario:health", None, VolumeModel(target=10, duration=SCENARIO_DURATION)),
        # Journey("http_scenario:list_items", None, VolumeModel(target=4, duration=SCENARIO_DURATION)),
        # Journey("http_scenario:slow_items", None, VolumeModel(target=1, duration=SCENARIO_DURATION)),
        # Journey("http_scenario:post_echo", None, VolumeModel(target=3, duration=SCENARIO_DURATION)),
        # Journey("http_scenario:error_variant", None, VolumeModel(target=2, duration=SCENARIO_DURATION)),
        # Journey("http_scenario:fallback", None, VolumeModel(target=2, duration=SCENARIO_DURATION)),
    ],
    delay=2,
)


base_url = os.getenv("IRONSWARM_DEMO_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
ERROR_CODES = [404, 429, 502, 503]


def _record_response(context, method: str, url: str, resp) -> None:
    context.log(f"{method} {url} - Status: {resp.status}")
    context.log(f"{asyncio.get_event_loop().time()},{resp.elapsed}")


@http_session()
async def home(context):
    url = f"{base_url}/"
    async with context.session.get(url) as resp:
        _record_response(context, "GET", url, resp)


@http_session()
async def health(context):
    url = f"{base_url}/health"
    async with context.session.get(url) as resp:
        _record_response(context, "GET", url, resp)


@http_session()
async def list_items(context):
    url = f"{base_url}/api/items"
    async with context.session.get(url) as resp:
        _record_response(context, "GET", url, resp)


@http_session()
async def slow_items(context):
    url = f"{base_url}/api/items/slow"
    async with context.session.get(url) as resp:
        _record_response(context, "GET", url, resp)


@http_session()
async def post_echo(context):
    url = f"{base_url}/api/echo"
    payload = {"message": "ironswarm-demo", "id": random.randint(1, 10_000)}
    async with context.session.post(url, json=payload) as resp:
        _record_response(context, "POST", url, resp)


@http_session()
async def error_variant(context):
    status_code = random.choice(ERROR_CODES)
    url = f"{base_url}/error/{status_code}"
    async with context.session.get(url) as resp:
        _record_response(context, "GET", url, resp)


@http_session()
async def fallback(context):
    url = f"{base_url}/not-real-{random.randint(1, 9999)}"
    async with context.session.get(url) as resp:
        _record_response(context, "GET", url, resp)
