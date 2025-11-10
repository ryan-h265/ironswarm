#!/usr/bin/env python3
"""
Benchmark: find the maximum number of simultaneous aiohttp requests that can
complete within a 5‑second timeout on the current machine.

Features
--------
* Raises the soft file‑descriptor limit (if possible).
* Uses a single aiohttp.ClientSession with an unrestricted TCPConnector.
* Performs a binary‑search style ramp‑up to locate the “break‑point”.
* Reports:
    - concurrency tried
    - success rate
    - average latency
    - overall wall‑clock time
* Handles KeyboardInterrupt cleanly.
"""

import asyncio
import resource
import sys
import time

import aiohttp

# ----------------------------------------------------------------------
# USER SETTINGS ---------------------------------------------------------
# ----------------------------------------------------------------------
TARGET_URL = "http://127.0.0.1:8000/"   # <-- change to your local endpoint
REQUEST_TIMEOUT = 5.0                     # seconds per request (hard timeout)
MAX_SEARCH_ITER = 20                      # how many binary‑search steps
INITIAL_CONCURRENCY = 100               # start point for the search
DESIRED_SOFT_FD_LIMIT = 65_536           # target soft limit for file descriptors
# ----------------------------------------------------------------------


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


async def fetch_one(session: aiohttp.ClientSession, url: str) -> tuple[bool, float]:
    """
    Perform a single GET request with a per‑request timeout.
    Returns a tuple ``(success, elapsed_seconds)``.
    """
    start = time.perf_counter()
    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with session.get(url, timeout=timeout) as resp:
            await resp.read()               # consume body so the connection closes cleanly
            success = resp.status == 200
    except (aiohttp.ClientError, asyncio.TimeoutError):
        success = False
    elapsed = time.perf_counter() - start
    return success, elapsed


async def run_batch(concurrency: int) -> tuple[int, float, float]:
    """
    Fire ``concurrency`` requests concurrently and wait for them all.
    Returns ``(successful_requests, avg_latency, wall_clock_time)``.
    """
    connector = aiohttp.TCPConnector(limit=0)   # no global cap
    timeout = aiohttp.ClientTimeout(total=None)  # we enforce our own per‑request timeout
    async with aiohttp.ClientSession(connector=connector,
                                      timeout=timeout) as session:

        # Build the task list
        tasks = [fetch_one(session, TARGET_URL) for _ in range(concurrency)]

        wall_start = time.perf_counter()
        results = await asyncio.gather(*tasks, return_exceptions=False)
        wall_elapsed = time.perf_counter() - wall_start

        successes = sum(1 for ok, _ in results if ok)
        avg_latency = sum(lat for _, lat in results) / len(results)

        return successes, avg_latency, wall_elapsed


def binary_search_max_concurrency() -> int:
    """
    Perform a binary‑search‑style ramp‑up to locate the highest concurrency
    that finishes *all* requests within ``REQUEST_TIMEOUT`` seconds.
    """
    low = 0
    high = INITIAL_CONCURRENCY * 2   # start with a generous upper bound
    best = 0

    for iteration in range(1, MAX_SEARCH_ITER + 1):
        mid = (low + high) // 2
        if mid == 0:
            break

        print(f"\n=== Iteration {iteration}: testing {mid:,} concurrent requests ===")
        successes, avg_lat, wall = asyncio.run(run_batch(mid))

        # Did *every* request finish within the timeout?
        all_ok = (successes == mid) and (wall <= REQUEST_TIMEOUT)

        print(f"[result] Successes: {successes:,}/{mid:,} "
              f" | avg latency: {avg_lat:.3f}s"
              f" | wall‑time: {wall:.3f}s"
              f" | {'PASS' if all_ok else 'FAIL'}")

        if all_ok:
            best = mid
            low = mid + 1          # try a bigger batch
        else:
            high = mid - 1         # shrink the batch

        # Early exit if the search window collapses
        if low > high:
            break

    return best


def main() -> None:
    print("=== aiohttp concurrency benchmark (5‑second deadline) ===")
    # raise_fd_limit(DESIRED_SOFT_FD_LIMIT)

    try:
        max_conc = binary_search_max_concurrency()
        print("\n=== FINAL RESULT ===")
        if max_conc:
            print(f"The highest concurrency that completed **all** requests "
                  f"within {REQUEST_TIMEOUT}s on this machine is ≈ {max_conc:,}.")
        else:
            print("No concurrency level satisfied the 5‑second deadline. "
                  "Try increasing the timeout or checking the endpoint.")
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
