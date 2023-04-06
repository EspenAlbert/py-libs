from model_lib.metadata import (
    pop_metadata,
    read_metadata_or_none,
    set_metadata,
    update_metadata,
)
from model_lib.metadata.context_dict import get_context_dict, set_context_dict
from model_lib.metadata.metadata_fields import EventMetadata

TASK_ID = EventMetadata.task_id


def test_ensure_metadata_is_deep_copied():
    assert read_metadata_or_none(TASK_ID) is None
    set_metadata(TASK_ID, "t1")
    assert read_metadata_or_none(TASK_ID) == "t1"
    old = get_context_dict()
    new = old.copy_to_new_task("unknown")
    _, m1 = old.popitem()
    _, m2 = new.popitem()
    assert m1 is not m2
    assert m1 == m2
    set_context_dict(new)
    update_metadata(m2)
    assert pop_metadata(TASK_ID) == "t1"
    assert read_metadata_or_none(TASK_ID) is None
