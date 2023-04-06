from model_lib.metadata import current_metadata
from model_lib.metadata.metadata_dump import add_metadata_dumper, dump_metadata


def test_metadata_dump_doesnt_change_original_metadata():
    MY_KEY = "my_key"
    MY_VALUE = "hello"

    def add_my_metadata(metadata: dict):
        metadata[MY_KEY] = MY_VALUE

    remove_dump_call = add_metadata_dumper(add_my_metadata)
    assert current_metadata() == {}
    assert dump_metadata() == {MY_KEY: MY_VALUE}
    remove_dump_call()
    assert current_metadata() == {}
    assert dump_metadata() == {}
