from __future__ import annotations

import logging
from collections.abc import Iterable
from contextlib import suppress
from functools import partial
from queue import Empty, Queue
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

QueueType = TypeVar("QueueType")

_empty = object()


class QueueIsClosed(Exception):
    pass


def _raise_queue_is_closed(item: object, *, queue: ClosableQueue, **kwargs):
    if item is not ClosableQueue.SENTINEL:
        raise QueueIsClosed
    Queue.put(queue, item, **kwargs)


class ClosableQueue(Queue[QueueType], Generic[QueueType]):
    SENTINEL = object()
    __QUEUES: list[ClosableQueue] = []

    def __init__(self, maxsize: int = 0):  # 0 == infinite
        super().__init__(maxsize=maxsize)
        self.__QUEUES.append(self)

    def close(self):
        self.put(self.SENTINEL)
        self.put = partial(_raise_queue_is_closed, queue=self)
        with suppress(Exception):
            self.__QUEUES.remove(self)

    def close_safely(self):
        with suppress(QueueIsClosed):
            self.close()

    def __iter__(self) -> Iterable[QueueType]:
        while True:
            item = self.get()
            try:
                if item is self.SENTINEL:
                    self.put(item)  # ensure next iterator will finish immediately
                    return  # Cause the thread to exit
                yield item
            finally:
                self.task_done()

    def has_next(self):
        """
        Warning: Side effect of put first item to the end of the queue
        """
        next = self.pop()
        if next is _empty:
            return False
        self.put(next)
        return True

    def pop(self, default=_empty):
        try:
            next = self.get_nowait()
        except Empty:
            return default
        else:
            if next is self.SENTINEL:
                self.put(self.SENTINEL)  # ensure next iterator will finish immediately
            return next

    def iter_non_blocking(self) -> Iterable[QueueType]:
        next_or_sentinel = partial(self.pop, self.SENTINEL)
        return iter(next_or_sentinel, self.SENTINEL)

    @classmethod
    def close_all(cls):
        if cls.__QUEUES:
            logger.info("closing all queues")
            for q in list(cls.__QUEUES):  # avoid modification during iteration
                q.close()

    def get_nowait(self) -> QueueType:
        item = super().get_nowait()
        if item is self.SENTINEL:
            raise QueueIsClosed
        return item
