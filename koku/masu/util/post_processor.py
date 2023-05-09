from abc import ABC
from abc import abstractmethod


class PostProcessor(ABC):
    @abstractmethod
    def check_ingress_required_columns(self):
        """Checks the requires ingress columns."""
        pass

    @abstractmethod
    def process_dataframe(self, data_frame):
        pass

    @abstractmethod
    def _generate_daily_data(self, data_frame):
        "Generate daily data frames."
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
