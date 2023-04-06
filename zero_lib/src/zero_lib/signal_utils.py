import concurrent.futures
import logging
import os
import signal
import sys
from concurrent.futures.thread import ThreadPoolExecutor
from threading import Lock
from typing import Callable, Optional

from zero_lib.env_reader import process_shutdown_timeout
from zero_lib.object_name import as_name

logger = logging.getLogger(__name__)
#: Normal callbacks for cleaning up on system exit
_callbacks = []
#: Late callbacks for stopping thread pools or other late finishers
_late_callbacks = []
#: Main thread callbacks
_main_thread_callbacks = []
_registered = False
_lock = Lock()


def stop(reason: str, should_exit=True, timeout: float = None):
    if timeout is not None:
        set_shutdown_timeout(timeout)
    logger.warning(f"stopping everything, reason={reason}")
    _on_stop(signal.SIGTERM, reason, should_exit)


def set_shutdown_timeout(timeout: float):
    logger.info(f"setting timeout for shutdown {timeout}")
    os.environ["utils_shutdown_timeout"] = str(timeout)


def _on_stop(signum, frame, should_exit=True):
    """Makes sure the python process stops, usually called by
    KeyboardInterrupt.

    Args:
        should_exit: when False we skip calling the sys.exit()
    Tip:
        should_exit=False, when called from a testing context
    """
    global _callbacks, _late_callbacks, _main_thread_callbacks
    logger.critical(f"received signum: {signum}, frame={frame}")
    with ThreadPoolExecutor(max_workers=100) as executor:
        skip_exit = False
        if _callbacks:
            logger.warning(f"shutting down normal callbacks: {len(_callbacks)}")
            skip_exit = _shutdown(executor, _callbacks, should_exit=False)
        if _late_callbacks:
            logger.warning(f"shutting down late callbacks: {len(_late_callbacks)}")
            should_exit = not bool(_main_thread_callbacks) and should_exit
            _shutdown(
                executor, _late_callbacks, should_exit=should_exit, skip_exit=skip_exit
            )
    if _main_thread_callbacks:
        logger.warning(
            f"shutting down {len(_main_thread_callbacks)} MainThread callbacks"
        )
        for c in _main_thread_callbacks:
            c()


def _shutdown(executor, callbacks, should_exit, skip_exit=False):
    """runs through each callback with the executor.

    Warning:
        Will ALWAYS EXIT if one of the callbacks timeouts
    Returns:
        skip_exit: A flag which can be switched by the shutdown callbacks.
    Tip:
        Use skip_exit=True when you want the MainThread to finish by itself. \
    Examples:
        see :mod:`tests_utils.shutdown_tests_bash`
    """
    callback_tasks = []
    callbacks_copied = list(callbacks)
    for c in list(callbacks_copied):
        callback_tasks.append(executor.submit(c))
    logger.info(f"awaiting shutdown callbacks to complete, len={len(callback_tasks)}")
    for func, t in zip(callbacks_copied, callback_tasks):
        func_name = as_name(func)
        try:
            result = t.result(timeout=process_shutdown_timeout())
        except concurrent.futures.TimeoutError:
            logger.critical(f"timeout when waiting for {func_name}")
            t.set_exception(Exception("signal received and timeout reached"))
            break
        except Exception as e:
            logger.warning(f"exception for callback: {func_name}")
            logger.exception(e)
        else:
            logger.info(f"got result={result} from shutdown callback {func_name}")
            if result:
                logger.info("callback wants to finish the main thread by itself")
                skip_exit = True
    else:
        logger.info("successfully finished shutting down all callbacks")
        if should_exit:
            logger.info("exiting cleanly")
            flush_outputs()
            if not skip_exit:
                sys.exit(0)
            else:
                logger.info("skipping exit")
        return skip_exit
    logger.critical("system is forcing an exit")
    flush_outputs()
    os.kill(os.getpid(), signal.SIGKILL)
    sys.exit("SHUTDOWN NOT CLEAN")


def flush_outputs():
    sys.stdout.flush()
    sys.stderr.flush()


def register_shutdown_callback(
    callback: Callable[[], Optional[bool]], is_late=False, is_main_thread=False
) -> Callable:
    """
    Args:
        callback: If it returns a True then the sys.exit(0) will not be called
    Tip:
        Return True from the callback if everything goes ok and you expect MainThread to finish on its own
        Return False from the callback if you need to "force-stop"
    Returns:
        the function for removing the callback
    """
    global _registered
    logger.info(
        f"adding callback for shutdown signal: {as_name(callback)}, late={is_late}, is_main={is_main_thread}"
    )
    with _lock:
        if is_late:

            def removal_func():
                logger.info(
                    f"removing callback for shutdown signal: {as_name(callback)}, late={is_late}"
                )
                _late_callbacks.remove(callback)

            _late_callbacks.append(callback)
        elif is_main_thread:

            def removal_func():
                logger.info(
                    f"removing callback for shutdown signal: {as_name(callback)}, late={is_late}"
                )
                _main_thread_callbacks.remove(callback)

            _main_thread_callbacks.append(callback)
        else:

            def removal_func():
                logger.info(
                    f"removing callback for shutdown signal: {as_name(callback)}, late={is_late}"
                )
                _callbacks.remove(callback)

            _callbacks.append(callback)
        if not _registered:
            signal.signal(signal.SIGINT, _on_stop)
            signal.signal(signal.SIGTERM, _on_stop)
            _registered = True
        return removal_func
