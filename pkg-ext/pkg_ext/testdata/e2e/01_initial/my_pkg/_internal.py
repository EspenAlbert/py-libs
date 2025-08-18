from dataclasses import dataclass


def expose():
    return "EXPOSED"


@dataclass
class MyCls:
    name: str


def expose_with_arg(my_arg: MyCls):
    return my_arg.name


def hidden():
    return "HIDDEN"
