--
-- PostgreSQL database dump
--

-- Dumped from database version 9.6.13
-- Dumped by pg_dump version 11.1

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: acct10001; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA acct10001;


ALTER SCHEMA acct10001 OWNER TO postgres;

SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: django_migrations; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.django_migrations (
    id integer NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


ALTER TABLE acct10001.django_migrations OWNER TO postgres;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.django_migrations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.django_migrations_id_seq OWNER TO postgres;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.django_migrations_id_seq OWNED BY acct10001.django_migrations.id;


--
-- Name: rates_rate; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.rates_rate (
    id integer NOT NULL,
    uuid uuid NOT NULL,
    metric character varying(256) NOT NULL,
    rates jsonb NOT NULL
);


ALTER TABLE acct10001.rates_rate OWNER TO postgres;

--
-- Name: rates_rate_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.rates_rate_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.rates_rate_id_seq OWNER TO postgres;

--
-- Name: rates_rate_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.rates_rate_id_seq OWNED BY acct10001.rates_rate.id;


--
-- Name: rates_ratemap; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.rates_ratemap (
    id integer NOT NULL,
    provider_uuid uuid NOT NULL,
    rate_id integer
);


ALTER TABLE acct10001.rates_ratemap OWNER TO postgres;

--
-- Name: rates_ratemap_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.rates_ratemap_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.rates_ratemap_id_seq OWNER TO postgres;

--
-- Name: rates_ratemap_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.rates_ratemap_id_seq OWNED BY acct10001.rates_ratemap.id;


--
-- Name: reporting_awsaccountalias; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_awsaccountalias (
    id integer NOT NULL,
    account_id character varying(50) NOT NULL,
    account_alias character varying(63)
);


ALTER TABLE acct10001.reporting_awsaccountalias OWNER TO postgres;

--
-- Name: reporting_awsaccountalias_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_awsaccountalias_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_awsaccountalias_id_seq OWNER TO postgres;

--
-- Name: reporting_awsaccountalias_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_awsaccountalias_id_seq OWNED BY acct10001.reporting_awsaccountalias.id;


--
-- Name: reporting_awscostentry; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_awscostentry (
    id integer NOT NULL,
    interval_start timestamp with time zone NOT NULL,
    interval_end timestamp with time zone NOT NULL,
    bill_id integer NOT NULL
);


ALTER TABLE acct10001.reporting_awscostentry OWNER TO postgres;

--
-- Name: reporting_awscostentry_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_awscostentry_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_awscostentry_id_seq OWNER TO postgres;

--
-- Name: reporting_awscostentry_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_awscostentry_id_seq OWNED BY acct10001.reporting_awscostentry.id;


--
-- Name: reporting_awscostentrybill; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_awscostentrybill (
    id integer NOT NULL,
    billing_resource character varying(50) NOT NULL,
    bill_type character varying(50) NOT NULL,
    payer_account_id character varying(50) NOT NULL,
    billing_period_start timestamp with time zone NOT NULL,
    billing_period_end timestamp with time zone NOT NULL,
    finalized_datetime timestamp with time zone,
    summary_data_creation_datetime timestamp with time zone,
    summary_data_updated_datetime timestamp with time zone,
    provider_id integer,
    derived_cost_datetime timestamp with time zone
);


ALTER TABLE acct10001.reporting_awscostentrybill OWNER TO postgres;

--
-- Name: reporting_awscostentrybill_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_awscostentrybill_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_awscostentrybill_id_seq OWNER TO postgres;

--
-- Name: reporting_awscostentrybill_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_awscostentrybill_id_seq OWNED BY acct10001.reporting_awscostentrybill.id;


--
-- Name: reporting_awscostentrylineitem; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_awscostentrylineitem (
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
    usage_amount numeric(17,9),
    normalization_factor double precision,
    normalized_usage_amount numeric(17,9),
    currency_code character varying(10) NOT NULL,
    unblended_rate numeric(17,9),
    unblended_cost numeric(17,9),
    blended_rate numeric(17,9),
    blended_cost numeric(17,9),
    public_on_demand_cost numeric(17,9),
    public_on_demand_rate numeric(17,9),
    reservation_amortized_upfront_fee numeric(17,9),
    reservation_amortized_upfront_cost_for_usage numeric(17,9),
    reservation_recurring_fee_for_usage numeric(17,9),
    reservation_unused_quantity numeric(17,9),
    reservation_unused_recurring_fee numeric(17,9),
    tax_type text,
    cost_entry_id integer NOT NULL,
    cost_entry_bill_id integer NOT NULL,
    cost_entry_pricing_id integer,
    cost_entry_product_id integer,
    cost_entry_reservation_id integer
);


ALTER TABLE acct10001.reporting_awscostentrylineitem OWNER TO postgres;

--
-- Name: reporting_awscostentrylineitem_daily; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_awscostentrylineitem_daily (
    id bigint NOT NULL,
    line_item_type character varying(50) NOT NULL,
    usage_account_id character varying(50) NOT NULL,
    usage_start timestamp with time zone NOT NULL,
    usage_end timestamp with time zone,
    product_code character varying(50) NOT NULL,
    usage_type character varying(50),
    operation character varying(50),
    availability_zone character varying(50),
    resource_id character varying(256),
    usage_amount numeric(24,9),
    normalization_factor double precision,
    normalized_usage_amount double precision,
    currency_code character varying(10) NOT NULL,
    unblended_rate numeric(17,9),
    unblended_cost numeric(17,9),
    blended_rate numeric(17,9),
    blended_cost numeric(17,9),
    public_on_demand_cost numeric(17,9),
    public_on_demand_rate numeric(17,9),
    tax_type text,
    tags jsonb,
    cost_entry_pricing_id integer,
    cost_entry_product_id integer,
    cost_entry_reservation_id integer,
    cost_entry_bill_id integer
);


ALTER TABLE acct10001.reporting_awscostentrylineitem_daily OWNER TO postgres;

--
-- Name: reporting_awscostentrylineitem_daily_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_awscostentrylineitem_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_awscostentrylineitem_daily_id_seq OWNER TO postgres;

--
-- Name: reporting_awscostentrylineitem_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_awscostentrylineitem_daily_id_seq OWNED BY acct10001.reporting_awscostentrylineitem_daily.id;


--
-- Name: reporting_awscostentrylineitem_daily_summary; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_awscostentrylineitem_daily_summary (
    id bigint NOT NULL,
    usage_start timestamp with time zone NOT NULL,
    usage_end timestamp with time zone,
    usage_account_id character varying(50) NOT NULL,
    product_code character varying(50) NOT NULL,
    product_family character varying(150),
    availability_zone character varying(50),
    region character varying(50),
    instance_type character varying(50),
    unit character varying(63),
    resource_count integer,
    usage_amount numeric(24,9),
    normalization_factor double precision,
    normalized_usage_amount double precision,
    currency_code character varying(10) NOT NULL,
    unblended_rate numeric(17,9),
    unblended_cost numeric(17,9),
    blended_rate numeric(17,9),
    blended_cost numeric(17,9),
    public_on_demand_cost numeric(17,9),
    public_on_demand_rate numeric(17,9),
    tax_type text,
    account_alias_id integer,
    tags jsonb,
    resource_ids character varying(256)[],
    cost_entry_bill_id integer
);


ALTER TABLE acct10001.reporting_awscostentrylineitem_daily_summary OWNER TO postgres;

--
-- Name: reporting_awscostentrylineitem_daily_summary_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_awscostentrylineitem_daily_summary_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_awscostentrylineitem_daily_summary_id_seq OWNER TO postgres;

--
-- Name: reporting_awscostentrylineitem_daily_summary_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_awscostentrylineitem_daily_summary_id_seq OWNED BY acct10001.reporting_awscostentrylineitem_daily_summary.id;


--
-- Name: reporting_awscostentrylineitem_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_awscostentrylineitem_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_awscostentrylineitem_id_seq OWNER TO postgres;

--
-- Name: reporting_awscostentrylineitem_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_awscostentrylineitem_id_seq OWNED BY acct10001.reporting_awscostentrylineitem.id;


--
-- Name: reporting_awscostentrypricing; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_awscostentrypricing (
    id integer NOT NULL,
    term character varying(63),
    unit character varying(63)
);


ALTER TABLE acct10001.reporting_awscostentrypricing OWNER TO postgres;

--
-- Name: reporting_awscostentrypricing_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_awscostentrypricing_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_awscostentrypricing_id_seq OWNER TO postgres;

--
-- Name: reporting_awscostentrypricing_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_awscostentrypricing_id_seq OWNED BY acct10001.reporting_awscostentrypricing.id;


--
-- Name: reporting_awscostentryproduct; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_awscostentryproduct (
    id integer NOT NULL,
    sku character varying(128),
    product_name character varying(63),
    product_family character varying(150),
    service_code character varying(50),
    region character varying(50),
    instance_type character varying(50),
    memory double precision,
    memory_unit character varying(24),
    vcpu integer,
    CONSTRAINT reporting_awscostentryproduct_vcpu_check CHECK ((vcpu >= 0))
);


ALTER TABLE acct10001.reporting_awscostentryproduct OWNER TO postgres;

--
-- Name: reporting_awscostentryproduct_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_awscostentryproduct_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_awscostentryproduct_id_seq OWNER TO postgres;

--
-- Name: reporting_awscostentryproduct_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_awscostentryproduct_id_seq OWNED BY acct10001.reporting_awscostentryproduct.id;


--
-- Name: reporting_awscostentryreservation; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_awscostentryreservation (
    id integer NOT NULL,
    reservation_arn text NOT NULL,
    number_of_reservations integer,
    units_per_reservation numeric(17,9),
    start_time timestamp with time zone,
    end_time timestamp with time zone,
    CONSTRAINT reporting_awscostentryreservation_number_of_reservations_check CHECK ((number_of_reservations >= 0))
);


ALTER TABLE acct10001.reporting_awscostentryreservation OWNER TO postgres;

--
-- Name: reporting_awscostentryreservation_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_awscostentryreservation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_awscostentryreservation_id_seq OWNER TO postgres;

--
-- Name: reporting_awscostentryreservation_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_awscostentryreservation_id_seq OWNED BY acct10001.reporting_awscostentryreservation.id;


--
-- Name: reporting_awstags_summary; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_awstags_summary (
    key character varying(253) NOT NULL,
    "values" character varying(253)[] NOT NULL
);


ALTER TABLE acct10001.reporting_awstags_summary OWNER TO postgres;

--
-- Name: reporting_ocpawscostlineitem_daily_summary; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpawscostlineitem_daily_summary (
    id integer NOT NULL,
    cluster_id character varying(50),
    cluster_alias character varying(256),
    namespace character varying(253)[] NOT NULL,
    pod character varying(253)[] NOT NULL,
    node character varying(253) NOT NULL,
    resource_id character varying(253),
    usage_start timestamp with time zone NOT NULL,
    usage_end timestamp with time zone NOT NULL,
    product_code character varying(50) NOT NULL,
    product_family character varying(150),
    usage_account_id character varying(50) NOT NULL,
    availability_zone character varying(50),
    region character varying(50),
    unit character varying(63),
    tags jsonb,
    unblended_cost numeric(17,9),
    account_alias_id integer,
    normalized_usage_amount double precision,
    usage_amount numeric(24,9),
    instance_type character varying(50),
    currency_code character varying(10),
    shared_projects integer NOT NULL,
    project_costs jsonb,
    cost_entry_bill_id integer
);


ALTER TABLE acct10001.reporting_ocpawscostlineitem_daily_summary OWNER TO postgres;

--
-- Name: reporting_ocpawscostlineitem_daily_summary_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_ocpawscostlineitem_daily_summary_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_ocpawscostlineitem_daily_summary_id_seq OWNER TO postgres;

--
-- Name: reporting_ocpawscostlineitem_daily_summary_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_ocpawscostlineitem_daily_summary_id_seq OWNED BY acct10001.reporting_ocpawscostlineitem_daily_summary.id;


--
-- Name: reporting_ocpawscostlineitem_project_daily_summary; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpawscostlineitem_project_daily_summary (
    id integer NOT NULL,
    cluster_id character varying(50),
    cluster_alias character varying(256),
    namespace character varying(253) NOT NULL,
    node character varying(253) NOT NULL,
    resource_id character varying(253),
    usage_start timestamp with time zone NOT NULL,
    usage_end timestamp with time zone NOT NULL,
    product_code character varying(50) NOT NULL,
    product_family character varying(150),
    instance_type character varying(50),
    usage_account_id character varying(50) NOT NULL,
    availability_zone character varying(50),
    region character varying(50),
    unit character varying(63),
    usage_amount numeric(24,9),
    normalized_usage_amount double precision,
    currency_code character varying(10),
    unblended_cost numeric(17,9),
    pod_cost numeric(24,6),
    account_alias_id integer,
    pod character varying(253),
    pod_labels jsonb,
    cost_entry_bill_id integer
);


ALTER TABLE acct10001.reporting_ocpawscostlineitem_project_daily_summary OWNER TO postgres;

--
-- Name: reporting_ocpawscostlineitem_project_daily_summary_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_ocpawscostlineitem_project_daily_summary_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_ocpawscostlineitem_project_daily_summary_id_seq OWNER TO postgres;

--
-- Name: reporting_ocpawscostlineitem_project_daily_summary_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_ocpawscostlineitem_project_daily_summary_id_seq OWNED BY acct10001.reporting_ocpawscostlineitem_project_daily_summary.id;


--
-- Name: reporting_ocpcosts_summary; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpcosts_summary (
    id integer NOT NULL,
    cluster_id character varying(50),
    cluster_alias character varying(256),
    namespace character varying(253) NOT NULL,
    pod character varying(253),
    node character varying(253),
    usage_start timestamp with time zone NOT NULL,
    usage_end timestamp with time zone NOT NULL,
    pod_charge_cpu_core_hours numeric(24,6),
    pod_charge_memory_gigabyte_hours numeric(24,6),
    persistentvolumeclaim_charge_gb_month numeric(24,6),
    infra_cost numeric(24,6),
    project_infra_cost numeric(24,6),
    pod_labels jsonb
);


ALTER TABLE acct10001.reporting_ocpcosts_summary OWNER TO postgres;

--
-- Name: reporting_ocpcosts_summary_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_ocpcosts_summary_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_ocpcosts_summary_id_seq OWNER TO postgres;

--
-- Name: reporting_ocpcosts_summary_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_ocpcosts_summary_id_seq OWNED BY acct10001.reporting_ocpcosts_summary.id;


--
-- Name: reporting_ocpstoragelineitem; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpstoragelineitem (
    id bigint NOT NULL,
    namespace character varying(253) NOT NULL,
    pod character varying(253),
    persistentvolumeclaim character varying(253) NOT NULL,
    persistentvolume character varying(253) NOT NULL,
    storageclass character varying(50),
    persistentvolumeclaim_capacity_bytes numeric(24,6),
    persistentvolumeclaim_capacity_byte_seconds numeric(24,6),
    volume_request_storage_byte_seconds numeric(24,6),
    persistentvolumeclaim_usage_byte_seconds numeric(24,6),
    persistentvolume_labels jsonb,
    persistentvolumeclaim_labels jsonb,
    report_id integer NOT NULL,
    report_period_id integer NOT NULL
);


ALTER TABLE acct10001.reporting_ocpstoragelineitem OWNER TO postgres;

--
-- Name: reporting_ocpstoragelineitem_daily; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpstoragelineitem_daily (
    id bigint NOT NULL,
    cluster_id character varying(50),
    cluster_alias character varying(256),
    namespace character varying(253) NOT NULL,
    pod character varying(253),
    persistentvolumeclaim character varying(253) NOT NULL,
    persistentvolume character varying(253) NOT NULL,
    storageclass character varying(50),
    usage_start timestamp with time zone NOT NULL,
    usage_end timestamp with time zone NOT NULL,
    persistentvolumeclaim_capacity_bytes numeric(24,6),
    persistentvolumeclaim_capacity_byte_seconds numeric(24,6),
    volume_request_storage_byte_seconds numeric(24,6),
    persistentvolumeclaim_usage_byte_seconds numeric(24,6),
    total_seconds integer NOT NULL,
    persistentvolume_labels jsonb,
    persistentvolumeclaim_labels jsonb,
    node character varying(253)
);


ALTER TABLE acct10001.reporting_ocpstoragelineitem_daily OWNER TO postgres;

--
-- Name: reporting_ocpstoragelineitem_daily_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_ocpstoragelineitem_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_ocpstoragelineitem_daily_id_seq OWNER TO postgres;

--
-- Name: reporting_ocpstoragelineitem_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_ocpstoragelineitem_daily_id_seq OWNED BY acct10001.reporting_ocpstoragelineitem_daily.id;


--
-- Name: reporting_ocpstoragelineitem_daily_summary; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpstoragelineitem_daily_summary (
    id bigint NOT NULL,
    cluster_id character varying(50),
    cluster_alias character varying(256),
    namespace character varying(253) NOT NULL,
    persistentvolumeclaim character varying(253) NOT NULL,
    persistentvolume character varying(253) NOT NULL,
    storageclass character varying(50),
    pod character varying(253),
    usage_start timestamp with time zone NOT NULL,
    usage_end timestamp with time zone NOT NULL,
    volume_labels jsonb,
    persistentvolumeclaim_capacity_gigabyte numeric(24,6),
    persistentvolumeclaim_capacity_gigabyte_months numeric(24,6),
    volume_request_storage_gigabyte_months numeric(24,6),
    persistentvolumeclaim_usage_gigabyte_months numeric(24,6),
    persistentvolumeclaim_charge_gb_month numeric(24,6),
    node character varying(253)
);


ALTER TABLE acct10001.reporting_ocpstoragelineitem_daily_summary OWNER TO postgres;

--
-- Name: reporting_ocpstoragelineitem_daily_summary_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_ocpstoragelineitem_daily_summary_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_ocpstoragelineitem_daily_summary_id_seq OWNER TO postgres;

--
-- Name: reporting_ocpstoragelineitem_daily_summary_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_ocpstoragelineitem_daily_summary_id_seq OWNED BY acct10001.reporting_ocpstoragelineitem_daily_summary.id;


--
-- Name: reporting_ocpstoragelineitem_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_ocpstoragelineitem_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_ocpstoragelineitem_id_seq OWNER TO postgres;

--
-- Name: reporting_ocpstoragelineitem_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_ocpstoragelineitem_id_seq OWNED BY acct10001.reporting_ocpstoragelineitem.id;


--
-- Name: reporting_ocpstoragevolumeclaimlabel_summary; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpstoragevolumeclaimlabel_summary (
    key character varying(253) NOT NULL,
    "values" character varying(253)[] NOT NULL
);


ALTER TABLE acct10001.reporting_ocpstoragevolumeclaimlabel_summary OWNER TO postgres;

--
-- Name: reporting_ocpstoragevolumelabel_summary; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpstoragevolumelabel_summary (
    key character varying(253) NOT NULL,
    "values" character varying(253)[] NOT NULL
);


ALTER TABLE acct10001.reporting_ocpstoragevolumelabel_summary OWNER TO postgres;

--
-- Name: reporting_ocpusagelineitem; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpusagelineitem (
    id bigint NOT NULL,
    namespace character varying(253) NOT NULL,
    pod character varying(253) NOT NULL,
    node character varying(253) NOT NULL,
    pod_usage_cpu_core_seconds numeric(24,6),
    pod_limit_cpu_core_seconds numeric(24,6),
    report_id integer NOT NULL,
    report_period_id integer NOT NULL,
    pod_limit_memory_byte_seconds numeric(24,6),
    pod_request_cpu_core_seconds numeric(24,6),
    pod_request_memory_byte_seconds numeric(24,6),
    pod_usage_memory_byte_seconds numeric(24,6),
    node_capacity_cpu_core_seconds numeric(24,6),
    node_capacity_cpu_cores numeric(24,6),
    node_capacity_memory_byte_seconds numeric(24,6),
    node_capacity_memory_bytes numeric(24,6),
    pod_labels jsonb,
    resource_id character varying(253)
);


ALTER TABLE acct10001.reporting_ocpusagelineitem OWNER TO postgres;

--
-- Name: reporting_ocpusagelineitem_daily; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpusagelineitem_daily (
    id bigint NOT NULL,
    namespace character varying(253) NOT NULL,
    pod character varying(253) NOT NULL,
    node character varying(253) NOT NULL,
    usage_start timestamp with time zone NOT NULL,
    usage_end timestamp with time zone NOT NULL,
    pod_usage_cpu_core_seconds numeric(24,6),
    pod_limit_cpu_core_seconds numeric(24,6),
    pod_limit_memory_byte_seconds numeric(24,6),
    pod_request_cpu_core_seconds numeric(24,6),
    pod_request_memory_byte_seconds numeric(24,6),
    pod_usage_memory_byte_seconds numeric(24,6),
    cluster_id character varying(50),
    total_seconds integer NOT NULL,
    node_capacity_cpu_core_seconds numeric(24,6),
    node_capacity_cpu_cores numeric(24,6),
    node_capacity_memory_byte_seconds numeric(24,6),
    node_capacity_memory_bytes numeric(24,6),
    pod_labels jsonb,
    cluster_capacity_cpu_core_seconds numeric(24,6),
    cluster_capacity_memory_byte_seconds numeric(24,6),
    cluster_alias character varying(256),
    resource_id character varying(253),
    total_capacity_cpu_core_seconds numeric(24,6),
    total_capacity_memory_byte_seconds numeric(24,6)
);


ALTER TABLE acct10001.reporting_ocpusagelineitem_daily OWNER TO postgres;

--
-- Name: reporting_ocpusagelineitem_daily_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_ocpusagelineitem_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_ocpusagelineitem_daily_id_seq OWNER TO postgres;

--
-- Name: reporting_ocpusagelineitem_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_ocpusagelineitem_daily_id_seq OWNED BY acct10001.reporting_ocpusagelineitem_daily.id;


--
-- Name: reporting_ocpusagelineitem_daily_summary; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpusagelineitem_daily_summary (
    id bigint NOT NULL,
    cluster_id character varying(50),
    namespace character varying(253) NOT NULL,
    pod character varying(253) NOT NULL,
    node character varying(253) NOT NULL,
    usage_start timestamp with time zone NOT NULL,
    usage_end timestamp with time zone NOT NULL,
    pod_usage_cpu_core_hours numeric(24,6),
    pod_request_cpu_core_hours numeric(24,6),
    pod_limit_cpu_core_hours numeric(24,6),
    pod_usage_memory_gigabyte_hours numeric(24,6),
    pod_request_memory_gigabyte_hours numeric(24,6),
    pod_limit_memory_gigabyte_hours numeric(24,6),
    node_capacity_cpu_core_hours numeric(24,6),
    node_capacity_cpu_cores numeric(24,6),
    pod_charge_cpu_core_hours numeric(24,6),
    pod_charge_memory_gigabyte_hours numeric(24,6),
    node_capacity_memory_gigabyte_hours numeric(24,6),
    node_capacity_memory_gigabytes numeric(24,6),
    cluster_capacity_cpu_core_hours numeric(24,6),
    cluster_capacity_memory_gigabyte_hours numeric(24,6),
    pod_labels jsonb,
    cluster_alias character varying(256),
    resource_id character varying(253),
    total_capacity_cpu_core_hours numeric(24,6),
    total_capacity_memory_gigabyte_hours numeric(24,6)
);


ALTER TABLE acct10001.reporting_ocpusagelineitem_daily_summary OWNER TO postgres;

--
-- Name: reporting_ocpusagelineitem_daily_summary_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_ocpusagelineitem_daily_summary_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_ocpusagelineitem_daily_summary_id_seq OWNER TO postgres;

--
-- Name: reporting_ocpusagelineitem_daily_summary_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_ocpusagelineitem_daily_summary_id_seq OWNED BY acct10001.reporting_ocpusagelineitem_daily_summary.id;


--
-- Name: reporting_ocpusagelineitem_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_ocpusagelineitem_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_ocpusagelineitem_id_seq OWNER TO postgres;

--
-- Name: reporting_ocpusagelineitem_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_ocpusagelineitem_id_seq OWNED BY acct10001.reporting_ocpusagelineitem.id;


--
-- Name: reporting_ocpusagepodlabel_summary; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpusagepodlabel_summary (
    key character varying(253) NOT NULL,
    "values" character varying(253)[] NOT NULL
);


ALTER TABLE acct10001.reporting_ocpusagepodlabel_summary OWNER TO postgres;

--
-- Name: reporting_ocpusagereport; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpusagereport (
    id integer NOT NULL,
    interval_start timestamp with time zone NOT NULL,
    interval_end timestamp with time zone NOT NULL,
    report_period_id integer NOT NULL
);


ALTER TABLE acct10001.reporting_ocpusagereport OWNER TO postgres;

--
-- Name: reporting_ocpusagereport_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_ocpusagereport_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_ocpusagereport_id_seq OWNER TO postgres;

--
-- Name: reporting_ocpusagereport_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_ocpusagereport_id_seq OWNED BY acct10001.reporting_ocpusagereport.id;


--
-- Name: reporting_ocpusagereportperiod; Type: TABLE; Schema: acct10001; Owner: postgres
--

CREATE TABLE acct10001.reporting_ocpusagereportperiod (
    id integer NOT NULL,
    cluster_id character varying(50) NOT NULL,
    report_period_start timestamp with time zone NOT NULL,
    report_period_end timestamp with time zone NOT NULL,
    provider_id integer,
    summary_data_creation_datetime timestamp with time zone,
    summary_data_updated_datetime timestamp with time zone,
    derived_cost_datetime timestamp with time zone
);


ALTER TABLE acct10001.reporting_ocpusagereportperiod OWNER TO postgres;

--
-- Name: reporting_ocpusagereportperiod_id_seq; Type: SEQUENCE; Schema: acct10001; Owner: postgres
--

CREATE SEQUENCE acct10001.reporting_ocpusagereportperiod_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE acct10001.reporting_ocpusagereportperiod_id_seq OWNER TO postgres;

--
-- Name: reporting_ocpusagereportperiod_id_seq; Type: SEQUENCE OWNED BY; Schema: acct10001; Owner: postgres
--

ALTER SEQUENCE acct10001.reporting_ocpusagereportperiod_id_seq OWNED BY acct10001.reporting_ocpusagereportperiod.id;


--
-- Name: api_customer; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.api_customer (
    id integer NOT NULL,
    date_created timestamp with time zone NOT NULL,
    uuid uuid NOT NULL,
    account_id character varying(150),
    schema_name text NOT NULL
);


ALTER TABLE public.api_customer OWNER TO postgres;

--
-- Name: api_customer_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.api_customer_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.api_customer_id_seq OWNER TO postgres;

--
-- Name: api_customer_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.api_customer_id_seq OWNED BY public.api_customer.id;


--
-- Name: api_provider; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.api_provider (
    id integer NOT NULL,
    uuid uuid NOT NULL,
    name character varying(256) NOT NULL,
    type character varying(50) NOT NULL,
    setup_complete boolean NOT NULL,
    authentication_id integer,
    billing_source_id integer,
    created_by_id integer,
    customer_id integer
);


ALTER TABLE public.api_provider OWNER TO postgres;

--
-- Name: api_provider_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.api_provider_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.api_provider_id_seq OWNER TO postgres;

--
-- Name: api_provider_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.api_provider_id_seq OWNED BY public.api_provider.id;


--
-- Name: api_providerauthentication; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.api_providerauthentication (
    id integer NOT NULL,
    uuid uuid NOT NULL,
    provider_resource_name text NOT NULL
);


ALTER TABLE public.api_providerauthentication OWNER TO postgres;

--
-- Name: api_providerauthentication_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.api_providerauthentication_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.api_providerauthentication_id_seq OWNER TO postgres;

--
-- Name: api_providerauthentication_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.api_providerauthentication_id_seq OWNED BY public.api_providerauthentication.id;


--
-- Name: api_providerbillingsource; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.api_providerbillingsource (
    id integer NOT NULL,
    uuid uuid NOT NULL,
    bucket character varying(63) NOT NULL
);


ALTER TABLE public.api_providerbillingsource OWNER TO postgres;

--
-- Name: api_providerbillingsource_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.api_providerbillingsource_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.api_providerbillingsource_id_seq OWNER TO postgres;

--
-- Name: api_providerbillingsource_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.api_providerbillingsource_id_seq OWNED BY public.api_providerbillingsource.id;


--
-- Name: api_providerstatus; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.api_providerstatus (
    id integer NOT NULL,
    status integer NOT NULL,
    last_message character varying(256) NOT NULL,
    "timestamp" timestamp with time zone NOT NULL,
    retries integer NOT NULL,
    provider_id integer NOT NULL
);


ALTER TABLE public.api_providerstatus OWNER TO postgres;

--
-- Name: api_providerstatus_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.api_providerstatus_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.api_providerstatus_id_seq OWNER TO postgres;

--
-- Name: api_providerstatus_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.api_providerstatus_id_seq OWNED BY public.api_providerstatus.id;


--
-- Name: api_tenant; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.api_tenant (
    id integer NOT NULL,
    schema_name character varying(63) NOT NULL
);


ALTER TABLE public.api_tenant OWNER TO postgres;

--
-- Name: api_tenant_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.api_tenant_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.api_tenant_id_seq OWNER TO postgres;

--
-- Name: api_tenant_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.api_tenant_id_seq OWNED BY public.api_tenant.id;


--
-- Name: api_user; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.api_user (
    id integer NOT NULL,
    uuid uuid NOT NULL,
    username character varying(150) NOT NULL,
    email character varying(254) NOT NULL,
    date_created timestamp with time zone NOT NULL,
    is_active boolean,
    customer_id integer
);


ALTER TABLE public.api_user OWNER TO postgres;

--
-- Name: api_user_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.api_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.api_user_id_seq OWNER TO postgres;

--
-- Name: api_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.api_user_id_seq OWNED BY public.api_user.id;


--
-- Name: api_userpreference; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.api_userpreference (
    id integer NOT NULL,
    uuid uuid NOT NULL,
    preference jsonb NOT NULL,
    name character varying(255) NOT NULL,
    description character varying(255),
    user_id integer NOT NULL
);


ALTER TABLE public.api_userpreference OWNER TO postgres;

--
-- Name: api_userpreference_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.api_userpreference_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.api_userpreference_id_seq OWNER TO postgres;

--
-- Name: api_userpreference_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.api_userpreference_id_seq OWNED BY public.api_userpreference.id;


--
-- Name: auth_group; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.auth_group (
    id integer NOT NULL,
    name character varying(150) NOT NULL
);


ALTER TABLE public.auth_group OWNER TO postgres;

--
-- Name: auth_group_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.auth_group_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.auth_group_id_seq OWNER TO postgres;

--
-- Name: auth_group_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.auth_group_id_seq OWNED BY public.auth_group.id;


--
-- Name: auth_group_permissions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.auth_group_permissions (
    id integer NOT NULL,
    group_id integer NOT NULL,
    permission_id integer NOT NULL
);


ALTER TABLE public.auth_group_permissions OWNER TO postgres;

--
-- Name: auth_group_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.auth_group_permissions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.auth_group_permissions_id_seq OWNER TO postgres;

--
-- Name: auth_group_permissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.auth_group_permissions_id_seq OWNED BY public.auth_group_permissions.id;


--
-- Name: auth_permission; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.auth_permission (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    content_type_id integer NOT NULL,
    codename character varying(100) NOT NULL
);


ALTER TABLE public.auth_permission OWNER TO postgres;

--
-- Name: auth_permission_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.auth_permission_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.auth_permission_id_seq OWNER TO postgres;

--
-- Name: auth_permission_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.auth_permission_id_seq OWNED BY public.auth_permission.id;


--
-- Name: auth_user; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.auth_user (
    id integer NOT NULL,
    password character varying(128) NOT NULL,
    last_login timestamp with time zone,
    is_superuser boolean NOT NULL,
    username character varying(150) NOT NULL,
    first_name character varying(30) NOT NULL,
    last_name character varying(150) NOT NULL,
    email character varying(254) NOT NULL,
    is_staff boolean NOT NULL,
    is_active boolean NOT NULL,
    date_joined timestamp with time zone NOT NULL
);


ALTER TABLE public.auth_user OWNER TO postgres;

--
-- Name: auth_user_groups; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.auth_user_groups (
    id integer NOT NULL,
    user_id integer NOT NULL,
    group_id integer NOT NULL
);


ALTER TABLE public.auth_user_groups OWNER TO postgres;

--
-- Name: auth_user_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.auth_user_groups_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.auth_user_groups_id_seq OWNER TO postgres;

--
-- Name: auth_user_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.auth_user_groups_id_seq OWNED BY public.auth_user_groups.id;


--
-- Name: auth_user_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.auth_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.auth_user_id_seq OWNER TO postgres;

--
-- Name: auth_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.auth_user_id_seq OWNED BY public.auth_user.id;


--
-- Name: auth_user_user_permissions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.auth_user_user_permissions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    permission_id integer NOT NULL
);


ALTER TABLE public.auth_user_user_permissions OWNER TO postgres;

--
-- Name: auth_user_user_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.auth_user_user_permissions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.auth_user_user_permissions_id_seq OWNER TO postgres;

--
-- Name: auth_user_user_permissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.auth_user_user_permissions_id_seq OWNED BY public.auth_user_user_permissions.id;


--
-- Name: cost_models_metrics_map; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cost_models_metrics_map (
    id integer NOT NULL,
    source_type character varying(50) NOT NULL,
    metric character varying(256) NOT NULL,
    label_metric character varying(256) NOT NULL,
    label_measurement character varying(256) NOT NULL,
    label_measurement_unit character varying(64) NOT NULL
);


ALTER TABLE public.cost_models_metrics_map OWNER TO postgres;

--
-- Name: cost_models_metrics_map_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cost_models_metrics_map_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.cost_models_metrics_map_id_seq OWNER TO postgres;

--
-- Name: cost_models_metrics_map_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cost_models_metrics_map_id_seq OWNED BY public.cost_models_metrics_map.id;


--
-- Name: django_content_type; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.django_content_type (
    id integer NOT NULL,
    app_label character varying(100) NOT NULL,
    model character varying(100) NOT NULL
);


ALTER TABLE public.django_content_type OWNER TO postgres;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.django_content_type_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.django_content_type_id_seq OWNER TO postgres;

--
-- Name: django_content_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.django_content_type_id_seq OWNED BY public.django_content_type.id;


--
-- Name: django_migrations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.django_migrations (
    id integer NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


ALTER TABLE public.django_migrations OWNER TO postgres;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.django_migrations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.django_migrations_id_seq OWNER TO postgres;

--
-- Name: django_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.django_migrations_id_seq OWNED BY public.django_migrations.id;


--
-- Name: django_session; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.django_session (
    session_key character varying(40) NOT NULL,
    session_data text NOT NULL,
    expire_date timestamp with time zone NOT NULL
);


ALTER TABLE public.django_session OWNER TO postgres;

--
-- Name: region_mapping; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.region_mapping (
    id integer NOT NULL,
    region character varying(32) NOT NULL,
    region_name character varying(64) NOT NULL
);


ALTER TABLE public.region_mapping OWNER TO postgres;

--
-- Name: region_mapping_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.region_mapping_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.region_mapping_id_seq OWNER TO postgres;

--
-- Name: region_mapping_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.region_mapping_id_seq OWNED BY public.region_mapping.id;


--
-- Name: reporting_common_costusagereportmanifest; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reporting_common_costusagereportmanifest (
    id integer NOT NULL,
    assembly_id text NOT NULL,
    manifest_creation_datetime timestamp with time zone,
    manifest_updated_datetime timestamp with time zone,
    billing_period_start_datetime timestamp with time zone NOT NULL,
    num_processed_files integer NOT NULL,
    num_total_files integer NOT NULL,
    provider_id integer NOT NULL
);


ALTER TABLE public.reporting_common_costusagereportmanifest OWNER TO postgres;

--
-- Name: reporting_common_costusagereportmanifest_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.reporting_common_costusagereportmanifest_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.reporting_common_costusagereportmanifest_id_seq OWNER TO postgres;

--
-- Name: reporting_common_costusagereportmanifest_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.reporting_common_costusagereportmanifest_id_seq OWNED BY public.reporting_common_costusagereportmanifest.id;


--
-- Name: reporting_common_costusagereportstatus; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reporting_common_costusagereportstatus (
    id integer NOT NULL,
    report_name character varying(128) NOT NULL,
    last_completed_datetime timestamp with time zone,
    last_started_datetime timestamp with time zone,
    etag character varying(64),
    manifest_id integer
);


ALTER TABLE public.reporting_common_costusagereportstatus OWNER TO postgres;

--
-- Name: reporting_common_costusagereportstatus_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.reporting_common_costusagereportstatus_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.reporting_common_costusagereportstatus_id_seq OWNER TO postgres;

--
-- Name: reporting_common_costusagereportstatus_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.reporting_common_costusagereportstatus_id_seq OWNED BY public.reporting_common_costusagereportstatus.id;


--
-- Name: reporting_common_reportcolumnmap; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reporting_common_reportcolumnmap (
    id integer NOT NULL,
    provider_type character varying(50) NOT NULL,
    provider_column_name character varying(128) NOT NULL,
    database_table character varying(50) NOT NULL,
    database_column character varying(128) NOT NULL,
    report_type character varying(50)
);


ALTER TABLE public.reporting_common_reportcolumnmap OWNER TO postgres;

--
-- Name: reporting_common_reportcolumnmap_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.reporting_common_reportcolumnmap_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.reporting_common_reportcolumnmap_id_seq OWNER TO postgres;

--
-- Name: reporting_common_reportcolumnmap_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.reporting_common_reportcolumnmap_id_seq OWNED BY public.reporting_common_reportcolumnmap.id;


--
-- Name: si_unit_scale; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.si_unit_scale (
    id integer NOT NULL,
    prefix character varying(12) NOT NULL,
    prefix_symbol character varying(1) NOT NULL,
    multiplying_factor numeric(49,24) NOT NULL
);


ALTER TABLE public.si_unit_scale OWNER TO postgres;

--
-- Name: si_unit_scale_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.si_unit_scale_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.si_unit_scale_id_seq OWNER TO postgres;

--
-- Name: si_unit_scale_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.si_unit_scale_id_seq OWNED BY public.si_unit_scale.id;


--
-- Name: django_migrations id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.django_migrations ALTER COLUMN id SET DEFAULT nextval('acct10001.django_migrations_id_seq'::regclass);


--
-- Name: rates_rate id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.rates_rate ALTER COLUMN id SET DEFAULT nextval('acct10001.rates_rate_id_seq'::regclass);


--
-- Name: rates_ratemap id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.rates_ratemap ALTER COLUMN id SET DEFAULT nextval('acct10001.rates_ratemap_id_seq'::regclass);


--
-- Name: reporting_awsaccountalias id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awsaccountalias ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_awsaccountalias_id_seq'::regclass);


--
-- Name: reporting_awscostentry id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentry ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_awscostentry_id_seq'::regclass);


--
-- Name: reporting_awscostentrybill id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrybill ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_awscostentrybill_id_seq'::regclass);


--
-- Name: reporting_awscostentrylineitem id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_awscostentrylineitem_id_seq'::regclass);


--
-- Name: reporting_awscostentrylineitem_daily id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem_daily ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_awscostentrylineitem_daily_id_seq'::regclass);


--
-- Name: reporting_awscostentrylineitem_daily_summary id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem_daily_summary ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_awscostentrylineitem_daily_summary_id_seq'::regclass);


--
-- Name: reporting_awscostentrypricing id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrypricing ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_awscostentrypricing_id_seq'::regclass);


--
-- Name: reporting_awscostentryproduct id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentryproduct ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_awscostentryproduct_id_seq'::regclass);


--
-- Name: reporting_awscostentryreservation id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentryreservation ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_awscostentryreservation_id_seq'::regclass);


--
-- Name: reporting_ocpawscostlineitem_daily_summary id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpawscostlineitem_daily_summary ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_ocpawscostlineitem_daily_summary_id_seq'::regclass);


--
-- Name: reporting_ocpawscostlineitem_project_daily_summary id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpawscostlineitem_project_daily_summary ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_ocpawscostlineitem_project_daily_summary_id_seq'::regclass);


--
-- Name: reporting_ocpcosts_summary id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpcosts_summary ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_ocpcosts_summary_id_seq'::regclass);


--
-- Name: reporting_ocpstoragelineitem id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpstoragelineitem ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_ocpstoragelineitem_id_seq'::regclass);


--
-- Name: reporting_ocpstoragelineitem_daily id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpstoragelineitem_daily ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_ocpstoragelineitem_daily_id_seq'::regclass);


--
-- Name: reporting_ocpstoragelineitem_daily_summary id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpstoragelineitem_daily_summary ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_ocpstoragelineitem_daily_summary_id_seq'::regclass);


--
-- Name: reporting_ocpusagelineitem id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagelineitem ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_ocpusagelineitem_id_seq'::regclass);


--
-- Name: reporting_ocpusagelineitem_daily id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagelineitem_daily ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_ocpusagelineitem_daily_id_seq'::regclass);


--
-- Name: reporting_ocpusagelineitem_daily_summary id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagelineitem_daily_summary ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_ocpusagelineitem_daily_summary_id_seq'::regclass);


--
-- Name: reporting_ocpusagereport id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagereport ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_ocpusagereport_id_seq'::regclass);


--
-- Name: reporting_ocpusagereportperiod id; Type: DEFAULT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagereportperiod ALTER COLUMN id SET DEFAULT nextval('acct10001.reporting_ocpusagereportperiod_id_seq'::regclass);


--
-- Name: api_customer id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_customer ALTER COLUMN id SET DEFAULT nextval('public.api_customer_id_seq'::regclass);


--
-- Name: api_provider id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_provider ALTER COLUMN id SET DEFAULT nextval('public.api_provider_id_seq'::regclass);


--
-- Name: api_providerauthentication id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_providerauthentication ALTER COLUMN id SET DEFAULT nextval('public.api_providerauthentication_id_seq'::regclass);


--
-- Name: api_providerbillingsource id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_providerbillingsource ALTER COLUMN id SET DEFAULT nextval('public.api_providerbillingsource_id_seq'::regclass);


--
-- Name: api_providerstatus id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_providerstatus ALTER COLUMN id SET DEFAULT nextval('public.api_providerstatus_id_seq'::regclass);


--
-- Name: api_tenant id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_tenant ALTER COLUMN id SET DEFAULT nextval('public.api_tenant_id_seq'::regclass);


--
-- Name: api_user id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_user ALTER COLUMN id SET DEFAULT nextval('public.api_user_id_seq'::regclass);


--
-- Name: api_userpreference id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_userpreference ALTER COLUMN id SET DEFAULT nextval('public.api_userpreference_id_seq'::regclass);


--
-- Name: auth_group id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_group ALTER COLUMN id SET DEFAULT nextval('public.auth_group_id_seq'::regclass);


--
-- Name: auth_group_permissions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_group_permissions ALTER COLUMN id SET DEFAULT nextval('public.auth_group_permissions_id_seq'::regclass);


--
-- Name: auth_permission id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_permission ALTER COLUMN id SET DEFAULT nextval('public.auth_permission_id_seq'::regclass);


--
-- Name: auth_user id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user ALTER COLUMN id SET DEFAULT nextval('public.auth_user_id_seq'::regclass);


--
-- Name: auth_user_groups id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user_groups ALTER COLUMN id SET DEFAULT nextval('public.auth_user_groups_id_seq'::regclass);


--
-- Name: auth_user_user_permissions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user_user_permissions ALTER COLUMN id SET DEFAULT nextval('public.auth_user_user_permissions_id_seq'::regclass);


--
-- Name: cost_models_metrics_map id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cost_models_metrics_map ALTER COLUMN id SET DEFAULT nextval('public.cost_models_metrics_map_id_seq'::regclass);


--
-- Name: django_content_type id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.django_content_type ALTER COLUMN id SET DEFAULT nextval('public.django_content_type_id_seq'::regclass);


--
-- Name: django_migrations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.django_migrations ALTER COLUMN id SET DEFAULT nextval('public.django_migrations_id_seq'::regclass);


--
-- Name: region_mapping id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.region_mapping ALTER COLUMN id SET DEFAULT nextval('public.region_mapping_id_seq'::regclass);


--
-- Name: reporting_common_costusagereportmanifest id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reporting_common_costusagereportmanifest ALTER COLUMN id SET DEFAULT nextval('public.reporting_common_costusagereportmanifest_id_seq'::regclass);


--
-- Name: reporting_common_costusagereportstatus id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reporting_common_costusagereportstatus ALTER COLUMN id SET DEFAULT nextval('public.reporting_common_costusagereportstatus_id_seq'::regclass);


--
-- Name: reporting_common_reportcolumnmap id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reporting_common_reportcolumnmap ALTER COLUMN id SET DEFAULT nextval('public.reporting_common_reportcolumnmap_id_seq'::regclass);


--
-- Name: si_unit_scale id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.si_unit_scale ALTER COLUMN id SET DEFAULT nextval('public.si_unit_scale_id_seq'::regclass);


--
-- Data for Name: django_migrations; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.django_migrations (id, app, name, applied) FROM stdin;
1	api	0001_initial	2019-06-05 18:28:29.439109+00
2	api	0002_auto_20180926_1905	2019-06-05 18:28:29.441304+00
3	api	0003_auto_20181008_1819	2019-06-05 18:28:29.443033+00
4	api	0004_auto_20181012_1507	2019-06-05 18:28:29.444684+00
5	api	0005_auto_20181109_2121	2019-06-05 18:28:29.446481+00
6	api	0006_delete_rate	2019-06-05 18:28:29.448209+00
7	api	0007_auto_20181213_1940	2019-06-05 18:28:29.449928+00
8	api	0008_auto_20190305_2015	2019-06-05 18:28:29.451786+00
9	api	0009_providerstatus	2019-06-05 18:28:29.461819+00
10	api	0010_costmodelmetricsmap	2019-06-05 18:28:29.468328+00
11	contenttypes	0001_initial	2019-06-05 18:28:29.47586+00
12	contenttypes	0002_remove_content_type_name	2019-06-05 18:28:29.484162+00
13	auth	0001_initial	2019-06-05 18:28:29.499527+00
14	auth	0002_alter_permission_name_max_length	2019-06-05 18:28:29.510308+00
15	auth	0003_alter_user_email_max_length	2019-06-05 18:28:29.520133+00
16	auth	0004_alter_user_username_opts	2019-06-05 18:28:29.529559+00
17	auth	0005_alter_user_last_login_null	2019-06-05 18:28:29.539507+00
18	auth	0006_require_contenttypes_0002	2019-06-05 18:28:29.542923+00
19	auth	0007_alter_validators_add_error_messages	2019-06-05 18:28:29.552345+00
20	auth	0008_alter_user_username_max_length	2019-06-05 18:28:29.562176+00
21	auth	0009_alter_user_last_name_max_length	2019-06-05 18:28:29.571629+00
22	auth	0010_alter_group_name_max_length	2019-06-05 18:28:29.581137+00
23	auth	0011_update_proxy_permissions	2019-06-05 18:28:29.585935+00
24	rates	0001_initial	2019-06-05 18:28:29.609419+00
25	rates	0002_auto_20181205_1810	2019-06-05 18:28:29.615212+00
26	rates	0003_auto_20190213_2040	2019-06-05 18:28:29.62063+00
27	rates	0004_auto_20190301_1850	2019-06-05 18:28:29.626455+00
28	rates	0005_auto_20190422_1415	2019-06-05 18:28:29.652985+00
29	reporting	0001_initial	2019-06-05 18:28:31.261795+00
30	reporting	0002_auto_20180926_1818	2019-06-05 18:28:31.263806+00
31	reporting	0003_auto_20180928_1840	2019-06-05 18:28:31.265734+00
32	reporting	0004_auto_20181003_1633	2019-06-05 18:28:31.267597+00
33	reporting	0005_auto_20181003_1416	2019-06-05 18:28:31.269791+00
34	reporting	0006_awscostentrylineitemaggregates_account_alias	2019-06-05 18:28:31.271564+00
35	reporting	0007_awscostentrybill_provider_id	2019-06-05 18:28:31.27349+00
36	reporting	0008_auto_20181012_1724	2019-06-05 18:28:31.27524+00
37	reporting	0009_auto_20181016_1940	2019-06-05 18:28:31.277215+00
38	reporting	0010_auto_20181017_1659	2019-06-05 18:28:31.278972+00
39	reporting	0011_auto_20181018_1811	2019-06-05 18:28:31.280694+00
40	reporting	0012_auto_20181106_1502	2019-06-05 18:28:31.282414+00
41	reporting	0013_auto_20181107_1956	2019-06-05 18:28:31.284132+00
42	reporting	0014_auto_20181108_0207	2019-06-05 18:28:31.285926+00
43	reporting	0015_auto_20181109_1618	2019-06-05 18:28:31.287852+00
44	reporting	0016_delete_rate	2019-06-05 18:28:31.2897+00
45	reporting	0017_auto_20181121_1444	2019-06-05 18:28:31.291542+00
46	reporting	0018_auto_20181129_0217	2019-06-05 18:28:31.293328+00
47	reporting	0019_auto_20181206_2138	2019-06-05 18:28:31.295117+00
48	reporting	0020_auto_20181211_1557	2019-06-05 18:28:31.297083+00
49	reporting	0021_auto_20181212_1816	2019-06-05 18:28:31.298991+00
50	reporting	0022_auto_20181221_1617	2019-06-05 18:28:31.300779+00
51	reporting	0023_awscostentrylineitemdailysummary_tags	2019-06-05 18:28:31.302579+00
52	reporting	0024_ocpusagepodlabelsummary	2019-06-05 18:28:31.304363+00
53	reporting	0025_auto_20190128_1825	2019-06-05 18:28:31.306291+00
54	reporting	0026_auto_20190130_1746	2019-06-05 18:28:31.30833+00
55	reporting	0027_auto_20190205_1659	2019-06-05 18:28:31.310293+00
56	reporting	0028_auto_20190205_2022	2019-06-05 18:28:31.312294+00
57	reporting	0029_auto_20190207_1526	2019-06-05 18:28:31.31418+00
58	reporting	0030_auto_20190208_0159	2019-06-05 18:28:31.316148+00
59	reporting	0031_ocpawscostlineitemdailysummary_instance_type	2019-06-05 18:28:31.318181+00
60	reporting	0032_auto_20190213_2152	2019-06-05 18:28:31.320283+00
61	reporting	0033_auto_20190214_1637	2019-06-05 18:28:31.322164+00
62	reporting	0034_ocpstoragevolumeclaimlabelsummary_ocpstoragevolumelabelsummary	2019-06-05 18:28:31.324047+00
63	reporting	0035_ocpawscostlineitemdailysummary_currency_code	2019-06-05 18:28:31.326234+00
64	reporting	0036_auto_20190215_2058	2019-06-05 18:28:31.328206+00
65	reporting	0037_auto_20190218_2054	2019-06-05 18:28:31.330273+00
66	reporting	0038_auto_20190220_1511	2019-06-05 18:28:31.332518+00
67	reporting	0039_auto_20190220_1610	2019-06-05 18:28:31.33468+00
68	reporting	0040_auto_20190226_1538	2019-06-05 18:28:31.336818+00
69	reporting	0041_auto_20190301_1548	2019-06-05 18:28:31.338798+00
70	reporting	0042_awscostentrylineitemdailysummary_resource_ids	2019-06-05 18:28:31.340783+00
71	reporting	0043_auto_20190228_2016	2019-06-05 18:28:31.342695+00
72	reporting	0044_costsummary	2019-06-05 18:28:31.344557+00
73	reporting	0045_auto_20190308_1839	2019-06-05 18:28:31.346366+00
74	reporting	0046_auto_20190313_1533	2019-06-05 18:28:31.34828+00
75	reporting	0047_auto_20190311_2021	2019-06-05 18:28:31.350127+00
76	reporting	0048_auto_20190313_1804	2019-06-05 18:28:31.352136+00
77	reporting	0049_auto_20190314_2016	2019-06-05 18:28:31.35412+00
78	reporting	0050_auto_20190315_1339	2019-06-05 18:28:31.356029+00
79	reporting	0051_auto_20190315_1458	2019-06-05 18:28:31.48415+00
80	reporting	0052_auto_20190318_1741	2019-06-05 18:28:31.492742+00
81	reporting	0053_auto_20190412_1529	2019-06-05 18:28:31.51267+00
82	reporting	0054_delete_ocpawscostlineitemdaily	2019-06-05 18:28:31.518467+00
83	reporting	0055_auto_20190416_2025	2019-06-05 18:28:31.608356+00
84	reporting	0056_auto_20190418_1850	2019-06-05 18:28:31.699042+00
85	reporting	0057_auto_20190422_1910	2019-06-05 18:28:31.742987+00
86	reporting	0058_auto_20190422_1915	2019-06-05 18:28:31.782714+00
87	reporting	0059_auto_20190422_1924	2019-06-05 18:28:31.819712+00
88	reporting	0060_auto_20190430_1926	2019-06-05 18:28:31.890507+00
89	reporting	0061_auto_20190501_1854	2019-06-05 18:28:31.957183+00
90	reporting	0062_auto_20190604_1840	2019-06-05 18:28:32.04476+00
91	reporting_common	0001_initial	2019-06-05 18:28:32.112656+00
92	reporting_common	0002_auto_20180926_1905	2019-06-05 18:28:32.114743+00
93	reporting_common	0003_auto_20180928_1732	2019-06-05 18:28:32.116849+00
94	reporting_common	0004_auto_20181003_1859	2019-06-05 18:28:32.118811+00
95	reporting_common	0005_auto_20181127_2046	2019-06-05 18:28:32.120864+00
96	reporting_common	0006_auto_20190208_0316	2019-06-05 18:28:32.122878+00
97	reporting_common	0007_auto_20190208_0316	2019-06-05 18:28:32.124839+00
98	reporting_common	0008_auto_20190412_1330	2019-06-05 18:28:32.148992+00
99	reporting_common	0009_costusagereportstatus_history	2019-06-05 18:28:32.160413+00
100	reporting_common	0010_remove_costusagereportstatus_history	2019-06-05 18:28:32.172042+00
101	sessions	0001_initial	2019-06-05 18:28:32.181168+00
102	api	0001_initial_squashed_0008_auto_20190305_2015	2019-06-05 18:28:32.188675+00
103	reporting	0001_initial_squashed_0050_auto_20190315_1339	2019-06-05 18:28:32.191734+00
104	reporting_common	0001_initial_squashed_0007_auto_20190208_0316	2019-06-05 18:28:32.194495+00
\.


--
-- Data for Name: rates_rate; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.rates_rate (id, uuid, metric, rates) FROM stdin;
\.


--
-- Data for Name: rates_ratemap; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.rates_ratemap (id, provider_uuid, rate_id) FROM stdin;
\.


--
-- Data for Name: reporting_awsaccountalias; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_awsaccountalias (id, account_id, account_alias) FROM stdin;
\.


--
-- Data for Name: reporting_awscostentry; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_awscostentry (id, interval_start, interval_end, bill_id) FROM stdin;
\.


--
-- Data for Name: reporting_awscostentrybill; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_awscostentrybill (id, billing_resource, bill_type, payer_account_id, billing_period_start, billing_period_end, finalized_datetime, summary_data_creation_datetime, summary_data_updated_datetime, provider_id, derived_cost_datetime) FROM stdin;
\.


--
-- Data for Name: reporting_awscostentrylineitem; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_awscostentrylineitem (id, tags, invoice_id, line_item_type, usage_account_id, usage_start, usage_end, product_code, usage_type, operation, availability_zone, resource_id, usage_amount, normalization_factor, normalized_usage_amount, currency_code, unblended_rate, unblended_cost, blended_rate, blended_cost, public_on_demand_cost, public_on_demand_rate, reservation_amortized_upfront_fee, reservation_amortized_upfront_cost_for_usage, reservation_recurring_fee_for_usage, reservation_unused_quantity, reservation_unused_recurring_fee, tax_type, cost_entry_id, cost_entry_bill_id, cost_entry_pricing_id, cost_entry_product_id, cost_entry_reservation_id) FROM stdin;
\.


--
-- Data for Name: reporting_awscostentrylineitem_daily; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_awscostentrylineitem_daily (id, line_item_type, usage_account_id, usage_start, usage_end, product_code, usage_type, operation, availability_zone, resource_id, usage_amount, normalization_factor, normalized_usage_amount, currency_code, unblended_rate, unblended_cost, blended_rate, blended_cost, public_on_demand_cost, public_on_demand_rate, tax_type, tags, cost_entry_pricing_id, cost_entry_product_id, cost_entry_reservation_id, cost_entry_bill_id) FROM stdin;
\.


--
-- Data for Name: reporting_awscostentrylineitem_daily_summary; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_awscostentrylineitem_daily_summary (id, usage_start, usage_end, usage_account_id, product_code, product_family, availability_zone, region, instance_type, unit, resource_count, usage_amount, normalization_factor, normalized_usage_amount, currency_code, unblended_rate, unblended_cost, blended_rate, blended_cost, public_on_demand_cost, public_on_demand_rate, tax_type, account_alias_id, tags, resource_ids, cost_entry_bill_id) FROM stdin;
\.


--
-- Data for Name: reporting_awscostentrypricing; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_awscostentrypricing (id, term, unit) FROM stdin;
\.


--
-- Data for Name: reporting_awscostentryproduct; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_awscostentryproduct (id, sku, product_name, product_family, service_code, region, instance_type, memory, memory_unit, vcpu) FROM stdin;
\.


--
-- Data for Name: reporting_awscostentryreservation; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_awscostentryreservation (id, reservation_arn, number_of_reservations, units_per_reservation, start_time, end_time) FROM stdin;
\.


--
-- Data for Name: reporting_awstags_summary; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_awstags_summary (key, "values") FROM stdin;
\.


--
-- Data for Name: reporting_ocpawscostlineitem_daily_summary; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpawscostlineitem_daily_summary (id, cluster_id, cluster_alias, namespace, pod, node, resource_id, usage_start, usage_end, product_code, product_family, usage_account_id, availability_zone, region, unit, tags, unblended_cost, account_alias_id, normalized_usage_amount, usage_amount, instance_type, currency_code, shared_projects, project_costs, cost_entry_bill_id) FROM stdin;
\.


--
-- Data for Name: reporting_ocpawscostlineitem_project_daily_summary; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpawscostlineitem_project_daily_summary (id, cluster_id, cluster_alias, namespace, node, resource_id, usage_start, usage_end, product_code, product_family, instance_type, usage_account_id, availability_zone, region, unit, usage_amount, normalized_usage_amount, currency_code, unblended_cost, pod_cost, account_alias_id, pod, pod_labels, cost_entry_bill_id) FROM stdin;
\.


--
-- Data for Name: reporting_ocpcosts_summary; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpcosts_summary (id, cluster_id, cluster_alias, namespace, pod, node, usage_start, usage_end, pod_charge_cpu_core_hours, pod_charge_memory_gigabyte_hours, persistentvolumeclaim_charge_gb_month, infra_cost, project_infra_cost, pod_labels) FROM stdin;
\.


--
-- Data for Name: reporting_ocpstoragelineitem; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpstoragelineitem (id, namespace, pod, persistentvolumeclaim, persistentvolume, storageclass, persistentvolumeclaim_capacity_bytes, persistentvolumeclaim_capacity_byte_seconds, volume_request_storage_byte_seconds, persistentvolumeclaim_usage_byte_seconds, persistentvolume_labels, persistentvolumeclaim_labels, report_id, report_period_id) FROM stdin;
\.


--
-- Data for Name: reporting_ocpstoragelineitem_daily; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpstoragelineitem_daily (id, cluster_id, cluster_alias, namespace, pod, persistentvolumeclaim, persistentvolume, storageclass, usage_start, usage_end, persistentvolumeclaim_capacity_bytes, persistentvolumeclaim_capacity_byte_seconds, volume_request_storage_byte_seconds, persistentvolumeclaim_usage_byte_seconds, total_seconds, persistentvolume_labels, persistentvolumeclaim_labels, node) FROM stdin;
\.


--
-- Data for Name: reporting_ocpstoragelineitem_daily_summary; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpstoragelineitem_daily_summary (id, cluster_id, cluster_alias, namespace, persistentvolumeclaim, persistentvolume, storageclass, pod, usage_start, usage_end, volume_labels, persistentvolumeclaim_capacity_gigabyte, persistentvolumeclaim_capacity_gigabyte_months, volume_request_storage_gigabyte_months, persistentvolumeclaim_usage_gigabyte_months, persistentvolumeclaim_charge_gb_month, node) FROM stdin;
\.


--
-- Data for Name: reporting_ocpstoragevolumeclaimlabel_summary; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpstoragevolumeclaimlabel_summary (key, "values") FROM stdin;
\.


--
-- Data for Name: reporting_ocpstoragevolumelabel_summary; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpstoragevolumelabel_summary (key, "values") FROM stdin;
\.


--
-- Data for Name: reporting_ocpusagelineitem; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpusagelineitem (id, namespace, pod, node, pod_usage_cpu_core_seconds, pod_limit_cpu_core_seconds, report_id, report_period_id, pod_limit_memory_byte_seconds, pod_request_cpu_core_seconds, pod_request_memory_byte_seconds, pod_usage_memory_byte_seconds, node_capacity_cpu_core_seconds, node_capacity_cpu_cores, node_capacity_memory_byte_seconds, node_capacity_memory_bytes, pod_labels, resource_id) FROM stdin;
\.


--
-- Data for Name: reporting_ocpusagelineitem_daily; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpusagelineitem_daily (id, namespace, pod, node, usage_start, usage_end, pod_usage_cpu_core_seconds, pod_limit_cpu_core_seconds, pod_limit_memory_byte_seconds, pod_request_cpu_core_seconds, pod_request_memory_byte_seconds, pod_usage_memory_byte_seconds, cluster_id, total_seconds, node_capacity_cpu_core_seconds, node_capacity_cpu_cores, node_capacity_memory_byte_seconds, node_capacity_memory_bytes, pod_labels, cluster_capacity_cpu_core_seconds, cluster_capacity_memory_byte_seconds, cluster_alias, resource_id, total_capacity_cpu_core_seconds, total_capacity_memory_byte_seconds) FROM stdin;
\.


--
-- Data for Name: reporting_ocpusagelineitem_daily_summary; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpusagelineitem_daily_summary (id, cluster_id, namespace, pod, node, usage_start, usage_end, pod_usage_cpu_core_hours, pod_request_cpu_core_hours, pod_limit_cpu_core_hours, pod_usage_memory_gigabyte_hours, pod_request_memory_gigabyte_hours, pod_limit_memory_gigabyte_hours, node_capacity_cpu_core_hours, node_capacity_cpu_cores, pod_charge_cpu_core_hours, pod_charge_memory_gigabyte_hours, node_capacity_memory_gigabyte_hours, node_capacity_memory_gigabytes, cluster_capacity_cpu_core_hours, cluster_capacity_memory_gigabyte_hours, pod_labels, cluster_alias, resource_id, total_capacity_cpu_core_hours, total_capacity_memory_gigabyte_hours) FROM stdin;
\.


--
-- Data for Name: reporting_ocpusagepodlabel_summary; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpusagepodlabel_summary (key, "values") FROM stdin;
\.


--
-- Data for Name: reporting_ocpusagereport; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpusagereport (id, interval_start, interval_end, report_period_id) FROM stdin;
\.


--
-- Data for Name: reporting_ocpusagereportperiod; Type: TABLE DATA; Schema: acct10001; Owner: postgres
--

COPY acct10001.reporting_ocpusagereportperiod (id, cluster_id, report_period_start, report_period_end, provider_id, summary_data_creation_datetime, summary_data_updated_datetime, derived_cost_datetime) FROM stdin;
\.


--
-- Data for Name: api_customer; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.api_customer (id, date_created, uuid, account_id, schema_name) FROM stdin;
1	2019-06-05 18:28:29.350659+00	57e8ec04-bad2-4c52-bc3e-1977b1fcccf3	10001	acct10001
\.


--
-- Data for Name: api_provider; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.api_provider (id, uuid, name, type, setup_complete, authentication_id, billing_source_id, created_by_id, customer_id) FROM stdin;
1	6e212746-484a-40cd-bba0-09a19d132d64	Test Provider	AWS	f	1	1	1	1
2	3c6e687e-1a09-4a05-970c-2ccf44b0952e	OCP Test Provider	OCP	f	2	\N	1	1
\.


--
-- Data for Name: api_providerauthentication; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.api_providerauthentication (id, uuid, provider_resource_name) FROM stdin;
1	7e4ec31b-7ced-4a17-9f7e-f77e9efa8fd6	arn:aws:iam::111111111111:role/CostManagement
2	5e421052-8e16-4f66-93d4-27223c4673f2	my-ocp-cluster-1
\.


--
-- Data for Name: api_providerbillingsource; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.api_providerbillingsource (id, uuid, bucket) FROM stdin;
1	75b17096-319a-45ec-92c1-18dbd5e78f94	test-bucket
\.


--
-- Data for Name: api_providerstatus; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.api_providerstatus (id, status, last_message, "timestamp", retries, provider_id) FROM stdin;
\.


--
-- Data for Name: api_tenant; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.api_tenant (id, schema_name) FROM stdin;
1	acct10001
\.


--
-- Data for Name: api_user; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.api_user (id, uuid, username, email, date_created, is_active, customer_id) FROM stdin;
1	6bc3dccd-b8fc-47d2-9e97-507c4132746c	user_dev	user_dev@foo.com	2019-06-05 18:28:32.267027+00	t	1
\.


--
-- Data for Name: api_userpreference; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.api_userpreference (id, uuid, preference, name, description, user_id) FROM stdin;
1	794e8969-e721-494a-b7d8-88c97be1220c	{"currency": "USD"}	currency	default preference	1
2	f65a849e-13d8-4b4d-b9e8-b8f4bfb7c991	{"timezone": "UTC"}	timezone	default preference	1
3	68041cba-247c-4e09-be38-6983d8b643c8	{"locale": "en_US.UTF-8"}	locale	default preference	1
\.


--
-- Data for Name: auth_group; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.auth_group (id, name) FROM stdin;
\.


--
-- Data for Name: auth_group_permissions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.auth_group_permissions (id, group_id, permission_id) FROM stdin;
\.


--
-- Data for Name: auth_permission; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.auth_permission (id, name, content_type_id, codename) FROM stdin;
1	Can add permission	1	add_permission
2	Can change permission	1	change_permission
3	Can delete permission	1	delete_permission
4	Can view permission	1	view_permission
5	Can add group	2	add_group
6	Can change group	2	change_group
7	Can delete group	2	delete_group
8	Can view group	2	view_group
9	Can add user	3	add_user
10	Can change user	3	change_user
11	Can delete user	3	delete_user
12	Can view user	3	view_user
13	Can add content type	4	add_contenttype
14	Can change content type	4	change_contenttype
15	Can delete content type	4	delete_contenttype
16	Can view content type	4	view_contenttype
17	Can add session	5	add_session
18	Can change session	5	change_session
19	Can delete session	5	delete_session
20	Can view session	5	view_session
21	Can add customer	6	add_customer
22	Can change customer	6	change_customer
23	Can delete customer	6	delete_customer
24	Can view customer	6	view_customer
25	Can add provider authentication	7	add_providerauthentication
26	Can change provider authentication	7	change_providerauthentication
27	Can delete provider authentication	7	delete_providerauthentication
28	Can view provider authentication	7	view_providerauthentication
29	Can add provider billing source	8	add_providerbillingsource
30	Can change provider billing source	8	change_providerbillingsource
31	Can delete provider billing source	8	delete_providerbillingsource
32	Can view provider billing source	8	view_providerbillingsource
33	Can add tenant	9	add_tenant
34	Can change tenant	9	change_tenant
35	Can delete tenant	9	delete_tenant
36	Can view tenant	9	view_tenant
37	Can add user	10	add_user
38	Can change user	10	change_user
39	Can delete user	10	delete_user
40	Can view user	10	view_user
41	Can add user preference	11	add_userpreference
42	Can change user preference	11	change_userpreference
43	Can delete user preference	11	delete_userpreference
44	Can view user preference	11	view_userpreference
45	Can add provider	12	add_provider
46	Can change provider	12	change_provider
47	Can delete provider	12	delete_provider
48	Can view provider	12	view_provider
49	Can add provider status	13	add_providerstatus
50	Can change provider status	13	change_providerstatus
51	Can delete provider status	13	delete_providerstatus
52	Can view provider status	13	view_providerstatus
53	Can add cost model metrics map	14	add_costmodelmetricsmap
54	Can change cost model metrics map	14	change_costmodelmetricsmap
55	Can delete cost model metrics map	14	delete_costmodelmetricsmap
56	Can view cost model metrics map	14	view_costmodelmetricsmap
57	Can add aws account alias	15	add_awsaccountalias
58	Can change aws account alias	15	change_awsaccountalias
59	Can delete aws account alias	15	delete_awsaccountalias
60	Can view aws account alias	15	view_awsaccountalias
61	Can add aws cost entry	16	add_awscostentry
62	Can change aws cost entry	16	change_awscostentry
63	Can delete aws cost entry	16	delete_awscostentry
64	Can view aws cost entry	16	view_awscostentry
65	Can add aws cost entry bill	17	add_awscostentrybill
66	Can change aws cost entry bill	17	change_awscostentrybill
67	Can delete aws cost entry bill	17	delete_awscostentrybill
68	Can view aws cost entry bill	17	view_awscostentrybill
69	Can add aws cost entry line item	18	add_awscostentrylineitem
70	Can change aws cost entry line item	18	change_awscostentrylineitem
71	Can delete aws cost entry line item	18	delete_awscostentrylineitem
72	Can view aws cost entry line item	18	view_awscostentrylineitem
73	Can add aws cost entry line item daily	19	add_awscostentrylineitemdaily
74	Can change aws cost entry line item daily	19	change_awscostentrylineitemdaily
75	Can delete aws cost entry line item daily	19	delete_awscostentrylineitemdaily
76	Can view aws cost entry line item daily	19	view_awscostentrylineitemdaily
77	Can add aws cost entry line item daily summary	20	add_awscostentrylineitemdailysummary
78	Can change aws cost entry line item daily summary	20	change_awscostentrylineitemdailysummary
79	Can delete aws cost entry line item daily summary	20	delete_awscostentrylineitemdailysummary
80	Can view aws cost entry line item daily summary	20	view_awscostentrylineitemdailysummary
81	Can add aws cost entry pricing	21	add_awscostentrypricing
82	Can change aws cost entry pricing	21	change_awscostentrypricing
83	Can delete aws cost entry pricing	21	delete_awscostentrypricing
84	Can view aws cost entry pricing	21	view_awscostentrypricing
85	Can add aws cost entry product	22	add_awscostentryproduct
86	Can change aws cost entry product	22	change_awscostentryproduct
87	Can delete aws cost entry product	22	delete_awscostentryproduct
88	Can view aws cost entry product	22	view_awscostentryproduct
89	Can add aws cost entry reservation	23	add_awscostentryreservation
90	Can change aws cost entry reservation	23	change_awscostentryreservation
91	Can delete aws cost entry reservation	23	delete_awscostentryreservation
92	Can view aws cost entry reservation	23	view_awscostentryreservation
93	Can add ocp usage line item	24	add_ocpusagelineitem
94	Can change ocp usage line item	24	change_ocpusagelineitem
95	Can delete ocp usage line item	24	delete_ocpusagelineitem
96	Can view ocp usage line item	24	view_ocpusagelineitem
97	Can add ocp usage line item daily	25	add_ocpusagelineitemdaily
98	Can change ocp usage line item daily	25	change_ocpusagelineitemdaily
99	Can delete ocp usage line item daily	25	delete_ocpusagelineitemdaily
100	Can view ocp usage line item daily	25	view_ocpusagelineitemdaily
101	Can add ocp usage report period	26	add_ocpusagereportperiod
102	Can change ocp usage report period	26	change_ocpusagereportperiod
103	Can delete ocp usage report period	26	delete_ocpusagereportperiod
104	Can view ocp usage report period	26	view_ocpusagereportperiod
105	Can add ocp usage report	27	add_ocpusagereport
106	Can change ocp usage report	27	change_ocpusagereport
107	Can delete ocp usage report	27	delete_ocpusagereport
108	Can view ocp usage report	27	view_ocpusagereport
109	Can add ocp usage line item daily summary	28	add_ocpusagelineitemdailysummary
110	Can change ocp usage line item daily summary	28	change_ocpusagelineitemdailysummary
111	Can delete ocp usage line item daily summary	28	delete_ocpusagelineitemdailysummary
112	Can view ocp usage line item daily summary	28	view_ocpusagelineitemdailysummary
113	Can add ocp usage pod label summary	29	add_ocpusagepodlabelsummary
114	Can change ocp usage pod label summary	29	change_ocpusagepodlabelsummary
115	Can delete ocp usage pod label summary	29	delete_ocpusagepodlabelsummary
116	Can view ocp usage pod label summary	29	view_ocpusagepodlabelsummary
117	Can add aws tags summary	30	add_awstagssummary
118	Can change aws tags summary	30	change_awstagssummary
119	Can delete aws tags summary	30	delete_awstagssummary
120	Can view aws tags summary	30	view_awstagssummary
121	Can add ocpaws cost line item daily summary	31	add_ocpawscostlineitemdailysummary
122	Can change ocpaws cost line item daily summary	31	change_ocpawscostlineitemdailysummary
123	Can delete ocpaws cost line item daily summary	31	delete_ocpawscostlineitemdailysummary
124	Can view ocpaws cost line item daily summary	31	view_ocpawscostlineitemdailysummary
125	Can add ocp storage line item	32	add_ocpstoragelineitem
126	Can change ocp storage line item	32	change_ocpstoragelineitem
127	Can delete ocp storage line item	32	delete_ocpstoragelineitem
128	Can view ocp storage line item	32	view_ocpstoragelineitem
129	Can add ocp storage volume claim label summary	33	add_ocpstoragevolumeclaimlabelsummary
130	Can change ocp storage volume claim label summary	33	change_ocpstoragevolumeclaimlabelsummary
131	Can delete ocp storage volume claim label summary	33	delete_ocpstoragevolumeclaimlabelsummary
132	Can view ocp storage volume claim label summary	33	view_ocpstoragevolumeclaimlabelsummary
133	Can add ocp storage volume label summary	34	add_ocpstoragevolumelabelsummary
134	Can change ocp storage volume label summary	34	change_ocpstoragevolumelabelsummary
135	Can delete ocp storage volume label summary	34	delete_ocpstoragevolumelabelsummary
136	Can view ocp storage volume label summary	34	view_ocpstoragevolumelabelsummary
137	Can add ocp storage line item daily	35	add_ocpstoragelineitemdaily
138	Can change ocp storage line item daily	35	change_ocpstoragelineitemdaily
139	Can delete ocp storage line item daily	35	delete_ocpstoragelineitemdaily
140	Can view ocp storage line item daily	35	view_ocpstoragelineitemdaily
141	Can add ocp storage line item daily summary	36	add_ocpstoragelineitemdailysummary
142	Can change ocp storage line item daily summary	36	change_ocpstoragelineitemdailysummary
143	Can delete ocp storage line item daily summary	36	delete_ocpstoragelineitemdailysummary
144	Can view ocp storage line item daily summary	36	view_ocpstoragelineitemdailysummary
145	Can add cost summary	37	add_costsummary
146	Can change cost summary	37	change_costsummary
147	Can delete cost summary	37	delete_costsummary
148	Can view cost summary	37	view_costsummary
149	Can add ocpaws cost line item project daily summary	38	add_ocpawscostlineitemprojectdailysummary
150	Can change ocpaws cost line item project daily summary	38	change_ocpawscostlineitemprojectdailysummary
151	Can delete ocpaws cost line item project daily summary	38	delete_ocpawscostlineitemprojectdailysummary
152	Can view ocpaws cost line item project daily summary	38	view_ocpawscostlineitemprojectdailysummary
153	Can add cost usage report status	39	add_costusagereportstatus
154	Can change cost usage report status	39	change_costusagereportstatus
155	Can delete cost usage report status	39	delete_costusagereportstatus
156	Can view cost usage report status	39	view_costusagereportstatus
157	Can add region mapping	40	add_regionmapping
158	Can change region mapping	40	change_regionmapping
159	Can delete region mapping	40	delete_regionmapping
160	Can view region mapping	40	view_regionmapping
161	Can add report column map	41	add_reportcolumnmap
162	Can change report column map	41	change_reportcolumnmap
163	Can delete report column map	41	delete_reportcolumnmap
164	Can view report column map	41	view_reportcolumnmap
165	Can add si unit scale	42	add_siunitscale
166	Can change si unit scale	42	change_siunitscale
167	Can delete si unit scale	42	delete_siunitscale
168	Can view si unit scale	42	view_siunitscale
169	Can add cost usage report manifest	43	add_costusagereportmanifest
170	Can change cost usage report manifest	43	change_costusagereportmanifest
171	Can delete cost usage report manifest	43	delete_costusagereportmanifest
172	Can view cost usage report manifest	43	view_costusagereportmanifest
173	Can add rate	44	add_rate
174	Can change rate	44	change_rate
175	Can delete rate	44	delete_rate
176	Can view rate	44	view_rate
177	Can add rate map	45	add_ratemap
178	Can change rate map	45	change_ratemap
179	Can delete rate map	45	delete_ratemap
180	Can view rate map	45	view_ratemap
\.


--
-- Data for Name: auth_user; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.auth_user (id, password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined) FROM stdin;
\.


--
-- Data for Name: auth_user_groups; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.auth_user_groups (id, user_id, group_id) FROM stdin;
\.


--
-- Data for Name: auth_user_user_permissions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.auth_user_user_permissions (id, user_id, permission_id) FROM stdin;
\.


--
-- Data for Name: cost_models_metrics_map; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cost_models_metrics_map (id, source_type, metric, label_metric, label_measurement, label_measurement_unit) FROM stdin;
1	OCP	cpu_core_usage_per_hour	CPU	Usage	core-hours
2	OCP	cpu_core_request_per_hour	CPU	Request	core-hours
3	OCP	memory_gb_usage_per_hour	Memory	Usage	GB-hours
4	OCP	memory_gb_request_per_hour	Memory	Request	GB-hours
5	OCP	storage_gb_usage_per_month	Storage	Usage	GB-month
6	OCP	storage_gb_request_per_month	Storage	Request	GB-month
\.


--
-- Data for Name: django_content_type; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.django_content_type (id, app_label, model) FROM stdin;
1	auth	permission
2	auth	group
3	auth	user
4	contenttypes	contenttype
5	sessions	session
6	api	customer
7	api	providerauthentication
8	api	providerbillingsource
9	api	tenant
10	api	user
11	api	userpreference
12	api	provider
13	api	providerstatus
14	api	costmodelmetricsmap
15	reporting	awsaccountalias
16	reporting	awscostentry
17	reporting	awscostentrybill
18	reporting	awscostentrylineitem
19	reporting	awscostentrylineitemdaily
20	reporting	awscostentrylineitemdailysummary
21	reporting	awscostentrypricing
22	reporting	awscostentryproduct
23	reporting	awscostentryreservation
24	reporting	ocpusagelineitem
25	reporting	ocpusagelineitemdaily
26	reporting	ocpusagereportperiod
27	reporting	ocpusagereport
28	reporting	ocpusagelineitemdailysummary
29	reporting	ocpusagepodlabelsummary
30	reporting	awstagssummary
31	reporting	ocpawscostlineitemdailysummary
32	reporting	ocpstoragelineitem
33	reporting	ocpstoragevolumeclaimlabelsummary
34	reporting	ocpstoragevolumelabelsummary
35	reporting	ocpstoragelineitemdaily
36	reporting	ocpstoragelineitemdailysummary
37	reporting	costsummary
38	reporting	ocpawscostlineitemprojectdailysummary
39	reporting_common	costusagereportstatus
40	reporting_common	regionmapping
41	reporting_common	reportcolumnmap
42	reporting_common	siunitscale
43	reporting_common	costusagereportmanifest
44	rates	rate
45	rates	ratemap
\.


--
-- Data for Name: django_migrations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.django_migrations (id, app, name, applied) FROM stdin;
1	api	0001_initial	2019-06-05 18:27:25.405482+00
2	api	0002_auto_20180926_1905	2019-06-05 18:27:25.407977+00
3	api	0003_auto_20181008_1819	2019-06-05 18:27:25.409791+00
4	api	0004_auto_20181012_1507	2019-06-05 18:27:25.411536+00
5	api	0005_auto_20181109_2121	2019-06-05 18:27:25.413545+00
6	api	0006_delete_rate	2019-06-05 18:27:25.415883+00
7	api	0007_auto_20181213_1940	2019-06-05 18:27:25.418638+00
8	api	0008_auto_20190305_2015	2019-06-05 18:27:25.420831+00
9	api	0009_providerstatus	2019-06-05 18:27:25.489845+00
10	api	0010_costmodelmetricsmap	2019-06-05 18:27:25.523589+00
11	contenttypes	0001_initial	2019-06-05 18:27:25.542779+00
12	contenttypes	0002_remove_content_type_name	2019-06-05 18:27:25.560098+00
13	auth	0001_initial	2019-06-05 18:27:25.611744+00
14	auth	0002_alter_permission_name_max_length	2019-06-05 18:27:25.671773+00
15	auth	0003_alter_user_email_max_length	2019-06-05 18:27:25.683472+00
16	auth	0004_alter_user_username_opts	2019-06-05 18:27:25.693888+00
17	auth	0005_alter_user_last_login_null	2019-06-05 18:27:25.706454+00
18	auth	0006_require_contenttypes_0002	2019-06-05 18:27:25.710296+00
19	auth	0007_alter_validators_add_error_messages	2019-06-05 18:27:25.721562+00
20	auth	0008_alter_user_username_max_length	2019-06-05 18:27:25.738425+00
21	auth	0009_alter_user_last_name_max_length	2019-06-05 18:27:25.749418+00
22	auth	0010_alter_group_name_max_length	2019-06-05 18:27:25.761781+00
23	auth	0011_update_proxy_permissions	2019-06-05 18:27:25.777879+00
24	rates	0001_initial	2019-06-05 18:27:25.786197+00
25	rates	0002_auto_20181205_1810	2019-06-05 18:27:25.792207+00
26	rates	0003_auto_20190213_2040	2019-06-05 18:27:25.797925+00
27	rates	0004_auto_20190301_1850	2019-06-05 18:27:25.803224+00
28	rates	0005_auto_20190422_1415	2019-06-05 18:27:25.816165+00
29	reporting	0001_initial	2019-06-05 18:27:26.744781+00
30	reporting	0002_auto_20180926_1818	2019-06-05 18:27:26.746851+00
31	reporting	0003_auto_20180928_1840	2019-06-05 18:27:26.749224+00
32	reporting	0004_auto_20181003_1633	2019-06-05 18:27:26.75108+00
33	reporting	0005_auto_20181003_1416	2019-06-05 18:27:26.753065+00
34	reporting	0006_awscostentrylineitemaggregates_account_alias	2019-06-05 18:27:26.75508+00
35	reporting	0007_awscostentrybill_provider_id	2019-06-05 18:27:26.757087+00
36	reporting	0008_auto_20181012_1724	2019-06-05 18:27:26.759088+00
37	reporting	0009_auto_20181016_1940	2019-06-05 18:27:26.760869+00
38	reporting	0010_auto_20181017_1659	2019-06-05 18:27:26.762626+00
39	reporting	0011_auto_20181018_1811	2019-06-05 18:27:26.76456+00
40	reporting	0012_auto_20181106_1502	2019-06-05 18:27:26.766446+00
41	reporting	0013_auto_20181107_1956	2019-06-05 18:27:26.768489+00
42	reporting	0014_auto_20181108_0207	2019-06-05 18:27:26.770532+00
43	reporting	0015_auto_20181109_1618	2019-06-05 18:27:26.772393+00
44	reporting	0016_delete_rate	2019-06-05 18:27:26.774266+00
45	reporting	0017_auto_20181121_1444	2019-06-05 18:27:26.776114+00
46	reporting	0018_auto_20181129_0217	2019-06-05 18:27:26.77793+00
47	reporting	0019_auto_20181206_2138	2019-06-05 18:27:26.779857+00
48	reporting	0020_auto_20181211_1557	2019-06-05 18:27:26.781613+00
49	reporting	0021_auto_20181212_1816	2019-06-05 18:27:26.783319+00
50	reporting	0022_auto_20181221_1617	2019-06-05 18:27:26.784973+00
51	reporting	0023_awscostentrylineitemdailysummary_tags	2019-06-05 18:27:26.78664+00
52	reporting	0024_ocpusagepodlabelsummary	2019-06-05 18:27:26.789751+00
53	reporting	0025_auto_20190128_1825	2019-06-05 18:27:26.792014+00
54	reporting	0026_auto_20190130_1746	2019-06-05 18:27:26.793866+00
55	reporting	0027_auto_20190205_1659	2019-06-05 18:27:26.795658+00
56	reporting	0028_auto_20190205_2022	2019-06-05 18:27:26.79745+00
57	reporting	0029_auto_20190207_1526	2019-06-05 18:27:26.7997+00
58	reporting	0030_auto_20190208_0159	2019-06-05 18:27:26.80148+00
59	reporting	0031_ocpawscostlineitemdailysummary_instance_type	2019-06-05 18:27:26.80331+00
60	reporting	0032_auto_20190213_2152	2019-06-05 18:27:26.80516+00
61	reporting	0033_auto_20190214_1637	2019-06-05 18:27:26.806915+00
62	reporting	0034_ocpstoragevolumeclaimlabelsummary_ocpstoragevolumelabelsummary	2019-06-05 18:27:26.8087+00
63	reporting	0035_ocpawscostlineitemdailysummary_currency_code	2019-06-05 18:27:26.810535+00
64	reporting	0036_auto_20190215_2058	2019-06-05 18:27:26.812894+00
65	reporting	0037_auto_20190218_2054	2019-06-05 18:27:26.814967+00
66	reporting	0038_auto_20190220_1511	2019-06-05 18:27:26.816953+00
67	reporting	0039_auto_20190220_1610	2019-06-05 18:27:26.818889+00
68	reporting	0040_auto_20190226_1538	2019-06-05 18:27:26.820796+00
69	reporting	0041_auto_20190301_1548	2019-06-05 18:27:26.822766+00
70	reporting	0042_awscostentrylineitemdailysummary_resource_ids	2019-06-05 18:27:26.824749+00
71	reporting	0043_auto_20190228_2016	2019-06-05 18:27:26.826664+00
72	reporting	0044_costsummary	2019-06-05 18:27:26.828516+00
73	reporting	0045_auto_20190308_1839	2019-06-05 18:27:26.830358+00
74	reporting	0046_auto_20190313_1533	2019-06-05 18:27:26.833228+00
75	reporting	0047_auto_20190311_2021	2019-06-05 18:27:26.835384+00
76	reporting	0048_auto_20190313_1804	2019-06-05 18:27:26.837333+00
77	reporting	0049_auto_20190314_2016	2019-06-05 18:27:26.8395+00
78	reporting	0050_auto_20190315_1339	2019-06-05 18:27:26.84134+00
79	reporting	0051_auto_20190315_1458	2019-06-05 18:27:26.869719+00
80	reporting	0052_auto_20190318_1741	2019-06-05 18:27:26.876727+00
81	reporting	0053_auto_20190412_1529	2019-06-05 18:27:26.887824+00
82	reporting	0054_delete_ocpawscostlineitemdaily	2019-06-05 18:27:26.892908+00
83	reporting	0055_auto_20190416_2025	2019-06-05 18:27:26.941165+00
84	reporting	0056_auto_20190418_1850	2019-06-05 18:27:26.998211+00
85	reporting	0057_auto_20190422_1910	2019-06-05 18:27:27.032021+00
86	reporting	0058_auto_20190422_1915	2019-06-05 18:27:27.062821+00
87	reporting	0059_auto_20190422_1924	2019-06-05 18:27:27.088963+00
88	reporting	0060_auto_20190430_1926	2019-06-05 18:27:27.163217+00
89	reporting	0061_auto_20190501_1854	2019-06-05 18:27:27.228156+00
90	reporting	0062_auto_20190604_1840	2019-06-05 18:27:27.25305+00
91	reporting_common	0001_initial	2019-06-05 18:27:27.824276+00
92	reporting_common	0002_auto_20180926_1905	2019-06-05 18:27:27.82598+00
93	reporting_common	0003_auto_20180928_1732	2019-06-05 18:27:27.827524+00
94	reporting_common	0004_auto_20181003_1859	2019-06-05 18:27:27.829319+00
95	reporting_common	0005_auto_20181127_2046	2019-06-05 18:27:27.831459+00
96	reporting_common	0006_auto_20190208_0316	2019-06-05 18:27:27.833442+00
97	reporting_common	0007_auto_20190208_0316	2019-06-05 18:27:27.836086+00
98	reporting_common	0008_auto_20190412_1330	2019-06-05 18:27:27.899138+00
99	reporting_common	0009_costusagereportstatus_history	2019-06-05 18:27:27.914412+00
100	reporting_common	0010_remove_costusagereportstatus_history	2019-06-05 18:27:27.924519+00
101	sessions	0001_initial	2019-06-05 18:27:27.940861+00
102	api	0001_initial_squashed_0008_auto_20190305_2015	2019-06-05 18:27:27.951722+00
103	reporting	0001_initial_squashed_0050_auto_20190315_1339	2019-06-05 18:27:27.954484+00
104	reporting_common	0001_initial_squashed_0007_auto_20190208_0316	2019-06-05 18:27:27.957327+00
\.


--
-- Data for Name: django_session; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.django_session (session_key, session_data, expire_date) FROM stdin;
\.


--
-- Data for Name: region_mapping; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.region_mapping (id, region, region_name) FROM stdin;
\.


--
-- Data for Name: reporting_common_costusagereportmanifest; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reporting_common_costusagereportmanifest (id, assembly_id, manifest_creation_datetime, manifest_updated_datetime, billing_period_start_datetime, num_processed_files, num_total_files, provider_id) FROM stdin;
\.


--
-- Data for Name: reporting_common_costusagereportstatus; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reporting_common_costusagereportstatus (id, report_name, last_completed_datetime, last_started_datetime, etag, manifest_id) FROM stdin;
\.


--
-- Data for Name: reporting_common_reportcolumnmap; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reporting_common_reportcolumnmap (id, provider_type, provider_column_name, database_table, database_column, report_type) FROM stdin;
88	OCP	cluster_id	reporting_ocpusagereportperiod	cluster_id	OCP-CPU-MEM
89	OCP	report_period_start	reporting_ocpusagereportperiod	report_period_start	OCP-CPU-MEM
90	OCP	report_period_end	reporting_ocpusagereportperiod	report_period_end	OCP-CPU-MEM
91	OCP	interval_start	reporting_ocpusagereport	interval_start	OCP-CPU-MEM
92	OCP	interval_end	reporting_ocpusagereport	interval_end	OCP-CPU-MEM
93	OCP	namespace	reporting_ocpusagelineitem	namespace	OCP-CPU-MEM
94	OCP	pod	reporting_ocpusagelineitem	pod	OCP-CPU-MEM
95	OCP	node	reporting_ocpusagelineitem	node	OCP-CPU-MEM
96	OCP	pod_usage_cpu_core_seconds	reporting_ocpusagelineitem	pod_usage_cpu_core_seconds	OCP-CPU-MEM
97	OCP	pod_request_cpu_core_seconds	reporting_ocpusagelineitem	pod_request_cpu_core_seconds	OCP-CPU-MEM
98	OCP	pod_limit_cpu_core_seconds	reporting_ocpusagelineitem	pod_limit_cpu_core_seconds	OCP-CPU-MEM
99	OCP	pod_usage_memory_byte_seconds	reporting_ocpusagelineitem	pod_usage_memory_byte_seconds	OCP-CPU-MEM
100	OCP	pod_request_memory_byte_seconds	reporting_ocpusagelineitem	pod_request_memory_byte_seconds	OCP-CPU-MEM
101	OCP	pod_limit_memory_byte_seconds	reporting_ocpusagelineitem	pod_limit_memory_byte_seconds	OCP-CPU-MEM
102	OCP	node_capacity_cpu_cores	reporting_ocpusagelineitem	node_capacity_cpu_cores	OCP-CPU-MEM
103	OCP	node_capacity_cpu_core_seconds	reporting_ocpusagelineitem	node_capacity_cpu_core_seconds	OCP-CPU-MEM
104	OCP	node_capacity_memory_bytes	reporting_ocpusagelineitem	node_capacity_memory_bytes	OCP-CPU-MEM
105	OCP	node_capacity_memory_byte_seconds	reporting_ocpusagelineitem	node_capacity_memory_byte_seconds	OCP-CPU-MEM
106	OCP	resource_id	reporting_ocpusagelineitem	resource_id	OCP-CPU-MEM
107	OCP	pod_labels	reporting_ocpusagelineitem	pod_labels	OCP-CPU-MEM
108	OCP	pod	reporting_ocpstoragelineitem	pod	OCP-STORAGE
109	OCP	namespace	reporting_ocpstoragelineitem	namespace	OCP-STORAGE
110	OCP	persistentvolumeclaim	reporting_ocpstoragelineitem	persistentvolumeclaim	OCP-STORAGE
111	OCP	persistentvolume	reporting_ocpstoragelineitem	persistentvolume	OCP-STORAGE
112	OCP	storageclass	reporting_ocpstoragelineitem	storageclass	OCP-STORAGE
113	OCP	persistentvolumeclaim_capacity_bytes	reporting_ocpstoragelineitem	persistentvolumeclaim_capacity_bytes	OCP-STORAGE
114	OCP	persistentvolumeclaim_capacity_byte_seconds	reporting_ocpstoragelineitem	persistentvolumeclaim_capacity_byte_seconds	OCP-STORAGE
115	OCP	volume_request_storage_byte_seconds	reporting_ocpstoragelineitem	volume_request_storage_byte_seconds	OCP-STORAGE
116	OCP	persistentvolumeclaim_usage_byte_seconds	reporting_ocpstoragelineitem	persistentvolumeclaim_usage_byte_seconds	OCP-STORAGE
117	OCP	persistentvolume_labels	reporting_ocpstoragelineitem	persistentvolume_labels	OCP-STORAGE
118	OCP	persistentvolumeclaim_labels	reporting_ocpstoragelineitem	persistentvolumeclaim_labels	OCP-STORAGE
119	AWS	bill/BillingEntity	reporting_awscostentrybill	billing_resource	AWS-CUR
120	AWS	bill/BillType	reporting_awscostentrybill	bill_type	AWS-CUR
121	AWS	bill/PayerAccountId	reporting_awscostentrybill	payer_account_id	AWS-CUR
122	AWS	bill/BillingPeriodStartDate	reporting_awscostentrybill	billing_period_start	AWS-CUR
123	AWS	bill/BillingPeriodEndDate	reporting_awscostentrybill	billing_period_end	AWS-CUR
124	AWS	bill/InvoiceId	reporting_awscostentrylineitem	invoice_id	AWS-CUR
125	AWS	lineItem/LineItemType	reporting_awscostentrylineitem	line_item_type	AWS-CUR
126	AWS	lineItem/UsageAccountId	reporting_awscostentrylineitem	usage_account_id	AWS-CUR
127	AWS	lineItem/UsageStartDate	reporting_awscostentrylineitem	usage_start	AWS-CUR
128	AWS	lineItem/UsageEndDate	reporting_awscostentrylineitem	usage_end	AWS-CUR
129	AWS	lineItem/ProductCode	reporting_awscostentrylineitem	product_code	AWS-CUR
130	AWS	lineItem/UsageType	reporting_awscostentrylineitem	usage_type	AWS-CUR
131	AWS	lineItem/Operation	reporting_awscostentrylineitem	operation	AWS-CUR
132	AWS	lineItem/AvailabilityZone	reporting_awscostentrylineitem	availability_zone	AWS-CUR
133	AWS	lineItem/ResourceId	reporting_awscostentrylineitem	resource_id	AWS-CUR
134	AWS	lineItem/UsageAmount	reporting_awscostentrylineitem	usage_amount	AWS-CUR
135	AWS	lineItem/NormalizationFactor	reporting_awscostentrylineitem	normalization_factor	AWS-CUR
136	AWS	lineItem/NormalizedUsageAmount	reporting_awscostentrylineitem	normalized_usage_amount	AWS-CUR
137	AWS	lineItem/CurrencyCode	reporting_awscostentrylineitem	currency_code	AWS-CUR
138	AWS	lineItem/UnblendedRate	reporting_awscostentrylineitem	unblended_rate	AWS-CUR
139	AWS	lineItem/UnblendedCost	reporting_awscostentrylineitem	unblended_cost	AWS-CUR
140	AWS	lineItem/BlendedRate	reporting_awscostentrylineitem	blended_rate	AWS-CUR
141	AWS	lineItem/BlendedCost	reporting_awscostentrylineitem	blended_cost	AWS-CUR
142	AWS	lineItem/TaxType	reporting_awscostentrylineitem	tax_type	AWS-CUR
143	AWS	pricing/publicOnDemandCost	reporting_awscostentrylineitem	public_on_demand_cost	AWS-CUR
144	AWS	pricing/publicOnDemandRate	reporting_awscostentrylineitem	public_on_demand_rate	AWS-CUR
145	AWS	pricing/term	reporting_awscostentrypricing	term	AWS-CUR
146	AWS	pricing/unit	reporting_awscostentrypricing	unit	AWS-CUR
147	AWS	product/sku	reporting_awscostentryproduct	sku	AWS-CUR
148	AWS	product/ProductName	reporting_awscostentryproduct	product_name	AWS-CUR
149	AWS	product/productFamily	reporting_awscostentryproduct	product_family	AWS-CUR
150	AWS	product/servicecode	reporting_awscostentryproduct	service_code	AWS-CUR
151	AWS	product/region	reporting_awscostentryproduct	region	AWS-CUR
152	AWS	product/instanceType	reporting_awscostentryproduct	instance_type	AWS-CUR
153	AWS	product/memory	reporting_awscostentryproduct	memory	AWS-CUR
154	AWS	product/memory_unit	reporting_awscostentryproduct	memory_unit	AWS-CUR
155	AWS	product/vcpu	reporting_awscostentryproduct	vcpu	AWS-CUR
156	AWS	reservation/ReservationARN	reporting_awscostentryreservation	reservation_arn	AWS-CUR
157	AWS	reservation/NumberOfReservations	reporting_awscostentryreservation	number_of_reservations	AWS-CUR
158	AWS	reservation/UnitsPerReservation	reporting_awscostentryreservation	units_per_reservation	AWS-CUR
159	AWS	reservation/StartTime	reporting_awscostentryreservation	start_time	AWS-CUR
160	AWS	reservation/EndTime	reporting_awscostentryreservation	end_time	AWS-CUR
161	AWS	reservation/AmortizedUpfrontFeeForBillingPeriod	reporting_awscostentrylineitem	reservation_amortized_upfront_fee	AWS-CUR
162	AWS	reservation/AmortizedUpfrontCostForUsage	reporting_awscostentrylineitem	reservation_amortized_upfront_cost_for_usage	AWS-CUR
163	AWS	reservation/RecurringFeeForUsage	reporting_awscostentrylineitem	reservation_recurring_fee_for_usage	AWS-CUR
164	AWS	reservation/UnusedQuantity	reporting_awscostentrylineitem	reservation_unused_quantity	AWS-CUR
165	AWS	reservation/UnusedRecurringFee	reporting_awscostentrylineitem	reservation_unused_recurring_fee	AWS-CUR
\.


--
-- Data for Name: si_unit_scale; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.si_unit_scale (id, prefix, prefix_symbol, multiplying_factor) FROM stdin;
\.


--
-- Name: django_migrations_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.django_migrations_id_seq', 104, true);


--
-- Name: rates_rate_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.rates_rate_id_seq', 1, false);


--
-- Name: rates_ratemap_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.rates_ratemap_id_seq', 1, false);


--
-- Name: reporting_awsaccountalias_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_awsaccountalias_id_seq', 1, false);


--
-- Name: reporting_awscostentry_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_awscostentry_id_seq', 1, false);


--
-- Name: reporting_awscostentrybill_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_awscostentrybill_id_seq', 1, false);


--
-- Name: reporting_awscostentrylineitem_daily_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_awscostentrylineitem_daily_id_seq', 1, false);


--
-- Name: reporting_awscostentrylineitem_daily_summary_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_awscostentrylineitem_daily_summary_id_seq', 1, false);


--
-- Name: reporting_awscostentrylineitem_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_awscostentrylineitem_id_seq', 1, false);


--
-- Name: reporting_awscostentrypricing_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_awscostentrypricing_id_seq', 1, false);


--
-- Name: reporting_awscostentryproduct_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_awscostentryproduct_id_seq', 1, false);


--
-- Name: reporting_awscostentryreservation_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_awscostentryreservation_id_seq', 1, false);


--
-- Name: reporting_ocpawscostlineitem_daily_summary_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_ocpawscostlineitem_daily_summary_id_seq', 1, false);


--
-- Name: reporting_ocpawscostlineitem_project_daily_summary_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_ocpawscostlineitem_project_daily_summary_id_seq', 1, false);


--
-- Name: reporting_ocpcosts_summary_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_ocpcosts_summary_id_seq', 1, false);


--
-- Name: reporting_ocpstoragelineitem_daily_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_ocpstoragelineitem_daily_id_seq', 1, false);


--
-- Name: reporting_ocpstoragelineitem_daily_summary_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_ocpstoragelineitem_daily_summary_id_seq', 1, false);


--
-- Name: reporting_ocpstoragelineitem_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_ocpstoragelineitem_id_seq', 1, false);


--
-- Name: reporting_ocpusagelineitem_daily_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_ocpusagelineitem_daily_id_seq', 1, false);


--
-- Name: reporting_ocpusagelineitem_daily_summary_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_ocpusagelineitem_daily_summary_id_seq', 1, false);


--
-- Name: reporting_ocpusagelineitem_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_ocpusagelineitem_id_seq', 1, false);


--
-- Name: reporting_ocpusagereport_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_ocpusagereport_id_seq', 1, false);


--
-- Name: reporting_ocpusagereportperiod_id_seq; Type: SEQUENCE SET; Schema: acct10001; Owner: postgres
--

SELECT pg_catalog.setval('acct10001.reporting_ocpusagereportperiod_id_seq', 1, false);


--
-- Name: api_customer_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.api_customer_id_seq', 1, true);


--
-- Name: api_provider_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.api_provider_id_seq', 2, true);


--
-- Name: api_providerauthentication_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.api_providerauthentication_id_seq', 2, true);


--
-- Name: api_providerbillingsource_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.api_providerbillingsource_id_seq', 1, true);


--
-- Name: api_providerstatus_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.api_providerstatus_id_seq', 1, false);


--
-- Name: api_tenant_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.api_tenant_id_seq', 1, true);


--
-- Name: api_user_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.api_user_id_seq', 1, true);


--
-- Name: api_userpreference_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.api_userpreference_id_seq', 3, true);


--
-- Name: auth_group_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.auth_group_id_seq', 1, false);


--
-- Name: auth_group_permissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.auth_group_permissions_id_seq', 1, false);


--
-- Name: auth_permission_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.auth_permission_id_seq', 180, true);


--
-- Name: auth_user_groups_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.auth_user_groups_id_seq', 1, false);


--
-- Name: auth_user_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.auth_user_id_seq', 1, false);


--
-- Name: auth_user_user_permissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.auth_user_user_permissions_id_seq', 1, false);


--
-- Name: cost_models_metrics_map_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.cost_models_metrics_map_id_seq', 6, true);


--
-- Name: django_content_type_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.django_content_type_id_seq', 45, true);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.django_migrations_id_seq', 104, true);


--
-- Name: region_mapping_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.region_mapping_id_seq', 1, false);


--
-- Name: reporting_common_costusagereportmanifest_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.reporting_common_costusagereportmanifest_id_seq', 1, false);


--
-- Name: reporting_common_costusagereportstatus_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.reporting_common_costusagereportstatus_id_seq', 1, false);


--
-- Name: reporting_common_reportcolumnmap_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.reporting_common_reportcolumnmap_id_seq', 165, true);


--
-- Name: si_unit_scale_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.si_unit_scale_id_seq', 1, false);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: rates_rate rates_rate_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.rates_rate
    ADD CONSTRAINT rates_rate_pkey PRIMARY KEY (id);


--
-- Name: rates_rate rates_rate_uuid_key; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.rates_rate
    ADD CONSTRAINT rates_rate_uuid_key UNIQUE (uuid);


--
-- Name: rates_ratemap rates_ratemap_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.rates_ratemap
    ADD CONSTRAINT rates_ratemap_pkey PRIMARY KEY (id);


--
-- Name: rates_ratemap rates_ratemap_provider_uuid_rate_id_e065f227_uniq; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.rates_ratemap
    ADD CONSTRAINT rates_ratemap_provider_uuid_rate_id_e065f227_uniq UNIQUE (provider_uuid, rate_id);


--
-- Name: reporting_awsaccountalias reporting_awsaccountalias_account_id_key; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awsaccountalias
    ADD CONSTRAINT reporting_awsaccountalias_account_id_key UNIQUE (account_id);


--
-- Name: reporting_awsaccountalias reporting_awsaccountalias_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awsaccountalias
    ADD CONSTRAINT reporting_awsaccountalias_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentry reporting_awscostentry_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentry
    ADD CONSTRAINT reporting_awscostentry_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentrybill reporting_awscostentrybi_bill_type_payer_account__6f101061_uniq; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrybill
    ADD CONSTRAINT reporting_awscostentrybi_bill_type_payer_account__6f101061_uniq UNIQUE (bill_type, payer_account_id, billing_period_start, provider_id);


--
-- Name: reporting_awscostentrybill reporting_awscostentrybill_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrybill
    ADD CONSTRAINT reporting_awscostentrybill_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentrylineitem_daily reporting_awscostentrylineitem_daily_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem_daily
    ADD CONSTRAINT reporting_awscostentrylineitem_daily_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentrylineitem_daily_summary reporting_awscostentrylineitem_daily_summary_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem_daily_summary
    ADD CONSTRAINT reporting_awscostentrylineitem_daily_summary_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentrylineitem reporting_awscostentrylineitem_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostentrylineitem_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentryproduct reporting_awscostentrypr_sku_product_name_region_fea902ae_uniq; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentryproduct
    ADD CONSTRAINT reporting_awscostentrypr_sku_product_name_region_fea902ae_uniq UNIQUE (sku, product_name, region);


--
-- Name: reporting_awscostentrypricing reporting_awscostentrypricing_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrypricing
    ADD CONSTRAINT reporting_awscostentrypricing_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentrypricing reporting_awscostentrypricing_term_unit_c3978af3_uniq; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrypricing
    ADD CONSTRAINT reporting_awscostentrypricing_term_unit_c3978af3_uniq UNIQUE (term, unit);


--
-- Name: reporting_awscostentryproduct reporting_awscostentryproduct_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentryproduct
    ADD CONSTRAINT reporting_awscostentryproduct_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentryreservation reporting_awscostentryreservation_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentryreservation
    ADD CONSTRAINT reporting_awscostentryreservation_pkey PRIMARY KEY (id);


--
-- Name: reporting_awscostentryreservation reporting_awscostentryreservation_reservation_arn_key; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentryreservation
    ADD CONSTRAINT reporting_awscostentryreservation_reservation_arn_key UNIQUE (reservation_arn);


--
-- Name: reporting_awstags_summary reporting_awstags_summary_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awstags_summary
    ADD CONSTRAINT reporting_awstags_summary_pkey PRIMARY KEY (key);


--
-- Name: reporting_ocpawscostlineitem_daily_summary reporting_ocpawscostlineitem_daily_summary_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpawscostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpawscostlineitem_daily_summary_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpawscostlineitem_project_daily_summary reporting_ocpawscostlineitem_project_daily_summary_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpawscostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpawscostlineitem_project_daily_summary_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpcosts_summary reporting_ocpcosts_summary_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpcosts_summary
    ADD CONSTRAINT reporting_ocpcosts_summary_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpstoragelineitem reporting_ocpstorageline_report_id_namespace_pers_9bf00103_uniq; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpstoragelineitem
    ADD CONSTRAINT reporting_ocpstorageline_report_id_namespace_pers_9bf00103_uniq UNIQUE (report_id, namespace, persistentvolumeclaim);


--
-- Name: reporting_ocpstoragelineitem_daily reporting_ocpstoragelineitem_daily_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpstoragelineitem_daily
    ADD CONSTRAINT reporting_ocpstoragelineitem_daily_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpstoragelineitem_daily_summary reporting_ocpstoragelineitem_daily_summary_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpstoragelineitem_daily_summary
    ADD CONSTRAINT reporting_ocpstoragelineitem_daily_summary_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpstoragelineitem reporting_ocpstoragelineitem_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpstoragelineitem
    ADD CONSTRAINT reporting_ocpstoragelineitem_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpstoragevolumeclaimlabel_summary reporting_ocpstoragevolumeclaimlabel_summary_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpstoragevolumeclaimlabel_summary
    ADD CONSTRAINT reporting_ocpstoragevolumeclaimlabel_summary_pkey PRIMARY KEY (key);


--
-- Name: reporting_ocpstoragevolumelabel_summary reporting_ocpstoragevolumelabel_summary_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpstoragevolumelabel_summary
    ADD CONSTRAINT reporting_ocpstoragevolumelabel_summary_pkey PRIMARY KEY (key);


--
-- Name: reporting_ocpusagelineitem reporting_ocpusagelineit_report_id_namespace_pod__dfc2c342_uniq; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagelineitem
    ADD CONSTRAINT reporting_ocpusagelineit_report_id_namespace_pod__dfc2c342_uniq UNIQUE (report_id, namespace, pod, node);


--
-- Name: reporting_ocpusagelineitem_daily reporting_ocpusagelineitem_daily_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagelineitem_daily
    ADD CONSTRAINT reporting_ocpusagelineitem_daily_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpusagelineitem_daily_summary reporting_ocpusagelineitem_daily_summary_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagelineitem_daily_summary
    ADD CONSTRAINT reporting_ocpusagelineitem_daily_summary_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpusagelineitem reporting_ocpusagelineitem_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagelineitem
    ADD CONSTRAINT reporting_ocpusagelineitem_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpusagepodlabel_summary reporting_ocpusagepodlabel_summary_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagepodlabel_summary
    ADD CONSTRAINT reporting_ocpusagepodlabel_summary_pkey PRIMARY KEY (key);


--
-- Name: reporting_ocpusagereportperiod reporting_ocpusagereport_cluster_id_report_period_ff3ea314_uniq; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagereportperiod
    ADD CONSTRAINT reporting_ocpusagereport_cluster_id_report_period_ff3ea314_uniq UNIQUE (cluster_id, report_period_start, provider_id);


--
-- Name: reporting_ocpusagereport reporting_ocpusagereport_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagereport
    ADD CONSTRAINT reporting_ocpusagereport_pkey PRIMARY KEY (id);


--
-- Name: reporting_ocpusagereport reporting_ocpusagereport_report_period_id_interva_066551f3_uniq; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagereport
    ADD CONSTRAINT reporting_ocpusagereport_report_period_id_interva_066551f3_uniq UNIQUE (report_period_id, interval_start);


--
-- Name: reporting_ocpusagereportperiod reporting_ocpusagereportperiod_pkey; Type: CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagereportperiod
    ADD CONSTRAINT reporting_ocpusagereportperiod_pkey PRIMARY KEY (id);


--
-- Name: api_customer api_customer_account_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_customer
    ADD CONSTRAINT api_customer_account_id_key UNIQUE (account_id);


--
-- Name: api_customer api_customer_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_customer
    ADD CONSTRAINT api_customer_pkey PRIMARY KEY (id);


--
-- Name: api_customer api_customer_schema_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_customer
    ADD CONSTRAINT api_customer_schema_name_key UNIQUE (schema_name);


--
-- Name: api_customer api_customer_uuid_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_customer
    ADD CONSTRAINT api_customer_uuid_key UNIQUE (uuid);


--
-- Name: api_provider api_provider_authentication_id_billing_source_id_8f2af497_uniq; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_provider
    ADD CONSTRAINT api_provider_authentication_id_billing_source_id_8f2af497_uniq UNIQUE (authentication_id, billing_source_id);


--
-- Name: api_provider api_provider_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_provider
    ADD CONSTRAINT api_provider_pkey PRIMARY KEY (id);


--
-- Name: api_provider api_provider_uuid_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_provider
    ADD CONSTRAINT api_provider_uuid_key UNIQUE (uuid);


--
-- Name: api_providerauthentication api_providerauthentication_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_providerauthentication
    ADD CONSTRAINT api_providerauthentication_pkey PRIMARY KEY (id);


--
-- Name: api_providerauthentication api_providerauthentication_provider_resource_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_providerauthentication
    ADD CONSTRAINT api_providerauthentication_provider_resource_name_key UNIQUE (provider_resource_name);


--
-- Name: api_providerauthentication api_providerauthentication_uuid_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_providerauthentication
    ADD CONSTRAINT api_providerauthentication_uuid_key UNIQUE (uuid);


--
-- Name: api_providerbillingsource api_providerbillingsource_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_providerbillingsource
    ADD CONSTRAINT api_providerbillingsource_pkey PRIMARY KEY (id);


--
-- Name: api_providerbillingsource api_providerbillingsource_uuid_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_providerbillingsource
    ADD CONSTRAINT api_providerbillingsource_uuid_key UNIQUE (uuid);


--
-- Name: api_providerstatus api_providerstatus_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_providerstatus
    ADD CONSTRAINT api_providerstatus_pkey PRIMARY KEY (id);


--
-- Name: api_tenant api_tenant_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_tenant
    ADD CONSTRAINT api_tenant_pkey PRIMARY KEY (id);


--
-- Name: api_tenant api_tenant_schema_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_tenant
    ADD CONSTRAINT api_tenant_schema_name_key UNIQUE (schema_name);


--
-- Name: api_user api_user_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_user
    ADD CONSTRAINT api_user_pkey PRIMARY KEY (id);


--
-- Name: api_user api_user_username_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_user
    ADD CONSTRAINT api_user_username_key UNIQUE (username);


--
-- Name: api_user api_user_uuid_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_user
    ADD CONSTRAINT api_user_uuid_key UNIQUE (uuid);


--
-- Name: api_userpreference api_userpreference_name_user_id_9f2a465b_uniq; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_userpreference
    ADD CONSTRAINT api_userpreference_name_user_id_9f2a465b_uniq UNIQUE (name, user_id);


--
-- Name: api_userpreference api_userpreference_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_userpreference
    ADD CONSTRAINT api_userpreference_pkey PRIMARY KEY (id);


--
-- Name: api_userpreference api_userpreference_uuid_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_userpreference
    ADD CONSTRAINT api_userpreference_uuid_key UNIQUE (uuid);


--
-- Name: auth_group auth_group_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_group
    ADD CONSTRAINT auth_group_name_key UNIQUE (name);


--
-- Name: auth_group_permissions auth_group_permissions_group_id_permission_id_0cd325b0_uniq; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_group_id_permission_id_0cd325b0_uniq UNIQUE (group_id, permission_id);


--
-- Name: auth_group_permissions auth_group_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_pkey PRIMARY KEY (id);


--
-- Name: auth_group auth_group_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_group
    ADD CONSTRAINT auth_group_pkey PRIMARY KEY (id);


--
-- Name: auth_permission auth_permission_content_type_id_codename_01ab375a_uniq; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_content_type_id_codename_01ab375a_uniq UNIQUE (content_type_id, codename);


--
-- Name: auth_permission auth_permission_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_pkey PRIMARY KEY (id);


--
-- Name: auth_user_groups auth_user_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user_groups
    ADD CONSTRAINT auth_user_groups_pkey PRIMARY KEY (id);


--
-- Name: auth_user_groups auth_user_groups_user_id_group_id_94350c0c_uniq; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user_groups
    ADD CONSTRAINT auth_user_groups_user_id_group_id_94350c0c_uniq UNIQUE (user_id, group_id);


--
-- Name: auth_user auth_user_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user
    ADD CONSTRAINT auth_user_pkey PRIMARY KEY (id);


--
-- Name: auth_user_user_permissions auth_user_user_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user_user_permissions
    ADD CONSTRAINT auth_user_user_permissions_pkey PRIMARY KEY (id);


--
-- Name: auth_user_user_permissions auth_user_user_permissions_user_id_permission_id_14a6b632_uniq; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user_user_permissions
    ADD CONSTRAINT auth_user_user_permissions_user_id_permission_id_14a6b632_uniq UNIQUE (user_id, permission_id);


--
-- Name: auth_user auth_user_username_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user
    ADD CONSTRAINT auth_user_username_key UNIQUE (username);


--
-- Name: cost_models_metrics_map cost_models_metrics_map_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cost_models_metrics_map
    ADD CONSTRAINT cost_models_metrics_map_pkey PRIMARY KEY (id);


--
-- Name: cost_models_metrics_map cost_models_metrics_map_source_type_metric_958905f5_uniq; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cost_models_metrics_map
    ADD CONSTRAINT cost_models_metrics_map_source_type_metric_958905f5_uniq UNIQUE (source_type, metric);


--
-- Name: django_content_type django_content_type_app_label_model_76bd3d3b_uniq; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.django_content_type
    ADD CONSTRAINT django_content_type_app_label_model_76bd3d3b_uniq UNIQUE (app_label, model);


--
-- Name: django_content_type django_content_type_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.django_content_type
    ADD CONSTRAINT django_content_type_pkey PRIMARY KEY (id);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: django_session django_session_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.django_session
    ADD CONSTRAINT django_session_pkey PRIMARY KEY (session_key);


--
-- Name: region_mapping region_mapping_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.region_mapping
    ADD CONSTRAINT region_mapping_pkey PRIMARY KEY (id);


--
-- Name: region_mapping region_mapping_region_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.region_mapping
    ADD CONSTRAINT region_mapping_region_key UNIQUE (region);


--
-- Name: region_mapping region_mapping_region_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.region_mapping
    ADD CONSTRAINT region_mapping_region_name_key UNIQUE (region_name);


--
-- Name: reporting_common_costusagereportmanifest reporting_common_costusa_provider_id_assembly_id_32d4d2f1_uniq; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reporting_common_costusagereportmanifest
    ADD CONSTRAINT reporting_common_costusa_provider_id_assembly_id_32d4d2f1_uniq UNIQUE (provider_id, assembly_id);


--
-- Name: reporting_common_costusagereportmanifest reporting_common_costusagereportmanifest_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reporting_common_costusagereportmanifest
    ADD CONSTRAINT reporting_common_costusagereportmanifest_pkey PRIMARY KEY (id);


--
-- Name: reporting_common_costusagereportstatus reporting_common_costusagereportstatus_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reporting_common_costusagereportstatus
    ADD CONSTRAINT reporting_common_costusagereportstatus_pkey PRIMARY KEY (id);


--
-- Name: reporting_common_costusagereportstatus reporting_common_costusagereportstatus_report_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reporting_common_costusagereportstatus
    ADD CONSTRAINT reporting_common_costusagereportstatus_report_name_key UNIQUE (report_name);


--
-- Name: reporting_common_reportcolumnmap reporting_common_reportc_report_type_provider_col_986f6289_uniq; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reporting_common_reportcolumnmap
    ADD CONSTRAINT reporting_common_reportc_report_type_provider_col_986f6289_uniq UNIQUE (report_type, provider_column_name);


--
-- Name: reporting_common_reportcolumnmap reporting_common_reportcolumnmap_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reporting_common_reportcolumnmap
    ADD CONSTRAINT reporting_common_reportcolumnmap_pkey PRIMARY KEY (id);


--
-- Name: si_unit_scale si_unit_scale_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.si_unit_scale
    ADD CONSTRAINT si_unit_scale_pkey PRIMARY KEY (id);


--
-- Name: si_unit_scale si_unit_scale_prefix_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.si_unit_scale
    ADD CONSTRAINT si_unit_scale_prefix_key UNIQUE (prefix);


--
-- Name: cost__proj_sum_namespace_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX cost__proj_sum_namespace_idx ON acct10001.reporting_ocpawscostlineitem_project_daily_summary USING btree (namespace);


--
-- Name: cost_proj_pod_labels_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX cost_proj_pod_labels_idx ON acct10001.reporting_ocpawscostlineitem_project_daily_summary USING gin (pod_labels);


--
-- Name: cost_proj_sum_node_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX cost_proj_sum_node_idx ON acct10001.reporting_ocpawscostlineitem_project_daily_summary USING btree (node);


--
-- Name: cost_proj_sum_ocp_usage_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX cost_proj_sum_ocp_usage_idx ON acct10001.reporting_ocpawscostlineitem_project_daily_summary USING btree (usage_start);


--
-- Name: cost_proj_sum_resource_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX cost_proj_sum_resource_idx ON acct10001.reporting_ocpawscostlineitem_project_daily_summary USING btree (resource_id);


--
-- Name: cost_summary_namespace_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX cost_summary_namespace_idx ON acct10001.reporting_ocpawscostlineitem_daily_summary USING btree (namespace);


--
-- Name: cost_summary_node_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX cost_summary_node_idx ON acct10001.reporting_ocpawscostlineitem_daily_summary USING btree (node);


--
-- Name: cost_summary_ocp_usage_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX cost_summary_ocp_usage_idx ON acct10001.reporting_ocpawscostlineitem_daily_summary USING btree (usage_start);


--
-- Name: cost_summary_resource_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX cost_summary_resource_idx ON acct10001.reporting_ocpawscostlineitem_daily_summary USING btree (resource_id);


--
-- Name: cost_tags_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX cost_tags_idx ON acct10001.reporting_ocpawscostlineitem_daily_summary USING gin (tags);


--
-- Name: interval_start_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX interval_start_idx ON acct10001.reporting_awscostentry USING btree (interval_start);


--
-- Name: namespace_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX namespace_idx ON acct10001.reporting_ocpusagelineitem_daily USING btree (namespace);


--
-- Name: node_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX node_idx ON acct10001.reporting_ocpusagelineitem_daily USING btree (node);


--
-- Name: ocp_aws_instance_type_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX ocp_aws_instance_type_idx ON acct10001.reporting_ocpawscostlineitem_daily_summary USING btree (instance_type);


--
-- Name: ocp_aws_product_family_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX ocp_aws_product_family_idx ON acct10001.reporting_ocpawscostlineitem_daily_summary USING btree (product_family);


--
-- Name: ocp_aws_proj_inst_type_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX ocp_aws_proj_inst_type_idx ON acct10001.reporting_ocpawscostlineitem_project_daily_summary USING btree (instance_type);


--
-- Name: ocp_aws_proj_prod_fam_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX ocp_aws_proj_prod_fam_idx ON acct10001.reporting_ocpawscostlineitem_project_daily_summary USING btree (product_family);


--
-- Name: ocp_interval_start_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX ocp_interval_start_idx ON acct10001.reporting_ocpusagereport USING btree (interval_start);


--
-- Name: ocp_usage_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX ocp_usage_idx ON acct10001.reporting_ocpusagelineitem_daily USING btree (usage_start);


--
-- Name: pod_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX pod_idx ON acct10001.reporting_ocpusagelineitem_daily USING btree (pod);


--
-- Name: pod_labels_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX pod_labels_idx ON acct10001.reporting_ocpusagelineitem_daily_summary USING gin (pod_labels);


--
-- Name: product_code_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX product_code_idx ON acct10001.reporting_awscostentrylineitem_daily USING btree (product_code);


--
-- Name: rates_ratemap_rate_id_5db2509b; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX rates_ratemap_rate_id_5db2509b ON acct10001.rates_ratemap USING btree (rate_id);


--
-- Name: region_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX region_idx ON acct10001.reporting_awscostentryproduct USING btree (region);


--
-- Name: reporting_awsaccountalias_account_id_85724b8c_like; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awsaccountalias_account_id_85724b8c_like ON acct10001.reporting_awsaccountalias USING btree (account_id varchar_pattern_ops);


--
-- Name: reporting_awscostentry_bill_id_017f27a3; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentry_bill_id_017f27a3 ON acct10001.reporting_awscostentry USING btree (bill_id);


--
-- Name: reporting_awscostentryline_account_alias_id_684d6c01; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentryline_account_alias_id_684d6c01 ON acct10001.reporting_awscostentrylineitem_daily_summary USING btree (account_alias_id);


--
-- Name: reporting_awscostentryline_cost_entry_bill_id_54ece653; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentryline_cost_entry_bill_id_54ece653 ON acct10001.reporting_awscostentrylineitem_daily USING btree (cost_entry_bill_id);


--
-- Name: reporting_awscostentryline_cost_entry_bill_id_d7af1eb6; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentryline_cost_entry_bill_id_d7af1eb6 ON acct10001.reporting_awscostentrylineitem_daily_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_awscostentryline_cost_entry_pricing_id_5a6a9b38; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentryline_cost_entry_pricing_id_5a6a9b38 ON acct10001.reporting_awscostentrylineitem_daily USING btree (cost_entry_pricing_id);


--
-- Name: reporting_awscostentryline_cost_entry_product_id_4d8ef2fd; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentryline_cost_entry_product_id_4d8ef2fd ON acct10001.reporting_awscostentrylineitem_daily USING btree (cost_entry_product_id);


--
-- Name: reporting_awscostentryline_cost_entry_reservation_id_13b1cb08; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentryline_cost_entry_reservation_id_13b1cb08 ON acct10001.reporting_awscostentrylineitem_daily USING btree (cost_entry_reservation_id);


--
-- Name: reporting_awscostentryline_cost_entry_reservation_id_9332b371; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentryline_cost_entry_reservation_id_9332b371 ON acct10001.reporting_awscostentrylineitem USING btree (cost_entry_reservation_id);


--
-- Name: reporting_awscostentrylineitem_cost_entry_bill_id_5ae74e09; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentrylineitem_cost_entry_bill_id_5ae74e09 ON acct10001.reporting_awscostentrylineitem USING btree (cost_entry_bill_id);


--
-- Name: reporting_awscostentrylineitem_cost_entry_id_4d1a7fc4; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentrylineitem_cost_entry_id_4d1a7fc4 ON acct10001.reporting_awscostentrylineitem USING btree (cost_entry_id);


--
-- Name: reporting_awscostentrylineitem_cost_entry_pricing_id_a654a7e3; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentrylineitem_cost_entry_pricing_id_a654a7e3 ON acct10001.reporting_awscostentrylineitem USING btree (cost_entry_pricing_id);


--
-- Name: reporting_awscostentrylineitem_cost_entry_product_id_29c80210; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentrylineitem_cost_entry_product_id_29c80210 ON acct10001.reporting_awscostentrylineitem USING btree (cost_entry_product_id);


--
-- Name: reporting_awscostentryreservation_reservation_arn_e387aa5b_like; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awscostentryreservation_reservation_arn_e387aa5b_like ON acct10001.reporting_awscostentryreservation USING btree (reservation_arn text_pattern_ops);


--
-- Name: reporting_awstags_summary_key_c99caa53_like; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_awstags_summary_key_c99caa53_like ON acct10001.reporting_awstags_summary USING btree (key varchar_pattern_ops);


--
-- Name: reporting_ocpawscostlineit_account_alias_id_d12902c6; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpawscostlineit_account_alias_id_d12902c6 ON acct10001.reporting_ocpawscostlineitem_project_daily_summary USING btree (account_alias_id);


--
-- Name: reporting_ocpawscostlineit_account_alias_id_f19d2883; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpawscostlineit_account_alias_id_f19d2883 ON acct10001.reporting_ocpawscostlineitem_daily_summary USING btree (account_alias_id);


--
-- Name: reporting_ocpawscostlineit_cost_entry_bill_id_2740da80; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpawscostlineit_cost_entry_bill_id_2740da80 ON acct10001.reporting_ocpawscostlineitem_project_daily_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_ocpawscostlineit_cost_entry_bill_id_2a473151; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpawscostlineit_cost_entry_bill_id_2a473151 ON acct10001.reporting_ocpawscostlineitem_daily_summary USING btree (cost_entry_bill_id);


--
-- Name: reporting_ocpstoragelineitem_report_id_6ff71ea6; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpstoragelineitem_report_id_6ff71ea6 ON acct10001.reporting_ocpstoragelineitem USING btree (report_id);


--
-- Name: reporting_ocpstoragelineitem_report_period_id_6d730b12; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpstoragelineitem_report_period_id_6d730b12 ON acct10001.reporting_ocpstoragelineitem USING btree (report_period_id);


--
-- Name: reporting_ocpstoragevolumeclaimlabel_summary_key_012a657a_like; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpstoragevolumeclaimlabel_summary_key_012a657a_like ON acct10001.reporting_ocpstoragevolumeclaimlabel_summary USING btree (key varchar_pattern_ops);


--
-- Name: reporting_ocpstoragevolumelabel_summary_key_05144f9e_like; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpstoragevolumelabel_summary_key_05144f9e_like ON acct10001.reporting_ocpstoragevolumelabel_summary USING btree (key varchar_pattern_ops);


--
-- Name: reporting_ocpusagelineitem_report_id_32a973b0; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpusagelineitem_report_id_32a973b0 ON acct10001.reporting_ocpusagelineitem USING btree (report_id);


--
-- Name: reporting_ocpusagelineitem_report_period_id_be7fa5ad; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpusagelineitem_report_period_id_be7fa5ad ON acct10001.reporting_ocpusagelineitem USING btree (report_period_id);


--
-- Name: reporting_ocpusagepodlabel_summary_key_fa0b8105_like; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpusagepodlabel_summary_key_fa0b8105_like ON acct10001.reporting_ocpusagepodlabel_summary USING btree (key varchar_pattern_ops);


--
-- Name: reporting_ocpusagereport_report_period_id_477508c6; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX reporting_ocpusagereport_report_period_id_477508c6 ON acct10001.reporting_ocpusagereport USING btree (report_period_id);


--
-- Name: storage_summary_namespace_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX storage_summary_namespace_idx ON acct10001.reporting_ocpstoragelineitem_daily_summary USING btree (namespace);


--
-- Name: storage_summary_node_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX storage_summary_node_idx ON acct10001.reporting_ocpstoragelineitem_daily_summary USING btree (node);


--
-- Name: storage_summary_ocp_usage_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX storage_summary_ocp_usage_idx ON acct10001.reporting_ocpstoragelineitem_daily_summary USING btree (usage_start);


--
-- Name: storage_volume_labels_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX storage_volume_labels_idx ON acct10001.reporting_ocpstoragelineitem_daily_summary USING gin (volume_labels);


--
-- Name: summary_account_alias_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX summary_account_alias_idx ON acct10001.reporting_awscostentrylineitem_daily_summary USING btree (account_alias_id);


--
-- Name: summary_instance_type_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX summary_instance_type_idx ON acct10001.reporting_awscostentrylineitem_daily_summary USING btree (instance_type);


--
-- Name: summary_namespace_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX summary_namespace_idx ON acct10001.reporting_ocpusagelineitem_daily_summary USING btree (namespace);


--
-- Name: summary_node_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX summary_node_idx ON acct10001.reporting_ocpusagelineitem_daily_summary USING btree (node);


--
-- Name: summary_ocp_usage_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX summary_ocp_usage_idx ON acct10001.reporting_ocpusagelineitem_daily_summary USING btree (usage_start);


--
-- Name: summary_product_code_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX summary_product_code_idx ON acct10001.reporting_awscostentrylineitem_daily_summary USING btree (product_code);


--
-- Name: summary_product_family_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX summary_product_family_idx ON acct10001.reporting_awscostentrylineitem_daily_summary USING btree (product_family);


--
-- Name: summary_usage_account_id_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX summary_usage_account_id_idx ON acct10001.reporting_awscostentrylineitem_daily_summary USING btree (usage_account_id);


--
-- Name: summary_usage_start_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX summary_usage_start_idx ON acct10001.reporting_awscostentrylineitem_daily_summary USING btree (usage_start);


--
-- Name: tags_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX tags_idx ON acct10001.reporting_awscostentrylineitem_daily_summary USING gin (tags);


--
-- Name: usage_account_id_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX usage_account_id_idx ON acct10001.reporting_awscostentrylineitem_daily USING btree (usage_account_id);


--
-- Name: usage_start_idx; Type: INDEX; Schema: acct10001; Owner: postgres
--

CREATE INDEX usage_start_idx ON acct10001.reporting_awscostentrylineitem_daily USING btree (usage_start);


--
-- Name: api_customer_account_id_206bec02_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_customer_account_id_206bec02_like ON public.api_customer USING btree (account_id varchar_pattern_ops);


--
-- Name: api_customer_schema_name_6b716c4b_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_customer_schema_name_6b716c4b_like ON public.api_customer USING btree (schema_name text_pattern_ops);


--
-- Name: api_provider_authentication_id_201fd4b9; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_provider_authentication_id_201fd4b9 ON public.api_provider USING btree (authentication_id);


--
-- Name: api_provider_billing_source_id_cb6b5a6f; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_provider_billing_source_id_cb6b5a6f ON public.api_provider USING btree (billing_source_id);


--
-- Name: api_provider_created_by_id_e740fc35; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_provider_created_by_id_e740fc35 ON public.api_provider USING btree (created_by_id);


--
-- Name: api_provider_customer_id_87062290; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_provider_customer_id_87062290 ON public.api_provider USING btree (customer_id);


--
-- Name: api_providerauthentication_provider_resource_name_fa7deecb_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_providerauthentication_provider_resource_name_fa7deecb_like ON public.api_providerauthentication USING btree (provider_resource_name text_pattern_ops);


--
-- Name: api_providerstatus_provider_id_3acce5df; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_providerstatus_provider_id_3acce5df ON public.api_providerstatus USING btree (provider_id);


--
-- Name: api_tenant_schema_name_733d339b_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_tenant_schema_name_733d339b_like ON public.api_tenant USING btree (schema_name varchar_pattern_ops);


--
-- Name: api_user_customer_id_90bd21ef; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_user_customer_id_90bd21ef ON public.api_user USING btree (customer_id);


--
-- Name: api_user_username_cf4e88d2_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_user_username_cf4e88d2_like ON public.api_user USING btree (username varchar_pattern_ops);


--
-- Name: api_userpreference_user_id_e62eaffa; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX api_userpreference_user_id_e62eaffa ON public.api_userpreference USING btree (user_id);


--
-- Name: auth_group_name_a6ea08ec_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX auth_group_name_a6ea08ec_like ON public.auth_group USING btree (name varchar_pattern_ops);


--
-- Name: auth_group_permissions_group_id_b120cbf9; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX auth_group_permissions_group_id_b120cbf9 ON public.auth_group_permissions USING btree (group_id);


--
-- Name: auth_group_permissions_permission_id_84c5c92e; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX auth_group_permissions_permission_id_84c5c92e ON public.auth_group_permissions USING btree (permission_id);


--
-- Name: auth_permission_content_type_id_2f476e4b; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX auth_permission_content_type_id_2f476e4b ON public.auth_permission USING btree (content_type_id);


--
-- Name: auth_user_groups_group_id_97559544; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX auth_user_groups_group_id_97559544 ON public.auth_user_groups USING btree (group_id);


--
-- Name: auth_user_groups_user_id_6a12ed8b; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX auth_user_groups_user_id_6a12ed8b ON public.auth_user_groups USING btree (user_id);


--
-- Name: auth_user_user_permissions_permission_id_1fbb5f2c; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX auth_user_user_permissions_permission_id_1fbb5f2c ON public.auth_user_user_permissions USING btree (permission_id);


--
-- Name: auth_user_user_permissions_user_id_a95ead1b; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX auth_user_user_permissions_user_id_a95ead1b ON public.auth_user_user_permissions USING btree (user_id);


--
-- Name: auth_user_username_6821ab7c_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX auth_user_username_6821ab7c_like ON public.auth_user USING btree (username varchar_pattern_ops);


--
-- Name: django_session_expire_date_a5c62663; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX django_session_expire_date_a5c62663 ON public.django_session USING btree (expire_date);


--
-- Name: django_session_session_key_c0390e0f_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX django_session_session_key_c0390e0f_like ON public.django_session USING btree (session_key varchar_pattern_ops);


--
-- Name: region_mapping_region_9c0d71ba_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX region_mapping_region_9c0d71ba_like ON public.region_mapping USING btree (region varchar_pattern_ops);


--
-- Name: region_mapping_region_name_ad295b89_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX region_mapping_region_name_ad295b89_like ON public.region_mapping USING btree (region_name varchar_pattern_ops);


--
-- Name: reporting_common_costusa_report_name_134674b5_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX reporting_common_costusa_report_name_134674b5_like ON public.reporting_common_costusagereportstatus USING btree (report_name varchar_pattern_ops);


--
-- Name: reporting_common_costusagereportmanifest_provider_id_6abb15de; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX reporting_common_costusagereportmanifest_provider_id_6abb15de ON public.reporting_common_costusagereportmanifest USING btree (provider_id);


--
-- Name: reporting_common_costusagereportstatus_manifest_id_62ef64b9; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX reporting_common_costusagereportstatus_manifest_id_62ef64b9 ON public.reporting_common_costusagereportstatus USING btree (manifest_id);


--
-- Name: reporting_common_reportc_provider_column_name_e01eaba3_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX reporting_common_reportc_provider_column_name_e01eaba3_like ON public.reporting_common_reportcolumnmap USING btree (provider_column_name varchar_pattern_ops);


--
-- Name: si_unit_scale_prefix_eb9daade_like; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX si_unit_scale_prefix_eb9daade_like ON public.si_unit_scale USING btree (prefix varchar_pattern_ops);


--
-- Name: rates_ratemap rates_ratemap_rate_id_5db2509b_fk_rates_rate_id; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.rates_ratemap
    ADD CONSTRAINT rates_ratemap_rate_id_5db2509b_fk_rates_rate_id FOREIGN KEY (rate_id) REFERENCES acct10001.rates_rate(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily_summary reporting_awscostent_account_alias_id_684d6c01_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem_daily_summary
    ADD CONSTRAINT reporting_awscostent_account_alias_id_684d6c01_fk_reporting FOREIGN KEY (account_alias_id) REFERENCES acct10001.reporting_awsaccountalias(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentry reporting_awscostent_bill_id_017f27a3_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentry
    ADD CONSTRAINT reporting_awscostent_bill_id_017f27a3_fk_reporting FOREIGN KEY (bill_id) REFERENCES acct10001.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily reporting_awscostent_cost_entry_bill_id_54ece653_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem_daily
    ADD CONSTRAINT reporting_awscostent_cost_entry_bill_id_54ece653_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES acct10001.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem reporting_awscostent_cost_entry_bill_id_5ae74e09_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostent_cost_entry_bill_id_5ae74e09_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES acct10001.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily_summary reporting_awscostent_cost_entry_bill_id_d7af1eb6_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem_daily_summary
    ADD CONSTRAINT reporting_awscostent_cost_entry_bill_id_d7af1eb6_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES acct10001.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem reporting_awscostent_cost_entry_id_4d1a7fc4_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostent_cost_entry_id_4d1a7fc4_fk_reporting FOREIGN KEY (cost_entry_id) REFERENCES acct10001.reporting_awscostentry(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily reporting_awscostent_cost_entry_pricing_i_5a6a9b38_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem_daily
    ADD CONSTRAINT reporting_awscostent_cost_entry_pricing_i_5a6a9b38_fk_reporting FOREIGN KEY (cost_entry_pricing_id) REFERENCES acct10001.reporting_awscostentrypricing(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem reporting_awscostent_cost_entry_pricing_i_a654a7e3_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostent_cost_entry_pricing_i_a654a7e3_fk_reporting FOREIGN KEY (cost_entry_pricing_id) REFERENCES acct10001.reporting_awscostentrypricing(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem reporting_awscostent_cost_entry_product_i_29c80210_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostent_cost_entry_product_i_29c80210_fk_reporting FOREIGN KEY (cost_entry_product_id) REFERENCES acct10001.reporting_awscostentryproduct(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily reporting_awscostent_cost_entry_product_i_4d8ef2fd_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem_daily
    ADD CONSTRAINT reporting_awscostent_cost_entry_product_i_4d8ef2fd_fk_reporting FOREIGN KEY (cost_entry_product_id) REFERENCES acct10001.reporting_awscostentryproduct(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem_daily reporting_awscostent_cost_entry_reservati_13b1cb08_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem_daily
    ADD CONSTRAINT reporting_awscostent_cost_entry_reservati_13b1cb08_fk_reporting FOREIGN KEY (cost_entry_reservation_id) REFERENCES acct10001.reporting_awscostentryreservation(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_awscostentrylineitem reporting_awscostent_cost_entry_reservati_9332b371_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_awscostentrylineitem
    ADD CONSTRAINT reporting_awscostent_cost_entry_reservati_9332b371_fk_reporting FOREIGN KEY (cost_entry_reservation_id) REFERENCES acct10001.reporting_awscostentryreservation(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawscostlineitem_project_daily_summary reporting_ocpawscost_account_alias_id_d12902c6_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpawscostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpawscost_account_alias_id_d12902c6_fk_reporting FOREIGN KEY (account_alias_id) REFERENCES acct10001.reporting_awsaccountalias(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawscostlineitem_daily_summary reporting_ocpawscost_account_alias_id_f19d2883_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpawscostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpawscost_account_alias_id_f19d2883_fk_reporting FOREIGN KEY (account_alias_id) REFERENCES acct10001.reporting_awsaccountalias(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawscostlineitem_project_daily_summary reporting_ocpawscost_cost_entry_bill_id_2740da80_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpawscostlineitem_project_daily_summary
    ADD CONSTRAINT reporting_ocpawscost_cost_entry_bill_id_2740da80_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES acct10001.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpawscostlineitem_daily_summary reporting_ocpawscost_cost_entry_bill_id_2a473151_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpawscostlineitem_daily_summary
    ADD CONSTRAINT reporting_ocpawscost_cost_entry_bill_id_2a473151_fk_reporting FOREIGN KEY (cost_entry_bill_id) REFERENCES acct10001.reporting_awscostentrybill(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpstoragelineitem reporting_ocpstorage_report_id_6ff71ea6_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpstoragelineitem
    ADD CONSTRAINT reporting_ocpstorage_report_id_6ff71ea6_fk_reporting FOREIGN KEY (report_id) REFERENCES acct10001.reporting_ocpusagereport(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpstoragelineitem reporting_ocpstorage_report_period_id_6d730b12_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpstoragelineitem
    ADD CONSTRAINT reporting_ocpstorage_report_period_id_6d730b12_fk_reporting FOREIGN KEY (report_period_id) REFERENCES acct10001.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpusagelineitem reporting_ocpusageli_report_id_32a973b0_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagelineitem
    ADD CONSTRAINT reporting_ocpusageli_report_id_32a973b0_fk_reporting FOREIGN KEY (report_id) REFERENCES acct10001.reporting_ocpusagereport(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpusagelineitem reporting_ocpusageli_report_period_id_be7fa5ad_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagelineitem
    ADD CONSTRAINT reporting_ocpusageli_report_period_id_be7fa5ad_fk_reporting FOREIGN KEY (report_period_id) REFERENCES acct10001.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_ocpusagereport reporting_ocpusagere_report_period_id_477508c6_fk_reporting; Type: FK CONSTRAINT; Schema: acct10001; Owner: postgres
--

ALTER TABLE ONLY acct10001.reporting_ocpusagereport
    ADD CONSTRAINT reporting_ocpusagere_report_period_id_477508c6_fk_reporting FOREIGN KEY (report_period_id) REFERENCES acct10001.reporting_ocpusagereportperiod(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: api_provider api_provider_authentication_id_201fd4b9_fk_api_provi; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_provider
    ADD CONSTRAINT api_provider_authentication_id_201fd4b9_fk_api_provi FOREIGN KEY (authentication_id) REFERENCES public.api_providerauthentication(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: api_provider api_provider_billing_source_id_cb6b5a6f_fk_api_provi; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_provider
    ADD CONSTRAINT api_provider_billing_source_id_cb6b5a6f_fk_api_provi FOREIGN KEY (billing_source_id) REFERENCES public.api_providerbillingsource(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: api_provider api_provider_created_by_id_e740fc35_fk_api_user_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_provider
    ADD CONSTRAINT api_provider_created_by_id_e740fc35_fk_api_user_id FOREIGN KEY (created_by_id) REFERENCES public.api_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: api_provider api_provider_customer_id_87062290_fk_api_customer_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_provider
    ADD CONSTRAINT api_provider_customer_id_87062290_fk_api_customer_id FOREIGN KEY (customer_id) REFERENCES public.api_customer(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: api_providerstatus api_providerstatus_provider_id_3acce5df_fk_api_provider_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_providerstatus
    ADD CONSTRAINT api_providerstatus_provider_id_3acce5df_fk_api_provider_id FOREIGN KEY (provider_id) REFERENCES public.api_provider(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: api_user api_user_customer_id_90bd21ef_fk_api_customer_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_user
    ADD CONSTRAINT api_user_customer_id_90bd21ef_fk_api_customer_id FOREIGN KEY (customer_id) REFERENCES public.api_customer(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: api_userpreference api_userpreference_user_id_e62eaffa_fk_api_user_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.api_userpreference
    ADD CONSTRAINT api_userpreference_user_id_e62eaffa_fk_api_user_id FOREIGN KEY (user_id) REFERENCES public.api_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_group_permissions auth_group_permissio_permission_id_84c5c92e_fk_auth_perm; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissio_permission_id_84c5c92e_fk_auth_perm FOREIGN KEY (permission_id) REFERENCES public.auth_permission(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_group_permissions auth_group_permissions_group_id_b120cbf9_fk_auth_group_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_group_id_b120cbf9_fk_auth_group_id FOREIGN KEY (group_id) REFERENCES public.auth_group(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_permission auth_permission_content_type_id_2f476e4b_fk_django_co; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_content_type_id_2f476e4b_fk_django_co FOREIGN KEY (content_type_id) REFERENCES public.django_content_type(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_user_groups auth_user_groups_group_id_97559544_fk_auth_group_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user_groups
    ADD CONSTRAINT auth_user_groups_group_id_97559544_fk_auth_group_id FOREIGN KEY (group_id) REFERENCES public.auth_group(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_user_groups auth_user_groups_user_id_6a12ed8b_fk_auth_user_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user_groups
    ADD CONSTRAINT auth_user_groups_user_id_6a12ed8b_fk_auth_user_id FOREIGN KEY (user_id) REFERENCES public.auth_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_user_user_permissions auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user_user_permissions
    ADD CONSTRAINT auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm FOREIGN KEY (permission_id) REFERENCES public.auth_permission(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_user_user_permissions auth_user_user_permissions_user_id_a95ead1b_fk_auth_user_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_user_user_permissions
    ADD CONSTRAINT auth_user_user_permissions_user_id_a95ead1b_fk_auth_user_id FOREIGN KEY (user_id) REFERENCES public.auth_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_common_costusagereportstatus reporting_common_cos_manifest_id_62ef64b9_fk_reporting; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reporting_common_costusagereportstatus
    ADD CONSTRAINT reporting_common_cos_manifest_id_62ef64b9_fk_reporting FOREIGN KEY (manifest_id) REFERENCES public.reporting_common_costusagereportmanifest(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: reporting_common_costusagereportmanifest reporting_common_cos_provider_id_6abb15de_fk_api_provi; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reporting_common_costusagereportmanifest
    ADD CONSTRAINT reporting_common_cos_provider_id_6abb15de_fk_api_provi FOREIGN KEY (provider_id) REFERENCES public.api_provider(id) DEFERRABLE INITIALLY DEFERRED;


--
-- PostgreSQL database dump complete
--

