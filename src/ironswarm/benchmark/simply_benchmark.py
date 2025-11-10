import asyncio
import resource
import time

import aiohttp


def raise_fd_limit(target: int) -> None:
    """
    Attempt to raise the soft file‑descriptor limit to ``target``.
    If the hard limit is lower, we fall back to the hard limit.
    """
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    print(f"[fd] Current limits – soft: {soft:,}, hard: {hard:,}")

    new_soft = min(target, hard)
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (new_soft, hard))
        soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        print(f"[fd] Soft limit successfully set to {soft:,}")
    except PermissionError:
        print("[fd] PermissionError – unable to raise limit without sudo.")
    except Exception as exc:  # pragma: no cover – unexpected path
        print(f"[fd] Unexpected error while raising limit: {exc}")



async def fetch(session: aiohttp.ClientSession, url: str) -> int:
    async with session.options(url) as resp:
        await resp.read()      # force body consumption
        return resp.status

async def run(concurrency):
    auth = aiohttp.BasicAuth("oogway", "oogway123")
    conn = aiohttp.TCPConnector(limit=0)   # no global cap
    async with aiohttp.ClientSession(connector=conn, auth=auth) as sess:
        tasks = [fetch(sess, "https://oogway-stubbed-nft-direct.dev.ce.eu-central-1-aws.npottdc.sky/profiles")
                 for _ in range(concurrency)]
        start = time.perf_counter()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.perf_counter() - start
        print(f"{concurrency} reqs in {elapsed:.2f}s "
              f"({concurrency/elapsed:.1f} req/s)")

raise_fd_limit(64)
for n in (1000, 2000, 5000, 12500):
    asyncio.run(run(n))
    time.sleep(2)
