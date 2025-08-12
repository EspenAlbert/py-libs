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
