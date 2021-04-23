--
-- PostgreSQL database dump
--

-- Dumped from database version 12.4 (Debian 12.4-1.pgdg100+1)
-- Dumped by pg_dump version 12.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: template0; Type: SCHEMA; Schema: -; Owner: table_owner
--

CREATE SCHEMA template0;


ALTER SCHEMA template0 OWNER TO table_owner;

--
-- Name: process_cost_model_audit(); Type: FUNCTION; Schema: template0; Owner: table_owner
--

CREATE FUNCTION template0.process_cost_model_audit() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
                DECLARE
                    provider_uuids uuid[];
                BEGIN
                    --
                    -- Create a row in cost_model_audit to reflect the operation performed on cost_model,
                    -- make use of the special variable TG_OP to work out the operation.
                    --
                    IF (TG_OP = 'DELETE') THEN
                        provider_uuids := (SELECT array_agg(provider_uuid) FROM cost_model_map WHERE cost_model_id = OLD.uuid);
                        INSERT INTO cost_model_audit SELECT nextval('cost_model_audit_id_seq'), 'DELETE', now(), provider_uuids, OLD.*;
                        RETURN OLD;
                    ELSIF (TG_OP = 'UPDATE') THEN
                        provider_uuids := (SELECT array_agg(provider_uuid) FROM cost_model_map WHERE cost_model_id = NEW.uuid);
                        INSERT INTO cost_model_audit SELECT nextval('cost_model_audit_id_seq'), 'UPDATE', now(), provider_uuids, NEW.*;
                        RETURN NEW;
                    ELSIF (TG_OP = 'INSERT') THEN
                        provider_uuids := (SELECT array_agg(provider_uuid) FROM cost_model_map WHERE cost_model_id = NEW.uuid);
                        INSERT INTO cost_model_audit SELECT nextval('cost_model_audit_id_seq'), 'INSERT', now(), provider_uuids, NEW.*;
                        RETURN NEW;
                    END IF;
                    RETURN NULL; -- result is ignored since this is an AFTER trigger
                END;
            $$;


ALTER FUNCTION template0.process_cost_model_audit() OWNER TO table_owner;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: cost_model; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.cost_model (
    uuid uuid NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    source_type character varying(50) NOT NULL,
    created_timestamp timestamp with time zone NOT NULL,
    updated_timestamp timestamp with time zone NOT NULL,
    rates jsonb NOT NULL,
    markup jsonb NOT NULL
);


ALTER TABLE template0.cost_model OWNER TO table_owner;

--
-- Name: cost_model_audit; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.cost_model_audit (
    id integer NOT NULL,
    operation character varying(16) NOT NULL,
    audit_timestamp timestamp with time zone NOT NULL,
    provider_uuids uuid[],
    uuid uuid NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    source_type character varying(50) NOT NULL,
    created_timestamp timestamp with time zone NOT NULL,
    updated_timestamp timestamp with time zone NOT NULL,
    rates jsonb NOT NULL,
    markup jsonb NOT NULL
);


ALTER TABLE template0.cost_model_audit OWNER TO table_owner;

--
-- Name: cost_model_audit_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.cost_model_audit_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.cost_model_audit_id_seq OWNER TO table_owner;

--
-- Name: cost_model_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.cost_model_audit_id_seq OWNED BY template0.cost_model_audit.id;


--
-- Name: cost_model_map; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.cost_model_map (
    id integer NOT NULL,
    provider_uuid uuid NOT NULL,
    cost_model_id uuid
);


ALTER TABLE template0.cost_model_map OWNER TO table_owner;

--
-- Name: cost_model_map_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.cost_model_map_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.cost_model_map_id_seq OWNER TO table_owner;

--
-- Name: cost_model_map_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.cost_model_map_id_seq OWNED BY template0.cost_model_map.id;


--
-- Name: django_migrations; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.django_migrations (
    id integer NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


ALTER TABLE template0.django_migrations OWNER TO table_owner;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.django_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.django_migrations_id_seq OWNER TO table_owner;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.django_migrations_id_seq OWNED BY template0.django_migrations.id;


--
-- Name: partitioned_tables; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.partitioned_tables (
    id integer NOT NULL,
    schema_name text NOT NULL,
    table_name text NOT NULL,
    partition_of_table_name text NOT NULL,
    partition_type text NOT NULL,
    partition_col text NOT NULL,
    partition_parameters jsonb NOT NULL,
    active boolean DEFAULT true NOT NULL
);


ALTER TABLE template0.partitioned_tables OWNER TO table_owner;

--
-- Name: partitioned_tables_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.partitioned_tables_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.partitioned_tables_id_seq OWNER TO table_owner;

--
-- Name: partitioned_tables_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.partitioned_tables_id_seq OWNED BY template0.partitioned_tables.id;


--
-- Name: presto_delete_wrapper_log; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.presto_delete_wrapper_log (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    action_ts timestamp with time zone DEFAULT now() NOT NULL,
    table_name text NOT NULL,
    where_clause text NOT NULL,
    result_rows bigint
);


ALTER TABLE template0.presto_delete_wrapper_log OWNER TO table_owner;

--
-- Name: TABLE presto_delete_wrapper_log; Type: COMMENT; Schema: template0; Owner: table_owner
--

COMMENT ON TABLE template0.presto_delete_wrapper_log IS 'Table to log and execute delete statements initiated from Presto';


--
-- Name: COLUMN presto_delete_wrapper_log.table_name; Type: COMMENT; Schema: template0; Owner: table_owner
--

COMMENT ON COLUMN template0.presto_delete_wrapper_log.table_name IS 'Target table from which to delete';


--
-- Name: COLUMN presto_delete_wrapper_log.where_clause; Type: COMMENT; Schema: template0; Owner: table_owner
--

COMMENT ON COLUMN template0.presto_delete_wrapper_log.where_clause IS 'Where clause for delete action';


--
-- Name: COLUMN presto_delete_wrapper_log.result_rows; Type: COMMENT; Schema: template0; Owner: table_owner
--

COMMENT ON COLUMN template0.presto_delete_wrapper_log.result_rows IS 'Number of records affected by the delete action';


--
-- Name: presto_pk_delete_wrapper_log; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.presto_pk_delete_wrapper_log (
    transaction_id text NOT NULL,
    action_ts timestamp with time zone DEFAULT now() NOT NULL,
    table_name text NOT NULL,
    pk_column text NOT NULL,
    pk_value text NOT NULL,
    pk_value_cast text NOT NULL
);


ALTER TABLE template0.presto_pk_delete_wrapper_log OWNER TO table_owner;

--
-- Name: TABLE presto_pk_delete_wrapper_log; Type: COMMENT; Schema: template0; Owner: table_owner
--

COMMENT ON TABLE template0.presto_pk_delete_wrapper_log IS 'Table to hold primary key values to use when bulk-deleting using the presto delete wrapper log';


--
-- Name: COLUMN presto_pk_delete_wrapper_log.transaction_id; Type: COMMENT; Schema: template0; Owner: table_owner
--

COMMENT ON COLUMN template0.presto_pk_delete_wrapper_log.transaction_id IS 'Presto transaction identifier';


--
-- Name: COLUMN presto_pk_delete_wrapper_log.table_name; Type: COMMENT; Schema: template0; Owner: table_owner
--

COMMENT ON COLUMN template0.presto_pk_delete_wrapper_log.table_name IS 'Target table in which the primary key values reside';


--
-- Name: COLUMN presto_pk_delete_wrapper_log.pk_column; Type: COMMENT; Schema: template0; Owner: table_owner
--

COMMENT ON COLUMN template0.presto_pk_delete_wrapper_log.pk_column IS 'Name of the primary key column for the target table';


--
-- Name: COLUMN presto_pk_delete_wrapper_log.pk_value; Type: COMMENT; Schema: template0; Owner: table_owner
--

COMMENT ON COLUMN template0.presto_pk_delete_wrapper_log.pk_value IS 'String representation of the primary key value';


--
-- Name: COLUMN presto_pk_delete_wrapper_log.pk_value_cast; Type: COMMENT; Schema: template0; Owner: table_owner
--

COMMENT ON COLUMN template0.presto_pk_delete_wrapper_log.pk_value_cast IS 'Data type to which the string primary key value should be cast';


--
-- Name: reporting_awscostentrylineitem_daily_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awscostentrylineitem_daily_summary (
    usage_start date NOT NULL,
    usage_end date,
    usage_account_id character varying(50) NOT NULL,
    product_code character varying(50) NOT NULL,
    product_family character varying(150),
    availability_zone character varying(50),
    region character varying(50),
    instance_type character varying(50),
    unit character varying(63),
    resource_ids text[],
    resource_count integer,
    usage_amount numeric(24,9),
    normalization_factor double precision,
    normalized_usage_amount double precision,
    currency_code character varying(10) NOT NULL,
    unblended_rate numeric(24,9),
    unblended_cost numeric(24,9),
    markup_cost numeric(24,9),
    blended_rate numeric(24,9),
    blended_cost numeric(24,9),
    public_on_demand_cost numeric(24,9),
    public_on_demand_rate numeric(24,9),
    tax_type text,
    tags jsonb,
    source_uuid uuid,
    account_alias_id integer,
    cost_entry_bill_id integer,
    organizational_unit_id integer,
    uuid uuid NOT NULL
)
PARTITION BY RANGE (usage_start);


ALTER TABLE template0.reporting_awscostentrylineitem_daily_summary OWNER TO table_owner;

--
-- Name: reporting_aws_compute_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_compute_summary AS
 SELECT row_number() OVER (ORDER BY c.usage_start, c.instance_type, c.source_uuid) AS id,
    c.usage_start,
    c.usage_start AS usage_end,
    c.instance_type,
    r.resource_ids,
    cardinality(r.resource_ids) AS resource_count,
    c.usage_amount,
    c.unit,
    c.unblended_cost,
    c.markup_cost,
    c.currency_code,
    c.source_uuid
   FROM (( SELECT reporting_awscostentrylineitem_daily_summary.usage_start,
            reporting_awscostentrylineitem_daily_summary.instance_type,
            sum(reporting_awscostentrylineitem_daily_summary.usage_amount) AS usage_amount,
            max((reporting_awscostentrylineitem_daily_summary.unit)::text) AS unit,
            sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
            sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
            max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
            reporting_awscostentrylineitem_daily_summary.source_uuid
           FROM template0.reporting_awscostentrylineitem_daily_summary
          WHERE ((reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_awscostentrylineitem_daily_summary.instance_type IS NOT NULL))
          GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.instance_type, reporting_awscostentrylineitem_daily_summary.source_uuid) c
     JOIN ( SELECT x.usage_start,
            x.instance_type,
            array_agg(DISTINCT x.resource_id ORDER BY x.resource_id) AS resource_ids
           FROM ( SELECT reporting_awscostentrylineitem_daily_summary.usage_start,
                    reporting_awscostentrylineitem_daily_summary.instance_type,
                    unnest(reporting_awscostentrylineitem_daily_summary.resource_ids) AS resource_id
                   FROM template0.reporting_awscostentrylineitem_daily_summary
                  WHERE ((reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_awscostentrylineitem_daily_summary.instance_type IS NOT NULL))) x
          GROUP BY x.usage_start, x.instance_type) r ON (((c.usage_start = r.usage_start) AND ((c.instance_type)::text = (r.instance_type)::text))))
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_compute_summary OWNER TO table_owner;

--
-- Name: reporting_aws_compute_summary_by_account; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_compute_summary_by_account AS
 SELECT row_number() OVER (ORDER BY c.usage_start, c.usage_account_id, c.instance_type) AS id,
    c.usage_start,
    c.usage_start AS usage_end,
    c.usage_account_id,
    c.account_alias_id,
    c.organizational_unit_id,
    c.instance_type,
    r.resource_ids,
    cardinality(r.resource_ids) AS resource_count,
    c.usage_amount,
    c.unit,
    c.unblended_cost,
    c.markup_cost,
    c.currency_code,
    c.source_uuid
   FROM (( SELECT reporting_awscostentrylineitem_daily_summary.usage_start,
            reporting_awscostentrylineitem_daily_summary.usage_account_id,
            max(reporting_awscostentrylineitem_daily_summary.account_alias_id) AS account_alias_id,
            max(reporting_awscostentrylineitem_daily_summary.organizational_unit_id) AS organizational_unit_id,
            reporting_awscostentrylineitem_daily_summary.instance_type,
            sum(reporting_awscostentrylineitem_daily_summary.usage_amount) AS usage_amount,
            max((reporting_awscostentrylineitem_daily_summary.unit)::text) AS unit,
            sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
            sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
            max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
            (max((reporting_awscostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
           FROM template0.reporting_awscostentrylineitem_daily_summary
          WHERE ((reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_awscostentrylineitem_daily_summary.instance_type IS NOT NULL))
          GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.instance_type) c
     JOIN ( SELECT x.usage_start,
            x.usage_account_id,
            max(x.account_alias_id) AS account_alias_id,
            x.instance_type,
            array_agg(DISTINCT x.resource_id ORDER BY x.resource_id) AS resource_ids
           FROM ( SELECT reporting_awscostentrylineitem_daily_summary.usage_start,
                    reporting_awscostentrylineitem_daily_summary.usage_account_id,
                    reporting_awscostentrylineitem_daily_summary.account_alias_id,
                    reporting_awscostentrylineitem_daily_summary.instance_type,
                    unnest(reporting_awscostentrylineitem_daily_summary.resource_ids) AS resource_id
                   FROM template0.reporting_awscostentrylineitem_daily_summary
                  WHERE ((reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_awscostentrylineitem_daily_summary.instance_type IS NOT NULL))) x
          GROUP BY x.usage_start, x.usage_account_id, x.instance_type) r ON (((c.usage_start = r.usage_start) AND ((c.instance_type)::text = (r.instance_type)::text) AND ((c.usage_account_id)::text = (r.usage_account_id)::text))))
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_compute_summary_by_account OWNER TO table_owner;

--
-- Name: reporting_aws_compute_summary_by_region; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_compute_summary_by_region AS
 SELECT row_number() OVER (ORDER BY c.usage_start, c.usage_account_id, c.region, c.availability_zone, c.instance_type) AS id,
    c.usage_start,
    c.usage_start AS usage_end,
    c.usage_account_id,
    c.account_alias_id,
    c.organizational_unit_id,
    c.region,
    c.availability_zone,
    c.instance_type,
    r.resource_ids,
    cardinality(r.resource_ids) AS resource_count,
    c.usage_amount,
    c.unit,
    c.unblended_cost,
    c.markup_cost,
    c.currency_code,
    c.source_uuid
   FROM (( SELECT reporting_awscostentrylineitem_daily_summary.usage_start,
            reporting_awscostentrylineitem_daily_summary.usage_account_id,
            max(reporting_awscostentrylineitem_daily_summary.account_alias_id) AS account_alias_id,
            max(reporting_awscostentrylineitem_daily_summary.organizational_unit_id) AS organizational_unit_id,
            reporting_awscostentrylineitem_daily_summary.region,
            reporting_awscostentrylineitem_daily_summary.availability_zone,
            reporting_awscostentrylineitem_daily_summary.instance_type,
            sum(reporting_awscostentrylineitem_daily_summary.usage_amount) AS usage_amount,
            max((reporting_awscostentrylineitem_daily_summary.unit)::text) AS unit,
            sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
            sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
            max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
            (max((reporting_awscostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
           FROM template0.reporting_awscostentrylineitem_daily_summary
          WHERE ((reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date) AND (reporting_awscostentrylineitem_daily_summary.instance_type IS NOT NULL))
          GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.region, reporting_awscostentrylineitem_daily_summary.availability_zone, reporting_awscostentrylineitem_daily_summary.instance_type) c
     JOIN ( SELECT x.usage_start,
            x.usage_account_id,
            max(x.account_alias_id) AS account_alias_id,
            x.region,
            x.availability_zone,
            x.instance_type,
            array_agg(DISTINCT x.resource_id ORDER BY x.resource_id) AS resource_ids
           FROM ( SELECT reporting_awscostentrylineitem_daily_summary.usage_start,
                    reporting_awscostentrylineitem_daily_summary.usage_account_id,
                    reporting_awscostentrylineitem_daily_summary.account_alias_id,
                    reporting_awscostentrylineitem_daily_summary.region,
                    reporting_awscostentrylineitem_daily_summary.availability_zone,
                    reporting_awscostentrylineitem_daily_summary.instance_type,
                    unnest(reporting_awscostentrylineitem_daily_summary.resource_ids) AS resource_id
                   FROM template0.reporting_awscostentrylineitem_daily_summary
                  WHERE ((reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_awscostentrylineitem_daily_summary.instance_type IS NOT NULL))) x
          GROUP BY x.usage_start, x.usage_account_id, x.region, x.availability_zone, x.instance_type) r ON (((c.usage_start = r.usage_start) AND ((c.region)::text = (r.region)::text) AND ((c.availability_zone)::text = (r.availability_zone)::text) AND ((c.instance_type)::text = (r.instance_type)::text) AND ((c.usage_account_id)::text = (r.usage_account_id)::text))))
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_compute_summary_by_region OWNER TO table_owner;

--
-- Name: reporting_aws_compute_summary_by_service; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_compute_summary_by_service AS
 SELECT row_number() OVER (ORDER BY c.usage_start, c.usage_account_id, c.product_code, c.product_family, c.instance_type) AS id,
    c.usage_start,
    c.usage_start AS usage_end,
    c.usage_account_id,
    c.account_alias_id,
    c.organizational_unit_id,
    c.product_code,
    c.product_family,
    c.instance_type,
    r.resource_ids,
    cardinality(r.resource_ids) AS resource_count,
    c.usage_amount,
    c.unit,
    c.unblended_cost,
    c.markup_cost,
    c.currency_code,
    c.source_uuid
   FROM (( SELECT reporting_awscostentrylineitem_daily_summary.usage_start,
            reporting_awscostentrylineitem_daily_summary.usage_account_id,
            max(reporting_awscostentrylineitem_daily_summary.account_alias_id) AS account_alias_id,
            max(reporting_awscostentrylineitem_daily_summary.organizational_unit_id) AS organizational_unit_id,
            reporting_awscostentrylineitem_daily_summary.product_code,
            reporting_awscostentrylineitem_daily_summary.product_family,
            reporting_awscostentrylineitem_daily_summary.instance_type,
            sum(reporting_awscostentrylineitem_daily_summary.usage_amount) AS usage_amount,
            max((reporting_awscostentrylineitem_daily_summary.unit)::text) AS unit,
            sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
            sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
            max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
            (max((reporting_awscostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
           FROM template0.reporting_awscostentrylineitem_daily_summary
          WHERE ((reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_awscostentrylineitem_daily_summary.instance_type IS NOT NULL))
          GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.product_code, reporting_awscostentrylineitem_daily_summary.product_family, reporting_awscostentrylineitem_daily_summary.instance_type) c
     JOIN ( SELECT x.usage_start,
            x.usage_account_id,
            max(x.account_alias_id) AS account_alias_id,
            x.product_code,
            x.product_family,
            x.instance_type,
            array_agg(DISTINCT x.resource_id ORDER BY x.resource_id) AS resource_ids
           FROM ( SELECT reporting_awscostentrylineitem_daily_summary.usage_start,
                    reporting_awscostentrylineitem_daily_summary.usage_account_id,
                    reporting_awscostentrylineitem_daily_summary.account_alias_id,
                    reporting_awscostentrylineitem_daily_summary.product_code,
                    reporting_awscostentrylineitem_daily_summary.product_family,
                    reporting_awscostentrylineitem_daily_summary.instance_type,
                    unnest(reporting_awscostentrylineitem_daily_summary.resource_ids) AS resource_id
                   FROM template0.reporting_awscostentrylineitem_daily_summary
                  WHERE ((reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_awscostentrylineitem_daily_summary.instance_type IS NOT NULL))) x
          GROUP BY x.usage_start, x.usage_account_id, x.product_code, x.product_family, x.instance_type) r ON (((c.usage_start = r.usage_start) AND ((c.product_code)::text = (r.product_code)::text) AND ((c.product_family)::text = (r.product_family)::text) AND ((c.instance_type)::text = (r.instance_type)::text) AND ((c.usage_account_id)::text = (r.usage_account_id)::text))))
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_compute_summary_by_service OWNER TO table_owner;

--
-- Name: reporting_aws_cost_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_cost_summary AS
 SELECT row_number() OVER (ORDER BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.source_uuid) AS id,
    reporting_awscostentrylineitem_daily_summary.usage_start,
    reporting_awscostentrylineitem_daily_summary.usage_start AS usage_end,
    sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
    reporting_awscostentrylineitem_daily_summary.source_uuid
   FROM template0.reporting_awscostentrylineitem_daily_summary
  WHERE (reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_cost_summary OWNER TO table_owner;

--
-- Name: reporting_aws_cost_summary_by_account; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_cost_summary_by_account AS
 SELECT row_number() OVER (ORDER BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id) AS id,
    reporting_awscostentrylineitem_daily_summary.usage_start,
    reporting_awscostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_awscostentrylineitem_daily_summary.usage_account_id,
    max(reporting_awscostentrylineitem_daily_summary.account_alias_id) AS account_alias_id,
    max(reporting_awscostentrylineitem_daily_summary.organizational_unit_id) AS organizational_unit_id,
    sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_awscostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_awscostentrylineitem_daily_summary
  WHERE (reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_cost_summary_by_account OWNER TO table_owner;

--
-- Name: reporting_aws_cost_summary_by_region; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_cost_summary_by_region AS
 SELECT row_number() OVER (ORDER BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.region, reporting_awscostentrylineitem_daily_summary.availability_zone) AS id,
    reporting_awscostentrylineitem_daily_summary.usage_start,
    reporting_awscostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_awscostentrylineitem_daily_summary.usage_account_id,
    max(reporting_awscostentrylineitem_daily_summary.account_alias_id) AS account_alias_id,
    max(reporting_awscostentrylineitem_daily_summary.organizational_unit_id) AS organizational_unit_id,
    reporting_awscostentrylineitem_daily_summary.region,
    reporting_awscostentrylineitem_daily_summary.availability_zone,
    sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_awscostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_awscostentrylineitem_daily_summary
  WHERE (reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.region, reporting_awscostentrylineitem_daily_summary.availability_zone
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_cost_summary_by_region OWNER TO table_owner;

--
-- Name: reporting_aws_cost_summary_by_service; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_cost_summary_by_service AS
 SELECT row_number() OVER (ORDER BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.product_code, reporting_awscostentrylineitem_daily_summary.product_family) AS id,
    reporting_awscostentrylineitem_daily_summary.usage_start,
    reporting_awscostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_awscostentrylineitem_daily_summary.usage_account_id,
    max(reporting_awscostentrylineitem_daily_summary.account_alias_id) AS account_alias_id,
    max(reporting_awscostentrylineitem_daily_summary.organizational_unit_id) AS organizational_unit_id,
    reporting_awscostentrylineitem_daily_summary.product_code,
    reporting_awscostentrylineitem_daily_summary.product_family,
    sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_awscostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_awscostentrylineitem_daily_summary
  WHERE (reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.product_code, reporting_awscostentrylineitem_daily_summary.product_family
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_cost_summary_by_service OWNER TO table_owner;

--
-- Name: reporting_aws_database_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_database_summary AS
 SELECT row_number() OVER (ORDER BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.product_code) AS id,
    reporting_awscostentrylineitem_daily_summary.usage_start,
    reporting_awscostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_awscostentrylineitem_daily_summary.usage_account_id,
    max(reporting_awscostentrylineitem_daily_summary.account_alias_id) AS account_alias_id,
    max(reporting_awscostentrylineitem_daily_summary.organizational_unit_id) AS organizational_unit_id,
    reporting_awscostentrylineitem_daily_summary.product_code,
    sum(reporting_awscostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_awscostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_awscostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_awscostentrylineitem_daily_summary
  WHERE (((reporting_awscostentrylineitem_daily_summary.product_code)::text = ANY ((ARRAY['AmazonRDS'::character varying, 'AmazonDynamoDB'::character varying, 'AmazonElastiCache'::character varying, 'AmazonNeptune'::character varying, 'AmazonRedshift'::character varying, 'AmazonDocumentDB'::character varying])::text[])) AND (reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date))
  GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.product_code
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_database_summary OWNER TO table_owner;

--
-- Name: reporting_aws_network_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_network_summary AS
 SELECT row_number() OVER (ORDER BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.product_code) AS id,
    reporting_awscostentrylineitem_daily_summary.usage_start,
    reporting_awscostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_awscostentrylineitem_daily_summary.usage_account_id,
    max(reporting_awscostentrylineitem_daily_summary.account_alias_id) AS account_alias_id,
    max(reporting_awscostentrylineitem_daily_summary.organizational_unit_id) AS organizational_unit_id,
    reporting_awscostentrylineitem_daily_summary.product_code,
    sum(reporting_awscostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_awscostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_awscostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_awscostentrylineitem_daily_summary
  WHERE (((reporting_awscostentrylineitem_daily_summary.product_code)::text = ANY ((ARRAY['AmazonVPC'::character varying, 'AmazonCloudFront'::character varying, 'AmazonRoute53'::character varying, 'AmazonAPIGateway'::character varying])::text[])) AND (reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date))
  GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.product_code
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_network_summary OWNER TO table_owner;

--
-- Name: reporting_aws_storage_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_storage_summary AS
 SELECT row_number() OVER (ORDER BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.source_uuid, reporting_awscostentrylineitem_daily_summary.product_family) AS id,
    reporting_awscostentrylineitem_daily_summary.usage_start,
    reporting_awscostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_awscostentrylineitem_daily_summary.product_family,
    sum(reporting_awscostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_awscostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
    reporting_awscostentrylineitem_daily_summary.source_uuid
   FROM template0.reporting_awscostentrylineitem_daily_summary
  WHERE (((reporting_awscostentrylineitem_daily_summary.product_family)::text ~~ '%Storage%'::text) AND ((reporting_awscostentrylineitem_daily_summary.unit)::text = 'GB-Mo'::text) AND (reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date))
  GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.source_uuid, reporting_awscostentrylineitem_daily_summary.product_family
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_storage_summary OWNER TO table_owner;

--
-- Name: reporting_aws_storage_summary_by_account; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_storage_summary_by_account AS
 SELECT row_number() OVER (ORDER BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.product_family) AS id,
    reporting_awscostentrylineitem_daily_summary.usage_start,
    reporting_awscostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_awscostentrylineitem_daily_summary.usage_account_id,
    max(reporting_awscostentrylineitem_daily_summary.account_alias_id) AS account_alias_id,
    max(reporting_awscostentrylineitem_daily_summary.organizational_unit_id) AS organizational_unit_id,
    reporting_awscostentrylineitem_daily_summary.product_family,
    sum(reporting_awscostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_awscostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_awscostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_awscostentrylineitem_daily_summary
  WHERE (((reporting_awscostentrylineitem_daily_summary.product_family)::text ~~ '%Storage%'::text) AND ((reporting_awscostentrylineitem_daily_summary.unit)::text = 'GB-Mo'::text) AND (reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date))
  GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.product_family
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_storage_summary_by_account OWNER TO table_owner;

--
-- Name: reporting_aws_storage_summary_by_region; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_storage_summary_by_region AS
 SELECT row_number() OVER (ORDER BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.region, reporting_awscostentrylineitem_daily_summary.availability_zone, reporting_awscostentrylineitem_daily_summary.product_family) AS id,
    reporting_awscostentrylineitem_daily_summary.usage_start,
    reporting_awscostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_awscostentrylineitem_daily_summary.usage_account_id,
    max(reporting_awscostentrylineitem_daily_summary.account_alias_id) AS account_alias_id,
    max(reporting_awscostentrylineitem_daily_summary.organizational_unit_id) AS organizational_unit_id,
    reporting_awscostentrylineitem_daily_summary.region,
    reporting_awscostentrylineitem_daily_summary.availability_zone,
    reporting_awscostentrylineitem_daily_summary.product_family,
    sum(reporting_awscostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_awscostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_awscostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_awscostentrylineitem_daily_summary
  WHERE (((reporting_awscostentrylineitem_daily_summary.product_family)::text ~~ '%Storage%'::text) AND ((reporting_awscostentrylineitem_daily_summary.unit)::text = 'GB-Mo'::text) AND (reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date))
  GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.region, reporting_awscostentrylineitem_daily_summary.availability_zone, reporting_awscostentrylineitem_daily_summary.product_family
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_storage_summary_by_region OWNER TO table_owner;

--
-- Name: reporting_aws_storage_summary_by_service; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_aws_storage_summary_by_service AS
 SELECT row_number() OVER (ORDER BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.product_code, reporting_awscostentrylineitem_daily_summary.product_family) AS id,
    reporting_awscostentrylineitem_daily_summary.usage_start,
    reporting_awscostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_awscostentrylineitem_daily_summary.usage_account_id,
    max(reporting_awscostentrylineitem_daily_summary.account_alias_id) AS account_alias_id,
    max(reporting_awscostentrylineitem_daily_summary.organizational_unit_id) AS organizational_unit_id,
    reporting_awscostentrylineitem_daily_summary.product_code,
    reporting_awscostentrylineitem_daily_summary.product_family,
    sum(reporting_awscostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_awscostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_awscostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_awscostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_awscostentrylineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_awscostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_awscostentrylineitem_daily_summary
  WHERE (((reporting_awscostentrylineitem_daily_summary.product_family)::text ~~ '%Storage%'::text) AND ((reporting_awscostentrylineitem_daily_summary.unit)::text = 'GB-Mo'::text) AND (reporting_awscostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date))
  GROUP BY reporting_awscostentrylineitem_daily_summary.usage_start, reporting_awscostentrylineitem_daily_summary.usage_account_id, reporting_awscostentrylineitem_daily_summary.product_code, reporting_awscostentrylineitem_daily_summary.product_family
  WITH NO DATA;


ALTER TABLE template0.reporting_aws_storage_summary_by_service OWNER TO table_owner;

--
-- Name: reporting_awsaccountalias; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awsaccountalias (
    id integer NOT NULL,
    account_id character varying(50) NOT NULL,
    account_alias character varying(63)
);


ALTER TABLE template0.reporting_awsaccountalias OWNER TO table_owner;

--
-- Name: reporting_awsaccountalias_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_awsaccountalias_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_awsaccountalias_id_seq OWNER TO table_owner;

--
-- Name: reporting_awsaccountalias_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_awsaccountalias_id_seq OWNED BY template0.reporting_awsaccountalias.id;


--
-- Name: reporting_awscostentry; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awscostentry (
    id integer NOT NULL,
    interval_start timestamp with time zone NOT NULL,
    interval_end timestamp with time zone NOT NULL,
    bill_id integer NOT NULL
);


ALTER TABLE template0.reporting_awscostentry OWNER TO table_owner;

--
-- Name: reporting_awscostentry_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_awscostentry_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_awscostentry_id_seq OWNER TO table_owner;

--
-- Name: reporting_awscostentry_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_awscostentry_id_seq OWNED BY template0.reporting_awscostentry.id;


--
-- Name: reporting_awscostentrybill; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awscostentrybill (
    id integer NOT NULL,
    billing_resource character varying(50) NOT NULL,
    bill_type character varying(50),
    payer_account_id character varying(50),
    billing_period_start timestamp with time zone NOT NULL,
    billing_period_end timestamp with time zone NOT NULL,
    summary_data_creation_datetime timestamp with time zone,
    summary_data_updated_datetime timestamp with time zone,
    finalized_datetime timestamp with time zone,
    derived_cost_datetime timestamp with time zone,
    provider_id uuid NOT NULL
);


ALTER TABLE template0.reporting_awscostentrybill OWNER TO table_owner;

--
-- Name: reporting_awscostentrybill_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_awscostentrybill_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_awscostentrybill_id_seq OWNER TO table_owner;

--
-- Name: reporting_awscostentrybill_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_awscostentrybill_id_seq OWNED BY template0.reporting_awscostentrybill.id;


--
-- Name: reporting_awscostentrylineitem; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awscostentrylineitem (
    id bigint NOT NULL,
    tags jsonb,
    invoice_id character varying(63),
    line_item_type character varying(50) NOT NULL,
    usage_account_id character varying(50) NOT NULL,
    usage_start timestamp with time zone NOT NULL,
    usage_end timestamp with time zone NOT NULL,
    product_code character varying(50) NOT NULL,
    usage_type character varying(50),
    operation character varying(50),
    availability_zone character varying(50),
    resource_id character varying(256),
    usage_amount numeric(24,9),
    normalization_factor double precision,
    normalized_usage_amount numeric(24,9),
    currency_code character varying(10) NOT NULL,
    unblended_rate numeric(24,9),
    unblended_cost numeric(24,9),
    blended_rate numeric(24,9),
    blended_cost numeric(24,9),
    public_on_demand_cost numeric(24,9),
    public_on_demand_rate numeric(24,9),
    reservation_amortized_upfront_fee numeric(24,9),
    reservation_amortized_upfront_cost_for_usage numeric(24,9),
    reservation_recurring_fee_for_usage numeric(24,9),
    reservation_unused_quantity numeric(24,9),
    reservation_unused_recurring_fee numeric(24,9),
    tax_type text,
    cost_entry_id integer NOT NULL,
    cost_entry_bill_id integer NOT NULL,
    cost_entry_pricing_id integer,
    cost_entry_product_id integer,
    cost_entry_reservation_id integer
);


ALTER TABLE template0.reporting_awscostentrylineitem OWNER TO table_owner;

--
-- Name: reporting_awscostentrylineitem_daily; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awscostentrylineitem_daily (
    id bigint NOT NULL,
    line_item_type character varying(50) NOT NULL,
    usage_account_id character varying(50) NOT NULL,
    usage_start date NOT NULL,
    usage_end date,
    product_code character varying(50) NOT NULL,
    usage_type character varying(50),
    operation character varying(50),
    availability_zone character varying(50),
    resource_id character varying(256),
    usage_amount numeric(24,9),
    normalization_factor double precision,
    normalized_usage_amount double precision,
    currency_code character varying(10) NOT NULL,
    unblended_rate numeric(24,9),
    unblended_cost numeric(24,9),
    blended_rate numeric(24,9),
    blended_cost numeric(24,9),
    public_on_demand_cost numeric(24,9),
    public_on_demand_rate numeric(24,9),
    tax_type text,
    tags jsonb,
    cost_entry_bill_id integer,
    cost_entry_pricing_id integer,
    cost_entry_product_id integer,
    cost_entry_reservation_id integer
);


ALTER TABLE template0.reporting_awscostentrylineitem_daily OWNER TO table_owner;

--
-- Name: reporting_awscostentrylineitem_daily_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_awscostentrylineitem_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_awscostentrylineitem_daily_id_seq OWNER TO table_owner;

--
-- Name: reporting_awscostentrylineitem_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_awscostentrylineitem_daily_id_seq OWNED BY template0.reporting_awscostentrylineitem_daily.id;


--
-- Name: reporting_awscostentrylineitem_daily_summary_default; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awscostentrylineitem_daily_summary_default (
    usage_start date NOT NULL,
    usage_end date,
    usage_account_id character varying(50) NOT NULL,
    product_code character varying(50) NOT NULL,
    product_family character varying(150),
    availability_zone character varying(50),
    region character varying(50),
    instance_type character varying(50),
    unit character varying(63),
    resource_ids text[],
    resource_count integer,
    usage_amount numeric(24,9),
    normalization_factor double precision,
    normalized_usage_amount double precision,
    currency_code character varying(10) NOT NULL,
    unblended_rate numeric(24,9),
    unblended_cost numeric(24,9),
    markup_cost numeric(24,9),
    blended_rate numeric(24,9),
    blended_cost numeric(24,9),
    public_on_demand_cost numeric(24,9),
    public_on_demand_rate numeric(24,9),
    tax_type text,
    tags jsonb,
    source_uuid uuid,
    account_alias_id integer,
    cost_entry_bill_id integer,
    organizational_unit_id integer,
    uuid uuid NOT NULL
);
ALTER TABLE ONLY template0.reporting_awscostentrylineitem_daily_summary ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summary_default DEFAULT;


ALTER TABLE template0.reporting_awscostentrylineitem_daily_summary_default OWNER TO table_owner;

--
-- Name: reporting_awscostentrylineitem_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_awscostentrylineitem_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_awscostentrylineitem_id_seq OWNER TO table_owner;

--
-- Name: reporting_awscostentrylineitem_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_awscostentrylineitem_id_seq OWNED BY template0.reporting_awscostentrylineitem.id;


--
-- Name: reporting_awscostentrypricing; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awscostentrypricing (
    id integer NOT NULL,
    term character varying(63),
    unit character varying(63)
);


ALTER TABLE template0.reporting_awscostentrypricing OWNER TO table_owner;

--
-- Name: reporting_awscostentrypricing_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_awscostentrypricing_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_awscostentrypricing_id_seq OWNER TO table_owner;

--
-- Name: reporting_awscostentrypricing_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_awscostentrypricing_id_seq OWNED BY template0.reporting_awscostentrypricing.id;


--
-- Name: reporting_awscostentryproduct; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awscostentryproduct (
    id integer NOT NULL,
    sku character varying(128),
    product_name text,
    product_family character varying(150),
    service_code character varying(50),
    region character varying(50),
    instance_type character varying(50),
    memory double precision,
    memory_unit character varying(24),
    vcpu integer,
    CONSTRAINT reporting_awscostentryproduct_vcpu_check CHECK ((vcpu >= 0))
);


ALTER TABLE template0.reporting_awscostentryproduct OWNER TO table_owner;

--
-- Name: reporting_awscostentryproduct_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_awscostentryproduct_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_awscostentryproduct_id_seq OWNER TO table_owner;

--
-- Name: reporting_awscostentryproduct_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_awscostentryproduct_id_seq OWNED BY template0.reporting_awscostentryproduct.id;


--
-- Name: reporting_awscostentryreservation; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awscostentryreservation (
    id integer NOT NULL,
    reservation_arn text NOT NULL,
    number_of_reservations integer,
    units_per_reservation numeric(24,9),
    start_time timestamp with time zone,
    end_time timestamp with time zone,
    CONSTRAINT reporting_awscostentryreservation_number_of_reservations_check CHECK ((number_of_reservations >= 0))
);


ALTER TABLE template0.reporting_awscostentryreservation OWNER TO table_owner;

--
-- Name: reporting_awscostentryreservation_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_awscostentryreservation_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_awscostentryreservation_id_seq OWNER TO table_owner;

--
-- Name: reporting_awscostentryreservation_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_awscostentryreservation_id_seq OWNED BY template0.reporting_awscostentryreservation.id;


--
-- Name: reporting_awsenabledtagkeys; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awsenabledtagkeys (
    key character varying(253) NOT NULL,
    enabled boolean DEFAULT true NOT NULL
);


ALTER TABLE template0.reporting_awsenabledtagkeys OWNER TO table_owner;

--
-- Name: reporting_awsorganizationalunit; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awsorganizationalunit (
    id integer NOT NULL,
    org_unit_name character varying(250) NOT NULL,
    org_unit_id character varying(50) NOT NULL,
    org_unit_path text NOT NULL,
    level smallint NOT NULL,
    created_timestamp date NOT NULL,
    deleted_timestamp date,
    account_alias_id integer,
    provider_id uuid,
    CONSTRAINT reporting_awsorganizationalunit_level_check CHECK ((level >= 0))
);


ALTER TABLE template0.reporting_awsorganizationalunit OWNER TO table_owner;

--
-- Name: reporting_awsorganizationalunit_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_awsorganizationalunit_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_awsorganizationalunit_id_seq OWNER TO table_owner;

--
-- Name: reporting_awsorganizationalunit_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_awsorganizationalunit_id_seq OWNED BY template0.reporting_awsorganizationalunit.id;


--
-- Name: reporting_awstags_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awstags_summary (
    uuid uuid NOT NULL,
    key text NOT NULL,
    "values" text[] NOT NULL,
    usage_account_id text,
    account_alias_id integer,
    cost_entry_bill_id integer NOT NULL
);


ALTER TABLE template0.reporting_awstags_summary OWNER TO table_owner;

--
-- Name: reporting_awstags_values; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_awstags_values (
    uuid uuid NOT NULL,
    key text NOT NULL,
    value text NOT NULL,
    usage_account_ids text[] NOT NULL,
    account_aliases text[] NOT NULL
);


ALTER TABLE template0.reporting_awstags_values OWNER TO table_owner;

--
-- Name: reporting_azurecostentrylineitem_daily_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_azurecostentrylineitem_daily_summary (
    subscription_guid text NOT NULL,
    instance_type text,
    service_name text,
    resource_location text,
    tags jsonb,
    usage_start date NOT NULL,
    usage_end date,
    usage_quantity numeric(24,9),
    pretax_cost numeric(24,9),
    markup_cost numeric(24,9),
    currency text,
    instance_ids text[],
    instance_count integer,
    unit_of_measure text,
    source_uuid uuid,
    cost_entry_bill_id integer NOT NULL,
    meter_id integer,
    uuid uuid NOT NULL
)
PARTITION BY RANGE (usage_start);


ALTER TABLE template0.reporting_azurecostentrylineitem_daily_summary OWNER TO table_owner;

--
-- Name: reporting_azure_compute_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_azure_compute_summary AS
 SELECT row_number() OVER (ORDER BY c.usage_start, c.subscription_guid, c.instance_type) AS id,
    c.usage_start,
    c.usage_start AS usage_end,
    c.subscription_guid,
    c.instance_type,
    r.instance_ids,
    cardinality(r.instance_ids) AS instance_count,
    c.usage_quantity,
    c.unit_of_measure,
    c.pretax_cost,
    c.markup_cost,
    c.currency,
    c.source_uuid
   FROM (( SELECT reporting_azurecostentrylineitem_daily_summary.usage_start,
            reporting_azurecostentrylineitem_daily_summary.subscription_guid,
            reporting_azurecostentrylineitem_daily_summary.instance_type,
            sum(reporting_azurecostentrylineitem_daily_summary.usage_quantity) AS usage_quantity,
            max(reporting_azurecostentrylineitem_daily_summary.unit_of_measure) AS unit_of_measure,
            sum(reporting_azurecostentrylineitem_daily_summary.pretax_cost) AS pretax_cost,
            sum(reporting_azurecostentrylineitem_daily_summary.markup_cost) AS markup_cost,
            max(reporting_azurecostentrylineitem_daily_summary.currency) AS currency,
            (max((reporting_azurecostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
           FROM template0.reporting_azurecostentrylineitem_daily_summary
          WHERE ((reporting_azurecostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_azurecostentrylineitem_daily_summary.instance_type IS NOT NULL) AND (reporting_azurecostentrylineitem_daily_summary.unit_of_measure = 'Hrs'::text))
          GROUP BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid, reporting_azurecostentrylineitem_daily_summary.instance_type) c
     JOIN ( SELECT x.usage_start,
            x.subscription_guid,
            x.instance_type,
            array_agg(DISTINCT x.instance_id ORDER BY x.instance_id) AS instance_ids
           FROM ( SELECT reporting_azurecostentrylineitem_daily_summary.usage_start,
                    reporting_azurecostentrylineitem_daily_summary.subscription_guid,
                    reporting_azurecostentrylineitem_daily_summary.instance_type,
                    unnest(reporting_azurecostentrylineitem_daily_summary.instance_ids) AS instance_id
                   FROM template0.reporting_azurecostentrylineitem_daily_summary
                  WHERE ((reporting_azurecostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_azurecostentrylineitem_daily_summary.instance_type IS NOT NULL))) x
          GROUP BY x.usage_start, x.subscription_guid, x.instance_type) r ON (((c.usage_start = r.usage_start) AND (c.subscription_guid = r.subscription_guid) AND (c.instance_type = r.instance_type))))
  WITH NO DATA;


ALTER TABLE template0.reporting_azure_compute_summary OWNER TO table_owner;

--
-- Name: reporting_azure_cost_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_azure_cost_summary AS
 SELECT row_number() OVER (ORDER BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.source_uuid) AS id,
    reporting_azurecostentrylineitem_daily_summary.usage_start,
    reporting_azurecostentrylineitem_daily_summary.usage_start AS usage_end,
    sum(reporting_azurecostentrylineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_azurecostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_azurecostentrylineitem_daily_summary.currency) AS currency,
    reporting_azurecostentrylineitem_daily_summary.source_uuid
   FROM template0.reporting_azurecostentrylineitem_daily_summary
  WHERE (reporting_azurecostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_azure_cost_summary OWNER TO table_owner;

--
-- Name: reporting_azure_cost_summary_by_account; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_azure_cost_summary_by_account AS
 SELECT row_number() OVER (ORDER BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid) AS id,
    reporting_azurecostentrylineitem_daily_summary.usage_start,
    reporting_azurecostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_azurecostentrylineitem_daily_summary.subscription_guid,
    sum(reporting_azurecostentrylineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_azurecostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_azurecostentrylineitem_daily_summary.currency) AS currency,
    (max((reporting_azurecostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_azurecostentrylineitem_daily_summary
  WHERE (reporting_azurecostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid
  WITH NO DATA;


ALTER TABLE template0.reporting_azure_cost_summary_by_account OWNER TO table_owner;

--
-- Name: reporting_azure_cost_summary_by_location; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_azure_cost_summary_by_location AS
 SELECT row_number() OVER (ORDER BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid, reporting_azurecostentrylineitem_daily_summary.resource_location) AS id,
    reporting_azurecostentrylineitem_daily_summary.usage_start,
    reporting_azurecostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_azurecostentrylineitem_daily_summary.subscription_guid,
    reporting_azurecostentrylineitem_daily_summary.resource_location,
    sum(reporting_azurecostentrylineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_azurecostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_azurecostentrylineitem_daily_summary.currency) AS currency,
    (max((reporting_azurecostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_azurecostentrylineitem_daily_summary
  WHERE (reporting_azurecostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid, reporting_azurecostentrylineitem_daily_summary.resource_location
  WITH NO DATA;


ALTER TABLE template0.reporting_azure_cost_summary_by_location OWNER TO table_owner;

--
-- Name: reporting_azure_cost_summary_by_service; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_azure_cost_summary_by_service AS
 SELECT row_number() OVER (ORDER BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid, reporting_azurecostentrylineitem_daily_summary.service_name) AS id,
    reporting_azurecostentrylineitem_daily_summary.usage_start,
    reporting_azurecostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_azurecostentrylineitem_daily_summary.subscription_guid,
    reporting_azurecostentrylineitem_daily_summary.service_name,
    sum(reporting_azurecostentrylineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_azurecostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_azurecostentrylineitem_daily_summary.currency) AS currency,
    (max((reporting_azurecostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_azurecostentrylineitem_daily_summary
  WHERE (reporting_azurecostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid, reporting_azurecostentrylineitem_daily_summary.service_name
  WITH NO DATA;


ALTER TABLE template0.reporting_azure_cost_summary_by_service OWNER TO table_owner;

--
-- Name: reporting_azure_database_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_azure_database_summary AS
 SELECT row_number() OVER (ORDER BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid, reporting_azurecostentrylineitem_daily_summary.service_name) AS id,
    reporting_azurecostentrylineitem_daily_summary.usage_start,
    reporting_azurecostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_azurecostentrylineitem_daily_summary.subscription_guid,
    reporting_azurecostentrylineitem_daily_summary.service_name,
    sum(reporting_azurecostentrylineitem_daily_summary.usage_quantity) AS usage_quantity,
    max(reporting_azurecostentrylineitem_daily_summary.unit_of_measure) AS unit_of_measure,
    sum(reporting_azurecostentrylineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_azurecostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_azurecostentrylineitem_daily_summary.currency) AS currency,
    (max((reporting_azurecostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_azurecostentrylineitem_daily_summary
  WHERE ((reporting_azurecostentrylineitem_daily_summary.service_name = ANY (ARRAY['Cosmos DB'::text, 'Cache for Redis'::text])) OR ((reporting_azurecostentrylineitem_daily_summary.service_name ~~* '%database%'::text) AND (reporting_azurecostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)))
  GROUP BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid, reporting_azurecostentrylineitem_daily_summary.service_name
  WITH NO DATA;


ALTER TABLE template0.reporting_azure_database_summary OWNER TO table_owner;

--
-- Name: reporting_azure_network_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_azure_network_summary AS
 SELECT row_number() OVER (ORDER BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid, reporting_azurecostentrylineitem_daily_summary.service_name) AS id,
    reporting_azurecostentrylineitem_daily_summary.usage_start,
    reporting_azurecostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_azurecostentrylineitem_daily_summary.subscription_guid,
    reporting_azurecostentrylineitem_daily_summary.service_name,
    sum(reporting_azurecostentrylineitem_daily_summary.usage_quantity) AS usage_quantity,
    max(reporting_azurecostentrylineitem_daily_summary.unit_of_measure) AS unit_of_measure,
    sum(reporting_azurecostentrylineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_azurecostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_azurecostentrylineitem_daily_summary.currency) AS currency,
    (max((reporting_azurecostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_azurecostentrylineitem_daily_summary
  WHERE ((reporting_azurecostentrylineitem_daily_summary.service_name = ANY (ARRAY['Virtual Network'::text, 'VPN'::text, 'DNS'::text, 'Traffic Manager'::text, 'ExpressRoute'::text, 'Load Balancer'::text, 'Application Gateway'::text])) AND (reporting_azurecostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date))
  GROUP BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid, reporting_azurecostentrylineitem_daily_summary.service_name
  WITH NO DATA;


ALTER TABLE template0.reporting_azure_network_summary OWNER TO table_owner;

--
-- Name: reporting_azure_storage_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_azure_storage_summary AS
 SELECT row_number() OVER (ORDER BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid, reporting_azurecostentrylineitem_daily_summary.service_name) AS id,
    reporting_azurecostentrylineitem_daily_summary.usage_start,
    reporting_azurecostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_azurecostentrylineitem_daily_summary.subscription_guid,
    reporting_azurecostentrylineitem_daily_summary.service_name,
    sum(reporting_azurecostentrylineitem_daily_summary.usage_quantity) AS usage_quantity,
    max(reporting_azurecostentrylineitem_daily_summary.unit_of_measure) AS unit_of_measure,
    sum(reporting_azurecostentrylineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_azurecostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_azurecostentrylineitem_daily_summary.currency) AS currency,
    (max((reporting_azurecostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_azurecostentrylineitem_daily_summary
  WHERE ((reporting_azurecostentrylineitem_daily_summary.service_name ~~ '%Storage%'::text) AND (reporting_azurecostentrylineitem_daily_summary.unit_of_measure = 'GB-Mo'::text) AND (reporting_azurecostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date))
  GROUP BY reporting_azurecostentrylineitem_daily_summary.usage_start, reporting_azurecostentrylineitem_daily_summary.subscription_guid, reporting_azurecostentrylineitem_daily_summary.service_name
  WITH NO DATA;


ALTER TABLE template0.reporting_azure_storage_summary OWNER TO table_owner;

--
-- Name: reporting_azurecostentrybill; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_azurecostentrybill (
    id integer NOT NULL,
    billing_period_start timestamp with time zone NOT NULL,
    billing_period_end timestamp with time zone NOT NULL,
    summary_data_creation_datetime timestamp with time zone,
    summary_data_updated_datetime timestamp with time zone,
    finalized_datetime timestamp with time zone,
    derived_cost_datetime timestamp with time zone,
    provider_id uuid NOT NULL
);


ALTER TABLE template0.reporting_azurecostentrybill OWNER TO table_owner;

--
-- Name: reporting_azurecostentrybill_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_azurecostentrybill_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_azurecostentrybill_id_seq OWNER TO table_owner;

--
-- Name: reporting_azurecostentrybill_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_azurecostentrybill_id_seq OWNED BY template0.reporting_azurecostentrybill.id;


--
-- Name: reporting_azurecostentrylineitem_daily; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_azurecostentrylineitem_daily (
    id bigint NOT NULL,
    subscription_guid text NOT NULL,
    tags jsonb,
    usage_date date NOT NULL,
    usage_quantity numeric(24,9),
    pretax_cost numeric(24,9),
    cost_entry_bill_id integer NOT NULL,
    cost_entry_product_id integer,
    meter_id integer
);


ALTER TABLE template0.reporting_azurecostentrylineitem_daily OWNER TO table_owner;

--
-- Name: reporting_azurecostentrylineitem_daily_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_azurecostentrylineitem_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_azurecostentrylineitem_daily_id_seq OWNER TO table_owner;

--
-- Name: reporting_azurecostentrylineitem_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_azurecostentrylineitem_daily_id_seq OWNED BY template0.reporting_azurecostentrylineitem_daily.id;


--
-- Name: reporting_azurecostentrylineitem_daily_summary_default; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_azurecostentrylineitem_daily_summary_default (
    subscription_guid text NOT NULL,
    instance_type text,
    service_name text,
    resource_location text,
    tags jsonb,
    usage_start date NOT NULL,
    usage_end date,
    usage_quantity numeric(24,9),
    pretax_cost numeric(24,9),
    markup_cost numeric(24,9),
    currency text,
    instance_ids text[],
    instance_count integer,
    unit_of_measure text,
    source_uuid uuid,
    cost_entry_bill_id integer NOT NULL,
    meter_id integer,
    uuid uuid NOT NULL
);
ALTER TABLE ONLY template0.reporting_azurecostentrylineitem_daily_summary ATTACH PARTITION template0.reporting_azurecostentrylineitem_daily_summary_default DEFAULT;


ALTER TABLE template0.reporting_azurecostentrylineitem_daily_summary_default OWNER TO table_owner;

--
-- Name: reporting_azurecostentryproductservice; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_azurecostentryproductservice (
    id integer NOT NULL,
    instance_id text NOT NULL,
    resource_location text,
    consumed_service text,
    resource_type text,
    resource_group text,
    additional_info jsonb,
    service_tier text,
    service_name text,
    service_info1 text,
    service_info2 text,
    instance_type text,
    provider_id uuid
);


ALTER TABLE template0.reporting_azurecostentryproductservice OWNER TO table_owner;

--
-- Name: reporting_azurecostentryproductservice_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_azurecostentryproductservice_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_azurecostentryproductservice_id_seq OWNER TO table_owner;

--
-- Name: reporting_azurecostentryproductservice_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_azurecostentryproductservice_id_seq OWNED BY template0.reporting_azurecostentryproductservice.id;


--
-- Name: reporting_azureenabledtagkeys; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_azureenabledtagkeys (
    id bigint NOT NULL,
    key character varying(253) NOT NULL
);


ALTER TABLE template0.reporting_azureenabledtagkeys OWNER TO table_owner;

--
-- Name: reporting_azureenabledtagkeys_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_azureenabledtagkeys_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_azureenabledtagkeys_id_seq OWNER TO table_owner;

--
-- Name: reporting_azureenabledtagkeys_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_azureenabledtagkeys_id_seq OWNED BY template0.reporting_azureenabledtagkeys.id;


--
-- Name: reporting_azuremeter; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_azuremeter (
    id integer NOT NULL,
    meter_id uuid NOT NULL,
    meter_name text NOT NULL,
    meter_category text,
    meter_subcategory text,
    meter_region text,
    resource_rate numeric(24,9),
    currency text,
    unit_of_measure text,
    provider_id uuid
);


ALTER TABLE template0.reporting_azuremeter OWNER TO table_owner;

--
-- Name: reporting_azuremeter_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_azuremeter_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_azuremeter_id_seq OWNER TO table_owner;

--
-- Name: reporting_azuremeter_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_azuremeter_id_seq OWNED BY template0.reporting_azuremeter.id;


--
-- Name: reporting_azuretags_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_azuretags_summary (
    uuid uuid NOT NULL,
    key text NOT NULL,
    "values" text[] NOT NULL,
    subscription_guid text,
    cost_entry_bill_id integer NOT NULL
);


ALTER TABLE template0.reporting_azuretags_summary OWNER TO table_owner;

--
-- Name: reporting_azuretags_values; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_azuretags_values (
    uuid uuid NOT NULL,
    key text NOT NULL,
    value text NOT NULL,
    subscription_guids text[] NOT NULL
);


ALTER TABLE template0.reporting_azuretags_values OWNER TO table_owner;

--
-- Name: reporting_gcpcostentrylineitem_daily_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_gcpcostentrylineitem_daily_summary (
    uuid uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    account_id character varying(20) NOT NULL,
    project_id character varying(256) NOT NULL,
    project_name character varying(256) NOT NULL,
    service_id character varying(256),
    service_alias character varying(256),
    sku_id character varying(256),
    sku_alias character varying(256),
    usage_start date NOT NULL,
    usage_end date,
    region character varying(50),
    instance_type character varying(50),
    unit character varying(63),
    line_item_type character varying(256),
    usage_amount numeric(24,9),
    currency character varying(10) NOT NULL,
    unblended_cost numeric(24,9),
    markup_cost numeric(24,9),
    tags jsonb,
    source_uuid uuid,
    cost_entry_bill_id integer NOT NULL
)
PARTITION BY RANGE (usage_start);


ALTER TABLE template0.reporting_gcpcostentrylineitem_daily_summary OWNER TO table_owner;

--
-- Name: reporting_gcp_compute_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_compute_summary AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.instance_type, reporting_gcpcostentrylineitem_daily_summary.source_uuid) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_gcpcostentrylineitem_daily_summary.instance_type,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    reporting_gcpcostentrylineitem_daily_summary.source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE ((reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_gcpcostentrylineitem_daily_summary.instance_type IS NOT NULL))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.instance_type, reporting_gcpcostentrylineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_compute_summary OWNER TO table_owner;

--
-- Name: reporting_gcp_compute_summary_by_account; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_compute_summary_by_account AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.instance_type, reporting_gcpcostentrylineitem_daily_summary.account_id) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_gcpcostentrylineitem_daily_summary.instance_type,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE ((reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_gcpcostentrylineitem_daily_summary.instance_type IS NOT NULL))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.instance_type, reporting_gcpcostentrylineitem_daily_summary.account_id
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_compute_summary_by_account OWNER TO table_owner;

--
-- Name: reporting_gcp_compute_summary_by_project; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_compute_summary_by_project AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.instance_type, reporting_gcpcostentrylineitem_daily_summary.project_id, reporting_gcpcostentrylineitem_daily_summary.project_name, reporting_gcpcostentrylineitem_daily_summary.account_id) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_gcpcostentrylineitem_daily_summary.instance_type,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    reporting_gcpcostentrylineitem_daily_summary.project_id,
    reporting_gcpcostentrylineitem_daily_summary.project_name,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE ((reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_gcpcostentrylineitem_daily_summary.instance_type IS NOT NULL))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.instance_type, reporting_gcpcostentrylineitem_daily_summary.project_id, reporting_gcpcostentrylineitem_daily_summary.project_name, reporting_gcpcostentrylineitem_daily_summary.account_id
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_compute_summary_by_project OWNER TO table_owner;

--
-- Name: reporting_gcp_compute_summary_by_region; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_compute_summary_by_region AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.instance_type, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.region) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_gcpcostentrylineitem_daily_summary.instance_type,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    reporting_gcpcostentrylineitem_daily_summary.region,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE ((reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_gcpcostentrylineitem_daily_summary.instance_type IS NOT NULL))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.instance_type, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.region
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_compute_summary_by_region OWNER TO table_owner;

--
-- Name: reporting_gcp_compute_summary_by_service; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_compute_summary_by_service AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.instance_type, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.service_id, reporting_gcpcostentrylineitem_daily_summary.service_alias) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_gcpcostentrylineitem_daily_summary.instance_type,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    reporting_gcpcostentrylineitem_daily_summary.service_id,
    reporting_gcpcostentrylineitem_daily_summary.service_alias,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE ((reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (reporting_gcpcostentrylineitem_daily_summary.instance_type IS NOT NULL))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.instance_type, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.service_id, reporting_gcpcostentrylineitem_daily_summary.service_alias
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_compute_summary_by_service OWNER TO table_owner;

--
-- Name: reporting_gcp_cost_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_cost_summary AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.source_uuid) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    reporting_gcpcostentrylineitem_daily_summary.source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE (reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_cost_summary OWNER TO table_owner;

--
-- Name: reporting_gcp_cost_summary_by_account; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_cost_summary_by_account AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE (reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_cost_summary_by_account OWNER TO table_owner;

--
-- Name: reporting_gcp_cost_summary_by_project; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_cost_summary_by_project AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.project_id, reporting_gcpcostentrylineitem_daily_summary.project_name, reporting_gcpcostentrylineitem_daily_summary.account_id) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid,
    reporting_gcpcostentrylineitem_daily_summary.project_id,
    reporting_gcpcostentrylineitem_daily_summary.project_name,
    reporting_gcpcostentrylineitem_daily_summary.account_id
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE (reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.project_id, reporting_gcpcostentrylineitem_daily_summary.project_name, reporting_gcpcostentrylineitem_daily_summary.account_id
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_cost_summary_by_project OWNER TO table_owner;

--
-- Name: reporting_gcp_cost_summary_by_region; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_cost_summary_by_region AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.region) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    reporting_gcpcostentrylineitem_daily_summary.region,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE (reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.region
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_cost_summary_by_region OWNER TO table_owner;

--
-- Name: reporting_gcp_cost_summary_by_service; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_cost_summary_by_service AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.service_id, reporting_gcpcostentrylineitem_daily_summary.service_alias) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    reporting_gcpcostentrylineitem_daily_summary.service_id,
    reporting_gcpcostentrylineitem_daily_summary.service_alias,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE (reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.service_id, reporting_gcpcostentrylineitem_daily_summary.service_alias
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_cost_summary_by_service OWNER TO table_owner;

--
-- Name: reporting_gcp_database_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_database_summary AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid,
    reporting_gcpcostentrylineitem_daily_summary.service_id,
    reporting_gcpcostentrylineitem_daily_summary.service_alias
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE (((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%SQL%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Spanner%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Bigtable%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Firestore%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Firebase%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Memorystore%'::text) OR (((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%MongoDB%'::text) AND (reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.service_id, reporting_gcpcostentrylineitem_daily_summary.service_alias
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_database_summary OWNER TO table_owner;

--
-- Name: reporting_gcp_network_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_network_summary AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid,
    reporting_gcpcostentrylineitem_daily_summary.service_id,
    reporting_gcpcostentrylineitem_daily_summary.service_alias
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE (((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Network%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%VPC%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Firewall%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Route%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%IP%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%DNS%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%CDN%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%NAT%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Traffic Director%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Service Discovery%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Cloud Domains%'::text) OR ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Private Service Connect%'::text) OR (((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text ~~ '%Cloud Armor%'::text) AND (reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.service_id, reporting_gcpcostentrylineitem_daily_summary.service_alias
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_network_summary OWNER TO table_owner;

--
-- Name: reporting_gcp_storage_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_storage_summary AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.source_uuid) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    reporting_gcpcostentrylineitem_daily_summary.source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE ((reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text = ANY ((ARRAY['Filestore'::character varying, 'Storage'::character varying, 'Cloud Storage'::character varying, 'Data Transfer'::character varying])::text[])))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_storage_summary OWNER TO table_owner;

--
-- Name: reporting_gcp_storage_summary_by_account; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_storage_summary_by_account AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE ((reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text = ANY ((ARRAY['Filestore'::character varying, 'Storage'::character varying, 'Cloud Storage'::character varying, 'Data Transfer'::character varying])::text[])))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_storage_summary_by_account OWNER TO table_owner;

--
-- Name: reporting_gcp_storage_summary_by_project; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_storage_summary_by_project AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.project_id, reporting_gcpcostentrylineitem_daily_summary.project_name, reporting_gcpcostentrylineitem_daily_summary.account_id) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    reporting_gcpcostentrylineitem_daily_summary.project_id,
    reporting_gcpcostentrylineitem_daily_summary.project_name,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE ((reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text = ANY ((ARRAY['Filestore'::character varying, 'Storage'::character varying, 'Cloud Storage'::character varying, 'Data Transfer'::character varying])::text[])))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.project_id, reporting_gcpcostentrylineitem_daily_summary.project_name, reporting_gcpcostentrylineitem_daily_summary.account_id
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_storage_summary_by_project OWNER TO table_owner;

--
-- Name: reporting_gcp_storage_summary_by_region; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_storage_summary_by_region AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.region) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    reporting_gcpcostentrylineitem_daily_summary.region,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE ((reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text = ANY ((ARRAY['Filestore'::character varying, 'Storage'::character varying, 'Cloud Storage'::character varying, 'Data Transfer'::character varying])::text[])))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.region
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_storage_summary_by_region OWNER TO table_owner;

--
-- Name: reporting_gcp_storage_summary_by_service; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_gcp_storage_summary_by_service AS
 SELECT row_number() OVER (ORDER BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.service_id, reporting_gcpcostentrylineitem_daily_summary.service_alias) AS id,
    reporting_gcpcostentrylineitem_daily_summary.usage_start,
    reporting_gcpcostentrylineitem_daily_summary.usage_start AS usage_end,
    sum(reporting_gcpcostentrylineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_gcpcostentrylineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_gcpcostentrylineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_gcpcostentrylineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_gcpcostentrylineitem_daily_summary.currency)::text) AS currency,
    reporting_gcpcostentrylineitem_daily_summary.account_id,
    reporting_gcpcostentrylineitem_daily_summary.service_id,
    reporting_gcpcostentrylineitem_daily_summary.service_alias,
    (max((reporting_gcpcostentrylineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_gcpcostentrylineitem_daily_summary
  WHERE ((reporting_gcpcostentrylineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND ((reporting_gcpcostentrylineitem_daily_summary.service_alias)::text = ANY ((ARRAY['Filestore'::character varying, 'Storage'::character varying, 'Cloud Storage'::character varying, 'Data Transfer'::character varying])::text[])))
  GROUP BY reporting_gcpcostentrylineitem_daily_summary.usage_start, reporting_gcpcostentrylineitem_daily_summary.account_id, reporting_gcpcostentrylineitem_daily_summary.service_id, reporting_gcpcostentrylineitem_daily_summary.service_alias
  WITH NO DATA;


ALTER TABLE template0.reporting_gcp_storage_summary_by_service OWNER TO table_owner;

--
-- Name: reporting_gcpcostentrybill; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_gcpcostentrybill (
    id integer NOT NULL,
    billing_period_start timestamp with time zone NOT NULL,
    billing_period_end timestamp with time zone NOT NULL,
    summary_data_creation_datetime timestamp with time zone,
    summary_data_updated_datetime timestamp with time zone,
    finalized_datetime timestamp with time zone,
    derived_cost_datetime timestamp with time zone,
    provider_id uuid NOT NULL
);


ALTER TABLE template0.reporting_gcpcostentrybill OWNER TO table_owner;

--
-- Name: reporting_gcpcostentrybill_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_gcpcostentrybill_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_gcpcostentrybill_id_seq OWNER TO table_owner;

--
-- Name: reporting_gcpcostentrybill_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_gcpcostentrybill_id_seq OWNED BY template0.reporting_gcpcostentrybill.id;


--
-- Name: reporting_gcpcostentrylineitem; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_gcpcostentrylineitem (
    id bigint NOT NULL,
    usage_start timestamp with time zone NOT NULL,
    usage_end timestamp with time zone NOT NULL,
    tags jsonb,
    usage_type character varying(50),
    location character varying(256),
    country character varying(256),
    region character varying(256),
    zone character varying(256),
    export_time character varying(256),
    cost numeric(24,9),
    currency character varying(256),
    conversion_rate character varying(256),
    usage_to_pricing_units numeric(24,9),
    usage_pricing_unit character varying(256),
    credits character varying(256),
    invoice_month character varying(256),
    cost_type character varying(256),
    line_item_type character varying(256),
    cost_entry_bill_id integer NOT NULL,
    cost_entry_product_id bigint,
    project_id integer NOT NULL
);


ALTER TABLE template0.reporting_gcpcostentrylineitem OWNER TO table_owner;

--
-- Name: reporting_gcpcostentrylineitem_daily; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_gcpcostentrylineitem_daily (
    id bigint NOT NULL,
    line_item_type character varying(256),
    usage_start date NOT NULL,
    usage_end date,
    tags jsonb,
    usage_type character varying(50),
    region character varying(256),
    cost numeric(24,9),
    currency character varying(256),
    conversion_rate character varying(256),
    usage_in_pricing_units numeric(24,9),
    usage_pricing_unit character varying(256),
    invoice_month character varying(256),
    tax_type character varying(256),
    cost_entry_bill_id integer NOT NULL,
    cost_entry_product_id bigint,
    project_id integer NOT NULL
);


ALTER TABLE template0.reporting_gcpcostentrylineitem_daily OWNER TO table_owner;

--
-- Name: reporting_gcpcostentrylineitem_daily_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_gcpcostentrylineitem_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_gcpcostentrylineitem_daily_id_seq OWNER TO table_owner;

--
-- Name: reporting_gcpcostentrylineitem_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_gcpcostentrylineitem_daily_id_seq OWNED BY template0.reporting_gcpcostentrylineitem_daily.id;


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_default; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_gcpcostentrylineitem_daily_summary_default (
    uuid uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    account_id character varying(20) NOT NULL,
    project_id character varying(256) NOT NULL,
    project_name character varying(256) NOT NULL,
    service_id character varying(256),
    service_alias character varying(256),
    sku_id character varying(256),
    sku_alias character varying(256),
    usage_start date NOT NULL,
    usage_end date,
    region character varying(50),
    instance_type character varying(50),
    unit character varying(63),
    line_item_type character varying(256),
    usage_amount numeric(24,9),
    currency character varying(10) NOT NULL,
    unblended_cost numeric(24,9),
    markup_cost numeric(24,9),
    tags jsonb,
    source_uuid uuid,
    cost_entry_bill_id integer NOT NULL
);
ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem_daily_summary ATTACH PARTITION template0.reporting_gcpcostentrylineitem_daily_summary_default DEFAULT;


ALTER TABLE template0.reporting_gcpcostentrylineitem_daily_summary_default OWNER TO table_owner;

--
-- Name: reporting_gcpcostentrylineitem_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_gcpcostentrylineitem_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_gcpcostentrylineitem_id_seq OWNER TO table_owner;

--
-- Name: reporting_gcpcostentrylineitem_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_gcpcostentrylineitem_id_seq OWNED BY template0.reporting_gcpcostentrylineitem.id;


--
-- Name: reporting_gcpcostentryproductservice; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_gcpcostentryproductservice (
    id bigint NOT NULL,
    service_id character varying(256),
    service_alias character varying(256),
    sku_id character varying(256),
    sku_alias character varying(256)
);


ALTER TABLE template0.reporting_gcpcostentryproductservice OWNER TO table_owner;

--
-- Name: reporting_gcpcostentryproductservice_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_gcpcostentryproductservice_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_gcpcostentryproductservice_id_seq OWNER TO table_owner;

--
-- Name: reporting_gcpcostentryproductservice_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_gcpcostentryproductservice_id_seq OWNED BY template0.reporting_gcpcostentryproductservice.id;


--
-- Name: reporting_gcpenabledtagkeys; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_gcpenabledtagkeys (
    id bigint NOT NULL,
    key character varying(253) NOT NULL
);


ALTER TABLE template0.reporting_gcpenabledtagkeys OWNER TO table_owner;

--
-- Name: reporting_gcpenabledtagkeys_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_gcpenabledtagkeys_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_gcpenabledtagkeys_id_seq OWNER TO table_owner;

--
-- Name: reporting_gcpenabledtagkeys_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_gcpenabledtagkeys_id_seq OWNED BY template0.reporting_gcpenabledtagkeys.id;


--
-- Name: reporting_gcpproject; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_gcpproject (
    id integer NOT NULL,
    account_id character varying(20) NOT NULL,
    project_id character varying(256) NOT NULL,
    project_name character varying(256) NOT NULL,
    project_labels character varying(256)
);


ALTER TABLE template0.reporting_gcpproject OWNER TO table_owner;

--
-- Name: reporting_gcpproject_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_gcpproject_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_gcpproject_id_seq OWNER TO table_owner;

--
-- Name: reporting_gcpproject_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_gcpproject_id_seq OWNED BY template0.reporting_gcpproject.id;


--
-- Name: reporting_gcptags_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_gcptags_summary (
    uuid uuid NOT NULL,
    key text NOT NULL,
    "values" text[] NOT NULL,
    account_id text,
    cost_entry_bill_id integer NOT NULL,
    project_id text,
    project_name text
);


ALTER TABLE template0.reporting_gcptags_summary OWNER TO table_owner;

--
-- Name: reporting_gcptags_values; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_gcptags_values (
    uuid uuid NOT NULL,
    key text NOT NULL,
    value text NOT NULL,
    account_ids text[] NOT NULL,
    project_ids text[],
    project_names text[]
);


ALTER TABLE template0.reporting_gcptags_values OWNER TO table_owner;

--
-- Name: reporting_ocpusagelineitem_daily_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpusagelineitem_daily_summary (
    cluster_id character varying(50),
    cluster_alias character varying(256),
    data_source character varying(64),
    namespace character varying(253),
    node character varying(253),
    resource_id character varying(253),
    usage_start date NOT NULL,
    usage_end date NOT NULL,
    pod_labels jsonb,
    pod_usage_cpu_core_hours numeric(18,6),
    pod_request_cpu_core_hours numeric(18,6),
    pod_limit_cpu_core_hours numeric(18,6),
    pod_usage_memory_gigabyte_hours numeric(18,6),
    pod_request_memory_gigabyte_hours numeric(18,6),
    pod_limit_memory_gigabyte_hours numeric(18,6),
    node_capacity_cpu_cores numeric(18,6),
    node_capacity_cpu_core_hours numeric(18,6),
    node_capacity_memory_gigabytes numeric(18,6),
    node_capacity_memory_gigabyte_hours numeric(18,6),
    cluster_capacity_cpu_core_hours numeric(18,6),
    cluster_capacity_memory_gigabyte_hours numeric(18,6),
    persistentvolumeclaim character varying(253),
    persistentvolume character varying(253),
    storageclass character varying(50),
    volume_labels jsonb,
    persistentvolumeclaim_capacity_gigabyte numeric(18,6),
    persistentvolumeclaim_capacity_gigabyte_months numeric(18,6),
    volume_request_storage_gigabyte_months numeric(18,6),
    persistentvolumeclaim_usage_gigabyte_months numeric(18,6),
    infrastructure_raw_cost numeric(33,15),
    infrastructure_project_raw_cost numeric(33,15),
    infrastructure_usage_cost jsonb,
    infrastructure_markup_cost numeric(33,15),
    infrastructure_project_markup_cost numeric(33,15),
    infrastructure_monthly_cost numeric(33,15),
    supplementary_usage_cost jsonb,
    supplementary_monthly_cost numeric(33,15),
    monthly_cost_type text,
    source_uuid uuid,
    report_period_id integer,
    uuid uuid NOT NULL
)
PARTITION BY RANGE (usage_start);


ALTER TABLE template0.reporting_ocpusagelineitem_daily_summary OWNER TO table_owner;

--
-- Name: reporting_ocp_cost_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocp_cost_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias) AS id,
    reporting_ocpusagelineitem_daily_summary.usage_start,
    reporting_ocpusagelineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpusagelineitem_daily_summary.cluster_id,
    reporting_ocpusagelineitem_daily_summary.cluster_alias,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'storage'::text))::numeric)) AS supplementary_usage_cost,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'storage'::text))::numeric)) AS infrastructure_usage_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_raw_cost) AS infrastructure_raw_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_markup_cost) AS infrastructure_markup_cost,
    sum(reporting_ocpusagelineitem_daily_summary.supplementary_monthly_cost) AS supplementary_monthly_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_monthly_cost) AS infrastructure_monthly_cost,
    reporting_ocpusagelineitem_daily_summary.source_uuid
   FROM template0.reporting_ocpusagelineitem_daily_summary
  WHERE (reporting_ocpusagelineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias, reporting_ocpusagelineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_ocp_cost_summary OWNER TO table_owner;

--
-- Name: reporting_ocp_cost_summary_by_node; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocp_cost_summary_by_node AS
 SELECT row_number() OVER (ORDER BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias, reporting_ocpusagelineitem_daily_summary.node) AS id,
    reporting_ocpusagelineitem_daily_summary.usage_start,
    reporting_ocpusagelineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpusagelineitem_daily_summary.cluster_id,
    reporting_ocpusagelineitem_daily_summary.cluster_alias,
    reporting_ocpusagelineitem_daily_summary.node,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'storage'::text))::numeric)) AS supplementary_usage_cost,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'storage'::text))::numeric)) AS infrastructure_usage_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_raw_cost) AS infrastructure_raw_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_markup_cost) AS infrastructure_markup_cost,
    sum(reporting_ocpusagelineitem_daily_summary.supplementary_monthly_cost) AS supplementary_monthly_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_monthly_cost) AS infrastructure_monthly_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_project_markup_cost) AS infrastructure_project_markup_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_project_raw_cost) AS infrastructure_project_raw_cost,
    reporting_ocpusagelineitem_daily_summary.source_uuid
   FROM template0.reporting_ocpusagelineitem_daily_summary
  WHERE (reporting_ocpusagelineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias, reporting_ocpusagelineitem_daily_summary.node, reporting_ocpusagelineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_ocp_cost_summary_by_node OWNER TO table_owner;

--
-- Name: reporting_ocp_cost_summary_by_project; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocp_cost_summary_by_project AS
 SELECT row_number() OVER (ORDER BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias, reporting_ocpusagelineitem_daily_summary.namespace) AS id,
    reporting_ocpusagelineitem_daily_summary.usage_start,
    reporting_ocpusagelineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpusagelineitem_daily_summary.cluster_id,
    reporting_ocpusagelineitem_daily_summary.cluster_alias,
    reporting_ocpusagelineitem_daily_summary.namespace,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'storage'::text))::numeric)) AS supplementary_usage_cost,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'storage'::text))::numeric)) AS infrastructure_usage_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_project_raw_cost) AS infrastructure_project_raw_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_project_markup_cost) AS infrastructure_project_markup_cost,
    sum(reporting_ocpusagelineitem_daily_summary.supplementary_monthly_cost) AS supplementary_monthly_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_monthly_cost) AS infrastructure_monthly_cost,
    reporting_ocpusagelineitem_daily_summary.source_uuid
   FROM template0.reporting_ocpusagelineitem_daily_summary
  WHERE (reporting_ocpusagelineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias, reporting_ocpusagelineitem_daily_summary.namespace, reporting_ocpusagelineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_ocp_cost_summary_by_project OWNER TO table_owner;

--
-- Name: reporting_ocp_pod_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocp_pod_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias) AS id,
    reporting_ocpusagelineitem_daily_summary.usage_start,
    reporting_ocpusagelineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpusagelineitem_daily_summary.cluster_id,
    reporting_ocpusagelineitem_daily_summary.cluster_alias,
    max((reporting_ocpusagelineitem_daily_summary.data_source)::text) AS data_source,
    array_agg(DISTINCT reporting_ocpusagelineitem_daily_summary.resource_id) AS resource_ids,
    count(DISTINCT reporting_ocpusagelineitem_daily_summary.resource_id) AS resource_count,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'storage'::text))::numeric)) AS supplementary_usage_cost,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'storage'::text))::numeric)) AS infrastructure_usage_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_raw_cost) AS infrastructure_raw_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_markup_cost) AS infrastructure_markup_cost,
    sum(reporting_ocpusagelineitem_daily_summary.pod_usage_cpu_core_hours) AS pod_usage_cpu_core_hours,
    sum(reporting_ocpusagelineitem_daily_summary.pod_request_cpu_core_hours) AS pod_request_cpu_core_hours,
    sum(reporting_ocpusagelineitem_daily_summary.pod_limit_cpu_core_hours) AS pod_limit_cpu_core_hours,
    max(reporting_ocpusagelineitem_daily_summary.cluster_capacity_cpu_core_hours) AS cluster_capacity_cpu_core_hours,
    sum(reporting_ocpusagelineitem_daily_summary.pod_usage_memory_gigabyte_hours) AS pod_usage_memory_gigabyte_hours,
    sum(reporting_ocpusagelineitem_daily_summary.pod_request_memory_gigabyte_hours) AS pod_request_memory_gigabyte_hours,
    sum(reporting_ocpusagelineitem_daily_summary.pod_limit_memory_gigabyte_hours) AS pod_limit_memory_gigabyte_hours,
    max(reporting_ocpusagelineitem_daily_summary.cluster_capacity_memory_gigabyte_hours) AS cluster_capacity_memory_gigabyte_hours,
    reporting_ocpusagelineitem_daily_summary.source_uuid
   FROM template0.reporting_ocpusagelineitem_daily_summary
  WHERE ((reporting_ocpusagelineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND ((reporting_ocpusagelineitem_daily_summary.data_source)::text = 'Pod'::text))
  GROUP BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias, reporting_ocpusagelineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_ocp_pod_summary OWNER TO table_owner;

--
-- Name: reporting_ocp_pod_summary_by_project; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocp_pod_summary_by_project AS
 SELECT row_number() OVER (ORDER BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias, reporting_ocpusagelineitem_daily_summary.namespace) AS id,
    reporting_ocpusagelineitem_daily_summary.usage_start,
    reporting_ocpusagelineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpusagelineitem_daily_summary.cluster_id,
    reporting_ocpusagelineitem_daily_summary.cluster_alias,
    reporting_ocpusagelineitem_daily_summary.namespace,
    max((reporting_ocpusagelineitem_daily_summary.data_source)::text) AS data_source,
    array_agg(DISTINCT reporting_ocpusagelineitem_daily_summary.resource_id) AS resource_ids,
    count(DISTINCT reporting_ocpusagelineitem_daily_summary.resource_id) AS resource_count,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'storage'::text))::numeric)) AS supplementary_usage_cost,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'storage'::text))::numeric)) AS infrastructure_usage_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_raw_cost) AS infrastructure_raw_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_markup_cost) AS infrastructure_markup_cost,
    sum(reporting_ocpusagelineitem_daily_summary.pod_usage_cpu_core_hours) AS pod_usage_cpu_core_hours,
    sum(reporting_ocpusagelineitem_daily_summary.pod_request_cpu_core_hours) AS pod_request_cpu_core_hours,
    sum(reporting_ocpusagelineitem_daily_summary.pod_limit_cpu_core_hours) AS pod_limit_cpu_core_hours,
    max(reporting_ocpusagelineitem_daily_summary.cluster_capacity_cpu_core_hours) AS cluster_capacity_cpu_core_hours,
    sum(reporting_ocpusagelineitem_daily_summary.pod_usage_memory_gigabyte_hours) AS pod_usage_memory_gigabyte_hours,
    sum(reporting_ocpusagelineitem_daily_summary.pod_request_memory_gigabyte_hours) AS pod_request_memory_gigabyte_hours,
    sum(reporting_ocpusagelineitem_daily_summary.pod_limit_memory_gigabyte_hours) AS pod_limit_memory_gigabyte_hours,
    max(reporting_ocpusagelineitem_daily_summary.cluster_capacity_memory_gigabyte_hours) AS cluster_capacity_memory_gigabyte_hours,
    reporting_ocpusagelineitem_daily_summary.source_uuid
   FROM template0.reporting_ocpusagelineitem_daily_summary
  WHERE ((reporting_ocpusagelineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND ((reporting_ocpusagelineitem_daily_summary.data_source)::text = 'Pod'::text))
  GROUP BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias, reporting_ocpusagelineitem_daily_summary.namespace, reporting_ocpusagelineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_ocp_pod_summary_by_project OWNER TO table_owner;

--
-- Name: reporting_ocp_volume_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocp_volume_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias) AS id,
    reporting_ocpusagelineitem_daily_summary.usage_start,
    reporting_ocpusagelineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpusagelineitem_daily_summary.cluster_id,
    reporting_ocpusagelineitem_daily_summary.cluster_alias,
    max((reporting_ocpusagelineitem_daily_summary.data_source)::text) AS data_source,
    array_agg(DISTINCT reporting_ocpusagelineitem_daily_summary.resource_id) AS resource_ids,
    count(DISTINCT reporting_ocpusagelineitem_daily_summary.resource_id) AS resource_count,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'storage'::text))::numeric)) AS supplementary_usage_cost,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'storage'::text))::numeric)) AS infrastructure_usage_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_raw_cost) AS infrastructure_raw_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_markup_cost) AS infrastructure_markup_cost,
    sum(reporting_ocpusagelineitem_daily_summary.persistentvolumeclaim_usage_gigabyte_months) AS persistentvolumeclaim_usage_gigabyte_months,
    sum(reporting_ocpusagelineitem_daily_summary.volume_request_storage_gigabyte_months) AS volume_request_storage_gigabyte_months,
    sum(reporting_ocpusagelineitem_daily_summary.persistentvolumeclaim_capacity_gigabyte_months) AS persistentvolumeclaim_capacity_gigabyte_months,
    reporting_ocpusagelineitem_daily_summary.source_uuid
   FROM template0.reporting_ocpusagelineitem_daily_summary
  WHERE ((reporting_ocpusagelineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND ((reporting_ocpusagelineitem_daily_summary.data_source)::text = 'Storage'::text))
  GROUP BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias, reporting_ocpusagelineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_ocp_volume_summary OWNER TO table_owner;

--
-- Name: reporting_ocp_volume_summary_by_project; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocp_volume_summary_by_project AS
 SELECT row_number() OVER (ORDER BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias, reporting_ocpusagelineitem_daily_summary.namespace) AS id,
    reporting_ocpusagelineitem_daily_summary.usage_start,
    reporting_ocpusagelineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpusagelineitem_daily_summary.cluster_id,
    reporting_ocpusagelineitem_daily_summary.cluster_alias,
    reporting_ocpusagelineitem_daily_summary.namespace,
    max((reporting_ocpusagelineitem_daily_summary.data_source)::text) AS data_source,
    array_agg(DISTINCT reporting_ocpusagelineitem_daily_summary.resource_id) AS resource_ids,
    count(DISTINCT reporting_ocpusagelineitem_daily_summary.resource_id) AS resource_count,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.supplementary_usage_cost ->> 'storage'::text))::numeric)) AS supplementary_usage_cost,
    json_build_object('cpu', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'cpu'::text))::numeric), 'memory', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'memory'::text))::numeric), 'storage', sum(((reporting_ocpusagelineitem_daily_summary.infrastructure_usage_cost ->> 'storage'::text))::numeric)) AS infrastructure_usage_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_raw_cost) AS infrastructure_raw_cost,
    sum(reporting_ocpusagelineitem_daily_summary.infrastructure_markup_cost) AS infrastructure_markup_cost,
    sum(reporting_ocpusagelineitem_daily_summary.persistentvolumeclaim_usage_gigabyte_months) AS persistentvolumeclaim_usage_gigabyte_months,
    sum(reporting_ocpusagelineitem_daily_summary.volume_request_storage_gigabyte_months) AS volume_request_storage_gigabyte_months,
    sum(reporting_ocpusagelineitem_daily_summary.persistentvolumeclaim_capacity_gigabyte_months) AS persistentvolumeclaim_capacity_gigabyte_months,
    reporting_ocpusagelineitem_daily_summary.source_uuid
   FROM template0.reporting_ocpusagelineitem_daily_summary
  WHERE ((reporting_ocpusagelineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND ((reporting_ocpusagelineitem_daily_summary.data_source)::text = 'Storage'::text))
  GROUP BY reporting_ocpusagelineitem_daily_summary.usage_start, reporting_ocpusagelineitem_daily_summary.cluster_id, reporting_ocpusagelineitem_daily_summary.cluster_alias, reporting_ocpusagelineitem_daily_summary.namespace, reporting_ocpusagelineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_ocp_volume_summary_by_project OWNER TO table_owner;

--
-- Name: reporting_ocpawscostlineitem_daily_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpawscostlineitem_daily_summary (
    cluster_id character varying(50),
    cluster_alias character varying(256),
    namespace character varying(253)[] NOT NULL,
    node character varying(253),
    resource_id character varying(253),
    usage_start date NOT NULL,
    usage_end date NOT NULL,
    product_code character varying(50) NOT NULL,
    product_family character varying(150),
    instance_type character varying(50),
    usage_account_id character varying(50) NOT NULL,
    availability_zone character varying(50),
    region character varying(50),
    unit character varying(63),
    tags jsonb,
    usage_amount numeric(24,9),
    normalized_usage_amount double precision,
    currency_code character varying(10),
    unblended_cost numeric(30,15),
    markup_cost numeric(30,15),
    shared_projects integer NOT NULL,
    project_costs jsonb,
    source_uuid uuid,
    account_alias_id integer,
    cost_entry_bill_id integer,
    report_period_id integer,
    uuid uuid NOT NULL
);


ALTER TABLE template0.reporting_ocpawscostlineitem_daily_summary OWNER TO table_owner;

--
-- Name: reporting_ocpazurecostlineitem_daily_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpazurecostlineitem_daily_summary (
    cluster_id character varying(50),
    cluster_alias character varying(256),
    namespace character varying(253)[] NOT NULL,
    node character varying(253),
    resource_id character varying(253),
    usage_start date NOT NULL,
    usage_end date NOT NULL,
    subscription_guid text NOT NULL,
    instance_type text,
    service_name text,
    resource_location text,
    tags jsonb,
    usage_quantity numeric(24,9),
    pretax_cost numeric(17,9),
    markup_cost numeric(17,9),
    currency text,
    unit_of_measure text,
    shared_projects integer NOT NULL,
    project_costs jsonb,
    source_uuid uuid,
    cost_entry_bill_id integer NOT NULL,
    report_period_id integer,
    uuid uuid NOT NULL
);


ALTER TABLE template0.reporting_ocpazurecostlineitem_daily_summary OWNER TO table_owner;

--
-- Name: reporting_ocpallcostlineitem_daily_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpallcostlineitem_daily_summary AS
 SELECT row_number() OVER () AS id,
    lids.source_type,
    lids.cluster_id,
    max((lids.cluster_alias)::text) AS cluster_alias,
    lids.namespace,
    lids.node,
    lids.resource_id,
    lids.usage_start,
    lids.usage_start AS usage_end,
    lids.usage_account_id,
    max(lids.account_alias_id) AS account_alias_id,
    lids.product_code,
    lids.product_family,
    lids.instance_type,
    lids.region,
    lids.availability_zone,
    lids.tags,
    sum(lids.usage_amount) AS usage_amount,
    max((lids.unit)::text) AS unit,
    sum(lids.unblended_cost) AS unblended_cost,
    sum(lids.markup_cost) AS markup_cost,
    max((lids.currency_code)::text) AS currency_code,
    max(lids.shared_projects) AS shared_projects,
    lids.project_costs,
    (max((lids.source_uuid)::text))::uuid AS source_uuid
   FROM ( SELECT 'AWS'::text AS source_type,
            reporting_ocpawscostlineitem_daily_summary.cluster_id,
            reporting_ocpawscostlineitem_daily_summary.cluster_alias,
            reporting_ocpawscostlineitem_daily_summary.namespace,
            (reporting_ocpawscostlineitem_daily_summary.node)::text AS node,
            reporting_ocpawscostlineitem_daily_summary.resource_id,
            reporting_ocpawscostlineitem_daily_summary.usage_start,
            reporting_ocpawscostlineitem_daily_summary.usage_end,
            reporting_ocpawscostlineitem_daily_summary.usage_account_id,
            reporting_ocpawscostlineitem_daily_summary.account_alias_id,
            reporting_ocpawscostlineitem_daily_summary.product_code,
            reporting_ocpawscostlineitem_daily_summary.product_family,
            reporting_ocpawscostlineitem_daily_summary.instance_type,
            reporting_ocpawscostlineitem_daily_summary.region,
            reporting_ocpawscostlineitem_daily_summary.availability_zone,
            reporting_ocpawscostlineitem_daily_summary.tags,
            reporting_ocpawscostlineitem_daily_summary.usage_amount,
            reporting_ocpawscostlineitem_daily_summary.unit,
            reporting_ocpawscostlineitem_daily_summary.unblended_cost,
            reporting_ocpawscostlineitem_daily_summary.markup_cost,
            reporting_ocpawscostlineitem_daily_summary.currency_code,
            reporting_ocpawscostlineitem_daily_summary.shared_projects,
            reporting_ocpawscostlineitem_daily_summary.project_costs,
            reporting_ocpawscostlineitem_daily_summary.source_uuid
           FROM template0.reporting_ocpawscostlineitem_daily_summary
          WHERE (reporting_ocpawscostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date)
        UNION
         SELECT 'Azure'::text AS source_type,
            reporting_ocpazurecostlineitem_daily_summary.cluster_id,
            reporting_ocpazurecostlineitem_daily_summary.cluster_alias,
            reporting_ocpazurecostlineitem_daily_summary.namespace,
            (reporting_ocpazurecostlineitem_daily_summary.node)::text AS node,
            reporting_ocpazurecostlineitem_daily_summary.resource_id,
            reporting_ocpazurecostlineitem_daily_summary.usage_start,
            reporting_ocpazurecostlineitem_daily_summary.usage_end,
            reporting_ocpazurecostlineitem_daily_summary.subscription_guid AS usage_account_id,
            NULL::integer AS account_alias_id,
            reporting_ocpazurecostlineitem_daily_summary.service_name AS product_code,
            NULL::character varying AS product_family,
            reporting_ocpazurecostlineitem_daily_summary.instance_type,
            reporting_ocpazurecostlineitem_daily_summary.resource_location AS region,
            NULL::character varying AS availability_zone,
            reporting_ocpazurecostlineitem_daily_summary.tags,
            reporting_ocpazurecostlineitem_daily_summary.usage_quantity AS usage_amount,
            reporting_ocpazurecostlineitem_daily_summary.unit_of_measure AS unit,
            reporting_ocpazurecostlineitem_daily_summary.pretax_cost AS unblended_cost,
            reporting_ocpazurecostlineitem_daily_summary.markup_cost,
            reporting_ocpazurecostlineitem_daily_summary.currency AS currency_code,
            reporting_ocpazurecostlineitem_daily_summary.shared_projects,
            reporting_ocpazurecostlineitem_daily_summary.project_costs,
            reporting_ocpazurecostlineitem_daily_summary.source_uuid
           FROM template0.reporting_ocpazurecostlineitem_daily_summary
          WHERE (reporting_ocpazurecostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date)) lids
  GROUP BY lids.source_type, lids.usage_start, lids.cluster_id, lids.namespace, lids.node, lids.usage_account_id, lids.resource_id, lids.product_code, lids.product_family, lids.instance_type, lids.region, lids.availability_zone, lids.tags, lids.project_costs
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpallcostlineitem_daily_summary OWNER TO table_owner;

--
-- Name: reporting_ocpall_compute_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpall_compute_summary AS
 SELECT row_number() OVER (ORDER BY lids.usage_start, lids.cluster_id, lids.usage_account_id, lids.product_code) AS id,
    lids.usage_start,
    lids.usage_start AS usage_end,
    lids.cluster_id,
    max(lids.cluster_alias) AS cluster_alias,
    lids.usage_account_id,
    max(lids.account_alias_id) AS account_alias_id,
    lids.product_code,
    lids.instance_type,
    lids.resource_id,
    sum(lids.usage_amount) AS usage_amount,
    max(lids.unit) AS unit,
    sum(lids.unblended_cost) AS unblended_cost,
    sum(lids.markup_cost) AS markup_cost,
    max(lids.currency_code) AS currency_code,
    (max((lids.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpallcostlineitem_daily_summary lids
  WHERE ((lids.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (lids.instance_type IS NOT NULL))
  GROUP BY lids.usage_start, lids.cluster_id, lids.usage_account_id, lids.product_code, lids.instance_type, lids.resource_id
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpall_compute_summary OWNER TO table_owner;

--
-- Name: reporting_ocpall_cost_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpall_cost_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpallcostlineitem_daily_summary.usage_start, reporting_ocpallcostlineitem_daily_summary.cluster_id, reporting_ocpallcostlineitem_daily_summary.source_uuid) AS id,
    reporting_ocpallcostlineitem_daily_summary.usage_start,
    reporting_ocpallcostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpallcostlineitem_daily_summary.cluster_id,
    max(reporting_ocpallcostlineitem_daily_summary.cluster_alias) AS cluster_alias,
    sum(reporting_ocpallcostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpallcostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpallcostlineitem_daily_summary.currency_code) AS currency_code,
    reporting_ocpallcostlineitem_daily_summary.source_uuid
   FROM template0.reporting_ocpallcostlineitem_daily_summary
  WHERE (reporting_ocpallcostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_ocpallcostlineitem_daily_summary.usage_start, reporting_ocpallcostlineitem_daily_summary.cluster_id, reporting_ocpallcostlineitem_daily_summary.cluster_alias, reporting_ocpallcostlineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpall_cost_summary OWNER TO table_owner;

--
-- Name: reporting_ocpall_cost_summary_by_account; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpall_cost_summary_by_account AS
 SELECT row_number() OVER (ORDER BY reporting_ocpallcostlineitem_daily_summary.usage_start, reporting_ocpallcostlineitem_daily_summary.cluster_id, reporting_ocpallcostlineitem_daily_summary.usage_account_id) AS id,
    reporting_ocpallcostlineitem_daily_summary.usage_start,
    reporting_ocpallcostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpallcostlineitem_daily_summary.cluster_id,
    max(reporting_ocpallcostlineitem_daily_summary.cluster_alias) AS cluster_alias,
    reporting_ocpallcostlineitem_daily_summary.usage_account_id,
    max(reporting_ocpallcostlineitem_daily_summary.account_alias_id) AS account_alias_id,
    sum(reporting_ocpallcostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpallcostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpallcostlineitem_daily_summary.currency_code) AS currency_code,
    (max((reporting_ocpallcostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpallcostlineitem_daily_summary
  WHERE (reporting_ocpallcostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_ocpallcostlineitem_daily_summary.usage_start, reporting_ocpallcostlineitem_daily_summary.cluster_id, reporting_ocpallcostlineitem_daily_summary.usage_account_id
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpall_cost_summary_by_account OWNER TO table_owner;

--
-- Name: reporting_ocpall_cost_summary_by_region; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpall_cost_summary_by_region AS
 SELECT row_number() OVER (ORDER BY reporting_ocpallcostlineitem_daily_summary.usage_start, reporting_ocpallcostlineitem_daily_summary.cluster_id, reporting_ocpallcostlineitem_daily_summary.usage_account_id, reporting_ocpallcostlineitem_daily_summary.region, reporting_ocpallcostlineitem_daily_summary.availability_zone) AS id,
    reporting_ocpallcostlineitem_daily_summary.usage_start,
    reporting_ocpallcostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpallcostlineitem_daily_summary.cluster_id,
    max(reporting_ocpallcostlineitem_daily_summary.cluster_alias) AS cluster_alias,
    reporting_ocpallcostlineitem_daily_summary.usage_account_id,
    max(reporting_ocpallcostlineitem_daily_summary.account_alias_id) AS account_alias_id,
    reporting_ocpallcostlineitem_daily_summary.region,
    reporting_ocpallcostlineitem_daily_summary.availability_zone,
    sum(reporting_ocpallcostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpallcostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpallcostlineitem_daily_summary.currency_code) AS currency_code,
    (max((reporting_ocpallcostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpallcostlineitem_daily_summary
  WHERE (reporting_ocpallcostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_ocpallcostlineitem_daily_summary.usage_start, reporting_ocpallcostlineitem_daily_summary.cluster_id, reporting_ocpallcostlineitem_daily_summary.usage_account_id, reporting_ocpallcostlineitem_daily_summary.region, reporting_ocpallcostlineitem_daily_summary.availability_zone
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpall_cost_summary_by_region OWNER TO table_owner;

--
-- Name: reporting_ocpall_cost_summary_by_service; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpall_cost_summary_by_service AS
 SELECT row_number() OVER (ORDER BY reporting_ocpallcostlineitem_daily_summary.usage_start, reporting_ocpallcostlineitem_daily_summary.cluster_id, reporting_ocpallcostlineitem_daily_summary.usage_account_id, reporting_ocpallcostlineitem_daily_summary.product_code, reporting_ocpallcostlineitem_daily_summary.product_family) AS id,
    reporting_ocpallcostlineitem_daily_summary.usage_start,
    reporting_ocpallcostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpallcostlineitem_daily_summary.cluster_id,
    max(reporting_ocpallcostlineitem_daily_summary.cluster_alias) AS cluster_alias,
    reporting_ocpallcostlineitem_daily_summary.usage_account_id,
    max(reporting_ocpallcostlineitem_daily_summary.account_alias_id) AS account_alias_id,
    reporting_ocpallcostlineitem_daily_summary.product_code,
    reporting_ocpallcostlineitem_daily_summary.product_family,
    sum(reporting_ocpallcostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpallcostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpallcostlineitem_daily_summary.currency_code) AS currency_code,
    (max((reporting_ocpallcostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpallcostlineitem_daily_summary
  WHERE (reporting_ocpallcostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
  GROUP BY reporting_ocpallcostlineitem_daily_summary.usage_start, reporting_ocpallcostlineitem_daily_summary.cluster_id, reporting_ocpallcostlineitem_daily_summary.usage_account_id, reporting_ocpallcostlineitem_daily_summary.product_code, reporting_ocpallcostlineitem_daily_summary.product_family
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpall_cost_summary_by_service OWNER TO table_owner;

--
-- Name: reporting_ocpall_database_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpall_database_summary AS
 SELECT row_number() OVER (ORDER BY lids.usage_start, lids.cluster_id, lids.usage_account_id, lids.product_code) AS id,
    lids.usage_start,
    lids.usage_start AS usage_end,
    lids.cluster_id,
    max(lids.cluster_alias) AS cluster_alias,
    lids.usage_account_id,
    max(lids.account_alias_id) AS account_alias_id,
    lids.product_code,
    sum(lids.usage_amount) AS usage_amount,
    max(lids.unit) AS unit,
    sum(lids.unblended_cost) AS unblended_cost,
    sum(lids.markup_cost) AS markup_cost,
    max(lids.currency_code) AS currency_code,
    (max((lids.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpallcostlineitem_daily_summary lids
  WHERE ((lids.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (((lids.product_code)::text = ANY ((ARRAY['AmazonRDS'::character varying, 'AmazonDynamoDB'::character varying, 'AmazonElastiCache'::character varying, 'AmazonNeptune'::character varying, 'AmazonRedshift'::character varying, 'AmazonDocumentDB'::character varying, 'Cosmos DB'::character varying, 'Cache for Redis'::character varying])::text[])) OR ((lids.product_code)::text ~~ '%Database%'::text)))
  GROUP BY lids.usage_start, lids.cluster_id, lids.usage_account_id, lids.product_code
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpall_database_summary OWNER TO table_owner;

--
-- Name: reporting_ocpall_network_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpall_network_summary AS
 SELECT row_number() OVER (ORDER BY lids.usage_start, lids.cluster_id, lids.usage_account_id, lids.product_code) AS id,
    lids.cluster_id,
    max(lids.cluster_alias) AS cluster_alias,
    lids.usage_account_id,
    max(lids.account_alias_id) AS account_alias_id,
    lids.usage_start,
    lids.usage_start AS usage_end,
    lids.product_code,
    sum(lids.usage_amount) AS usage_amount,
    max(lids.unit) AS unit,
    sum(lids.unblended_cost) AS unblended_cost,
    sum(lids.markup_cost) AS markup_cost,
    max(lids.currency_code) AS currency_code,
    (max((lids.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpallcostlineitem_daily_summary lids
  WHERE ((lids.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND ((lids.product_code)::text = ANY ((ARRAY['AmazonVPC'::character varying, 'AmazonCloudFront'::character varying, 'AmazonRoute53'::character varying, 'AmazonAPIGateway'::character varying, 'Virtual Network'::character varying, 'VPN'::character varying, 'DNS'::character varying, 'Traffic Manager'::character varying, 'ExpressRoute'::character varying, 'Load Balancer'::character varying, 'Application Gateway'::character varying])::text[])))
  GROUP BY lids.usage_start, lids.cluster_id, lids.usage_account_id, lids.product_code
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpall_network_summary OWNER TO table_owner;

--
-- Name: reporting_ocpall_storage_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpall_storage_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpallcostlineitem_daily_summary.usage_start, reporting_ocpallcostlineitem_daily_summary.cluster_id, reporting_ocpallcostlineitem_daily_summary.usage_account_id, reporting_ocpallcostlineitem_daily_summary.product_family, reporting_ocpallcostlineitem_daily_summary.product_code) AS id,
    reporting_ocpallcostlineitem_daily_summary.cluster_id,
    max(reporting_ocpallcostlineitem_daily_summary.cluster_alias) AS cluster_alias,
    reporting_ocpallcostlineitem_daily_summary.usage_account_id,
    max(reporting_ocpallcostlineitem_daily_summary.account_alias_id) AS account_alias_id,
    reporting_ocpallcostlineitem_daily_summary.usage_start,
    reporting_ocpallcostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpallcostlineitem_daily_summary.product_family,
    reporting_ocpallcostlineitem_daily_summary.product_code,
    sum(reporting_ocpallcostlineitem_daily_summary.usage_amount) AS usage_amount,
    max(reporting_ocpallcostlineitem_daily_summary.unit) AS unit,
    sum(reporting_ocpallcostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpallcostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpallcostlineitem_daily_summary.currency_code) AS currency_code,
    (max((reporting_ocpallcostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpallcostlineitem_daily_summary
  WHERE ((reporting_ocpallcostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date) AND (((reporting_ocpallcostlineitem_daily_summary.product_family)::text ~~ '%Storage%'::text) OR ((reporting_ocpallcostlineitem_daily_summary.product_code)::text ~~ '%Storage%'::text)) AND (reporting_ocpallcostlineitem_daily_summary.unit = 'GB-Mo'::text))
  GROUP BY reporting_ocpallcostlineitem_daily_summary.usage_start, reporting_ocpallcostlineitem_daily_summary.cluster_id, reporting_ocpallcostlineitem_daily_summary.usage_account_id, reporting_ocpallcostlineitem_daily_summary.product_family, reporting_ocpallcostlineitem_daily_summary.product_code
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpall_storage_summary OWNER TO table_owner;

--
-- Name: reporting_ocpawscostlineitem_project_daily_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpawscostlineitem_project_daily_summary (
    cluster_id character varying(50),
    cluster_alias character varying(256),
    data_source character varying(64),
    namespace character varying(253) NOT NULL,
    node character varying(253),
    pod_labels jsonb,
    resource_id character varying(253),
    usage_start date NOT NULL,
    usage_end date NOT NULL,
    product_code character varying(50) NOT NULL,
    product_family character varying(150),
    instance_type character varying(50),
    usage_account_id character varying(50) NOT NULL,
    availability_zone character varying(50),
    region character varying(50),
    unit character varying(63),
    usage_amount numeric(30,15),
    normalized_usage_amount double precision,
    currency_code character varying(10),
    unblended_cost numeric(30,15),
    markup_cost numeric(30,15),
    project_markup_cost numeric(30,15),
    pod_cost numeric(30,15),
    source_uuid uuid,
    account_alias_id integer,
    cost_entry_bill_id integer,
    report_period_id integer,
    uuid uuid NOT NULL
);


ALTER TABLE template0.reporting_ocpawscostlineitem_project_daily_summary OWNER TO table_owner;

--
-- Name: reporting_ocpazurecostlineitem_project_daily_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpazurecostlineitem_project_daily_summary (
    cluster_id character varying(50),
    cluster_alias character varying(256),
    data_source character varying(64),
    namespace character varying(253) NOT NULL,
    node character varying(253),
    pod_labels jsonb,
    resource_id character varying(253),
    usage_start date NOT NULL,
    usage_end date NOT NULL,
    subscription_guid text NOT NULL,
    instance_type text,
    service_name text,
    resource_location text,
    usage_quantity numeric(24,9),
    unit_of_measure text,
    currency text,
    pretax_cost numeric(17,9),
    markup_cost numeric(17,9),
    project_markup_cost numeric(17,9),
    pod_cost numeric(24,6),
    source_uuid uuid,
    cost_entry_bill_id integer NOT NULL,
    report_period_id integer,
    uuid uuid NOT NULL
);


ALTER TABLE template0.reporting_ocpazurecostlineitem_project_daily_summary OWNER TO table_owner;

--
-- Name: reporting_ocpallcostlineitem_project_daily_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpallcostlineitem_project_daily_summary AS
 SELECT row_number() OVER () AS id,
    lids.source_type,
    lids.cluster_id,
    lids.cluster_alias,
    lids.data_source,
    lids.namespace,
    lids.node,
    lids.pod_labels,
    lids.resource_id,
    lids.usage_start,
    lids.usage_end,
    lids.usage_account_id,
    lids.account_alias_id,
    lids.product_code,
    lids.product_family,
    lids.instance_type,
    lids.region,
    lids.availability_zone,
    lids.usage_amount,
    lids.unit,
    lids.unblended_cost,
    lids.project_markup_cost,
    lids.pod_cost,
    lids.currency_code,
    lids.source_uuid
   FROM ( SELECT 'AWS'::text AS source_type,
            reporting_ocpawscostlineitem_project_daily_summary.cluster_id,
            max((reporting_ocpawscostlineitem_project_daily_summary.cluster_alias)::text) AS cluster_alias,
            reporting_ocpawscostlineitem_project_daily_summary.data_source,
            (reporting_ocpawscostlineitem_project_daily_summary.namespace)::text AS namespace,
            (reporting_ocpawscostlineitem_project_daily_summary.node)::text AS node,
            reporting_ocpawscostlineitem_project_daily_summary.pod_labels,
            reporting_ocpawscostlineitem_project_daily_summary.resource_id,
            reporting_ocpawscostlineitem_project_daily_summary.usage_start,
            reporting_ocpawscostlineitem_project_daily_summary.usage_end,
            reporting_ocpawscostlineitem_project_daily_summary.usage_account_id,
            max(reporting_ocpawscostlineitem_project_daily_summary.account_alias_id) AS account_alias_id,
            reporting_ocpawscostlineitem_project_daily_summary.product_code,
            reporting_ocpawscostlineitem_project_daily_summary.product_family,
            reporting_ocpawscostlineitem_project_daily_summary.instance_type,
            reporting_ocpawscostlineitem_project_daily_summary.region,
            reporting_ocpawscostlineitem_project_daily_summary.availability_zone,
            sum(reporting_ocpawscostlineitem_project_daily_summary.usage_amount) AS usage_amount,
            max((reporting_ocpawscostlineitem_project_daily_summary.unit)::text) AS unit,
            sum(reporting_ocpawscostlineitem_project_daily_summary.unblended_cost) AS unblended_cost,
            sum(reporting_ocpawscostlineitem_project_daily_summary.project_markup_cost) AS project_markup_cost,
            sum(reporting_ocpawscostlineitem_project_daily_summary.pod_cost) AS pod_cost,
            max((reporting_ocpawscostlineitem_project_daily_summary.currency_code)::text) AS currency_code,
            (max((reporting_ocpawscostlineitem_project_daily_summary.source_uuid)::text))::uuid AS source_uuid
           FROM template0.reporting_ocpawscostlineitem_project_daily_summary
          WHERE (reporting_ocpawscostlineitem_project_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
          GROUP BY 'AWS'::text, reporting_ocpawscostlineitem_project_daily_summary.usage_start, reporting_ocpawscostlineitem_project_daily_summary.usage_end, reporting_ocpawscostlineitem_project_daily_summary.cluster_id, reporting_ocpawscostlineitem_project_daily_summary.data_source, reporting_ocpawscostlineitem_project_daily_summary.namespace, reporting_ocpawscostlineitem_project_daily_summary.node, reporting_ocpawscostlineitem_project_daily_summary.usage_account_id, reporting_ocpawscostlineitem_project_daily_summary.resource_id, reporting_ocpawscostlineitem_project_daily_summary.product_code, reporting_ocpawscostlineitem_project_daily_summary.product_family, reporting_ocpawscostlineitem_project_daily_summary.instance_type, reporting_ocpawscostlineitem_project_daily_summary.region, reporting_ocpawscostlineitem_project_daily_summary.availability_zone, reporting_ocpawscostlineitem_project_daily_summary.pod_labels
        UNION
         SELECT 'Azure'::text AS source_type,
            reporting_ocpazurecostlineitem_project_daily_summary.cluster_id,
            max((reporting_ocpazurecostlineitem_project_daily_summary.cluster_alias)::text) AS cluster_alias,
            reporting_ocpazurecostlineitem_project_daily_summary.data_source,
            (reporting_ocpazurecostlineitem_project_daily_summary.namespace)::text AS namespace,
            (reporting_ocpazurecostlineitem_project_daily_summary.node)::text AS node,
            reporting_ocpazurecostlineitem_project_daily_summary.pod_labels,
            reporting_ocpazurecostlineitem_project_daily_summary.resource_id,
            reporting_ocpazurecostlineitem_project_daily_summary.usage_start,
            reporting_ocpazurecostlineitem_project_daily_summary.usage_end,
            reporting_ocpazurecostlineitem_project_daily_summary.subscription_guid AS usage_account_id,
            NULL::integer AS account_alias_id,
            reporting_ocpazurecostlineitem_project_daily_summary.service_name AS product_code,
            NULL::text AS product_family,
            reporting_ocpazurecostlineitem_project_daily_summary.instance_type,
            reporting_ocpazurecostlineitem_project_daily_summary.resource_location AS region,
            NULL::text AS availability_zone,
            sum(reporting_ocpazurecostlineitem_project_daily_summary.usage_quantity) AS usage_amount,
            max(reporting_ocpazurecostlineitem_project_daily_summary.unit_of_measure) AS unit,
            sum(reporting_ocpazurecostlineitem_project_daily_summary.pretax_cost) AS unblended_cost,
            sum(reporting_ocpazurecostlineitem_project_daily_summary.project_markup_cost) AS project_markup_cost,
            sum(reporting_ocpazurecostlineitem_project_daily_summary.pod_cost) AS pod_cost,
            max(reporting_ocpazurecostlineitem_project_daily_summary.currency) AS currency_code,
            (max((reporting_ocpazurecostlineitem_project_daily_summary.source_uuid)::text))::uuid AS source_uuid
           FROM template0.reporting_ocpazurecostlineitem_project_daily_summary
          WHERE (reporting_ocpazurecostlineitem_project_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '2 mons'::interval)))::date)
          GROUP BY 'Azure'::text, reporting_ocpazurecostlineitem_project_daily_summary.usage_start, reporting_ocpazurecostlineitem_project_daily_summary.usage_end, reporting_ocpazurecostlineitem_project_daily_summary.cluster_id, reporting_ocpazurecostlineitem_project_daily_summary.data_source, reporting_ocpazurecostlineitem_project_daily_summary.namespace, reporting_ocpazurecostlineitem_project_daily_summary.node, reporting_ocpazurecostlineitem_project_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_project_daily_summary.resource_id, reporting_ocpazurecostlineitem_project_daily_summary.service_name, NULL::text, reporting_ocpazurecostlineitem_project_daily_summary.instance_type, reporting_ocpazurecostlineitem_project_daily_summary.resource_location, NULL::text, reporting_ocpazurecostlineitem_project_daily_summary.pod_labels) lids
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpallcostlineitem_project_daily_summary OWNER TO table_owner;

--
-- Name: reporting_ocpaws_compute_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpaws_compute_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.instance_type, reporting_ocpawscostlineitem_daily_summary.resource_id) AS id,
    reporting_ocpawscostlineitem_daily_summary.usage_start,
    reporting_ocpawscostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpawscostlineitem_daily_summary.cluster_id,
    max((reporting_ocpawscostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpawscostlineitem_daily_summary.usage_account_id,
    max(reporting_ocpawscostlineitem_daily_summary.account_alias_id) AS account_alias_id,
    reporting_ocpawscostlineitem_daily_summary.instance_type,
    reporting_ocpawscostlineitem_daily_summary.resource_id,
    sum(reporting_ocpawscostlineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_ocpawscostlineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_ocpawscostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpawscostlineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_ocpawscostlineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_ocpawscostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpawscostlineitem_daily_summary
  WHERE ((reporting_ocpawscostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date) AND (reporting_ocpawscostlineitem_daily_summary.instance_type IS NOT NULL))
  GROUP BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.instance_type, reporting_ocpawscostlineitem_daily_summary.resource_id
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpaws_compute_summary OWNER TO table_owner;

--
-- Name: reporting_ocpaws_cost_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpaws_cost_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id) AS id,
    reporting_ocpawscostlineitem_daily_summary.usage_start,
    reporting_ocpawscostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpawscostlineitem_daily_summary.cluster_id,
    max((reporting_ocpawscostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    sum(reporting_ocpawscostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpawscostlineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_ocpawscostlineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_ocpawscostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpawscostlineitem_daily_summary
  WHERE (reporting_ocpawscostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date)
  GROUP BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpaws_cost_summary OWNER TO table_owner;

--
-- Name: reporting_ocpaws_cost_summary_by_account; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpaws_cost_summary_by_account AS
 SELECT row_number() OVER (ORDER BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id) AS id,
    reporting_ocpawscostlineitem_daily_summary.usage_start,
    reporting_ocpawscostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpawscostlineitem_daily_summary.cluster_id,
    max((reporting_ocpawscostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpawscostlineitem_daily_summary.usage_account_id,
    max(reporting_ocpawscostlineitem_daily_summary.account_alias_id) AS account_alias_id,
    sum(reporting_ocpawscostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpawscostlineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_ocpawscostlineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_ocpawscostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpawscostlineitem_daily_summary
  WHERE (reporting_ocpawscostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date)
  GROUP BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpaws_cost_summary_by_account OWNER TO table_owner;

--
-- Name: reporting_ocpaws_cost_summary_by_region; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpaws_cost_summary_by_region AS
 SELECT row_number() OVER (ORDER BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.region, reporting_ocpawscostlineitem_daily_summary.availability_zone) AS id,
    reporting_ocpawscostlineitem_daily_summary.usage_start,
    reporting_ocpawscostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpawscostlineitem_daily_summary.cluster_id,
    max((reporting_ocpawscostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpawscostlineitem_daily_summary.usage_account_id,
    max(reporting_ocpawscostlineitem_daily_summary.account_alias_id) AS account_alias_id,
    reporting_ocpawscostlineitem_daily_summary.region,
    reporting_ocpawscostlineitem_daily_summary.availability_zone,
    sum(reporting_ocpawscostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpawscostlineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_ocpawscostlineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_ocpawscostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpawscostlineitem_daily_summary
  WHERE (reporting_ocpawscostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date)
  GROUP BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.region, reporting_ocpawscostlineitem_daily_summary.availability_zone
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpaws_cost_summary_by_region OWNER TO table_owner;

--
-- Name: reporting_ocpaws_cost_summary_by_service; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpaws_cost_summary_by_service AS
 SELECT row_number() OVER (ORDER BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.product_code, reporting_ocpawscostlineitem_daily_summary.product_family) AS id,
    reporting_ocpawscostlineitem_daily_summary.usage_start,
    reporting_ocpawscostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpawscostlineitem_daily_summary.cluster_id,
    max((reporting_ocpawscostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpawscostlineitem_daily_summary.usage_account_id,
    max(reporting_ocpawscostlineitem_daily_summary.account_alias_id) AS account_alias_id,
    reporting_ocpawscostlineitem_daily_summary.product_code,
    reporting_ocpawscostlineitem_daily_summary.product_family,
    sum(reporting_ocpawscostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpawscostlineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_ocpawscostlineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_ocpawscostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpawscostlineitem_daily_summary
  WHERE (reporting_ocpawscostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date)
  GROUP BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.product_code, reporting_ocpawscostlineitem_daily_summary.product_family
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpaws_cost_summary_by_service OWNER TO table_owner;

--
-- Name: reporting_ocpaws_database_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpaws_database_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.product_code) AS id,
    reporting_ocpawscostlineitem_daily_summary.usage_start,
    reporting_ocpawscostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpawscostlineitem_daily_summary.cluster_id,
    max((reporting_ocpawscostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpawscostlineitem_daily_summary.usage_account_id,
    max(reporting_ocpawscostlineitem_daily_summary.account_alias_id) AS account_alias_id,
    reporting_ocpawscostlineitem_daily_summary.product_code,
    sum(reporting_ocpawscostlineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_ocpawscostlineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_ocpawscostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpawscostlineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_ocpawscostlineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_ocpawscostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpawscostlineitem_daily_summary
  WHERE (((reporting_ocpawscostlineitem_daily_summary.product_code)::text = ANY ((ARRAY['AmazonRDS'::character varying, 'AmazonDynamoDB'::character varying, 'AmazonElastiCache'::character varying, 'AmazonNeptune'::character varying, 'AmazonRedshift'::character varying, 'AmazonDocumentDB'::character varying])::text[])) AND (reporting_ocpawscostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date))
  GROUP BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.product_code
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpaws_database_summary OWNER TO table_owner;

--
-- Name: reporting_ocpaws_network_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpaws_network_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.product_code) AS id,
    reporting_ocpawscostlineitem_daily_summary.usage_start,
    reporting_ocpawscostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpawscostlineitem_daily_summary.cluster_id,
    max((reporting_ocpawscostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpawscostlineitem_daily_summary.usage_account_id,
    max(reporting_ocpawscostlineitem_daily_summary.account_alias_id) AS account_alias_id,
    reporting_ocpawscostlineitem_daily_summary.product_code,
    sum(reporting_ocpawscostlineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_ocpawscostlineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_ocpawscostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpawscostlineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_ocpawscostlineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_ocpawscostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpawscostlineitem_daily_summary
  WHERE (((reporting_ocpawscostlineitem_daily_summary.product_code)::text = ANY ((ARRAY['AmazonVPC'::character varying, 'AmazonCloudFront'::character varying, 'AmazonRoute53'::character varying, 'AmazonAPIGateway'::character varying])::text[])) AND (reporting_ocpawscostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date))
  GROUP BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.product_code
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpaws_network_summary OWNER TO table_owner;

--
-- Name: reporting_ocpaws_storage_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpaws_storage_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.product_family) AS id,
    reporting_ocpawscostlineitem_daily_summary.usage_start,
    reporting_ocpawscostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpawscostlineitem_daily_summary.cluster_id,
    max((reporting_ocpawscostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpawscostlineitem_daily_summary.usage_account_id,
    max(reporting_ocpawscostlineitem_daily_summary.account_alias_id) AS account_alias_id,
    reporting_ocpawscostlineitem_daily_summary.product_family,
    sum(reporting_ocpawscostlineitem_daily_summary.usage_amount) AS usage_amount,
    max((reporting_ocpawscostlineitem_daily_summary.unit)::text) AS unit,
    sum(reporting_ocpawscostlineitem_daily_summary.unblended_cost) AS unblended_cost,
    sum(reporting_ocpawscostlineitem_daily_summary.markup_cost) AS markup_cost,
    max((reporting_ocpawscostlineitem_daily_summary.currency_code)::text) AS currency_code,
    (max((reporting_ocpawscostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpawscostlineitem_daily_summary
  WHERE (((reporting_ocpawscostlineitem_daily_summary.product_family)::text ~~ '%Storage%'::text) AND ((reporting_ocpawscostlineitem_daily_summary.unit)::text = 'GB-Mo'::text) AND (reporting_ocpawscostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date))
  GROUP BY reporting_ocpawscostlineitem_daily_summary.usage_start, reporting_ocpawscostlineitem_daily_summary.cluster_id, reporting_ocpawscostlineitem_daily_summary.usage_account_id, reporting_ocpawscostlineitem_daily_summary.product_family
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpaws_storage_summary OWNER TO table_owner;

--
-- Name: reporting_ocpawstags_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpawstags_summary (
    uuid uuid NOT NULL,
    key character varying(253) NOT NULL,
    "values" text[] NOT NULL,
    usage_account_id character varying(50),
    namespace text NOT NULL,
    node text,
    account_alias_id integer,
    cost_entry_bill_id integer NOT NULL,
    report_period_id integer NOT NULL
);


ALTER TABLE template0.reporting_ocpawstags_summary OWNER TO table_owner;

--
-- Name: reporting_ocpawstags_values; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpawstags_values (
    uuid uuid NOT NULL,
    key text NOT NULL,
    value text NOT NULL,
    usage_account_ids text[] NOT NULL,
    account_aliases text[] NOT NULL,
    cluster_ids text[] NOT NULL,
    cluster_aliases text[] NOT NULL,
    namespaces text[] NOT NULL,
    nodes text[]
);


ALTER TABLE template0.reporting_ocpawstags_values OWNER TO table_owner;

--
-- Name: reporting_ocpazure_compute_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpazure_compute_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.instance_type, reporting_ocpazurecostlineitem_daily_summary.resource_id) AS id,
    reporting_ocpazurecostlineitem_daily_summary.usage_start,
    reporting_ocpazurecostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpazurecostlineitem_daily_summary.cluster_id,
    max((reporting_ocpazurecostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpazurecostlineitem_daily_summary.subscription_guid,
    reporting_ocpazurecostlineitem_daily_summary.instance_type,
    reporting_ocpazurecostlineitem_daily_summary.resource_id,
    sum(reporting_ocpazurecostlineitem_daily_summary.usage_quantity) AS usage_quantity,
    max(reporting_ocpazurecostlineitem_daily_summary.unit_of_measure) AS unit_of_measure,
    sum(reporting_ocpazurecostlineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_ocpazurecostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpazurecostlineitem_daily_summary.currency) AS currency,
    (max((reporting_ocpazurecostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpazurecostlineitem_daily_summary
  WHERE ((reporting_ocpazurecostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date) AND (reporting_ocpazurecostlineitem_daily_summary.instance_type IS NOT NULL) AND (reporting_ocpazurecostlineitem_daily_summary.unit_of_measure = 'Hrs'::text))
  GROUP BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.instance_type, reporting_ocpazurecostlineitem_daily_summary.resource_id
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpazure_compute_summary OWNER TO table_owner;

--
-- Name: reporting_ocpazure_cost_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpazure_cost_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.source_uuid) AS id,
    reporting_ocpazurecostlineitem_daily_summary.usage_start,
    reporting_ocpazurecostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpazurecostlineitem_daily_summary.cluster_id,
    max((reporting_ocpazurecostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    sum(reporting_ocpazurecostlineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_ocpazurecostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpazurecostlineitem_daily_summary.currency) AS currency,
    reporting_ocpazurecostlineitem_daily_summary.source_uuid
   FROM template0.reporting_ocpazurecostlineitem_daily_summary
  WHERE (reporting_ocpazurecostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date)
  GROUP BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.source_uuid
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpazure_cost_summary OWNER TO table_owner;

--
-- Name: reporting_ocpazure_cost_summary_by_account; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpazure_cost_summary_by_account AS
 SELECT row_number() OVER (ORDER BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid) AS id,
    reporting_ocpazurecostlineitem_daily_summary.usage_start,
    reporting_ocpazurecostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpazurecostlineitem_daily_summary.cluster_id,
    max((reporting_ocpazurecostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpazurecostlineitem_daily_summary.subscription_guid,
    sum(reporting_ocpazurecostlineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_ocpazurecostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpazurecostlineitem_daily_summary.currency) AS currency,
    (max((reporting_ocpazurecostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpazurecostlineitem_daily_summary
  WHERE (reporting_ocpazurecostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date)
  GROUP BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpazure_cost_summary_by_account OWNER TO table_owner;

--
-- Name: reporting_ocpazure_cost_summary_by_location; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpazure_cost_summary_by_location AS
 SELECT row_number() OVER (ORDER BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.resource_location) AS id,
    reporting_ocpazurecostlineitem_daily_summary.usage_start,
    reporting_ocpazurecostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpazurecostlineitem_daily_summary.cluster_id,
    max((reporting_ocpazurecostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpazurecostlineitem_daily_summary.subscription_guid,
    reporting_ocpazurecostlineitem_daily_summary.resource_location,
    sum(reporting_ocpazurecostlineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_ocpazurecostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpazurecostlineitem_daily_summary.currency) AS currency,
    (max((reporting_ocpazurecostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpazurecostlineitem_daily_summary
  WHERE (reporting_ocpazurecostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date)
  GROUP BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.resource_location
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpazure_cost_summary_by_location OWNER TO table_owner;

--
-- Name: reporting_ocpazure_cost_summary_by_service; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpazure_cost_summary_by_service AS
 SELECT row_number() OVER (ORDER BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.service_name) AS id,
    reporting_ocpazurecostlineitem_daily_summary.usage_start,
    reporting_ocpazurecostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpazurecostlineitem_daily_summary.cluster_id,
    max((reporting_ocpazurecostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpazurecostlineitem_daily_summary.subscription_guid,
    reporting_ocpazurecostlineitem_daily_summary.service_name,
    sum(reporting_ocpazurecostlineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_ocpazurecostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpazurecostlineitem_daily_summary.currency) AS currency,
    (max((reporting_ocpazurecostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpazurecostlineitem_daily_summary
  WHERE (reporting_ocpazurecostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date)
  GROUP BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.service_name
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpazure_cost_summary_by_service OWNER TO table_owner;

--
-- Name: reporting_ocpazure_database_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpazure_database_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.service_name) AS id,
    reporting_ocpazurecostlineitem_daily_summary.usage_start,
    reporting_ocpazurecostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpazurecostlineitem_daily_summary.cluster_id,
    max((reporting_ocpazurecostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpazurecostlineitem_daily_summary.subscription_guid,
    reporting_ocpazurecostlineitem_daily_summary.service_name,
    sum(reporting_ocpazurecostlineitem_daily_summary.usage_quantity) AS usage_quantity,
    max(reporting_ocpazurecostlineitem_daily_summary.unit_of_measure) AS unit_of_measure,
    sum(reporting_ocpazurecostlineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_ocpazurecostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpazurecostlineitem_daily_summary.currency) AS currency,
    (max((reporting_ocpazurecostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpazurecostlineitem_daily_summary
  WHERE ((reporting_ocpazurecostlineitem_daily_summary.service_name = ANY (ARRAY['Cosmos DB'::text, 'Cache for Redis'::text])) OR ((reporting_ocpazurecostlineitem_daily_summary.service_name ~~* '%database%'::text) AND (reporting_ocpazurecostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date)))
  GROUP BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.service_name
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpazure_database_summary OWNER TO table_owner;

--
-- Name: reporting_ocpazure_network_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpazure_network_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.service_name) AS id,
    reporting_ocpazurecostlineitem_daily_summary.usage_start,
    reporting_ocpazurecostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpazurecostlineitem_daily_summary.cluster_id,
    max((reporting_ocpazurecostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpazurecostlineitem_daily_summary.subscription_guid,
    reporting_ocpazurecostlineitem_daily_summary.service_name,
    sum(reporting_ocpazurecostlineitem_daily_summary.usage_quantity) AS usage_quantity,
    max(reporting_ocpazurecostlineitem_daily_summary.unit_of_measure) AS unit_of_measure,
    sum(reporting_ocpazurecostlineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_ocpazurecostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpazurecostlineitem_daily_summary.currency) AS currency,
    (max((reporting_ocpazurecostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpazurecostlineitem_daily_summary
  WHERE ((reporting_ocpazurecostlineitem_daily_summary.service_name = ANY (ARRAY['Virtual Network'::text, 'VPN'::text, 'DNS'::text, 'Traffic Manager'::text, 'ExpressRoute'::text, 'Load Balancer'::text, 'Application Gateway'::text])) AND (reporting_ocpazurecostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date))
  GROUP BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.service_name
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpazure_network_summary OWNER TO table_owner;

--
-- Name: reporting_ocpazure_storage_summary; Type: MATERIALIZED VIEW; Schema: template0; Owner: table_owner
--

CREATE MATERIALIZED VIEW template0.reporting_ocpazure_storage_summary AS
 SELECT row_number() OVER (ORDER BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.service_name) AS id,
    reporting_ocpazurecostlineitem_daily_summary.usage_start,
    reporting_ocpazurecostlineitem_daily_summary.usage_start AS usage_end,
    reporting_ocpazurecostlineitem_daily_summary.cluster_id,
    max((reporting_ocpazurecostlineitem_daily_summary.cluster_alias)::text) AS cluster_alias,
    reporting_ocpazurecostlineitem_daily_summary.subscription_guid,
    reporting_ocpazurecostlineitem_daily_summary.service_name,
    sum(reporting_ocpazurecostlineitem_daily_summary.usage_quantity) AS usage_quantity,
    max(reporting_ocpazurecostlineitem_daily_summary.unit_of_measure) AS unit_of_measure,
    sum(reporting_ocpazurecostlineitem_daily_summary.pretax_cost) AS pretax_cost,
    sum(reporting_ocpazurecostlineitem_daily_summary.markup_cost) AS markup_cost,
    max(reporting_ocpazurecostlineitem_daily_summary.currency) AS currency,
    (max((reporting_ocpazurecostlineitem_daily_summary.source_uuid)::text))::uuid AS source_uuid
   FROM template0.reporting_ocpazurecostlineitem_daily_summary
  WHERE ((reporting_ocpazurecostlineitem_daily_summary.service_name ~~ '%Storage%'::text) AND (reporting_ocpazurecostlineitem_daily_summary.unit_of_measure = 'GB-Mo'::text) AND (reporting_ocpazurecostlineitem_daily_summary.usage_start >= (date_trunc('month'::text, (now() - '1 mon'::interval)))::date))
  GROUP BY reporting_ocpazurecostlineitem_daily_summary.usage_start, reporting_ocpazurecostlineitem_daily_summary.cluster_id, reporting_ocpazurecostlineitem_daily_summary.subscription_guid, reporting_ocpazurecostlineitem_daily_summary.service_name
  WITH NO DATA;


ALTER TABLE template0.reporting_ocpazure_storage_summary OWNER TO table_owner;

--
-- Name: reporting_ocpazuretags_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpazuretags_summary (
    uuid uuid NOT NULL,
    key character varying(253) NOT NULL,
    "values" text[] NOT NULL,
    subscription_guid text,
    namespace text NOT NULL,
    node text,
    cost_entry_bill_id integer NOT NULL,
    report_period_id integer NOT NULL
);


ALTER TABLE template0.reporting_ocpazuretags_summary OWNER TO table_owner;

--
-- Name: reporting_ocpazuretags_values; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpazuretags_values (
    uuid uuid NOT NULL,
    key text NOT NULL,
    value text NOT NULL,
    subscription_guids text[] NOT NULL,
    cluster_ids text[] NOT NULL,
    cluster_aliases text[] NOT NULL,
    namespaces text[] NOT NULL,
    nodes text[]
);


ALTER TABLE template0.reporting_ocpazuretags_values OWNER TO table_owner;

--
-- Name: reporting_ocpcosts_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpcosts_summary (
    id integer NOT NULL,
    cluster_id character varying(50),
    cluster_alias character varying(256),
    namespace character varying(253),
    pod character varying(253),
    node character varying(253),
    usage_start date NOT NULL,
    usage_end date NOT NULL,
    pod_charge_cpu_core_hours numeric(27,9),
    pod_charge_memory_gigabyte_hours numeric(27,9),
    persistentvolumeclaim_charge_gb_month numeric(27,9),
    infra_cost numeric(33,15),
    project_infra_cost numeric(33,15),
    markup_cost numeric(27,9),
    project_markup_cost numeric(27,9),
    pod_labels jsonb,
    monthly_cost numeric(33,15),
    report_period_id integer
);


ALTER TABLE template0.reporting_ocpcosts_summary OWNER TO table_owner;

--
-- Name: reporting_ocpcosts_summary_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_ocpcosts_summary_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_ocpcosts_summary_id_seq OWNER TO table_owner;

--
-- Name: reporting_ocpcosts_summary_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_ocpcosts_summary_id_seq OWNED BY template0.reporting_ocpcosts_summary.id;


--
-- Name: reporting_ocpenabledtagkeys; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpenabledtagkeys (
    id bigint NOT NULL,
    key character varying(253) NOT NULL
);


ALTER TABLE template0.reporting_ocpenabledtagkeys OWNER TO table_owner;

--
-- Name: reporting_ocpenabledtagkeys_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_ocpenabledtagkeys_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_ocpenabledtagkeys_id_seq OWNER TO table_owner;

--
-- Name: reporting_ocpenabledtagkeys_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_ocpenabledtagkeys_id_seq OWNED BY template0.reporting_ocpenabledtagkeys.id;


--
-- Name: reporting_ocpnamespacelabellineitem; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpnamespacelabellineitem (
    id bigint NOT NULL,
    namespace character varying(253),
    namespace_labels jsonb,
    report_id integer NOT NULL,
    report_period_id integer NOT NULL
);


ALTER TABLE template0.reporting_ocpnamespacelabellineitem OWNER TO table_owner;

--
-- Name: reporting_ocpnamespacelabellineitem_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_ocpnamespacelabellineitem_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_ocpnamespacelabellineitem_id_seq OWNER TO table_owner;

--
-- Name: reporting_ocpnamespacelabellineitem_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_ocpnamespacelabellineitem_id_seq OWNED BY template0.reporting_ocpnamespacelabellineitem.id;


--
-- Name: reporting_ocpnodelabellineitem; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpnodelabellineitem (
    id bigint NOT NULL,
    node character varying(253),
    node_labels jsonb,
    report_id integer NOT NULL,
    report_period_id integer NOT NULL
);


ALTER TABLE template0.reporting_ocpnodelabellineitem OWNER TO table_owner;

--
-- Name: reporting_ocpnodelabellineitem_daily; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpnodelabellineitem_daily (
    id bigint NOT NULL,
    cluster_id character varying(50),
    cluster_alias character varying(256),
    node character varying(253),
    usage_start date NOT NULL,
    usage_end date NOT NULL,
    node_labels jsonb,
    total_seconds integer NOT NULL,
    report_period_id integer
);


ALTER TABLE template0.reporting_ocpnodelabellineitem_daily OWNER TO table_owner;

--
-- Name: reporting_ocpnodelabellineitem_daily_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_ocpnodelabellineitem_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_ocpnodelabellineitem_daily_id_seq OWNER TO table_owner;

--
-- Name: reporting_ocpnodelabellineitem_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_ocpnodelabellineitem_daily_id_seq OWNED BY template0.reporting_ocpnodelabellineitem_daily.id;


--
-- Name: reporting_ocpnodelabellineitem_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_ocpnodelabellineitem_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_ocpnodelabellineitem_id_seq OWNER TO table_owner;

--
-- Name: reporting_ocpnodelabellineitem_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_ocpnodelabellineitem_id_seq OWNED BY template0.reporting_ocpnodelabellineitem.id;


--
-- Name: reporting_ocpstoragelineitem; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpstoragelineitem (
    id bigint NOT NULL,
    namespace character varying(253) NOT NULL,
    pod character varying(253),
    persistentvolumeclaim character varying(253) NOT NULL,
    persistentvolume character varying(253) NOT NULL,
    storageclass character varying(50),
    persistentvolumeclaim_capacity_bytes numeric(73,9),
    persistentvolumeclaim_capacity_byte_seconds numeric(73,9),
    volume_request_storage_byte_seconds numeric(73,9),
    persistentvolumeclaim_usage_byte_seconds numeric(73,9),
    persistentvolume_labels jsonb,
    persistentvolumeclaim_labels jsonb,
    report_id integer NOT NULL,
    report_period_id integer NOT NULL
);


ALTER TABLE template0.reporting_ocpstoragelineitem OWNER TO table_owner;

--
-- Name: reporting_ocpstoragelineitem_daily; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpstoragelineitem_daily (
    id bigint NOT NULL,
    cluster_id character varying(50),
    cluster_alias character varying(256),
    namespace character varying(253) NOT NULL,
    pod character varying(253),
    node character varying(253),
    persistentvolumeclaim character varying(253) NOT NULL,
    persistentvolume character varying(253) NOT NULL,
    storageclass character varying(50),
    usage_start date NOT NULL,
    usage_end date NOT NULL,
    persistentvolumeclaim_capacity_bytes numeric(73,9),
    persistentvolumeclaim_capacity_byte_seconds numeric(73,9),
    volume_request_storage_byte_seconds numeric(73,9),
    persistentvolumeclaim_usage_byte_seconds numeric(73,9),
    total_seconds integer NOT NULL,
    persistentvolume_labels jsonb,
    persistentvolumeclaim_labels jsonb,
    report_period_id integer
);


ALTER TABLE template0.reporting_ocpstoragelineitem_daily OWNER TO table_owner;

--
-- Name: reporting_ocpstoragelineitem_daily_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_ocpstoragelineitem_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_ocpstoragelineitem_daily_id_seq OWNER TO table_owner;

--
-- Name: reporting_ocpstoragelineitem_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_ocpstoragelineitem_daily_id_seq OWNED BY template0.reporting_ocpstoragelineitem_daily.id;


--
-- Name: reporting_ocpstoragelineitem_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_ocpstoragelineitem_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_ocpstoragelineitem_id_seq OWNER TO table_owner;

--
-- Name: reporting_ocpstoragelineitem_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_ocpstoragelineitem_id_seq OWNED BY template0.reporting_ocpstoragelineitem.id;


--
-- Name: reporting_ocpstoragevolumelabel_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpstoragevolumelabel_summary (
    uuid uuid NOT NULL,
    key text NOT NULL,
    "values" text[] NOT NULL,
    namespace text NOT NULL,
    node text,
    report_period_id integer NOT NULL
);


ALTER TABLE template0.reporting_ocpstoragevolumelabel_summary OWNER TO table_owner;

--
-- Name: reporting_ocptags_values; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocptags_values (
    uuid uuid NOT NULL,
    key text NOT NULL,
    value text NOT NULL,
    cluster_ids text[] NOT NULL,
    cluster_aliases text[] NOT NULL,
    namespaces text[] NOT NULL,
    nodes text[]
);


ALTER TABLE template0.reporting_ocptags_values OWNER TO table_owner;

--
-- Name: reporting_ocpusagelineitem; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpusagelineitem (
    id bigint NOT NULL,
    namespace character varying(253) NOT NULL,
    pod character varying(253) NOT NULL,
    node character varying(253) NOT NULL,
    resource_id character varying(253),
    pod_usage_cpu_core_seconds numeric(73,9),
    pod_request_cpu_core_seconds numeric(73,9),
    pod_limit_cpu_core_seconds numeric(73,9),
    pod_usage_memory_byte_seconds numeric(73,9),
    pod_request_memory_byte_seconds numeric(73,9),
    pod_limit_memory_byte_seconds numeric(73,9),
    node_capacity_cpu_cores numeric(73,9),
    node_capacity_cpu_core_seconds numeric(73,9),
    node_capacity_memory_bytes numeric(73,9),
    node_capacity_memory_byte_seconds numeric(73,9),
    pod_labels jsonb,
    report_id integer NOT NULL,
    report_period_id integer NOT NULL
);


ALTER TABLE template0.reporting_ocpusagelineitem OWNER TO table_owner;

--
-- Name: reporting_ocpusagelineitem_daily; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpusagelineitem_daily (
    id bigint NOT NULL,
    cluster_id character varying(50),
    cluster_alias character varying(256),
    namespace character varying(253) NOT NULL,
    pod character varying(253) NOT NULL,
    node character varying(253) NOT NULL,
    resource_id character varying(253),
    usage_start date NOT NULL,
    usage_end date NOT NULL,
    pod_usage_cpu_core_seconds numeric(73,9),
    pod_request_cpu_core_seconds numeric(73,9),
    pod_limit_cpu_core_seconds numeric(73,9),
    pod_usage_memory_byte_seconds numeric(73,9),
    pod_request_memory_byte_seconds numeric(73,9),
    pod_limit_memory_byte_seconds numeric(73,9),
    node_capacity_cpu_cores numeric(73,9),
    node_capacity_cpu_core_seconds numeric(73,9),
    node_capacity_memory_bytes numeric(73,9),
    node_capacity_memory_byte_seconds numeric(73,9),
    cluster_capacity_cpu_core_seconds numeric(73,9),
    cluster_capacity_memory_byte_seconds numeric(73,9),
    total_seconds integer NOT NULL,
    pod_labels jsonb,
    report_period_id integer
);


ALTER TABLE template0.reporting_ocpusagelineitem_daily OWNER TO table_owner;

--
-- Name: reporting_ocpusagelineitem_daily_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_ocpusagelineitem_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_ocpusagelineitem_daily_id_seq OWNER TO table_owner;

--
-- Name: reporting_ocpusagelineitem_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_ocpusagelineitem_daily_id_seq OWNED BY template0.reporting_ocpusagelineitem_daily.id;


--
-- Name: reporting_ocpusagelineitem_daily_summary_default; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpusagelineitem_daily_summary_default (
    cluster_id character varying(50),
    cluster_alias character varying(256),
    data_source character varying(64),
    namespace character varying(253),
    node character varying(253),
    resource_id character varying(253),
    usage_start date NOT NULL,
    usage_end date NOT NULL,
    pod_labels jsonb,
    pod_usage_cpu_core_hours numeric(18,6),
    pod_request_cpu_core_hours numeric(18,6),
    pod_limit_cpu_core_hours numeric(18,6),
    pod_usage_memory_gigabyte_hours numeric(18,6),
    pod_request_memory_gigabyte_hours numeric(18,6),
    pod_limit_memory_gigabyte_hours numeric(18,6),
    node_capacity_cpu_cores numeric(18,6),
    node_capacity_cpu_core_hours numeric(18,6),
    node_capacity_memory_gigabytes numeric(18,6),
    node_capacity_memory_gigabyte_hours numeric(18,6),
    cluster_capacity_cpu_core_hours numeric(18,6),
    cluster_capacity_memory_gigabyte_hours numeric(18,6),
    persistentvolumeclaim character varying(253),
    persistentvolume character varying(253),
    storageclass character varying(50),
    volume_labels jsonb,
    persistentvolumeclaim_capacity_gigabyte numeric(18,6),
    persistentvolumeclaim_capacity_gigabyte_months numeric(18,6),
    volume_request_storage_gigabyte_months numeric(18,6),
    persistentvolumeclaim_usage_gigabyte_months numeric(18,6),
    infrastructure_raw_cost numeric(33,15),
    infrastructure_project_raw_cost numeric(33,15),
    infrastructure_usage_cost jsonb,
    infrastructure_markup_cost numeric(33,15),
    infrastructure_project_markup_cost numeric(33,15),
    infrastructure_monthly_cost numeric(33,15),
    supplementary_usage_cost jsonb,
    supplementary_monthly_cost numeric(33,15),
    monthly_cost_type text,
    source_uuid uuid,
    report_period_id integer,
    uuid uuid NOT NULL
);
ALTER TABLE ONLY template0.reporting_ocpusagelineitem_daily_summary ATTACH PARTITION template0.reporting_ocpusagelineitem_daily_summary_default DEFAULT;


ALTER TABLE template0.reporting_ocpusagelineitem_daily_summary_default OWNER TO table_owner;

--
-- Name: reporting_ocpusagelineitem_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_ocpusagelineitem_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_ocpusagelineitem_id_seq OWNER TO table_owner;

--
-- Name: reporting_ocpusagelineitem_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_ocpusagelineitem_id_seq OWNED BY template0.reporting_ocpusagelineitem.id;


--
-- Name: reporting_ocpusagepodlabel_summary; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpusagepodlabel_summary (
    uuid uuid NOT NULL,
    key text NOT NULL,
    "values" text[] NOT NULL,
    namespace text NOT NULL,
    node text,
    report_period_id integer NOT NULL
);


ALTER TABLE template0.reporting_ocpusagepodlabel_summary OWNER TO table_owner;

--
-- Name: reporting_ocpusagereport; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpusagereport (
    id integer NOT NULL,
    interval_start timestamp with time zone NOT NULL,
    interval_end timestamp with time zone NOT NULL,
    report_period_id integer NOT NULL
);


ALTER TABLE template0.reporting_ocpusagereport OWNER TO table_owner;

--
-- Name: reporting_ocpusagereport_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_ocpusagereport_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_ocpusagereport_id_seq OWNER TO table_owner;

--
-- Name: reporting_ocpusagereport_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_ocpusagereport_id_seq OWNED BY template0.reporting_ocpusagereport.id;


--
-- Name: reporting_ocpusagereportperiod; Type: TABLE; Schema: template0; Owner: table_owner
--

CREATE TABLE template0.reporting_ocpusagereportperiod (
    id integer NOT NULL,
    cluster_id character varying(50) NOT NULL,
    cluster_alias character varying(256),
    report_period_start timestamp with time zone NOT NULL,
    report_period_end timestamp with time zone NOT NULL,
    summary_data_creation_datetime timestamp with time zone,
    summary_data_updated_datetime timestamp with time zone,
    derived_cost_datetime timestamp with time zone,
    provider_id uuid NOT NULL
);


ALTER TABLE template0.reporting_ocpusagereportperiod OWNER TO table_owner;

--
-- Name: reporting_ocpusagereportperiod_id_seq; Type: SEQUENCE; Schema: template0; Owner: table_owner
--

CREATE SEQUENCE template0.reporting_ocpusagereportperiod_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE template0.reporting_ocpusagereportperiod_id_seq OWNER TO table_owner;

--
-- Name: reporting_ocpusagereportperiod_id_seq; Type: SEQUENCE OWNED BY; Schema: template0; Owner: table_owner
--

ALTER SEQUENCE template0.reporting_ocpusagereportperiod_id_seq OWNED BY template0.reporting_ocpusagereportperiod.id;


--
-- Name: cost_model_audit id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.cost_model_audit ALTER COLUMN id SET DEFAULT nextval('template0.cost_model_audit_id_seq'::regclass);


--
-- Name: cost_model_map id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.cost_model_map ALTER COLUMN id SET DEFAULT nextval('template0.cost_model_map_id_seq'::regclass);


--
-- Name: django_migrations id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.django_migrations ALTER COLUMN id SET DEFAULT nextval('template0.django_migrations_id_seq'::regclass);


--
-- Name: partitioned_tables id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.partitioned_tables ALTER COLUMN id SET DEFAULT nextval('template0.partitioned_tables_id_seq'::regclass);


--
-- Name: reporting_awsaccountalias id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awsaccountalias ALTER COLUMN id SET DEFAULT nextval('template0.reporting_awsaccountalias_id_seq'::regclass);


--
-- Name: reporting_awscostentry id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentry ALTER COLUMN id SET DEFAULT nextval('template0.reporting_awscostentry_id_seq'::regclass);


--
-- Name: reporting_awscostentrybill id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrybill ALTER COLUMN id SET DEFAULT nextval('template0.reporting_awscostentrybill_id_seq'::regclass);


--
-- Name: reporting_awscostentrylineitem id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem ALTER COLUMN id SET DEFAULT nextval('template0.reporting_awscostentrylineitem_id_seq'::regclass);


--
-- Name: reporting_awscostentrylineitem_daily id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem_daily ALTER COLUMN id SET DEFAULT nextval('template0.reporting_awscostentrylineitem_daily_id_seq'::regclass);


--
-- Name: reporting_awscostentrypricing id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrypricing ALTER COLUMN id SET DEFAULT nextval('template0.reporting_awscostentrypricing_id_seq'::regclass);


--
-- Name: reporting_awscostentryproduct id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentryproduct ALTER COLUMN id SET DEFAULT nextval('template0.reporting_awscostentryproduct_id_seq'::regclass);


--
-- Name: reporting_awscostentryreservation id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentryreservation ALTER COLUMN id SET DEFAULT nextval('template0.reporting_awscostentryreservation_id_seq'::regclass);


--
-- Name: reporting_awsorganizationalunit id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awsorganizationalunit ALTER COLUMN id SET DEFAULT nextval('template0.reporting_awsorganizationalunit_id_seq'::regclass);


--
-- Name: reporting_azurecostentrybill id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentrybill ALTER COLUMN id SET DEFAULT nextval('template0.reporting_azurecostentrybill_id_seq'::regclass);


--
-- Name: reporting_azurecostentrylineitem_daily id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentrylineitem_daily ALTER COLUMN id SET DEFAULT nextval('template0.reporting_azurecostentrylineitem_daily_id_seq'::regclass);


--
-- Name: reporting_azurecostentryproductservice id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentryproductservice ALTER COLUMN id SET DEFAULT nextval('template0.reporting_azurecostentryproductservice_id_seq'::regclass);


--
-- Name: reporting_azureenabledtagkeys id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azureenabledtagkeys ALTER COLUMN id SET DEFAULT nextval('template0.reporting_azureenabledtagkeys_id_seq'::regclass);


--
-- Name: reporting_azuremeter id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azuremeter ALTER COLUMN id SET DEFAULT nextval('template0.reporting_azuremeter_id_seq'::regclass);


--
-- Name: reporting_gcpcostentrybill id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrybill ALTER COLUMN id SET DEFAULT nextval('template0.reporting_gcpcostentrybill_id_seq'::regclass);


--
-- Name: reporting_gcpcostentrylineitem id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem ALTER COLUMN id SET DEFAULT nextval('template0.reporting_gcpcostentrylineitem_id_seq'::regclass);


--
-- Name: reporting_gcpcostentrylineitem_daily id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem_daily ALTER COLUMN id SET DEFAULT nextval('template0.reporting_gcpcostentrylineitem_daily_id_seq'::regclass);


--
-- Name: reporting_gcpcostentryproductservice id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentryproductservice ALTER COLUMN id SET DEFAULT nextval('template0.reporting_gcpcostentryproductservice_id_seq'::regclass);


--
-- Name: reporting_gcpenabledtagkeys id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpenabledtagkeys ALTER COLUMN id SET DEFAULT nextval('template0.reporting_gcpenabledtagkeys_id_seq'::regclass);


--
-- Name: reporting_gcpproject id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpproject ALTER COLUMN id SET DEFAULT nextval('template0.reporting_gcpproject_id_seq'::regclass);


--
-- Name: reporting_ocpcosts_summary id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpcosts_summary ALTER COLUMN id SET DEFAULT nextval('template0.reporting_ocpcosts_summary_id_seq'::regclass);


--
-- Name: reporting_ocpenabledtagkeys id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpenabledtagkeys ALTER COLUMN id SET DEFAULT nextval('template0.reporting_ocpenabledtagkeys_id_seq'::regclass);


--
-- Name: reporting_ocpnamespacelabellineitem id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnamespacelabellineitem ALTER COLUMN id SET DEFAULT nextval('template0.reporting_ocpnamespacelabellineitem_id_seq'::regclass);


--
-- Name: reporting_ocpnodelabellineitem id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnodelabellineitem ALTER COLUMN id SET DEFAULT nextval('template0.reporting_ocpnodelabellineitem_id_seq'::regclass);


--
-- Name: reporting_ocpnodelabellineitem_daily id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnodelabellineitem_daily ALTER COLUMN id SET DEFAULT nextval('template0.reporting_ocpnodelabellineitem_daily_id_seq'::regclass);


--
-- Name: reporting_ocpstoragelineitem id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpstoragelineitem ALTER COLUMN id SET DEFAULT nextval('template0.reporting_ocpstoragelineitem_id_seq'::regclass);


--
-- Name: reporting_ocpstoragelineitem_daily id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpstoragelineitem_daily ALTER COLUMN id SET DEFAULT nextval('template0.reporting_ocpstoragelineitem_daily_id_seq'::regclass);


--
-- Name: reporting_ocpusagelineitem id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagelineitem ALTER COLUMN id SET DEFAULT nextval('template0.reporting_ocpusagelineitem_id_seq'::regclass);


--
-- Name: reporting_ocpusagelineitem_daily id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagelineitem_daily ALTER COLUMN id SET DEFAULT nextval('template0.reporting_ocpusagelineitem_daily_id_seq'::regclass);


--
-- Name: reporting_ocpusagereport id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagereport ALTER COLUMN id SET DEFAULT nextval('template0.reporting_ocpusagereport_id_seq'::regclass);


--
-- Name: reporting_ocpusagereportperiod id; Type: DEFAULT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagereportperiod ALTER COLUMN id SET DEFAULT nextval('template0.reporting_ocpusagereportperiod_id_seq'::regclass);


--
-- Data for Name: cost_model; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: cost_model_audit; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: cost_model_map; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: django_migrations; Type: TABLE DATA; Schema: template0; Owner: table_owner
--

INSERT INTO template0.django_migrations VALUES (1, 'api', '0001_initial_squashed_0008_auto_20190305_2015', '2021-04-23 14:29:05.580039+00');
INSERT INTO template0.django_migrations VALUES (2, 'api', '0009_providerstatus_squashed_0042_auto_20200116_2048', '2021-04-23 14:29:05.58214+00');
INSERT INTO template0.django_migrations VALUES (3, 'api', '0010_auto_20200128_2138', '2021-04-23 14:29:05.584398+00');
INSERT INTO template0.django_migrations VALUES (4, 'api', '0011_auto_20200204_1647', '2021-04-23 14:29:05.586432+00');
INSERT INTO template0.django_migrations VALUES (5, 'api', '0012_auto_20200225_2022', '2021-04-23 14:29:05.588183+00');
INSERT INTO template0.django_migrations VALUES (6, 'api', '0013_auto_20200226_1953', '2021-04-23 14:29:05.589832+00');
INSERT INTO template0.django_migrations VALUES (7, 'api', '0014_reload_azure_map', '2021-04-23 14:29:05.591623+00');
INSERT INTO template0.django_migrations VALUES (8, 'api', '0015_auto_20200311_2049', '2021-04-23 14:29:05.59352+00');
INSERT INTO template0.django_migrations VALUES (9, 'api', '0016_auto_20200324_1420', '2021-04-23 14:29:05.596081+00');
INSERT INTO template0.django_migrations VALUES (10, 'api', '0017_delete_cloudaccount', '2021-04-23 14:29:05.59872+00');
INSERT INTO template0.django_migrations VALUES (11, 'api', '0018_auto_20200326_0102', '2021-04-23 14:29:05.601325+00');
INSERT INTO template0.django_migrations VALUES (12, 'api', '0019_delete_costmodelmetricsmap', '2021-04-23 14:29:05.603855+00');
INSERT INTO template0.django_migrations VALUES (13, 'api', '0020_sources_out_of_order_delete', '2021-04-23 14:29:05.606375+00');
INSERT INTO template0.django_migrations VALUES (14, 'api', '0021_delete_providerstatus', '2021-04-23 14:29:05.609099+00');
INSERT INTO template0.django_migrations VALUES (15, 'api', '0022_auto_20200812_1945', '2021-04-23 14:29:05.611595+00');
INSERT INTO template0.django_migrations VALUES (16, 'api', '0023_auto_20200820_2314', '2021-04-23 14:29:05.614021+00');
INSERT INTO template0.django_migrations VALUES (17, 'api', '0024_auto_20200824_1759', '2021-04-23 14:29:05.616414+00');
INSERT INTO template0.django_migrations VALUES (18, 'api', '0025_db_functions', '2021-04-23 14:29:05.619031+00');
INSERT INTO template0.django_migrations VALUES (19, 'api', '0026_provider_data_updated_timestamp', '2021-04-23 14:29:05.621544+00');
INSERT INTO template0.django_migrations VALUES (20, 'api', '0027_customer_date_updated', '2021-04-23 14:29:05.623893+00');
INSERT INTO template0.django_migrations VALUES (21, 'api', '0028_public_function_update', '2021-04-23 14:29:05.626121+00');
INSERT INTO template0.django_migrations VALUES (22, 'api', '0029_auto_20200921_2016', '2021-04-23 14:29:05.628359+00');
INSERT INTO template0.django_migrations VALUES (23, 'api', '0030_auto_20201007_1403', '2021-04-23 14:29:05.636348+00');
INSERT INTO template0.django_migrations VALUES (24, 'api', '0031_clone_schema', '2021-04-23 14:29:05.641704+00');
INSERT INTO template0.django_migrations VALUES (25, 'api', '0032_presto_delete_log_trigger_func', '2021-04-23 14:29:05.646453+00');
INSERT INTO template0.django_migrations VALUES (26, 'api', '0033_sources_name_text', '2021-04-23 14:29:05.656864+00');
INSERT INTO template0.django_migrations VALUES (27, 'api', '0034_remove_sources_endpoint_id', '2021-04-23 14:29:05.66252+00');
INSERT INTO template0.django_migrations VALUES (28, 'api', '0035_reapply_partition_and_clone_func', '2021-04-23 14:29:05.667438+00');
INSERT INTO template0.django_migrations VALUES (29, 'api', '0036_reapply_check_migrations_func', '2021-04-23 14:29:05.672516+00');
INSERT INTO template0.django_migrations VALUES (30, 'api', '0037_auto_20210223_2136', '2021-04-23 14:29:05.678354+00');
INSERT INTO template0.django_migrations VALUES (31, 'api', '0038_drop_app_needs_migrations_func', '2021-04-23 14:29:05.683253+00');
INSERT INTO template0.django_migrations VALUES (32, 'api', '0039_create_hive_db', '2021-04-23 14:29:05.687973+00');
INSERT INTO template0.django_migrations VALUES (33, 'api', '0040_auto_20210318_1514', '2021-04-23 14:29:05.701593+00');
INSERT INTO template0.django_migrations VALUES (34, 'api', '0041_array_subtract_dbfunc', '2021-04-23 14:29:05.706549+00');
INSERT INTO template0.django_migrations VALUES (35, 'api', '0042_reapply_clone_func', '2021-04-23 14:29:05.711578+00');
INSERT INTO template0.django_migrations VALUES (36, 'contenttypes', '0001_initial', '2021-04-23 14:29:05.718643+00');
INSERT INTO template0.django_migrations VALUES (37, 'contenttypes', '0002_remove_content_type_name', '2021-04-23 14:29:05.765794+00');
INSERT INTO template0.django_migrations VALUES (38, 'auth', '0001_initial', '2021-04-23 14:29:05.7845+00');
INSERT INTO template0.django_migrations VALUES (39, 'auth', '0002_alter_permission_name_max_length', '2021-04-23 14:29:05.793834+00');
INSERT INTO template0.django_migrations VALUES (40, 'auth', '0003_alter_user_email_max_length', '2021-04-23 14:29:05.802435+00');
INSERT INTO template0.django_migrations VALUES (41, 'auth', '0004_alter_user_username_opts', '2021-04-23 14:29:05.811581+00');
INSERT INTO template0.django_migrations VALUES (42, 'auth', '0005_alter_user_last_login_null', '2021-04-23 14:29:05.820438+00');
INSERT INTO template0.django_migrations VALUES (43, 'auth', '0006_require_contenttypes_0002', '2021-04-23 14:29:05.824431+00');
INSERT INTO template0.django_migrations VALUES (44, 'auth', '0007_alter_validators_add_error_messages', '2021-04-23 14:29:05.834342+00');
INSERT INTO template0.django_migrations VALUES (45, 'auth', '0008_alter_user_username_max_length', '2021-04-23 14:29:05.843063+00');
INSERT INTO template0.django_migrations VALUES (46, 'auth', '0009_alter_user_last_name_max_length', '2021-04-23 14:29:05.851637+00');
INSERT INTO template0.django_migrations VALUES (47, 'auth', '0010_alter_group_name_max_length', '2021-04-23 14:29:05.860055+00');
INSERT INTO template0.django_migrations VALUES (48, 'auth', '0011_update_proxy_permissions', '2021-04-23 14:29:05.864596+00');
INSERT INTO template0.django_migrations VALUES (49, 'auth', '0012_alter_user_first_name_max_length', '2021-04-23 14:29:05.873001+00');
INSERT INTO template0.django_migrations VALUES (50, 'cost_models', '0001_initial_squashed_0018_auto_20200116_2048', '2021-04-23 14:29:05.916831+00');
INSERT INTO template0.django_migrations VALUES (51, 'cost_models', '0002_auto_20200318_1233', '2021-04-23 14:29:05.919382+00');
INSERT INTO template0.django_migrations VALUES (52, 'cost_models', '0002_auto_20210318_1514', '2021-04-23 14:29:05.931301+00');
INSERT INTO template0.django_migrations VALUES (53, 'reporting', '0001_squashed_0090_ocpallcostlineitemdailysummary_ocpallcostlineitemprojectdailysummary', '2021-04-23 14:29:17.310761+00');
INSERT INTO template0.django_migrations VALUES (54, 'reporting', '0091_aws_compute_cost_correction', '2021-04-23 14:29:17.312972+00');
INSERT INTO template0.django_migrations VALUES (55, 'reporting', '0092_auto_20200203_1758', '2021-04-23 14:29:17.315058+00');
INSERT INTO template0.django_migrations VALUES (56, 'reporting', '0093_auto_20200210_1920', '2021-04-23 14:29:17.317324+00');
INSERT INTO template0.django_migrations VALUES (57, 'reporting', '0094_auto_20200211_1449', '2021-04-23 14:29:17.320087+00');
INSERT INTO template0.django_migrations VALUES (58, 'reporting', '0095_auto_20200212_1606', '2021-04-23 14:29:17.323707+00');
INSERT INTO template0.django_migrations VALUES (59, 'reporting', '0096_auto_20200218_2227', '2021-04-23 14:29:17.326895+00');
INSERT INTO template0.django_migrations VALUES (60, 'reporting', '0097_auto_20200221_1331', '2021-04-23 14:29:17.329449+00');
INSERT INTO template0.django_migrations VALUES (61, 'reporting', '0098_auto_20200221_2034', '2021-04-23 14:29:17.331811+00');
INSERT INTO template0.django_migrations VALUES (62, 'reporting', '0099_ocp_performance', '2021-04-23 14:29:17.33428+00');
INSERT INTO template0.django_migrations VALUES (63, 'reporting', '0100_aws_azure_query_perforance', '2021-04-23 14:29:17.336631+00');
INSERT INTO template0.django_migrations VALUES (64, 'reporting', '0101_ocpenabledtagkeys', '2021-04-23 14:29:17.33888+00');
INSERT INTO template0.django_migrations VALUES (65, 'reporting', '0102_auto_20200228_1812', '2021-04-23 14:29:17.341322+00');
INSERT INTO template0.django_migrations VALUES (66, 'reporting', '0103_azurecomputesummary_azurecostsummary_azurecostsummarybyaccount_azurecostsummarybylocation_azurecosts', '2021-04-23 14:29:17.343694+00');
INSERT INTO template0.django_migrations VALUES (67, 'reporting', '0104_ocpallcomputesummary_ocpallcostsummary_ocpallcostsummarybyaccount_ocpallcostsummarybyregion_ocpallco', '2021-04-23 14:29:17.346137+00');
INSERT INTO template0.django_migrations VALUES (68, 'reporting', '0105_ocpcostsummary_ocpcostsummarybynode_ocpcostsummarybyproject_ocppodsummary_ocppodsummarybyproject_ocp', '2021-04-23 14:29:17.348615+00');
INSERT INTO template0.django_migrations VALUES (69, 'reporting', '0106_ocpawscostsummary', '2021-04-23 14:29:17.350871+00');
INSERT INTO template0.django_migrations VALUES (70, 'reporting', '0107_ocpazurecomputesummary_ocpazurecostsummary_ocpazurecostsummarybyaccount_ocpazurecostsummarybylocatio', '2021-04-23 14:29:17.353131+00');
INSERT INTO template0.django_migrations VALUES (71, 'reporting', '0108_auto_20200405_1316', '2021-04-23 14:29:17.355555+00');
INSERT INTO template0.django_migrations VALUES (72, 'reporting', '0109_remove_ocpusagelineitemdailysummary_pod', '2021-04-23 14:29:17.358067+00');
INSERT INTO template0.django_migrations VALUES (73, 'reporting', '0110_summary_indexes', '2021-04-23 14:29:17.360625+00');
INSERT INTO template0.django_migrations VALUES (74, 'reporting', '0111_drop_azure_service_not_null', '2021-04-23 14:29:17.363445+00');
INSERT INTO template0.django_migrations VALUES (75, 'reporting', '0112_auto_20200416_1733', '2021-04-23 14:29:17.365875+00');
INSERT INTO template0.django_migrations VALUES (76, 'reporting', '0113_aws_organizational_units', '2021-04-23 14:29:17.368753+00');
INSERT INTO template0.django_migrations VALUES (77, 'reporting', '0114_adding_source_uuid', '2021-04-23 14:29:17.371292+00');
INSERT INTO template0.django_migrations VALUES (78, 'reporting', '0115_populate_source_uuid', '2021-04-23 14:29:17.373787+00');
INSERT INTO template0.django_migrations VALUES (79, 'reporting', '0116_ocpall_unique_index', '2021-04-23 14:29:17.37641+00');
INSERT INTO template0.django_migrations VALUES (80, 'reporting', '0117_auto_20200617_1452', '2021-04-23 14:29:17.378868+00');
INSERT INTO template0.django_migrations VALUES (81, 'reporting', '0118_auto_20200630_1819', '2021-04-23 14:29:17.381216+00');
INSERT INTO template0.django_migrations VALUES (82, 'reporting', '0119_auto_20200707_1934', '2021-04-23 14:29:17.383518+00');
INSERT INTO template0.django_migrations VALUES (83, 'reporting', '0120_auto_20200724_1354', '2021-04-23 14:29:17.38576+00');
INSERT INTO template0.django_migrations VALUES (84, 'reporting', '0121_auto_20200728_2258', '2021-04-23 14:29:17.388132+00');
INSERT INTO template0.django_migrations VALUES (85, 'reporting', '0122_auto_20200803_2307', '2021-04-23 14:29:17.390665+00');
INSERT INTO template0.django_migrations VALUES (86, 'reporting', '0123_auto_20200727_2302', '2021-04-23 14:29:17.393049+00');
INSERT INTO template0.django_migrations VALUES (87, 'reporting', '0124_auto_20200806_1943', '2021-04-23 14:29:17.395203+00');
INSERT INTO template0.django_migrations VALUES (88, 'reporting', '0125_azure_unit_normalization', '2021-04-23 14:29:17.397633+00');
INSERT INTO template0.django_migrations VALUES (89, 'reporting', '0126_clear_org_units', '2021-04-23 14:29:17.400121+00');
INSERT INTO template0.django_migrations VALUES (90, 'reporting', '0127_ocpazure_unit_normalization', '2021-04-23 14:29:17.402666+00');
INSERT INTO template0.django_migrations VALUES (91, 'reporting', '0128_auto_20200820_1540', '2021-04-23 14:29:17.405066+00');
INSERT INTO template0.django_migrations VALUES (92, 'reporting', '0129_partitioned_daily_summary', '2021-04-23 14:29:17.407544+00');
INSERT INTO template0.django_migrations VALUES (93, 'reporting', '0130_auto_20200826_1819', '2021-04-23 14:29:17.409813+00');
INSERT INTO template0.django_migrations VALUES (94, 'reporting', '0131_auto_20200827_1253', '2021-04-23 14:29:17.412128+00');
INSERT INTO template0.django_migrations VALUES (95, 'reporting', '0132_auto_20200901_1811', '2021-04-23 14:29:17.414342+00');
INSERT INTO template0.django_migrations VALUES (96, 'reporting', '0133_auto_20200901_2245', '2021-04-23 14:29:17.416555+00');
INSERT INTO template0.django_migrations VALUES (97, 'reporting', '0134_auto_20200902_1602', '2021-04-23 14:29:17.418657+00');
INSERT INTO template0.django_migrations VALUES (98, 'reporting', '0135_auto_20200902_1808', '2021-04-23 14:29:17.420912+00');
INSERT INTO template0.django_migrations VALUES (99, 'reporting', '0136_auto_20200909_1400', '2021-04-23 14:29:17.423336+00');
INSERT INTO template0.django_migrations VALUES (100, 'reporting', '0137_partitioned_tables_triggers', '2021-04-23 14:29:17.425784+00');
INSERT INTO template0.django_migrations VALUES (101, 'reporting', '0138_auto_20200918_1724', '2021-04-23 14:29:17.428314+00');
INSERT INTO template0.django_migrations VALUES (102, 'reporting', '0139_auto_20200925_1432', '2021-04-23 14:29:17.43059+00');
INSERT INTO template0.django_migrations VALUES (103, 'reporting', '0140_auto_20200925_1825', '2021-04-23 14:29:17.432997+00');
INSERT INTO template0.django_migrations VALUES (104, 'reporting', '0141_auto_20201002_1925', '2021-04-23 14:29:17.435132+00');
INSERT INTO template0.django_migrations VALUES (105, 'reporting', '0142_auto_20201002_1925', '2021-04-23 14:29:17.43733+00');
INSERT INTO template0.django_migrations VALUES (106, 'reporting', '0143_awsorganizationalunit_provider', '2021-04-23 14:29:17.842648+00');
INSERT INTO template0.django_migrations VALUES (107, 'reporting', '0144_auto_20201007_1441', '2021-04-23 14:29:17.860307+00');
INSERT INTO template0.django_migrations VALUES (108, 'reporting', '0145_awsenabledtagkeys_azureenabledtagkeys', '2021-04-23 14:29:17.887242+00');
INSERT INTO template0.django_migrations VALUES (109, 'reporting', '0146_auto_20200917_1448', '2021-04-23 14:29:18.141139+00');
INSERT INTO template0.django_migrations VALUES (110, 'reporting', '0147_auto_20201028_1305', '2021-04-23 14:29:18.150088+00');
INSERT INTO template0.django_migrations VALUES (111, 'reporting', '0148_presto_delete_log', '2021-04-23 14:29:18.166861+00');
INSERT INTO template0.django_migrations VALUES (112, 'reporting', '0149_auto_20201112_1414', '2021-04-23 14:29:18.175659+00');
INSERT INTO template0.django_migrations VALUES (113, 'reporting', '0150_presto_bulk_pk_delete', '2021-04-23 14:29:18.190668+00');
INSERT INTO template0.django_migrations VALUES (114, 'reporting', '0151_ocp_summary_table_presto_interface', '2021-04-23 14:29:18.206066+00');
INSERT INTO template0.django_migrations VALUES (115, 'reporting', '0152_gcpcostentrylineitem', '2021-04-23 14:29:18.43378+00');
INSERT INTO template0.django_migrations VALUES (116, 'reporting', '0153_ocpnamespacelabellineitem', '2021-04-23 14:29:18.521513+00');
INSERT INTO template0.django_migrations VALUES (117, 'reporting', '0154_gcp_summary_tables', '2021-04-23 14:29:19.278613+00');
INSERT INTO template0.django_migrations VALUES (118, 'reporting', '0155_gcp_partitioned', '2021-04-23 14:29:19.492431+00');
INSERT INTO template0.django_migrations VALUES (119, 'reporting', '0156_auto_20201208_2029', '2021-04-23 14:29:20.596405+00');
INSERT INTO template0.django_migrations VALUES (120, 'reporting', '0157_auto_20201214_1757', '2021-04-23 14:29:20.610292+00');
INSERT INTO template0.django_migrations VALUES (121, 'reporting', '0158_auto_20201214_1757', '2021-04-23 14:29:20.82659+00');
INSERT INTO template0.django_migrations VALUES (122, 'reporting', '0159_gcp_cost_summary', '2021-04-23 14:29:20.972728+00');
INSERT INTO template0.django_migrations VALUES (123, 'reporting', '0160_auto_20210114_1548', '2021-04-23 14:29:21.051241+00');
INSERT INTO template0.django_migrations VALUES (124, 'reporting', '0161_auto_20210118_2113', '2021-04-23 14:29:21.08103+00');
INSERT INTO template0.django_migrations VALUES (125, 'reporting', '0162_auto_20201120_1901', '2021-04-23 14:29:21.146479+00');
INSERT INTO template0.django_migrations VALUES (126, 'reporting', '0163_gcp_compute_summary', '2021-04-23 14:29:21.290881+00');
INSERT INTO template0.django_migrations VALUES (127, 'reporting', '0164_gcpcomputesummary_gcpcomputesummarybyaccount_gcpcomputesummarybyproject_gcpcomputesummarybyregion_gc', '2021-04-23 14:29:21.314344+00');
INSERT INTO template0.django_migrations VALUES (128, 'reporting', '0165_repartition_default_data', '2021-04-23 14:29:21.58916+00');
INSERT INTO template0.django_migrations VALUES (129, 'reporting', '0166_gcp_storage_summary', '2021-04-23 14:29:21.780641+00');
INSERT INTO template0.django_migrations VALUES (130, 'reporting', '0167_gcpdatabasesummary_gcpnetworksummary', '2021-04-23 14:29:21.921574+00');
INSERT INTO template0.django_migrations VALUES (131, 'reporting', '0168_auto_20210211_2210', '2021-04-23 14:29:21.990456+00');
INSERT INTO template0.django_migrations VALUES (132, 'reporting', '0169_auto_20210216_1448', '2021-04-23 14:29:22.134038+00');
INSERT INTO template0.django_migrations VALUES (133, 'reporting', '0170_auto_20210305_1659', '2021-04-23 14:29:22.418885+00');
INSERT INTO template0.django_migrations VALUES (134, 'reporting', '0171_gcp_database_network_additions', '2021-04-23 14:29:22.552644+00');
INSERT INTO template0.django_migrations VALUES (135, 'reporting', '0172_auto_20210318_1514', '2021-04-23 14:29:22.57849+00');
INSERT INTO template0.django_migrations VALUES (136, 'reporting', '0173_auto_20210325_1354', '2021-04-23 14:29:22.738107+00');
INSERT INTO template0.django_migrations VALUES (137, 'reporting', '0174_update_ocpall_matviews', '2021-04-23 14:29:22.990809+00');
INSERT INTO template0.django_migrations VALUES (138, 'reporting', '0175_auto_20210407_2043', '2021-04-23 14:29:23.110435+00');
INSERT INTO template0.django_migrations VALUES (139, 'reporting', '0176_update_aws_enabled_keys', '2021-04-23 14:29:23.160154+00');
INSERT INTO template0.django_migrations VALUES (140, 'reporting_common', '0001_initial_squashed_0007_auto_20190208_0316_squashed_0019_auto_20191022_1602', '2021-04-23 14:29:23.509154+00');
INSERT INTO template0.django_migrations VALUES (141, 'reporting_common', '0020_auto_20191022_1620_squashed_0025_auto_20200116_2048', '2021-04-23 14:29:23.512109+00');
INSERT INTO template0.django_migrations VALUES (142, 'reporting_common', '0021_delete_reportcolumnmap', '2021-04-23 14:29:23.514811+00');
INSERT INTO template0.django_migrations VALUES (143, 'reporting_common', '0022_auto_20200505_1707', '2021-04-23 14:29:23.517554+00');
INSERT INTO template0.django_migrations VALUES (144, 'reporting_common', '0023_delete_siunitscale', '2021-04-23 14:29:23.52069+00');
INSERT INTO template0.django_migrations VALUES (145, 'reporting_common', '0024_remove_costusagereportmanifest_num_processed_files', '2021-04-23 14:29:23.523571+00');
INSERT INTO template0.django_migrations VALUES (146, 'reporting_common', '0025_remove_costusagereportmanifest_task', '2021-04-23 14:29:23.52629+00');
INSERT INTO template0.django_migrations VALUES (147, 'reporting_common', '0026_costusagereportmanifest_manifest_modified_datetime', '2021-04-23 14:29:23.528819+00');
INSERT INTO template0.django_migrations VALUES (148, 'reporting_common', '0027_auto_20210412_1731', '2021-04-23 14:29:23.572201+00');
INSERT INTO template0.django_migrations VALUES (149, 'sessions', '0001_initial', '2021-04-23 14:29:23.581773+00');
INSERT INTO template0.django_migrations VALUES (150, 'api', '0001_initial', '2021-04-23 14:29:23.591231+00');
INSERT INTO template0.django_migrations VALUES (151, 'reporting', '0001_initial', '2021-04-23 14:29:23.594217+00');
INSERT INTO template0.django_migrations VALUES (152, 'reporting_common', '0001_initial', '2021-04-23 14:29:23.597153+00');
INSERT INTO template0.django_migrations VALUES (153, 'cost_models', '0001_initial', '2021-04-23 14:29:23.600165+00');


--
-- Data for Name: partitioned_tables; Type: TABLE DATA; Schema: template0; Owner: table_owner
--

INSERT INTO template0.partitioned_tables VALUES (1, 'template0', 'reporting_ocpusagelineitem_daily_summary_default', 'reporting_ocpusagelineitem_daily_summary', 'range', 'usage_start', '{"default": true}', true);
INSERT INTO template0.partitioned_tables VALUES (2, 'template0', 'reporting_awscostentrylineitem_daily_summary_default', 'reporting_awscostentrylineitem_daily_summary', 'range', 'usage_start', '{"default": true}', true);
INSERT INTO template0.partitioned_tables VALUES (3, 'template0', 'reporting_azurecostentrylineitem_daily_summary_default', 'reporting_azurecostentrylineitem_daily_summary', 'range', 'usage_start', '{"default": true}', true);
INSERT INTO template0.partitioned_tables VALUES (4, 'template0', 'reporting_gcpcostentrylineitem_daily_summary_default', 'reporting_gcpcostentrylineitem_daily_summary', 'range', 'usage_start', '{"default": true}', true);


--
-- Data for Name: presto_delete_wrapper_log; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: presto_pk_delete_wrapper_log; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awsaccountalias; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awscostentry; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awscostentrybill; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awscostentrylineitem; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awscostentrylineitem_daily; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awscostentrylineitem_daily_summary_default; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awscostentrypricing; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awscostentryproduct; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awscostentryreservation; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awsenabledtagkeys; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awsorganizationalunit; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awstags_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_awstags_values; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_azurecostentrybill; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_azurecostentrylineitem_daily; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_azurecostentrylineitem_daily_summary_default; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_azurecostentryproductservice; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_azureenabledtagkeys; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_azuremeter; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_azuretags_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_azuretags_values; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_gcpcostentrybill; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_gcpcostentrylineitem; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_gcpcostentrylineitem_daily; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_gcpcostentrylineitem_daily_summary_default; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_gcpcostentryproductservice; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_gcpenabledtagkeys; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_gcpproject; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_gcptags_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_gcptags_values; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpawscostlineitem_daily_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpawscostlineitem_project_daily_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpawstags_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpawstags_values; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpazurecostlineitem_daily_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpazurecostlineitem_project_daily_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpazuretags_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpazuretags_values; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpcosts_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpenabledtagkeys; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpnamespacelabellineitem; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpnodelabellineitem; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpnodelabellineitem_daily; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpstoragelineitem; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpstoragelineitem_daily; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpstoragevolumelabel_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocptags_values; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpusagelineitem; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpusagelineitem_daily; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpusagelineitem_daily_summary_default; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpusagepodlabel_summary; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpusagereport; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Data for Name: reporting_ocpusagereportperiod; Type: TABLE DATA; Schema: template0; Owner: table_owner
--



--
-- Name: cost_model_audit_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.cost_model_audit_id_seq', 1, false);


--
-- Name: cost_model_map_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.cost_model_map_id_seq', 1, false);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.django_migrations_id_seq', 153, true);


--
-- Name: partitioned_tables_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.partitioned_tables_id_seq', 4, true);


--
-- Name: reporting_awsaccountalias_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_awsaccountalias_id_seq', 1, false);


--
-- Name: reporting_awscostentry_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_awscostentry_id_seq', 1, false);


--
-- Name: reporting_awscostentrybill_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_awscostentrybill_id_seq', 1, false);


--
-- Name: reporting_awscostentrylineitem_daily_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_awscostentrylineitem_daily_id_seq', 1, false);


--
-- Name: reporting_awscostentrylineitem_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_awscostentrylineitem_id_seq', 1, false);


--
-- Name: reporting_awscostentrypricing_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_awscostentrypricing_id_seq', 1, false);


--
-- Name: reporting_awscostentryproduct_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_awscostentryproduct_id_seq', 1, false);


--
-- Name: reporting_awscostentryreservation_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_awscostentryreservation_id_seq', 1, false);


--
-- Name: reporting_awsorganizationalunit_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_awsorganizationalunit_id_seq', 1, false);


--
-- Name: reporting_azurecostentrybill_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_azurecostentrybill_id_seq', 1, false);


--
-- Name: reporting_azurecostentrylineitem_daily_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_azurecostentrylineitem_daily_id_seq', 1, false);


--
-- Name: reporting_azurecostentryproductservice_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_azurecostentryproductservice_id_seq', 1, false);


--
-- Name: reporting_azureenabledtagkeys_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_azureenabledtagkeys_id_seq', 1, false);


--
-- Name: reporting_azuremeter_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_azuremeter_id_seq', 1, false);


--
-- Name: reporting_gcpcostentrybill_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_gcpcostentrybill_id_seq', 1, false);


--
-- Name: reporting_gcpcostentrylineitem_daily_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_gcpcostentrylineitem_daily_id_seq', 1, false);


--
-- Name: reporting_gcpcostentrylineitem_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_gcpcostentrylineitem_id_seq', 1, false);


--
-- Name: reporting_gcpcostentryproductservice_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_gcpcostentryproductservice_id_seq', 1, false);


--
-- Name: reporting_gcpenabledtagkeys_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_gcpenabledtagkeys_id_seq', 1, false);


--
-- Name: reporting_gcpproject_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_gcpproject_id_seq', 1, false);


--
-- Name: reporting_ocpcosts_summary_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_ocpcosts_summary_id_seq', 1, false);


--
-- Name: reporting_ocpenabledtagkeys_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_ocpenabledtagkeys_id_seq', 1, false);


--
-- Name: reporting_ocpnamespacelabellineitem_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_ocpnamespacelabellineitem_id_seq', 1, false);


--
-- Name: reporting_ocpnodelabellineitem_daily_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_ocpnodelabellineitem_daily_id_seq', 1, false);


--
-- Name: reporting_ocpnodelabellineitem_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_ocpnodelabellineitem_id_seq', 1, false);


--
-- Name: reporting_ocpstoragelineitem_daily_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_ocpstoragelineitem_daily_id_seq', 1, false);


--
-- Name: reporting_ocpstoragelineitem_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_ocpstoragelineitem_id_seq', 1, false);


--
-- Name: reporting_ocpusagelineitem_daily_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_ocpusagelineitem_daily_id_seq', 1, false);


--
-- Name: reporting_ocpusagelineitem_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_ocpusagelineitem_id_seq', 1, false);


--
-- Name: reporting_ocpusagereport_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_ocpusagereport_id_seq', 1, false);


--
-- Name: reporting_ocpusagereportperiod_id_seq; Type: SEQUENCE SET; Schema: template0; Owner: table_owner
--

SELECT pg_catalog.setval('template0.reporting_ocpusagereportperiod_id_seq', 1, false);


--
-- Name: cost_model_audit cost_model_audit_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.cost_model_audit
    ADD CONSTRAINT cost_model_audit_pkey PRIMARY KEY (id);


--
-- Name: cost_model_map cost_model_map_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.cost_model_map
    ADD CONSTRAINT cost_model_map_pkey PRIMARY KEY (id);


--
-- Name: cost_model_map cost_model_map_provider_uuid_cost_model_id_40cf193b_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.cost_model_map
    ADD CONSTRAINT cost_model_map_provider_uuid_cost_model_id_40cf193b_uniq UNIQUE (provider_uuid, cost_model_id);


--
-- Name: cost_model cost_model_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.cost_model
    ADD CONSTRAINT cost_model_pkey PRIMARY KEY (uuid);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: reporting_gcpcostentrylineitem_daily_summary p_reporting_gcpcostentrylineitem_daily_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem_daily_summary
    ADD CONSTRAINT p_reporting_gcpcostentrylineitem_daily_summary_pkey PRIMARY KEY (usage_start, uuid);


--
-- Name: partitioned_tables partitioned_tables_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.partitioned_tables
    ADD CONSTRAINT partitioned_tables_pkey PRIMARY KEY (id);


--
-- Name: partitioned_tables partitioned_tables_schema_name_table_name_5f95f299_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.partitioned_tables
    ADD CONSTRAINT partitioned_tables_schema_name_table_name_5f95f299_uniq UNIQUE (schema_name, table_name);


--
-- Name: presto_delete_wrapper_log presto_delete_wrapper_log_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.presto_delete_wrapper_log
    ADD CONSTRAINT presto_delete_wrapper_log_pkey PRIMARY KEY (id);


--
-- Name: reporting_awsaccountalias reporting_awsaccountalias_account_id_key; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awsaccountalias
    ADD CONSTRAINT reporting_awsaccountalias_account_id_key UNIQUE (account_id);


--
-- Name: reporting_awsaccountalias reporting_awsaccountalias_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awsaccountalias
    ADD CONSTRAINT reporting_awsaccountalias_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentry reporting_awscostentry_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentry
    ADD CONSTRAINT reporting_awscostentry_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentrybill reporting_awscostentrybi_bill_type_payer_account__6f101061_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrybill
    ADD CONSTRAINT reporting_awscostentrybi_bill_type_payer_account__6f101061_uniq UNIQUE (bill_type, payer_account_id, billing_period_start, provider_id);


--
-- Name: reporting_awscostentrybill reporting_awscostentrybill_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrybill
    ADD CONSTRAINT reporting_awscostentrybill_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentrylineitem_daily reporting_awscostentrylineitem_daily_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem_daily
    ADD CONSTRAINT reporting_awscostentrylineitem_daily_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentrylineitem_daily_summary reporting_awscostentrylineitem_daily_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem_daily_summary
    ADD CONSTRAINT reporting_awscostentrylineitem_daily_summary_pkey PRIMARY KEY (usage_start, uuid);


--
-- Name: reporting_awscostentrylineitem_daily_summary_default reporting_awscostentrylineitem_daily_summary_default_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem_daily_summary_default
    ADD CONSTRAINT reporting_awscostentrylineitem_daily_summary_default_pkey PRIMARY KEY (usage_start, uuid);


--
-- Name: reporting_awscostentrylineitem reporting_awscostentrylineitem_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostentrylineitem_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentryproduct reporting_awscostentrypr_sku_product_name_region_fea902ae_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentryproduct
    ADD CONSTRAINT reporting_awscostentrypr_sku_product_name_region_fea902ae_uniq UNIQUE (sku, product_name, region);


--
-- Name: reporting_awscostentrypricing reporting_awscostentrypricing_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrypricing
    ADD CONSTRAINT reporting_awscostentrypricing_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentrypricing reporting_awscostentrypricing_term_unit_c3978af3_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrypricing
    ADD CONSTRAINT reporting_awscostentrypricing_term_unit_c3978af3_uniq UNIQUE (term, unit);


--
-- Name: reporting_awscostentryproduct reporting_awscostentryproduct_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentryproduct
    ADD CONSTRAINT reporting_awscostentryproduct_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentryreservation reporting_awscostentryreservation_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentryreservation
    ADD CONSTRAINT reporting_awscostentryreservation_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentryreservation reporting_awscostentryreservation_reservation_arn_key; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentryreservation
    ADD CONSTRAINT reporting_awscostentryreservation_reservation_arn_key UNIQUE (reservation_arn);


--
-- Name: reporting_awsenabledtagkeys reporting_awsenabledtagkeys_key_8c2841c2_pk; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awsenabledtagkeys
    ADD CONSTRAINT reporting_awsenabledtagkeys_key_8c2841c2_pk PRIMARY KEY (key);


--
-- Name: reporting_awsorganizationalunit reporting_awsorganizationalunit_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awsorganizationalunit
    ADD CONSTRAINT reporting_awsorganizationalunit_pkey PRIMARY KEY (id);


--
-- Name: reporting_awstags_summary reporting_awstags_summar_key_cost_entry_bill_id_u_1f71e435_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awstags_summary
    ADD CONSTRAINT reporting_awstags_summar_key_cost_entry_bill_id_u_1f71e435_uniq UNIQUE (key, cost_entry_bill_id, usage_account_id);


--
-- Name: reporting_awstags_summary reporting_awstags_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awstags_summary
    ADD CONSTRAINT reporting_awstags_summary_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_awstags_values reporting_awstags_values_key_value_56d23b8e_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awstags_values
    ADD CONSTRAINT reporting_awstags_values_key_value_56d23b8e_uniq UNIQUE (key, value);


--
-- Name: reporting_awstags_values reporting_awstags_values_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awstags_values
    ADD CONSTRAINT reporting_awstags_values_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_azurecostentrybill reporting_azurecostentry_billing_period_start_pro_c99ba20a_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentrybill
    ADD CONSTRAINT reporting_azurecostentry_billing_period_start_pro_c99ba20a_uniq UNIQUE (billing_period_start, provider_id);


--
-- Name: reporting_azurecostentryproductservice reporting_azurecostentry_instance_id_instance_typ_44f8ec94_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentryproductservice
    ADD CONSTRAINT reporting_azurecostentry_instance_id_instance_typ_44f8ec94_uniq UNIQUE (instance_id, instance_type, service_tier, service_name);


--
-- Name: reporting_azurecostentrybill reporting_azurecostentrybill_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentrybill
    ADD CONSTRAINT reporting_azurecostentrybill_pkey PRIMARY KEY (id);


--
-- Name: reporting_azurecostentrylineitem_daily reporting_azurecostentrylineitem_daily_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentrylineitem_daily
    ADD CONSTRAINT reporting_azurecostentrylineitem_daily_pkey PRIMARY KEY (id);


--
-- Name: reporting_azurecostentrylineitem_daily_summary reporting_azurecostentrylineitem_daily_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentrylineitem_daily_summary
    ADD CONSTRAINT reporting_azurecostentrylineitem_daily_summary_pkey PRIMARY KEY (usage_start, uuid);


--
-- Name: reporting_azurecostentrylineitem_daily_summary_default reporting_azurecostentrylineitem_daily_summary_default_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentrylineitem_daily_summary_default
    ADD CONSTRAINT reporting_azurecostentrylineitem_daily_summary_default_pkey PRIMARY KEY (usage_start, uuid);


--
-- Name: reporting_azurecostentryproductservice reporting_azurecostentryproductservice_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentryproductservice
    ADD CONSTRAINT reporting_azurecostentryproductservice_pkey PRIMARY KEY (id);


--
-- Name: reporting_azureenabledtagkeys reporting_azureenabledtagkeys_key_key; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azureenabledtagkeys
    ADD CONSTRAINT reporting_azureenabledtagkeys_key_key UNIQUE (key);


--
-- Name: reporting_azureenabledtagkeys reporting_azureenabledtagkeys_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azureenabledtagkeys
    ADD CONSTRAINT reporting_azureenabledtagkeys_pkey PRIMARY KEY (id);


--
-- Name: reporting_azuremeter reporting_azuremeter_meter_id_key; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azuremeter
    ADD CONSTRAINT reporting_azuremeter_meter_id_key UNIQUE (meter_id);


--
-- Name: reporting_azuremeter reporting_azuremeter_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azuremeter
    ADD CONSTRAINT reporting_azuremeter_pkey PRIMARY KEY (id);


--
-- Name: reporting_azuretags_summary reporting_azuretags_summ_key_cost_entry_bill_id_s_bf83e989_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azuretags_summary
    ADD CONSTRAINT reporting_azuretags_summ_key_cost_entry_bill_id_s_bf83e989_uniq UNIQUE (key, cost_entry_bill_id, subscription_guid);


--
-- Name: reporting_azuretags_summary reporting_azuretags_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azuretags_summary
    ADD CONSTRAINT reporting_azuretags_summary_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_azuretags_values reporting_azuretags_values_key_value_bb8b5dff_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azuretags_values
    ADD CONSTRAINT reporting_azuretags_values_key_value_bb8b5dff_uniq UNIQUE (key, value);


--
-- Name: reporting_azuretags_values reporting_azuretags_values_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azuretags_values
    ADD CONSTRAINT reporting_azuretags_values_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_gcpcostentrybill reporting_gcpcostentrybi_billing_period_start_pro_f84030ae_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrybill
    ADD CONSTRAINT reporting_gcpcostentrybi_billing_period_start_pro_f84030ae_uniq UNIQUE (billing_period_start, provider_id);


--
-- Name: reporting_gcpcostentrybill reporting_gcpcostentrybill_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrybill
    ADD CONSTRAINT reporting_gcpcostentrybill_pkey PRIMARY KEY (id);


--
-- Name: reporting_gcpcostentrylineitem_daily reporting_gcpcostentrylineitem_daily_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem_daily
    ADD CONSTRAINT reporting_gcpcostentrylineitem_daily_pkey PRIMARY KEY (id);


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_default reporting_gcpcostentrylineitem_daily_summary_default_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem_daily_summary_default
    ADD CONSTRAINT reporting_gcpcostentrylineitem_daily_summary_default_pkey PRIMARY KEY (usage_start, uuid);


--
-- Name: reporting_gcpcostentrylineitem reporting_gcpcostentrylineitem_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem
    ADD CONSTRAINT reporting_gcpcostentrylineitem_pkey PRIMARY KEY (id);


--
-- Name: reporting_gcpcostentryproductservice reporting_gcpcostentrypr_service_id_service_alias_47942f37_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentryproductservice
    ADD CONSTRAINT reporting_gcpcostentrypr_service_id_service_alias_47942f37_uniq UNIQUE (service_id, service_alias, sku_id, sku_alias);


--
-- Name: reporting_gcpcostentryproductservice reporting_gcpcostentryproductservice_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentryproductservice
    ADD CONSTRAINT reporting_gcpcostentryproductservice_pkey PRIMARY KEY (id);


--
-- Name: reporting_gcpenabledtagkeys reporting_gcpenabledtagkeys_key_key; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpenabledtagkeys
    ADD CONSTRAINT reporting_gcpenabledtagkeys_key_key UNIQUE (key);


--
-- Name: reporting_gcpenabledtagkeys reporting_gcpenabledtagkeys_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpenabledtagkeys
    ADD CONSTRAINT reporting_gcpenabledtagkeys_pkey PRIMARY KEY (id);


--
-- Name: reporting_gcpproject reporting_gcpproject_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpproject
    ADD CONSTRAINT reporting_gcpproject_pkey PRIMARY KEY (id);


--
-- Name: reporting_gcpproject reporting_gcpproject_project_id_key; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpproject
    ADD CONSTRAINT reporting_gcpproject_project_id_key UNIQUE (project_id);


--
-- Name: reporting_gcptags_summary reporting_gcptags_summar_key_cost_entry_bill_id_a_a0ec79e3_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcptags_summary
    ADD CONSTRAINT reporting_gcptags_summar_key_cost_entry_bill_id_a_a0ec79e3_uniq UNIQUE (key, cost_entry_bill_id, account_id, project_id, project_name);


--
-- Name: reporting_gcptags_summary reporting_gcptags_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcptags_summary
    ADD CONSTRAINT reporting_gcptags_summary_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_gcptags_values reporting_gcptags_values_key_value_dfee3462_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcptags_values
    ADD CONSTRAINT reporting_gcptags_values_key_value_dfee3462_uniq UNIQUE (key, value);


--
-- Name: reporting_gcptags_values reporting_gcptags_values_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcptags_values
    ADD CONSTRAINT reporting_gcptags_values_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_ocpawscostlineitem_project_daily_summary reporting_ocpawscostline_uuid_9afa8623_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawscostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpawscostline_uuid_9afa8623_uniq UNIQUE (uuid);


--
-- Name: reporting_ocpawscostlineitem_project_daily_summary reporting_ocpawscostlinei_uuid_9afa8623_pk; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawscostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpawscostlinei_uuid_9afa8623_pk PRIMARY KEY (uuid);


--
-- Name: reporting_ocpawscostlineitem_daily_summary reporting_ocpawscostlineitem_daily_summary_uuid_3d5dc959_pk; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawscostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpawscostlineitem_daily_summary_uuid_3d5dc959_pk PRIMARY KEY (uuid);


--
-- Name: reporting_ocpawscostlineitem_daily_summary reporting_ocpawscostlineitem_daily_summary_uuid_3d5dc959_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawscostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpawscostlineitem_daily_summary_uuid_3d5dc959_uniq UNIQUE (uuid);


--
-- Name: reporting_ocpawstags_summary reporting_ocpawstags_sum_key_cost_entry_bill_id_r_00bc8a3b_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawstags_summary
    ADD CONSTRAINT reporting_ocpawstags_sum_key_cost_entry_bill_id_r_00bc8a3b_uniq UNIQUE (key, cost_entry_bill_id, report_period_id, usage_account_id, namespace, node);


--
-- Name: reporting_ocpawstags_summary reporting_ocpawstags_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawstags_summary
    ADD CONSTRAINT reporting_ocpawstags_summary_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_ocpawstags_values reporting_ocpawstags_values_key_value_1efa08ea_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawstags_values
    ADD CONSTRAINT reporting_ocpawstags_values_key_value_1efa08ea_uniq UNIQUE (key, value);


--
-- Name: reporting_ocpawstags_values reporting_ocpawstags_values_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawstags_values
    ADD CONSTRAINT reporting_ocpawstags_values_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_ocpazurecostlineitem_project_daily_summary reporting_ocpazurecostli_uuid_1cf2074c_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazurecostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpazurecostli_uuid_1cf2074c_uniq UNIQUE (uuid);


--
-- Name: reporting_ocpazurecostlineitem_project_daily_summary reporting_ocpazurecostlin_uuid_1cf2074c_pk; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazurecostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpazurecostlin_uuid_1cf2074c_pk PRIMARY KEY (uuid);


--
-- Name: reporting_ocpazurecostlineitem_daily_summary reporting_ocpazurecostlineitem_daily_summary_uuid_4063f4f5_pk; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazurecostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpazurecostlineitem_daily_summary_uuid_4063f4f5_pk PRIMARY KEY (uuid);


--
-- Name: reporting_ocpazurecostlineitem_daily_summary reporting_ocpazurecostlineitem_daily_summary_uuid_4063f4f5_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazurecostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpazurecostlineitem_daily_summary_uuid_4063f4f5_uniq UNIQUE (uuid);


--
-- Name: reporting_ocpazuretags_summary reporting_ocpazuretags_s_key_cost_entry_bill_id_r_7fb461bc_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazuretags_summary
    ADD CONSTRAINT reporting_ocpazuretags_s_key_cost_entry_bill_id_r_7fb461bc_uniq UNIQUE (key, cost_entry_bill_id, report_period_id, subscription_guid, namespace, node);


--
-- Name: reporting_ocpazuretags_summary reporting_ocpazuretags_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazuretags_summary
    ADD CONSTRAINT reporting_ocpazuretags_summary_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_ocpazuretags_values reporting_ocpazuretags_values_key_value_306fdd41_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazuretags_values
    ADD CONSTRAINT reporting_ocpazuretags_values_key_value_306fdd41_uniq UNIQUE (key, value);


--
-- Name: reporting_ocpazuretags_values reporting_ocpazuretags_values_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazuretags_values
    ADD CONSTRAINT reporting_ocpazuretags_values_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_ocpcosts_summary reporting_ocpcosts_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpcosts_summary
    ADD CONSTRAINT reporting_ocpcosts_summary_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpenabledtagkeys reporting_ocpenabledtagkeys_key_key; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpenabledtagkeys
    ADD CONSTRAINT reporting_ocpenabledtagkeys_key_key UNIQUE (key);


--
-- Name: reporting_ocpenabledtagkeys reporting_ocpenabledtagkeys_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpenabledtagkeys
    ADD CONSTRAINT reporting_ocpenabledtagkeys_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpnamespacelabellineitem reporting_ocpnamespacela_report_id_namespace_00f2972c_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnamespacelabellineitem
    ADD CONSTRAINT reporting_ocpnamespacela_report_id_namespace_00f2972c_uniq UNIQUE (report_id, namespace);


--
-- Name: reporting_ocpnamespacelabellineitem reporting_ocpnamespacelabellineitem_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnamespacelabellineitem
    ADD CONSTRAINT reporting_ocpnamespacelabellineitem_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpnodelabellineitem_daily reporting_ocpnodelabellineitem_daily_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnodelabellineitem_daily
    ADD CONSTRAINT reporting_ocpnodelabellineitem_daily_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpnodelabellineitem reporting_ocpnodelabellineitem_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnodelabellineitem
    ADD CONSTRAINT reporting_ocpnodelabellineitem_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpnodelabellineitem reporting_ocpnodelabellineitem_report_id_node_babd91c2_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnodelabellineitem
    ADD CONSTRAINT reporting_ocpnodelabellineitem_report_id_node_babd91c2_uniq UNIQUE (report_id, node);


--
-- Name: reporting_ocpstoragelineitem reporting_ocpstorageline_report_id_namespace_pers_9bf00103_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpstoragelineitem
    ADD CONSTRAINT reporting_ocpstorageline_report_id_namespace_pers_9bf00103_uniq UNIQUE (report_id, namespace, persistentvolumeclaim);


--
-- Name: reporting_ocpstoragelineitem_daily reporting_ocpstoragelineitem_daily_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpstoragelineitem_daily
    ADD CONSTRAINT reporting_ocpstoragelineitem_daily_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpstoragelineitem reporting_ocpstoragelineitem_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpstoragelineitem
    ADD CONSTRAINT reporting_ocpstoragelineitem_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpstoragevolumelabel_summary reporting_ocpstoragevolu_key_report_period_id_nam_17bc3852_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpstoragevolumelabel_summary
    ADD CONSTRAINT reporting_ocpstoragevolu_key_report_period_id_nam_17bc3852_uniq UNIQUE (key, report_period_id, namespace, node);


--
-- Name: reporting_ocpstoragevolumelabel_summary reporting_ocpstoragevolumelabel_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpstoragevolumelabel_summary
    ADD CONSTRAINT reporting_ocpstoragevolumelabel_summary_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_ocptags_values reporting_ocptags_values_key_value_135d8752_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocptags_values
    ADD CONSTRAINT reporting_ocptags_values_key_value_135d8752_uniq UNIQUE (key, value);


--
-- Name: reporting_ocptags_values reporting_ocptags_values_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocptags_values
    ADD CONSTRAINT reporting_ocptags_values_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_ocpusagelineitem reporting_ocpusagelineit_report_id_namespace_pod__dfc2c342_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagelineitem
    ADD CONSTRAINT reporting_ocpusagelineit_report_id_namespace_pod__dfc2c342_uniq UNIQUE (report_id, namespace, pod, node);


--
-- Name: reporting_ocpusagelineitem_daily reporting_ocpusagelineitem_daily_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagelineitem_daily
    ADD CONSTRAINT reporting_ocpusagelineitem_daily_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpusagelineitem_daily_summary reporting_ocpusagelineitem_daily_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagelineitem_daily_summary
    ADD CONSTRAINT reporting_ocpusagelineitem_daily_summary_pkey PRIMARY KEY (usage_start, uuid);


--
-- Name: reporting_ocpusagelineitem_daily_summary_default reporting_ocpusagelineitem_daily_summary_default_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagelineitem_daily_summary_default
    ADD CONSTRAINT reporting_ocpusagelineitem_daily_summary_default_pkey PRIMARY KEY (usage_start, uuid);


--
-- Name: reporting_ocpusagelineitem reporting_ocpusagelineitem_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagelineitem
    ADD CONSTRAINT reporting_ocpusagelineitem_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpusagepodlabel_summary reporting_ocpusagepodlab_key_report_period_id_nam_8284236c_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagepodlabel_summary
    ADD CONSTRAINT reporting_ocpusagepodlab_key_report_period_id_nam_8284236c_uniq UNIQUE (key, report_period_id, namespace, node);


--
-- Name: reporting_ocpusagepodlabel_summary reporting_ocpusagepodlabel_summary_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagepodlabel_summary
    ADD CONSTRAINT reporting_ocpusagepodlabel_summary_pkey PRIMARY KEY (uuid);


--
-- Name: reporting_ocpusagereportperiod reporting_ocpusagereport_cluster_id_report_period_ff3ea314_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagereportperiod
    ADD CONSTRAINT reporting_ocpusagereport_cluster_id_report_period_ff3ea314_uniq UNIQUE (cluster_id, report_period_start, provider_id);


--
-- Name: reporting_ocpusagereport reporting_ocpusagereport_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagereport
    ADD CONSTRAINT reporting_ocpusagereport_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpusagereport reporting_ocpusagereport_report_period_id_interva_066551f3_uniq; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagereport
    ADD CONSTRAINT reporting_ocpusagereport_report_period_id_interva_066551f3_uniq UNIQUE (report_period_id, interval_start);


--
-- Name: reporting_ocpusagereportperiod reporting_ocpusagereportperiod_pkey; Type: CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagereportperiod
    ADD CONSTRAINT reporting_ocpusagereportperiod_pkey PRIMARY KEY (id);


--
-- Name: aws_compute_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_compute_summary ON template0.reporting_aws_compute_summary USING btree (usage_start, source_uuid, instance_type);


--
-- Name: aws_compute_summary_account; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_compute_summary_account ON template0.reporting_aws_compute_summary_by_account USING btree (usage_start, usage_account_id, account_alias_id, instance_type);


--
-- Name: aws_compute_summary_region; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_compute_summary_region ON template0.reporting_aws_compute_summary_by_region USING btree (usage_start, usage_account_id, region, availability_zone, instance_type);


--
-- Name: aws_compute_summary_service; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_compute_summary_service ON template0.reporting_aws_compute_summary_by_service USING btree (usage_start, usage_account_id, product_code, product_family, instance_type);


--
-- Name: aws_cost_entry; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX aws_cost_entry ON template0.reporting_awscostentrylineitem_daily USING gin (tags);


--
-- Name: aws_cost_pcode_like; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX aws_cost_pcode_like ON template0.reporting_awscostentrylineitem_daily USING gin (product_code public.gin_trgm_ops);


--
-- Name: aws_cost_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_cost_summary ON template0.reporting_aws_cost_summary USING btree (usage_start, source_uuid);


--
-- Name: aws_cost_summary_account; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_cost_summary_account ON template0.reporting_aws_cost_summary_by_account USING btree (usage_start, usage_account_id);


--
-- Name: aws_cost_summary_region; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_cost_summary_region ON template0.reporting_aws_cost_summary_by_region USING btree (usage_start, usage_account_id, region, availability_zone);


--
-- Name: aws_cost_summary_service; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_cost_summary_service ON template0.reporting_aws_cost_summary_by_service USING btree (usage_start, usage_account_id, product_code, product_family);


--
-- Name: aws_database_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_database_summary ON template0.reporting_aws_database_summary USING btree (usage_start, usage_account_id, product_code);


--
-- Name: aws_enabled_key_index; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX aws_enabled_key_index ON template0.reporting_awsenabledtagkeys USING btree (key, enabled);


--
-- Name: aws_network_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_network_summary ON template0.reporting_aws_network_summary USING btree (usage_start, usage_account_id, product_code);


--
-- Name: aws_storage_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_storage_summary ON template0.reporting_aws_storage_summary USING btree (usage_start, source_uuid, product_family);


--
-- Name: aws_storage_summary_account; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_storage_summary_account ON template0.reporting_aws_storage_summary_by_account USING btree (usage_start, usage_account_id, product_family);


--
-- Name: aws_storage_summary_region; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_storage_summary_region ON template0.reporting_aws_storage_summary_by_region USING btree (usage_start, usage_account_id, region, availability_zone, product_family);


--
-- Name: aws_storage_summary_service; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX aws_storage_summary_service ON template0.reporting_aws_storage_summary_by_service USING btree (usage_start, usage_account_id, product_code, product_family);


--
-- Name: aws_summ_usage_pcode_ilike; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX aws_summ_usage_pcode_ilike ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING gin (upper((product_family)::text) public.gin_trgm_ops);


--
-- Name: aws_summ_usage_pfam_ilike; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX aws_summ_usage_pfam_ilike ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING gin (upper((product_family)::text) public.gin_trgm_ops);


--
-- Name: aws_tags_value_key_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX aws_tags_value_key_idx ON template0.reporting_awstags_values USING btree (key);


--
-- Name: azure_compute_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX azure_compute_summary ON template0.reporting_azure_compute_summary USING btree (usage_start, subscription_guid, instance_type);


--
-- Name: azure_cost_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX azure_cost_summary ON template0.reporting_azure_cost_summary USING btree (usage_start, source_uuid);


--
-- Name: azure_cost_summary_account; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX azure_cost_summary_account ON template0.reporting_azure_cost_summary_by_account USING btree (usage_start, subscription_guid);


--
-- Name: azure_cost_summary_location; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX azure_cost_summary_location ON template0.reporting_azure_cost_summary_by_location USING btree (usage_start, subscription_guid, resource_location);


--
-- Name: azure_cost_summary_service; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX azure_cost_summary_service ON template0.reporting_azure_cost_summary_by_service USING btree (usage_start, subscription_guid, service_name);


--
-- Name: azure_database_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX azure_database_summary ON template0.reporting_azure_database_summary USING btree (usage_start, subscription_guid, service_name);


--
-- Name: azure_network_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX azure_network_summary ON template0.reporting_azure_network_summary USING btree (usage_start, subscription_guid, service_name);


--
-- Name: azure_storage_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX azure_storage_summary ON template0.reporting_azure_storage_summary USING btree (usage_start, subscription_guid, service_name);


--
-- Name: azure_tags_value_key_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX azure_tags_value_key_idx ON template0.reporting_azuretags_values USING btree (key);


--
-- Name: cost__proj_sum_namespace_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost__proj_sum_namespace_idx ON template0.reporting_ocpawscostlineitem_project_daily_summary USING btree (namespace varchar_pattern_ops);


--
-- Name: cost__proj_sum_namespace_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost__proj_sum_namespace_like_idx ON template0.reporting_ocpawscostlineitem_project_daily_summary USING gin (upper((namespace)::text) public.gin_trgm_ops);


--
-- Name: cost__proj_sum_node_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost__proj_sum_node_like_idx ON template0.reporting_ocpawscostlineitem_project_daily_summary USING gin (upper((node)::text) public.gin_trgm_ops);


--
-- Name: cost_model_map_cost_model_id_3c67db61; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost_model_map_cost_model_id_3c67db61 ON template0.cost_model_map USING btree (cost_model_id);


--
-- Name: cost_proj_pod_labels_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost_proj_pod_labels_idx ON template0.reporting_ocpawscostlineitem_project_daily_summary USING gin (pod_labels);


--
-- Name: cost_proj_sum_node_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost_proj_sum_node_idx ON template0.reporting_ocpawscostlineitem_project_daily_summary USING btree (node varchar_pattern_ops);


--
-- Name: cost_proj_sum_ocp_usage_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost_proj_sum_ocp_usage_idx ON template0.reporting_ocpawscostlineitem_project_daily_summary USING btree (usage_start);


--
-- Name: cost_proj_sum_resource_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost_proj_sum_resource_idx ON template0.reporting_ocpawscostlineitem_project_daily_summary USING btree (resource_id);


--
-- Name: cost_summary_namespace_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost_summary_namespace_idx ON template0.reporting_ocpawscostlineitem_daily_summary USING btree (namespace);


--
-- Name: cost_summary_node_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost_summary_node_idx ON template0.reporting_ocpawscostlineitem_daily_summary USING btree (node varchar_pattern_ops);


--
-- Name: cost_summary_node_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost_summary_node_like_idx ON template0.reporting_ocpawscostlineitem_daily_summary USING gin (upper((node)::text) public.gin_trgm_ops);


--
-- Name: cost_summary_ocp_usage_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost_summary_ocp_usage_idx ON template0.reporting_ocpawscostlineitem_daily_summary USING btree (usage_start);


--
-- Name: cost_summary_resource_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost_summary_resource_idx ON template0.reporting_ocpawscostlineitem_daily_summary USING btree (resource_id);


--
-- Name: cost_tags_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX cost_tags_idx ON template0.reporting_ocpawscostlineitem_daily_summary USING gin (tags);


--
-- Name: gcp_compute_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_compute_summary ON template0.reporting_gcp_compute_summary USING btree (usage_start, source_uuid, instance_type);


--
-- Name: gcp_compute_summary_account; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_compute_summary_account ON template0.reporting_gcp_compute_summary_by_account USING btree (usage_start, instance_type, account_id);


--
-- Name: gcp_compute_summary_project; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_compute_summary_project ON template0.reporting_gcp_compute_summary_by_project USING btree (usage_start, instance_type, project_id, project_name, account_id);


--
-- Name: gcp_compute_summary_region; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_compute_summary_region ON template0.reporting_gcp_compute_summary_by_region USING btree (usage_start, instance_type, account_id, region);


--
-- Name: gcp_compute_summary_service; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_compute_summary_service ON template0.reporting_gcp_compute_summary_by_service USING btree (usage_start, instance_type, account_id, service_id, service_alias);


--
-- Name: gcp_cost_entry; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX gcp_cost_entry ON template0.reporting_gcpcostentrylineitem_daily USING gin (tags);


--
-- Name: gcp_cost_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_cost_summary ON template0.reporting_gcp_cost_summary USING btree (usage_start, source_uuid);


--
-- Name: gcp_cost_summary_account; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_cost_summary_account ON template0.reporting_gcp_cost_summary_by_account USING btree (usage_start, account_id);


--
-- Name: gcp_cost_summary_project; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_cost_summary_project ON template0.reporting_gcp_cost_summary_by_project USING btree (usage_start, project_id, project_name, account_id);


--
-- Name: gcp_cost_summary_region; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_cost_summary_region ON template0.reporting_gcp_cost_summary_by_region USING btree (usage_start, account_id, region);


--
-- Name: gcp_cost_summary_service; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_cost_summary_service ON template0.reporting_gcp_cost_summary_by_service USING btree (usage_start, account_id, service_id, service_alias);


--
-- Name: gcp_database_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_database_summary ON template0.reporting_gcp_database_summary USING btree (usage_start, account_id, service_id, service_alias);


--
-- Name: gcp_network_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_network_summary ON template0.reporting_gcp_network_summary USING btree (usage_start, account_id, service_id, service_alias);


--
-- Name: gcp_storage_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_storage_summary ON template0.reporting_gcp_storage_summary USING btree (usage_start, source_uuid);


--
-- Name: gcp_storage_summary_account; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_storage_summary_account ON template0.reporting_gcp_storage_summary_by_account USING btree (usage_start, account_id);


--
-- Name: gcp_storage_summary_project; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_storage_summary_project ON template0.reporting_gcp_storage_summary_by_project USING btree (usage_start, project_id, project_name, account_id);


--
-- Name: gcp_storage_summary_region; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_storage_summary_region ON template0.reporting_gcp_storage_summary_by_region USING btree (usage_start, account_id, region);


--
-- Name: gcp_storage_summary_service; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX gcp_storage_summary_service ON template0.reporting_gcp_storage_summary_by_service USING btree (usage_start, account_id, service_id, service_alias);


--
-- Name: gcp_tags_value_key_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX gcp_tags_value_key_idx ON template0.reporting_gcptags_values USING btree (key);


--
-- Name: gcp_usage_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX gcp_usage_start_idx ON template0.reporting_gcpcostentrylineitem_daily USING btree (usage_start);


--
-- Name: interval_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX interval_start_idx ON template0.reporting_awscostentry USING btree (interval_start);


--
-- Name: ix_azure_costentrydlysumm_service_name; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ix_azure_costentrydlysumm_service_name ON ONLY template0.reporting_azurecostentrylineitem_daily_summary USING gin (upper(service_name) public.gin_trgm_ops);


--
-- Name: ix_ocp_aws_product_code_ilike; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ix_ocp_aws_product_code_ilike ON template0.reporting_ocpawscostlineitem_daily_summary USING gin (upper((product_code)::text) public.gin_trgm_ops);


--
-- Name: ix_ocp_aws_product_family_ilike; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ix_ocp_aws_product_family_ilike ON template0.reporting_ocpawscostlineitem_daily_summary USING gin (upper((product_family)::text) public.gin_trgm_ops);


--
-- Name: ix_ocpazure_service_name_ilike; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ix_ocpazure_service_name_ilike ON template0.reporting_ocpazurecostlineitem_daily_summary USING gin (upper(service_name) public.gin_trgm_ops);


--
-- Name: name_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX name_idx ON template0.cost_model USING btree (name);


--
-- Name: namespace_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX namespace_idx ON template0.reporting_ocpusagelineitem_daily USING btree (namespace varchar_pattern_ops);


--
-- Name: node_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX node_idx ON template0.reporting_ocpusagelineitem_daily USING btree (node varchar_pattern_ops);


--
-- Name: ocp_aws_instance_type_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_aws_instance_type_idx ON template0.reporting_ocpawscostlineitem_daily_summary USING btree (instance_type);


--
-- Name: ocp_aws_product_family_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_aws_product_family_idx ON template0.reporting_ocpawscostlineitem_daily_summary USING btree (product_family);


--
-- Name: ocp_aws_proj_inst_type_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_aws_proj_inst_type_idx ON template0.reporting_ocpawscostlineitem_project_daily_summary USING btree (instance_type);


--
-- Name: ocp_aws_proj_prod_fam_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_aws_proj_prod_fam_idx ON template0.reporting_ocpawscostlineitem_project_daily_summary USING btree (product_family);


--
-- Name: ocp_aws_tags_value_key_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_aws_tags_value_key_idx ON template0.reporting_ocpawstags_values USING btree (key);


--
-- Name: ocp_azure_tags_value_key_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_azure_tags_value_key_idx ON template0.reporting_ocpazuretags_values USING btree (key);


--
-- Name: ocp_cost_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocp_cost_summary ON template0.reporting_ocp_cost_summary USING btree (usage_start, cluster_id, cluster_alias, source_uuid);


--
-- Name: ocp_cost_summary_by_node; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocp_cost_summary_by_node ON template0.reporting_ocp_cost_summary_by_node USING btree (usage_start, cluster_id, cluster_alias, node, source_uuid);


--
-- Name: ocp_cost_summary_by_project; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocp_cost_summary_by_project ON template0.reporting_ocp_cost_summary_by_project USING btree (usage_start, cluster_id, cluster_alias, namespace, source_uuid);


--
-- Name: ocp_interval_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_interval_start_idx ON template0.reporting_ocpusagereport USING btree (interval_start);


--
-- Name: ocp_namespace_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_namespace_idx ON template0.reporting_ocpusagelineitem_daily USING gin (upper((namespace)::text) public.gin_trgm_ops);


--
-- Name: ocp_node_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_node_idx ON template0.reporting_ocpusagelineitem_daily USING gin (upper((node)::text) public.gin_trgm_ops);


--
-- Name: ocp_pod_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocp_pod_summary ON template0.reporting_ocp_pod_summary USING btree (usage_start, cluster_id, cluster_alias, source_uuid);


--
-- Name: ocp_pod_summary_by_project; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocp_pod_summary_by_project ON template0.reporting_ocp_pod_summary_by_project USING btree (usage_start, cluster_id, cluster_alias, namespace, source_uuid);


--
-- Name: ocp_storage_li_namespace_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_storage_li_namespace_idx ON template0.reporting_ocpstoragelineitem_daily USING btree (namespace varchar_pattern_ops);


--
-- Name: ocp_storage_li_namespace_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_storage_li_namespace_like_idx ON template0.reporting_ocpstoragelineitem_daily USING gin (upper((namespace)::text) public.gin_trgm_ops);


--
-- Name: ocp_storage_li_node_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_storage_li_node_idx ON template0.reporting_ocpstoragelineitem_daily USING btree (node varchar_pattern_ops);


--
-- Name: ocp_storage_li_node_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_storage_li_node_like_idx ON template0.reporting_ocpstoragelineitem_daily USING gin (upper((node)::text) public.gin_trgm_ops);


--
-- Name: ocp_summary_namespace_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_summary_namespace_like_idx ON ONLY template0.reporting_ocpusagelineitem_daily_summary USING gin (upper((namespace)::text) public.gin_trgm_ops);


--
-- Name: ocp_summary_node_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_summary_node_like_idx ON ONLY template0.reporting_ocpusagelineitem_daily_summary USING gin (upper((node)::text) public.gin_trgm_ops);


--
-- Name: ocp_usage_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocp_usage_idx ON template0.reporting_ocpusagelineitem_daily USING btree (usage_start);


--
-- Name: ocp_volume_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocp_volume_summary ON template0.reporting_ocp_volume_summary USING btree (usage_start, cluster_id, cluster_alias, source_uuid);


--
-- Name: ocp_volume_summary_by_project; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocp_volume_summary_by_project ON template0.reporting_ocp_volume_summary_by_project USING btree (usage_start, cluster_id, cluster_alias, namespace, source_uuid);


--
-- Name: ocpall_compute_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpall_compute_summary ON template0.reporting_ocpall_compute_summary USING btree (usage_start, cluster_id, usage_account_id, product_code, instance_type, resource_id);


--
-- Name: ocpall_cost_daily_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpall_cost_daily_summary ON template0.reporting_ocpallcostlineitem_daily_summary USING btree (source_type, usage_start, cluster_id, namespace, node, usage_account_id, resource_id, product_code, product_family, instance_type, region, availability_zone, tags);


--
-- Name: ocpall_cost_project_daily_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpall_cost_project_daily_summary ON template0.reporting_ocpallcostlineitem_project_daily_summary USING btree (source_type, usage_start, cluster_id, data_source, namespace, node, usage_account_id, resource_id, product_code, product_family, instance_type, region, availability_zone, pod_labels);


--
-- Name: ocpall_cost_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpall_cost_summary ON template0.reporting_ocpall_cost_summary USING btree (usage_start, cluster_id, source_uuid);


--
-- Name: ocpall_cost_summary_account; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpall_cost_summary_account ON template0.reporting_ocpall_cost_summary_by_account USING btree (usage_start, cluster_id, usage_account_id);


--
-- Name: ocpall_cost_summary_region; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpall_cost_summary_region ON template0.reporting_ocpall_cost_summary_by_region USING btree (usage_start, cluster_id, usage_account_id, region, availability_zone);


--
-- Name: ocpall_cost_summary_service; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpall_cost_summary_service ON template0.reporting_ocpall_cost_summary_by_service USING btree (usage_start, cluster_id, usage_account_id, product_code, product_family);


--
-- Name: ocpall_database_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpall_database_summary ON template0.reporting_ocpall_database_summary USING btree (usage_start, cluster_id, usage_account_id, product_code);


--
-- Name: ocpall_network_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpall_network_summary ON template0.reporting_ocpall_network_summary USING btree (usage_start, cluster_id, usage_account_id, product_code);


--
-- Name: ocpall_product_code_ilike; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpall_product_code_ilike ON template0.reporting_ocpallcostlineitem_daily_summary USING gin (upper((product_code)::text) public.gin_trgm_ops);


--
-- Name: ocpall_product_family_ilike; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpall_product_family_ilike ON template0.reporting_ocpallcostlineitem_daily_summary USING gin (upper((product_family)::text) public.gin_trgm_ops);


--
-- Name: ocpall_storage_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpall_storage_summary ON template0.reporting_ocpall_storage_summary USING btree (usage_start, cluster_id, usage_account_id, product_family, product_code);


--
-- Name: ocpallcstdlysumm_node; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpallcstdlysumm_node ON template0.reporting_ocpallcostlineitem_daily_summary USING btree (node text_pattern_ops);


--
-- Name: ocpallcstdlysumm_node_like; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpallcstdlysumm_node_like ON template0.reporting_ocpallcostlineitem_daily_summary USING gin (node public.gin_trgm_ops);


--
-- Name: ocpallcstdlysumm_nsp; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpallcstdlysumm_nsp ON template0.reporting_ocpallcostlineitem_daily_summary USING gin (namespace);


--
-- Name: ocpallcstprjdlysumm_node; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpallcstprjdlysumm_node ON template0.reporting_ocpallcostlineitem_project_daily_summary USING btree (node text_pattern_ops);


--
-- Name: ocpallcstprjdlysumm_node_like; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpallcstprjdlysumm_node_like ON template0.reporting_ocpallcostlineitem_project_daily_summary USING gin (node public.gin_trgm_ops);


--
-- Name: ocpallcstprjdlysumm_nsp; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpallcstprjdlysumm_nsp ON template0.reporting_ocpallcostlineitem_project_daily_summary USING btree (namespace text_pattern_ops);


--
-- Name: ocpallcstprjdlysumm_nsp_like; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpallcstprjdlysumm_nsp_like ON template0.reporting_ocpallcostlineitem_project_daily_summary USING gin (namespace public.gin_trgm_ops);


--
-- Name: ocpaws_compute_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpaws_compute_summary ON template0.reporting_ocpaws_compute_summary USING btree (usage_start, cluster_id, usage_account_id, instance_type, resource_id);


--
-- Name: ocpaws_cost_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpaws_cost_summary ON template0.reporting_ocpaws_cost_summary USING btree (usage_start, cluster_id);


--
-- Name: ocpaws_cost_summary_account; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpaws_cost_summary_account ON template0.reporting_ocpaws_cost_summary_by_account USING btree (usage_start, cluster_id, usage_account_id);


--
-- Name: ocpaws_cost_summary_region; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpaws_cost_summary_region ON template0.reporting_ocpaws_cost_summary_by_region USING btree (usage_start, cluster_id, usage_account_id, region, availability_zone);


--
-- Name: ocpaws_cost_summary_service; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpaws_cost_summary_service ON template0.reporting_ocpaws_cost_summary_by_service USING btree (usage_start, cluster_id, usage_account_id, product_code, product_family);


--
-- Name: ocpaws_database_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpaws_database_summary ON template0.reporting_ocpaws_database_summary USING btree (usage_start, cluster_id, usage_account_id, product_code);


--
-- Name: ocpaws_network_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpaws_network_summary ON template0.reporting_ocpaws_network_summary USING btree (usage_start, cluster_id, usage_account_id, product_code);


--
-- Name: ocpaws_storage_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpaws_storage_summary ON template0.reporting_ocpaws_storage_summary USING btree (usage_start, cluster_id, usage_account_id, product_family);


--
-- Name: ocpazure_compute_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpazure_compute_summary ON template0.reporting_ocpazure_compute_summary USING btree (usage_start, cluster_id, subscription_guid, instance_type, resource_id);


--
-- Name: ocpazure_cost_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpazure_cost_summary ON template0.reporting_ocpazure_cost_summary USING btree (usage_start, cluster_id, cluster_alias, source_uuid);


--
-- Name: ocpazure_cost_summary_account; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpazure_cost_summary_account ON template0.reporting_ocpazure_cost_summary_by_account USING btree (usage_start, cluster_id, subscription_guid);


--
-- Name: ocpazure_cost_summary_location; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpazure_cost_summary_location ON template0.reporting_ocpazure_cost_summary_by_location USING btree (usage_start, cluster_id, subscription_guid, resource_location);


--
-- Name: ocpazure_cost_summary_service; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpazure_cost_summary_service ON template0.reporting_ocpazure_cost_summary_by_service USING btree (usage_start, cluster_id, subscription_guid, service_name);


--
-- Name: ocpazure_database_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpazure_database_summary ON template0.reporting_ocpazure_database_summary USING btree (usage_start, cluster_id, subscription_guid, service_name);


--
-- Name: ocpazure_instance_type_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_instance_type_idx ON template0.reporting_ocpazurecostlineitem_daily_summary USING btree (instance_type);


--
-- Name: ocpazure_namespace_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_namespace_idx ON template0.reporting_ocpazurecostlineitem_daily_summary USING btree (namespace);


--
-- Name: ocpazure_network_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpazure_network_summary ON template0.reporting_ocpazure_network_summary USING btree (usage_start, cluster_id, subscription_guid, service_name);


--
-- Name: ocpazure_node_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_node_idx ON template0.reporting_ocpazurecostlineitem_daily_summary USING btree (node varchar_pattern_ops);


--
-- Name: ocpazure_node_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_node_like_idx ON template0.reporting_ocpazurecostlineitem_daily_summary USING gin (upper((node)::text) public.gin_trgm_ops);


--
-- Name: ocpazure_proj_inst_type_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_proj_inst_type_idx ON template0.reporting_ocpazurecostlineitem_project_daily_summary USING btree (instance_type);


--
-- Name: ocpazure_proj_namespace_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_proj_namespace_idx ON template0.reporting_ocpazurecostlineitem_project_daily_summary USING btree (namespace varchar_pattern_ops);


--
-- Name: ocpazure_proj_namespace_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_proj_namespace_like_idx ON template0.reporting_ocpazurecostlineitem_project_daily_summary USING gin (upper((namespace)::text) public.gin_trgm_ops);


--
-- Name: ocpazure_proj_node_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_proj_node_idx ON template0.reporting_ocpazurecostlineitem_project_daily_summary USING btree (node varchar_pattern_ops);


--
-- Name: ocpazure_proj_node_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_proj_node_like_idx ON template0.reporting_ocpazurecostlineitem_project_daily_summary USING gin (upper((node)::text) public.gin_trgm_ops);


--
-- Name: ocpazure_proj_pod_labels_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_proj_pod_labels_idx ON template0.reporting_ocpazurecostlineitem_project_daily_summary USING gin (pod_labels);


--
-- Name: ocpazure_proj_resource_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_proj_resource_id_idx ON template0.reporting_ocpazurecostlineitem_project_daily_summary USING btree (resource_id);


--
-- Name: ocpazure_proj_service_name_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_proj_service_name_idx ON template0.reporting_ocpazurecostlineitem_project_daily_summary USING btree (service_name);


--
-- Name: ocpazure_proj_usage_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_proj_usage_start_idx ON template0.reporting_ocpazurecostlineitem_project_daily_summary USING btree (usage_start);


--
-- Name: ocpazure_resource_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_resource_idx ON template0.reporting_ocpazurecostlineitem_daily_summary USING btree (resource_id);


--
-- Name: ocpazure_service_name_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_service_name_idx ON template0.reporting_ocpazurecostlineitem_daily_summary USING btree (service_name);


--
-- Name: ocpazure_storage_summary; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE UNIQUE INDEX ocpazure_storage_summary ON template0.reporting_ocpazure_storage_summary USING btree (usage_start, cluster_id, subscription_guid, service_name);


--
-- Name: ocpazure_tags_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_tags_idx ON template0.reporting_ocpazurecostlineitem_daily_summary USING gin (tags);


--
-- Name: ocpazure_usage_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpazure_usage_start_idx ON template0.reporting_ocpazurecostlineitem_daily_summary USING btree (usage_start);


--
-- Name: ocpcostsum_namespace_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpcostsum_namespace_idx ON template0.reporting_ocpcosts_summary USING btree (namespace varchar_pattern_ops);


--
-- Name: ocpcostsum_namespace_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpcostsum_namespace_like_idx ON template0.reporting_ocpcosts_summary USING gin (upper((namespace)::text) public.gin_trgm_ops);


--
-- Name: ocpcostsum_node_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpcostsum_node_idx ON template0.reporting_ocpcosts_summary USING btree (node varchar_pattern_ops);


--
-- Name: ocpcostsum_node_like_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpcostsum_node_like_idx ON template0.reporting_ocpcosts_summary USING gin (upper((node)::text) public.gin_trgm_ops);


--
-- Name: ocpcostsum_pod_labels_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpcostsum_pod_labels_idx ON template0.reporting_ocpcosts_summary USING gin (pod_labels);


--
-- Name: ocpcostsum_usage_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocpcostsum_usage_start_idx ON template0.reporting_ocpcosts_summary USING btree (usage_start);


--
-- Name: ocplblnitdly_node_labels; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocplblnitdly_node_labels ON template0.reporting_ocpnodelabellineitem_daily USING gin (node_labels);


--
-- Name: ocplblnitdly_usage_start; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX ocplblnitdly_usage_start ON template0.reporting_ocpnodelabellineitem_daily USING btree (usage_start);


--
-- Name: openshift_tags_value_key_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX openshift_tags_value_key_idx ON template0.reporting_ocptags_values USING btree (key);


--
-- Name: p_gcp_summary_instance_type_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_gcp_summary_instance_type_idx ON ONLY template0.reporting_gcpcostentrylineitem_daily_summary USING btree (instance_type);


--
-- Name: p_gcp_summary_project_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_gcp_summary_project_id_idx ON ONLY template0.reporting_gcpcostentrylineitem_daily_summary USING btree (project_id);


--
-- Name: p_gcp_summary_project_name_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_gcp_summary_project_name_idx ON ONLY template0.reporting_gcpcostentrylineitem_daily_summary USING btree (project_name);


--
-- Name: p_gcp_summary_service_alias_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_gcp_summary_service_alias_idx ON ONLY template0.reporting_gcpcostentrylineitem_daily_summary USING btree (service_alias);


--
-- Name: p_gcp_summary_service_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_gcp_summary_service_id_idx ON ONLY template0.reporting_gcpcostentrylineitem_daily_summary USING btree (service_id);


--
-- Name: p_gcp_summary_usage_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_gcp_summary_usage_start_idx ON ONLY template0.reporting_gcpcostentrylineitem_daily_summary USING btree (usage_start);


--
-- Name: p_gcp_tags_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_gcp_tags_idx ON ONLY template0.reporting_gcpcostentrylineitem_daily_summary USING gin (tags);


--
-- Name: p_ix_azurecstentrydlysumm_start; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_ix_azurecstentrydlysumm_start ON ONLY template0.reporting_azurecostentrylineitem_daily_summary USING btree (usage_start);


--
-- Name: p_pod_labels_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_pod_labels_idx ON ONLY template0.reporting_ocpusagelineitem_daily_summary USING gin (pod_labels);


--
-- Name: p_reporting_gcpcostentryline_cost_entry_bill_id_bf00a16b; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_reporting_gcpcostentryline_cost_entry_bill_id_bf00a16b ON ONLY template0.reporting_gcpcostentrylineitem_daily_summary USING btree (cost_entry_bill_id);


--
-- Name: p_summary_account_alias_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_summary_account_alias_idx ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING btree (account_alias_id);


--
-- Name: p_summary_data_source_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_summary_data_source_idx ON ONLY template0.reporting_ocpusagelineitem_daily_summary USING btree (data_source);


--
-- Name: p_summary_instance_type_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_summary_instance_type_idx ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING btree (instance_type);


--
-- Name: p_summary_namespace_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_summary_namespace_idx ON ONLY template0.reporting_ocpusagelineitem_daily_summary USING btree (namespace varchar_pattern_ops);


--
-- Name: p_summary_node_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_summary_node_idx ON ONLY template0.reporting_ocpusagelineitem_daily_summary USING btree (node varchar_pattern_ops);


--
-- Name: p_summary_ocp_usage_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_summary_ocp_usage_idx ON ONLY template0.reporting_ocpusagelineitem_daily_summary USING btree (usage_start);


--
-- Name: p_summary_product_code_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_summary_product_code_idx ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING btree (product_code);


--
-- Name: p_summary_product_family_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_summary_product_family_idx ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING btree (product_family);


--
-- Name: p_summary_usage_account_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_summary_usage_account_id_idx ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING btree (usage_account_id);


--
-- Name: p_summary_usage_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_summary_usage_start_idx ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING btree (usage_start);


--
-- Name: p_tags_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX p_tags_idx ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING gin (tags);


--
-- Name: partable_partition_parameters; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX partable_partition_parameters ON template0.partitioned_tables USING gin (partition_parameters);


--
-- Name: partable_partition_type; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX partable_partition_type ON template0.partitioned_tables USING btree (partition_type);


--
-- Name: partable_table; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX partable_table ON template0.partitioned_tables USING btree (schema_name, table_name);


--
-- Name: pod_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX pod_idx ON template0.reporting_ocpusagelineitem_daily USING btree (pod);


--
-- Name: presto_pk_delete_wrapper_log_tx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX presto_pk_delete_wrapper_log_tx ON template0.presto_pk_delete_wrapper_log USING btree (transaction_id, table_name);


--
-- Name: product_code_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX product_code_idx ON template0.reporting_awscostentrylineitem_daily USING btree (product_code);


--
-- Name: region_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX region_idx ON template0.reporting_awscostentryproduct USING btree (region);


--
-- Name: reporting_awsaccountalias_account_id_85724b8c_like; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awsaccountalias_account_id_85724b8c_like ON template0.reporting_awsaccountalias USING btree (account_id varchar_pattern_ops);


--
-- Name: reporting_awscostentry_bill_id_017f27a3; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentry_bill_id_017f27a3 ON template0.reporting_awscostentry USING btree (bill_id);


--
-- Name: reporting_awscostentrybill_provider_id_a08725b3; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrybill_provider_id_a08725b3 ON template0.reporting_awscostentrybill USING btree (provider_id);


--
-- Name: reporting_awscostentryline_account_alias_id_684d6c01; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentryline_account_alias_id_684d6c01 ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING btree (account_alias_id);


--
-- Name: reporting_awscostentryline_cost_entry_bill_id_54ece653; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentryline_cost_entry_bill_id_54ece653 ON template0.reporting_awscostentrylineitem_daily USING btree (cost_entry_bill_id);


--
-- Name: reporting_awscostentryline_cost_entry_bill_id_d7af1eb6; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentryline_cost_entry_bill_id_d7af1eb6 ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_awscostentryline_cost_entry_pricing_id_5a6a9b38; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentryline_cost_entry_pricing_id_5a6a9b38 ON template0.reporting_awscostentrylineitem_daily USING btree (cost_entry_pricing_id);


--
-- Name: reporting_awscostentryline_cost_entry_product_id_4d8ef2fd; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentryline_cost_entry_product_id_4d8ef2fd ON template0.reporting_awscostentrylineitem_daily USING btree (cost_entry_product_id);


--
-- Name: reporting_awscostentryline_cost_entry_reservation_id_13b1cb08; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentryline_cost_entry_reservation_id_13b1cb08 ON template0.reporting_awscostentrylineitem_daily USING btree (cost_entry_reservation_id);


--
-- Name: reporting_awscostentryline_cost_entry_reservation_id_9332b371; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentryline_cost_entry_reservation_id_9332b371 ON template0.reporting_awscostentrylineitem USING btree (cost_entry_reservation_id);


--
-- Name: reporting_awscostentryline_organizational_unit_id_01926b46; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentryline_organizational_unit_id_01926b46 ON ONLY template0.reporting_awscostentrylineitem_daily_summary USING btree (organizational_unit_id);


--
-- Name: reporting_awscostentrylineitem_cost_entry_bill_id_5ae74e09; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_cost_entry_bill_id_5ae74e09 ON template0.reporting_awscostentrylineitem USING btree (cost_entry_bill_id);


--
-- Name: reporting_awscostentrylineitem_cost_entry_id_4d1a7fc4; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_cost_entry_id_4d1a7fc4 ON template0.reporting_awscostentrylineitem USING btree (cost_entry_id);


--
-- Name: reporting_awscostentrylineitem_cost_entry_pricing_id_a654a7e3; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_cost_entry_pricing_id_a654a7e3 ON template0.reporting_awscostentrylineitem USING btree (cost_entry_pricing_id);


--
-- Name: reporting_awscostentrylineitem_cost_entry_product_id_29c80210; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_cost_entry_product_id_29c80210 ON template0.reporting_awscostentrylineitem USING btree (cost_entry_product_id);


--
-- Name: reporting_awscostentrylineitem_daily_organizational_unit_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_organizational_unit_id_idx ON template0.reporting_awscostentrylineitem_daily_summary_default USING btree (organizational_unit_id);


--
-- Name: reporting_awscostentrylineitem_daily_sum_cost_entry_bill_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_sum_cost_entry_bill_id_idx ON template0.reporting_awscostentrylineitem_daily_summary_default USING btree (cost_entry_bill_id);


--
-- Name: reporting_awscostentrylineitem_daily_summ_account_alias_id_idx1; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_summ_account_alias_id_idx1 ON template0.reporting_awscostentrylineitem_daily_summary_default USING btree (account_alias_id);


--
-- Name: reporting_awscostentrylineitem_daily_summa_account_alias_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_summa_account_alias_id_idx ON template0.reporting_awscostentrylineitem_daily_summary_default USING btree (account_alias_id);


--
-- Name: reporting_awscostentrylineitem_daily_summa_usage_account_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_summa_usage_account_id_idx ON template0.reporting_awscostentrylineitem_daily_summary_default USING btree (usage_account_id);


--
-- Name: reporting_awscostentrylineitem_daily_summary__instance_type_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_summary__instance_type_idx ON template0.reporting_awscostentrylineitem_daily_summary_default USING btree (instance_type);


--
-- Name: reporting_awscostentrylineitem_daily_summary_d_product_code_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_summary_d_product_code_idx ON template0.reporting_awscostentrylineitem_daily_summary_default USING btree (product_code);


--
-- Name: reporting_awscostentrylineitem_daily_summary_de_usage_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_summary_de_usage_start_idx ON template0.reporting_awscostentrylineitem_daily_summary_default USING btree (usage_start);


--
-- Name: reporting_awscostentrylineitem_daily_summary_default_tags_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_summary_default_tags_idx ON template0.reporting_awscostentrylineitem_daily_summary_default USING gin (tags);


--
-- Name: reporting_awscostentrylineitem_daily_summary_default_upper_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_summary_default_upper_idx ON template0.reporting_awscostentrylineitem_daily_summary_default USING gin (upper((product_family)::text) public.gin_trgm_ops);


--
-- Name: reporting_awscostentrylineitem_daily_summary_default_upper_idx1; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_summary_default_upper_idx1 ON template0.reporting_awscostentrylineitem_daily_summary_default USING gin (upper((product_family)::text) public.gin_trgm_ops);


--
-- Name: reporting_awscostentrylineitem_daily_summary_product_family_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentrylineitem_daily_summary_product_family_idx ON template0.reporting_awscostentrylineitem_daily_summary_default USING btree (product_family);


--
-- Name: reporting_awscostentryreservation_reservation_arn_e387aa5b_like; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awscostentryreservation_reservation_arn_e387aa5b_like ON template0.reporting_awscostentryreservation USING btree (reservation_arn text_pattern_ops);


--
-- Name: reporting_awsenabledtagkeys_key_8c2841c2_like; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awsenabledtagkeys_key_8c2841c2_like ON template0.reporting_awsenabledtagkeys USING btree (key varchar_pattern_ops);


--
-- Name: reporting_awsorganizationalunit_account_alias_id_7bd6273b; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awsorganizationalunit_account_alias_id_7bd6273b ON template0.reporting_awsorganizationalunit USING btree (account_alias_id);


--
-- Name: reporting_awsorganizationalunit_provider_id_6e91f0ae; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awsorganizationalunit_provider_id_6e91f0ae ON template0.reporting_awsorganizationalunit USING btree (provider_id);


--
-- Name: reporting_awstags_summary_account_alias_id_8a49f381; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awstags_summary_account_alias_id_8a49f381 ON template0.reporting_awstags_summary USING btree (account_alias_id);


--
-- Name: reporting_awstags_summary_cost_entry_bill_id_c9c45ad6; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_awstags_summary_cost_entry_bill_id_c9c45ad6 ON template0.reporting_awstags_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_azurecostentrybill_provider_id_5b7738d5; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azurecostentrybill_provider_id_5b7738d5 ON template0.reporting_azurecostentrybill USING btree (provider_id);


--
-- Name: reporting_azurecostentryli_cost_entry_bill_id_7898bce4; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azurecostentryli_cost_entry_bill_id_7898bce4 ON template0.reporting_azurecostentrylineitem_daily USING btree (cost_entry_bill_id);


--
-- Name: reporting_azurecostentryli_cost_entry_bill_id_e7c3e625; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azurecostentryli_cost_entry_bill_id_e7c3e625 ON ONLY template0.reporting_azurecostentrylineitem_daily_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_azurecostentryli_cost_entry_product_id_b84c188a; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azurecostentryli_cost_entry_product_id_b84c188a ON template0.reporting_azurecostentrylineitem_daily USING btree (cost_entry_product_id);


--
-- Name: reporting_azurecostentryli_meter_id_799dc028; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azurecostentryli_meter_id_799dc028 ON ONLY template0.reporting_azurecostentrylineitem_daily_summary USING btree (meter_id);


--
-- Name: reporting_azurecostentrylineitem_daily_meter_id_292c06f8; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azurecostentrylineitem_daily_meter_id_292c06f8 ON template0.reporting_azurecostentrylineitem_daily USING btree (meter_id);


--
-- Name: reporting_azurecostentrylineitem_daily_s_cost_entry_bill_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azurecostentrylineitem_daily_s_cost_entry_bill_id_idx ON template0.reporting_azurecostentrylineitem_daily_summary_default USING btree (cost_entry_bill_id);


--
-- Name: reporting_azurecostentrylineitem_daily_summary__usage_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azurecostentrylineitem_daily_summary__usage_start_idx ON template0.reporting_azurecostentrylineitem_daily_summary_default USING btree (usage_start);


--
-- Name: reporting_azurecostentrylineitem_daily_summary_def_meter_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azurecostentrylineitem_daily_summary_def_meter_id_idx ON template0.reporting_azurecostentrylineitem_daily_summary_default USING btree (meter_id);


--
-- Name: reporting_azurecostentrylineitem_daily_summary_defaul_upper_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azurecostentrylineitem_daily_summary_defaul_upper_idx ON template0.reporting_azurecostentrylineitem_daily_summary_default USING gin (upper(service_name) public.gin_trgm_ops);


--
-- Name: reporting_azurecostentryproductservice_provider_id_2072db59; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azurecostentryproductservice_provider_id_2072db59 ON template0.reporting_azurecostentryproductservice USING btree (provider_id);


--
-- Name: reporting_azureenabledtagkeys_key_a00bc136_like; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azureenabledtagkeys_key_a00bc136_like ON template0.reporting_azureenabledtagkeys USING btree (key varchar_pattern_ops);


--
-- Name: reporting_azuremeter_provider_id_d6bb7273; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azuremeter_provider_id_d6bb7273 ON template0.reporting_azuremeter USING btree (provider_id);


--
-- Name: reporting_azuretags_summary_cost_entry_bill_id_cb69e67a; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_azuretags_summary_cost_entry_bill_id_cb69e67a ON template0.reporting_azuretags_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_gcpcostentrybill_provider_id_4da1742f; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrybill_provider_id_4da1742f ON template0.reporting_gcpcostentrybill USING btree (provider_id);


--
-- Name: reporting_gcpcostentryline_cost_entry_bill_id_a3272999; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentryline_cost_entry_bill_id_a3272999 ON template0.reporting_gcpcostentrylineitem_daily USING btree (cost_entry_bill_id);


--
-- Name: reporting_gcpcostentryline_cost_entry_product_id_bce5f583; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentryline_cost_entry_product_id_bce5f583 ON template0.reporting_gcpcostentrylineitem_daily USING btree (cost_entry_product_id);


--
-- Name: reporting_gcpcostentrylineitem_cost_entry_bill_id_7a8f16fd; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_cost_entry_bill_id_7a8f16fd ON template0.reporting_gcpcostentrylineitem USING btree (cost_entry_bill_id);


--
-- Name: reporting_gcpcostentrylineitem_cost_entry_product_id_cec870b8; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_cost_entry_product_id_cec870b8 ON template0.reporting_gcpcostentrylineitem USING btree (cost_entry_product_id);


--
-- Name: reporting_gcpcostentrylineitem_daily_project_id_18365d99; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_daily_project_id_18365d99 ON template0.reporting_gcpcostentrylineitem_daily USING btree (project_id);


--
-- Name: reporting_gcpcostentrylineitem_daily_sum_cost_entry_bill_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_daily_sum_cost_entry_bill_id_idx ON template0.reporting_gcpcostentrylineitem_daily_summary_default USING btree (cost_entry_bill_id);


--
-- Name: reporting_gcpcostentrylineitem_daily_summary__instance_type_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_daily_summary__instance_type_idx ON template0.reporting_gcpcostentrylineitem_daily_summary_default USING btree (instance_type);


--
-- Name: reporting_gcpcostentrylineitem_daily_summary__service_alias_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_daily_summary__service_alias_idx ON template0.reporting_gcpcostentrylineitem_daily_summary_default USING btree (service_alias);


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_d_project_name_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_daily_summary_d_project_name_idx ON template0.reporting_gcpcostentrylineitem_daily_summary_default USING btree (project_name);


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_de_usage_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_daily_summary_de_usage_start_idx ON template0.reporting_gcpcostentrylineitem_daily_summary_default USING btree (usage_start);


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_def_project_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_daily_summary_def_project_id_idx ON template0.reporting_gcpcostentrylineitem_daily_summary_default USING btree (project_id);


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_def_service_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_daily_summary_def_service_id_idx ON template0.reporting_gcpcostentrylineitem_daily_summary_default USING btree (service_id);


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_default_tags_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_daily_summary_default_tags_idx ON template0.reporting_gcpcostentrylineitem_daily_summary_default USING gin (tags);


--
-- Name: reporting_gcpcostentrylineitem_project_id_bf066e6e; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpcostentrylineitem_project_id_bf066e6e ON template0.reporting_gcpcostentrylineitem USING btree (project_id);


--
-- Name: reporting_gcpenabledtagkeys_key_0e50e656_like; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpenabledtagkeys_key_0e50e656_like ON template0.reporting_gcpenabledtagkeys USING btree (key varchar_pattern_ops);


--
-- Name: reporting_gcpproject_project_id_77600c9d_like; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcpproject_project_id_77600c9d_like ON template0.reporting_gcpproject USING btree (project_id varchar_pattern_ops);


--
-- Name: reporting_gcptags_summary_cost_entry_bill_id_e442ff66; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_gcptags_summary_cost_entry_bill_id_e442ff66 ON template0.reporting_gcptags_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_ocpawscostlineit_account_alias_id_d12902c6; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpawscostlineit_account_alias_id_d12902c6 ON template0.reporting_ocpawscostlineitem_project_daily_summary USING btree (account_alias_id);


--
-- Name: reporting_ocpawscostlineit_account_alias_id_f19d2883; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpawscostlineit_account_alias_id_f19d2883 ON template0.reporting_ocpawscostlineitem_daily_summary USING btree (account_alias_id);


--
-- Name: reporting_ocpawscostlineit_cost_entry_bill_id_2740da80; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpawscostlineit_cost_entry_bill_id_2740da80 ON template0.reporting_ocpawscostlineitem_project_daily_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_ocpawscostlineit_cost_entry_bill_id_2a473151; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpawscostlineit_cost_entry_bill_id_2a473151 ON template0.reporting_ocpawscostlineitem_daily_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_ocpawscostlineit_report_period_id_150c5620; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpawscostlineit_report_period_id_150c5620 ON template0.reporting_ocpawscostlineitem_daily_summary USING btree (report_period_id);


--
-- Name: reporting_ocpawscostlineit_report_period_id_3f8d2da5; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpawscostlineit_report_period_id_3f8d2da5 ON template0.reporting_ocpawscostlineitem_project_daily_summary USING btree (report_period_id);


--
-- Name: reporting_ocpawstags_summary_account_alias_id_f3d8c2e0; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpawstags_summary_account_alias_id_f3d8c2e0 ON template0.reporting_ocpawstags_summary USING btree (account_alias_id);


--
-- Name: reporting_ocpawstags_summary_cost_entry_bill_id_9fe9ad45; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpawstags_summary_cost_entry_bill_id_9fe9ad45 ON template0.reporting_ocpawstags_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_ocpawstags_summary_report_period_id_54cc3cc4; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpawstags_summary_report_period_id_54cc3cc4 ON template0.reporting_ocpawstags_summary USING btree (report_period_id);


--
-- Name: reporting_ocpazurecostline_cost_entry_bill_id_442560ac; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpazurecostline_cost_entry_bill_id_442560ac ON template0.reporting_ocpazurecostlineitem_project_daily_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_ocpazurecostline_cost_entry_bill_id_b12d05bd; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpazurecostline_cost_entry_bill_id_b12d05bd ON template0.reporting_ocpazurecostlineitem_daily_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_ocpazurecostline_report_period_id_145b540e; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpazurecostline_report_period_id_145b540e ON template0.reporting_ocpazurecostlineitem_project_daily_summary USING btree (report_period_id);


--
-- Name: reporting_ocpazurecostline_report_period_id_e5bbf81f; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpazurecostline_report_period_id_e5bbf81f ON template0.reporting_ocpazurecostlineitem_daily_summary USING btree (report_period_id);


--
-- Name: reporting_ocpazuretags_summary_cost_entry_bill_id_c84d2dc3; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpazuretags_summary_cost_entry_bill_id_c84d2dc3 ON template0.reporting_ocpazuretags_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_ocpazuretags_summary_report_period_id_19a6abdb; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpazuretags_summary_report_period_id_19a6abdb ON template0.reporting_ocpazuretags_summary USING btree (report_period_id);


--
-- Name: reporting_ocpcosts_summary_report_period_id_e53cdbb2; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpcosts_summary_report_period_id_e53cdbb2 ON template0.reporting_ocpcosts_summary USING btree (report_period_id);


--
-- Name: reporting_ocpenabledtagkeys_key_c3a4025b_like; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpenabledtagkeys_key_c3a4025b_like ON template0.reporting_ocpenabledtagkeys USING btree (key varchar_pattern_ops);


--
-- Name: reporting_ocpnamespacelabellineitem_report_id_16489a95; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpnamespacelabellineitem_report_id_16489a95 ON template0.reporting_ocpnamespacelabellineitem USING btree (report_id);


--
-- Name: reporting_ocpnamespacelabellineitem_report_period_id_704a722f; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpnamespacelabellineitem_report_period_id_704a722f ON template0.reporting_ocpnamespacelabellineitem USING btree (report_period_id);


--
-- Name: reporting_ocpnodelabellineitem_daily_report_period_id_de6c8f1f; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpnodelabellineitem_daily_report_period_id_de6c8f1f ON template0.reporting_ocpnodelabellineitem_daily USING btree (report_period_id);


--
-- Name: reporting_ocpnodelabellineitem_report_id_5e2f992a; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpnodelabellineitem_report_id_5e2f992a ON template0.reporting_ocpnodelabellineitem USING btree (report_id);


--
-- Name: reporting_ocpnodelabellineitem_report_period_id_d3fcf22e; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpnodelabellineitem_report_period_id_d3fcf22e ON template0.reporting_ocpnodelabellineitem USING btree (report_period_id);


--
-- Name: reporting_ocpstoragelineitem_daily_report_period_id_ad325037; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpstoragelineitem_daily_report_period_id_ad325037 ON template0.reporting_ocpstoragelineitem_daily USING btree (report_period_id);


--
-- Name: reporting_ocpstoragelineitem_report_id_6ff71ea6; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpstoragelineitem_report_id_6ff71ea6 ON template0.reporting_ocpstoragelineitem USING btree (report_id);


--
-- Name: reporting_ocpstoragelineitem_report_period_id_6d730b12; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpstoragelineitem_report_period_id_6d730b12 ON template0.reporting_ocpstoragelineitem USING btree (report_period_id);


--
-- Name: reporting_ocpstoragevolume_report_period_id_53b5a3b8; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpstoragevolume_report_period_id_53b5a3b8 ON template0.reporting_ocpstoragevolumelabel_summary USING btree (report_period_id);


--
-- Name: reporting_ocpusagelineitem_daily_report_period_id_d5388c41; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_daily_report_period_id_d5388c41 ON template0.reporting_ocpusagelineitem_daily USING btree (report_period_id);


--
-- Name: reporting_ocpusagelineitem_report_period_id_fc68baea; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_report_period_id_fc68baea ON ONLY template0.reporting_ocpusagelineitem_daily_summary USING btree (report_period_id);


--
-- Name: reporting_ocpusagelineitem_daily_summary_d_report_period_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_daily_summary_d_report_period_id_idx ON template0.reporting_ocpusagelineitem_daily_summary_default USING btree (report_period_id);


--
-- Name: reporting_ocpusagelineitem_daily_summary_defaul_data_source_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_daily_summary_defaul_data_source_idx ON template0.reporting_ocpusagelineitem_daily_summary_default USING btree (data_source);


--
-- Name: reporting_ocpusagelineitem_daily_summary_defaul_usage_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_daily_summary_defaul_usage_start_idx ON template0.reporting_ocpusagelineitem_daily_summary_default USING btree (usage_start);


--
-- Name: reporting_ocpusagelineitem_daily_summary_default_namespace_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_daily_summary_default_namespace_idx ON template0.reporting_ocpusagelineitem_daily_summary_default USING btree (namespace varchar_pattern_ops);


--
-- Name: reporting_ocpusagelineitem_daily_summary_default_node_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_daily_summary_default_node_idx ON template0.reporting_ocpusagelineitem_daily_summary_default USING btree (node varchar_pattern_ops);


--
-- Name: reporting_ocpusagelineitem_daily_summary_default_pod_labels_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_daily_summary_default_pod_labels_idx ON template0.reporting_ocpusagelineitem_daily_summary_default USING gin (pod_labels);


--
-- Name: reporting_ocpusagelineitem_daily_summary_default_upper_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_daily_summary_default_upper_idx ON template0.reporting_ocpusagelineitem_daily_summary_default USING gin (upper((namespace)::text) public.gin_trgm_ops);


--
-- Name: reporting_ocpusagelineitem_daily_summary_default_upper_idx1; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_daily_summary_default_upper_idx1 ON template0.reporting_ocpusagelineitem_daily_summary_default USING gin (upper((node)::text) public.gin_trgm_ops);


--
-- Name: reporting_ocpusagelineitem_report_id_32a973b0; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_report_id_32a973b0 ON template0.reporting_ocpusagelineitem USING btree (report_id);


--
-- Name: reporting_ocpusagelineitem_report_period_id_be7fa5ad; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagelineitem_report_period_id_be7fa5ad ON template0.reporting_ocpusagelineitem USING btree (report_period_id);


--
-- Name: reporting_ocpusagepodlabel_summary_report_period_id_fa250ee5; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagepodlabel_summary_report_period_id_fa250ee5 ON template0.reporting_ocpusagepodlabel_summary USING btree (report_period_id);


--
-- Name: reporting_ocpusagereport_report_period_id_477508c6; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagereport_report_period_id_477508c6 ON template0.reporting_ocpusagereport USING btree (report_period_id);


--
-- Name: reporting_ocpusagereportperiod_provider_id_7348fe66; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX reporting_ocpusagereportperiod_provider_id_7348fe66 ON template0.reporting_ocpusagereportperiod USING btree (provider_id);


--
-- Name: resource_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX resource_id_idx ON template0.reporting_awscostentrylineitem_daily USING btree (resource_id);


--
-- Name: source_type_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX source_type_idx ON template0.cost_model USING btree (source_type);


--
-- Name: updated_timestamp_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX updated_timestamp_idx ON template0.cost_model USING btree (updated_timestamp);


--
-- Name: usage_account_id_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX usage_account_id_idx ON template0.reporting_awscostentrylineitem_daily USING btree (usage_account_id);


--
-- Name: usage_start_idx; Type: INDEX; Schema: template0; Owner: table_owner
--

CREATE INDEX usage_start_idx ON template0.reporting_awscostentrylineitem_daily USING btree (usage_start);


--
-- Name: reporting_awscostentrylineitem_daily_organizational_unit_id_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.reporting_awscostentryline_organizational_unit_id_01926b46 ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_organizational_unit_id_idx;


--
-- Name: reporting_awscostentrylineitem_daily_sum_cost_entry_bill_id_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.reporting_awscostentryline_cost_entry_bill_id_d7af1eb6 ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_sum_cost_entry_bill_id_idx;


--
-- Name: reporting_awscostentrylineitem_daily_summ_account_alias_id_idx1; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.reporting_awscostentryline_account_alias_id_684d6c01 ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summ_account_alias_id_idx1;


--
-- Name: reporting_awscostentrylineitem_daily_summa_account_alias_id_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_summary_account_alias_idx ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summa_account_alias_id_idx;


--
-- Name: reporting_awscostentrylineitem_daily_summa_usage_account_id_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_summary_usage_account_id_idx ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summa_usage_account_id_idx;


--
-- Name: reporting_awscostentrylineitem_daily_summary__instance_type_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_summary_instance_type_idx ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summary__instance_type_idx;


--
-- Name: reporting_awscostentrylineitem_daily_summary_d_product_code_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_summary_product_code_idx ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summary_d_product_code_idx;


--
-- Name: reporting_awscostentrylineitem_daily_summary_de_usage_start_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_summary_usage_start_idx ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summary_de_usage_start_idx;


--
-- Name: reporting_awscostentrylineitem_daily_summary_default_pkey; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.reporting_awscostentrylineitem_daily_summary_pkey ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summary_default_pkey;


--
-- Name: reporting_awscostentrylineitem_daily_summary_default_tags_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_tags_idx ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summary_default_tags_idx;


--
-- Name: reporting_awscostentrylineitem_daily_summary_default_upper_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.aws_summ_usage_pfam_ilike ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summary_default_upper_idx;


--
-- Name: reporting_awscostentrylineitem_daily_summary_default_upper_idx1; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.aws_summ_usage_pcode_ilike ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summary_default_upper_idx1;


--
-- Name: reporting_awscostentrylineitem_daily_summary_product_family_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_summary_product_family_idx ATTACH PARTITION template0.reporting_awscostentrylineitem_daily_summary_product_family_idx;


--
-- Name: reporting_azurecostentrylineitem_daily_s_cost_entry_bill_id_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.reporting_azurecostentryli_cost_entry_bill_id_e7c3e625 ATTACH PARTITION template0.reporting_azurecostentrylineitem_daily_s_cost_entry_bill_id_idx;


--
-- Name: reporting_azurecostentrylineitem_daily_summary__usage_start_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_ix_azurecstentrydlysumm_start ATTACH PARTITION template0.reporting_azurecostentrylineitem_daily_summary__usage_start_idx;


--
-- Name: reporting_azurecostentrylineitem_daily_summary_def_meter_id_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.reporting_azurecostentryli_meter_id_799dc028 ATTACH PARTITION template0.reporting_azurecostentrylineitem_daily_summary_def_meter_id_idx;


--
-- Name: reporting_azurecostentrylineitem_daily_summary_defaul_upper_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.ix_azure_costentrydlysumm_service_name ATTACH PARTITION template0.reporting_azurecostentrylineitem_daily_summary_defaul_upper_idx;


--
-- Name: reporting_azurecostentrylineitem_daily_summary_default_pkey; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.reporting_azurecostentrylineitem_daily_summary_pkey ATTACH PARTITION template0.reporting_azurecostentrylineitem_daily_summary_default_pkey;


--
-- Name: reporting_gcpcostentrylineitem_daily_sum_cost_entry_bill_id_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_reporting_gcpcostentryline_cost_entry_bill_id_bf00a16b ATTACH PARTITION template0.reporting_gcpcostentrylineitem_daily_sum_cost_entry_bill_id_idx;


--
-- Name: reporting_gcpcostentrylineitem_daily_summary__instance_type_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_gcp_summary_instance_type_idx ATTACH PARTITION template0.reporting_gcpcostentrylineitem_daily_summary__instance_type_idx;


--
-- Name: reporting_gcpcostentrylineitem_daily_summary__service_alias_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_gcp_summary_service_alias_idx ATTACH PARTITION template0.reporting_gcpcostentrylineitem_daily_summary__service_alias_idx;


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_d_project_name_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_gcp_summary_project_name_idx ATTACH PARTITION template0.reporting_gcpcostentrylineitem_daily_summary_d_project_name_idx;


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_de_usage_start_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_gcp_summary_usage_start_idx ATTACH PARTITION template0.reporting_gcpcostentrylineitem_daily_summary_de_usage_start_idx;


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_def_project_id_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_gcp_summary_project_id_idx ATTACH PARTITION template0.reporting_gcpcostentrylineitem_daily_summary_def_project_id_idx;


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_def_service_id_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_gcp_summary_service_id_idx ATTACH PARTITION template0.reporting_gcpcostentrylineitem_daily_summary_def_service_id_idx;


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_default_pkey; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_reporting_gcpcostentrylineitem_daily_summary_pkey ATTACH PARTITION template0.reporting_gcpcostentrylineitem_daily_summary_default_pkey;


--
-- Name: reporting_gcpcostentrylineitem_daily_summary_default_tags_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_gcp_tags_idx ATTACH PARTITION template0.reporting_gcpcostentrylineitem_daily_summary_default_tags_idx;


--
-- Name: reporting_ocpusagelineitem_daily_summary_d_report_period_id_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.reporting_ocpusagelineitem_report_period_id_fc68baea ATTACH PARTITION template0.reporting_ocpusagelineitem_daily_summary_d_report_period_id_idx;


--
-- Name: reporting_ocpusagelineitem_daily_summary_defaul_data_source_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_summary_data_source_idx ATTACH PARTITION template0.reporting_ocpusagelineitem_daily_summary_defaul_data_source_idx;


--
-- Name: reporting_ocpusagelineitem_daily_summary_defaul_usage_start_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_summary_ocp_usage_idx ATTACH PARTITION template0.reporting_ocpusagelineitem_daily_summary_defaul_usage_start_idx;


--
-- Name: reporting_ocpusagelineitem_daily_summary_default_namespace_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_summary_namespace_idx ATTACH PARTITION template0.reporting_ocpusagelineitem_daily_summary_default_namespace_idx;


--
-- Name: reporting_ocpusagelineitem_daily_summary_default_node_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_summary_node_idx ATTACH PARTITION template0.reporting_ocpusagelineitem_daily_summary_default_node_idx;


--
-- Name: reporting_ocpusagelineitem_daily_summary_default_pkey; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.reporting_ocpusagelineitem_daily_summary_pkey ATTACH PARTITION template0.reporting_ocpusagelineitem_daily_summary_default_pkey;


--
-- Name: reporting_ocpusagelineitem_daily_summary_default_pod_labels_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.p_pod_labels_idx ATTACH PARTITION template0.reporting_ocpusagelineitem_daily_summary_default_pod_labels_idx;


--
-- Name: reporting_ocpusagelineitem_daily_summary_default_upper_idx; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.ocp_summary_namespace_like_idx ATTACH PARTITION template0.reporting_ocpusagelineitem_daily_summary_default_upper_idx;


--
-- Name: reporting_ocpusagelineitem_daily_summary_default_upper_idx1; Type: INDEX ATTACH; Schema: template0; Owner: -
--

ALTER INDEX template0.ocp_summary_node_like_idx ATTACH PARTITION template0.reporting_ocpusagelineitem_daily_summary_default_upper_idx1;


--
-- Name: cost_model cost_model_audit; Type: TRIGGER; Schema: template0; Owner: table_owner
--

CREATE TRIGGER cost_model_audit AFTER INSERT OR DELETE OR UPDATE ON template0.cost_model FOR EACH ROW EXECUTE FUNCTION template0.process_cost_model_audit();


--
-- Name: partitioned_tables tr_attach_date_range_partition; Type: TRIGGER; Schema: template0; Owner: table_owner
--

CREATE TRIGGER tr_attach_date_range_partition AFTER UPDATE OF active ON template0.partitioned_tables FOR EACH ROW EXECUTE FUNCTION public.trfn_attach_date_range_partition();


--
-- Name: partitioned_tables tr_manage_date_range_partition; Type: TRIGGER; Schema: template0; Owner: table_owner
--

CREATE TRIGGER tr_manage_date_range_partition AFTER INSERT OR DELETE OR UPDATE OF partition_parameters ON template0.partitioned_tables FOR EACH ROW EXECUTE FUNCTION public.trfn_manage_date_range_partition();


--
-- Name: presto_delete_wrapper_log tr_presto_before_insert; Type: TRIGGER; Schema: template0; Owner: table_owner
--

CREATE TRIGGER tr_presto_before_insert BEFORE INSERT ON template0.presto_delete_wrapper_log FOR EACH ROW EXECUTE FUNCTION public.tr_presto_delete_wrapper_log_action();


--
-- Name: cost_model_map cost_model_map_cost_model_id_3c67db61_fk_cost_model_uuid; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.cost_model_map
    ADD CONSTRAINT cost_model_map_cost_model_id_3c67db61_fk_cost_model_uuid FOREIGN KEY (cost_model_id) REFERENCES template0.cost_model(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily_summary p_reporting_awscostent_account_alias_id_684d6c01_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE template0.reporting_awscostentrylineitem_daily_summary
    ADD CONSTRAINT p_reporting_awscostent_account_alias_id_684d6c01_fk_reporting FOREIGN KEY (account_alias_id) REFERENCES template0.reporting_awsaccountalias(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily_summary p_reporting_awscostent_cost_entry_bill_id_d7af1eb6_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE template0.reporting_awscostentrylineitem_daily_summary
    ADD CONSTRAINT p_reporting_awscostent_cost_entry_bill_id_d7af1eb6_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily_summary p_reporting_awscostent_organizational_unit__01926b46_fk_reporti; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE template0.reporting_awscostentrylineitem_daily_summary
    ADD CONSTRAINT p_reporting_awscostent_organizational_unit__01926b46_fk_reporti FOREIGN KEY (organizational_unit_id) REFERENCES template0.reporting_awsorganizationalunit(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_azurecostentrylineitem_daily_summary p_reporting_azurecoste_cost_entry_bill_id_e7c3e625_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE template0.reporting_azurecostentrylineitem_daily_summary
    ADD CONSTRAINT p_reporting_azurecoste_cost_entry_bill_id_e7c3e625_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_azurecostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_azurecostentrylineitem_daily_summary p_reporting_azurecoste_meter_id_799dc028_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE template0.reporting_azurecostentrylineitem_daily_summary
    ADD CONSTRAINT p_reporting_azurecoste_meter_id_799dc028_fk_reporting FOREIGN KEY (meter_id) REFERENCES template0.reporting_azuremeter(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_gcpcostentrylineitem_daily_summary p_reporting_gcpcostent_cost_entry_bill_id_bf00a16b_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE template0.reporting_gcpcostentrylineitem_daily_summary
    ADD CONSTRAINT p_reporting_gcpcostent_cost_entry_bill_id_bf00a16b_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_gcpcostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpusagelineitem_daily_summary p_reporting_ocpusageli_report_period_id_fc68baea_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE template0.reporting_ocpusagelineitem_daily_summary
    ADD CONSTRAINT p_reporting_ocpusageli_report_period_id_fc68baea_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentry reporting_awscostent_bill_id_017f27a3_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentry
    ADD CONSTRAINT reporting_awscostent_bill_id_017f27a3_fk_reporting FOREIGN KEY (bill_id) REFERENCES template0.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily reporting_awscostent_cost_entry_bill_id_54ece653_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem_daily
    ADD CONSTRAINT reporting_awscostent_cost_entry_bill_id_54ece653_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem reporting_awscostent_cost_entry_bill_id_5ae74e09_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostent_cost_entry_bill_id_5ae74e09_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem reporting_awscostent_cost_entry_id_4d1a7fc4_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostent_cost_entry_id_4d1a7fc4_fk_reporting FOREIGN KEY (cost_entry_id) REFERENCES template0.reporting_awscostentry(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily reporting_awscostent_cost_entry_pricing_i_5a6a9b38_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem_daily
    ADD CONSTRAINT reporting_awscostent_cost_entry_pricing_i_5a6a9b38_fk_reporting FOREIGN KEY (cost_entry_pricing_id) REFERENCES template0.reporting_awscostentrypricing(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem reporting_awscostent_cost_entry_pricing_i_a654a7e3_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostent_cost_entry_pricing_i_a654a7e3_fk_reporting FOREIGN KEY (cost_entry_pricing_id) REFERENCES template0.reporting_awscostentrypricing(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem reporting_awscostent_cost_entry_product_i_29c80210_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostent_cost_entry_product_i_29c80210_fk_reporting FOREIGN KEY (cost_entry_product_id) REFERENCES template0.reporting_awscostentryproduct(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily reporting_awscostent_cost_entry_product_i_4d8ef2fd_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem_daily
    ADD CONSTRAINT reporting_awscostent_cost_entry_product_i_4d8ef2fd_fk_reporting FOREIGN KEY (cost_entry_product_id) REFERENCES template0.reporting_awscostentryproduct(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily reporting_awscostent_cost_entry_reservati_13b1cb08_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem_daily
    ADD CONSTRAINT reporting_awscostent_cost_entry_reservati_13b1cb08_fk_reporting FOREIGN KEY (cost_entry_reservation_id) REFERENCES template0.reporting_awscostentryreservation(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem reporting_awscostent_cost_entry_reservati_9332b371_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostent_cost_entry_reservati_9332b371_fk_reporting FOREIGN KEY (cost_entry_reservation_id) REFERENCES template0.reporting_awscostentryreservation(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrybill reporting_awscostent_provider_id_a08725b3_fk_api_provi; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awscostentrybill
    ADD CONSTRAINT reporting_awscostent_provider_id_a08725b3_fk_api_provi FOREIGN KEY (provider_id) REFERENCES public.api_provider(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awsorganizationalunit reporting_awsorganiz_account_alias_id_7bd6273b_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awsorganizationalunit
    ADD CONSTRAINT reporting_awsorganiz_account_alias_id_7bd6273b_fk_reporting FOREIGN KEY (account_alias_id) REFERENCES template0.reporting_awsaccountalias(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awsorganizationalunit reporting_awsorganiz_provider_id_6e91f0ae_fk_api_provi; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awsorganizationalunit
    ADD CONSTRAINT reporting_awsorganiz_provider_id_6e91f0ae_fk_api_provi FOREIGN KEY (provider_id) REFERENCES public.api_provider(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awstags_summary reporting_awstags_su_account_alias_id_8a49f381_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awstags_summary
    ADD CONSTRAINT reporting_awstags_su_account_alias_id_8a49f381_fk_reporting FOREIGN KEY (account_alias_id) REFERENCES template0.reporting_awsaccountalias(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awstags_summary reporting_awstags_su_cost_entry_bill_id_c9c45ad6_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_awstags_summary
    ADD CONSTRAINT reporting_awstags_su_cost_entry_bill_id_c9c45ad6_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_azurecostentrylineitem_daily reporting_azurecoste_cost_entry_bill_id_7898bce4_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentrylineitem_daily
    ADD CONSTRAINT reporting_azurecoste_cost_entry_bill_id_7898bce4_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_azurecostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_azurecostentrylineitem_daily reporting_azurecoste_cost_entry_product_i_b84c188a_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentrylineitem_daily
    ADD CONSTRAINT reporting_azurecoste_cost_entry_product_i_b84c188a_fk_reporting FOREIGN KEY (cost_entry_product_id) REFERENCES template0.reporting_azurecostentryproductservice(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_azurecostentrylineitem_daily reporting_azurecoste_meter_id_292c06f8_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentrylineitem_daily
    ADD CONSTRAINT reporting_azurecoste_meter_id_292c06f8_fk_reporting FOREIGN KEY (meter_id) REFERENCES template0.reporting_azuremeter(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_azurecostentryproductservice reporting_azurecoste_provider_id_2072db59_fk_api_provi; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentryproductservice
    ADD CONSTRAINT reporting_azurecoste_provider_id_2072db59_fk_api_provi FOREIGN KEY (provider_id) REFERENCES public.api_provider(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_azurecostentrybill reporting_azurecoste_provider_id_5b7738d5_fk_api_provi; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azurecostentrybill
    ADD CONSTRAINT reporting_azurecoste_provider_id_5b7738d5_fk_api_provi FOREIGN KEY (provider_id) REFERENCES public.api_provider(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_azuremeter reporting_azuremeter_provider_id_d6bb7273_fk_api_provider_uuid; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azuremeter
    ADD CONSTRAINT reporting_azuremeter_provider_id_d6bb7273_fk_api_provider_uuid FOREIGN KEY (provider_id) REFERENCES public.api_provider(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_azuretags_summary reporting_azuretags__cost_entry_bill_id_cb69e67a_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_azuretags_summary
    ADD CONSTRAINT reporting_azuretags__cost_entry_bill_id_cb69e67a_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_azurecostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_gcpcostentrylineitem reporting_gcpcostent_cost_entry_bill_id_7a8f16fd_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem
    ADD CONSTRAINT reporting_gcpcostent_cost_entry_bill_id_7a8f16fd_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_gcpcostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_gcpcostentrylineitem_daily reporting_gcpcostent_cost_entry_bill_id_a3272999_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem_daily
    ADD CONSTRAINT reporting_gcpcostent_cost_entry_bill_id_a3272999_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_gcpcostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_gcpcostentrylineitem_daily reporting_gcpcostent_cost_entry_product_i_bce5f583_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem_daily
    ADD CONSTRAINT reporting_gcpcostent_cost_entry_product_i_bce5f583_fk_reporting FOREIGN KEY (cost_entry_product_id) REFERENCES template0.reporting_gcpcostentryproductservice(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_gcpcostentrylineitem reporting_gcpcostent_cost_entry_product_i_cec870b8_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem
    ADD CONSTRAINT reporting_gcpcostent_cost_entry_product_i_cec870b8_fk_reporting FOREIGN KEY (cost_entry_product_id) REFERENCES template0.reporting_gcpcostentryproductservice(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_gcpcostentrylineitem_daily reporting_gcpcostent_project_id_18365d99_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem_daily
    ADD CONSTRAINT reporting_gcpcostent_project_id_18365d99_fk_reporting FOREIGN KEY (project_id) REFERENCES template0.reporting_gcpproject(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_gcpcostentrylineitem reporting_gcpcostent_project_id_bf066e6e_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrylineitem
    ADD CONSTRAINT reporting_gcpcostent_project_id_bf066e6e_fk_reporting FOREIGN KEY (project_id) REFERENCES template0.reporting_gcpproject(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_gcpcostentrybill reporting_gcpcostent_provider_id_4da1742f_fk_api_provi; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcpcostentrybill
    ADD CONSTRAINT reporting_gcpcostent_provider_id_4da1742f_fk_api_provi FOREIGN KEY (provider_id) REFERENCES public.api_provider(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_gcptags_summary reporting_gcptags_su_cost_entry_bill_id_e442ff66_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_gcptags_summary
    ADD CONSTRAINT reporting_gcptags_su_cost_entry_bill_id_e442ff66_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_gcpcostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawscostlineitem_project_daily_summary reporting_ocpawscost_account_alias_id_d12902c6_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawscostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpawscost_account_alias_id_d12902c6_fk_reporting FOREIGN KEY (account_alias_id) REFERENCES template0.reporting_awsaccountalias(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawscostlineitem_daily_summary reporting_ocpawscost_account_alias_id_f19d2883_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawscostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpawscost_account_alias_id_f19d2883_fk_reporting FOREIGN KEY (account_alias_id) REFERENCES template0.reporting_awsaccountalias(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawscostlineitem_project_daily_summary reporting_ocpawscost_cost_entry_bill_id_2740da80_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawscostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpawscost_cost_entry_bill_id_2740da80_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawscostlineitem_daily_summary reporting_ocpawscost_cost_entry_bill_id_2a473151_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawscostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpawscost_cost_entry_bill_id_2a473151_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawscostlineitem_daily_summary reporting_ocpawscost_report_period_id_150c5620_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawscostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpawscost_report_period_id_150c5620_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawscostlineitem_project_daily_summary reporting_ocpawscost_report_period_id_3f8d2da5_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawscostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpawscost_report_period_id_3f8d2da5_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawstags_summary reporting_ocpawstags_account_alias_id_f3d8c2e0_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawstags_summary
    ADD CONSTRAINT reporting_ocpawstags_account_alias_id_f3d8c2e0_fk_reporting FOREIGN KEY (account_alias_id) REFERENCES template0.reporting_awsaccountalias(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawstags_summary reporting_ocpawstags_cost_entry_bill_id_9fe9ad45_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawstags_summary
    ADD CONSTRAINT reporting_ocpawstags_cost_entry_bill_id_9fe9ad45_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawstags_summary reporting_ocpawstags_report_period_id_54cc3cc4_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpawstags_summary
    ADD CONSTRAINT reporting_ocpawstags_report_period_id_54cc3cc4_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpazurecostlineitem_project_daily_summary reporting_ocpazureco_cost_entry_bill_id_442560ac_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazurecostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpazureco_cost_entry_bill_id_442560ac_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_azurecostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpazurecostlineitem_daily_summary reporting_ocpazureco_cost_entry_bill_id_b12d05bd_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazurecostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpazureco_cost_entry_bill_id_b12d05bd_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_azurecostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpazurecostlineitem_project_daily_summary reporting_ocpazureco_report_period_id_145b540e_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazurecostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpazureco_report_period_id_145b540e_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpazurecostlineitem_daily_summary reporting_ocpazureco_report_period_id_e5bbf81f_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazurecostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpazureco_report_period_id_e5bbf81f_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpazuretags_summary reporting_ocpazureta_cost_entry_bill_id_c84d2dc3_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazuretags_summary
    ADD CONSTRAINT reporting_ocpazureta_cost_entry_bill_id_c84d2dc3_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES template0.reporting_azurecostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpazuretags_summary reporting_ocpazureta_report_period_id_19a6abdb_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpazuretags_summary
    ADD CONSTRAINT reporting_ocpazureta_report_period_id_19a6abdb_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpcosts_summary reporting_ocpcosts_s_report_period_id_e53cdbb2_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpcosts_summary
    ADD CONSTRAINT reporting_ocpcosts_s_report_period_id_e53cdbb2_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpnamespacelabellineitem reporting_ocpnamespa_report_id_16489a95_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnamespacelabellineitem
    ADD CONSTRAINT reporting_ocpnamespa_report_id_16489a95_fk_reporting FOREIGN KEY (report_id) REFERENCES template0.reporting_ocpusagereport(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpnamespacelabellineitem reporting_ocpnamespa_report_period_id_704a722f_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnamespacelabellineitem
    ADD CONSTRAINT reporting_ocpnamespa_report_period_id_704a722f_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpnodelabellineitem reporting_ocpnodelab_report_id_5e2f992a_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnodelabellineitem
    ADD CONSTRAINT reporting_ocpnodelab_report_id_5e2f992a_fk_reporting FOREIGN KEY (report_id) REFERENCES template0.reporting_ocpusagereport(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpnodelabellineitem reporting_ocpnodelab_report_period_id_d3fcf22e_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnodelabellineitem
    ADD CONSTRAINT reporting_ocpnodelab_report_period_id_d3fcf22e_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpnodelabellineitem_daily reporting_ocpnodelab_report_period_id_de6c8f1f_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpnodelabellineitem_daily
    ADD CONSTRAINT reporting_ocpnodelab_report_period_id_de6c8f1f_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpstoragelineitem reporting_ocpstorage_report_id_6ff71ea6_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpstoragelineitem
    ADD CONSTRAINT reporting_ocpstorage_report_id_6ff71ea6_fk_reporting FOREIGN KEY (report_id) REFERENCES template0.reporting_ocpusagereport(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpstoragevolumelabel_summary reporting_ocpstorage_report_period_id_53b5a3b8_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpstoragevolumelabel_summary
    ADD CONSTRAINT reporting_ocpstorage_report_period_id_53b5a3b8_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpstoragelineitem reporting_ocpstorage_report_period_id_6d730b12_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpstoragelineitem
    ADD CONSTRAINT reporting_ocpstorage_report_period_id_6d730b12_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpstoragelineitem_daily reporting_ocpstorage_report_period_id_ad325037_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpstoragelineitem_daily
    ADD CONSTRAINT reporting_ocpstorage_report_period_id_ad325037_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpusagelineitem reporting_ocpusageli_report_id_32a973b0_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagelineitem
    ADD CONSTRAINT reporting_ocpusageli_report_id_32a973b0_fk_reporting FOREIGN KEY (report_id) REFERENCES template0.reporting_ocpusagereport(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpusagelineitem reporting_ocpusageli_report_period_id_be7fa5ad_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagelineitem
    ADD CONSTRAINT reporting_ocpusageli_report_period_id_be7fa5ad_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpusagelineitem_daily reporting_ocpusageli_report_period_id_d5388c41_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagelineitem_daily
    ADD CONSTRAINT reporting_ocpusageli_report_period_id_d5388c41_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpusagepodlabel_summary reporting_ocpusagepo_report_period_id_fa250ee5_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagepodlabel_summary
    ADD CONSTRAINT reporting_ocpusagepo_report_period_id_fa250ee5_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpusagereportperiod reporting_ocpusagere_provider_id_7348fe66_fk_api_provi; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagereportperiod
    ADD CONSTRAINT reporting_ocpusagere_provider_id_7348fe66_fk_api_provi FOREIGN KEY (provider_id) REFERENCES public.api_provider(uuid) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpusagereport reporting_ocpusagere_report_period_id_477508c6_fk_reporting; Type: FK CONSTRAINT; Schema: template0; Owner: table_owner
--

ALTER TABLE ONLY template0.reporting_ocpusagereport
    ADD CONSTRAINT reporting_ocpusagere_report_period_id_477508c6_fk_reporting FOREIGN KEY (report_period_id) REFERENCES template0.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_aws_compute_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_compute_summary;


--
-- Name: reporting_aws_compute_summary_by_account; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_compute_summary_by_account;


--
-- Name: reporting_aws_compute_summary_by_region; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_compute_summary_by_region;


--
-- Name: reporting_aws_compute_summary_by_service; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_compute_summary_by_service;


--
-- Name: reporting_aws_cost_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_cost_summary;


--
-- Name: reporting_aws_cost_summary_by_account; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_cost_summary_by_account;


--
-- Name: reporting_aws_cost_summary_by_region; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_cost_summary_by_region;


--
-- Name: reporting_aws_cost_summary_by_service; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_cost_summary_by_service;


--
-- Name: reporting_aws_database_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_database_summary;


--
-- Name: reporting_aws_network_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_network_summary;


--
-- Name: reporting_aws_storage_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_storage_summary;


--
-- Name: reporting_aws_storage_summary_by_account; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_storage_summary_by_account;


--
-- Name: reporting_aws_storage_summary_by_region; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_storage_summary_by_region;


--
-- Name: reporting_aws_storage_summary_by_service; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_aws_storage_summary_by_service;


--
-- Name: reporting_azure_compute_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_azure_compute_summary;


--
-- Name: reporting_azure_cost_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_azure_cost_summary;


--
-- Name: reporting_azure_cost_summary_by_account; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_azure_cost_summary_by_account;


--
-- Name: reporting_azure_cost_summary_by_location; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_azure_cost_summary_by_location;


--
-- Name: reporting_azure_cost_summary_by_service; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_azure_cost_summary_by_service;


--
-- Name: reporting_azure_database_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_azure_database_summary;


--
-- Name: reporting_azure_network_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_azure_network_summary;


--
-- Name: reporting_azure_storage_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_azure_storage_summary;


--
-- Name: reporting_gcp_compute_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_compute_summary;


--
-- Name: reporting_gcp_compute_summary_by_account; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_compute_summary_by_account;


--
-- Name: reporting_gcp_compute_summary_by_project; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_compute_summary_by_project;


--
-- Name: reporting_gcp_compute_summary_by_region; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_compute_summary_by_region;


--
-- Name: reporting_gcp_compute_summary_by_service; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_compute_summary_by_service;


--
-- Name: reporting_gcp_cost_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_cost_summary;


--
-- Name: reporting_gcp_cost_summary_by_account; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_cost_summary_by_account;


--
-- Name: reporting_gcp_cost_summary_by_project; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_cost_summary_by_project;


--
-- Name: reporting_gcp_cost_summary_by_region; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_cost_summary_by_region;


--
-- Name: reporting_gcp_cost_summary_by_service; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_cost_summary_by_service;


--
-- Name: reporting_gcp_database_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_database_summary;


--
-- Name: reporting_gcp_network_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_network_summary;


--
-- Name: reporting_gcp_storage_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_storage_summary;


--
-- Name: reporting_gcp_storage_summary_by_account; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_storage_summary_by_account;


--
-- Name: reporting_gcp_storage_summary_by_project; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_storage_summary_by_project;


--
-- Name: reporting_gcp_storage_summary_by_region; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_storage_summary_by_region;


--
-- Name: reporting_gcp_storage_summary_by_service; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_gcp_storage_summary_by_service;


--
-- Name: reporting_ocp_cost_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocp_cost_summary;


--
-- Name: reporting_ocp_cost_summary_by_node; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocp_cost_summary_by_node;


--
-- Name: reporting_ocp_cost_summary_by_project; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocp_cost_summary_by_project;


--
-- Name: reporting_ocp_pod_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocp_pod_summary;


--
-- Name: reporting_ocp_pod_summary_by_project; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocp_pod_summary_by_project;


--
-- Name: reporting_ocp_volume_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocp_volume_summary;


--
-- Name: reporting_ocp_volume_summary_by_project; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocp_volume_summary_by_project;


--
-- Name: reporting_ocpallcostlineitem_daily_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpallcostlineitem_daily_summary;


--
-- Name: reporting_ocpall_compute_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpall_compute_summary;


--
-- Name: reporting_ocpall_cost_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpall_cost_summary;


--
-- Name: reporting_ocpall_cost_summary_by_account; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpall_cost_summary_by_account;


--
-- Name: reporting_ocpall_cost_summary_by_region; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpall_cost_summary_by_region;


--
-- Name: reporting_ocpall_cost_summary_by_service; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpall_cost_summary_by_service;


--
-- Name: reporting_ocpall_database_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpall_database_summary;


--
-- Name: reporting_ocpall_network_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpall_network_summary;


--
-- Name: reporting_ocpall_storage_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpall_storage_summary;


--
-- Name: reporting_ocpallcostlineitem_project_daily_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpallcostlineitem_project_daily_summary;


--
-- Name: reporting_ocpaws_compute_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpaws_compute_summary;


--
-- Name: reporting_ocpaws_cost_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpaws_cost_summary;


--
-- Name: reporting_ocpaws_cost_summary_by_account; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpaws_cost_summary_by_account;


--
-- Name: reporting_ocpaws_cost_summary_by_region; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpaws_cost_summary_by_region;


--
-- Name: reporting_ocpaws_cost_summary_by_service; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpaws_cost_summary_by_service;


--
-- Name: reporting_ocpaws_database_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpaws_database_summary;


--
-- Name: reporting_ocpaws_network_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpaws_network_summary;


--
-- Name: reporting_ocpaws_storage_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpaws_storage_summary;


--
-- Name: reporting_ocpazure_compute_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpazure_compute_summary;


--
-- Name: reporting_ocpazure_cost_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpazure_cost_summary;


--
-- Name: reporting_ocpazure_cost_summary_by_account; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpazure_cost_summary_by_account;


--
-- Name: reporting_ocpazure_cost_summary_by_location; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpazure_cost_summary_by_location;


--
-- Name: reporting_ocpazure_cost_summary_by_service; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpazure_cost_summary_by_service;


--
-- Name: reporting_ocpazure_database_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpazure_database_summary;


--
-- Name: reporting_ocpazure_network_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpazure_network_summary;


--
-- Name: reporting_ocpazure_storage_summary; Type: MATERIALIZED VIEW DATA; Schema: template0; Owner: table_owner
--

REFRESH MATERIALIZED VIEW template0.reporting_ocpazure_storage_summary;


--
-- PostgreSQL database dump complete
--
