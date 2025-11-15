import asyncio
import os
import random

from ironswarm.journey.http import http_session
from ironswarm.scenario import Journey, Scenario
from ironswarm.volumemodel import VolumeModel
from ironswarm.datapools import FileDatapool, RecyclableDatapool

base_url = os.getenv("TEST_SCENARIO_BASE_URL", "http://127.0.0.1:8080").rstrip("/")


def _record_response(context, method: str, url: str, resp) -> None:
    context.log(f"{method} {url} - Status: {resp.status}")


@http_session()
async def get_users(context):
    """Fetch users from the API"""
    url = f"{base_url}/api/users"

    async with context.session.get(url, headers={"Accept": "application/json"}) as resp:
        _record_response(context, "GET", url, resp)
        data = await resp.json()
        context.vars["user_id"] = data[0]["id"]


@http_session()
async def create_post(context):
    """Create a new post"""
    url = f"{base_url}/api/posts"

    async with context.session.post(
        url,
        headers={"Content-Type": "application/json", "Authorization": "Bearer token123"},
        data='{"title": "Test Post", "content": "This is a test"}'
    ) as resp:
        _record_response(context, "POST", url, resp)


@http_session()
async def search_items(context):
    """Search for items"""
    url = f"{base_url}/api/search"

    async with context.session.get(
        url,
        params={"q": "test", "limit": "10"},
        headers={"Accept": "application/json"}
    ) as resp:
        _record_response(context, "GET", url, resp)


scenario = Scenario(
    delay=5,
    journeys=[
        Journey(
            spec=get_users,
            datapool=RecyclableDatapool(['user1', 'user2', 'user3']),
            volume_model=VolumeModel(target=20, duration=120)
        ),
        Journey(
            spec=create_post,
            volume_model=VolumeModel(target=15, duration=90)
        ),
        Journey(
            spec=search_items,
            volume_model=VolumeModel(target=30, duration=60)
        ),
    ]
)
