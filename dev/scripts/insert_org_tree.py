import json
import logging
import os
import sys
from datetime import datetime

import requests
import yaml

logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def require_env(envvar):
    """Require that the env var be set to move forward with script."""
    var_value = os.getenv(envvar)
    if var_value is None:
        LOG.error(f"The variable '{envvar}' is required in your environment.")
        sys.exit(1)
    return var_value


class UploadAwsTreeError(Exception):
    def __init__(self, err_msg):
        self.message = err_msg
        super().__init__(self.message)


class UploadAwsTree:
    def __init__(self, tree_yaml, schema, masu_host, masu_port, start_date=None):
        """Initializes the class."""
        self.tree_yaml = tree_yaml
        self.start_date = start_date
        self.masu_host = masu_host
        self.masu_port = masu_port
        self.schema = schema
        self.source_name = "aws_org_tree"

    def import_yaml(self, yaml_file_path):
        """Imports the yaml file."""
        try:
            with open(yaml_file_path) as file_obj:
                yml_data = yaml.safe_load(file_obj)
            return yml_data
        except Exception as e:
            msg = f"There was an issue reading the yaml. Exception raised: \n {e}"
            raise UploadAwsTreeError(err_msg=msg)

    def convert_tree_yaml_to_json(self, tree_yaml):
        """Reads the tree yaml and converts it to json."""
        tree_yaml_content = self.import_yaml(tree_yaml)
        # Add in vars passed to class
        tree_yaml_content["schema"] = self.schema
        if self.start_date:
            tree_yaml_content["start_date"] = self.start_date
        # Collect account ids to be used for nise cmd later on
        return json.loads(json.dumps(tree_yaml_content))

    def upload_tree(self, provider_uuid):
        """Creates the curl command"""
        aws_org_tree_json = self.convert_tree_yaml_to_json(self.tree_yaml)
        url = f"http://{self.masu_host}:{self.masu_port}/api/cost-management/v1/crawl_account_hierarchy/?provider_uuid={provider_uuid}"  # noqa: E501
        try:
            requests.post(url, json=aws_org_tree_json)
        except Exception as e:
            msg = ("Error: uploading to endpoint", f"post_url: {url}" f"response: {e}")
            raise UploadAwsTreeError(err_msg=msg)

    def source_exists(self, koku_host, koku_port):
        """Check if the source exists."""
        source_url = f"http://{koku_host}:{koku_port}/api/cost-management/v1/sources/?type=AWS-local"
        source_info = requests.get(source_url)
        source_data = source_info.json()
        for source in source_data.get("data"):
            if source.get("name") == self.source_name:
                return True
        return False

    def create_aws_source(self, koku_host, koku_port):
        """Creates the aws source."""
        source_url = f"http://{koku_host}:{koku_port}/api/cost-management/v1/sources/"
        json_info = {
            "name": self.source_name,
            "source_type": "AWS-local",
            "authentication": {"credentials": {"role_arn": "arn:aws:iam::111111111111:role/LocalAWSSource"}},
            "billing_source": {"data_source": {"bucket": "/tmp/local_bucket_1"}},
        }
        LOG.info("Creating a source with the following information:\n" f"\t{json_info}")
        source_info = requests.post(source_url, json=json_info)
        source_data = source_info.json()
        return source_data["uuid"]

    def run_nise_command(self, nise_yaml, koku_host, koku_port):
        """Updates configures nise, creates aws source and runs download."""
        testing_path = os.getcwd() + "/testing/local_providers/aws_local_1"
        nise_command = (
            f"nise report aws --static-report-file {nise_yaml} "
            f"--aws-s3-bucket-name {testing_path} --aws-s3-report-name local-bucket"
        )
        LOG.info("Running the following Nise command:\n" f"\t{nise_command}")
        os.system(nise_command)
        LOG.info("Triggering the masu download")
        download_url = f"http://{self.masu_host}:{self.masu_port}/api/cost-management/v1/download/"
        requests.get(download_url)


if "__main__" in __name__:
    # Without making sure the migrations are run there is a chance that the
    # reporting_awsorganizationalunit table will not be created in the database yet.
    koku_port = require_env("KOKU_PORT")
    koku_host = require_env("KOKU_API_HOSTNAME")
    url = f"http://{koku_host}:{koku_port}/api/cost-management/v1/organizations/aws/"
    requests.get(url)
    sys_args = sys.argv
    sys_args.pop(0)
    tree_yaml = "dev/scripts/aws_org_tree.yml"
    nise_yaml = "dev/scripts/nise_ymls/org_tree_aws_static_data.yml"
    schema = "org1234567"
    start_date = str(datetime.today().date())
    masu_host = require_env("MASU_API_HOSTNAME")
    masu_port = require_env("MASU_PORT")
    for arg in sys_args:
        arg_key, arg_value = arg.split("=")
        if arg_key == "tree_yml" and arg_value != "":
            tree_yaml = arg_value
        elif arg_key == "schema" and arg_value != "":
            schema = arg_value
        elif arg_key == "nise_yml" and arg_value != "":
            nise_yaml = arg_value
        elif arg_key == "start_date" and arg_value != "":
            start_date = arg_value
    upload_obj = UploadAwsTree(tree_yaml, schema, masu_host, masu_port, start_date)
    if not upload_obj.source_exists(koku_host, koku_port):
        source_uuid = upload_obj.create_aws_source(koku_host, koku_port)
        upload_obj.upload_tree(provider_uuid=source_uuid)
        upload_obj.run_nise_command(nise_yaml, koku_host, koku_port)
