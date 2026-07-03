from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 5
    retryable_statuses: set[int] = field(
        default_factory=lambda: {408, 429, 500, 502, 503, 504}
    )
    retry_non_status_http_errors: bool = True
    retry_value_errors: bool = False
    min_retry_after: float = 0.5
    max_delay: float = 30.0

    def delay(
        self,
        attempt: int,
        response: httpx.Response | None = None,
    ) -> float:
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return max(float(retry_after), self.min_retry_after)
                except ValueError:
                    pass

        return min(2**attempt, self.max_delay) + random.uniform(0.1, 0.5)

    def is_retryable(self, exc: BaseException) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in self.retryable_statuses

        return (
            self.retry_non_status_http_errors
            and isinstance(
                exc,
                (TimeoutError, httpx.TimeoutException, httpx.TransportError),
            )
        ) or (self.retry_value_errors and isinstance(exc, ValueError))


async def request_with_retries(
    request: Callable[[], Awaitable[httpx.Response]],
    policy: RetryPolicy,
) -> httpx.Response:
    response: httpx.Response | None = None

    for attempt in range(policy.max_retries):
        try:
            response = await request()

            if response.status_code in policy.retryable_statuses:
                raise httpx.HTTPStatusError(
                    f"Retryable HTTP {response.status_code}: {response.url}",
                    request=response.request,
                    response=response,
                )

            response.raise_for_status()
            return response

        except (TimeoutError, httpx.HTTPError, ValueError) as exc:
            if attempt == policy.max_retries - 1 or not policy.is_retryable(
                exc
            ):
                raise

            await asyncio.sleep(policy.delay(attempt, response))

    raise RuntimeError("Unreachable retry state")
