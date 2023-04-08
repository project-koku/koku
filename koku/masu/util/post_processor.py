import logging
from abc import abstractmethod

from tenant_schemas.utils import schema_context

from masu.util.common import batch


LOG = logging.getLogger(__name__)


class PostProcessor:
    def __init__(self, schema):
        self.schema = schema

    def create_enabled_keys(self, enabled_keys, table):
        """
        Creates enabled key records.
        """
        if not enabled_keys:
            return
        LOG.info("Creating enabled tag key records.")
        changed = False

        if enabled_keys:
            with schema_context(self.schema):
                new_keys = list(set(enabled_keys) - {k.key for k in table.objects.all()})
                if new_keys:
                    changed = True
                    # Processing in batches for increased efficiency
                    for batch_num, new_batch in enumerate(batch(new_keys, _slice=500)):
                        batch_size = len(new_batch)
                        LOG.info(f"Create batch {batch_num + 1}: batch_size {batch_size}")
                        for ix in range(batch_size):
                            new_batch[ix] = table(key=new_batch[ix])
                        table.objects.bulk_create(new_batch, ignore_conflicts=True)
        if not changed:
            LOG.info("No enabled keys added")

        return changed

    @abstractmethod
    def check_ingress_required_columns(self):
        """Checks the requires ingress columns."""
        pass

    @abstractmethod
    def process_dataframe(self, data_frame):
        pass

    @abstractmethod
    def finalize_post_processing(self):
        """
        Uses information gather in the post processing to update the cost models.
        """
        pass

    @abstractmethod
    def get_column_converters(self):
        """
        Return source specific parquet column converters.
        """
        pass
