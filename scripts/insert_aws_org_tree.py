import os
import sys

import psycopg2
import requests
import yaml
from psycopg2 import sql

FILENAME_DEFAULT = "scripts/aws_org_tree.yml"
SCHEMA_DEFAULT = "acct10001"


class InsertAwsOrgTree:
    """AWS org unit crawler."""

    def __init__(self, filename, schema):
        self._migrations()
        self.filename = filename
        self.schema = schema
        self.cursor = self._establish_db_conn()
        self.tree_yaml_contents = self._load_yaml_file(self.filename)
        self.yesterday_accounts = []
        self.yesterday_orgs = []
        self.today_accounts = []
        self.today_orgs = []
        self.nise_accounts = []

    def _migrations(self):
        """Make sure the aws org unit migrations are run."""
        # Without making sure the migrations are run there is a chance that the
        # reporting_awsorganizationalunit table will not be created in the database yet.
        url = "http://{}:{}/api/cost-management/v1/organizations/aws/".format(
            os.getenv("KOKU_API_HOSTNAME"), os.getenv("KOKU_PORT")
        )
        requests.get(url)

    def _establish_db_conn(self):
        """Creates a connection to the database."""
        dbinfo = {
            "database": os.getenv("DATABASE_NAME"),
            "user": os.getenv("DATABASE_USER"),
            "password": os.getenv("DATABASE_PASSWORD"),
            "port": os.getenv("POSTGRES_SQL_SERVICE_PORT"),
            "host": os.getenv("POSTGRES_SQL_SERVICE_HOST"),
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

    def _insert_account(self, node, date):
        """Inserts the account information in the database."""
        # Make sure the account alias is created and get id
        account_alias_sql = """INSERT INTO {schema}.reporting_awsaccountalias (account_id, account_alias)
                               VALUES (%s, %s) ON CONFLICT (account_id) DO NOTHING;
                               SELECT id FROM {schema}.reporting_awsaccountalias WHERE account_id = %s;"""
        account_alias_sql = sql.SQL(account_alias_sql).format(schema=sql.Identifier(self.schema))
        values = [node["account_alias_id"], node["account_alias_name"], node["account_alias_id"]]
        self.cursor.execute(account_alias_sql, values)
        account_alias_id = self.cursor.fetchone()[0]
        # Grab org info from database
        parent_org_id = node["parent_path"].split("&")[-1]
        select_org_sql = """SELECT org_unit_name, org_unit_id, org_unit_path, level
                            FROM {schema}.reporting_awsorganizationalunit WHERE
                            id = (SELECT max(id) FROM {schema}.reporting_awsorganizationalunit
                            WHERE org_unit_id = %s);"""
        select_org_sql = sql.SQL(select_org_sql).format(schema=sql.Identifier(self.schema))
        self.cursor.execute(select_org_sql, [parent_org_id])
        org_name, org_id, org_path, level = self.cursor.fetchone()
        # Check to see if account is created in the database if not create it
        select_sql = """SELECT * FROM {schema}.reporting_awsorganizationalunit
                        WHERE org_unit_name = %s AND org_unit_id = %s AND org_unit_path = %s
                        AND level = %s AND account_alias_id = %s"""
        select_sql = sql.SQL(select_sql).format(schema=sql.Identifier(self.schema))
        values = [org_name, org_id, org_path, level, account_alias_id]
        self.cursor.execute(select_sql, values)
        org_exists = self.cursor.fetchone()
        if org_exists is None:
            insert_account_sql = """INSERT INTO {schema}.reporting_awsorganizationalunit
                                    (org_unit_name, org_unit_id, org_unit_path, created_timestamp,
                                    level, account_alias_id) VALUES (%s, %s, %s, %s, %s, %s)"""
            insert_account_sql = sql.SQL(insert_account_sql).format(schema=sql.Identifier(self.schema))
            values = [org_name, org_id, org_path, date, level, account_alias_id]
            self.cursor.execute(insert_account_sql, values)

    def _insert_org_sql(self, org_name, org_id, org_path, date, level):
        """Inserts the org unit information into the database."""
        select_sql = """SELECT * FROM {schema}.reporting_awsorganizationalunit
                        WHERE org_unit_name = %s and org_unit_id = %s and org_unit_path = %s and level = %s"""
        select_sql = sql.SQL(select_sql).format(schema=sql.Identifier(self.schema))
        values = [org_name, org_id, org_path, level]
        self.cursor.execute(select_sql, values)
        org_exists = self.cursor.fetchone()
        if org_exists is None:
            org_insert_sql = """INSERT INTO {schema}.reporting_awsorganizationalunit
                                (org_unit_name, org_unit_id, org_unit_path, created_timestamp, level)
                                VALUES (%s, %s, %s, %s, %s);"""
            org_insert_sql = sql.SQL(org_insert_sql).format(schema=sql.Identifier(self.schema))
            values = [org_name, org_id, org_path, date, level]
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

    def insert_tree(self):
        """Inserts the tree into the database."""
        try:
            day_list = self.tree_yaml_contents["account_structure"]["days"]
            for day_dict in day_list:
                day = day_dict["day"]
                date = day["date"]
                root = day["root"]
                self._insert_org_sql(root["org_unit_name"], root["org_unit_id"], root["org_unit_id"], date, 0)
                for node in day["nodes"]:
                    if node.get("account", False) is None:
                        account_id = node["account_alias_id"]
                        if account_id not in self.nise_accounts:
                            self.nise_accounts.append(account_id)
                        if account_id in self.yesterday_accounts:
                            self.yesterday_accounts.remove(account_id)
                        self.today_accounts.append(account_id)
                        self._insert_account(node, date)
                    elif node.get("organizational_unit", False) is None:
                        level = node["parent_path"].count("&")
                        level += 1
                        org_id = node["org_unit_id"]
                        org_path = node["parent_path"] + "&" + org_id
                        if org_id in self.yesterday_orgs:
                            self.yesterday_orgs.remove(org_id)
                        self.today_orgs.append(org_id)
                        self._insert_org_sql(node["org_unit_name"], org_id, org_path, date, level)
                self._set_deleted_timestamp(date)
        except KeyError as e:
            print(f"Error: '{self.filename}' file is not formatted correctly, could not find the following key: {e}")
            sys.exit(1)

    def update_nise_yaml(self):
        """Update the nise yaml to contain the accounts in the tree."""
        # TODO: Allow the user to pass in their own nise_yml, for now hard code it to the nise repo stuff.
        nise_yml_path = os.getenv("NISE_REPO_PATH")
        nise_aws_yaml = os.path.join(nise_yml_path, "example_aws_static_data.yml")
        nise_yaml_contents = self._load_yaml_file(nise_aws_yaml)
        new_nise_user_accounts = nise_yaml_contents["accounts"]["user"]
        for account in self.nise_accounts:
            if account not in new_nise_user_accounts:
                new_nise_user_accounts.append(account)
        nise_yaml_contents["accounts"]["user"] = new_nise_user_accounts
        for generator in nise_yaml_contents["generators"]:
            for _, metadata in generator.items():
                metadata["start_date"] = "last_month"
        with open(nise_aws_yaml, "w") as f:
            yaml.dump(nise_yaml_contents, f)
        nise_command = "nise --aws --static-report-file %s --aws-s3-bucket-name %s --aws-s3-report-name local-bucket"
        testing_path = os.getcwd() + "/testing/local_providers/aws_local_1"
        nise_command = nise_command % (nise_aws_yaml, testing_path)
        os.system(nise_command)
        source_url = "http://{}:{}/api/cost-management/v1/sources/".format(
            os.getenv("KOKU_API_HOSTNAME"), os.getenv("KOKU_PORT")
        )
        json_info = {
            "name": "aws_org_tree",
            "source_type": "AWS-local",
            "authentication": {"resource_name": os.getenv("AWS_RESOURCE_NAME")},
            "billing_source": {"bucket": "/tmp/local_bucket_1"},
        }
        requests.post(source_url, json=json_info)
        download_url = "http://{}:{}/api/cost-management/v1/download/".format(
            os.getenv("MASU_API_HOSTNAME"), os.getenv("MASU_PORT")
        )
        requests.get(download_url)
        if nise_aws_yaml == os.path.join(os.getenv("NISE_REPO_PATH"), "example_aws_static_data.yml"):
            git_checkout_cmd = "cd {} && git checkout -- {}".format(os.getenv("NISE_REPO_PATH"), nise_aws_yaml)
            os.system(git_checkout_cmd)


if "__main__" in __name__:
    arg_list = [FILENAME_DEFAULT, SCHEMA_DEFAULT]
    sys_args = sys.argv
    sys_args.pop(0)
    for arg in sys_args:
        arg_key, arg_value = arg.split("=")
        if arg_key == "tree" and arg_value != "":
            arg_list[0] = arg_value
        elif arg_key == "schema" and arg_value != "":
            arg_list[1] = arg_value
    insert_tree_obj = InsertAwsOrgTree(*arg_list)
    insert_tree_obj.insert_tree()
    insert_tree_obj.update_nise_yaml()
