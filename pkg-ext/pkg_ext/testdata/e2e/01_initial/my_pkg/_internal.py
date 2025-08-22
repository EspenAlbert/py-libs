from my_pkg._internal2 import MyCls


def expose():
    return "EXPOSED"


def expose_with_arg(my_arg: MyCls):
    return my_arg.name


def hidden():
    return "HIDDEN"
