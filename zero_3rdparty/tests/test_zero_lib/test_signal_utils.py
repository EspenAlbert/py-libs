from zero_3rdparty.signal_utils import _callbacks, register_shutdown_callback


def test_removing_callback():
    def never_called():
        pass

    before_length = len(_callbacks)
    de_register = register_shutdown_callback(never_called)
    assert len(_callbacks) == 1 + before_length
    de_register()
    assert len(_callbacks) == before_length
