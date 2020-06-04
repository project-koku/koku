import os
import sys
from datetime import datetime
from datetime import timedelta

import psycopg2
import requests
import yaml
from psycopg2 import sql


class InsertAwsOrgTree:
    """AWS org unit crawler."""

    def __init__(self, tree_yml_path, schema, db_name, start_date=None, nise_yml_path=None):
        """Initialize the insert aws org tree."""
        self.db_name = db_name
        self.tree_yml_path = tree_yml_path
        self.nise_yml_path = nise_yml_path
        self.schema = schema
        self.start_date = start_date
        self.tree_yaml_contents = self._load_yaml_file(self.tree_yml_path)
        if self.nise_yml_path:
            self.nise_yaml_contents = self._load_yaml_file(self.nise_yml_path)
        self.cursor = self._establish_db_conn()
        self.yesterday_accounts = []
        self.yesterday_orgs = []
        self.today_accounts = []
        self.today_orgs = []
        self.nise_accounts = []

    def require_env(self, envvar):
        """Require that the env var be set to move forward with script."""
        var_value = os.getenv(envvar)
        if var_value is None:
            err_msg = "The variable '%s' is required in your environment."
            print(err_msg % (envvar))
            sys.exit(1)
        return var_value

    def _establish_db_conn(self):
        """Creates a connection to the database."""
        dbinfo = {
            "database": self.db_name,
            "user": self.require_env("DATABASE_USER"),
            "password": self.require_env("DATABASE_PASSWORD"),
            "port": self.require_env("POSTGRES_SQL_SERVICE_PORT"),
            "host": self.require_env("POSTGRES_SQL_SERVICE_HOST"),
        }
        with psycopg2.connect(**dbinfo) as conn:
            conn.autocommit = True
            cursor = conn.cursor()
        return cursor

    def _load_yaml_file(self, filename):
        """Local data from yaml file."""
        yamlfile = None
        if not os.path.isfile(filename):
            print("Error: No such file: %s" % filename)
            sys.exit(1)
        try:
            with open(filename, "r+") as yaml_file:
                yamlfile = yaml.safe_load(yaml_file)
        except TypeError:
            yamlfile = yaml.safe_load(filename)
        return yamlfile

    def _insert_account(self, org_node, act_info, date):
        """Inserts the account information in the database."""
        # Make sure the account alias is created and get id
        account_alias_sql = """INSERT INTO {schema}.reporting_awsaccountalias (account_id, account_alias)
                               VALUES (%s, %s) ON CONFLICT (account_id) DO NOTHING;
                               SELECT id FROM {schema}.reporting_awsaccountalias WHERE account_id = %s;"""
        account_alias_sql = sql.SQL(account_alias_sql).format(schema=sql.Identifier(self.schema))
        values = [act_info["account_alias_id"], act_info["account_alias_name"], act_info["account_alias_id"]]
        self.cursor.execute(account_alias_sql, values)
        account_alias_id = self.cursor.fetchone()[0]
        select_sql = """SELECT * FROM {schema}.reporting_awsorganizationalunit
                        WHERE org_unit_name = %s AND org_unit_id = %s AND org_unit_path = %s
                        AND level = %s AND account_alias_id = %s"""
        select_sql = sql.SQL(select_sql).format(schema=sql.Identifier(self.schema))
        values = [
            org_node["org_unit_name"],
            org_node["org_unit_id"],
            org_node["org_path"],
            org_node["level"],
            account_alias_id,
        ]
        self.cursor.execute(select_sql, values)
        org_exists = self.cursor.fetchone()
        if org_exists is None:
            insert_account_sql = """INSERT INTO {schema}.reporting_awsorganizationalunit
                                    (org_unit_name, org_unit_id, org_unit_path, created_timestamp,
                                    level, account_alias_id) VALUES (%s, %s, %s, %s, %s, %s)"""
            insert_account_sql = sql.SQL(insert_account_sql).format(schema=sql.Identifier(self.schema))
            values = [
                org_node["org_unit_name"],
                org_node["org_unit_id"],
                org_node["org_path"],
                date,
                org_node["level"],
                account_alias_id,
            ]
            self.cursor.execute(insert_account_sql, values)

    def _insert_org_sql(self, org_node, date):
        """Inserts the org unit information into the database."""
        select_sql = """SELECT * FROM {schema}.reporting_awsorganizationalunit
                        WHERE org_unit_name = %s and org_unit_id = %s and org_unit_path = %s and level = %s"""
        select_sql = sql.SQL(select_sql).format(schema=sql.Identifier(self.schema))
        values = [org_node["org_unit_name"], org_node["org_unit_id"], org_node["org_path"], org_node["level"]]
        self.cursor.execute(select_sql, values)
        org_exists = self.cursor.fetchone()
        if org_exists is None:
            org_insert_sql = """INSERT INTO {schema}.reporting_awsorganizationalunit
                                (org_unit_name, org_unit_id, org_unit_path, created_timestamp, level)
                                VALUES (%s, %s, %s, %s, %s);"""
            org_insert_sql = sql.SQL(org_insert_sql).format(schema=sql.Identifier(self.schema))
            values = [
                org_node["org_unit_name"],
                org_node["org_unit_id"],
                org_node["org_path"],
                date,
                org_node["level"],
            ]
            self.cursor.execute(org_insert_sql, values)

    def _set_deleted_timestamp(self, date):
        """Updates the delete timestamp for values left in the yesterday lists."""
        if self.yesterday_accounts != []:
            for account_id in self.yesterday_accounts:
                alias_query = """SELECT id FROM {schema}.reporting_awsaccountalias WHERE account_id = %s;"""
                alias_query = sql.SQL(alias_query).format(schema=sql.Identifier(self.schema))
                self.cursor.execute(alias_query, [account_id])
                alias_id = self.cursor.fetchone()[0]
                update_delete_sql = """UPDATE {schema}.reporting_awsorganizationalunit
                                       SET deleted_timestamp = %s WHERE account_alias_id = %s"""
                update_delete_sql = sql.SQL(update_delete_sql).format(schema=sql.Identifier(self.schema))
                self.cursor.execute(update_delete_sql, [date, alias_id])
        if self.yesterday_orgs != []:
            for org_unit in self.yesterday_orgs:
                update_delete_sql = """UPDATE {schema}.reporting_awsorganizationalunit
                                       SET deleted_timestamp = %s WHERE org_unit_id = %s"""
                update_delete_sql = sql.SQL(update_delete_sql).format(schema=sql.Identifier(self.schema))
                self.cursor.execute(update_delete_sql, [date, org_unit])
        self.yesterday_accounts = self.today_accounts
        self.yesterday_orgs = self.today_orgs
        self.today_accounts = []
        self.today_orgs = []

    def calculate_date(self, day_delta):
        """Calculate the date based off of a delta and a range start date."""
        range_start = self.start_date
        if not range_start:
            today = datetime.today().date()
            range_start = today.replace(day=1)
        date = range_start + timedelta(days=day_delta)
        return str(date)

    def insert_tree(self):  # noqa: C901
        """Inserts the tree into the database."""
        try:
            day_list = self.tree_yaml_contents["account_structure"]["days"]
            for day_dict in day_list:
                day = day_dict["day"]
                date_delta = day["date"]
                date = self.calculate_date(date_delta)
                for node in day["nodes"]:
                    org_id = node["org_unit_id"]
                    parent_path = node.get("parent_path", "")
                    if parent_path == "":
                        node["org_path"] = org_id
                        node["level"] = 0
                    else:
                        node["level"] = parent_path.count("&") + 1
                        node["org_path"] = parent_path + "&" + org_id
                    if org_id in self.yesterday_orgs:
                        self.yesterday_orgs.remove(org_id)
                    self.today_orgs.append(org_id)
                    self._insert_org_sql(node, date)
                    if node.get("accounts"):
                        for account in node.get("accounts"):
                            account_id = account["account_alias_id"]
                            if account_id not in self.nise_accounts:
                                self.nise_accounts.append(account_id)
                            if account_id in self.yesterday_accounts:
                                self.yesterday_accounts.remove(account_id)
                            self.today_accounts.append(account_id)
                            self._insert_account(node, account, date)
                self._set_deleted_timestamp(date)
        except KeyError as e:
            print(
                f"Error: '{self.tree_yml_path}' file is not formatted correctly, could not find the following key: {e}"
            )
            sys.exit(1)

    def run_nise_command(self):
        """Updates configures nise, creates aws source and runs download."""
        # Updating the nise file to contain nise account info
        new_nise_user_accounts = self.nise_yaml_contents["accounts"]["user"]
        for account in self.nise_accounts:
            if account not in new_nise_user_accounts:
                new_nise_user_accounts.append(account)
        self.nise_yaml_contents["accounts"]["user"] = new_nise_user_accounts
        for generator in self.nise_yaml_contents["generators"]:
            for _, metadata in generator.items():
                metadata["start_date"] = "last_month"
        with open(self.nise_yml_path, "w") as f:
            yaml.dump(self.nise_yaml_contents, f)
        # Building an running nise command
        testing_path = os.getcwd() + "/testing/local_providers/aws_local_1"
        nise_command = (
            f"nise report aws --static-report-file {self.nise_yml_path} "
            f"--aws-s3-bucket-name {testing_path} --aws-s3-report-name local-bucket"
        )
        os.system(nise_command)
        # Add aws source
        source_url = "http://{}:{}/api/cost-management/v1/sources/".format(
            self.require_env("KOKU_API_HOSTNAME"), self.require_env("KOKU_PORT")
        )
        json_info = {
            "name": "aws_org_tree",
            "source_type": "AWS-local",
            "authentication": {"resource_name": self.require_env("AWS_RESOURCE_NAME")},
            "billing_source": {"bucket": "/tmp/local_bucket_1"},
        }
        requests.post(source_url, json=json_info)
        # Trigger the download
        download_url = "http://{}:{}/api/cost-management/v1/download/".format(
            self.require_env("MASU_API_HOSTNAME"), self.require_env("MASU_PORT")
        )
        requests.get(download_url)
        nise_repo_path = self.require_env("NISE_REPO_PATH")
        if nise_repo_path in self.nise_yml_path:
            git_checkout_cmd = "cd {} && git checkout -- {}".format(nise_repo_path, "example_aws_static_data.yml")
            os.system(git_checkout_cmd)


if "__main__" in __name__:
    # Without making sure the migrations are run there is a chance that the
    # reporting_awsorganizationalunit table will not be created in the database yet.
    url = "http://{}:{}/api/cost-management/v1/organizations/aws/".format(
        os.getenv("KOKU_API_HOSTNAME"), os.getenv("KOKU_PORT")
    )
    requests.get(url)
    default_tree_yml = "scripts/aws_org_tree.yml"
    default_nise_yml = os.path.join(os.getenv("NISE_REPO_PATH"), "example_aws_static_data.yml")
    default_schema = "acct10001"
    default_db = os.getenv("DATABASE_NAME")
    default_delta_start = today = datetime.today().date().replace(day=1)
    arg_list = [default_tree_yml, default_schema, default_db, default_delta_start, default_nise_yml]
    sys_args = sys.argv
    sys_args.pop(0)
    for arg in sys_args:
        arg_key, arg_value = arg.split("=")
        if arg_key == "tree_yml" and arg_value != "":
            arg_list[0] = arg_value
        elif arg_key == "schema" and arg_value != "":
            arg_list[1] = arg_value
        elif arg_key == "nise_yml" and arg_value != "":
            arg_list[3] = arg_value
    insert_tree_obj = InsertAwsOrgTree(*arg_list)
    insert_tree_obj.insert_tree()
    insert_tree_obj.run_nise_command()
