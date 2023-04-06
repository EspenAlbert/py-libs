"""Example of metadata to use when dumping."""
from typing import Any, Iterable


class EventMetadata:
    task_id_parent = "task_id_parent"
    topic = "topic"
    topic_prefix = "topic_prefix"
    tags = "tags"  #: a list of [(key, value)] pairs
    app_id = "app_id"
    task_level = "task_level"  # see Action.task_level
    task_id = "task_id"  # see Action.task_uuid
    task_start = "task_start"  # the start of the 1st RootContext
    debug = "debug"  # flag for sending messages to a debug exchange
    trace_start = "trace_start"  # the start of current RootContext
    dispatch_start_time = "dispatch_start_time"  # start of the DispatchContext
    dispatch_name = "dispatch_name"  # who dispatched
    dump_time = "dump_time"  # dump time
    event_id = "event_id"  # unique event_id per Event (useful to avoid duplicates)
    trace_action = "trace_action"  # action name of the current trace
    session_id = "session_id"  # found from request/previous metadata
    user_id = "user_id"  # found from request/previous metadata
    maybe_duplicate = "maybe_duplicate"  # e.g. when consuming the same message twice


def iter_tags(metadata: dict) -> Iterable[tuple[str, Any]]:
    #: a list of [(key, value)] pairs
    yield from metadata.get(EventMetadata.tags, [])
