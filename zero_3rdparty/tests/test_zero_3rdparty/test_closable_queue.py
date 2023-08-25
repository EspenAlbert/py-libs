import logging
import time
from concurrent.futures import ThreadPoolExecutor, wait

import pytest

from zero_3rdparty.closable_queue import ClosableQueue, QueueIsClosed

logger = logging.getLogger(__name__)


def test_closing_a_queue_twice():
    queue = ClosableQueue()
    queue.close()


def test_putting_a_message_on_a_closed_queue_should_fail():
    queue = ClosableQueue()
    queue.put(1)
    assert queue.get() == 1
    queue.close()
    with pytest.raises(QueueIsClosed):
        queue.put(1)


def test_putting_a_message_on_a_closed_queue_should_fail_safely_close():
    queue = ClosableQueue()
    queue.put(1)
    assert queue.get() == 1
    queue.close_safely()
    with pytest.raises(QueueIsClosed):
        queue.put(1)


def test_close_safely_when_queue_is_already_closed_should_not_raise_error():
    queue = ClosableQueue()
    queue.close()
    queue.close_safely()
    with pytest.raises(QueueIsClosed):
        queue.put(1)
    with pytest.raises(QueueIsClosed):
        queue.put_nowait(1)


def test_iterating_over_a_closed_queue_should_return_immediately():
    queue = ClosableQueue()

    def iterate(messages: list[str]):
        for m in queue:
            messages.append(m)

    with ThreadPoolExecutor() as executor:
        messages1 = []
        f1 = executor.submit(iterate, messages1)
        queue.put("1")
        queue.close()
        f1.result(timeout=1)
        messages2 = []
        f2 = executor.submit(iterate, messages2)
        f2.result(timeout=1)
    assert messages1 == ["1"]
    assert messages2 == []


@pytest.mark.parametrize("no_wait", [False, True])
def test_should_not_get_sentinel(no_wait):
    queue = ClosableQueue()
    queue.put(1)
    queue.close()
    assert queue.get() == 1
    with pytest.raises(QueueIsClosed):
        if no_wait:
            queue.get_nowait()
        else:
            queue.get()


def test_many_consumers_all_should_finish():
    queue = ClosableQueue()

    def iterate() -> list[str]:
        messages: list[str] = []
        for m in queue:
            messages.append(m)
        return messages

    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(iterate): i for i in range(30)}
        time.sleep(0.1)
        queue.put("1")
        queue.close()
        wait(futures.keys(), timeout=1)
    winner_i = {i for f, i in futures.items() if f.result()}
    assert len(winner_i) == 1
