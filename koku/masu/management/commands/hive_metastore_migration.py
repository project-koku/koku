# Copyright 2016-2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT
# This script avoids adding any external dependencies
# except for python 2.7 standard library and Spark 2.1
import argparse
import json
import logging
import re
import sys
from datetime import datetime
from datetime import UTC
from time import localtime
from time import strftime

import polars as pl

# import adbc_driver_postgresql.dbapi

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


def remove(lis, elem):
    lis.remove(elem)
    return lis


def get_schema_type(df, column_name):
    return df.schema[column_name]


@pl.api.register_dataframe_namespace("custom_join")
class JoinFrame:
    def __init__(self, df: pl.DataFrame):
        self._df = df

    def join_other_to_single_column(
        self, other: pl.DataFrame, on: str, how: str, new_column_name: str
    ) -> pl.DataFrame:
        """
        :param df: this dataframe
        :param other: other dataframe
        :param on: the column to join on
        :param how: :param how: str, default "inner". One of "inner", "left", "right",
                                             "full", "semi", "anti", "cross", "outer".
        :param new_column_name: the column name for all fields from the other dataframe
        :return: this dataframe, with a single new column containing all fields of the other dataframe
        :type df: DataFrame
        :type other: DataFrame
        :type new_column_name: str
        """
        other_cols = remove(other.columns, on)
        other_combined = other.select([on, pl.struct(other_cols).alias(new_column_name)])
        return self._df.join(other=other_combined, on=on, how=how)


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
        return self.kv_pair_to_map(params_df, id_col, key, value, "parameters")

    def kv_pair_to_map(self, df: pl.DataFrame, id_col: str, key: str, value: str, map_col_name: str) -> pl.DataFrame:
        return df.group_by(id_col).agg(
            pl.struct([key, value])
            .map_elements(
                lambda row: json.dumps({x[key]: x[value] for x in row if x[key] is not None}),
                return_dtype=pl.String,
            )
            .alias(map_col_name)
        )

    def join_with_params(self, df: pl.DataFrame, df_params: pl.DataFrame, id_col: str) -> pl.DataFrame:
        df_params_map = self.transform_params(params_df=df_params, id_col=id_col)
        return df.join(other=df_params_map, on=id_col, how="left")

    def transform_df_with_idx_string(self, df: pl.DataFrame, id_col, idx, payloads_column_name, select_col):
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

    def transform_df_with_idx_struct(self, df: pl.DataFrame, id_col, idx, payloads_column_name, select_cols):
        df = df.rename(select_cols)
        return df.sort(idx).group_by(id_col).agg(pl.struct(select_cols.values()).alias(payloads_column_name))

    def transform_ms_partition_keys(self, ms_partition_keys: pl.DataFrame):
        return self.transform_df_with_idx_struct(
            df=ms_partition_keys,
            id_col="TBL_ID",
            idx="INTEGER_IDX",
            payloads_column_name="partitionKeys",
            select_cols={"PKEY_NAME": "name", "PKEY_TYPE": "type", "PKEY_COMMENT": "comment"},
        )

    def transform_ms_partition_key_vals(self, ms_partition_key_vals: pl.DataFrame):
        return self.transform_df_with_idx_string(
            df=ms_partition_key_vals,
            id_col="PART_ID",
            idx="INTEGER_IDX",
            payloads_column_name="values",
            select_col="PART_KEY_VAL",
        )

    def transform_ms_bucketing_cols(self, ms_bucketing_cols: pl.DataFrame):
        return self.transform_df_with_idx_string(
            df=ms_bucketing_cols,
            id_col="SD_ID",
            idx="INTEGER_IDX",
            payloads_column_name="bucketColumns",
            select_col="BUCKET_COL_NAME",
        )

    def transform_ms_columns(self, ms_columns: pl.DataFrame):
        return self.transform_df_with_idx_struct(
            df=ms_columns,
            id_col="CD_ID",
            idx="INTEGER_IDX",
            payloads_column_name="columns",
            select_cols={"COLUMN_NAME": "name", "TYPE_NAME": "type", "COMMENT": "comment"},
        )

    def transform_ms_skewed_col_names(self, ms_skewed_col_names: pl.DataFrame):
        return self.transform_df_with_idx_string(
            df=ms_skewed_col_names,
            id_col="SD_ID",
            idx="INTEGER_IDX",
            payloads_column_name="skewedColumnNames",
            select_col="SKEWED_COL_NAME",
        )

    def transform_ms_skewed_string_list_values(self, ms_skewed_string_list_values: pl.DataFrame):
        return self.transform_df_with_idx_string(
            df=ms_skewed_string_list_values,
            id_col="STRING_LIST_ID",
            idx="INTEGER_IDX",
            payloads_column_name="skewedColumnValuesList",
            select_col="STRING_LIST_VALUE",
        )

    def transform_ms_sort_cols(self, ms_sort_cols: pl.DataFrame):
        return self.transform_df_with_idx_struct(
            df=ms_sort_cols,
            id_col="SD_ID",
            idx="INTEGER_IDX",
            payloads_column_name="sortColumns",
            select_cols={"COLUMN_NAME": "column", "ORDER": "order"},
        )

    @staticmethod
    def s3a_or_s3n_to_s3_in_location(df: pl.DataFrame, location_col_name: str) -> pl.DataFrame:
        """
        For a dataframe with a column containing location strings, for any location "s3a://..." or "s3n://...", replace
        them with "s3://...".
        :param df: dataframe
        :param location_col_name: the name of the column containing location, must be string type
        :return: dataframe with location columns where all "s3a" or "s3n" protocols are replaced by "s3"
        """

        def udf(location):
            return None if location is None else re.sub(r"^s3[a|n]:\/\/", "s3://", location)

        return df.with_columns(pl.col(location_col_name).map_elements(udf, return_dtype=pl.String))

    @staticmethod
    def add_prefix_to_column(df, column_to_modify, prefix):
        def udf(col):
            return prefix + col

        if prefix is None or prefix == "":
            return df
        return df.with_columns(pl.col(column_to_modify).map_elements(udf, return_dtype=pl.String))

    @staticmethod
    def utc_timestamp_to_iso8601_time(df, date_col_name, new_date_col_name):
        """
        Tape DataCatalog writer uses Gson to parse Date column. According to Gson deserializer, (https://goo.gl/mQdXuK)
        it uses either java DateFormat or ISO-8601 format. I convert Date to be compatible with java DateFormat
        :param df: dataframe with a column of unix timestamp in seconds of number type
        :param date_col_name: timestamp column
        :param new_date_col_name: new column with converted timestamp, if None, old column name is used
        :type df: DataFrame
        :type date_col_name: str
        :type new_date_col_name: str
        :return: dataframe with timestamp column converted to string representation of time
        """

        def udf(timestamp):
            if timestamp is None:
                return None
            return datetime.fromtimestamp(timestamp=float(timestamp), tz=UTC).strftime("%b %d, %Y %I:%M:%S %p")

        return df.with_columns(
            pl.col(date_col_name).map_elements(udf, return_dtype=pl.String).alias(new_date_col_name)
        )

    @staticmethod
    def transform_timestamp_cols(df, date_cols_map):
        """
        Call timestamp_int_to_iso8601_time in batch, rename all time columns in date_cols_map keys.
        :param df: dataframe with columns of unix timestamp
        :param date_cols_map: map from old column name to new column name
        :type date_cols_map: dict
        :return: dataframe
        """
        for k, v in date_cols_map.items():
            df = HiveMetastoreTransformer.utc_timestamp_to_iso8601_time(df, k, v)
        return df

    @staticmethod
    def join_dbs_tbls(ms_dbs: pl.DataFrame, ms_tbls: pl.DataFrame) -> pl.DataFrame:
        return ms_dbs.select("DB_ID", "NAME").join(other=ms_tbls, on="DB_ID", how="inner")

    def transform_skewed_values_and_loc_map(
        self, ms_skewed_string_list_values: pl.DataFrame, ms_skewed_col_value_loc_map: pl.DataFrame
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        def udf(values):
            return "".join(map(lambda v: "" if v is None else "%d%%%s" % (len(v), v), values))

        # columns: (STRING_LIST_ID:BigInt, skewedColumnValuesList:List[String])
        skewed_values_list = self.transform_ms_skewed_string_list_values(ms_skewed_string_list_values)

        # columns: (STRING_LIST_ID:BigInt, skewedColumnValuesStr:String)
        skewed_value_str = skewed_values_list.with_columns(
            pl.col("skewedColumnValuesList").map_elements(udf, return_dtype=pl.String).alias("skewedColumnValuesStr")
        )

        # columns: (SD_ID: BigInt, STRING_LIST_ID_KID: BigInt, STRING_LIST_ID: BigInt,
        # LOCATION: String, skewedColumnValuesStr: String)
        skewed_value_str_with_loc = ms_skewed_col_value_loc_map.join(
            other=skewed_value_str,
            # on=[ms_skewed_col_value_loc_map["STRING_LIST_ID_KID"] == skewed_value_str["STRING_LIST_ID"]],
            how="inner",
            left_on="STRING_LIST_ID_KID",
            right_on="STRING_LIST_ID",
        )

        # columns: (SD_ID: BigInt, skewedColumnValueLocationMaps: Map[String, String])
        skewed_column_value_location_maps = self.kv_pair_to_map(
            df=skewed_value_str_with_loc,
            id_col="SD_ID",
            key="skewedColumnValuesStr",
            value="LOCATION",
            map_col_name="skewedColumnValueLocationMaps",
        )

        # columns: (SD_ID: BigInt, skewedColumnValues: List[String])
        skewed_column_values = skewed_value_str_with_loc.group_by("SD_ID").agg(pl.col("skewedColumnValuesStr"))

        return skewed_column_values, skewed_column_value_location_maps

    def transform_skewed_info(self, ms_skewed_col_names, ms_skewed_string_list_values, ms_skewed_col_value_loc_map):
        (skewed_column_values, skewed_column_value_location_maps) = self.transform_skewed_values_and_loc_map(
            ms_skewed_string_list_values, ms_skewed_col_value_loc_map
        )

        # columns: (SD_ID: BigInt, skewedColumnNames: List[String])
        skewed_column_names = self.transform_ms_skewed_col_names(ms_skewed_col_names)

        return skewed_column_names.join(
            other=skewed_column_value_location_maps, on="SD_ID", how="full", coalesce=True
        ).join(other=skewed_column_values, on="SD_ID", how="full", coalesce=True)

    def transform_param_value(self, df: pl.DataFrame):
        def udf(param_value):
            return (
                param_value.replace("\\", "\\\\")
                .replace("|", "\\|")
                .replace('"', '\\"')
                .replace("{", "\\{")
                .replace(":", "\\:")
                .replace("}", "\\}")
            )

        return df.with_columns(pl.col("PARAM_VALUE").map_elements(udf, return_dtype=pl.String))

    def transform_ms_serde_info(self, ms_serdes, ms_serde_params):
        escaped_serde_params = self.transform_param_value(ms_serde_params)
        serde_with_params = self.join_with_params(df=ms_serdes, df_params=escaped_serde_params, id_col="SERDE_ID")
        serde_renamed = serde_with_params.rename({"NAME": "name", "SLIB": "serializationLibrary"})
        return serde_renamed.select("SERDE_ID", "name", "serializationLibrary", "parameters")

    def transform_storage_descriptors(
        self,
        ms_sds,
        ms_sd_params,
        ms_columns,
        ms_bucketing_cols,
        ms_serdes,
        ms_serde_params,
        ms_skewed_col_names,
        ms_skewed_string_list_values,
        ms_skewed_col_value_loc_map,
        ms_sort_cols,
    ):
        bucket_columns = self.transform_ms_bucketing_cols(ms_bucketing_cols)
        columns = self.transform_ms_columns(ms_columns)
        parameters = self.transform_params(params_df=ms_sd_params, id_col="SD_ID")
        serde_info = self.transform_ms_serde_info(ms_serdes=ms_serdes, ms_serde_params=ms_serde_params)
        skewed_info = self.transform_skewed_info(
            ms_skewed_col_names=ms_skewed_col_names,
            ms_skewed_string_list_values=ms_skewed_string_list_values,
            ms_skewed_col_value_loc_map=ms_skewed_col_value_loc_map,
        )
        sort_columns = self.transform_ms_sort_cols(ms_sort_cols)

        storage_descriptors_joined = (
            ms_sds.join(other=bucket_columns, on="SD_ID", how="left")
            .join(other=columns, on="CD_ID", how="left")
            .join(other=parameters, on="SD_ID", how="left")
            .custom_join.join_other_to_single_column(
                other=serde_info, on="SERDE_ID", how="left", new_column_name="serdeInfo"
            )
            .custom_join.join_other_to_single_column(
                other=skewed_info, on="SD_ID", how="left", new_column_name="skewedInfo"
            )
            .join(other=sort_columns, on="SD_ID", how="left")
        )

        storage_descriptors_s3_location_fixed = HiveMetastoreTransformer.s3a_or_s3n_to_s3_in_location(
            storage_descriptors_joined, "LOCATION"
        )
        storage_descriptors_renamed = storage_descriptors_s3_location_fixed.rename(
            {
                "INPUT_FORMAT": "inputFormat",
                "OUTPUT_FORMAT": "outputFormat",
                "LOCATION": "location",
                "NUM_BUCKETS": "numberOfBuckets",
                "IS_COMPRESSED": "compressed",
                "IS_STOREDASSUBDIRECTORIES": "storedAsSubDirectories",
            }
        )

        storage_descriptors_with_empty_sorted_cols = storage_descriptors_renamed.with_columns(
            pl.col("sortColumns").fill_null(value=[])
        )

        return storage_descriptors_with_empty_sorted_cols.drop(["SERDE_ID", "CD_ID"])

    def transform_tables(self, db_tbl_joined, ms_table_params, storage_descriptors, ms_partition_keys):
        tbls_date_transformed = self.transform_timestamp_cols(
            db_tbl_joined, date_cols_map={"CREATE_TIME": "createTime", "LAST_ACCESS_TIME": "lastAccessTime"}
        )
        tbls_with_params = self.join_with_params(
            df=tbls_date_transformed, df_params=self.transform_param_value(ms_table_params), id_col="TBL_ID"
        )
        partition_keys = self.transform_ms_partition_keys(ms_partition_keys)

        tbls_joined = tbls_with_params.join(
            other=partition_keys, on="TBL_ID", how="left"
        ).custom_join.join_other_to_single_column(
            other=storage_descriptors, on="SD_ID", how="left", new_column_name="storageDescriptor"
        )

        tbls_renamed = tbls_joined.rename(
            {
                "NAME": "databaseName",
                "TBL_NAME": "name",
                "TBL_TYPE": "tableType",
                "OWNER": "owner",
                "RETENTION": "retention",
                "VIEW_EXPANDED_TEXT": "viewExpandedText",
                "VIEW_ORIGINAL_TEXT": "viewOriginalText",
            },
        )

        tbls_dropped_cols = tbls_renamed.drop(
            ["DB_ID", "TBL_ID", "SD_ID", "OWNER_TYPE", "CREATE_TIME", "LAST_ACCESS_TIME", "IS_REWRITE_ENABLED"]
        )
        tbls_drop_invalid = tbls_dropped_cols.drop_nulls(subset=["name", "databaseName"])
        tbls_with_empty_part_cols = tbls_drop_invalid.with_columns(pl.col("partitionKeys").fill_null(value=[]))

        return tbls_with_empty_part_cols.select(
            pl.struct(pl.all()).alias("item"),
        ).with_columns(type=pl.lit("table"))

    def transform_partitions(
        self, db_tbl_joined, ms_partitions, storage_descriptors, ms_partition_params, ms_partition_key_vals
    ):
        parts_date_transformed = self.transform_timestamp_cols(
            df=ms_partitions, date_cols_map={"CREATE_TIME": "creationTime", "LAST_ACCESS_TIME": "lastAccessTime"}
        )
        db_tbl_names = db_tbl_joined.select(
            db_tbl_joined["NAME"].alias("namespaceName"),
            db_tbl_joined["TBL_NAME"].alias("tableName"),
            "DB_ID",
            "TBL_ID",
        )
        parts_with_db_tbl = parts_date_transformed.join(other=db_tbl_names, on="TBL_ID", how="inner")
        parts_with_params = self.join_with_params(
            df=parts_with_db_tbl, df_params=self.transform_param_value(ms_partition_params), id_col="PART_ID"
        )
        parts_with_sd = parts_with_params.custom_join.join_other_to_single_column(
            other=storage_descriptors, on="SD_ID", how="left", new_column_name="storageDescriptor"
        )
        part_values = self.transform_ms_partition_key_vals(ms_partition_key_vals)
        parts_with_values = parts_with_sd.join(other=part_values, on="PART_ID", how="left")
        parts_dropped_cols = parts_with_values.drop(
            ["DB_ID", "TBL_ID", "PART_ID", "SD_ID", "PART_NAME", "CREATE_TIME", "LAST_ACCESS_TIME"]
        )
        parts_drop_invalid = parts_dropped_cols.drop_nulls(subset=["values", "namespaceName", "tableName"])
        return parts_drop_invalid.select(
            parts_drop_invalid["namespaceName"].alias("database"),
            parts_drop_invalid["tableName"].alias("table"),
            pl.struct(parts_drop_invalid.columns).alias("item"),
        ).with_columns(type=pl.lit("partition"))

    def transform_databases(self, ms_dbs, ms_database_params):
        dbs_with_params = self.join_with_params(df=ms_dbs, df_params=ms_database_params, id_col="DB_ID")
        dbs_with_params = HiveMetastoreTransformer.s3a_or_s3n_to_s3_in_location(dbs_with_params, "DB_LOCATION_URI")
        dbs_renamed = dbs_with_params.rename(
            {"NAME": "name", "DESC": "description", "DB_LOCATION_URI": "locationUri"},
        )
        dbs_dropped_cols = dbs_renamed.drop(["DB_ID", "OWNER_NAME", "OWNER_TYPE"])
        dbs_drop_invalid = dbs_dropped_cols.drop_nulls(subset=["name"])
        return dbs_drop_invalid.select(pl.struct(dbs_dropped_cols.columns).alias("item")).with_columns(
            type=pl.lit("database")
        )

    def transform(self, hive_metastore) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        dbs_prefixed = HiveMetastoreTransformer.add_prefix_to_column(hive_metastore.ms_dbs, "NAME", self.db_prefix)
        tbls_prefixed = HiveMetastoreTransformer.add_prefix_to_column(
            hive_metastore.ms_tbls, "TBL_NAME", self.table_prefix
        )

        databases = self.transform_databases(ms_dbs=dbs_prefixed, ms_database_params=hive_metastore.ms_database_params)

        db_tbl_joined = HiveMetastoreTransformer.join_dbs_tbls(ms_dbs=dbs_prefixed, ms_tbls=tbls_prefixed)

        storage_descriptors = self.transform_storage_descriptors(
            ms_sds=hive_metastore.ms_sds,
            ms_sd_params=hive_metastore.ms_sd_params,
            ms_columns=hive_metastore.ms_columns,
            ms_bucketing_cols=hive_metastore.ms_bucketing_cols,
            ms_serdes=hive_metastore.ms_serdes,
            ms_serde_params=hive_metastore.ms_serde_params,
            ms_skewed_col_names=hive_metastore.ms_skewed_col_names,
            ms_skewed_string_list_values=hive_metastore.ms_skewed_string_list_values,
            ms_skewed_col_value_loc_map=hive_metastore.ms_skewed_col_value_loc_map,
            ms_sort_cols=hive_metastore.ms_sort_cols,
        )

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

    def __init__(self, sc, sql_context, db_prefix, table_prefix):
        self.sc = sc
        self.sql_context = sql_context
        self.db_prefix = db_prefix
        self.table_prefix = table_prefix


class HiveMetastore:
    """
    The class to extract data from Hive Metastore into DataFrames and write Dataframes to
    Hive Metastore. Each field represents a single Hive Metastore table.
    As a convention, the fields are prefixed by ms_ to show that it is raw Hive Metastore data
    """

    def read_table(self, connection, table_name=None):
        """
        Load a JDBC table into Pandas Dataframe
        """
        return pl.read_database(f'select * from "{table_name}"', connection)

    def write_table(self, connection, table_name=None, df: pl.DataFrame = None):
        """
        Write from Pandas Dataframe into a JDBC table
        """
        logging.info(f"hive_metastore_migration:write_table. URL: {connection.adbc_get_info()}, table: {table_name}")
        return df.write_database(
            table_name=table_name,
            connection=connection,
            if_table_exists="append",
        )

    def extract_metastore(self):
        self.ms_dbs = self.read_table(connection=self.connection, table_name="DBS")
        self.ms_database_params = self.read_table(connection=self.connection, table_name="DATABASE_PARAMS")
        self.ms_tbls = self.read_table(connection=self.connection, table_name="TBLS")
        self.ms_table_params = self.read_table(connection=self.connection, table_name="TABLE_PARAMS")
        self.ms_columns = self.read_table(connection=self.connection, table_name="COLUMNS_V2")
        self.ms_bucketing_cols = self.read_table(connection=self.connection, table_name="BUCKETING_COLS")
        self.ms_sds = self.read_table(connection=self.connection, table_name="SDS")
        self.ms_sd_params = self.read_table(connection=self.connection, table_name="SD_PARAMS")
        self.ms_serdes = self.read_table(connection=self.connection, table_name="SERDES")
        self.ms_serde_params = self.read_table(connection=self.connection, table_name="SERDE_PARAMS")
        self.ms_skewed_col_names = self.read_table(connection=self.connection, table_name="SKEWED_COL_NAMES")
        self.ms_skewed_string_list = self.read_table(connection=self.connection, table_name="SKEWED_STRING_LIST")
        self.ms_skewed_string_list_values = self.read_table(
            connection=self.connection, table_name="SKEWED_STRING_LIST_VALUES"
        )
        self.ms_skewed_col_value_loc_map = self.read_table(
            connection=self.connection, table_name="SKEWED_COL_VALUE_LOC_MAP"
        )
        self.ms_sort_cols = self.read_table(connection=self.connection, table_name="SORT_COLS")
        self.ms_partitions = self.read_table(connection=self.connection, table_name="PARTITIONS")
        self.ms_partition_params = self.read_table(connection=self.connection, table_name="PARTITION_PARAMS")
        self.ms_partition_keys = self.read_table(connection=self.connection, table_name="PARTITION_KEYS")
        self.ms_partition_key_vals = self.read_table(connection=self.connection, table_name="PARTITION_KEY_VALS")

    # order of write matters here
    def export_to_metastore(self):
        self.write_table(connection=self.connection, table_name="DBS", df=self.ms_dbs)
        self.write_table(connection=self.connection, table_name="DATABASE_PARAMS", df=self.ms_database_params)
        self.write_table(connection=self.connection, table_name="CDS", df=self.ms_cds)
        self.write_table(connection=self.connection, table_name="SERDES", df=self.ms_serdes)
        self.write_table(connection=self.connection, table_name="SERDE_PARAMS", df=self.ms_serde_params)
        self.write_table(connection=self.connection, table_name="COLUMNS_V2", df=self.ms_columns)
        self.write_table(connection=self.connection, table_name="SDS", df=self.ms_sds)
        self.write_table(connection=self.connection, table_name="SD_PARAMS", df=self.ms_sd_params)
        self.write_table(connection=self.connection, table_name="SKEWED_COL_NAMES", df=self.ms_skewed_col_names)
        self.write_table(connection=self.connection, table_name="SKEWED_STRING_LIST", df=self.ms_skewed_string_list)
        self.write_table(
            connection=self.connection, table_name="SKEWED_STRING_LIST_VALUES", df=self.ms_skewed_string_list_values
        )
        self.write_table(
            connection=self.connection, table_name="SKEWED_COL_VALUE_LOC_MAP", df=self.ms_skewed_col_value_loc_map
        )
        self.write_table(connection=self.connection, table_name="SORT_COLS", df=self.ms_sort_cols)
        self.write_table(connection=self.connection, table_name="TBLS", df=self.ms_tbls)
        self.write_table(connection=self.connection, table_name="TABLE_PARAMS", df=self.ms_table_params)
        self.write_table(connection=self.connection, table_name="PARTITION_KEYS", df=self.ms_partition_keys)
        self.write_table(connection=self.connection, table_name="PARTITIONS", df=self.ms_partitions)
        self.write_table(connection=self.connection, table_name="PARTITION_PARAMS", df=self.ms_partition_params)
        self.write_table(connection=self.connection, table_name="PARTITION_KEY_VALS", df=self.ms_partition_key_vals)

    def __init__(self, connection, sql_context):
        self.connection = connection
        self.sql_context = sql_context
        self.ms_dbs = None
        self.ms_database_params = None
        self.ms_tbls = None
        self.ms_table_params = None
        self.ms_columns = None
        self.ms_bucketing_cols = None
        self.ms_sds = None
        self.ms_sd_params = None
        self.ms_serdes = None
        self.ms_serde_params = None
        self.ms_skewed_col_names = None
        self.ms_skewed_string_list = None
        self.ms_skewed_string_list_values = None
        self.ms_skewed_col_value_loc_map = None
        self.ms_sort_cols = None
        self.ms_partitions = None
        self.ms_partition_params = None
        self.ms_partition_keys = None
        self.ms_partition_key_vals = None


def get_output_dir(output_dir_parent):
    if not output_dir_parent:
        raise ValueError("output path cannot be empty")
    if output_dir_parent[-1] != "/":
        output_dir_parent = f"{output_dir_parent}/"
    return f'{output_dir_parent}{strftime("%Y-%m-%d-%H-%M-%S", localtime())}/'


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
        help="Hive metastore JDBC url, example: jdbc:mysql://metastore.abcd.us-east-1.rds.amazonaws.com:3306",
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


# def get_spark_env():
#     conf = SparkConf()
#     sc = SparkContext(conf=conf)
#     sc.setLogLevel("ERROR")
#     sql_context = SQLContext(sc)
#     return (conf, sc, sql_context)


def etl_from_metastore(sc, sql_context, db_prefix, table_prefix, hive_metastore, options):
    # extract
    hive_metastore.extract_metastore()

    # transform
    (databases, tables, partitions) = HiveMetastoreTransformer(sc, sql_context, db_prefix, table_prefix).transform(
        hive_metastore
    )

    # load
    output_path = get_output_dir(options["output_path"])

    databases.write.format("json").mode("overwrite").save(f"{output_path}databases")
    tables.write.format("json").mode("overwrite").save(f"{output_path}tables")
    partitions.write.format("json").mode("overwrite").save(f"{output_path}partitions")


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

    connection = {"url": options["jdbc_url"], "user": options["jdbc_username"], "password": options["jdbc_password"]}
    db_prefix = options.get("database_prefix") or ""
    table_prefix = options.get("table_prefix") or ""

    # spark env
    # (conf, sc, sql_context) = get_spark_env()
    (sc, sql_context) = None, None
    # extract
    hive_metastore = HiveMetastore(connection, sql_context)

    if options["mode"] == FROM_METASTORE:
        etl_from_metastore(sc, sql_context, db_prefix, table_prefix, hive_metastore, options)


def replace_nested_key(data, key, value):
    if isinstance(data, dict):
        return {k: value(v or "{}") if k == key else replace_nested_key(v, key, value) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace_nested_key(v, key, value) for v in data]
    else:
        return data


def format_json(filename):
    with open(filename) as f:
        d = json.load(f)
    d = replace_nested_key(d, "parameters", json.loads)
    with open(filename, "w") as f:
        json.dump(d, f, indent=4)


if __name__ == "__main__":
    # main()
    uri = "postgres://postgres:postgres@localhost:15432/postgres"
    import adbc_driver_postgresql.dbapi

    connection = adbc_driver_postgresql.dbapi.connect(uri)
    hm = HiveMetastore(connection, None)
    hm.extract_metastore()

    hmt = HiveMetastoreTransformer(None, None, "", "")
    databases, tables, partitions = hmt.transform(hm)
    databases.write_json("hm_databases.json")
    tables.write_json("hm_tables.json")
    partitions.write_json("hm_partitions.json")

    format_json("hm_databases.json")
    format_json("hm_tables.json")
    format_json("hm_partitions.json")

    """
from masu.management.commands.hive_metastore_migration import HiveMetastoreTransformer
from masu.management.commands.hive_metastore_migration import HiveMetastore
import adbc_driver_postgresql.dbapi
uri = "postgres://postgres:postgres@localhost:15432/postgres"
connection = adbc_driver_postgresql.dbapi.connect(uri)
hm = HiveMetastore(connection, None)
hm.extract_metastore()
hmt = HiveMetastoreTransformer(None, None, "", "")
databases, tables, partitions = hmt.transform(hm)
databases.write_json('hm_databases.json')
tables.write_json('hm_tables.json')
partitions.write_json('hm_partitions.json')
    """
