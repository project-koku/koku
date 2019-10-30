"""SourceStatus class."""


class SourcesStatus:
    """This class represents a source status."""

    status = False

    def __init__(self, status):
        """Construct SourceStatus."""
        self.status = status
