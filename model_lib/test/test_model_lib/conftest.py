# flake8: noqa
from model_lib import dump_functions, errors, model_base, model_dump

assert (  # type: ignore
    errors,
    model_dump,
    model_base,
    dump_functions,
), "necessary for pants to infer import"  # noqa
