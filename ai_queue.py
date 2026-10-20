import asyncio
from contextlib import asynccontextmanager


class AIQueueFullError(Exception):
    pass


class AIRequestQueue:

    def __init__(
        self,
        concurrency: int = 1,
        max_waiting: int = 10,
    ):
        # Only this many AI jobs can run simultaneously.
        self._semaphore = asyncio.Semaphore(
            concurrency
        )

        self._state_lock = asyncio.Lock()

        self._waiting = 0
        self._processing = 0

        self.max_waiting = max_waiting

    @asynccontextmanager
    async def slot(self):

        waiting_registered = False
        acquired = False

        # ---------------------------------
        # Register this request in queue
        # ---------------------------------

        async with self._state_lock:

            if self._waiting >= self.max_waiting:

                raise AIQueueFullError(
                    "Voice search queue is full"
                )

            self._waiting += 1

            waiting_registered = True

        try:

            # ---------------------------------
            # Wait until AI becomes available
            # ---------------------------------

            await self._semaphore.acquire()

            acquired = True

            async with self._state_lock:

                self._waiting -= 1

                waiting_registered = False

                self._processing += 1

            # AI processing happens here.
            yield

        finally:

            # ---------------------------------
            # Request cancelled while waiting
            # ---------------------------------

            if waiting_registered:

                async with self._state_lock:

                    self._waiting = max(
                        0,
                        self._waiting - 1
                    )

            # ---------------------------------
            # Release AI for next customer
            # ---------------------------------

            if acquired:

                async with self._state_lock:

                    self._processing = max(
                        0,
                        self._processing - 1
                    )

                self._semaphore.release()

    async def status(self):

        async with self._state_lock:

            return {
                "processing":
                    self._processing,

                "waiting":
                    self._waiting,

                "max_waiting":
                    self.max_waiting,
            }


# Current PC:
# ONLY ONE AI inference at a time.
ai_queue = AIRequestQueue(
    concurrency=1,
    max_waiting=10,
)