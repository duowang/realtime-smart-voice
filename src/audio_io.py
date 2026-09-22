"""Small PortAudio helpers shared by wake detection and conversation playback."""

import asyncio
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


async def audio_operation[T](function: Callable[..., T], *args, **kwargs) -> T:
    """Run blocking device I/O without closing a device underneath its worker.

    Cancelling to_thread alone leaves the native read/write running. Wait for
    the current short audio operation to finish before propagating cancellation,
    so the owner's finally block can safely close the stream.
    """
    worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    return await complete_task(worker)


async def complete_task[T](worker: asyncio.Task[T]) -> T:
    """Defer cancellation until a resource-owning worker finishes, even on repeated stops."""
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(worker)
            break
        except asyncio.CancelledError:
            cancelled = True
            if worker.cancelled():
                raise
        except Exception:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
    if cancelled:
        raise asyncio.CancelledError
    return result


def close_stream(stream) -> None:
    """Attempt both stop and close, even when a disconnected device rejects stop."""
    if stream is None:
        return
    for operation in (stream.stop_stream, stream.close):
        try:
            operation()
        except Exception:
            logger.warning("Could not close audio stream cleanly", exc_info=True)
