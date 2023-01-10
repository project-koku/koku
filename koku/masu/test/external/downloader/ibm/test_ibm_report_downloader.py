"""Test the IBMReportDownloader class."""
import shutil
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch

from faker import Faker
from ibm_cloud_sdk_core.api_exception import ApiException

from api.utils import DateHelper
from masu.external import UNCOMPRESSED
from masu.external.downloader.ibm.ibm_report_downloader import create_daily_archives
from masu.external.downloader.ibm.ibm_report_downloader import DATA_DIR
from masu.external.downloader.ibm.ibm_report_downloader import download_pages_from
from masu.external.downloader.ibm.ibm_report_downloader import IBMReportDownloader
from masu.external.downloader.ibm.ibm_report_downloader import NoMoreReportPages
from masu.external.downloader.ibm.ibm_report_downloader import page_downloader_factory
from masu.external.downloader.ibm.ibm_report_downloader import writer_factory
from masu.test import MasuTestCase

FAKE = Faker()


class FakeResponse:
    def __init__(self, data):
        self.text = data


class IBMDownloadHelpers(MasuTestCase):
    """Tests for IBM download helpers."""

    @patch("masu.external.downloader.ibm.ibm_report_downloader.BaseService")
    @patch("masu.external.downloader.ibm.ibm_report_downloader.get_sdk_headers")
    def test_page_downloader_factory_no_more_pages(self, get_sdk_headers, base_service_mock):
        iam_token = FAKE.sha1()
        enterprise_id = FAKE.uuid4()
        credentials = dict(iam_token=iam_token)
        data_source = dict(enterprise_id=enterprise_id)

        get_sdk_headers.return_value = None

        service_mock = MagicMock()
        service_mock.prepare_request.return_value = None
        service_mock.send.side_effect = ApiException(code=400, message="Error: Total pages is 4")
        base_service_mock.return_value = service_mock

        page_downloader = page_downloader_factory(credentials, data_source, "2020-12")
        with self.assertRaises(NoMoreReportPages):
            page_downloader(page=100)

    @patch("masu.external.downloader.ibm.ibm_report_downloader.BaseService")
    @patch("masu.external.downloader.ibm.ibm_report_downloader.get_sdk_headers")
    def test_page_downloader_factory_success(self, get_sdk_headers, base_service_mock):
        iam_token = FAKE.sha1()
        enterprise_id = FAKE.uuid4()
        credentials = dict(iam_token=iam_token)
        data_source = dict(enterprise_id=enterprise_id)

        get_sdk_headers.return_value = None

        service_mock = MagicMock()
        service_mock.prepare_request.return_value = None
        base_service_mock.return_value = service_mock

        page_downloader = page_downloader_factory(credentials, data_source, "2020-12")
        page_downloader(page=2)

        service_mock.prepare_request.assert_called_once_with(
            method="GET",
            url="/v1/resource-instance-usage-reports",
            headers=None,
            params=dict(enterprise_id=enterprise_id, month="2020-12", recurse=True, format="csv", page=2),
        )
        service_mock.send.assert_called_once_with(None)

    def test_download_pages_from_success(self):
        resp = MagicMock()
        resp.get_result.return_value = FakeResponse("data")
        writer = MagicMock()
        page_downloader = MagicMock()
        page_downloader.side_effect = [resp, NoMoreReportPages]

        download_pages_from(page_downloader, writer, 2)
        writer.assert_called_once_with("data")

    def test_download_pages_from_failure(self):
        exc_msg = "network problems"
        writer = MagicMock()
        page_downloader = MagicMock()
        page_downloader.side_effect = [Exception(exc_msg)]

        with self.assertRaises(Exception) as exp:
            download_pages_from(page_downloader, writer, 2)
            self.assertEqual(exp.message, exc_msg)

    def test_writer_factory(self):
        with tempfile.TemporaryDirectory() as temp_dir_name:
            full_path = f"{temp_dir_name}/file.txt"
            writer = writer_factory(full_path)
            report_meta_data = (
                '"Entity ID","Entity Type","Billing Month","Total Pages","Current Page","Created Time"\n'
                '"0cc49d6f294240b4b688ac34cfcc7812,enterprise,2020-12,2,1,2021-03-29T14:36:37.581Z\n'
            )
            report_body = (
                "Enterprise ID,Enterprise Name,Account ID,Account Name\n"
                '"0cc49d6f294240b4b688ac34cfcc7812","Red Hat","2ac47896436e417d81929833f55eb02d","dev_sandbox_sten"\n'
            )
            data = f"{report_meta_data}\n{report_body}"
            writer(data)
            with open(full_path) as temp_file:
                self.assertEqual(report_body, temp_file.read())
            report_meta_data = (
                '"Entity ID","Entity Type","Billing Month","Total Pages","Current Page","Created Time"\n'
                '"0cc49d6f294240b4b688ac34cfcc7812,enterprise,2020-12,2,2,2021-03-29T14:36:37.581Z\n'
            )
            report_body = (
                "Enterprise ID,Enterprise Name,Account ID,Account Name\n"
                '"0cc49d6f294240b4b688ac34cfcc7812","Red Hat","2ac47896436e417d81929833f55eb02d","dev_sandbox_sten"\n'
            )
            data = f"{report_meta_data}\n{report_body}"
            expected_text = (
                "Enterprise ID,Enterprise Name,Account ID,Account Name\n"
                '"0cc49d6f294240b4b688ac34cfcc7812","Red Hat","2ac47896436e417d81929833f55eb02d","dev_sandbox_sten"\n'
                '"0cc49d6f294240b4b688ac34cfcc7812","Red Hat","2ac47896436e417d81929833f55eb02d","dev_sandbox_sten"\n'
            )
            writer(data)
            with open(full_path) as temp_file:
                self.assertEqual(expected_text, temp_file.read())

    @patch("masu.external.downloader.ibm.ibm_report_downloader.get_path_prefix")
    @patch("masu.external.downloader.ibm.ibm_report_downloader.copy_local_report_file_to_s3_bucket")
    def test_create_daily_archives(self, *args):
        dh = DateHelper()
        filename = FAKE.file_name(extension="csv")
        full_local_file = f"{FAKE.file_path()}/{filename}"
        archives = create_daily_archives(
            FAKE.sha1(), FAKE.name(), FAKE.uuid4(), filename, full_local_file, 2, dh.this_month_start, {}
        )
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0], full_local_file)


class IBMReportDownloaderTest(MasuTestCase):
    """Test Cases for the IBMReportDownloader object."""

    def setUp(self):
        """Setup vars for test."""
        super().setUp()
        self.today = DateHelper().today

    def tearDown(self):
        """Remove files and directories created during the test run."""
        super().tearDown()
        shutil.rmtree(DATA_DIR, ignore_errors=True)

    @patch("masu.external.downloader.ibm.ibm_report_downloader.IBMProvider")
    def create_ibm_downloader(self, ibm_provider_mock):
        return IBMReportDownloader(
            customer_name=FAKE.name(),
            data_source=dict(enterprise_id=FAKE.uuid4()),
            provider_uuid=FAKE.uuid4(),
            credentials=dict(iam_token=FAKE.sha1()),
        )

    def test_get_local_file_for_report(self):
        report = FAKE.name()
        downloader = self.create_ibm_downloader()
        self.assertEqual(downloader.get_local_file_for_report(report), report)

    @patch("masu.external.downloader.ibm.ibm_report_downloader.create_daily_archives")
    @patch("masu.external.downloader.ibm.ibm_report_downloader.page_downloader_factory")
    @patch("masu.external.downloader.ibm.ibm_report_downloader.writer_factory")
    @patch("masu.external.downloader.ibm.ibm_report_downloader.download_pages_from")
    @patch("masu.external.downloader.ibm.ibm_report_downloader.os")
    @patch("masu.external.downloader.ibm.ibm_report_downloader.DateHelper")
    def test_download_file(
        self,
        date_helper_mock,
        os_mock,
        download_pages_from_mock,
        writer_factory_mock,
        pag_downloader_factory_mock,
        create_daily_archives_mock,
    ):
        timestamp = "download_timestamp"
        dhInstance = MagicMock()
        dhInstance._now.strftime = MagicMock(return_value=timestamp)
        date_helper_mock.return_value = dhInstance
        expected_etag = "etag"
        key = f"uuid_date_{expected_etag}.csv"
        downloader = self.create_ibm_downloader()
        expected_filenames = [f"{DATA_DIR}/{downloader.customer_name}/ibm/file_1.csv"]
        create_daily_archives_mock.return_value = expected_filenames

        full_local_path, etag, _, file_names = downloader.download_file(key, None, None, None)
        os_mock.makedirs.assert_called_once_with(
            f"{DATA_DIR}/{downloader.customer_name}/ibm/{timestamp}", exist_ok=True
        )
        self.assertEqual(full_local_path, f"{DATA_DIR}/{downloader.customer_name}/ibm/{timestamp}/{key}")
        self.assertEqual(etag, expected_etag)
        self.assertEqual(len(file_names), 1)

    @patch("masu.external.downloader.ibm.ibm_report_downloader.util")
    def test_manifest_context_for_date(self, util_mock):
        expected_manifest_id = 2
        expected_etag = "etag_111"
        util_mock.generate_etag.return_value = expected_etag
        dh = DateHelper()
        start_date = dh.this_month_start
        downloader = self.create_ibm_downloader()
        expected_files = [
            {
                "key": f"{start_date.date()}_{expected_etag}.csv",
                "local_file": f"{start_date.date()}_{expected_etag}.csv",
            }
        ]
        with patch(
            "masu.external.downloader.ibm.ibm_report_downloader.IBMReportDownloader._process_manifest_db_record",
            return_value=expected_manifest_id,
        ):
            report_dict = downloader.get_manifest_context_for_date(start_date.date())
        self.assertEqual(report_dict.get("manifest_id"), expected_manifest_id)
        self.assertEqual(report_dict.get("files"), expected_files)
        self.assertEqual(report_dict.get("compression"), UNCOMPRESSED)
