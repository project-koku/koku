# Copyright 2016-2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT
# This script avoids adding any external dependencies
# except for python 2.7 standard library and Spark 2.1
import argparse
import logging
import os
import sys
from datetime import UTC
from time import localtime
from time import strftime

import adbc_driver_postgresql.dbapi
import boto3
import polars as pl

# from pyspark.context import SparkContext, SparkConf

# # from pyspark.sql import SQLContext, DataFrame, Rows
# from pyspark.sql.functions import (
#     lit,
#     struct,
#     array,
#     col,
#     UserDefinedFunction,
#     concat,
#     monotonically_increasing_id,
#     explode,
# )
# from pyspark.sql.types import (
#     StringType,
#     StructField,
#     StructType,
#     LongType,
#     ArrayType,
#     MapType,
#     IntegerType,
#     FloatType,
#     BooleanType,
# )

PYTHON_VERSION = sys.version_info[0]
MYSQL_DRIVER_CLASS = "com.mysql.jdbc.Driver"

# flags for migration direction
FROM_METASTORE = "from-metastore"
TO_METASTORE = "to-metastore"

S3_REGEX = r"^s3[a|n]:\/\/"
S3_VALUE = "s3://"


def remove_null_cols(df):
    not_null_cols = filter(lambda x: x.null_count() != df.height, df)
    not_null_col_names = map(lambda x: x.name, not_null_cols)
    return df.select(not_null_col_names)


class HiveMetastore:
    """
    The class to extract data from Hive Metastore into DataFrames and write Dataframes to
    Hive Metastore. Each field represents a single Hive Metastore table.
    As a convention, the fields are prefixed by ms_ to show that it is raw Hive Metastore data
    """

    def read_table(self, uri, table_name=None):
        """
        Load a JDBC table into Polars Dataframe
        """
        return pl.read_database_uri(f'select * from "{table_name}"', uri, engine="adbc")

    def write_table(self, uri, table_name=None, df: pl.DataFrame = None):
        """
        Write from Polars Dataframe into a JDBC table
        """
        uri = "postgresql://postgres:postgres@localhost:15432/postgres"
        print(f"hive_metastore_migration:write_table. URL: {uri}, table: {table_name}")
        with adbc_driver_postgresql.dbapi.connect(uri) as connection:
            return df.write_database(
                table_name=table_name,
                connection=connection,
                if_table_exists="append",
                engine="adbc",
            )

    def extract_metastore(self):
        print("extracting tables")
        # self.ms_dbs = self.read_table(uri=self.uri, table_name="DBS")
        self.ms_dbs = pl.read_database_uri(
            """select * from "DBS" where "NAME" != 'default'""", self.uri, engine="adbc"
        )
        self.ms_database_params = self.read_table(uri=self.uri, table_name="DATABASE_PARAMS")
        self.ms_cds = self.read_table(uri=self.uri, table_name="CDS")
        self.ms_serdes = self.read_table(uri=self.uri, table_name="SERDES")
        self.ms_sds = self.read_table(uri=self.uri, table_name="SDS")
        self.ms_tbls = self.read_table(uri=self.uri, table_name="TBLS")
        self.ms_table_params = self.read_table(uri=self.uri, table_name="TABLE_PARAMS")
        self.ms_columns = self.read_table(uri=self.uri, table_name="COLUMNS_V2")
        self.ms_bucketing_cols = self.read_table(uri=self.uri, table_name="BUCKETING_COLS")
        self.ms_sd_params = self.read_table(uri=self.uri, table_name="SD_PARAMS")
        self.ms_serde_params = self.read_table(uri=self.uri, table_name="SERDE_PARAMS")
        self.ms_sort_cols = self.read_table(uri=self.uri, table_name="SORT_COLS")
        self.ms_partitions = self.read_table(uri=self.uri, table_name="PARTITIONS")
        self.ms_partition_params = self.read_table(uri=self.uri, table_name="PARTITION_PARAMS")
        self.ms_partition_keys = self.read_table(uri=self.uri, table_name="PARTITION_KEYS")
        self.ms_partition_key_vals = self.read_table(uri=self.uri, table_name="PARTITION_KEY_VALS")

    # order of write matters here
    def export_to_metastore(self):
        print("exporting tables")
        self.write_table(uri=self.uri, table_name="DBS", df=self.ms_dbs)
        self.write_table(uri=self.uri, table_name="DATABASE_PARAMS", df=self.ms_database_params)
        self.write_table(uri=self.uri, table_name="CDS", df=self.ms_cds)
        self.write_table(uri=self.uri, table_name="SERDES", df=self.ms_serdes)
        self.write_table(uri=self.uri, table_name="SDS", df=self.ms_sds)
        self.write_table(uri=self.uri, table_name="TBLS", df=self.ms_tbls)
        self.write_table(uri=self.uri, table_name="TABLE_PARAMS", df=self.ms_table_params)
        self.write_table(uri=self.uri, table_name="COLUMNS_V2", df=self.ms_columns)
        self.write_table(uri=self.uri, table_name="BUCKETING_COLS", df=self.ms_bucketing_cols)
        self.write_table(uri=self.uri, table_name="SD_PARAMS", df=self.ms_sd_params)
        self.write_table(uri=self.uri, table_name="SERDE_PARAMS", df=self.ms_serde_params)
        self.write_table(uri=self.uri, table_name="SORT_COLS", df=self.ms_sort_cols)
        self.write_table(uri=self.uri, table_name="PARTITIONS", df=self.ms_partitions)
        self.write_table(uri=self.uri, table_name="PARTITION_PARAMS", df=self.ms_partition_params)
        self.write_table(uri=self.uri, table_name="PARTITION_KEYS", df=self.ms_partition_keys)
        self.write_table(uri=self.uri, table_name="PARTITION_KEY_VALS", df=self.ms_partition_key_vals)

    def __init__(self, uri):
        self.uri = uri
        self.ms_dbs = None
        self.ms_database_params = None
        self.ms_tbls = None
        self.ms_table_params = None
        self.ms_columns = None
        self.ms_bucketing_cols = None
        self.ms_cds = None
        self.ms_sds = None
        self.ms_sd_params = None
        self.ms_serdes = None
        self.ms_serde_params = None
        self.ms_sort_cols = None
        self.ms_partitions = None
        self.ms_partition_params = None
        self.ms_partition_keys = None
        self.ms_partition_key_vals = None

        print(uri)


class HiveMetastoreTransformer:
    def transform_params(
        self, params_df: pl.DataFrame, id_col: str, key: str = "PARAM_KEY", value: str = "PARAM_VALUE"
    ) -> pl.DataFrame:
        """
        Transform a PARAMS table dataframe to dataframe of 2 columns: (id, Map<key, value>)
        :param params_df: dataframe of PARAMS table
        :param id_col: column name for id field
        :param key: column name for key
        :param value: column name for value
        :return: dataframe of params in map
        """
        return self.kv_pair_to_map(params_df, id_col, key, value, "Parameters")

    def kv_pair_to_map(self, df: pl.DataFrame, id_col: str, key: str, value: str, map_col_name: str) -> pl.DataFrame:
        return df.group_by(id_col).agg(
            pl.struct([key, value])
            .map_elements(
                lambda row: {x[key]: x[value] for x in row if x[key] is not None},
                return_dtype=pl.Struct,
            )
            .alias(map_col_name)
        )

    def transform_df_with_idx_string(
        self, df: pl.DataFrame, id_col, idx, payloads_column_name, select_col
    ) -> pl.DataFrame:
        """
        Aggregate dataframe by ID, create a single PAYLOAD column where each row is a list of data sorted by IDX, and
        each element is a payload created by payload_func. Example:
        Input:
        df =
        +---+---+----+----+
        | ID|IDX|COL1|COL2|
        +---+---+----+----+
        |  1|  2|   1|   1|
        |  1|  1|   2|   2|
        |  2|  1|   3|   3|
        +---+---+----+----+
        id = 'ID'
        idx = 'IDX'
        payload_list_name = 'PAYLOADS'
        payload_func = row.COL1 + row.COL2
        Output:
        +------+--------+
        |    ID|PAYLOADS|
        +------+--------+
        |     1| [4, 2] |
        |     2|    [6] |
        +------+--------+
        The method assumes (ID, IDX) is input table primary key. ID and IDX values cannot be None
        :param df: dataframe with id and idx columns
        :param id_col: name of column for id
        :param idx: name of column for sort index
        :param payloads_column_name: the column name for payloads column in the output dataframe
        :param payload_func: the function to transform an input row to a payload object
        :param payload_type: the schema type for a single payload object
        :return: output dataframe with data grouped by id and sorted by idx
        """
        return df.sort(idx).group_by(id_col).agg(pl.col(select_col).alias(payloads_column_name))

    def transform_df_with_idx_struct(
        self, df: pl.DataFrame, id_col, idx, payloads_column_name, select_cols, rename_cols
    ) -> pl.DataFrame:
        return (
            df.rename(rename_cols).sort(idx).group_by(id_col).agg(pl.struct(select_cols).alias(payloads_column_name))
        )

    def transform_ms_partition_keys(self, ms_partition_keys: pl.DataFrame):
        ms_partition_keys = ms_partition_keys.fill_null(strategy="zero")
        return self.transform_df_with_idx_struct(
            df=ms_partition_keys,
            id_col="TBL_ID",
            idx="INTEGER_IDX",
            payloads_column_name="PartitionKeys",
            select_cols=["Name", "Type", "Comment"],
            rename_cols={"PKEY_NAME": "Name", "PKEY_TYPE": "Type", "PKEY_COMMENT": "Comment"},
        ).with_columns(pl.col("PartitionKeys").fill_null(value=[]))

    def transform_ms_partition_key_vals(self, ms_partition_key_vals: pl.DataFrame):
        ms_partition_key_vals = ms_partition_key_vals.fill_null(strategy="zero")
        return self.transform_df_with_idx_string(
            df=ms_partition_key_vals,
            id_col="PART_ID",
            idx="INTEGER_IDX",
            payloads_column_name="Values",
            select_col="PART_KEY_VAL",
        )

    def transform_ms_bucketing_cols(self, ms_bucketing_cols: pl.DataFrame):
        ms_bucketing_cols = ms_bucketing_cols.fill_null(strategy="zero")
        return self.transform_df_with_idx_string(
            df=ms_bucketing_cols,
            id_col="SD_ID",
            idx="INTEGER_IDX",
            payloads_column_name="BucketColumns",
            select_col="BUCKET_COL_NAME",
        )

    def transform_ms_columns(self, ms_columns: pl.DataFrame):
        ms_columns = ms_columns.fill_null(strategy="zero")
        return self.transform_df_with_idx_struct(
            df=ms_columns,
            id_col="CD_ID",
            idx="INTEGER_IDX",
            payloads_column_name="Columns",
            select_cols=["Name", "Type", "Comment"],
            rename_cols={"COLUMN_NAME": "Name", "TYPE_NAME": "Type", "COMMENT": "Comment"},
        )

    def transform_ms_sort_cols(self, ms_sort_cols: pl.DataFrame):
        ms_sort_cols = ms_sort_cols.fill_null(strategy="zero")
        return self.transform_df_with_idx_struct(
            df=ms_sort_cols,
            id_col="SD_ID",
            idx="INTEGER_IDX",
            payloads_column_name="SortColumns",
            select_cols=["Name", "SortOrder"],
            rename_cols={"COLUMN_NAME": "Name", "ORDER": "SortOrder"},
        ).with_columns(pl.col("SortColumns").fill_null(value=[]))

    def transform_ms_serde_info(self, ms_serdes: pl.DataFrame, ms_serde_params: pl.DataFrame) -> pl.DataFrame:
        ms_serdes = ms_serdes.join(ms_serde_params, on="SERDE_ID", how="left")
        return ms_serdes.rename({"NAME": "Name", "SLIB": "SerializationLibrary"}).select(
            "SERDE_ID",
            pl.struct("Name", "SerializationLibrary").alias("SerdeInfo"),
            "Parameters",
        )

    def transform_storage_descriptors(
        self,
        ms_sds: pl.DataFrame,
        ms_sd_params: pl.DataFrame,
        ms_columns: pl.DataFrame,
        ms_bucketing_cols: pl.DataFrame,
        ms_serdes: pl.DataFrame,
        ms_serde_params: pl.DataFrame,
        ms_sort_cols: pl.DataFrame,
    ) -> pl.DataFrame:
        bucket_columns = self.transform_ms_bucketing_cols(ms_bucketing_cols)
        columns = self.transform_ms_columns(ms_columns)
        parameters = self.transform_params(ms_sd_params, id_col="SD_ID")
        ms_serde_params = self.transform_params(ms_serde_params, id_col="SERDE_ID")
        serde_info = self.transform_ms_serde_info(ms_serdes=ms_serdes, ms_serde_params=ms_serde_params)
        sort_columns = self.transform_ms_sort_cols(ms_sort_cols)

        storage_descriptors_joined = (
            ms_sds.join(other=bucket_columns, on="SD_ID", how="left")
            .join(other=columns, on="CD_ID", how="left")
            .join(other=parameters, on="SD_ID", how="left")
            .join(other=serde_info, on="SERDE_ID", how="left")
            .join(other=sort_columns, on="SD_ID", how="left")
            .with_columns(Location=pl.col("LOCATION").str.replace(S3_REGEX, S3_VALUE))
            .rename(
                {
                    "INPUT_FORMAT": "InputFormat",
                    "OUTPUT_FORMAT": "OutputFormat",
                    "NUM_BUCKETS": "NumberOfBuckets",
                    "IS_COMPRESSED": "Compressed",
                    "IS_STOREDASSUBDIRECTORIES": "StoredAsSubDirectories",
                }
            )
        )
        cleaned = remove_null_cols(storage_descriptors_joined)
        init_cols = {
            "Columns",
            "Location",
            "InputFormat",
            "OutputFormat",
            "Compressed",
            "NumberOfBuckets",
            "SerdeInfo",
            "BucketColumns",
            "Parameters",
            "StoredAsSubDirectories",
        }
        select_cols = set(cleaned.columns) & init_cols

        return cleaned.select("SD_ID", StorageDescriptor=pl.struct(select_cols))

    def transform_tables(
        self,
        db_tbl_joined: pl.DataFrame,
        ms_table_params: pl.DataFrame,
        storage_descriptors: pl.DataFrame,
        ms_partition_keys: pl.DataFrame,
    ) -> pl.DataFrame:
        ms_table_params = self.transform_params(ms_table_params, "TBL_ID")
        partition_keys = self.transform_ms_partition_keys(ms_partition_keys)

        tbls_joined = (
            db_tbl_joined.with_columns(
                pl.from_epoch(pl.col(["LAST_ACCESS_TIME"]), time_unit="s").cast(pl.Datetime(time_zone=UTC))
            )
            .join(ms_table_params, on="TBL_ID", how="left")
            .join(other=partition_keys, on="TBL_ID", how="left")
            .join(other=storage_descriptors, on="SD_ID", how="left")
            .rename(
                {
                    "NAME": "DatabaseName",
                    "TBL_NAME": "Name",
                    "LAST_ACCESS_TIME": "LastAccessTime",
                    "TBL_TYPE": "TableType",
                    "OWNER": "Owner",
                    "RETENTION": "Retention",
                    "VIEW_EXPANDED_TEXT": "ViewExpandedText",
                    "VIEW_ORIGINAL_TEXT": "ViewOriginalText",
                },
            )
        ).drop_nulls(subset=["Name", "DatabaseName"])

        cleaned = remove_null_cols(tbls_joined)
        init_cols = {
            "Name",
            "Owner",
            "LastAccessTime",
            "Retention",
            "StorageDescriptor",
            "PartitionKeys",
            "ViewOriginalText",
            "ViewExpandedText",
            "TableType",
            "Parameters",
        }
        select_cols = set(cleaned.columns) & init_cols

        return tbls_joined.select("DatabaseName", TableInput=pl.struct(select_cols))

    def transform_partitions(
        self,
        db_tbl_joined: pl.DataFrame,
        ms_partitions: pl.DataFrame,
        storage_descriptors: pl.DataFrame,
        ms_partition_params: pl.DataFrame,
        ms_partition_key_vals: pl.DataFrame,
    ) -> pl.DataFrame:
        db_tbl_names = db_tbl_joined.select(
            db_tbl_joined["NAME"].alias("DatabaseName"),
            db_tbl_joined["TBL_NAME"].alias("TableName"),
            "TBL_ID",
        )
        ms_partition_params = self.transform_params(ms_partition_params, id_col="PART_ID")
        part_values = self.transform_ms_partition_key_vals(ms_partition_key_vals)

        parts_with_db_tbl = (
            ms_partitions.with_columns(
                pl.from_epoch(pl.col(["CREATE_TIME", "LAST_ACCESS_TIME"]), time_unit="s").cast(
                    pl.Datetime(time_zone=UTC)
                )
            )
            .rename({"CREATE_TIME": "CreationTime", "LAST_ACCESS_TIME": "LastAccessTime"})
            .join(other=db_tbl_names, on="TBL_ID", how="inner")
            .join(ms_partition_params, on="PART_ID", how="left")
            .join(other=storage_descriptors, on="SD_ID", how="left")
            .join(other=part_values, on="PART_ID", how="left")
            .drop_nulls(subset=["Values", "DatabaseName", "TableName"])
        )

        return remove_null_cols(
            parts_with_db_tbl.group_by("DatabaseName", "TableName",).agg(
                PartitionInputList=pl.struct(
                    "Values",
                    "LastAccessTime",
                    "StorageDescriptor",
                    "Parameters",
                ),
            )
        )

    def transform_databases(self, ms_dbs: pl.DataFrame, ms_database_params) -> pl.DataFrame:
        return (
            ms_dbs.join(self.transform_params(ms_database_params, "DB_ID"), on="DB_ID", how="left")
            .with_columns(LocationUri=pl.col("DB_LOCATION_URI").str.replace(S3_REGEX, S3_VALUE))
            .rename({"NAME": "Name", "DESC": "Description"})
            .select(
                "Name",
                "Description",
                "LocationUri",
                "Parameters",
            )
            .drop_nulls(subset=["Name"])
            .fill_null("")
        )

    def transform(self, hive_metastore: HiveMetastore):
        print("transforming data")
        dbs_prefixed = hive_metastore.ms_dbs.with_columns(NAME=(self.db_prefix + pl.col("NAME")))
        tbls_prefixed = hive_metastore.ms_tbls.with_columns(TBL_NAME=(self.db_prefix + pl.col("TBL_NAME")))

        databases = self.transform_databases(ms_dbs=dbs_prefixed, ms_database_params=hive_metastore.ms_database_params)

        storage_descriptors = self.transform_storage_descriptors(
            ms_sds=hive_metastore.ms_sds,
            ms_sd_params=hive_metastore.ms_sd_params,
            ms_columns=hive_metastore.ms_columns,
            ms_bucketing_cols=hive_metastore.ms_bucketing_cols,
            ms_serdes=hive_metastore.ms_serdes,
            ms_serde_params=hive_metastore.ms_serde_params,
            ms_sort_cols=hive_metastore.ms_sort_cols,
        )

        db_tbl_joined = dbs_prefixed.select("DB_ID", "NAME").join(other=tbls_prefixed, on="DB_ID", how="inner")

        tables = self.transform_tables(
            db_tbl_joined=db_tbl_joined,
            ms_table_params=hive_metastore.ms_table_params,
            storage_descriptors=storage_descriptors,
            ms_partition_keys=hive_metastore.ms_partition_keys,
        )

        partitions = self.transform_partitions(
            db_tbl_joined=db_tbl_joined,
            ms_partitions=hive_metastore.ms_partitions,
            storage_descriptors=storage_descriptors,
            ms_partition_params=hive_metastore.ms_partition_params,
            ms_partition_key_vals=hive_metastore.ms_partition_key_vals,
        )

        return databases, tables, partitions

    def __init__(self, db_prefix, table_prefix):
        self.db_prefix = db_prefix
        self.table_prefix = table_prefix


def get_output_dir(output_dir_parent):
    if not output_dir_parent:
        raise ValueError("output path cannot be empty")
    if output_dir_parent[-1] != "/":
        output_dir_parent = f"{output_dir_parent}/"
    output_dir = f'{output_dir_parent}{strftime("%Y-%m-%d-%H-%M-%S", localtime())}/'
    os.makedirs(os.path.dirname(output_dir), exist_ok=True)
    return output_dir


def get_options(parser, args):
    parsed, extra = parser.parse_known_args(args[1:])
    print("Found arguments:", vars(parsed))
    if extra:
        print("Found unrecognized arguments:", extra)
    return vars(parsed)


def parse_arguments(args):
    parser = argparse.ArgumentParser(prog=args[0])
    parser.add_argument(
        "-m",
        "--mode",
        required=True,
        choices=[FROM_METASTORE, TO_METASTORE],
        help="Choose to migrate metastore either from JDBC or from S3",
    )
    parser.add_argument(
        "-U",
        "--jdbc-url",
        required=True,
        help="Hive metastore JDBC url, example: metastore.abcd.us-east-1.rds.amazonaws.com:3306/database/",
    )
    parser.add_argument("-u", "--jdbc-username", required=True, help="Hive metastore JDBC user name")
    parser.add_argument("-p", "--jdbc-password", required=True, help="Hive metastore JDBC password")
    parser.add_argument(
        "-d", "--database-prefix", required=False, help="Optional prefix for database names in Glue DataCatalog"
    )
    parser.add_argument(
        "-t", "--table-prefix", required=False, help="Optional prefix for table name in Glue DataCatalog"
    )
    parser.add_argument("-o", "--output-path", required=False, help="Output path, either local directory or S3 path")
    parser.add_argument("-i", "--input_path", required=False, help="Input path, either local directory or S3 path")

    options = get_options(parser, args)

    if options["mode"] == FROM_METASTORE:
        validate_options_in_mode(
            options=options, mode=FROM_METASTORE, required_options=["output_path"], not_allowed_options=["input_path"]
        )
    elif options["mode"] == TO_METASTORE:
        validate_options_in_mode(
            options=options, mode=TO_METASTORE, required_options=["input_path"], not_allowed_options=["output_path"]
        )
    else:
        raise AssertionError("unknown mode " + options["mode"])

    return options


def etl_from_metastore(db_prefix, table_prefix, hive_metastore: HiveMetastore, options):
    # extract
    hive_metastore.extract_metastore()

    # transform
    (databases, tables, partitions) = HiveMetastoreTransformer(db_prefix, table_prefix).transform(hive_metastore)

    # load
    output_path = get_output_dir(options["output_path"])

    print(f"saving data to {output_path}")

    databases.write_json(f"{output_path}databases.json")
    tables.write_json(f"{output_path}tables.json")
    partitions.write_json(f"{output_path}partitions.json")

    glue = boto3.client("glue", region_name="us-east-1")

    # breakpoint()

    print("creating db")
    for db in databases.iter_rows(named=True):
        try:
            schema = db["Name"]
            glue.delete_database(Name=schema)
            print(f"Deleting database: {schema}")
        except Exception as e:
            print(f"Failed to delete db: {schema}, its possible it was already deleted: {e}")
        db = delete_none(db)
        glue.create_database(CatalogId="589173575009", DatabaseInput=db)
    print("creating tables")
    for table in tables.iter_rows(named=True):
        table = delete_none(table)
        glue.create_table(CatalogId="589173575009", **table)
    print("creating partitions")
    for part in partitions.iter_rows(named=True):
        part = delete_none(part)
        glue.batch_create_partition(CatalogId="589173575009", **part)


def delete_none(_dict):
    """Delete None values recursively from all of the dictionaries"""
    for key, value in list(_dict.items()):
        if isinstance(value, dict):
            delete_none(value)
        elif value is None:
            del _dict[key]
        elif isinstance(value, list):
            for v_i in value:
                if isinstance(v_i, dict):
                    delete_none(v_i)

    return _dict


def validate_options_in_mode(options, mode, required_options, not_allowed_options):
    for option in required_options:
        if options.get(option) is None:
            raise AssertionError(f"Option {option} is required for mode {mode}")
    for option in not_allowed_options:
        if options.get(option) is not None:
            raise AssertionError(f"Option {option} is not allowed for mode {mode}")


def validate_aws_regions(region):
    """
    To validate the region in the input. The region list below may be outdated as AWS and Glue expands, so it only
    create an error message if validation fails.
    If the migration destination is in a region other than Glue supported regions, the job will fail.
    :return: None
    """
    if region is None:
        return

    aws_glue_regions = [
        "ap-northeast-1",  # Tokyo
        "eu-west-1",  # Ireland
        "us-east-1",  # North Virginia
        "us-east-2",  # Ohio
        "us-west-2",  # Oregon
    ]

    aws_regions = aws_glue_regions + [
        "ap-northeast-2",  # Seoul
        "ap-south-1",  # Mumbai
        "ap-southeast-1",  # Singapore
        "ap-southeast-2",  # Sydney
        "ca-central-1",  # Montreal
        "cn-north-1",  # Beijing
        "cn-northwest-1",  # Ningxia
        "eu-central-1",  # Frankfurt
        "eu-west-2",  # London
        "sa-east-1",  # Sao Paulo
        "us-gov-west-1",  # GovCloud
        "us-west-1",  # Northern California
    ]

    error_msg = f"Invalid region: {region}, the job will fail if the destination is not in a Glue supported region"
    if region not in aws_regions:
        logging.error(error_msg)
    elif region not in aws_glue_regions:
        logging.warn(error_msg)


def main():
    options = parse_arguments(sys.argv)

    db_options = {"url": options["jdbc_url"], "user": options["jdbc_username"], "password": options["jdbc_password"]}
    db_prefix = options.get("database_prefix") or ""
    table_prefix = options.get("table_prefix") or ""

    # extract
    uri = f"postgresql://{db_options['user']}:{db_options['password']}@{db_options['url']}"
    # connection = adbc_driver_postgresql.dbapi.connect(uri)
    hive_metastore = HiveMetastore(uri)

    if options["mode"] == FROM_METASTORE:
        etl_from_metastore(db_prefix, table_prefix, hive_metastore, options)


if __name__ == "__main__":
    main()
