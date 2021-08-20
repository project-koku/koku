
CREATE TABLE {{schema_name | sqlsafe}}."partitioned_tables" (
    "id" integer NOT NULL,
    "schema_name" "text" NOT NULL,
    "table_name" "text" NOT NULL,
    "partition_of_table_name" "text" NOT NULL,
    "partition_type" "text" NOT NULL,
    "partition_col" "text" NOT NULL,
    "partition_parameters" "jsonb" NOT NULL,
    "active" boolean DEFAULT true NOT NULL,
    "subpartition_col" "text",
    "subpartition_type" "text"
);

ALTER TABLE {{schema_name | sqlsafe}}."partitioned_tables" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."partitioned_tables_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."partitioned_tables_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."partitioned_tables_id_seq" OWNED BY {{schema_name | sqlsafe}}."partitioned_tables"."id";

CREATE TABLE {{schema_name | sqlsafe}}."presto_delete_wrapper_log" (
    "id" "uuid" DEFAULT "public"."uuid_generate_v4"() NOT NULL,
    "action_ts" timestamp with time zone DEFAULT "now"() NOT NULL,
    "table_name" "text" NOT NULL,
    "where_clause" "text" NOT NULL,
    "result_rows" bigint
);

ALTER TABLE {{schema_name | sqlsafe}}."presto_delete_wrapper_log" OWNER TO current_user;

COMMENT ON TABLE {{schema_name | sqlsafe}}."presto_delete_wrapper_log" IS 'Table to log and execute delete statements initiated from Presto';

COMMENT ON COLUMN {{schema_name | sqlsafe}}."presto_delete_wrapper_log"."table_name" IS 'Target table from which to delete';

COMMENT ON COLUMN {{schema_name | sqlsafe}}."presto_delete_wrapper_log"."where_clause" IS 'Where clause for delete action';

COMMENT ON COLUMN {{schema_name | sqlsafe}}."presto_delete_wrapper_log"."result_rows" IS 'Number of records affected by the delete action';

CREATE TABLE {{schema_name | sqlsafe}}."presto_pk_delete_wrapper_log" (
    "transaction_id" "text" NOT NULL,
    "action_ts" timestamp with time zone DEFAULT "now"() NOT NULL,
    "table_name" "text" NOT NULL,
    "pk_column" "text" NOT NULL,
    "pk_value" "text" NOT NULL,
    "pk_value_cast" "text" NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."presto_pk_delete_wrapper_log" OWNER TO current_user;

COMMENT ON TABLE {{schema_name | sqlsafe}}."presto_pk_delete_wrapper_log" IS 'Table to hold primary key values to use when bulk-deleting using the presto delete wrapper log';

COMMENT ON COLUMN {{schema_name | sqlsafe}}."presto_pk_delete_wrapper_log"."transaction_id" IS 'Presto transaction identifier';

COMMENT ON COLUMN {{schema_name | sqlsafe}}."presto_pk_delete_wrapper_log"."table_name" IS 'Target table in which the primary key values reside';

COMMENT ON COLUMN {{schema_name | sqlsafe}}."presto_pk_delete_wrapper_log"."pk_column" IS 'Name of the primary key column for the target table';

COMMENT ON COLUMN {{schema_name | sqlsafe}}."presto_pk_delete_wrapper_log"."pk_value" IS 'String representation of the primary key value';

COMMENT ON COLUMN {{schema_name | sqlsafe}}."presto_pk_delete_wrapper_log"."pk_value_cast" IS 'Data type to which the string primary key value should be cast';

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" (
    "usage_start" "date" NOT NULL,
    "usage_end" "date",
    "usage_account_id" character varying(50) NOT NULL,
    "product_code" character varying(50) NOT NULL,
    "product_family" character varying(150),
    "availability_zone" character varying(50),
    "region" character varying(50),
    "instance_type" character varying(50),
    "unit" character varying(63),
    "resource_ids" "text"[],
    "resource_count" integer,
    "usage_amount" numeric(24,9),
    "normalization_factor" double precision,
    "normalized_usage_amount" double precision,
    "currency_code" character varying(10) NOT NULL,
    "unblended_rate" numeric(24,9),
    "unblended_cost" numeric(24,9),
    "markup_cost" numeric(24,9),
    "blended_rate" numeric(24,9),
    "blended_cost" numeric(24,9),
    "public_on_demand_cost" numeric(24,9),
    "public_on_demand_rate" numeric(24,9),
    "tax_type" "text",
    "tags" "jsonb",
    "source_uuid" "uuid",
    "account_alias_id" integer,
    "cost_entry_bill_id" integer,
    "organizational_unit_id" integer,
    "uuid" "uuid" NOT NULL
)
PARTITION BY RANGE ("usage_start");

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_compute_summary" AS
 SELECT "row_number"() OVER (ORDER BY "c"."usage_start", "c"."instance_type", "c"."source_uuid") AS "id",
    "c"."usage_start",
    "c"."usage_start" AS "usage_end",
    "c"."instance_type",
    "r"."resource_ids",
    "cardinality"("r"."resource_ids") AS "resource_count",
    "c"."usage_amount",
    "c"."unit",
    "c"."unblended_cost",
    "c"."markup_cost",
    "c"."currency_code",
    "c"."source_uuid"
   FROM (( SELECT "reporting_awscostentrylineitem_daily_summary"."usage_start",
            "reporting_awscostentrylineitem_daily_summary"."instance_type",
            "sum"("reporting_awscostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
            "max"(("reporting_awscostentrylineitem_daily_summary"."unit")::"text") AS "unit",
            "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
            "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
            "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
            "reporting_awscostentrylineitem_daily_summary"."source_uuid"
           FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
          WHERE (("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_awscostentrylineitem_daily_summary"."instance_type" IS NOT NULL))
          GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."instance_type", "reporting_awscostentrylineitem_daily_summary"."source_uuid") "c"
     JOIN ( SELECT "x"."usage_start",
            "x"."instance_type",
            "array_agg"(DISTINCT "x"."resource_id" ORDER BY "x"."resource_id") AS "resource_ids"
           FROM ( SELECT "reporting_awscostentrylineitem_daily_summary"."usage_start",
                    "reporting_awscostentrylineitem_daily_summary"."instance_type",
                    "unnest"("reporting_awscostentrylineitem_daily_summary"."resource_ids") AS "resource_id"
                   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
                  WHERE (("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_awscostentrylineitem_daily_summary"."instance_type" IS NOT NULL))) "x"
          GROUP BY "x"."usage_start", "x"."instance_type") "r" ON ((("c"."usage_start" = "r"."usage_start") AND (("c"."instance_type")::"text" = ("r"."instance_type")::"text"))))
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_compute_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_account" AS
 SELECT "row_number"() OVER (ORDER BY "c"."usage_start", "c"."usage_account_id", "c"."instance_type") AS "id",
    "c"."usage_start",
    "c"."usage_start" AS "usage_end",
    "c"."usage_account_id",
    "c"."account_alias_id",
    "c"."organizational_unit_id",
    "c"."instance_type",
    "r"."resource_ids",
    "cardinality"("r"."resource_ids") AS "resource_count",
    "c"."usage_amount",
    "c"."unit",
    "c"."unblended_cost",
    "c"."markup_cost",
    "c"."currency_code",
    "c"."source_uuid"
   FROM (( SELECT "reporting_awscostentrylineitem_daily_summary"."usage_start",
            "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
            "max"("reporting_awscostentrylineitem_daily_summary"."account_alias_id") AS "account_alias_id",
            "max"("reporting_awscostentrylineitem_daily_summary"."organizational_unit_id") AS "organizational_unit_id",
            "reporting_awscostentrylineitem_daily_summary"."instance_type",
            "sum"("reporting_awscostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
            "max"(("reporting_awscostentrylineitem_daily_summary"."unit")::"text") AS "unit",
            "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
            "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
            "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
            ("max"(("reporting_awscostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
           FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
          WHERE (("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_awscostentrylineitem_daily_summary"."instance_type" IS NOT NULL))
          GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."instance_type") "c"
     JOIN ( SELECT "x"."usage_start",
            "x"."usage_account_id",
            "max"("x"."account_alias_id") AS "account_alias_id",
            "x"."instance_type",
            "array_agg"(DISTINCT "x"."resource_id" ORDER BY "x"."resource_id") AS "resource_ids"
           FROM ( SELECT "reporting_awscostentrylineitem_daily_summary"."usage_start",
                    "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
                    "reporting_awscostentrylineitem_daily_summary"."account_alias_id",
                    "reporting_awscostentrylineitem_daily_summary"."instance_type",
                    "unnest"("reporting_awscostentrylineitem_daily_summary"."resource_ids") AS "resource_id"
                   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
                  WHERE (("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_awscostentrylineitem_daily_summary"."instance_type" IS NOT NULL))) "x"
          GROUP BY "x"."usage_start", "x"."usage_account_id", "x"."instance_type") "r" ON ((("c"."usage_start" = "r"."usage_start") AND (("c"."instance_type")::"text" = ("r"."instance_type")::"text") AND (("c"."usage_account_id")::"text" = ("r"."usage_account_id")::"text"))))
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_account" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_region" AS
 SELECT "row_number"() OVER (ORDER BY "c"."usage_start", "c"."usage_account_id", "c"."region", "c"."availability_zone", "c"."instance_type") AS "id",
    "c"."usage_start",
    "c"."usage_start" AS "usage_end",
    "c"."usage_account_id",
    "c"."account_alias_id",
    "c"."organizational_unit_id",
    "c"."region",
    "c"."availability_zone",
    "c"."instance_type",
    "r"."resource_ids",
    "cardinality"("r"."resource_ids") AS "resource_count",
    "c"."usage_amount",
    "c"."unit",
    "c"."unblended_cost",
    "c"."markup_cost",
    "c"."currency_code",
    "c"."source_uuid"
   FROM (( SELECT "reporting_awscostentrylineitem_daily_summary"."usage_start",
            "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
            "max"("reporting_awscostentrylineitem_daily_summary"."account_alias_id") AS "account_alias_id",
            "max"("reporting_awscostentrylineitem_daily_summary"."organizational_unit_id") AS "organizational_unit_id",
            "reporting_awscostentrylineitem_daily_summary"."region",
            "reporting_awscostentrylineitem_daily_summary"."availability_zone",
            "reporting_awscostentrylineitem_daily_summary"."instance_type",
            "sum"("reporting_awscostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
            "max"(("reporting_awscostentrylineitem_daily_summary"."unit")::"text") AS "unit",
            "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
            "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
            "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
            ("max"(("reporting_awscostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
           FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
          WHERE (("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date") AND ("reporting_awscostentrylineitem_daily_summary"."instance_type" IS NOT NULL))
          GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."region", "reporting_awscostentrylineitem_daily_summary"."availability_zone", "reporting_awscostentrylineitem_daily_summary"."instance_type") "c"
     JOIN ( SELECT "x"."usage_start",
            "x"."usage_account_id",
            "max"("x"."account_alias_id") AS "account_alias_id",
            "x"."region",
            "x"."availability_zone",
            "x"."instance_type",
            "array_agg"(DISTINCT "x"."resource_id" ORDER BY "x"."resource_id") AS "resource_ids"
           FROM ( SELECT "reporting_awscostentrylineitem_daily_summary"."usage_start",
                    "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
                    "reporting_awscostentrylineitem_daily_summary"."account_alias_id",
                    "reporting_awscostentrylineitem_daily_summary"."region",
                    "reporting_awscostentrylineitem_daily_summary"."availability_zone",
                    "reporting_awscostentrylineitem_daily_summary"."instance_type",
                    "unnest"("reporting_awscostentrylineitem_daily_summary"."resource_ids") AS "resource_id"
                   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
                  WHERE (("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_awscostentrylineitem_daily_summary"."instance_type" IS NOT NULL))) "x"
          GROUP BY "x"."usage_start", "x"."usage_account_id", "x"."region", "x"."availability_zone", "x"."instance_type") "r" ON ((("c"."usage_start" = "r"."usage_start") AND (("c"."region")::"text" = ("r"."region")::"text") AND (("c"."availability_zone")::"text" = ("r"."availability_zone")::"text") AND (("c"."instance_type")::"text" = ("r"."instance_type")::"text") AND (("c"."usage_account_id")::"text" = ("r"."usage_account_id")::"text"))))
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_region" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_service" AS
 SELECT "row_number"() OVER (ORDER BY "c"."usage_start", "c"."usage_account_id", "c"."product_code", "c"."product_family", "c"."instance_type") AS "id",
    "c"."usage_start",
    "c"."usage_start" AS "usage_end",
    "c"."usage_account_id",
    "c"."account_alias_id",
    "c"."organizational_unit_id",
    "c"."product_code",
    "c"."product_family",
    "c"."instance_type",
    "r"."resource_ids",
    "cardinality"("r"."resource_ids") AS "resource_count",
    "c"."usage_amount",
    "c"."unit",
    "c"."unblended_cost",
    "c"."markup_cost",
    "c"."currency_code",
    "c"."source_uuid"
   FROM (( SELECT "reporting_awscostentrylineitem_daily_summary"."usage_start",
            "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
            "max"("reporting_awscostentrylineitem_daily_summary"."account_alias_id") AS "account_alias_id",
            "max"("reporting_awscostentrylineitem_daily_summary"."organizational_unit_id") AS "organizational_unit_id",
            "reporting_awscostentrylineitem_daily_summary"."product_code",
            "reporting_awscostentrylineitem_daily_summary"."product_family",
            "reporting_awscostentrylineitem_daily_summary"."instance_type",
            "sum"("reporting_awscostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
            "max"(("reporting_awscostentrylineitem_daily_summary"."unit")::"text") AS "unit",
            "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
            "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
            "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
            ("max"(("reporting_awscostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
           FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
          WHERE (("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_awscostentrylineitem_daily_summary"."instance_type" IS NOT NULL))
          GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."product_code", "reporting_awscostentrylineitem_daily_summary"."product_family", "reporting_awscostentrylineitem_daily_summary"."instance_type") "c"
     JOIN ( SELECT "x"."usage_start",
            "x"."usage_account_id",
            "max"("x"."account_alias_id") AS "account_alias_id",
            "x"."product_code",
            "x"."product_family",
            "x"."instance_type",
            "array_agg"(DISTINCT "x"."resource_id" ORDER BY "x"."resource_id") AS "resource_ids"
           FROM ( SELECT "reporting_awscostentrylineitem_daily_summary"."usage_start",
                    "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
                    "reporting_awscostentrylineitem_daily_summary"."account_alias_id",
                    "reporting_awscostentrylineitem_daily_summary"."product_code",
                    "reporting_awscostentrylineitem_daily_summary"."product_family",
                    "reporting_awscostentrylineitem_daily_summary"."instance_type",
                    "unnest"("reporting_awscostentrylineitem_daily_summary"."resource_ids") AS "resource_id"
                   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
                  WHERE (("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_awscostentrylineitem_daily_summary"."instance_type" IS NOT NULL))) "x"
          GROUP BY "x"."usage_start", "x"."usage_account_id", "x"."product_code", "x"."product_family", "x"."instance_type") "r" ON ((("c"."usage_start" = "r"."usage_start") AND (("c"."product_code")::"text" = ("r"."product_code")::"text") AND (("c"."product_family")::"text" = ("r"."product_family")::"text") AND (("c"."instance_type")::"text" = ("r"."instance_type")::"text") AND (("c"."usage_account_id")::"text" = ("r"."usage_account_id")::"text"))))
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_service" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_cost_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."source_uuid") AS "id",
    "reporting_awscostentrylineitem_daily_summary"."usage_start",
    "reporting_awscostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    "reporting_awscostentrylineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
  WHERE ("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."source_uuid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_cost_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_account" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id") AS "id",
    "reporting_awscostentrylineitem_daily_summary"."usage_start",
    "reporting_awscostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."organizational_unit_id") AS "organizational_unit_id",
    "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_awscostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
  WHERE ("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_account" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_region" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."region", "reporting_awscostentrylineitem_daily_summary"."availability_zone") AS "id",
    "reporting_awscostentrylineitem_daily_summary"."usage_start",
    "reporting_awscostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."organizational_unit_id") AS "organizational_unit_id",
    "reporting_awscostentrylineitem_daily_summary"."region",
    "reporting_awscostentrylineitem_daily_summary"."availability_zone",
    "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_awscostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
  WHERE ("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."region", "reporting_awscostentrylineitem_daily_summary"."availability_zone"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_region" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_service" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."product_code", "reporting_awscostentrylineitem_daily_summary"."product_family") AS "id",
    "reporting_awscostentrylineitem_daily_summary"."usage_start",
    "reporting_awscostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."organizational_unit_id") AS "organizational_unit_id",
    "reporting_awscostentrylineitem_daily_summary"."product_code",
    "reporting_awscostentrylineitem_daily_summary"."product_family",
    "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_awscostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
  WHERE ("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."product_code", "reporting_awscostentrylineitem_daily_summary"."product_family"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_service" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_database_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."product_code") AS "id",
    "reporting_awscostentrylineitem_daily_summary"."usage_start",
    "reporting_awscostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."organizational_unit_id") AS "organizational_unit_id",
    "reporting_awscostentrylineitem_daily_summary"."product_code",
    "sum"("reporting_awscostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_awscostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_awscostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
  WHERE ((("reporting_awscostentrylineitem_daily_summary"."product_code")::"text" = ANY ((ARRAY['AmazonRDS'::character varying, 'AmazonDynamoDB'::character varying, 'AmazonElastiCache'::character varying, 'AmazonNeptune'::character varying, 'AmazonRedshift'::character varying, 'AmazonDocumentDB'::character varying])::"text"[])) AND ("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date"))
  GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."product_code"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_database_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_network_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."product_code") AS "id",
    "reporting_awscostentrylineitem_daily_summary"."usage_start",
    "reporting_awscostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."organizational_unit_id") AS "organizational_unit_id",
    "reporting_awscostentrylineitem_daily_summary"."product_code",
    "sum"("reporting_awscostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_awscostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_awscostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
  WHERE ((("reporting_awscostentrylineitem_daily_summary"."product_code")::"text" = ANY ((ARRAY['AmazonVPC'::character varying, 'AmazonCloudFront'::character varying, 'AmazonRoute53'::character varying, 'AmazonAPIGateway'::character varying])::"text"[])) AND ("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date"))
  GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."product_code"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_network_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_storage_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."source_uuid", "reporting_awscostentrylineitem_daily_summary"."product_family") AS "id",
    "reporting_awscostentrylineitem_daily_summary"."usage_start",
    "reporting_awscostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_awscostentrylineitem_daily_summary"."product_family",
    "sum"("reporting_awscostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_awscostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    "reporting_awscostentrylineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
  WHERE ((("reporting_awscostentrylineitem_daily_summary"."product_family")::"text" ~~ '%Storage%'::"text") AND (("reporting_awscostentrylineitem_daily_summary"."unit")::"text" = 'GB-Mo'::"text") AND ("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date"))
  GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."source_uuid", "reporting_awscostentrylineitem_daily_summary"."product_family"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_storage_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_account" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."product_family") AS "id",
    "reporting_awscostentrylineitem_daily_summary"."usage_start",
    "reporting_awscostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."organizational_unit_id") AS "organizational_unit_id",
    "reporting_awscostentrylineitem_daily_summary"."product_family",
    "sum"("reporting_awscostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_awscostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_awscostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
  WHERE ((("reporting_awscostentrylineitem_daily_summary"."product_family")::"text" ~~ '%Storage%'::"text") AND (("reporting_awscostentrylineitem_daily_summary"."unit")::"text" = 'GB-Mo'::"text") AND ("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date"))
  GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."product_family"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_account" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_region" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."region", "reporting_awscostentrylineitem_daily_summary"."availability_zone", "reporting_awscostentrylineitem_daily_summary"."product_family") AS "id",
    "reporting_awscostentrylineitem_daily_summary"."usage_start",
    "reporting_awscostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."organizational_unit_id") AS "organizational_unit_id",
    "reporting_awscostentrylineitem_daily_summary"."region",
    "reporting_awscostentrylineitem_daily_summary"."availability_zone",
    "reporting_awscostentrylineitem_daily_summary"."product_family",
    "sum"("reporting_awscostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_awscostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_awscostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
  WHERE ((("reporting_awscostentrylineitem_daily_summary"."product_family")::"text" ~~ '%Storage%'::"text") AND (("reporting_awscostentrylineitem_daily_summary"."unit")::"text" = 'GB-Mo'::"text") AND ("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date"))
  GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."region", "reporting_awscostentrylineitem_daily_summary"."availability_zone", "reporting_awscostentrylineitem_daily_summary"."product_family"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_region" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_service" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."product_code", "reporting_awscostentrylineitem_daily_summary"."product_family") AS "id",
    "reporting_awscostentrylineitem_daily_summary"."usage_start",
    "reporting_awscostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_awscostentrylineitem_daily_summary"."usage_account_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "max"("reporting_awscostentrylineitem_daily_summary"."organizational_unit_id") AS "organizational_unit_id",
    "reporting_awscostentrylineitem_daily_summary"."product_code",
    "reporting_awscostentrylineitem_daily_summary"."product_family",
    "sum"("reporting_awscostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_awscostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_awscostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_awscostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_awscostentrylineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_awscostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
  WHERE ((("reporting_awscostentrylineitem_daily_summary"."product_family")::"text" ~~ '%Storage%'::"text") AND (("reporting_awscostentrylineitem_daily_summary"."unit")::"text" = 'GB-Mo'::"text") AND ("reporting_awscostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date"))
  GROUP BY "reporting_awscostentrylineitem_daily_summary"."usage_start", "reporting_awscostentrylineitem_daily_summary"."usage_account_id", "reporting_awscostentrylineitem_daily_summary"."product_code", "reporting_awscostentrylineitem_daily_summary"."product_family"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_service" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awsaccountalias" (
    "id" integer NOT NULL,
    "account_id" character varying(50) NOT NULL,
    "account_alias" character varying(63)
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awsaccountalias" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_awsaccountalias_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awsaccountalias_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_awsaccountalias_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_awsaccountalias"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awscostentry" (
    "id" integer NOT NULL,
    "interval_start" timestamp with time zone NOT NULL,
    "interval_end" timestamp with time zone NOT NULL,
    "bill_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentry" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentry_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentry_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentry_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_awscostentry"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awscostentrybill" (
    "id" integer NOT NULL,
    "billing_resource" character varying(50) NOT NULL,
    "bill_type" character varying(50),
    "payer_account_id" character varying(50),
    "billing_period_start" timestamp with time zone NOT NULL,
    "billing_period_end" timestamp with time zone NOT NULL,
    "summary_data_creation_datetime" timestamp with time zone,
    "summary_data_updated_datetime" timestamp with time zone,
    "finalized_datetime" timestamp with time zone,
    "derived_cost_datetime" timestamp with time zone,
    "provider_id" "uuid" NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrybill" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentrybill_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrybill_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentrybill_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_awscostentrybill"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem" (
    "id" bigint NOT NULL,
    "tags" "jsonb",
    "invoice_id" character varying(63),
    "line_item_type" character varying(50) NOT NULL,
    "usage_account_id" character varying(50) NOT NULL,
    "usage_start" timestamp with time zone NOT NULL,
    "usage_end" timestamp with time zone NOT NULL,
    "product_code" character varying(50) NOT NULL,
    "usage_type" character varying(50),
    "operation" character varying(50),
    "availability_zone" character varying(50),
    "resource_id" character varying(256),
    "usage_amount" numeric(24,9),
    "normalization_factor" double precision,
    "normalized_usage_amount" numeric(24,9),
    "currency_code" character varying(10) NOT NULL,
    "unblended_rate" numeric(24,9),
    "unblended_cost" numeric(24,9),
    "blended_rate" numeric(24,9),
    "blended_cost" numeric(24,9),
    "public_on_demand_cost" numeric(24,9),
    "public_on_demand_rate" numeric(24,9),
    "reservation_amortized_upfront_fee" numeric(24,9),
    "reservation_amortized_upfront_cost_for_usage" numeric(24,9),
    "reservation_recurring_fee_for_usage" numeric(24,9),
    "reservation_unused_quantity" numeric(24,9),
    "reservation_unused_recurring_fee" numeric(24,9),
    "tax_type" "text",
    "cost_entry_id" integer NOT NULL,
    "cost_entry_bill_id" integer NOT NULL,
    "cost_entry_pricing_id" integer,
    "cost_entry_product_id" integer,
    "cost_entry_reservation_id" integer
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" (
    "id" bigint NOT NULL,
    "line_item_type" character varying(50) NOT NULL,
    "usage_account_id" character varying(50) NOT NULL,
    "usage_start" "date" NOT NULL,
    "usage_end" "date",
    "product_code" character varying(50) NOT NULL,
    "usage_type" character varying(50),
    "operation" character varying(50),
    "availability_zone" character varying(50),
    "resource_id" character varying(256),
    "usage_amount" numeric(24,9),
    "normalization_factor" double precision,
    "normalized_usage_amount" double precision,
    "currency_code" character varying(10) NOT NULL,
    "unblended_rate" numeric(24,9),
    "unblended_cost" numeric(24,9),
    "blended_rate" numeric(24,9),
    "blended_cost" numeric(24,9),
    "public_on_demand_cost" numeric(24,9),
    "public_on_demand_rate" numeric(24,9),
    "tax_type" "text",
    "tags" "jsonb",
    "cost_entry_bill_id" integer,
    "cost_entry_pricing_id" integer,
    "cost_entry_product_id" integer,
    "cost_entry_reservation_id" integer
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" (
    "usage_start" "date" NOT NULL,
    "usage_end" "date",
    "usage_account_id" character varying(50) NOT NULL,
    "product_code" character varying(50) NOT NULL,
    "product_family" character varying(150),
    "availability_zone" character varying(50),
    "region" character varying(50),
    "instance_type" character varying(50),
    "unit" character varying(63),
    "resource_ids" "text"[],
    "resource_count" integer,
    "usage_amount" numeric(24,9),
    "normalization_factor" double precision,
    "normalized_usage_amount" double precision,
    "currency_code" character varying(10) NOT NULL,
    "unblended_rate" numeric(24,9),
    "unblended_cost" numeric(24,9),
    "markup_cost" numeric(24,9),
    "blended_rate" numeric(24,9),
    "blended_cost" numeric(24,9),
    "public_on_demand_cost" numeric(24,9),
    "public_on_demand_rate" numeric(24,9),
    "tax_type" "text",
    "tags" "jsonb",
    "source_uuid" "uuid",
    "account_alias_id" integer,
    "cost_entry_bill_id" integer,
    "organizational_unit_id" integer,
    "uuid" "uuid" NOT NULL
);
ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" DEFAULT;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awscostentrypricing" (
    "id" integer NOT NULL,
    "term" character varying(63),
    "unit" character varying(63)
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrypricing" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentrypricing_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrypricing_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentrypricing_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_awscostentrypricing"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awscostentryproduct" (
    "id" integer NOT NULL,
    "sku" character varying(128),
    "product_name" "text",
    "product_family" character varying(150),
    "service_code" character varying(50),
    "region" character varying(50),
    "instance_type" character varying(50),
    "memory" double precision,
    "memory_unit" character varying(24),
    "vcpu" integer,
    CONSTRAINT "reporting_awscostentryproduct_vcpu_check" CHECK (("vcpu" >= 0))
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentryproduct" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentryproduct_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentryproduct_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentryproduct_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_awscostentryproduct"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awscostentryreservation" (
    "id" integer NOT NULL,
    "reservation_arn" "text" NOT NULL,
    "number_of_reservations" integer,
    "units_per_reservation" numeric(24,9),
    "start_time" timestamp with time zone,
    "end_time" timestamp with time zone,
    CONSTRAINT "reporting_awscostentryreservation_number_of_reservations_check" CHECK (("number_of_reservations" >= 0))
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentryreservation" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentryreservation_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentryreservation_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_awscostentryreservation_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_awscostentryreservation"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awsenabledtagkeys" (
    "key" character varying(253) NOT NULL,
    "enabled" boolean DEFAULT true NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awsenabledtagkeys" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awsorganizationalunit" (
    "id" integer NOT NULL,
    "org_unit_name" character varying(250) NOT NULL,
    "org_unit_id" character varying(50) NOT NULL,
    "org_unit_path" "text" NOT NULL,
    "level" smallint NOT NULL,
    "created_timestamp" "date" NOT NULL,
    "deleted_timestamp" "date",
    "account_alias_id" integer,
    "provider_id" "uuid",
    CONSTRAINT "reporting_awsorganizationalunit_level_check" CHECK (("level" >= 0))
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awsorganizationalunit" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_awsorganizationalunit_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awsorganizationalunit_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_awsorganizationalunit_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_awsorganizationalunit"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awstags_summary" (
    "uuid" "uuid" NOT NULL,
    "key" "text" NOT NULL,
    "values" "text"[] NOT NULL,
    "usage_account_id" "text",
    "account_alias_id" integer,
    "cost_entry_bill_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awstags_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_awstags_values" (
    "uuid" "uuid" NOT NULL,
    "key" "text" NOT NULL,
    "value" "text" NOT NULL,
    "usage_account_ids" "text"[] NOT NULL,
    "account_aliases" "text"[] NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awstags_values" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary" (
    "subscription_guid" "text" NOT NULL,
    "instance_type" "text",
    "service_name" "text",
    "resource_location" "text",
    "tags" "jsonb",
    "usage_start" "date" NOT NULL,
    "usage_end" "date",
    "usage_quantity" numeric(24,9),
    "pretax_cost" numeric(24,9),
    "markup_cost" numeric(24,9),
    "currency" "text",
    "instance_ids" "text"[],
    "instance_count" integer,
    "unit_of_measure" "text",
    "source_uuid" "uuid",
    "cost_entry_bill_id" integer NOT NULL,
    "meter_id" integer,
    "uuid" "uuid" NOT NULL
)
PARTITION BY RANGE ("usage_start");

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_compute_summary" AS
 SELECT "row_number"() OVER (ORDER BY "c"."usage_start", "c"."subscription_guid", "c"."instance_type") AS "id",
    "c"."usage_start",
    "c"."usage_start" AS "usage_end",
    "c"."subscription_guid",
    "c"."instance_type",
    "r"."instance_ids",
    "cardinality"("r"."instance_ids") AS "instance_count",
    "c"."usage_quantity",
    "c"."unit_of_measure",
    "c"."pretax_cost",
    "c"."markup_cost",
    "c"."currency",
    "c"."source_uuid"
   FROM (( SELECT "reporting_azurecostentrylineitem_daily_summary"."usage_start",
            "reporting_azurecostentrylineitem_daily_summary"."subscription_guid",
            "reporting_azurecostentrylineitem_daily_summary"."instance_type",
            "sum"("reporting_azurecostentrylineitem_daily_summary"."usage_quantity") AS "usage_quantity",
            "max"("reporting_azurecostentrylineitem_daily_summary"."unit_of_measure") AS "unit_of_measure",
            "sum"("reporting_azurecostentrylineitem_daily_summary"."pretax_cost") AS "pretax_cost",
            "sum"("reporting_azurecostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
            "max"("reporting_azurecostentrylineitem_daily_summary"."currency") AS "currency",
            ("max"(("reporting_azurecostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
           FROM {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
          WHERE (("reporting_azurecostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_azurecostentrylineitem_daily_summary"."instance_type" IS NOT NULL) AND ("reporting_azurecostentrylineitem_daily_summary"."unit_of_measure" = 'Hrs'::"text"))
          GROUP BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid", "reporting_azurecostentrylineitem_daily_summary"."instance_type") "c"
     JOIN ( SELECT "x"."usage_start",
            "x"."subscription_guid",
            "x"."instance_type",
            "array_agg"(DISTINCT "x"."instance_id" ORDER BY "x"."instance_id") AS "instance_ids"
           FROM ( SELECT "reporting_azurecostentrylineitem_daily_summary"."usage_start",
                    "reporting_azurecostentrylineitem_daily_summary"."subscription_guid",
                    "reporting_azurecostentrylineitem_daily_summary"."instance_type",
                    "unnest"("reporting_azurecostentrylineitem_daily_summary"."instance_ids") AS "instance_id"
                   FROM {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
                  WHERE (("reporting_azurecostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_azurecostentrylineitem_daily_summary"."instance_type" IS NOT NULL))) "x"
          GROUP BY "x"."usage_start", "x"."subscription_guid", "x"."instance_type") "r" ON ((("c"."usage_start" = "r"."usage_start") AND ("c"."subscription_guid" = "r"."subscription_guid") AND ("c"."instance_type" = "r"."instance_type"))))
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azure_compute_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_cost_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."source_uuid") AS "id",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_azurecostentrylineitem_daily_summary"."currency") AS "currency",
    "reporting_azurecostentrylineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
  WHERE ("reporting_azurecostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."source_uuid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azure_cost_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_account" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid") AS "id",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_azurecostentrylineitem_daily_summary"."subscription_guid",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_azurecostentrylineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_azurecostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
  WHERE ("reporting_azurecostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_account" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_location" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid", "reporting_azurecostentrylineitem_daily_summary"."resource_location") AS "id",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_azurecostentrylineitem_daily_summary"."subscription_guid",
    "reporting_azurecostentrylineitem_daily_summary"."resource_location",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_azurecostentrylineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_azurecostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
  WHERE ("reporting_azurecostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid", "reporting_azurecostentrylineitem_daily_summary"."resource_location"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_location" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_service" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid", "reporting_azurecostentrylineitem_daily_summary"."service_name") AS "id",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_azurecostentrylineitem_daily_summary"."subscription_guid",
    "reporting_azurecostentrylineitem_daily_summary"."service_name",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_azurecostentrylineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_azurecostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
  WHERE ("reporting_azurecostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid", "reporting_azurecostentrylineitem_daily_summary"."service_name"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_service" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_database_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid", "reporting_azurecostentrylineitem_daily_summary"."service_name") AS "id",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_azurecostentrylineitem_daily_summary"."subscription_guid",
    "reporting_azurecostentrylineitem_daily_summary"."service_name",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."usage_quantity") AS "usage_quantity",
    "max"("reporting_azurecostentrylineitem_daily_summary"."unit_of_measure") AS "unit_of_measure",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_azurecostentrylineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_azurecostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
  WHERE (("reporting_azurecostentrylineitem_daily_summary"."service_name" = ANY (ARRAY['Cosmos DB'::"text", 'Cache for Redis'::"text"])) OR (("reporting_azurecostentrylineitem_daily_summary"."service_name" ~~* '%database%'::"text") AND ("reporting_azurecostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")))
  GROUP BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid", "reporting_azurecostentrylineitem_daily_summary"."service_name"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azure_database_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_network_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid", "reporting_azurecostentrylineitem_daily_summary"."service_name") AS "id",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_azurecostentrylineitem_daily_summary"."subscription_guid",
    "reporting_azurecostentrylineitem_daily_summary"."service_name",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."usage_quantity") AS "usage_quantity",
    "max"("reporting_azurecostentrylineitem_daily_summary"."unit_of_measure") AS "unit_of_measure",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_azurecostentrylineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_azurecostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
  WHERE (("reporting_azurecostentrylineitem_daily_summary"."service_name" = ANY (ARRAY['Virtual Network'::"text", 'VPN'::"text", 'DNS'::"text", 'Traffic Manager'::"text", 'ExpressRoute'::"text", 'Load Balancer'::"text", 'Application Gateway'::"text"])) AND ("reporting_azurecostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date"))
  GROUP BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid", "reporting_azurecostentrylineitem_daily_summary"."service_name"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azure_network_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_storage_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid", "reporting_azurecostentrylineitem_daily_summary"."service_name") AS "id",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start",
    "reporting_azurecostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_azurecostentrylineitem_daily_summary"."subscription_guid",
    "reporting_azurecostentrylineitem_daily_summary"."service_name",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."usage_quantity") AS "usage_quantity",
    "max"("reporting_azurecostentrylineitem_daily_summary"."unit_of_measure") AS "unit_of_measure",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_azurecostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_azurecostentrylineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_azurecostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
  WHERE (("reporting_azurecostentrylineitem_daily_summary"."service_name" ~~ '%Storage%'::"text") AND ("reporting_azurecostentrylineitem_daily_summary"."unit_of_measure" = 'GB-Mo'::"text") AND ("reporting_azurecostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date"))
  GROUP BY "reporting_azurecostentrylineitem_daily_summary"."usage_start", "reporting_azurecostentrylineitem_daily_summary"."subscription_guid", "reporting_azurecostentrylineitem_daily_summary"."service_name"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azure_storage_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrybill" (
    "id" integer NOT NULL,
    "billing_period_start" timestamp with time zone NOT NULL,
    "billing_period_end" timestamp with time zone NOT NULL,
    "summary_data_creation_datetime" timestamp with time zone,
    "summary_data_updated_datetime" timestamp with time zone,
    "finalized_datetime" timestamp with time zone,
    "derived_cost_datetime" timestamp with time zone,
    "provider_id" "uuid" NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrybill" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_azurecostentrybill_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrybill_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_azurecostentrybill_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_azurecostentrybill"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily" (
    "id" bigint NOT NULL,
    "subscription_guid" "text" NOT NULL,
    "tags" "jsonb",
    "usage_date" "date" NOT NULL,
    "usage_quantity" numeric(24,9),
    "pretax_cost" numeric(24,9),
    "cost_entry_bill_id" integer NOT NULL,
    "cost_entry_product_id" integer,
    "meter_id" integer
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_default" (
    "subscription_guid" "text" NOT NULL,
    "instance_type" "text",
    "service_name" "text",
    "resource_location" "text",
    "tags" "jsonb",
    "usage_start" "date" NOT NULL,
    "usage_end" "date",
    "usage_quantity" numeric(24,9),
    "pretax_cost" numeric(24,9),
    "markup_cost" numeric(24,9),
    "currency" "text",
    "instance_ids" "text"[],
    "instance_count" integer,
    "unit_of_measure" "text",
    "source_uuid" "uuid",
    "cost_entry_bill_id" integer NOT NULL,
    "meter_id" integer,
    "uuid" "uuid" NOT NULL
);
ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_default" DEFAULT;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_default" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice" (
    "id" integer NOT NULL,
    "instance_id" "text" NOT NULL,
    "resource_location" "text",
    "consumed_service" "text",
    "resource_type" "text",
    "resource_group" "text",
    "additional_info" "jsonb",
    "service_tier" "text",
    "service_name" "text",
    "service_info1" "text",
    "service_info2" "text",
    "instance_type" "text",
    "provider_id" "uuid"
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_azureenabledtagkeys" (
    "id" bigint NOT NULL,
    "key" character varying(253) NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azureenabledtagkeys" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_azureenabledtagkeys_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azureenabledtagkeys_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_azureenabledtagkeys_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_azureenabledtagkeys"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_azuremeter" (
    "id" integer NOT NULL,
    "meter_id" "uuid" NOT NULL,
    "meter_name" "text" NOT NULL,
    "meter_category" "text",
    "meter_subcategory" "text",
    "meter_region" "text",
    "resource_rate" numeric(24,9),
    "currency" "text",
    "unit_of_measure" "text",
    "provider_id" "uuid"
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azuremeter" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_azuremeter_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azuremeter_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_azuremeter_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_azuremeter"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_azuretags_summary" (
    "uuid" "uuid" NOT NULL,
    "key" "text" NOT NULL,
    "values" "text"[] NOT NULL,
    "subscription_guid" "text",
    "cost_entry_bill_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azuretags_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_azuretags_values" (
    "uuid" "uuid" NOT NULL,
    "key" "text" NOT NULL,
    "value" "text" NOT NULL,
    "subscription_guids" "text"[] NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azuretags_values" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary" (
    "uuid" "uuid" DEFAULT "public"."uuid_generate_v4"() NOT NULL,
    "account_id" character varying(20) NOT NULL,
    "project_id" character varying(256) NOT NULL,
    "project_name" character varying(256) NOT NULL,
    "service_id" character varying(256),
    "service_alias" character varying(256),
    "sku_id" character varying(256),
    "sku_alias" character varying(256),
    "usage_start" "date" NOT NULL,
    "usage_end" "date",
    "region" character varying(50),
    "instance_type" character varying(50),
    "unit" character varying(63),
    "line_item_type" character varying(256),
    "usage_amount" numeric(24,9),
    "currency" character varying(10) NOT NULL,
    "unblended_cost" numeric(24,9),
    "markup_cost" numeric(24,9),
    "tags" "jsonb",
    "source_uuid" "uuid",
    "cost_entry_bill_id" integer NOT NULL,
    "invoice_month" character varying(256)
)
PARTITION BY RANGE ("usage_start");

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_compute_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."instance_type", "reporting_gcpcostentrylineitem_daily_summary"."source_uuid") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_gcpcostentrylineitem_daily_summary"."instance_type",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    "reporting_gcpcostentrylineitem_daily_summary"."source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE (("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_gcpcostentrylineitem_daily_summary"."instance_type" IS NOT NULL))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."instance_type", "reporting_gcpcostentrylineitem_daily_summary"."source_uuid", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_compute_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_account" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."instance_type", "reporting_gcpcostentrylineitem_daily_summary"."account_id") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_gcpcostentrylineitem_daily_summary"."instance_type",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE (("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_gcpcostentrylineitem_daily_summary"."instance_type" IS NOT NULL))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."instance_type", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_account" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_project" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."instance_type", "reporting_gcpcostentrylineitem_daily_summary"."project_id", "reporting_gcpcostentrylineitem_daily_summary"."project_name", "reporting_gcpcostentrylineitem_daily_summary"."account_id") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_gcpcostentrylineitem_daily_summary"."instance_type",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    "reporting_gcpcostentrylineitem_daily_summary"."project_id",
    "reporting_gcpcostentrylineitem_daily_summary"."project_name",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE (("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_gcpcostentrylineitem_daily_summary"."instance_type" IS NOT NULL))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."instance_type", "reporting_gcpcostentrylineitem_daily_summary"."project_id", "reporting_gcpcostentrylineitem_daily_summary"."project_name", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_project" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_region" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."instance_type", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."region") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_gcpcostentrylineitem_daily_summary"."instance_type",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    "reporting_gcpcostentrylineitem_daily_summary"."region",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE (("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_gcpcostentrylineitem_daily_summary"."instance_type" IS NOT NULL))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."instance_type", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."region", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_region" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_service" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."instance_type", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."service_id", "reporting_gcpcostentrylineitem_daily_summary"."service_alias") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_gcpcostentrylineitem_daily_summary"."instance_type",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    "reporting_gcpcostentrylineitem_daily_summary"."service_id",
    "reporting_gcpcostentrylineitem_daily_summary"."service_alias",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE (("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("reporting_gcpcostentrylineitem_daily_summary"."instance_type" IS NOT NULL))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."instance_type", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."service_id", "reporting_gcpcostentrylineitem_daily_summary"."service_alias", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_service" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_cost_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."source_uuid") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    "reporting_gcpcostentrylineitem_daily_summary"."source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE ("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."source_uuid", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_cost_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_account" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE ("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_account" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_project" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."project_id", "reporting_gcpcostentrylineitem_daily_summary"."project_name", "reporting_gcpcostentrylineitem_daily_summary"."account_id") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."project_id",
    "reporting_gcpcostentrylineitem_daily_summary"."project_name",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE ("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."project_id", "reporting_gcpcostentrylineitem_daily_summary"."project_name", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_project" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_region" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."region") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    "reporting_gcpcostentrylineitem_daily_summary"."region",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE ("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."region", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_region" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_service" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."service_id", "reporting_gcpcostentrylineitem_daily_summary"."service_alias") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    "reporting_gcpcostentrylineitem_daily_summary"."service_id",
    "reporting_gcpcostentrylineitem_daily_summary"."service_alias",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE ("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."service_id", "reporting_gcpcostentrylineitem_daily_summary"."service_alias", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_service" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_database_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."service_id",
    "reporting_gcpcostentrylineitem_daily_summary"."service_alias",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE ((("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%SQL%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Spanner%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Bigtable%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Firestore%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Firebase%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Memorystore%'::"text") OR ((("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%MongoDB%'::"text") AND ("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."service_id", "reporting_gcpcostentrylineitem_daily_summary"."service_alias", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_database_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_network_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."service_id",
    "reporting_gcpcostentrylineitem_daily_summary"."service_alias",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE ((("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Network%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%VPC%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Firewall%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Route%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%IP%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%DNS%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%CDN%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%NAT%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Traffic Director%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Service Discovery%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Cloud Domains%'::"text") OR (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Private Service Connect%'::"text") OR ((("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" ~~ '%Cloud Armor%'::"text") AND ("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."service_id", "reporting_gcpcostentrylineitem_daily_summary"."service_alias", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_network_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_storage_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."source_uuid") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    "reporting_gcpcostentrylineitem_daily_summary"."source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE (("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" = ANY ((ARRAY['Filestore'::character varying, 'Storage'::character varying, 'Cloud Storage'::character varying, 'Data Transfer'::character varying])::"text"[])))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."source_uuid", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_storage_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_account" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE (("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" = ANY ((ARRAY['Filestore'::character varying, 'Storage'::character varying, 'Cloud Storage'::character varying, 'Data Transfer'::character varying])::"text"[])))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_account" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_project" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."project_id", "reporting_gcpcostentrylineitem_daily_summary"."project_name", "reporting_gcpcostentrylineitem_daily_summary"."account_id") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    "reporting_gcpcostentrylineitem_daily_summary"."project_id",
    "reporting_gcpcostentrylineitem_daily_summary"."project_name",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE (("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" = ANY ((ARRAY['Filestore'::character varying, 'Storage'::character varying, 'Cloud Storage'::character varying, 'Data Transfer'::character varying])::"text"[])))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."project_id", "reporting_gcpcostentrylineitem_daily_summary"."project_name", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_project" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_region" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."region") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    "reporting_gcpcostentrylineitem_daily_summary"."region",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE (("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" = ANY ((ARRAY['Filestore'::character varying, 'Storage'::character varying, 'Cloud Storage'::character varying, 'Data Transfer'::character varying])::"text"[])))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."region", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_region" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_service" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."service_id", "reporting_gcpcostentrylineitem_daily_summary"."service_alias") AS "id",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start",
    "reporting_gcpcostentrylineitem_daily_summary"."usage_start" AS "usage_end",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_gcpcostentrylineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_gcpcostentrylineitem_daily_summary"."currency")::"text") AS "currency",
    "reporting_gcpcostentrylineitem_daily_summary"."account_id",
    "reporting_gcpcostentrylineitem_daily_summary"."service_id",
    "reporting_gcpcostentrylineitem_daily_summary"."service_alias",
    ("max"(("reporting_gcpcostentrylineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
   FROM {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
  WHERE (("reporting_gcpcostentrylineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND (("reporting_gcpcostentrylineitem_daily_summary"."service_alias")::"text" = ANY ((ARRAY['Filestore'::character varying, 'Storage'::character varying, 'Cloud Storage'::character varying, 'Data Transfer'::character varying])::"text"[])))
  GROUP BY "reporting_gcpcostentrylineitem_daily_summary"."usage_start", "reporting_gcpcostentrylineitem_daily_summary"."account_id", "reporting_gcpcostentrylineitem_daily_summary"."service_id", "reporting_gcpcostentrylineitem_daily_summary"."service_alias", "reporting_gcpcostentrylineitem_daily_summary"."invoice_month"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_service" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrybill" (
    "id" integer NOT NULL,
    "billing_period_start" timestamp with time zone NOT NULL,
    "billing_period_end" timestamp with time zone NOT NULL,
    "summary_data_creation_datetime" timestamp with time zone,
    "summary_data_updated_datetime" timestamp with time zone,
    "finalized_datetime" timestamp with time zone,
    "derived_cost_datetime" timestamp with time zone,
    "provider_id" "uuid" NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrybill" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpcostentrybill_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrybill_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpcostentrybill_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_gcpcostentrybill"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem" (
    "id" bigint NOT NULL,
    "usage_start" timestamp with time zone NOT NULL,
    "usage_end" timestamp with time zone NOT NULL,
    "tags" "jsonb",
    "usage_type" character varying(50),
    "location" character varying(256),
    "country" character varying(256),
    "region" character varying(256),
    "zone" character varying(256),
    "export_time" character varying(256),
    "cost" numeric(24,9),
    "currency" character varying(256),
    "conversion_rate" character varying(256),
    "usage_to_pricing_units" numeric(24,9),
    "usage_pricing_unit" character varying(256),
    "credits" character varying(256),
    "invoice_month" character varying(256),
    "cost_type" character varying(256),
    "line_item_type" character varying(256),
    "cost_entry_bill_id" integer NOT NULL,
    "cost_entry_product_id" bigint,
    "project_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily" (
    "id" bigint NOT NULL,
    "line_item_type" character varying(256),
    "usage_start" "date" NOT NULL,
    "usage_end" "date",
    "tags" "jsonb",
    "usage_type" character varying(50),
    "region" character varying(256),
    "cost" numeric(24,9),
    "currency" character varying(256),
    "conversion_rate" character varying(256),
    "usage_in_pricing_units" numeric(24,9),
    "usage_pricing_unit" character varying(256),
    "invoice_month" character varying(256),
    "tax_type" character varying(256),
    "cost_entry_bill_id" integer NOT NULL,
    "cost_entry_product_id" bigint,
    "project_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default" (
    "uuid" "uuid" DEFAULT "public"."uuid_generate_v4"() NOT NULL,
    "account_id" character varying(20) NOT NULL,
    "project_id" character varying(256) NOT NULL,
    "project_name" character varying(256) NOT NULL,
    "service_id" character varying(256),
    "service_alias" character varying(256),
    "sku_id" character varying(256),
    "sku_alias" character varying(256),
    "usage_start" "date" NOT NULL,
    "usage_end" "date",
    "region" character varying(50),
    "instance_type" character varying(50),
    "unit" character varying(63),
    "line_item_type" character varying(256),
    "usage_amount" numeric(24,9),
    "currency" character varying(10) NOT NULL,
    "unblended_cost" numeric(24,9),
    "markup_cost" numeric(24,9),
    "tags" "jsonb",
    "source_uuid" "uuid",
    "cost_entry_bill_id" integer NOT NULL,
    "invoice_month" character varying(256)
);
ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default" DEFAULT;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice" (
    "id" bigint NOT NULL,
    "service_id" character varying(256),
    "service_alias" character varying(256),
    "sku_id" character varying(256),
    "sku_alias" character varying(256)
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys" (
    "id" bigint NOT NULL,
    "key" character varying(253) NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_gcpproject" (
    "id" integer NOT NULL,
    "account_id" character varying(20) NOT NULL,
    "project_id" character varying(256) NOT NULL,
    "project_name" character varying(256) NOT NULL,
    "project_labels" character varying(256)
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpproject" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpproject_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpproject_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_gcpproject_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_gcpproject"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_gcptags_summary" (
    "uuid" "uuid" NOT NULL,
    "key" "text" NOT NULL,
    "values" "text"[] NOT NULL,
    "account_id" "text",
    "cost_entry_bill_id" integer NOT NULL,
    "project_id" "text",
    "project_name" "text"
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcptags_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_gcptags_values" (
    "uuid" "uuid" NOT NULL,
    "key" "text" NOT NULL,
    "value" "text" NOT NULL,
    "account_ids" "text"[] NOT NULL,
    "project_ids" "text"[],
    "project_names" "text"[]
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcptags_values" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocp_clusters" (
    "uuid" "uuid" NOT NULL,
    "cluster_id" "text" NOT NULL,
    "cluster_alias" "text",
    "provider_id" "uuid" NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocp_clusters" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary" (
    "cluster_id" character varying(50),
    "cluster_alias" character varying(256),
    "data_source" character varying(64),
    "namespace" character varying(253),
    "node" character varying(253),
    "resource_id" character varying(253),
    "usage_start" "date" NOT NULL,
    "usage_end" "date" NOT NULL,
    "pod_labels" "jsonb",
    "pod_usage_cpu_core_hours" numeric(18,6),
    "pod_request_cpu_core_hours" numeric(18,6),
    "pod_limit_cpu_core_hours" numeric(18,6),
    "pod_usage_memory_gigabyte_hours" numeric(18,6),
    "pod_request_memory_gigabyte_hours" numeric(18,6),
    "pod_limit_memory_gigabyte_hours" numeric(18,6),
    "node_capacity_cpu_cores" numeric(18,6),
    "node_capacity_cpu_core_hours" numeric(18,6),
    "node_capacity_memory_gigabytes" numeric(18,6),
    "node_capacity_memory_gigabyte_hours" numeric(18,6),
    "cluster_capacity_cpu_core_hours" numeric(18,6),
    "cluster_capacity_memory_gigabyte_hours" numeric(18,6),
    "persistentvolumeclaim" character varying(253),
    "persistentvolume" character varying(253),
    "storageclass" character varying(50),
    "volume_labels" "jsonb",
    "persistentvolumeclaim_capacity_gigabyte" numeric(18,6),
    "persistentvolumeclaim_capacity_gigabyte_months" numeric(18,6),
    "volume_request_storage_gigabyte_months" numeric(18,6),
    "persistentvolumeclaim_usage_gigabyte_months" numeric(18,6),
    "infrastructure_raw_cost" numeric(33,15),
    "infrastructure_project_raw_cost" numeric(33,15),
    "infrastructure_usage_cost" "jsonb",
    "infrastructure_markup_cost" numeric(33,15),
    "infrastructure_project_markup_cost" numeric(33,15),
    "infrastructure_monthly_cost" numeric(33,15),
    "supplementary_usage_cost" "jsonb",
    "supplementary_monthly_cost" numeric(33,15),
    "monthly_cost_type" "text",
    "source_uuid" "uuid",
    "report_period_id" integer,
    "uuid" "uuid" NOT NULL,
    "supplementary_monthly_cost_json" "jsonb",
    "infrastructure_monthly_cost_json" "jsonb",
    "supplementary_project_monthly_cost" "jsonb",
    "infrastructure_project_monthly_cost" "jsonb"
)
PARTITION BY RANGE ("usage_start");

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_cost_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias") AS "id",
    "reporting_ocpusagelineitem_daily_summary"."usage_start",
    "reporting_ocpusagelineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpusagelineitem_daily_summary"."cluster_id",
    "reporting_ocpusagelineitem_daily_summary"."cluster_alias",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'storage'::"text"))::numeric)) AS "supplementary_usage_cost",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'storage'::"text"))::numeric)) AS "infrastructure_usage_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_raw_cost") AS "infrastructure_raw_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_markup_cost") AS "infrastructure_markup_cost",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "supplementary_monthly_cost_json",
    "sum"("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost") AS "supplementary_monthly_cost",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "infrastructure_monthly_cost_json",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost") AS "infrastructure_monthly_cost",
    "reporting_ocpusagelineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary"
  WHERE ("reporting_ocpusagelineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias", "reporting_ocpusagelineitem_daily_summary"."source_uuid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocp_cost_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_cost_summary_by_node" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias", "reporting_ocpusagelineitem_daily_summary"."node") AS "id",
    "reporting_ocpusagelineitem_daily_summary"."usage_start",
    "reporting_ocpusagelineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpusagelineitem_daily_summary"."cluster_id",
    "reporting_ocpusagelineitem_daily_summary"."cluster_alias",
    "reporting_ocpusagelineitem_daily_summary"."node",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'storage'::"text"))::numeric)) AS "supplementary_usage_cost",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'storage'::"text"))::numeric)) AS "infrastructure_usage_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_raw_cost") AS "infrastructure_raw_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_markup_cost") AS "infrastructure_markup_cost",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "supplementary_monthly_cost_json",
    "sum"("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost") AS "supplementary_monthly_cost",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "infrastructure_monthly_cost_json",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost") AS "infrastructure_monthly_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_markup_cost") AS "infrastructure_project_markup_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_raw_cost") AS "infrastructure_project_raw_cost",
    "reporting_ocpusagelineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary"
  WHERE ("reporting_ocpusagelineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias", "reporting_ocpusagelineitem_daily_summary"."node", "reporting_ocpusagelineitem_daily_summary"."source_uuid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocp_cost_summary_by_node" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_cost_summary_by_project" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias", "reporting_ocpusagelineitem_daily_summary"."namespace") AS "id",
    "reporting_ocpusagelineitem_daily_summary"."usage_start",
    "reporting_ocpusagelineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpusagelineitem_daily_summary"."cluster_id",
    "reporting_ocpusagelineitem_daily_summary"."cluster_alias",
    "reporting_ocpusagelineitem_daily_summary"."namespace",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'storage'::"text"))::numeric)) AS "supplementary_usage_cost",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'storage'::"text"))::numeric)) AS "infrastructure_usage_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_raw_cost") AS "infrastructure_project_raw_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_markup_cost") AS "infrastructure_project_markup_cost",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_project_monthly_cost", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_project_monthly_cost", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_project_monthly_cost", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "supplementary_project_monthly_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost") AS "supplementary_monthly_cost",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_monthly_cost", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_monthly_cost", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_monthly_cost", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "infrastructure_project_monthly_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost") AS "infrastructure_monthly_cost",
    "reporting_ocpusagelineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary"
  WHERE ("reporting_ocpusagelineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias", "reporting_ocpusagelineitem_daily_summary"."namespace", "reporting_ocpusagelineitem_daily_summary"."source_uuid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocp_cost_summary_by_project" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocp_nodes" (
    "uuid" "uuid" NOT NULL,
    "node" "text" NOT NULL,
    "resource_id" "text",
    "node_capacity_cpu_cores" numeric(18,2),
    "cluster_id" "uuid" NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocp_nodes" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_pod_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias") AS "id",
    "reporting_ocpusagelineitem_daily_summary"."usage_start",
    "reporting_ocpusagelineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpusagelineitem_daily_summary"."cluster_id",
    "reporting_ocpusagelineitem_daily_summary"."cluster_alias",
    "max"(("reporting_ocpusagelineitem_daily_summary"."data_source")::"text") AS "data_source",
    "array_agg"(DISTINCT "reporting_ocpusagelineitem_daily_summary"."resource_id") AS "resource_ids",
    "count"(DISTINCT "reporting_ocpusagelineitem_daily_summary"."resource_id") AS "resource_count",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'storage'::"text"))::numeric)) AS "supplementary_usage_cost",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'storage'::"text"))::numeric)) AS "infrastructure_usage_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_raw_cost") AS "infrastructure_raw_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_markup_cost") AS "infrastructure_markup_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_usage_cpu_core_hours") AS "pod_usage_cpu_core_hours",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_request_cpu_core_hours") AS "pod_request_cpu_core_hours",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_limit_cpu_core_hours") AS "pod_limit_cpu_core_hours",
    "max"("reporting_ocpusagelineitem_daily_summary"."cluster_capacity_cpu_core_hours") AS "cluster_capacity_cpu_core_hours",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_usage_memory_gigabyte_hours") AS "pod_usage_memory_gigabyte_hours",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_request_memory_gigabyte_hours") AS "pod_request_memory_gigabyte_hours",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_limit_memory_gigabyte_hours") AS "pod_limit_memory_gigabyte_hours",
    "max"("reporting_ocpusagelineitem_daily_summary"."cluster_capacity_memory_gigabyte_hours") AS "cluster_capacity_memory_gigabyte_hours",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "supplementary_monthly_cost_json",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "infrastructure_monthly_cost_json",
    "reporting_ocpusagelineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary"
  WHERE (("reporting_ocpusagelineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND (("reporting_ocpusagelineitem_daily_summary"."data_source")::"text" = 'Pod'::"text"))
  GROUP BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias", "reporting_ocpusagelineitem_daily_summary"."source_uuid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocp_pod_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_pod_summary_by_project" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias", "reporting_ocpusagelineitem_daily_summary"."namespace") AS "id",
    "reporting_ocpusagelineitem_daily_summary"."usage_start",
    "reporting_ocpusagelineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpusagelineitem_daily_summary"."cluster_id",
    "reporting_ocpusagelineitem_daily_summary"."cluster_alias",
    "reporting_ocpusagelineitem_daily_summary"."namespace",
    "max"(("reporting_ocpusagelineitem_daily_summary"."data_source")::"text") AS "data_source",
    "array_agg"(DISTINCT "reporting_ocpusagelineitem_daily_summary"."resource_id") AS "resource_ids",
    "count"(DISTINCT "reporting_ocpusagelineitem_daily_summary"."resource_id") AS "resource_count",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'storage'::"text"))::numeric)) AS "supplementary_usage_cost",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'storage'::"text"))::numeric)) AS "infrastructure_usage_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_raw_cost") AS "infrastructure_raw_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_markup_cost") AS "infrastructure_markup_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_usage_cpu_core_hours") AS "pod_usage_cpu_core_hours",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_request_cpu_core_hours") AS "pod_request_cpu_core_hours",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_limit_cpu_core_hours") AS "pod_limit_cpu_core_hours",
    "max"("reporting_ocpusagelineitem_daily_summary"."cluster_capacity_cpu_core_hours") AS "cluster_capacity_cpu_core_hours",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_usage_memory_gigabyte_hours") AS "pod_usage_memory_gigabyte_hours",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_request_memory_gigabyte_hours") AS "pod_request_memory_gigabyte_hours",
    "sum"("reporting_ocpusagelineitem_daily_summary"."pod_limit_memory_gigabyte_hours") AS "pod_limit_memory_gigabyte_hours",
    "max"("reporting_ocpusagelineitem_daily_summary"."cluster_capacity_memory_gigabyte_hours") AS "cluster_capacity_memory_gigabyte_hours",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_project_monthly_cost", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_project_monthly_cost", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_project_monthly_cost", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "supplementary_monthly_cost_json",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_monthly_cost", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_monthly_cost", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_monthly_cost", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "infrastructure_monthly_cost_json",
    "reporting_ocpusagelineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary"
  WHERE (("reporting_ocpusagelineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND (("reporting_ocpusagelineitem_daily_summary"."data_source")::"text" = 'Pod'::"text"))
  GROUP BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias", "reporting_ocpusagelineitem_daily_summary"."namespace", "reporting_ocpusagelineitem_daily_summary"."source_uuid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocp_pod_summary_by_project" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocp_projects" (
    "uuid" "uuid" NOT NULL,
    "project" "text" NOT NULL,
    "cluster_id" "uuid" NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocp_projects" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocp_pvcs" (
    "uuid" "uuid" NOT NULL,
    "persistent_volume" "text" NOT NULL,
    "persistent_volume_claim" "text" NOT NULL,
    "cluster_id" "uuid" NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocp_pvcs" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_volume_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias") AS "id",
    "reporting_ocpusagelineitem_daily_summary"."usage_start",
    "reporting_ocpusagelineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpusagelineitem_daily_summary"."cluster_id",
    "reporting_ocpusagelineitem_daily_summary"."cluster_alias",
    "max"(("reporting_ocpusagelineitem_daily_summary"."data_source")::"text") AS "data_source",
    "array_agg"(DISTINCT "reporting_ocpusagelineitem_daily_summary"."resource_id") AS "resource_ids",
    "count"(DISTINCT "reporting_ocpusagelineitem_daily_summary"."resource_id") AS "resource_count",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'storage'::"text"))::numeric)) AS "supplementary_usage_cost",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'storage'::"text"))::numeric)) AS "infrastructure_usage_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_raw_cost") AS "infrastructure_raw_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_markup_cost") AS "infrastructure_markup_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."persistentvolumeclaim_usage_gigabyte_months") AS "persistentvolumeclaim_usage_gigabyte_months",
    "sum"("reporting_ocpusagelineitem_daily_summary"."volume_request_storage_gigabyte_months") AS "volume_request_storage_gigabyte_months",
    "sum"("reporting_ocpusagelineitem_daily_summary"."persistentvolumeclaim_capacity_gigabyte_months") AS "persistentvolumeclaim_capacity_gigabyte_months",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_monthly_cost_json", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "supplementary_monthly_cost_json",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_monthly_cost_json", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "infrastructure_monthly_cost_json",
    "reporting_ocpusagelineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary"
  WHERE (("reporting_ocpusagelineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND (("reporting_ocpusagelineitem_daily_summary"."data_source")::"text" = 'Storage'::"text"))
  GROUP BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias", "reporting_ocpusagelineitem_daily_summary"."source_uuid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocp_volume_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_volume_summary_by_project" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias", "reporting_ocpusagelineitem_daily_summary"."namespace") AS "id",
    "reporting_ocpusagelineitem_daily_summary"."usage_start",
    "reporting_ocpusagelineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpusagelineitem_daily_summary"."cluster_id",
    "reporting_ocpusagelineitem_daily_summary"."cluster_alias",
    "reporting_ocpusagelineitem_daily_summary"."namespace",
    "max"(("reporting_ocpusagelineitem_daily_summary"."data_source")::"text") AS "data_source",
    "array_agg"(DISTINCT "reporting_ocpusagelineitem_daily_summary"."resource_id") AS "resource_ids",
    "count"(DISTINCT "reporting_ocpusagelineitem_daily_summary"."resource_id") AS "resource_count",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."supplementary_usage_cost" ->> 'storage'::"text"))::numeric)) AS "supplementary_usage_cost",
    "json_build_object"('cpu', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'cpu'::"text"))::numeric), 'memory', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'memory'::"text"))::numeric), 'storage', "sum"((("reporting_ocpusagelineitem_daily_summary"."infrastructure_usage_cost" ->> 'storage'::"text"))::numeric)) AS "infrastructure_usage_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_raw_cost") AS "infrastructure_raw_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."infrastructure_markup_cost") AS "infrastructure_markup_cost",
    "sum"("reporting_ocpusagelineitem_daily_summary"."persistentvolumeclaim_usage_gigabyte_months") AS "persistentvolumeclaim_usage_gigabyte_months",
    "sum"("reporting_ocpusagelineitem_daily_summary"."volume_request_storage_gigabyte_months") AS "volume_request_storage_gigabyte_months",
    "sum"("reporting_ocpusagelineitem_daily_summary"."persistentvolumeclaim_capacity_gigabyte_months") AS "persistentvolumeclaim_capacity_gigabyte_months",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_project_monthly_cost", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_project_monthly_cost", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."supplementary_project_monthly_cost", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "supplementary_monthly_cost_json",
    "json_build_object"('cpu', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_monthly_cost", '{"cpu": 0}'::"jsonb") ->> 'cpu'::"text"))::numeric), 'memory', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_monthly_cost", '{"memory": 0}'::"jsonb") ->> 'memory'::"text"))::numeric), 'pvc', "sum"(((COALESCE("reporting_ocpusagelineitem_daily_summary"."infrastructure_project_monthly_cost", '{"pvc": 0}'::"jsonb") ->> 'pvc'::"text"))::numeric)) AS "infrastructure_monthly_cost_json",
    "reporting_ocpusagelineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary"
  WHERE (("reporting_ocpusagelineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND (("reporting_ocpusagelineitem_daily_summary"."data_source")::"text" = 'Storage'::"text"))
  GROUP BY "reporting_ocpusagelineitem_daily_summary"."usage_start", "reporting_ocpusagelineitem_daily_summary"."cluster_id", "reporting_ocpusagelineitem_daily_summary"."cluster_alias", "reporting_ocpusagelineitem_daily_summary"."namespace", "reporting_ocpusagelineitem_daily_summary"."source_uuid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocp_volume_summary_by_project" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" (
    "cluster_id" character varying(50),
    "cluster_alias" character varying(256),
    "namespace" character varying(253)[] NOT NULL,
    "node" character varying(253),
    "resource_id" character varying(253),
    "usage_start" "date" NOT NULL,
    "usage_end" "date" NOT NULL,
    "product_code" character varying(50) NOT NULL,
    "product_family" character varying(150),
    "instance_type" character varying(50),
    "usage_account_id" character varying(50) NOT NULL,
    "availability_zone" character varying(50),
    "region" character varying(50),
    "unit" character varying(63),
    "tags" "jsonb",
    "usage_amount" numeric(24,9),
    "normalized_usage_amount" double precision,
    "currency_code" character varying(10),
    "unblended_cost" numeric(30,15),
    "markup_cost" numeric(30,15),
    "shared_projects" integer NOT NULL,
    "project_costs" "jsonb",
    "source_uuid" "uuid",
    "account_alias_id" integer,
    "cost_entry_bill_id" integer,
    "report_period_id" integer,
    "uuid" "uuid" NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" (
    "cluster_id" character varying(50),
    "cluster_alias" character varying(256),
    "namespace" character varying(253)[] NOT NULL,
    "node" character varying(253),
    "resource_id" character varying(253),
    "usage_start" "date" NOT NULL,
    "usage_end" "date" NOT NULL,
    "subscription_guid" "text" NOT NULL,
    "instance_type" "text",
    "service_name" "text",
    "resource_location" "text",
    "tags" "jsonb",
    "usage_quantity" numeric(24,9),
    "pretax_cost" numeric(17,9),
    "markup_cost" numeric(17,9),
    "currency" "text",
    "unit_of_measure" "text",
    "shared_projects" integer NOT NULL,
    "project_costs" "jsonb",
    "source_uuid" "uuid",
    "cost_entry_bill_id" integer NOT NULL,
    "report_period_id" integer,
    "uuid" "uuid" NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary" AS
 SELECT "row_number"() OVER () AS "id",
    "lids"."source_type",
    "lids"."cluster_id",
    "max"(("lids"."cluster_alias")::"text") AS "cluster_alias",
    "lids"."namespace",
    "lids"."node",
    "lids"."resource_id",
    "lids"."usage_start",
    "lids"."usage_start" AS "usage_end",
    "lids"."usage_account_id",
    "max"("lids"."account_alias_id") AS "account_alias_id",
    "lids"."product_code",
    "lids"."product_family",
    "lids"."instance_type",
    "lids"."region",
    "lids"."availability_zone",
    "lids"."tags",
    "sum"("lids"."usage_amount") AS "usage_amount",
    "max"(("lids"."unit")::"text") AS "unit",
    "sum"("lids"."unblended_cost") AS "unblended_cost",
    "sum"("lids"."markup_cost") AS "markup_cost",
    "max"(("lids"."currency_code")::"text") AS "currency_code",
    "max"("lids"."shared_projects") AS "shared_projects",
    ("max"(("lids"."source_uuid")::"text"))::"uuid" AS "source_uuid",
    "lids"."tags_hash",
    "lids"."namespace_hash"
   FROM ( SELECT 'AWS'::"text" AS "source_type",
            "aws"."cluster_id",
            "aws"."cluster_alias",
            "aws"."namespace",
            "aws"."node",
            "aws"."resource_id",
            "aws"."usage_start",
            "aws"."usage_end",
            "aws"."usage_account_id",
            "aws"."account_alias_id",
            "aws"."product_code",
            "aws"."product_family",
            "aws"."instance_type",
            "aws"."region",
            "aws"."availability_zone",
            "aws"."tags",
            "aws"."usage_amount",
            "aws"."unit",
            "aws"."unblended_cost",
            "aws"."markup_cost",
            "aws"."currency_code",
            "aws"."shared_projects",
            "aws"."source_uuid",
            "public"."jsonb_sha256_text"("aws"."tags") AS "tags_hash",
            "encode"("sha256"("decode"("array_to_string"("aws"."namespace", '|'::"text"), 'escape'::"text")), 'hex'::"text") AS "namespace_hash"
           FROM {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" "aws"
          WHERE ("aws"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
        UNION
         SELECT 'Azure'::"text" AS "source_type",
            "azure"."cluster_id",
            "azure"."cluster_alias",
            "azure"."namespace",
            "azure"."node",
            "azure"."resource_id",
            "azure"."usage_start",
            "azure"."usage_end",
            "azure"."subscription_guid" AS "usage_account_id",
            NULL::integer AS "account_alias_id",
            "azure"."service_name" AS "product_code",
            NULL::character varying AS "product_family",
            "azure"."instance_type",
            "azure"."resource_location" AS "region",
            NULL::character varying AS "availability_zone",
            "azure"."tags",
            "azure"."usage_quantity" AS "usage_amount",
            "azure"."unit_of_measure" AS "unit",
            "azure"."pretax_cost" AS "unblended_cost",
            "azure"."markup_cost",
            "azure"."currency" AS "currency_code",
            "azure"."shared_projects",
            "azure"."source_uuid",
            "public"."jsonb_sha256_text"("azure"."tags") AS "tags_hash",
            "encode"("sha256"("decode"("array_to_string"("azure"."namespace", '|'::"text"), 'escape'::"text")), 'hex'::"text") AS "namespace_hash"
           FROM {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" "azure"
          WHERE ("azure"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")) "lids"
  GROUP BY "lids"."source_type", "lids"."cluster_id", "lids"."cluster_alias", "lids"."namespace", "lids"."namespace_hash", "lids"."node", "lids"."resource_id", "lids"."usage_start", "lids"."usage_account_id", "lids"."account_alias_id", "lids"."product_code", "lids"."product_family", "lids"."instance_type", "lids"."region", "lids"."availability_zone", "lids"."tags", "lids"."tags_hash"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_compute_summary" AS
 SELECT "row_number"() OVER (ORDER BY "lids"."usage_start", "lids"."cluster_id", "lids"."usage_account_id", "lids"."product_code") AS "id",
    "lids"."usage_start",
    "lids"."usage_start" AS "usage_end",
    "lids"."cluster_id",
    "max"("lids"."cluster_alias") AS "cluster_alias",
    "lids"."usage_account_id",
    "max"("lids"."account_alias_id") AS "account_alias_id",
    "lids"."product_code",
    "lids"."instance_type",
    "lids"."resource_id",
    "sum"("lids"."usage_amount") AS "usage_amount",
    "max"("lids"."unit") AS "unit",
    "sum"("lids"."unblended_cost") AS "unblended_cost",
    "sum"("lids"."markup_cost") AS "markup_cost",
    "max"("lids"."currency_code") AS "currency_code",
    ("max"(("lids"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary" "lids"
  WHERE (("lids"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ("lids"."instance_type" IS NOT NULL))
  GROUP BY "lids"."usage_start", "lids"."cluster_id", "lids"."usage_account_id", "lids"."product_code", "lids"."instance_type", "lids"."resource_id"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpall_compute_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpallcostlineitem_daily_summary"."usage_start", "reporting_ocpallcostlineitem_daily_summary"."cluster_id", "reporting_ocpallcostlineitem_daily_summary"."source_uuid") AS "id",
    "reporting_ocpallcostlineitem_daily_summary"."usage_start",
    "reporting_ocpallcostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpallcostlineitem_daily_summary"."cluster_id",
    "max"("reporting_ocpallcostlineitem_daily_summary"."cluster_alias") AS "cluster_alias",
    "sum"("reporting_ocpallcostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpallcostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpallcostlineitem_daily_summary"."currency_code") AS "currency_code",
    "reporting_ocpallcostlineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary"
  WHERE ("reporting_ocpallcostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_ocpallcostlineitem_daily_summary"."usage_start", "reporting_ocpallcostlineitem_daily_summary"."cluster_id", "reporting_ocpallcostlineitem_daily_summary"."cluster_alias", "reporting_ocpallcostlineitem_daily_summary"."source_uuid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_account" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpallcostlineitem_daily_summary"."usage_start", "reporting_ocpallcostlineitem_daily_summary"."cluster_id", "reporting_ocpallcostlineitem_daily_summary"."usage_account_id") AS "id",
    "reporting_ocpallcostlineitem_daily_summary"."usage_start",
    "reporting_ocpallcostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpallcostlineitem_daily_summary"."cluster_id",
    "max"("reporting_ocpallcostlineitem_daily_summary"."cluster_alias") AS "cluster_alias",
    "reporting_ocpallcostlineitem_daily_summary"."usage_account_id",
    "max"("reporting_ocpallcostlineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "sum"("reporting_ocpallcostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpallcostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpallcostlineitem_daily_summary"."currency_code") AS "currency_code",
    ("max"(("reporting_ocpallcostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary"
  WHERE ("reporting_ocpallcostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_ocpallcostlineitem_daily_summary"."usage_start", "reporting_ocpallcostlineitem_daily_summary"."cluster_id", "reporting_ocpallcostlineitem_daily_summary"."usage_account_id"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_account" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_region" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpallcostlineitem_daily_summary"."usage_start", "reporting_ocpallcostlineitem_daily_summary"."cluster_id", "reporting_ocpallcostlineitem_daily_summary"."usage_account_id", "reporting_ocpallcostlineitem_daily_summary"."region", "reporting_ocpallcostlineitem_daily_summary"."availability_zone") AS "id",
    "reporting_ocpallcostlineitem_daily_summary"."usage_start",
    "reporting_ocpallcostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpallcostlineitem_daily_summary"."cluster_id",
    "max"("reporting_ocpallcostlineitem_daily_summary"."cluster_alias") AS "cluster_alias",
    "reporting_ocpallcostlineitem_daily_summary"."usage_account_id",
    "max"("reporting_ocpallcostlineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "reporting_ocpallcostlineitem_daily_summary"."region",
    "reporting_ocpallcostlineitem_daily_summary"."availability_zone",
    "sum"("reporting_ocpallcostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpallcostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpallcostlineitem_daily_summary"."currency_code") AS "currency_code",
    ("max"(("reporting_ocpallcostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary"
  WHERE ("reporting_ocpallcostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_ocpallcostlineitem_daily_summary"."usage_start", "reporting_ocpallcostlineitem_daily_summary"."cluster_id", "reporting_ocpallcostlineitem_daily_summary"."usage_account_id", "reporting_ocpallcostlineitem_daily_summary"."region", "reporting_ocpallcostlineitem_daily_summary"."availability_zone"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_region" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_service" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpallcostlineitem_daily_summary"."usage_start", "reporting_ocpallcostlineitem_daily_summary"."cluster_id", "reporting_ocpallcostlineitem_daily_summary"."usage_account_id", "reporting_ocpallcostlineitem_daily_summary"."product_code", "reporting_ocpallcostlineitem_daily_summary"."product_family") AS "id",
    "reporting_ocpallcostlineitem_daily_summary"."usage_start",
    "reporting_ocpallcostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpallcostlineitem_daily_summary"."cluster_id",
    "max"("reporting_ocpallcostlineitem_daily_summary"."cluster_alias") AS "cluster_alias",
    "reporting_ocpallcostlineitem_daily_summary"."usage_account_id",
    "max"("reporting_ocpallcostlineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "reporting_ocpallcostlineitem_daily_summary"."product_code",
    "reporting_ocpallcostlineitem_daily_summary"."product_family",
    "sum"("reporting_ocpallcostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpallcostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpallcostlineitem_daily_summary"."currency_code") AS "currency_code",
    ("max"(("reporting_ocpallcostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary"
  WHERE ("reporting_ocpallcostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
  GROUP BY "reporting_ocpallcostlineitem_daily_summary"."usage_start", "reporting_ocpallcostlineitem_daily_summary"."cluster_id", "reporting_ocpallcostlineitem_daily_summary"."usage_account_id", "reporting_ocpallcostlineitem_daily_summary"."product_code", "reporting_ocpallcostlineitem_daily_summary"."product_family"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_service" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_database_summary" AS
 SELECT "row_number"() OVER (ORDER BY "lids"."usage_start", "lids"."cluster_id", "lids"."usage_account_id", "lids"."product_code") AS "id",
    "lids"."usage_start",
    "lids"."usage_start" AS "usage_end",
    "lids"."cluster_id",
    "max"("lids"."cluster_alias") AS "cluster_alias",
    "lids"."usage_account_id",
    "max"("lids"."account_alias_id") AS "account_alias_id",
    "lids"."product_code",
    "sum"("lids"."usage_amount") AS "usage_amount",
    "max"("lids"."unit") AS "unit",
    "sum"("lids"."unblended_cost") AS "unblended_cost",
    "sum"("lids"."markup_cost") AS "markup_cost",
    "max"("lids"."currency_code") AS "currency_code",
    ("max"(("lids"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary" "lids"
  WHERE (("lids"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ((("lids"."product_code")::"text" = ANY ((ARRAY['AmazonRDS'::character varying, 'AmazonDynamoDB'::character varying, 'AmazonElastiCache'::character varying, 'AmazonNeptune'::character varying, 'AmazonRedshift'::character varying, 'AmazonDocumentDB'::character varying, 'Cosmos DB'::character varying, 'Cache for Redis'::character varying])::"text"[])) OR (("lids"."product_code")::"text" ~~ '%Database%'::"text")))
  GROUP BY "lids"."usage_start", "lids"."cluster_id", "lids"."usage_account_id", "lids"."product_code"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpall_database_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_network_summary" AS
 SELECT "row_number"() OVER (ORDER BY "lids"."usage_start", "lids"."cluster_id", "lids"."usage_account_id", "lids"."product_code") AS "id",
    "lids"."cluster_id",
    "max"("lids"."cluster_alias") AS "cluster_alias",
    "lids"."usage_account_id",
    "max"("lids"."account_alias_id") AS "account_alias_id",
    "lids"."usage_start",
    "lids"."usage_start" AS "usage_end",
    "lids"."product_code",
    "sum"("lids"."usage_amount") AS "usage_amount",
    "max"("lids"."unit") AS "unit",
    "sum"("lids"."unblended_cost") AS "unblended_cost",
    "sum"("lids"."markup_cost") AS "markup_cost",
    "max"("lids"."currency_code") AS "currency_code",
    ("max"(("lids"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary" "lids"
  WHERE (("lids"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND (("lids"."product_code")::"text" = ANY ((ARRAY['AmazonVPC'::character varying, 'AmazonCloudFront'::character varying, 'AmazonRoute53'::character varying, 'AmazonAPIGateway'::character varying, 'Virtual Network'::character varying, 'VPN'::character varying, 'DNS'::character varying, 'Traffic Manager'::character varying, 'ExpressRoute'::character varying, 'Load Balancer'::character varying, 'Application Gateway'::character varying])::"text"[])))
  GROUP BY "lids"."usage_start", "lids"."cluster_id", "lids"."usage_account_id", "lids"."product_code"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpall_network_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_storage_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpallcostlineitem_daily_summary"."usage_start", "reporting_ocpallcostlineitem_daily_summary"."cluster_id", "reporting_ocpallcostlineitem_daily_summary"."usage_account_id", "reporting_ocpallcostlineitem_daily_summary"."product_family", "reporting_ocpallcostlineitem_daily_summary"."product_code") AS "id",
    "reporting_ocpallcostlineitem_daily_summary"."cluster_id",
    "max"("reporting_ocpallcostlineitem_daily_summary"."cluster_alias") AS "cluster_alias",
    "reporting_ocpallcostlineitem_daily_summary"."usage_account_id",
    "max"("reporting_ocpallcostlineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "reporting_ocpallcostlineitem_daily_summary"."usage_start",
    "reporting_ocpallcostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpallcostlineitem_daily_summary"."product_family",
    "reporting_ocpallcostlineitem_daily_summary"."product_code",
    "sum"("reporting_ocpallcostlineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"("reporting_ocpallcostlineitem_daily_summary"."unit") AS "unit",
    "sum"("reporting_ocpallcostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpallcostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpallcostlineitem_daily_summary"."currency_code") AS "currency_code",
    ("max"(("reporting_ocpallcostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary"
  WHERE (("reporting_ocpallcostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date") AND ((("reporting_ocpallcostlineitem_daily_summary"."product_family")::"text" ~~ '%Storage%'::"text") OR (("reporting_ocpallcostlineitem_daily_summary"."product_code")::"text" ~~ '%Storage%'::"text")) AND ("reporting_ocpallcostlineitem_daily_summary"."unit" = 'GB-Mo'::"text"))
  GROUP BY "reporting_ocpallcostlineitem_daily_summary"."usage_start", "reporting_ocpallcostlineitem_daily_summary"."cluster_id", "reporting_ocpallcostlineitem_daily_summary"."usage_account_id", "reporting_ocpallcostlineitem_daily_summary"."product_family", "reporting_ocpallcostlineitem_daily_summary"."product_code"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpall_storage_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" (
    "cluster_id" character varying(50),
    "cluster_alias" character varying(256),
    "data_source" character varying(64),
    "namespace" character varying(253) NOT NULL,
    "node" character varying(253),
    "pod_labels" "jsonb",
    "resource_id" character varying(253),
    "usage_start" "date" NOT NULL,
    "usage_end" "date" NOT NULL,
    "product_code" character varying(50) NOT NULL,
    "product_family" character varying(150),
    "instance_type" character varying(50),
    "usage_account_id" character varying(50) NOT NULL,
    "availability_zone" character varying(50),
    "region" character varying(50),
    "unit" character varying(63),
    "usage_amount" numeric(30,15),
    "normalized_usage_amount" double precision,
    "currency_code" character varying(10),
    "unblended_cost" numeric(30,15),
    "markup_cost" numeric(30,15),
    "project_markup_cost" numeric(30,15),
    "pod_cost" numeric(30,15),
    "source_uuid" "uuid",
    "account_alias_id" integer,
    "cost_entry_bill_id" integer,
    "report_period_id" integer,
    "uuid" "uuid" NOT NULL,
    "persistentvolume" character varying(253),
    "persistentvolumeclaim" character varying(253),
    "storageclass" character varying(50),
    "tags" "jsonb"
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" (
    "cluster_id" character varying(50),
    "cluster_alias" character varying(256),
    "data_source" character varying(64),
    "namespace" character varying(253) NOT NULL,
    "node" character varying(253),
    "pod_labels" "jsonb",
    "resource_id" character varying(253),
    "usage_start" "date" NOT NULL,
    "usage_end" "date" NOT NULL,
    "subscription_guid" "text" NOT NULL,
    "instance_type" "text",
    "service_name" "text",
    "resource_location" "text",
    "usage_quantity" numeric(24,9),
    "unit_of_measure" "text",
    "currency" "text",
    "pretax_cost" numeric(17,9),
    "markup_cost" numeric(17,9),
    "project_markup_cost" numeric(17,9),
    "pod_cost" numeric(24,6),
    "source_uuid" "uuid",
    "cost_entry_bill_id" integer NOT NULL,
    "report_period_id" integer,
    "uuid" "uuid" NOT NULL,
    "persistentvolume" character varying(253),
    "persistentvolumeclaim" character varying(253),
    "storageclass" character varying(50),
    "tags" "jsonb"
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_project_daily_summary" AS
 SELECT "row_number"() OVER () AS "id",
    "lids"."source_type",
    "lids"."cluster_id",
    "lids"."cluster_alias",
    "lids"."data_source",
    "lids"."namespace",
    "lids"."node",
    "lids"."pod_labels",
    "lids"."resource_id",
    "lids"."usage_start",
    "lids"."usage_end",
    "lids"."usage_account_id",
    "lids"."account_alias_id",
    "lids"."product_code",
    "lids"."product_family",
    "lids"."instance_type",
    "lids"."region",
    "lids"."availability_zone",
    "lids"."usage_amount",
    "lids"."unit",
    "lids"."unblended_cost",
    "lids"."project_markup_cost",
    "lids"."pod_cost",
    "lids"."currency_code",
    "lids"."source_uuid"
   FROM ( SELECT 'AWS'::"text" AS "source_type",
            "reporting_ocpawscostlineitem_project_daily_summary"."cluster_id",
            "max"(("reporting_ocpawscostlineitem_project_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
            "reporting_ocpawscostlineitem_project_daily_summary"."data_source",
            ("reporting_ocpawscostlineitem_project_daily_summary"."namespace")::"text" AS "namespace",
            ("reporting_ocpawscostlineitem_project_daily_summary"."node")::"text" AS "node",
            "reporting_ocpawscostlineitem_project_daily_summary"."pod_labels",
            "reporting_ocpawscostlineitem_project_daily_summary"."resource_id",
            "reporting_ocpawscostlineitem_project_daily_summary"."usage_start",
            "reporting_ocpawscostlineitem_project_daily_summary"."usage_end",
            "reporting_ocpawscostlineitem_project_daily_summary"."usage_account_id",
            "max"("reporting_ocpawscostlineitem_project_daily_summary"."account_alias_id") AS "account_alias_id",
            "reporting_ocpawscostlineitem_project_daily_summary"."product_code",
            "reporting_ocpawscostlineitem_project_daily_summary"."product_family",
            "reporting_ocpawscostlineitem_project_daily_summary"."instance_type",
            "reporting_ocpawscostlineitem_project_daily_summary"."region",
            "reporting_ocpawscostlineitem_project_daily_summary"."availability_zone",
            "sum"("reporting_ocpawscostlineitem_project_daily_summary"."usage_amount") AS "usage_amount",
            "max"(("reporting_ocpawscostlineitem_project_daily_summary"."unit")::"text") AS "unit",
            "sum"("reporting_ocpawscostlineitem_project_daily_summary"."unblended_cost") AS "unblended_cost",
            "sum"("reporting_ocpawscostlineitem_project_daily_summary"."project_markup_cost") AS "project_markup_cost",
            "sum"("reporting_ocpawscostlineitem_project_daily_summary"."pod_cost") AS "pod_cost",
            "max"(("reporting_ocpawscostlineitem_project_daily_summary"."currency_code")::"text") AS "currency_code",
            ("max"(("reporting_ocpawscostlineitem_project_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
           FROM {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary"
          WHERE ("reporting_ocpawscostlineitem_project_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
          GROUP BY 'AWS'::"text", "reporting_ocpawscostlineitem_project_daily_summary"."usage_start", "reporting_ocpawscostlineitem_project_daily_summary"."usage_end", "reporting_ocpawscostlineitem_project_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_project_daily_summary"."data_source", "reporting_ocpawscostlineitem_project_daily_summary"."namespace", "reporting_ocpawscostlineitem_project_daily_summary"."node", "reporting_ocpawscostlineitem_project_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_project_daily_summary"."resource_id", "reporting_ocpawscostlineitem_project_daily_summary"."product_code", "reporting_ocpawscostlineitem_project_daily_summary"."product_family", "reporting_ocpawscostlineitem_project_daily_summary"."instance_type", "reporting_ocpawscostlineitem_project_daily_summary"."region", "reporting_ocpawscostlineitem_project_daily_summary"."availability_zone", "reporting_ocpawscostlineitem_project_daily_summary"."pod_labels"
        UNION
         SELECT 'Azure'::"text" AS "source_type",
            "reporting_ocpazurecostlineitem_project_daily_summary"."cluster_id",
            "max"(("reporting_ocpazurecostlineitem_project_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
            "reporting_ocpazurecostlineitem_project_daily_summary"."data_source",
            ("reporting_ocpazurecostlineitem_project_daily_summary"."namespace")::"text" AS "namespace",
            ("reporting_ocpazurecostlineitem_project_daily_summary"."node")::"text" AS "node",
            "reporting_ocpazurecostlineitem_project_daily_summary"."pod_labels",
            "reporting_ocpazurecostlineitem_project_daily_summary"."resource_id",
            "reporting_ocpazurecostlineitem_project_daily_summary"."usage_start",
            "reporting_ocpazurecostlineitem_project_daily_summary"."usage_end",
            "reporting_ocpazurecostlineitem_project_daily_summary"."subscription_guid" AS "usage_account_id",
            NULL::integer AS "account_alias_id",
            "reporting_ocpazurecostlineitem_project_daily_summary"."service_name" AS "product_code",
            NULL::"text" AS "product_family",
            "reporting_ocpazurecostlineitem_project_daily_summary"."instance_type",
            "reporting_ocpazurecostlineitem_project_daily_summary"."resource_location" AS "region",
            NULL::"text" AS "availability_zone",
            "sum"("reporting_ocpazurecostlineitem_project_daily_summary"."usage_quantity") AS "usage_amount",
            "max"("reporting_ocpazurecostlineitem_project_daily_summary"."unit_of_measure") AS "unit",
            "sum"("reporting_ocpazurecostlineitem_project_daily_summary"."pretax_cost") AS "unblended_cost",
            "sum"("reporting_ocpazurecostlineitem_project_daily_summary"."project_markup_cost") AS "project_markup_cost",
            "sum"("reporting_ocpazurecostlineitem_project_daily_summary"."pod_cost") AS "pod_cost",
            "max"("reporting_ocpazurecostlineitem_project_daily_summary"."currency") AS "currency_code",
            ("max"(("reporting_ocpazurecostlineitem_project_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
           FROM {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary"
          WHERE ("reporting_ocpazurecostlineitem_project_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '2 mons'::interval)))::"date")
          GROUP BY 'Azure'::"text", "reporting_ocpazurecostlineitem_project_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_project_daily_summary"."usage_end", "reporting_ocpazurecostlineitem_project_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_project_daily_summary"."data_source", "reporting_ocpazurecostlineitem_project_daily_summary"."namespace", "reporting_ocpazurecostlineitem_project_daily_summary"."node", "reporting_ocpazurecostlineitem_project_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_project_daily_summary"."resource_id", "reporting_ocpazurecostlineitem_project_daily_summary"."service_name", NULL::"text", "reporting_ocpazurecostlineitem_project_daily_summary"."instance_type", "reporting_ocpazurecostlineitem_project_daily_summary"."resource_location", NULL::"text", "reporting_ocpazurecostlineitem_project_daily_summary"."pod_labels") "lids"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_project_daily_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_compute_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."instance_type", "reporting_ocpawscostlineitem_daily_summary"."resource_id") AS "id",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpawscostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpawscostlineitem_daily_summary"."usage_account_id",
    "max"("reporting_ocpawscostlineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "reporting_ocpawscostlineitem_daily_summary"."instance_type",
    "reporting_ocpawscostlineitem_daily_summary"."resource_id",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_ocpawscostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
  WHERE (("reporting_ocpawscostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date") AND ("reporting_ocpawscostlineitem_daily_summary"."instance_type" IS NOT NULL))
  GROUP BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."instance_type", "reporting_ocpawscostlineitem_daily_summary"."resource_id"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpaws_compute_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id") AS "id",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpawscostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_ocpawscostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
  WHERE ("reporting_ocpawscostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date")
  GROUP BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_account" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id") AS "id",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpawscostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpawscostlineitem_daily_summary"."usage_account_id",
    "max"("reporting_ocpawscostlineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_ocpawscostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
  WHERE ("reporting_ocpawscostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date")
  GROUP BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_account" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_region" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."region", "reporting_ocpawscostlineitem_daily_summary"."availability_zone") AS "id",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpawscostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpawscostlineitem_daily_summary"."usage_account_id",
    "max"("reporting_ocpawscostlineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "reporting_ocpawscostlineitem_daily_summary"."region",
    "reporting_ocpawscostlineitem_daily_summary"."availability_zone",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_ocpawscostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
  WHERE ("reporting_ocpawscostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date")
  GROUP BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."region", "reporting_ocpawscostlineitem_daily_summary"."availability_zone"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_region" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_service" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."product_code", "reporting_ocpawscostlineitem_daily_summary"."product_family") AS "id",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpawscostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpawscostlineitem_daily_summary"."usage_account_id",
    "max"("reporting_ocpawscostlineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "reporting_ocpawscostlineitem_daily_summary"."product_code",
    "reporting_ocpawscostlineitem_daily_summary"."product_family",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_ocpawscostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
  WHERE ("reporting_ocpawscostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date")
  GROUP BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."product_code", "reporting_ocpawscostlineitem_daily_summary"."product_family"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_service" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_database_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."product_code") AS "id",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpawscostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpawscostlineitem_daily_summary"."usage_account_id",
    "max"("reporting_ocpawscostlineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "reporting_ocpawscostlineitem_daily_summary"."product_code",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_ocpawscostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
  WHERE ((("reporting_ocpawscostlineitem_daily_summary"."product_code")::"text" = ANY ((ARRAY['AmazonRDS'::character varying, 'AmazonDynamoDB'::character varying, 'AmazonElastiCache'::character varying, 'AmazonNeptune'::character varying, 'AmazonRedshift'::character varying, 'AmazonDocumentDB'::character varying])::"text"[])) AND ("reporting_ocpawscostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date"))
  GROUP BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."product_code"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpaws_database_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_network_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."product_code") AS "id",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpawscostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpawscostlineitem_daily_summary"."usage_account_id",
    "max"("reporting_ocpawscostlineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "reporting_ocpawscostlineitem_daily_summary"."product_code",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_ocpawscostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
  WHERE ((("reporting_ocpawscostlineitem_daily_summary"."product_code")::"text" = ANY ((ARRAY['AmazonVPC'::character varying, 'AmazonCloudFront'::character varying, 'AmazonRoute53'::character varying, 'AmazonAPIGateway'::character varying])::"text"[])) AND ("reporting_ocpawscostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date"))
  GROUP BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."product_code"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpaws_network_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_storage_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."product_family") AS "id",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start",
    "reporting_ocpawscostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpawscostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpawscostlineitem_daily_summary"."usage_account_id",
    "max"("reporting_ocpawscostlineitem_daily_summary"."account_alias_id") AS "account_alias_id",
    "reporting_ocpawscostlineitem_daily_summary"."product_family",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."usage_amount") AS "usage_amount",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."unit")::"text") AS "unit",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."unblended_cost") AS "unblended_cost",
    "sum"("reporting_ocpawscostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"(("reporting_ocpawscostlineitem_daily_summary"."currency_code")::"text") AS "currency_code",
    ("max"(("reporting_ocpawscostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
  WHERE ((("reporting_ocpawscostlineitem_daily_summary"."product_family")::"text" ~~ '%Storage%'::"text") AND (("reporting_ocpawscostlineitem_daily_summary"."unit")::"text" = 'GB-Mo'::"text") AND ("reporting_ocpawscostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date"))
  GROUP BY "reporting_ocpawscostlineitem_daily_summary"."usage_start", "reporting_ocpawscostlineitem_daily_summary"."cluster_id", "reporting_ocpawscostlineitem_daily_summary"."usage_account_id", "reporting_ocpawscostlineitem_daily_summary"."product_family"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpaws_storage_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpawstags_summary" (
    "uuid" "uuid" NOT NULL,
    "key" character varying(253) NOT NULL,
    "values" "text"[] NOT NULL,
    "usage_account_id" character varying(50),
    "namespace" "text" NOT NULL,
    "node" "text",
    "account_alias_id" integer,
    "cost_entry_bill_id" integer NOT NULL,
    "report_period_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpawstags_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpawstags_values" (
    "uuid" "uuid" NOT NULL,
    "key" "text" NOT NULL,
    "value" "text" NOT NULL,
    "usage_account_ids" "text"[] NOT NULL,
    "account_aliases" "text"[] NOT NULL,
    "cluster_ids" "text"[] NOT NULL,
    "cluster_aliases" "text"[] NOT NULL,
    "namespaces" "text"[] NOT NULL,
    "nodes" "text"[]
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpawstags_values" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_compute_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."instance_type", "reporting_ocpazurecostlineitem_daily_summary"."resource_id") AS "id",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpazurecostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpazurecostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid",
    "reporting_ocpazurecostlineitem_daily_summary"."instance_type",
    "reporting_ocpazurecostlineitem_daily_summary"."resource_id",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."usage_quantity") AS "usage_quantity",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."unit_of_measure") AS "unit_of_measure",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_ocpazurecostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
  WHERE (("reporting_ocpazurecostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date") AND ("reporting_ocpazurecostlineitem_daily_summary"."instance_type" IS NOT NULL) AND ("reporting_ocpazurecostlineitem_daily_summary"."unit_of_measure" = 'Hrs'::"text"))
  GROUP BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."instance_type", "reporting_ocpazurecostlineitem_daily_summary"."resource_id"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazure_compute_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."source_uuid") AS "id",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpazurecostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpazurecostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."currency") AS "currency",
    "reporting_ocpazurecostlineitem_daily_summary"."source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
  WHERE ("reporting_ocpazurecostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date")
  GROUP BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."source_uuid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_account" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid") AS "id",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpazurecostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpazurecostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_ocpazurecostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
  WHERE ("reporting_ocpazurecostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date")
  GROUP BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_account" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_location" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."resource_location") AS "id",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpazurecostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpazurecostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid",
    "reporting_ocpazurecostlineitem_daily_summary"."resource_location",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_ocpazurecostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
  WHERE ("reporting_ocpazurecostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date")
  GROUP BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."resource_location"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_location" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_service" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."service_name") AS "id",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpazurecostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpazurecostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid",
    "reporting_ocpazurecostlineitem_daily_summary"."service_name",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_ocpazurecostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
  WHERE ("reporting_ocpazurecostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date")
  GROUP BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."service_name"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_service" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_database_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."service_name") AS "id",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpazurecostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpazurecostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid",
    "reporting_ocpazurecostlineitem_daily_summary"."service_name",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."usage_quantity") AS "usage_quantity",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."unit_of_measure") AS "unit_of_measure",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_ocpazurecostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
  WHERE (("reporting_ocpazurecostlineitem_daily_summary"."service_name" = ANY (ARRAY['Cosmos DB'::"text", 'Cache for Redis'::"text"])) OR (("reporting_ocpazurecostlineitem_daily_summary"."service_name" ~~* '%database%'::"text") AND ("reporting_ocpazurecostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date")))
  GROUP BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."service_name"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazure_database_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_network_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."service_name") AS "id",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpazurecostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpazurecostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid",
    "reporting_ocpazurecostlineitem_daily_summary"."service_name",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."usage_quantity") AS "usage_quantity",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."unit_of_measure") AS "unit_of_measure",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_ocpazurecostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
  WHERE (("reporting_ocpazurecostlineitem_daily_summary"."service_name" = ANY (ARRAY['Virtual Network'::"text", 'VPN'::"text", 'DNS'::"text", 'Traffic Manager'::"text", 'ExpressRoute'::"text", 'Load Balancer'::"text", 'Application Gateway'::"text"])) AND ("reporting_ocpazurecostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date"))
  GROUP BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."service_name"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazure_network_summary" OWNER TO current_user;

CREATE MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_storage_summary" AS
 SELECT "row_number"() OVER (ORDER BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."service_name") AS "id",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start",
    "reporting_ocpazurecostlineitem_daily_summary"."usage_start" AS "usage_end",
    "reporting_ocpazurecostlineitem_daily_summary"."cluster_id",
    "max"(("reporting_ocpazurecostlineitem_daily_summary"."cluster_alias")::"text") AS "cluster_alias",
    "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid",
    "reporting_ocpazurecostlineitem_daily_summary"."service_name",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."usage_quantity") AS "usage_quantity",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."unit_of_measure") AS "unit_of_measure",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."pretax_cost") AS "pretax_cost",
    "sum"("reporting_ocpazurecostlineitem_daily_summary"."markup_cost") AS "markup_cost",
    "max"("reporting_ocpazurecostlineitem_daily_summary"."currency") AS "currency",
    ("max"(("reporting_ocpazurecostlineitem_daily_summary"."source_uuid")::"text"))::"uuid" AS "source_uuid"
   FROM {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
  WHERE (("reporting_ocpazurecostlineitem_daily_summary"."service_name" ~~ '%Storage%'::"text") AND ("reporting_ocpazurecostlineitem_daily_summary"."unit_of_measure" = 'GB-Mo'::"text") AND ("reporting_ocpazurecostlineitem_daily_summary"."usage_start" >= ("date_trunc"('month'::"text", ("now"() - '1 mon'::interval)))::"date"))
  GROUP BY "reporting_ocpazurecostlineitem_daily_summary"."usage_start", "reporting_ocpazurecostlineitem_daily_summary"."cluster_id", "reporting_ocpazurecostlineitem_daily_summary"."subscription_guid", "reporting_ocpazurecostlineitem_daily_summary"."service_name"
  WITH NO DATA;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazure_storage_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpazuretags_summary" (
    "uuid" "uuid" NOT NULL,
    "key" character varying(253) NOT NULL,
    "values" "text"[] NOT NULL,
    "subscription_guid" "text",
    "namespace" "text" NOT NULL,
    "node" "text",
    "cost_entry_bill_id" integer NOT NULL,
    "report_period_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazuretags_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpazuretags_values" (
    "uuid" "uuid" NOT NULL,
    "key" "text" NOT NULL,
    "value" "text" NOT NULL,
    "subscription_guids" "text"[] NOT NULL,
    "cluster_ids" "text"[] NOT NULL,
    "cluster_aliases" "text"[] NOT NULL,
    "namespaces" "text"[] NOT NULL,
    "nodes" "text"[]
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpazuretags_values" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpcosts_summary" (
    "id" integer NOT NULL,
    "cluster_id" character varying(50),
    "cluster_alias" character varying(256),
    "namespace" character varying(253),
    "pod" character varying(253),
    "node" character varying(253),
    "usage_start" "date" NOT NULL,
    "usage_end" "date" NOT NULL,
    "pod_charge_cpu_core_hours" numeric(27,9),
    "pod_charge_memory_gigabyte_hours" numeric(27,9),
    "persistentvolumeclaim_charge_gb_month" numeric(27,9),
    "infra_cost" numeric(33,15),
    "project_infra_cost" numeric(33,15),
    "markup_cost" numeric(27,9),
    "project_markup_cost" numeric(27,9),
    "pod_labels" "jsonb",
    "monthly_cost" numeric(33,15),
    "report_period_id" integer
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpcosts_summary" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpcosts_summary_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpcosts_summary_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpcosts_summary_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_ocpcosts_summary"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys" (
    "id" bigint NOT NULL,
    "key" character varying(253) NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem" (
    "id" bigint NOT NULL,
    "namespace" character varying(253),
    "namespace_labels" "jsonb",
    "report_id" integer NOT NULL,
    "report_period_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem" (
    "id" bigint NOT NULL,
    "node" character varying(253),
    "node_labels" "jsonb",
    "report_id" integer NOT NULL,
    "report_period_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily" (
    "id" bigint NOT NULL,
    "cluster_id" character varying(50),
    "cluster_alias" character varying(256),
    "node" character varying(253),
    "usage_start" "date" NOT NULL,
    "usage_end" "date" NOT NULL,
    "node_labels" "jsonb",
    "total_seconds" integer NOT NULL,
    "report_period_id" integer
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily"."id";

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem" (
    "id" bigint NOT NULL,
    "namespace" character varying(253) NOT NULL,
    "pod" character varying(253),
    "persistentvolumeclaim" character varying(253) NOT NULL,
    "persistentvolume" character varying(253) NOT NULL,
    "storageclass" character varying(50),
    "persistentvolumeclaim_capacity_bytes" numeric(73,9),
    "persistentvolumeclaim_capacity_byte_seconds" numeric(73,9),
    "volume_request_storage_byte_seconds" numeric(73,9),
    "persistentvolumeclaim_usage_byte_seconds" numeric(73,9),
    "persistentvolume_labels" "jsonb",
    "persistentvolumeclaim_labels" "jsonb",
    "report_id" integer NOT NULL,
    "report_period_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily" (
    "id" bigint NOT NULL,
    "cluster_id" character varying(50),
    "cluster_alias" character varying(256),
    "namespace" character varying(253) NOT NULL,
    "pod" character varying(253),
    "node" character varying(253),
    "persistentvolumeclaim" character varying(253) NOT NULL,
    "persistentvolume" character varying(253) NOT NULL,
    "storageclass" character varying(50),
    "usage_start" "date" NOT NULL,
    "usage_end" "date" NOT NULL,
    "persistentvolumeclaim_capacity_bytes" numeric(73,9),
    "persistentvolumeclaim_capacity_byte_seconds" numeric(73,9),
    "volume_request_storage_byte_seconds" numeric(73,9),
    "persistentvolumeclaim_usage_byte_seconds" numeric(73,9),
    "total_seconds" integer NOT NULL,
    "persistentvolume_labels" "jsonb",
    "persistentvolumeclaim_labels" "jsonb",
    "report_period_id" integer
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily"."id";

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpstoragevolumelabel_summary" (
    "uuid" "uuid" NOT NULL,
    "key" "text" NOT NULL,
    "values" "text"[] NOT NULL,
    "namespace" "text" NOT NULL,
    "node" "text",
    "report_period_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpstoragevolumelabel_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocptags_values" (
    "uuid" "uuid" NOT NULL,
    "key" "text" NOT NULL,
    "value" "text" NOT NULL,
    "cluster_ids" "text"[] NOT NULL,
    "cluster_aliases" "text"[] NOT NULL,
    "namespaces" "text"[] NOT NULL,
    "nodes" "text"[]
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocptags_values" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem" (
    "id" bigint NOT NULL,
    "namespace" character varying(253) NOT NULL,
    "pod" character varying(253) NOT NULL,
    "node" character varying(253) NOT NULL,
    "resource_id" character varying(253),
    "pod_usage_cpu_core_seconds" numeric(73,9),
    "pod_request_cpu_core_seconds" numeric(73,9),
    "pod_limit_cpu_core_seconds" numeric(73,9),
    "pod_usage_memory_byte_seconds" numeric(73,9),
    "pod_request_memory_byte_seconds" numeric(73,9),
    "pod_limit_memory_byte_seconds" numeric(73,9),
    "node_capacity_cpu_cores" numeric(73,9),
    "node_capacity_cpu_core_seconds" numeric(73,9),
    "node_capacity_memory_bytes" numeric(73,9),
    "node_capacity_memory_byte_seconds" numeric(73,9),
    "pod_labels" "jsonb",
    "report_id" integer NOT NULL,
    "report_period_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily" (
    "id" bigint NOT NULL,
    "cluster_id" character varying(50),
    "cluster_alias" character varying(256),
    "namespace" character varying(253) NOT NULL,
    "pod" character varying(253) NOT NULL,
    "node" character varying(253) NOT NULL,
    "resource_id" character varying(253),
    "usage_start" "date" NOT NULL,
    "usage_end" "date" NOT NULL,
    "pod_usage_cpu_core_seconds" numeric(73,9),
    "pod_request_cpu_core_seconds" numeric(73,9),
    "pod_limit_cpu_core_seconds" numeric(73,9),
    "pod_usage_memory_byte_seconds" numeric(73,9),
    "pod_request_memory_byte_seconds" numeric(73,9),
    "pod_limit_memory_byte_seconds" numeric(73,9),
    "node_capacity_cpu_cores" numeric(73,9),
    "node_capacity_cpu_core_seconds" numeric(73,9),
    "node_capacity_memory_bytes" numeric(73,9),
    "node_capacity_memory_byte_seconds" numeric(73,9),
    "cluster_capacity_cpu_core_seconds" numeric(73,9),
    "cluster_capacity_memory_byte_seconds" numeric(73,9),
    "total_seconds" integer NOT NULL,
    "pod_labels" "jsonb",
    "report_period_id" integer
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default" (
    "cluster_id" character varying(50),
    "cluster_alias" character varying(256),
    "data_source" character varying(64),
    "namespace" character varying(253),
    "node" character varying(253),
    "resource_id" character varying(253),
    "usage_start" "date" NOT NULL,
    "usage_end" "date" NOT NULL,
    "pod_labels" "jsonb",
    "pod_usage_cpu_core_hours" numeric(18,6),
    "pod_request_cpu_core_hours" numeric(18,6),
    "pod_limit_cpu_core_hours" numeric(18,6),
    "pod_usage_memory_gigabyte_hours" numeric(18,6),
    "pod_request_memory_gigabyte_hours" numeric(18,6),
    "pod_limit_memory_gigabyte_hours" numeric(18,6),
    "node_capacity_cpu_cores" numeric(18,6),
    "node_capacity_cpu_core_hours" numeric(18,6),
    "node_capacity_memory_gigabytes" numeric(18,6),
    "node_capacity_memory_gigabyte_hours" numeric(18,6),
    "cluster_capacity_cpu_core_hours" numeric(18,6),
    "cluster_capacity_memory_gigabyte_hours" numeric(18,6),
    "persistentvolumeclaim" character varying(253),
    "persistentvolume" character varying(253),
    "storageclass" character varying(50),
    "volume_labels" "jsonb",
    "persistentvolumeclaim_capacity_gigabyte" numeric(18,6),
    "persistentvolumeclaim_capacity_gigabyte_months" numeric(18,6),
    "volume_request_storage_gigabyte_months" numeric(18,6),
    "persistentvolumeclaim_usage_gigabyte_months" numeric(18,6),
    "infrastructure_raw_cost" numeric(33,15),
    "infrastructure_project_raw_cost" numeric(33,15),
    "infrastructure_usage_cost" "jsonb",
    "infrastructure_markup_cost" numeric(33,15),
    "infrastructure_project_markup_cost" numeric(33,15),
    "infrastructure_monthly_cost" numeric(33,15),
    "supplementary_usage_cost" "jsonb",
    "supplementary_monthly_cost" numeric(33,15),
    "monthly_cost_type" "text",
    "source_uuid" "uuid",
    "report_period_id" integer,
    "uuid" "uuid" NOT NULL,
    "supplementary_monthly_cost_json" "jsonb",
    "infrastructure_monthly_cost_json" "jsonb",
    "supplementary_project_monthly_cost" "jsonb",
    "infrastructure_project_monthly_cost" "jsonb"
);
ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default" DEFAULT;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpusagepodlabel_summary" (
    "uuid" "uuid" NOT NULL,
    "key" "text" NOT NULL,
    "values" "text"[] NOT NULL,
    "namespace" "text" NOT NULL,
    "node" "text",
    "report_period_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagepodlabel_summary" OWNER TO current_user;

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpusagereport" (
    "id" integer NOT NULL,
    "interval_start" timestamp with time zone NOT NULL,
    "interval_end" timestamp with time zone NOT NULL,
    "report_period_id" integer NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagereport" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpusagereport_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagereport_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpusagereport_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_ocpusagereport"."id";

CREATE TABLE {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod" (
    "id" integer NOT NULL,
    "cluster_id" character varying(50) NOT NULL,
    "cluster_alias" character varying(256),
    "report_period_start" timestamp with time zone NOT NULL,
    "report_period_end" timestamp with time zone NOT NULL,
    "summary_data_creation_datetime" timestamp with time zone,
    "summary_data_updated_datetime" timestamp with time zone,
    "derived_cost_datetime" timestamp with time zone,
    "provider_id" "uuid" NOT NULL
);

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod" OWNER TO current_user;

CREATE SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod_id_seq" OWNER TO current_user;

ALTER SEQUENCE {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod_id_seq" OWNED BY {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"."id";

ALTER TABLE ONLY {{schema_name | sqlsafe}}."partitioned_tables" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."partitioned_tables_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awsaccountalias" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_awsaccountalias_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentry" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_awscostentry_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrybill" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_awscostentrybill_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_awscostentrylineitem_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrypricing" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_awscostentrypricing_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentryproduct" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_awscostentryproduct_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentryreservation" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_awscostentryreservation_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awsorganizationalunit" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_awsorganizationalunit_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrybill" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_azurecostentrybill_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_azurecostentryproductservice_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azureenabledtagkeys" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_azureenabledtagkeys_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azuremeter" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_azuremeter_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrybill" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_gcpcostentrybill_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpproject" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_gcpproject_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpcosts_summary" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_ocpcosts_summary_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_ocpusagelineitem_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagereport" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_ocpusagereport_id_seq"'::"regclass");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod" ALTER COLUMN "id" SET DEFAULT "nextval"('{{schema_name | sqlsafe}}."reporting_ocpusagereportperiod_id_seq"'::"regclass");

INSERT INTO {{schema_name | sqlsafe}}."partitioned_tables" (schema_name, table_name, partition_of_table_name, partition_type, partition_col, partition_parameters, active, subpartition_type, subpartition_col)
VALUES
('template0', 'reporting_ocpusagelineitem_daily_summary_default', 'reporting_ocpusagelineitem_daily_summary', 'range', 'usage_start', '{"default": true}', true, NULL, NULL),
('template0', 'reporting_awscostentrylineitem_daily_summary_default', 'reporting_awscostentrylineitem_daily_summary', 'range', 'usage_start', '{"default": true}', true, NULL, NULL),
('template0', 'reporting_azurecostentrylineitem_daily_summary_default', 'reporting_azurecostentrylineitem_daily_summary', 'range', 'usage_start', '{"default": true}', true, NULL, NULL),
('template0', 'reporting_gcpcostentrylineitem_daily_summary_default', 'reporting_gcpcostentrylineitem_daily_summary', 'range', 'usage_start', '{"default": true}', true, NULL, NULL)
;

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."partitioned_tables_id_seq"', 4, true);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_awsaccountalias_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_awscostentry_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_awscostentrybill_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_awscostentrylineitem_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_awscostentrypricing_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_awscostentryproduct_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_awscostentryreservation_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_awsorganizationalunit_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_azurecostentrybill_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_azurecostentryproductservice_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_azureenabledtagkeys_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_azuremeter_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_gcpcostentrybill_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_gcpproject_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_ocpcosts_summary_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_ocpusagelineitem_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_ocpusagereport_id_seq"', 1, false);

SELECT pg_catalog.setval('{{schema_name | sqlsafe}}."reporting_ocpusagereportperiod_id_seq"', 1, false);

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
    ADD CONSTRAINT "p_reporting_gcpcostentrylineitem_daily_summary_pkey" PRIMARY KEY ("usage_start", "uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."partitioned_tables"
    ADD CONSTRAINT "partitioned_tables_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."partitioned_tables"
    ADD CONSTRAINT "partitioned_tables_schema_name_table_name_5f95f299_uniq" UNIQUE ("schema_name", "table_name");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."presto_delete_wrapper_log"
    ADD CONSTRAINT "presto_delete_wrapper_log_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awsaccountalias"
    ADD CONSTRAINT "reporting_awsaccountalias_account_id_key" UNIQUE ("account_id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awsaccountalias"
    ADD CONSTRAINT "reporting_awsaccountalias_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentry"
    ADD CONSTRAINT "reporting_awscostentry_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrybill"
    ADD CONSTRAINT "reporting_awscostentrybi_bill_type_payer_account__6f101061_uniq" UNIQUE ("bill_type", "payer_account_id", "billing_period_start", "provider_id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrybill"
    ADD CONSTRAINT "reporting_awscostentrybill_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily"
    ADD CONSTRAINT "reporting_awscostentrylineitem_daily_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
    ADD CONSTRAINT "reporting_awscostentrylineitem_daily_summary_pkey" PRIMARY KEY ("usage_start", "uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default"
    ADD CONSTRAINT "reporting_awscostentrylineitem_daily_summary_default_pkey" PRIMARY KEY ("usage_start", "uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem"
    ADD CONSTRAINT "reporting_awscostentrylineitem_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentryproduct"
    ADD CONSTRAINT "reporting_awscostentrypr_sku_product_name_region_fea902ae_uniq" UNIQUE ("sku", "product_name", "region");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrypricing"
    ADD CONSTRAINT "reporting_awscostentrypricing_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrypricing"
    ADD CONSTRAINT "reporting_awscostentrypricing_term_unit_c3978af3_uniq" UNIQUE ("term", "unit");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentryproduct"
    ADD CONSTRAINT "reporting_awscostentryproduct_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentryreservation"
    ADD CONSTRAINT "reporting_awscostentryreservation_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentryreservation"
    ADD CONSTRAINT "reporting_awscostentryreservation_reservation_arn_key" UNIQUE ("reservation_arn");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awsenabledtagkeys"
    ADD CONSTRAINT "reporting_awsenabledtagkeys_key_8c2841c2_pk" PRIMARY KEY ("key");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awsorganizationalunit"
    ADD CONSTRAINT "reporting_awsorganizationalunit_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awstags_summary"
    ADD CONSTRAINT "reporting_awstags_summar_key_cost_entry_bill_id_u_1f71e435_uniq" UNIQUE ("key", "cost_entry_bill_id", "usage_account_id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awstags_summary"
    ADD CONSTRAINT "reporting_awstags_summary_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awstags_values"
    ADD CONSTRAINT "reporting_awstags_values_key_value_56d23b8e_uniq" UNIQUE ("key", "value");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awstags_values"
    ADD CONSTRAINT "reporting_awstags_values_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrybill"
    ADD CONSTRAINT "reporting_azurecostentry_billing_period_start_pro_c99ba20a_uniq" UNIQUE ("billing_period_start", "provider_id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice"
    ADD CONSTRAINT "reporting_azurecostentry_instance_id_instance_typ_44f8ec94_uniq" UNIQUE ("instance_id", "instance_type", "service_tier", "service_name");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrybill"
    ADD CONSTRAINT "reporting_azurecostentrybill_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily"
    ADD CONSTRAINT "reporting_azurecostentrylineitem_daily_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
    ADD CONSTRAINT "reporting_azurecostentrylineitem_daily_summary_pkey" PRIMARY KEY ("usage_start", "uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_default"
    ADD CONSTRAINT "reporting_azurecostentrylineitem_daily_summary_default_pkey" PRIMARY KEY ("usage_start", "uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice"
    ADD CONSTRAINT "reporting_azurecostentryproductservice_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azureenabledtagkeys"
    ADD CONSTRAINT "reporting_azureenabledtagkeys_key_key" UNIQUE ("key");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azureenabledtagkeys"
    ADD CONSTRAINT "reporting_azureenabledtagkeys_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azuremeter"
    ADD CONSTRAINT "reporting_azuremeter_meter_id_key" UNIQUE ("meter_id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azuremeter"
    ADD CONSTRAINT "reporting_azuremeter_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azuretags_summary"
    ADD CONSTRAINT "reporting_azuretags_summ_key_cost_entry_bill_id_s_bf83e989_uniq" UNIQUE ("key", "cost_entry_bill_id", "subscription_guid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azuretags_summary"
    ADD CONSTRAINT "reporting_azuretags_summary_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azuretags_values"
    ADD CONSTRAINT "reporting_azuretags_values_key_value_bb8b5dff_uniq" UNIQUE ("key", "value");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azuretags_values"
    ADD CONSTRAINT "reporting_azuretags_values_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrybill"
    ADD CONSTRAINT "reporting_gcpcostentrybi_billing_period_start_pro_f84030ae_uniq" UNIQUE ("billing_period_start", "provider_id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrybill"
    ADD CONSTRAINT "reporting_gcpcostentrybill_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily"
    ADD CONSTRAINT "reporting_gcpcostentrylineitem_daily_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default"
    ADD CONSTRAINT "reporting_gcpcostentrylineitem_daily_summary_default_pkey" PRIMARY KEY ("usage_start", "uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem"
    ADD CONSTRAINT "reporting_gcpcostentrylineitem_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice"
    ADD CONSTRAINT "reporting_gcpcostentrypr_service_id_service_alias_47942f37_uniq" UNIQUE ("service_id", "service_alias", "sku_id", "sku_alias");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice"
    ADD CONSTRAINT "reporting_gcpcostentryproductservice_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys"
    ADD CONSTRAINT "reporting_gcpenabledtagkeys_key_key" UNIQUE ("key");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys"
    ADD CONSTRAINT "reporting_gcpenabledtagkeys_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpproject"
    ADD CONSTRAINT "reporting_gcpproject_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpproject"
    ADD CONSTRAINT "reporting_gcpproject_project_id_key" UNIQUE ("project_id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcptags_summary"
    ADD CONSTRAINT "reporting_gcptags_summar_key_cost_entry_bill_id_a_a0ec79e3_uniq" UNIQUE ("key", "cost_entry_bill_id", "account_id", "project_id", "project_name");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcptags_summary"
    ADD CONSTRAINT "reporting_gcptags_summary_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcptags_values"
    ADD CONSTRAINT "reporting_gcptags_values_key_value_dfee3462_uniq" UNIQUE ("key", "value");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcptags_values"
    ADD CONSTRAINT "reporting_gcptags_values_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocp_clusters"
    ADD CONSTRAINT "reporting_ocp_clusters_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocp_nodes"
    ADD CONSTRAINT "reporting_ocp_nodes_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocp_projects"
    ADD CONSTRAINT "reporting_ocp_projects_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocp_pvcs"
    ADD CONSTRAINT "reporting_ocp_pvcs_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary"
    ADD CONSTRAINT "reporting_ocpawscostline_uuid_9afa8623_uniq" UNIQUE ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary"
    ADD CONSTRAINT "reporting_ocpawscostlinei_uuid_9afa8623_pk" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
    ADD CONSTRAINT "reporting_ocpawscostlineitem_daily_summary_uuid_3d5dc959_pk" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
    ADD CONSTRAINT "reporting_ocpawscostlineitem_daily_summary_uuid_3d5dc959_uniq" UNIQUE ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawstags_summary"
    ADD CONSTRAINT "reporting_ocpawstags_sum_key_cost_entry_bill_id_r_00bc8a3b_uniq" UNIQUE ("key", "cost_entry_bill_id", "report_period_id", "usage_account_id", "namespace", "node");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawstags_summary"
    ADD CONSTRAINT "reporting_ocpawstags_summary_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawstags_values"
    ADD CONSTRAINT "reporting_ocpawstags_values_key_value_1efa08ea_uniq" UNIQUE ("key", "value");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawstags_values"
    ADD CONSTRAINT "reporting_ocpawstags_values_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary"
    ADD CONSTRAINT "reporting_ocpazurecostli_uuid_1cf2074c_uniq" UNIQUE ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary"
    ADD CONSTRAINT "reporting_ocpazurecostlin_uuid_1cf2074c_pk" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
    ADD CONSTRAINT "reporting_ocpazurecostlineitem_daily_summary_uuid_4063f4f5_pk" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
    ADD CONSTRAINT "reporting_ocpazurecostlineitem_daily_summary_uuid_4063f4f5_uniq" UNIQUE ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazuretags_summary"
    ADD CONSTRAINT "reporting_ocpazuretags_s_key_cost_entry_bill_id_r_7fb461bc_uniq" UNIQUE ("key", "cost_entry_bill_id", "report_period_id", "subscription_guid", "namespace", "node");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazuretags_summary"
    ADD CONSTRAINT "reporting_ocpazuretags_summary_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazuretags_values"
    ADD CONSTRAINT "reporting_ocpazuretags_values_key_value_306fdd41_uniq" UNIQUE ("key", "value");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazuretags_values"
    ADD CONSTRAINT "reporting_ocpazuretags_values_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpcosts_summary"
    ADD CONSTRAINT "reporting_ocpcosts_summary_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys"
    ADD CONSTRAINT "reporting_ocpenabledtagkeys_key_key" UNIQUE ("key");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys"
    ADD CONSTRAINT "reporting_ocpenabledtagkeys_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem"
    ADD CONSTRAINT "reporting_ocpnamespacela_report_id_namespace_00f2972c_uniq" UNIQUE ("report_id", "namespace");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem"
    ADD CONSTRAINT "reporting_ocpnamespacelabellineitem_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily"
    ADD CONSTRAINT "reporting_ocpnodelabellineitem_daily_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem"
    ADD CONSTRAINT "reporting_ocpnodelabellineitem_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem"
    ADD CONSTRAINT "reporting_ocpnodelabellineitem_report_id_node_babd91c2_uniq" UNIQUE ("report_id", "node");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem"
    ADD CONSTRAINT "reporting_ocpstorageline_report_id_namespace_pers_9bf00103_uniq" UNIQUE ("report_id", "namespace", "persistentvolumeclaim");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily"
    ADD CONSTRAINT "reporting_ocpstoragelineitem_daily_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem"
    ADD CONSTRAINT "reporting_ocpstoragelineitem_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpstoragevolumelabel_summary"
    ADD CONSTRAINT "reporting_ocpstoragevolu_key_report_period_id_nam_17bc3852_uniq" UNIQUE ("key", "report_period_id", "namespace", "node");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpstoragevolumelabel_summary"
    ADD CONSTRAINT "reporting_ocpstoragevolumelabel_summary_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocptags_values"
    ADD CONSTRAINT "reporting_ocptags_values_key_value_135d8752_uniq" UNIQUE ("key", "value");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocptags_values"
    ADD CONSTRAINT "reporting_ocptags_values_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem"
    ADD CONSTRAINT "reporting_ocpusagelineit_report_id_namespace_pod__dfc2c342_uniq" UNIQUE ("report_id", "namespace", "pod", "node");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily"
    ADD CONSTRAINT "reporting_ocpusagelineitem_daily_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary"
    ADD CONSTRAINT "reporting_ocpusagelineitem_daily_summary_pkey" PRIMARY KEY ("usage_start", "uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default"
    ADD CONSTRAINT "reporting_ocpusagelineitem_daily_summary_default_pkey" PRIMARY KEY ("usage_start", "uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem"
    ADD CONSTRAINT "reporting_ocpusagelineitem_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagepodlabel_summary"
    ADD CONSTRAINT "reporting_ocpusagepodlab_key_report_period_id_nam_8284236c_uniq" UNIQUE ("key", "report_period_id", "namespace", "node");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagepodlabel_summary"
    ADD CONSTRAINT "reporting_ocpusagepodlabel_summary_pkey" PRIMARY KEY ("uuid");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"
    ADD CONSTRAINT "reporting_ocpusagereport_cluster_id_report_period_ff3ea314_uniq" UNIQUE ("cluster_id", "report_period_start", "provider_id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagereport"
    ADD CONSTRAINT "reporting_ocpusagereport_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagereport"
    ADD CONSTRAINT "reporting_ocpusagereport_report_period_id_interva_066551f3_uniq" UNIQUE ("report_period_id", "interval_start");

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"
    ADD CONSTRAINT "reporting_ocpusagereportperiod_pkey" PRIMARY KEY ("id");

CREATE UNIQUE INDEX "aws_compute_summary" ON {{schema_name | sqlsafe}}."reporting_aws_compute_summary" USING "btree" ("usage_start", "source_uuid", "instance_type");

CREATE UNIQUE INDEX "aws_compute_summary_account" ON {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_account" USING "btree" ("usage_start", "usage_account_id", "account_alias_id", "instance_type");

CREATE UNIQUE INDEX "aws_compute_summary_region" ON {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_region" USING "btree" ("usage_start", "usage_account_id", "region", "availability_zone", "instance_type");

CREATE UNIQUE INDEX "aws_compute_summary_service" ON {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_service" USING "btree" ("usage_start", "usage_account_id", "product_code", "product_family", "instance_type");

CREATE INDEX "aws_cost_entry" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" USING "gin" ("tags");

CREATE INDEX "aws_cost_pcode_like" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" USING "gin" ("product_code" "public"."gin_trgm_ops");

CREATE UNIQUE INDEX "aws_cost_summary" ON {{schema_name | sqlsafe}}."reporting_aws_cost_summary" USING "btree" ("usage_start", "source_uuid");

CREATE UNIQUE INDEX "aws_cost_summary_account" ON {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_account" USING "btree" ("usage_start", "usage_account_id");

CREATE UNIQUE INDEX "aws_cost_summary_region" ON {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_region" USING "btree" ("usage_start", "usage_account_id", "region", "availability_zone");

CREATE UNIQUE INDEX "aws_cost_summary_service" ON {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_service" USING "btree" ("usage_start", "usage_account_id", "product_code", "product_family");

CREATE UNIQUE INDEX "aws_database_summary" ON {{schema_name | sqlsafe}}."reporting_aws_database_summary" USING "btree" ("usage_start", "usage_account_id", "product_code");

CREATE INDEX "aws_enabled_key_index" ON {{schema_name | sqlsafe}}."reporting_awsenabledtagkeys" USING "btree" ("key", "enabled");

CREATE UNIQUE INDEX "aws_network_summary" ON {{schema_name | sqlsafe}}."reporting_aws_network_summary" USING "btree" ("usage_start", "usage_account_id", "product_code");

CREATE UNIQUE INDEX "aws_storage_summary" ON {{schema_name | sqlsafe}}."reporting_aws_storage_summary" USING "btree" ("usage_start", "source_uuid", "product_family");

CREATE UNIQUE INDEX "aws_storage_summary_account" ON {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_account" USING "btree" ("usage_start", "usage_account_id", "product_family");

CREATE UNIQUE INDEX "aws_storage_summary_region" ON {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_region" USING "btree" ("usage_start", "usage_account_id", "region", "availability_zone", "product_family");

CREATE UNIQUE INDEX "aws_storage_summary_service" ON {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_service" USING "btree" ("usage_start", "usage_account_id", "product_code", "product_family");

CREATE INDEX "aws_summ_usage_pcode_ilike" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "gin" ("upper"(("product_family")::"text") "public"."gin_trgm_ops");

CREATE INDEX "aws_summ_usage_pfam_ilike" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "gin" ("upper"(("product_family")::"text") "public"."gin_trgm_ops");

CREATE INDEX "aws_tags_value_key_idx" ON {{schema_name | sqlsafe}}."reporting_awstags_values" USING "btree" ("key");

CREATE UNIQUE INDEX "azure_compute_summary" ON {{schema_name | sqlsafe}}."reporting_azure_compute_summary" USING "btree" ("usage_start", "subscription_guid", "instance_type");

CREATE UNIQUE INDEX "azure_cost_summary" ON {{schema_name | sqlsafe}}."reporting_azure_cost_summary" USING "btree" ("usage_start", "source_uuid");

CREATE UNIQUE INDEX "azure_cost_summary_account" ON {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_account" USING "btree" ("usage_start", "subscription_guid");

CREATE UNIQUE INDEX "azure_cost_summary_location" ON {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_location" USING "btree" ("usage_start", "subscription_guid", "resource_location");

CREATE UNIQUE INDEX "azure_cost_summary_service" ON {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_service" USING "btree" ("usage_start", "subscription_guid", "service_name");

CREATE UNIQUE INDEX "azure_database_summary" ON {{schema_name | sqlsafe}}."reporting_azure_database_summary" USING "btree" ("usage_start", "subscription_guid", "service_name");

CREATE UNIQUE INDEX "azure_network_summary" ON {{schema_name | sqlsafe}}."reporting_azure_network_summary" USING "btree" ("usage_start", "subscription_guid", "service_name");

CREATE UNIQUE INDEX "azure_storage_summary" ON {{schema_name | sqlsafe}}."reporting_azure_storage_summary" USING "btree" ("usage_start", "subscription_guid", "service_name");

CREATE INDEX "azure_tags_value_key_idx" ON {{schema_name | sqlsafe}}."reporting_azuretags_values" USING "btree" ("key");

CREATE INDEX "cost__proj_sum_namespace_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "btree" ("namespace" "varchar_pattern_ops");

CREATE INDEX "cost__proj_sum_namespace_like_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "gin" ("upper"(("namespace")::"text") "public"."gin_trgm_ops");

CREATE INDEX "cost__proj_sum_node_like_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "gin" ("upper"(("node")::"text") "public"."gin_trgm_ops");

CREATE INDEX "cost_proj_pod_labels_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "gin" ("pod_labels");

CREATE INDEX "cost_proj_sum_node_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "btree" ("node" "varchar_pattern_ops");

CREATE INDEX "cost_proj_sum_ocp_usage_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "btree" ("usage_start");

CREATE INDEX "cost_proj_sum_resource_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "btree" ("resource_id");

CREATE INDEX "cost_summary_namespace_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "btree" ("namespace");

CREATE INDEX "cost_summary_node_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "btree" ("node" "varchar_pattern_ops");

CREATE INDEX "cost_summary_node_like_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "gin" ("upper"(("node")::"text") "public"."gin_trgm_ops");

CREATE INDEX "cost_summary_ocp_usage_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "btree" ("usage_start");

CREATE INDEX "cost_summary_resource_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "btree" ("resource_id");

CREATE INDEX "cost_tags_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "gin" ("tags");

CREATE UNIQUE INDEX "gcp_compute_summary" ON {{schema_name | sqlsafe}}."reporting_gcp_compute_summary" USING "btree" ("usage_start", "source_uuid", "instance_type", "invoice_month");

CREATE UNIQUE INDEX "gcp_compute_summary_account" ON {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_account" USING "btree" ("usage_start", "instance_type", "account_id", "invoice_month");

CREATE UNIQUE INDEX "gcp_compute_summary_project" ON {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_project" USING "btree" ("usage_start", "instance_type", "project_id", "project_name", "account_id", "invoice_month");

CREATE UNIQUE INDEX "gcp_compute_summary_region" ON {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_region" USING "btree" ("usage_start", "instance_type", "account_id", "region", "invoice_month");

CREATE UNIQUE INDEX "gcp_compute_summary_service" ON {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_service" USING "btree" ("usage_start", "instance_type", "account_id", "service_id", "service_alias", "invoice_month");

CREATE INDEX "gcp_cost_entry" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily" USING "gin" ("tags");

CREATE UNIQUE INDEX "gcp_cost_summary" ON {{schema_name | sqlsafe}}."reporting_gcp_cost_summary" USING "btree" ("usage_start", "source_uuid", "invoice_month");

CREATE UNIQUE INDEX "gcp_cost_summary_account" ON {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_account" USING "btree" ("usage_start", "account_id", "invoice_month");

CREATE UNIQUE INDEX "gcp_cost_summary_project" ON {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_project" USING "btree" ("usage_start", "project_id", "project_name", "account_id", "invoice_month");

CREATE UNIQUE INDEX "gcp_cost_summary_region" ON {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_region" USING "btree" ("usage_start", "account_id", "region", "invoice_month");

CREATE UNIQUE INDEX "gcp_cost_summary_service" ON {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_service" USING "btree" ("usage_start", "account_id", "service_id", "service_alias", "invoice_month");

CREATE UNIQUE INDEX "gcp_database_summary" ON {{schema_name | sqlsafe}}."reporting_gcp_database_summary" USING "btree" ("usage_start", "account_id", "service_id", "service_alias", "invoice_month");

CREATE UNIQUE INDEX "gcp_network_summary" ON {{schema_name | sqlsafe}}."reporting_gcp_network_summary" USING "btree" ("usage_start", "account_id", "service_id", "service_alias", "invoice_month");

CREATE UNIQUE INDEX "gcp_storage_summary" ON {{schema_name | sqlsafe}}."reporting_gcp_storage_summary" USING "btree" ("usage_start", "source_uuid", "invoice_month");

CREATE UNIQUE INDEX "gcp_storage_summary_account" ON {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_account" USING "btree" ("usage_start", "account_id", "invoice_month");

CREATE UNIQUE INDEX "gcp_storage_summary_project" ON {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_project" USING "btree" ("usage_start", "project_id", "project_name", "account_id", "invoice_month");

CREATE UNIQUE INDEX "gcp_storage_summary_region" ON {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_region" USING "btree" ("usage_start", "account_id", "region", "invoice_month");

CREATE UNIQUE INDEX "gcp_storage_summary_service" ON {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_service" USING "btree" ("usage_start", "account_id", "service_id", "service_alias", "invoice_month");

CREATE INDEX "gcp_tags_value_key_idx" ON {{schema_name | sqlsafe}}."reporting_gcptags_values" USING "btree" ("key");

CREATE INDEX "gcp_usage_start_idx" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily" USING "btree" ("usage_start");

CREATE INDEX "interval_start_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentry" USING "btree" ("interval_start");

CREATE INDEX "ix_azure_costentrydlysumm_service_name" ON ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary" USING "gin" ("upper"("service_name") "public"."gin_trgm_ops");

CREATE INDEX "ix_ocp_aws_product_code_ilike" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "gin" ("upper"(("product_code")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ix_ocp_aws_product_family_ilike" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "gin" ("upper"(("product_family")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ix_ocpazure_service_name_ilike" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" USING "gin" ("upper"("service_name") "public"."gin_trgm_ops");

CREATE INDEX "namespace_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily" USING "btree" ("namespace" "varchar_pattern_ops");

CREATE INDEX "node_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily" USING "btree" ("node" "varchar_pattern_ops");

CREATE INDEX "ocp_aws_instance_type_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "btree" ("instance_type");

CREATE INDEX "ocp_aws_product_family_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "btree" ("product_family");

CREATE INDEX "ocp_aws_proj_inst_type_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "btree" ("instance_type");

CREATE INDEX "ocp_aws_proj_prod_fam_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "btree" ("product_family");

CREATE INDEX "ocp_aws_tags_value_key_idx" ON {{schema_name | sqlsafe}}."reporting_ocpawstags_values" USING "btree" ("key");

CREATE INDEX "ocp_azure_tags_value_key_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazuretags_values" USING "btree" ("key");

CREATE UNIQUE INDEX "ocp_cost_summary" ON {{schema_name | sqlsafe}}."reporting_ocp_cost_summary" USING "btree" ("usage_start", "cluster_id", "cluster_alias", "source_uuid");

CREATE UNIQUE INDEX "ocp_cost_summary_by_node" ON {{schema_name | sqlsafe}}."reporting_ocp_cost_summary_by_node" USING "btree" ("usage_start", "cluster_id", "cluster_alias", "node", "source_uuid");

CREATE UNIQUE INDEX "ocp_cost_summary_by_project" ON {{schema_name | sqlsafe}}."reporting_ocp_cost_summary_by_project" USING "btree" ("usage_start", "cluster_id", "cluster_alias", "namespace", "source_uuid");

CREATE INDEX "ocp_interval_start_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagereport" USING "btree" ("interval_start");

CREATE INDEX "ocp_namespace_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily" USING "gin" ("upper"(("namespace")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ocp_node_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily" USING "gin" ("upper"(("node")::"text") "public"."gin_trgm_ops");

CREATE UNIQUE INDEX "ocp_pod_summary" ON {{schema_name | sqlsafe}}."reporting_ocp_pod_summary" USING "btree" ("usage_start", "cluster_id", "cluster_alias", "source_uuid");

CREATE UNIQUE INDEX "ocp_pod_summary_by_project" ON {{schema_name | sqlsafe}}."reporting_ocp_pod_summary_by_project" USING "btree" ("usage_start", "cluster_id", "cluster_alias", "namespace", "source_uuid");

CREATE INDEX "ocp_storage_li_namespace_idx" ON {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily" USING "btree" ("namespace" "varchar_pattern_ops");

CREATE INDEX "ocp_storage_li_namespace_like_idx" ON {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily" USING "gin" ("upper"(("namespace")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ocp_storage_li_node_idx" ON {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily" USING "btree" ("node" "varchar_pattern_ops");

CREATE INDEX "ocp_storage_li_node_like_idx" ON {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily" USING "gin" ("upper"(("node")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ocp_summary_namespace_like_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary" USING "gin" ("upper"(("namespace")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ocp_summary_node_like_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary" USING "gin" ("upper"(("node")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ocp_usage_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily" USING "btree" ("usage_start");

CREATE UNIQUE INDEX "ocp_volume_summary" ON {{schema_name | sqlsafe}}."reporting_ocp_volume_summary" USING "btree" ("usage_start", "cluster_id", "cluster_alias", "source_uuid");

CREATE UNIQUE INDEX "ocp_volume_summary_by_project" ON {{schema_name | sqlsafe}}."reporting_ocp_volume_summary_by_project" USING "btree" ("usage_start", "cluster_id", "cluster_alias", "namespace", "source_uuid");

CREATE UNIQUE INDEX "ocpall_compute_summary" ON {{schema_name | sqlsafe}}."reporting_ocpall_compute_summary" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "product_code", "instance_type", "resource_id");

CREATE UNIQUE INDEX "ocpall_cost_daily_summary" ON {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary" USING "btree" ("source_type", "cluster_id", "namespace_hash", "node", "resource_id", "usage_start", "usage_account_id", "product_code", "product_family", "instance_type", "region", "availability_zone", "tags_hash");

CREATE UNIQUE INDEX "ocpall_cost_project_daily_summary" ON {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_project_daily_summary" USING "btree" ("source_type", "usage_start", "cluster_id", "data_source", "namespace", "node", "usage_account_id", "resource_id", "product_code", "product_family", "instance_type", "region", "availability_zone", "pod_labels");

CREATE UNIQUE INDEX "ocpall_cost_summary" ON {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary" USING "btree" ("usage_start", "cluster_id", "source_uuid");

CREATE UNIQUE INDEX "ocpall_cost_summary_account" ON {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_account" USING "btree" ("usage_start", "cluster_id", "usage_account_id");

CREATE UNIQUE INDEX "ocpall_cost_summary_region" ON {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_region" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "region", "availability_zone");

CREATE UNIQUE INDEX "ocpall_cost_summary_service" ON {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_service" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "product_code", "product_family");

CREATE UNIQUE INDEX "ocpall_database_summary" ON {{schema_name | sqlsafe}}."reporting_ocpall_database_summary" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "product_code");

CREATE UNIQUE INDEX "ocpall_network_summary" ON {{schema_name | sqlsafe}}."reporting_ocpall_network_summary" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "product_code");

CREATE INDEX "ocpall_product_code_ilike" ON {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary" USING "gin" ("upper"(("product_code")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ocpall_product_family_ilike" ON {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary" USING "gin" ("upper"(("product_family")::"text") "public"."gin_trgm_ops");

CREATE UNIQUE INDEX "ocpall_storage_summary" ON {{schema_name | sqlsafe}}."reporting_ocpall_storage_summary" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "product_family", "product_code");

CREATE INDEX "ocpallcstdlysumm_node" ON {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary" USING "btree" ("node" "text_pattern_ops");

CREATE INDEX "ocpallcstdlysumm_node_like" ON {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary" USING "gin" ("node" "public"."gin_trgm_ops");

CREATE INDEX "ocpallcstdlysumm_nsp" ON {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary" USING "gin" ("namespace");

CREATE INDEX "ocpallcstprjdlysumm_node" ON {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_project_daily_summary" USING "btree" ("node" "text_pattern_ops");

CREATE INDEX "ocpallcstprjdlysumm_node_like" ON {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_project_daily_summary" USING "gin" ("node" "public"."gin_trgm_ops");

CREATE INDEX "ocpallcstprjdlysumm_nsp" ON {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_project_daily_summary" USING "btree" ("namespace" "text_pattern_ops");

CREATE INDEX "ocpallcstprjdlysumm_nsp_like" ON {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_project_daily_summary" USING "gin" ("namespace" "public"."gin_trgm_ops");

CREATE UNIQUE INDEX "ocpaws_compute_summary" ON {{schema_name | sqlsafe}}."reporting_ocpaws_compute_summary" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "instance_type", "resource_id");

CREATE UNIQUE INDEX "ocpaws_cost_summary" ON {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary" USING "btree" ("usage_start", "cluster_id");

CREATE UNIQUE INDEX "ocpaws_cost_summary_account" ON {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_account" USING "btree" ("usage_start", "cluster_id", "usage_account_id");

CREATE UNIQUE INDEX "ocpaws_cost_summary_region" ON {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_region" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "region", "availability_zone");

CREATE UNIQUE INDEX "ocpaws_cost_summary_service" ON {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_service" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "product_code", "product_family");

CREATE UNIQUE INDEX "ocpaws_database_summary" ON {{schema_name | sqlsafe}}."reporting_ocpaws_database_summary" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "product_code");

CREATE UNIQUE INDEX "ocpaws_network_summary" ON {{schema_name | sqlsafe}}."reporting_ocpaws_network_summary" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "product_code");

CREATE UNIQUE INDEX "ocpaws_storage_summary" ON {{schema_name | sqlsafe}}."reporting_ocpaws_storage_summary" USING "btree" ("usage_start", "cluster_id", "usage_account_id", "product_family");

CREATE UNIQUE INDEX "ocpazure_compute_summary" ON {{schema_name | sqlsafe}}."reporting_ocpazure_compute_summary" USING "btree" ("usage_start", "cluster_id", "subscription_guid", "instance_type", "resource_id");

CREATE UNIQUE INDEX "ocpazure_cost_summary" ON {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary" USING "btree" ("usage_start", "cluster_id", "cluster_alias", "source_uuid");

CREATE UNIQUE INDEX "ocpazure_cost_summary_account" ON {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_account" USING "btree" ("usage_start", "cluster_id", "subscription_guid");

CREATE UNIQUE INDEX "ocpazure_cost_summary_location" ON {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_location" USING "btree" ("usage_start", "cluster_id", "subscription_guid", "resource_location");

CREATE UNIQUE INDEX "ocpazure_cost_summary_service" ON {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_service" USING "btree" ("usage_start", "cluster_id", "subscription_guid", "service_name");

CREATE UNIQUE INDEX "ocpazure_database_summary" ON {{schema_name | sqlsafe}}."reporting_ocpazure_database_summary" USING "btree" ("usage_start", "cluster_id", "subscription_guid", "service_name");

CREATE INDEX "ocpazure_instance_type_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" USING "btree" ("instance_type");

CREATE INDEX "ocpazure_namespace_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" USING "btree" ("namespace");

CREATE UNIQUE INDEX "ocpazure_network_summary" ON {{schema_name | sqlsafe}}."reporting_ocpazure_network_summary" USING "btree" ("usage_start", "cluster_id", "subscription_guid", "service_name");

CREATE INDEX "ocpazure_node_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" USING "btree" ("node" "varchar_pattern_ops");

CREATE INDEX "ocpazure_node_like_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" USING "gin" ("upper"(("node")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ocpazure_proj_inst_type_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" USING "btree" ("instance_type");

CREATE INDEX "ocpazure_proj_namespace_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" USING "btree" ("namespace" "varchar_pattern_ops");

CREATE INDEX "ocpazure_proj_namespace_like_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" USING "gin" ("upper"(("namespace")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ocpazure_proj_node_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" USING "btree" ("node" "varchar_pattern_ops");

CREATE INDEX "ocpazure_proj_node_like_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" USING "gin" ("upper"(("node")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ocpazure_proj_pod_labels_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" USING "gin" ("pod_labels");

CREATE INDEX "ocpazure_proj_resource_id_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" USING "btree" ("resource_id");

CREATE INDEX "ocpazure_proj_service_name_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" USING "btree" ("service_name");

CREATE INDEX "ocpazure_proj_usage_start_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" USING "btree" ("usage_start");

CREATE INDEX "ocpazure_resource_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" USING "btree" ("resource_id");

CREATE INDEX "ocpazure_service_name_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" USING "btree" ("service_name");

CREATE UNIQUE INDEX "ocpazure_storage_summary" ON {{schema_name | sqlsafe}}."reporting_ocpazure_storage_summary" USING "btree" ("usage_start", "cluster_id", "subscription_guid", "service_name");

CREATE INDEX "ocpazure_tags_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" USING "gin" ("tags");

CREATE INDEX "ocpazure_usage_start_idx" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" USING "btree" ("usage_start");

CREATE INDEX "ocpcostsum_namespace_idx" ON {{schema_name | sqlsafe}}."reporting_ocpcosts_summary" USING "btree" ("namespace" "varchar_pattern_ops");

CREATE INDEX "ocpcostsum_namespace_like_idx" ON {{schema_name | sqlsafe}}."reporting_ocpcosts_summary" USING "gin" ("upper"(("namespace")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ocpcostsum_node_idx" ON {{schema_name | sqlsafe}}."reporting_ocpcosts_summary" USING "btree" ("node" "varchar_pattern_ops");

CREATE INDEX "ocpcostsum_node_like_idx" ON {{schema_name | sqlsafe}}."reporting_ocpcosts_summary" USING "gin" ("upper"(("node")::"text") "public"."gin_trgm_ops");

CREATE INDEX "ocpcostsum_pod_labels_idx" ON {{schema_name | sqlsafe}}."reporting_ocpcosts_summary" USING "gin" ("pod_labels");

CREATE INDEX "ocpcostsum_usage_start_idx" ON {{schema_name | sqlsafe}}."reporting_ocpcosts_summary" USING "btree" ("usage_start");

CREATE INDEX "ocplblnitdly_node_labels" ON {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily" USING "gin" ("node_labels");

CREATE INDEX "ocplblnitdly_usage_start" ON {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily" USING "btree" ("usage_start");

CREATE INDEX "openshift_tags_value_key_idx" ON {{schema_name | sqlsafe}}."reporting_ocptags_values" USING "btree" ("key");

CREATE INDEX "p_gcp_summary_instance_type_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary" USING "btree" ("instance_type");

CREATE INDEX "p_gcp_summary_project_id_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary" USING "btree" ("project_id");

CREATE INDEX "p_gcp_summary_project_name_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary" USING "btree" ("project_name");

CREATE INDEX "p_gcp_summary_service_alias_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary" USING "btree" ("service_alias");

CREATE INDEX "p_gcp_summary_service_id_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary" USING "btree" ("service_id");

CREATE INDEX "p_gcp_summary_usage_start_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary" USING "btree" ("usage_start");

CREATE INDEX "p_gcp_tags_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary" USING "gin" ("tags");

CREATE INDEX "p_ix_azurecstentrydlysumm_start" ON ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary" USING "btree" ("usage_start");

CREATE INDEX "p_pod_labels_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary" USING "gin" ("pod_labels");

CREATE INDEX "p_reporting_gcpcostentryline_cost_entry_bill_id_bf00a16b" ON ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "p_summary_account_alias_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "btree" ("account_alias_id");

CREATE INDEX "p_summary_data_source_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary" USING "btree" ("data_source");

CREATE INDEX "p_summary_instance_type_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "btree" ("instance_type");

CREATE INDEX "p_summary_namespace_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary" USING "btree" ("namespace" "varchar_pattern_ops");

CREATE INDEX "p_summary_node_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary" USING "btree" ("node" "varchar_pattern_ops");

CREATE INDEX "p_summary_ocp_usage_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary" USING "btree" ("usage_start");

CREATE INDEX "p_summary_product_code_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "btree" ("product_code");

CREATE INDEX "p_summary_product_family_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "btree" ("product_family");

CREATE INDEX "p_summary_usage_account_id_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "btree" ("usage_account_id");

CREATE INDEX "p_summary_usage_start_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "btree" ("usage_start");

CREATE INDEX "p_tags_idx" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "gin" ("tags");

CREATE INDEX "partable_partition_parameters" ON {{schema_name | sqlsafe}}."partitioned_tables" USING "gin" ("partition_parameters");

CREATE INDEX "partable_partition_type" ON {{schema_name | sqlsafe}}."partitioned_tables" USING "btree" ("partition_type");

CREATE INDEX "partable_table" ON {{schema_name | sqlsafe}}."partitioned_tables" USING "btree" ("schema_name", "table_name");

CREATE INDEX "pod_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily" USING "btree" ("pod");

CREATE INDEX "presto_pk_delete_wrapper_log_tx" ON {{schema_name | sqlsafe}}."presto_pk_delete_wrapper_log" USING "btree" ("transaction_id", "table_name");

CREATE INDEX "product_code_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" USING "btree" ("product_code");

CREATE INDEX "region_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentryproduct" USING "btree" ("region");

CREATE INDEX "reporting_awsaccountalias_account_id_85724b8c_like" ON {{schema_name | sqlsafe}}."reporting_awsaccountalias" USING "btree" ("account_id" "varchar_pattern_ops");

CREATE INDEX "reporting_awscostentry_bill_id_017f27a3" ON {{schema_name | sqlsafe}}."reporting_awscostentry" USING "btree" ("bill_id");

CREATE INDEX "reporting_awscostentrybill_provider_id_a08725b3" ON {{schema_name | sqlsafe}}."reporting_awscostentrybill" USING "btree" ("provider_id");

CREATE INDEX "reporting_awscostentryline_account_alias_id_684d6c01" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "btree" ("account_alias_id");

CREATE INDEX "reporting_awscostentryline_cost_entry_bill_id_54ece653" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_awscostentryline_cost_entry_bill_id_d7af1eb6" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_awscostentryline_cost_entry_pricing_id_5a6a9b38" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" USING "btree" ("cost_entry_pricing_id");

CREATE INDEX "reporting_awscostentryline_cost_entry_product_id_4d8ef2fd" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" USING "btree" ("cost_entry_product_id");

CREATE INDEX "reporting_awscostentryline_cost_entry_reservation_id_13b1cb08" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" USING "btree" ("cost_entry_reservation_id");

CREATE INDEX "reporting_awscostentryline_cost_entry_reservation_id_9332b371" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem" USING "btree" ("cost_entry_reservation_id");

CREATE INDEX "reporting_awscostentryline_organizational_unit_id_01926b46" ON ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary" USING "btree" ("organizational_unit_id");

CREATE INDEX "reporting_awscostentrylineitem_cost_entry_bill_id_5ae74e09" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_awscostentrylineitem_cost_entry_id_4d1a7fc4" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem" USING "btree" ("cost_entry_id");

CREATE INDEX "reporting_awscostentrylineitem_cost_entry_pricing_id_a654a7e3" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem" USING "btree" ("cost_entry_pricing_id");

CREATE INDEX "reporting_awscostentrylineitem_cost_entry_product_id_29c80210" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem" USING "btree" ("cost_entry_product_id");

CREATE INDEX "reporting_awscostentrylineitem_daily_organizational_unit_id_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "btree" ("organizational_unit_id");

CREATE INDEX "reporting_awscostentrylineitem_daily_sum_cost_entry_bill_id_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_awscostentrylineitem_daily_summ_account_alias_id_idx1" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "btree" ("account_alias_id");

CREATE INDEX "reporting_awscostentrylineitem_daily_summa_account_alias_id_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "btree" ("account_alias_id");

CREATE INDEX "reporting_awscostentrylineitem_daily_summa_usage_account_id_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "btree" ("usage_account_id");

CREATE INDEX "reporting_awscostentrylineitem_daily_summary__instance_type_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "btree" ("instance_type");

CREATE INDEX "reporting_awscostentrylineitem_daily_summary_d_product_code_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "btree" ("product_code");

CREATE INDEX "reporting_awscostentrylineitem_daily_summary_de_usage_start_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "btree" ("usage_start");

CREATE INDEX "reporting_awscostentrylineitem_daily_summary_default_tags_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "gin" ("tags");

CREATE INDEX "reporting_awscostentrylineitem_daily_summary_default_upper_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "gin" ("upper"(("product_family")::"text") "public"."gin_trgm_ops");

CREATE INDEX "reporting_awscostentrylineitem_daily_summary_default_upper_idx1" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "gin" ("upper"(("product_family")::"text") "public"."gin_trgm_ops");

CREATE INDEX "reporting_awscostentrylineitem_daily_summary_product_family_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default" USING "btree" ("product_family");

CREATE INDEX "reporting_awscostentryreservation_reservation_arn_e387aa5b_like" ON {{schema_name | sqlsafe}}."reporting_awscostentryreservation" USING "btree" ("reservation_arn" "text_pattern_ops");

CREATE INDEX "reporting_awsenabledtagkeys_key_8c2841c2_like" ON {{schema_name | sqlsafe}}."reporting_awsenabledtagkeys" USING "btree" ("key" "varchar_pattern_ops");

CREATE INDEX "reporting_awsorganizationalunit_account_alias_id_7bd6273b" ON {{schema_name | sqlsafe}}."reporting_awsorganizationalunit" USING "btree" ("account_alias_id");

CREATE INDEX "reporting_awsorganizationalunit_provider_id_6e91f0ae" ON {{schema_name | sqlsafe}}."reporting_awsorganizationalunit" USING "btree" ("provider_id");

CREATE INDEX "reporting_awstags_summary_account_alias_id_8a49f381" ON {{schema_name | sqlsafe}}."reporting_awstags_summary" USING "btree" ("account_alias_id");

CREATE INDEX "reporting_awstags_summary_cost_entry_bill_id_c9c45ad6" ON {{schema_name | sqlsafe}}."reporting_awstags_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_azurecostentrybill_provider_id_5b7738d5" ON {{schema_name | sqlsafe}}."reporting_azurecostentrybill" USING "btree" ("provider_id");

CREATE INDEX "reporting_azurecostentryli_cost_entry_bill_id_7898bce4" ON {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_azurecostentryli_cost_entry_bill_id_e7c3e625" ON ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_azurecostentryli_cost_entry_product_id_b84c188a" ON {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily" USING "btree" ("cost_entry_product_id");

CREATE INDEX "reporting_azurecostentryli_meter_id_799dc028" ON ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary" USING "btree" ("meter_id");

CREATE INDEX "reporting_azurecostentrylineitem_daily_meter_id_292c06f8" ON {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily" USING "btree" ("meter_id");

CREATE INDEX "reporting_azurecostentrylineitem_daily_s_cost_entry_bill_id_idx" ON {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_default" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_azurecostentrylineitem_daily_summary__usage_start_idx" ON {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_default" USING "btree" ("usage_start");

CREATE INDEX "reporting_azurecostentrylineitem_daily_summary_def_meter_id_idx" ON {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_default" USING "btree" ("meter_id");

CREATE INDEX "reporting_azurecostentrylineitem_daily_summary_defaul_upper_idx" ON {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_default" USING "gin" ("upper"("service_name") "public"."gin_trgm_ops");

CREATE INDEX "reporting_azurecostentryproductservice_provider_id_2072db59" ON {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice" USING "btree" ("provider_id");

CREATE INDEX "reporting_azureenabledtagkeys_key_a00bc136_like" ON {{schema_name | sqlsafe}}."reporting_azureenabledtagkeys" USING "btree" ("key" "varchar_pattern_ops");

CREATE INDEX "reporting_azuremeter_provider_id_d6bb7273" ON {{schema_name | sqlsafe}}."reporting_azuremeter" USING "btree" ("provider_id");

CREATE INDEX "reporting_azuretags_summary_cost_entry_bill_id_cb69e67a" ON {{schema_name | sqlsafe}}."reporting_azuretags_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_gcpcostentrybill_provider_id_4da1742f" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrybill" USING "btree" ("provider_id");

CREATE INDEX "reporting_gcpcostentryline_cost_entry_bill_id_a3272999" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_gcpcostentryline_cost_entry_product_id_bce5f583" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily" USING "btree" ("cost_entry_product_id");

CREATE INDEX "reporting_gcpcostentrylineitem_cost_entry_bill_id_7a8f16fd" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_gcpcostentrylineitem_cost_entry_product_id_cec870b8" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem" USING "btree" ("cost_entry_product_id");

CREATE INDEX "reporting_gcpcostentrylineitem_daily_project_id_18365d99" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily" USING "btree" ("project_id");

CREATE INDEX "reporting_gcpcostentrylineitem_daily_sum_cost_entry_bill_id_idx" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_gcpcostentrylineitem_daily_summary__instance_type_idx" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default" USING "btree" ("instance_type");

CREATE INDEX "reporting_gcpcostentrylineitem_daily_summary__service_alias_idx" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default" USING "btree" ("service_alias");

CREATE INDEX "reporting_gcpcostentrylineitem_daily_summary_d_project_name_idx" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default" USING "btree" ("project_name");

CREATE INDEX "reporting_gcpcostentrylineitem_daily_summary_de_usage_start_idx" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default" USING "btree" ("usage_start");

CREATE INDEX "reporting_gcpcostentrylineitem_daily_summary_def_project_id_idx" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default" USING "btree" ("project_id");

CREATE INDEX "reporting_gcpcostentrylineitem_daily_summary_def_service_id_idx" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default" USING "btree" ("service_id");

CREATE INDEX "reporting_gcpcostentrylineitem_daily_summary_default_tags_idx" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default" USING "gin" ("tags");

CREATE INDEX "reporting_gcpcostentrylineitem_project_id_bf066e6e" ON {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem" USING "btree" ("project_id");

CREATE INDEX "reporting_gcpenabledtagkeys_key_0e50e656_like" ON {{schema_name | sqlsafe}}."reporting_gcpenabledtagkeys" USING "btree" ("key" "varchar_pattern_ops");

CREATE INDEX "reporting_gcpproject_project_id_77600c9d_like" ON {{schema_name | sqlsafe}}."reporting_gcpproject" USING "btree" ("project_id" "varchar_pattern_ops");

CREATE INDEX "reporting_gcptags_summary_cost_entry_bill_id_e442ff66" ON {{schema_name | sqlsafe}}."reporting_gcptags_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_ocp_clusters_provider_id_ef184970" ON {{schema_name | sqlsafe}}."reporting_ocp_clusters" USING "btree" ("provider_id");

CREATE INDEX "reporting_ocp_nodes_cluster_id_fbf78679" ON {{schema_name | sqlsafe}}."reporting_ocp_nodes" USING "btree" ("cluster_id");

CREATE INDEX "reporting_ocp_projects_cluster_id_318d7969" ON {{schema_name | sqlsafe}}."reporting_ocp_projects" USING "btree" ("cluster_id");

CREATE INDEX "reporting_ocp_pvcs_cluster_id_c6f60f16" ON {{schema_name | sqlsafe}}."reporting_ocp_pvcs" USING "btree" ("cluster_id");

CREATE INDEX "reporting_ocpawscostlineit_account_alias_id_d12902c6" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "btree" ("account_alias_id");

CREATE INDEX "reporting_ocpawscostlineit_account_alias_id_f19d2883" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "btree" ("account_alias_id");

CREATE INDEX "reporting_ocpawscostlineit_cost_entry_bill_id_2740da80" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_ocpawscostlineit_cost_entry_bill_id_2a473151" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_ocpawscostlineit_report_period_id_150c5620" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpawscostlineit_report_period_id_3f8d2da5" ON {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpawstags_summary_account_alias_id_f3d8c2e0" ON {{schema_name | sqlsafe}}."reporting_ocpawstags_summary" USING "btree" ("account_alias_id");

CREATE INDEX "reporting_ocpawstags_summary_cost_entry_bill_id_9fe9ad45" ON {{schema_name | sqlsafe}}."reporting_ocpawstags_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_ocpawstags_summary_report_period_id_54cc3cc4" ON {{schema_name | sqlsafe}}."reporting_ocpawstags_summary" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpazurecostline_cost_entry_bill_id_442560ac" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_ocpazurecostline_cost_entry_bill_id_b12d05bd" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_ocpazurecostline_report_period_id_145b540e" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpazurecostline_report_period_id_e5bbf81f" ON {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpazuretags_summary_cost_entry_bill_id_c84d2dc3" ON {{schema_name | sqlsafe}}."reporting_ocpazuretags_summary" USING "btree" ("cost_entry_bill_id");

CREATE INDEX "reporting_ocpazuretags_summary_report_period_id_19a6abdb" ON {{schema_name | sqlsafe}}."reporting_ocpazuretags_summary" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpcosts_summary_report_period_id_e53cdbb2" ON {{schema_name | sqlsafe}}."reporting_ocpcosts_summary" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpenabledtagkeys_key_c3a4025b_like" ON {{schema_name | sqlsafe}}."reporting_ocpenabledtagkeys" USING "btree" ("key" "varchar_pattern_ops");

CREATE INDEX "reporting_ocpnamespacelabellineitem_report_id_16489a95" ON {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem" USING "btree" ("report_id");

CREATE INDEX "reporting_ocpnamespacelabellineitem_report_period_id_704a722f" ON {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpnodelabellineitem_daily_report_period_id_de6c8f1f" ON {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpnodelabellineitem_report_id_5e2f992a" ON {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem" USING "btree" ("report_id");

CREATE INDEX "reporting_ocpnodelabellineitem_report_period_id_d3fcf22e" ON {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpstoragelineitem_daily_report_period_id_ad325037" ON {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpstoragelineitem_report_id_6ff71ea6" ON {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem" USING "btree" ("report_id");

CREATE INDEX "reporting_ocpstoragelineitem_report_period_id_6d730b12" ON {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpstoragevolume_report_period_id_53b5a3b8" ON {{schema_name | sqlsafe}}."reporting_ocpstoragevolumelabel_summary" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpusagelineitem_daily_report_period_id_d5388c41" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpusagelineitem_report_period_id_fc68baea" ON ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpusagelineitem_daily_summary_d_report_period_id_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpusagelineitem_daily_summary_defaul_data_source_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default" USING "btree" ("data_source");

CREATE INDEX "reporting_ocpusagelineitem_daily_summary_defaul_usage_start_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default" USING "btree" ("usage_start");

CREATE INDEX "reporting_ocpusagelineitem_daily_summary_default_namespace_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default" USING "btree" ("namespace" "varchar_pattern_ops");

CREATE INDEX "reporting_ocpusagelineitem_daily_summary_default_node_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default" USING "btree" ("node" "varchar_pattern_ops");

CREATE INDEX "reporting_ocpusagelineitem_daily_summary_default_pod_labels_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default" USING "gin" ("pod_labels");

CREATE INDEX "reporting_ocpusagelineitem_daily_summary_default_upper_idx" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default" USING "gin" ("upper"(("namespace")::"text") "public"."gin_trgm_ops");

CREATE INDEX "reporting_ocpusagelineitem_daily_summary_default_upper_idx1" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default" USING "gin" ("upper"(("node")::"text") "public"."gin_trgm_ops");

CREATE INDEX "reporting_ocpusagelineitem_report_id_32a973b0" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem" USING "btree" ("report_id");

CREATE INDEX "reporting_ocpusagelineitem_report_period_id_be7fa5ad" ON {{schema_name | sqlsafe}}."reporting_ocpusagelineitem" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpusagepodlabel_summary_report_period_id_fa250ee5" ON {{schema_name | sqlsafe}}."reporting_ocpusagepodlabel_summary" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpusagereport_report_period_id_477508c6" ON {{schema_name | sqlsafe}}."reporting_ocpusagereport" USING "btree" ("report_period_id");

CREATE INDEX "reporting_ocpusagereportperiod_provider_id_7348fe66" ON {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod" USING "btree" ("provider_id");

CREATE INDEX "resource_id_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" USING "btree" ("resource_id");

CREATE INDEX "usage_account_id_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" USING "btree" ("usage_account_id");

CREATE INDEX "usage_start_idx" ON {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily" USING "btree" ("usage_start");

ALTER INDEX {{schema_name | sqlsafe}}."reporting_awscostentryline_organizational_unit_id_01926b46" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_organizational_unit_id_idx";

ALTER INDEX {{schema_name | sqlsafe}}."reporting_awscostentryline_cost_entry_bill_id_d7af1eb6" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_sum_cost_entry_bill_id_idx";

ALTER INDEX {{schema_name | sqlsafe}}."reporting_awscostentryline_account_alias_id_684d6c01" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summ_account_alias_id_idx1";

ALTER INDEX {{schema_name | sqlsafe}}."p_summary_account_alias_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summa_account_alias_id_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_summary_usage_account_id_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summa_usage_account_id_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_summary_instance_type_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary__instance_type_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_summary_product_code_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_d_product_code_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_summary_usage_start_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_de_usage_start_idx";

ALTER INDEX {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_pkey" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default_pkey";

ALTER INDEX {{schema_name | sqlsafe}}."p_tags_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default_tags_idx";

ALTER INDEX {{schema_name | sqlsafe}}."aws_summ_usage_pfam_ilike" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default_upper_idx";

ALTER INDEX {{schema_name | sqlsafe}}."aws_summ_usage_pcode_ilike" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_default_upper_idx1";

ALTER INDEX {{schema_name | sqlsafe}}."p_summary_product_family_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary_product_family_idx";

ALTER INDEX {{schema_name | sqlsafe}}."reporting_azurecostentryli_cost_entry_bill_id_e7c3e625" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_s_cost_entry_bill_id_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_ix_azurecstentrydlysumm_start" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary__usage_start_idx";

ALTER INDEX {{schema_name | sqlsafe}}."reporting_azurecostentryli_meter_id_799dc028" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_def_meter_id_idx";

ALTER INDEX {{schema_name | sqlsafe}}."ix_azure_costentrydlysumm_service_name" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_defaul_upper_idx";

ALTER INDEX {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_pkey" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary_default_pkey";

ALTER INDEX {{schema_name | sqlsafe}}."p_reporting_gcpcostentryline_cost_entry_bill_id_bf00a16b" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_sum_cost_entry_bill_id_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_gcp_summary_instance_type_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary__instance_type_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_gcp_summary_service_alias_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary__service_alias_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_gcp_summary_project_name_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_d_project_name_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_gcp_summary_usage_start_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_de_usage_start_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_gcp_summary_project_id_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_def_project_id_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_gcp_summary_service_id_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_def_service_id_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_reporting_gcpcostentrylineitem_daily_summary_pkey" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default_pkey";

ALTER INDEX {{schema_name | sqlsafe}}."p_gcp_tags_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary_default_tags_idx";

ALTER INDEX {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_report_period_id_fc68baea" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_d_report_period_id_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_summary_data_source_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_defaul_data_source_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_summary_ocp_usage_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_defaul_usage_start_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_summary_namespace_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default_namespace_idx";

ALTER INDEX {{schema_name | sqlsafe}}."p_summary_node_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default_node_idx";

ALTER INDEX {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_pkey" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default_pkey";

ALTER INDEX {{schema_name | sqlsafe}}."p_pod_labels_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default_pod_labels_idx";

ALTER INDEX {{schema_name | sqlsafe}}."ocp_summary_namespace_like_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default_upper_idx";

ALTER INDEX {{schema_name | sqlsafe}}."ocp_summary_node_like_idx" ATTACH PARTITION {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary_default_upper_idx1";

CREATE TRIGGER "tr_partition_manager" AFTER INSERT OR DELETE OR UPDATE ON {{schema_name | sqlsafe}}."partitioned_tables" FOR EACH ROW EXECUTE FUNCTION "public"."trfn_partition_manager"();

CREATE TRIGGER "tr_presto_before_insert" BEFORE INSERT ON {{schema_name | sqlsafe}}."presto_delete_wrapper_log" FOR EACH ROW EXECUTE FUNCTION "public"."tr_presto_delete_wrapper_log_action"();

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
    ADD CONSTRAINT "p_reporting_awscostent_account_alias_id_684d6c01_fk_reporting" FOREIGN KEY ("account_alias_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awsaccountalias"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
    ADD CONSTRAINT "p_reporting_awscostent_cost_entry_bill_id_d7af1eb6_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awscostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily_summary"
    ADD CONSTRAINT "p_reporting_awscostent_organizational_unit__01926b46_fk_reporti" FOREIGN KEY ("organizational_unit_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awsorganizationalunit"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
    ADD CONSTRAINT "p_reporting_azurecoste_cost_entry_bill_id_e7c3e625_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_azurecostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily_summary"
    ADD CONSTRAINT "p_reporting_azurecoste_meter_id_799dc028_fk_reporting" FOREIGN KEY ("meter_id") REFERENCES {{schema_name | sqlsafe}}."reporting_azuremeter"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily_summary"
    ADD CONSTRAINT "p_reporting_gcpcostent_cost_entry_bill_id_bf00a16b_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_gcpcostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily_summary"
    ADD CONSTRAINT "p_reporting_ocpusageli_report_period_id_fc68baea_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentry"
    ADD CONSTRAINT "reporting_awscostent_bill_id_017f27a3_fk_reporting" FOREIGN KEY ("bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awscostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily"
    ADD CONSTRAINT "reporting_awscostent_cost_entry_bill_id_54ece653_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awscostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily"
    ADD CONSTRAINT "reporting_awscostent_cost_entry_pricing_i_5a6a9b38_fk_reporting" FOREIGN KEY ("cost_entry_pricing_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awscostentrypricing"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily"
    ADD CONSTRAINT "reporting_awscostent_cost_entry_product_i_4d8ef2fd_fk_reporting" FOREIGN KEY ("cost_entry_product_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awscostentryproduct"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrylineitem_daily"
    ADD CONSTRAINT "reporting_awscostent_cost_entry_reservati_13b1cb08_fk_reporting" FOREIGN KEY ("cost_entry_reservation_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awscostentryreservation"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awscostentrybill"
    ADD CONSTRAINT "reporting_awscostent_provider_id_a08725b3_fk_api_provi" FOREIGN KEY ("provider_id") REFERENCES "public"."api_provider"("uuid") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awsorganizationalunit"
    ADD CONSTRAINT "reporting_awsorganiz_account_alias_id_7bd6273b_fk_reporting" FOREIGN KEY ("account_alias_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awsaccountalias"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awsorganizationalunit"
    ADD CONSTRAINT "reporting_awsorganiz_provider_id_6e91f0ae_fk_api_provi" FOREIGN KEY ("provider_id") REFERENCES "public"."api_provider"("uuid") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awstags_summary"
    ADD CONSTRAINT "reporting_awstags_su_account_alias_id_8a49f381_fk_reporting" FOREIGN KEY ("account_alias_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awsaccountalias"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_awstags_summary"
    ADD CONSTRAINT "reporting_awstags_su_cost_entry_bill_id_c9c45ad6_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awscostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily"
    ADD CONSTRAINT "reporting_azurecoste_cost_entry_bill_id_7898bce4_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_azurecostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily"
    ADD CONSTRAINT "reporting_azurecoste_cost_entry_product_i_b84c188a_fk_reporting" FOREIGN KEY ("cost_entry_product_id") REFERENCES {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrylineitem_daily"
    ADD CONSTRAINT "reporting_azurecoste_meter_id_292c06f8_fk_reporting" FOREIGN KEY ("meter_id") REFERENCES {{schema_name | sqlsafe}}."reporting_azuremeter"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentryproductservice"
    ADD CONSTRAINT "reporting_azurecoste_provider_id_2072db59_fk_api_provi" FOREIGN KEY ("provider_id") REFERENCES "public"."api_provider"("uuid") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azurecostentrybill"
    ADD CONSTRAINT "reporting_azurecoste_provider_id_5b7738d5_fk_api_provi" FOREIGN KEY ("provider_id") REFERENCES "public"."api_provider"("uuid") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azuremeter"
    ADD CONSTRAINT "reporting_azuremeter_provider_id_d6bb7273_fk_api_provider_uuid" FOREIGN KEY ("provider_id") REFERENCES "public"."api_provider"("uuid") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_azuretags_summary"
    ADD CONSTRAINT "reporting_azuretags__cost_entry_bill_id_cb69e67a_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_azurecostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily"
    ADD CONSTRAINT "reporting_gcpcostent_cost_entry_bill_id_a3272999_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_gcpcostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily"
    ADD CONSTRAINT "reporting_gcpcostent_cost_entry_product_i_bce5f583_fk_reporting" FOREIGN KEY ("cost_entry_product_id") REFERENCES {{schema_name | sqlsafe}}."reporting_gcpcostentryproductservice"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrylineitem_daily"
    ADD CONSTRAINT "reporting_gcpcostent_project_id_18365d99_fk_reporting" FOREIGN KEY ("project_id") REFERENCES {{schema_name | sqlsafe}}."reporting_gcpproject"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcpcostentrybill"
    ADD CONSTRAINT "reporting_gcpcostent_provider_id_4da1742f_fk_api_provi" FOREIGN KEY ("provider_id") REFERENCES "public"."api_provider"("uuid") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_gcptags_summary"
    ADD CONSTRAINT "reporting_gcptags_su_cost_entry_bill_id_e442ff66_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_gcpcostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocp_clusters"
    ADD CONSTRAINT "reporting_ocp_cluste_provider_id_ef184970_fk_api_provi" FOREIGN KEY ("provider_id") REFERENCES "public"."api_provider"("uuid") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocp_nodes"
    ADD CONSTRAINT "reporting_ocp_nodes_cluster_id_fbf78679_fk_reporting" FOREIGN KEY ("cluster_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocp_clusters"("uuid") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocp_projects"
    ADD CONSTRAINT "reporting_ocp_projec_cluster_id_318d7969_fk_reporting" FOREIGN KEY ("cluster_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocp_clusters"("uuid") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocp_pvcs"
    ADD CONSTRAINT "reporting_ocp_pvcs_cluster_id_c6f60f16_fk_reporting" FOREIGN KEY ("cluster_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocp_clusters"("uuid") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary"
    ADD CONSTRAINT "reporting_ocpawscost_account_alias_id_d12902c6_fk_reporting" FOREIGN KEY ("account_alias_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awsaccountalias"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
    ADD CONSTRAINT "reporting_ocpawscost_account_alias_id_f19d2883_fk_reporting" FOREIGN KEY ("account_alias_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awsaccountalias"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary"
    ADD CONSTRAINT "reporting_ocpawscost_cost_entry_bill_id_2740da80_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awscostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
    ADD CONSTRAINT "reporting_ocpawscost_cost_entry_bill_id_2a473151_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awscostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_daily_summary"
    ADD CONSTRAINT "reporting_ocpawscost_report_period_id_150c5620_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawscostlineitem_project_daily_summary"
    ADD CONSTRAINT "reporting_ocpawscost_report_period_id_3f8d2da5_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawstags_summary"
    ADD CONSTRAINT "reporting_ocpawstags_account_alias_id_f3d8c2e0_fk_reporting" FOREIGN KEY ("account_alias_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awsaccountalias"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawstags_summary"
    ADD CONSTRAINT "reporting_ocpawstags_cost_entry_bill_id_9fe9ad45_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_awscostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpawstags_summary"
    ADD CONSTRAINT "reporting_ocpawstags_report_period_id_54cc3cc4_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary"
    ADD CONSTRAINT "reporting_ocpazureco_cost_entry_bill_id_442560ac_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_azurecostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
    ADD CONSTRAINT "reporting_ocpazureco_cost_entry_bill_id_b12d05bd_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_azurecostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_project_daily_summary"
    ADD CONSTRAINT "reporting_ocpazureco_report_period_id_145b540e_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazurecostlineitem_daily_summary"
    ADD CONSTRAINT "reporting_ocpazureco_report_period_id_e5bbf81f_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazuretags_summary"
    ADD CONSTRAINT "reporting_ocpazureta_cost_entry_bill_id_c84d2dc3_fk_reporting" FOREIGN KEY ("cost_entry_bill_id") REFERENCES {{schema_name | sqlsafe}}."reporting_azurecostentrybill"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpazuretags_summary"
    ADD CONSTRAINT "reporting_ocpazureta_report_period_id_19a6abdb_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpcosts_summary"
    ADD CONSTRAINT "reporting_ocpcosts_s_report_period_id_e53cdbb2_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem"
    ADD CONSTRAINT "reporting_ocpnamespa_report_id_16489a95_fk_reporting" FOREIGN KEY ("report_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereport"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpnamespacelabellineitem"
    ADD CONSTRAINT "reporting_ocpnamespa_report_period_id_704a722f_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpnodelabellineitem_daily"
    ADD CONSTRAINT "reporting_ocpnodelab_report_period_id_de6c8f1f_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpstoragevolumelabel_summary"
    ADD CONSTRAINT "reporting_ocpstorage_report_period_id_53b5a3b8_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpstoragelineitem_daily"
    ADD CONSTRAINT "reporting_ocpstorage_report_period_id_ad325037_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagelineitem_daily"
    ADD CONSTRAINT "reporting_ocpusageli_report_period_id_d5388c41_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagepodlabel_summary"
    ADD CONSTRAINT "reporting_ocpusagepo_report_period_id_fa250ee5_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"
    ADD CONSTRAINT "reporting_ocpusagere_provider_id_7348fe66_fk_api_provi" FOREIGN KEY ("provider_id") REFERENCES "public"."api_provider"("uuid") DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ONLY {{schema_name | sqlsafe}}."reporting_ocpusagereport"
    ADD CONSTRAINT "reporting_ocpusagere_report_period_id_477508c6_fk_reporting" FOREIGN KEY ("report_period_id") REFERENCES {{schema_name | sqlsafe}}."reporting_ocpusagereportperiod"("id") DEFERRABLE INITIALLY DEFERRED;

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_compute_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_account";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_region";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_compute_summary_by_service";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_cost_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_account";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_region";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_cost_summary_by_service";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_database_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_network_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_storage_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_account";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_region";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_aws_storage_summary_by_service";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_compute_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_cost_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_account";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_location";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_cost_summary_by_service";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_database_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_network_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_azure_storage_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_compute_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_account";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_project";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_region";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_compute_summary_by_service";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_cost_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_account";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_project";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_region";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_cost_summary_by_service";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_database_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_network_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_storage_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_account";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_project";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_region";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_gcp_storage_summary_by_service";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_cost_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_cost_summary_by_node";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_cost_summary_by_project";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_pod_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_pod_summary_by_project";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_volume_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocp_volume_summary_by_project";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_daily_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_compute_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_account";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_region";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_cost_summary_by_service";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_database_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_network_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpall_storage_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpallcostlineitem_project_daily_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_compute_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_account";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_region";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_cost_summary_by_service";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_database_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_network_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpaws_storage_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_compute_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_account";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_location";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_cost_summary_by_service";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_database_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_network_summary";

REFRESH MATERIALIZED VIEW {{schema_name | sqlsafe}}."reporting_ocpazure_storage_summary";
