"""SourceStatus class."""


class SourcesStatus:
    """This class represents a source status."""

    status = False
    class Meta:
        managed = False
    def __init__(self, status):
        """Construct SourceStatus."""
        self.status = status

    class objects:

        def all():
            sources_status_list = []
            status1 = SourcesStatus(False)
            sources_status_list.append(status1)
            return sources_status_list
