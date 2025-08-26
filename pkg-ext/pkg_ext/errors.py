class NoPublicGroupMatch(Exception):
    """Internal error"""

    pass


class PublicGroupAlreadyExist(Exception):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)


class InvalidGroupSelectionError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class LocateError(Exception):
    def __init__(self, locate_ref: str):
        self.locate_ref = locate_ref
        super().__init__(f"Could not pydoc.locate {locate_ref}")


class RefSymbolNotInCodeError(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"RefSymbol {name} not found in code")
