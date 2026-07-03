from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from logging import Logger
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


async def gather_bounded(
    items: Iterable[T],
    worker: Callable[[T], Awaitable[R]],
    *,
    concurrency: int,
) -> list[R]:
    sem = asyncio.Semaphore(max(concurrency, 1))

    async def bounded(item: T) -> R:
        async with sem:
            return await worker(item)

    tasks = [asyncio.create_task(bounded(item)) for item in items]
    try:
        return await asyncio.gather(*tasks)
    except Exception:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def iter_completed_bounded(
    items: Iterable[T],
    worker: Callable[[T], Awaitable[R]],
    *,
    concurrency: int,
):
    sem = asyncio.Semaphore(max(concurrency, 1))

    async def bounded(item: T) -> R:
        async with sem:
            return await worker(item)

    tasks = [asyncio.create_task(bounded(item)) for item in items]
    try:
        for task in asyncio.as_completed(tasks):
            yield await task
    except Exception:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def iter_completed_tasks(
    tasks: list[asyncio.Task[R]],
    *,
    heartbeat_seconds: float = 0,
    logger: Logger | None = None,
    heartbeat_message: Callable[[int, int], str] | None = None,
):
    stop_heartbeat = asyncio.Event()

    async def log_heartbeat() -> None:
        if (
            heartbeat_seconds <= 0
            or logger is None
            or heartbeat_message is None
        ):
            return

        total = len(tasks)
        while not stop_heartbeat.is_set():
            try:
                await asyncio.wait_for(
                    stop_heartbeat.wait(),
                    timeout=heartbeat_seconds,
                )
            except TimeoutError:
                done = sum(1 for task in tasks if task.done())
                logger.info(heartbeat_message(done, total))

    heartbeat_task = asyncio.create_task(log_heartbeat())

    try:
        for task in asyncio.as_completed(tasks):
            yield await task
    except Exception:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        stop_heartbeat.set()
        await asyncio.gather(heartbeat_task, return_exceptions=True)


async def iter_completed_task_batches(
    tasks: list[asyncio.Task[R]],
    *,
    batch_size: int,
    heartbeat_seconds: float = 0,
    logger: Logger | None = None,
    heartbeat_message: Callable[[int, int], str] | None = None,
):
    batch: list[R] = []

    async for result in iter_completed_tasks(
        tasks,
        heartbeat_seconds=heartbeat_seconds,
        logger=logger,
        heartbeat_message=heartbeat_message,
    ):
        batch.append(result)
        if len(batch) >= batch_size:
            yield batch
            batch = []

    if batch:
        yield batch
