--
-- PostgreSQL database dump
--


-- Dumped from database version 18.3
-- Dumped by pg_dump version 18.3

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
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: api_request_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_request_logs (
    id integer NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    method character varying(10) NOT NULL,
    url text NOT NULL,
    request_body jsonb,
    response_status integer,
    response_body jsonb,
    error_message text,
    duration_ms integer,
    log_date character varying(10) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    operation character varying(80) DEFAULT ''::character varying,
    status character varying(40) DEFAULT ''::character varying,
    request_id character varying(120) DEFAULT ''::character varying,
    extra jsonb DEFAULT '{}'::jsonb
);


--
-- Name: api_request_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.api_request_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: api_request_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.api_request_logs_id_seq OWNED BY public.api_request_logs.id;


--
-- Name: dashboard_platform_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dashboard_platform_settings (
    id integer NOT NULL,
    platform character varying(40) NOT NULL,
    receipt_rate numeric(8,6) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE dashboard_platform_settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.dashboard_platform_settings IS '工作台平台经营参数';


--
-- Name: COLUMN dashboard_platform_settings.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.dashboard_platform_settings.id IS '主键ID';


--
-- Name: COLUMN dashboard_platform_settings.platform; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.dashboard_platform_settings.platform IS '平台代码，other 表示默认规则';


--
-- Name: COLUMN dashboard_platform_settings.receipt_rate; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.dashboard_platform_settings.receipt_rate IS '预计收款比例';


--
-- Name: COLUMN dashboard_platform_settings.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.dashboard_platform_settings.created_at IS '创建时间';


--
-- Name: COLUMN dashboard_platform_settings.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.dashboard_platform_settings.updated_at IS '更新时间';


--
-- Name: dashboard_platform_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dashboard_platform_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dashboard_platform_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dashboard_platform_settings_id_seq OWNED BY public.dashboard_platform_settings.id;


--
-- Name: email_smtp_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.email_smtp_settings (
    id integer NOT NULL,
    provider character varying(40) NOT NULL,
    enabled boolean NOT NULL,
    smtp_host character varying(255) NOT NULL,
    smtp_port integer NOT NULL,
    use_ssl boolean NOT NULL,
    sender_email character varying(255) NOT NULL,
    sender_name character varying(120) NOT NULL,
    encrypted_auth_code bytea,
    last_test_at timestamp without time zone,
    last_test_status character varying(40) NOT NULL,
    last_test_message text NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    notification_recipients jsonb DEFAULT '{}'::jsonb
);


--
-- Name: email_smtp_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.email_smtp_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: email_smtp_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.email_smtp_settings_id_seq OWNED BY public.email_smtp_settings.id;


--
-- Name: exchange_rate_currency_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.exchange_rate_currency_settings (
    id integer NOT NULL,
    currency_code character varying(12) NOT NULL,
    currency_name character varying(80) NOT NULL,
    enabled boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: exchange_rate_currency_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.exchange_rate_currency_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: exchange_rate_currency_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.exchange_rate_currency_settings_id_seq OWNED BY public.exchange_rate_currency_settings.id;


--
-- Name: exchange_rates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.exchange_rates (
    id integer NOT NULL,
    rate_date date NOT NULL,
    currency_code character varying(12) NOT NULL,
    currency_name character varying(80) NOT NULL,
    rate numeric(20,8) NOT NULL,
    source_updated_at timestamp without time zone,
    synced_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: exchange_rates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.exchange_rates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: exchange_rates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.exchange_rates_id_seq OWNED BY public.exchange_rates.id;


--
-- Name: label_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.label_files (
    id integer NOT NULL,
    shipment_id integer NOT NULL,
    file_path text NOT NULL,
    content_type character varying(120) NOT NULL,
    sha256 character varying(64) NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: label_files_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.label_files_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: label_files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.label_files_id_seq OWNED BY public.label_files.id;


--
-- Name: local_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.local_users (
    id integer NOT NULL,
    username character varying(80) NOT NULL,
    password_hash character varying(255) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    display_name character varying(120) DEFAULT ''::character varying,
    role_code character varying(40) DEFAULT 'user'::character varying,
    enabled boolean DEFAULT true,
    updated_at timestamp without time zone,
    role_id integer,
    wecom_mobile character varying(20) DEFAULT ''::character varying
);


--
-- Name: local_users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.local_users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: local_users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.local_users_id_seq OWNED BY public.local_users.id;


--
-- Name: logistics_authorizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.logistics_authorizations (
    id integer NOT NULL,
    carrier_code character varying(80) NOT NULL,
    carrier_name character varying(160) NOT NULL,
    account_name character varying(160) NOT NULL,
    enabled boolean NOT NULL,
    authorization_status character varying(40) NOT NULL,
    token_valid boolean,
    token_message text,
    credential_type character varying(40) NOT NULL,
    encrypted_credentials bytea,
    config_json jsonb NOT NULL,
    settings_json jsonb NOT NULL,
    last_authorized_at timestamp without time zone,
    authorization_expires_at timestamp without time zone,
    credentials_version character varying(80) NOT NULL,
    created_by character varying(80),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE logistics_authorizations; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.logistics_authorizations IS '物流公司授权配置表';


--
-- Name: COLUMN logistics_authorizations.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.id IS '主键ID';


--
-- Name: COLUMN logistics_authorizations.carrier_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.carrier_code IS '物流公司编码';


--
-- Name: COLUMN logistics_authorizations.carrier_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.carrier_name IS '物流公司名称';


--
-- Name: COLUMN logistics_authorizations.account_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.account_name IS '授权账号名称';


--
-- Name: COLUMN logistics_authorizations.enabled; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.enabled IS '是否启用';


--
-- Name: COLUMN logistics_authorizations.authorization_status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.authorization_status IS '授权状态';


--
-- Name: COLUMN logistics_authorizations.token_valid; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.token_valid IS '授权信息是否有效';


--
-- Name: COLUMN logistics_authorizations.token_message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.token_message IS '授权校验提示';


--
-- Name: COLUMN logistics_authorizations.credential_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.credential_type IS '凭据类型';


--
-- Name: COLUMN logistics_authorizations.encrypted_credentials; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.encrypted_credentials IS '加密后的物流授权 JSON';


--
-- Name: COLUMN logistics_authorizations.config_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.config_json IS '物流公司差异化配置 JSON';


--
-- Name: COLUMN logistics_authorizations.settings_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.settings_json IS '非敏感扩展设置 JSON';


--
-- Name: COLUMN logistics_authorizations.last_authorized_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.last_authorized_at IS '最近授权时间';


--
-- Name: COLUMN logistics_authorizations.authorization_expires_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.authorization_expires_at IS '授权到期时间';


--
-- Name: COLUMN logistics_authorizations.credentials_version; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.credentials_version IS '凭据版本';


--
-- Name: COLUMN logistics_authorizations.created_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.created_by IS '创建者用户名';


--
-- Name: COLUMN logistics_authorizations.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.created_at IS '创建时间';


--
-- Name: COLUMN logistics_authorizations.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_authorizations.updated_at IS '更新时间';


--
-- Name: logistics_authorizations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.logistics_authorizations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: logistics_authorizations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.logistics_authorizations_id_seq OWNED BY public.logistics_authorizations.id;


--
-- Name: logistics_match_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.logistics_match_rules (
    id integer NOT NULL,
    name character varying(160) NOT NULL,
    platform character varying(40) NOT NULL,
    priority integer NOT NULL,
    enabled boolean NOT NULL,
    shop_names jsonb NOT NULL,
    is_overseas_warehouse boolean,
    country_codes jsonb NOT NULL,
    logistics_channel character varying(160) NOT NULL,
    carrier_code character varying(80) NOT NULL,
    remark text NOT NULL,
    created_by character varying(80),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE logistics_match_rules; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.logistics_match_rules IS '物流规则表：按平台、店铺和目的国家给订单匹配物流渠道';


--
-- Name: COLUMN logistics_match_rules.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.id IS '主键ID';


--
-- Name: COLUMN logistics_match_rules.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.name IS '规则名称';


--
-- Name: COLUMN logistics_match_rules.platform; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.platform IS '适用平台代码';


--
-- Name: COLUMN logistics_match_rules.priority; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.priority IS '优先级，数值越小越优先';


--
-- Name: COLUMN logistics_match_rules.enabled; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.enabled IS '是否启用';


--
-- Name: COLUMN logistics_match_rules.shop_names; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.shop_names IS '来源店铺列表，匹配 shop_id/shop_name/account_id';


--
-- Name: COLUMN logistics_match_rules.is_overseas_warehouse; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.is_overseas_warehouse IS '是否海外仓订单；为空时不限制';


--
-- Name: COLUMN logistics_match_rules.country_codes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.country_codes IS '目的国家 ISO-2 代码列表';


--
-- Name: COLUMN logistics_match_rules.logistics_channel; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.logistics_channel IS '命中后显示的物流渠道';


--
-- Name: COLUMN logistics_match_rules.carrier_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.carrier_code IS '命中物流授权的物流商编码';


--
-- Name: COLUMN logistics_match_rules.remark; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.remark IS '备注';


--
-- Name: COLUMN logistics_match_rules.created_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.created_by IS '创建者用户名';


--
-- Name: COLUMN logistics_match_rules.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.created_at IS '创建时间';


--
-- Name: COLUMN logistics_match_rules.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_match_rules.updated_at IS '更新时间';


--
-- Name: logistics_match_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.logistics_match_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: logistics_match_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.logistics_match_rules_id_seq OWNED BY public.logistics_match_rules.id;


--
-- Name: logistics_order_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.logistics_order_submissions (
    id integer NOT NULL,
    tenant_id character varying(80) NOT NULL,
    carrier_code character varying(80) NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    transaction_id character varying(160) NOT NULL,
    customer_order_no character varying(160) NOT NULL,
    local_order_ids jsonb NOT NULL,
    request_hash character varying(64) NOT NULL,
    provider_order_no character varying(160) NOT NULL,
    channel_id integer,
    status character varying(40) NOT NULL,
    attempts integer NOT NULL,
    error_message text NOT NULL,
    response_json jsonb NOT NULL,
    submitted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE logistics_order_submissions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.logistics_order_submissions IS '第三方物流订单提交幂等记录，不保存收件人隐私';


--
-- Name: COLUMN logistics_order_submissions.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.id IS '主键ID';


--
-- Name: COLUMN logistics_order_submissions.tenant_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.tenant_id IS '租户ID';


--
-- Name: COLUMN logistics_order_submissions.carrier_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.carrier_code IS '物流公司编码';


--
-- Name: COLUMN logistics_order_submissions.platform; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.platform IS '来源平台';


--
-- Name: COLUMN logistics_order_submissions.account_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.account_id IS '来源店铺账号';


--
-- Name: COLUMN logistics_order_submissions.transaction_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.transaction_id IS '平台交易ID';


--
-- Name: COLUMN logistics_order_submissions.customer_order_no; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.customer_order_no IS '提交给物流商的客户订单号';


--
-- Name: COLUMN logistics_order_submissions.local_order_ids; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.local_order_ids IS '关联本地订单ID';


--
-- Name: COLUMN logistics_order_submissions.request_hash; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.request_hash IS '不含签名与隐私的请求指纹';


--
-- Name: COLUMN logistics_order_submissions.provider_order_no; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.provider_order_no IS '物流商订单号';


--
-- Name: COLUMN logistics_order_submissions.channel_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.channel_id IS '下单渠道ID';


--
-- Name: COLUMN logistics_order_submissions.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.status IS 'pending/succeeded/failed/uncertain';


--
-- Name: COLUMN logistics_order_submissions.attempts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.attempts IS '提交次数';


--
-- Name: COLUMN logistics_order_submissions.error_message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.error_message IS '最近一次错误';


--
-- Name: COLUMN logistics_order_submissions.response_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.response_json IS '物流商响应，不含请求隐私';


--
-- Name: COLUMN logistics_order_submissions.submitted_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.submitted_at IS '成功提交时间';


--
-- Name: COLUMN logistics_order_submissions.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.created_at IS '创建时间';


--
-- Name: COLUMN logistics_order_submissions.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.logistics_order_submissions.updated_at IS '更新时间';


--
-- Name: logistics_order_submissions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.logistics_order_submissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: logistics_order_submissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.logistics_order_submissions_id_seq OWNED BY public.logistics_order_submissions.id;


--
-- Name: model_endpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_endpoints (
    id integer NOT NULL,
    name character varying(160) NOT NULL,
    base_url text NOT NULL,
    encrypted_api_key bytea,
    enabled boolean NOT NULL,
    remark text NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE model_endpoints; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.model_endpoints IS '大模型接口配置';


--
-- Name: COLUMN model_endpoints.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_endpoints.id IS '主键ID';


--
-- Name: COLUMN model_endpoints.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_endpoints.name IS '接口配置名称';


--
-- Name: COLUMN model_endpoints.base_url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_endpoints.base_url IS 'OpenAI-compatible 基础地址';


--
-- Name: COLUMN model_endpoints.encrypted_api_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_endpoints.encrypted_api_key IS '加密后的 API Key';


--
-- Name: COLUMN model_endpoints.enabled; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_endpoints.enabled IS '是否启用';


--
-- Name: COLUMN model_endpoints.remark; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_endpoints.remark IS '备注';


--
-- Name: COLUMN model_endpoints.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_endpoints.created_at IS '创建时间';


--
-- Name: COLUMN model_endpoints.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_endpoints.updated_at IS '更新时间';


--
-- Name: model_endpoints_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.model_endpoints_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: model_endpoints_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.model_endpoints_id_seq OWNED BY public.model_endpoints.id;


--
-- Name: model_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_settings (
    id integer NOT NULL,
    name character varying(160) NOT NULL,
    model character varying(160) NOT NULL,
    endpoint_id integer NOT NULL,
    is_default boolean NOT NULL,
    supports_vision boolean NOT NULL,
    enabled boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE model_settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.model_settings IS '大模型配置';


--
-- Name: COLUMN model_settings.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_settings.id IS '主键ID';


--
-- Name: COLUMN model_settings.name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_settings.name IS '模型名称';


--
-- Name: COLUMN model_settings.model; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_settings.model IS '模型标识';


--
-- Name: COLUMN model_settings.endpoint_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_settings.endpoint_id IS '接口配置ID';


--
-- Name: COLUMN model_settings.is_default; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_settings.is_default IS '是否默认模型';


--
-- Name: COLUMN model_settings.supports_vision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_settings.supports_vision IS '是否支持图片理解';


--
-- Name: COLUMN model_settings.enabled; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_settings.enabled IS '是否启用';


--
-- Name: COLUMN model_settings.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_settings.created_at IS '创建时间';


--
-- Name: COLUMN model_settings.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.model_settings.updated_at IS '更新时间';


--
-- Name: model_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.model_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: model_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.model_settings_id_seq OWNED BY public.model_settings.id;


--
-- Name: oauth_authorization_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.oauth_authorization_sessions (
    id integer NOT NULL,
    platform_account_id integer NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    state character varying(160) NOT NULL,
    client_id character varying(255) NOT NULL,
    redirect_uri text NOT NULL,
    authorize_url text NOT NULL,
    token_url text NOT NULL,
    refresh_url text NOT NULL,
    scopes jsonb NOT NULL,
    status character varying(40) NOT NULL,
    error_message text NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    completed_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE oauth_authorization_sessions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.oauth_authorization_sessions IS '店铺首次 OAuth 授权会话';


--
-- Name: COLUMN oauth_authorization_sessions.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.id IS '主键ID';


--
-- Name: COLUMN oauth_authorization_sessions.platform_account_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.platform_account_id IS '店铺账号ID';


--
-- Name: COLUMN oauth_authorization_sessions.platform; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.platform IS '平台代码';


--
-- Name: COLUMN oauth_authorization_sessions.account_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.account_id IS '平台账号标识';


--
-- Name: COLUMN oauth_authorization_sessions.state; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.state IS 'OAuth state';


--
-- Name: COLUMN oauth_authorization_sessions.client_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.client_id IS 'OAuth Client ID';


--
-- Name: COLUMN oauth_authorization_sessions.redirect_uri; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.redirect_uri IS 'OAuth 回调地址';


--
-- Name: COLUMN oauth_authorization_sessions.authorize_url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.authorize_url IS 'OAuth 授权地址';


--
-- Name: COLUMN oauth_authorization_sessions.token_url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.token_url IS 'OAuth Token 地址';


--
-- Name: COLUMN oauth_authorization_sessions.refresh_url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.refresh_url IS 'OAuth Token 刷新地址';


--
-- Name: COLUMN oauth_authorization_sessions.scopes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.scopes IS 'OAuth scopes';


--
-- Name: COLUMN oauth_authorization_sessions.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.status IS 'pending/success/failed/expired';


--
-- Name: COLUMN oauth_authorization_sessions.error_message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.error_message IS '授权错误信息';


--
-- Name: COLUMN oauth_authorization_sessions.expires_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.expires_at IS '会话过期时间';


--
-- Name: COLUMN oauth_authorization_sessions.completed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.completed_at IS '完成时间';


--
-- Name: COLUMN oauth_authorization_sessions.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.created_at IS '创建时间';


--
-- Name: COLUMN oauth_authorization_sessions.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.oauth_authorization_sessions.updated_at IS '更新时间';


--
-- Name: oauth_authorization_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.oauth_authorization_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: oauth_authorization_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.oauth_authorization_sessions_id_seq OWNED BY public.oauth_authorization_sessions.id;


--
-- Name: order_follow_up_export_artifacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_follow_up_export_artifacts (
    id integer NOT NULL,
    job_id integer NOT NULL,
    artifact_type character varying(40) NOT NULL,
    status character varying(40) NOT NULL,
    file_path text NOT NULL,
    filename character varying(255) NOT NULL,
    sha256 character varying(64) NOT NULL,
    size_bytes bigint NOT NULL,
    row_count integer NOT NULL,
    error_message text NOT NULL,
    created_at timestamp without time zone NOT NULL,
    finished_at timestamp without time zone
);


--
-- Name: TABLE order_follow_up_export_artifacts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.order_follow_up_export_artifacts IS 'Order follow up 导出文件记录';


--
-- Name: COLUMN order_follow_up_export_artifacts.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.id IS '主键ID';


--
-- Name: COLUMN order_follow_up_export_artifacts.job_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.job_id IS '导出任务ID';


--
-- Name: COLUMN order_follow_up_export_artifacts.artifact_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.artifact_type IS 'workbook/purchase_plan';


--
-- Name: COLUMN order_follow_up_export_artifacts.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.status IS '文件状态';


--
-- Name: COLUMN order_follow_up_export_artifacts.file_path; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.file_path IS '文件绝对路径';


--
-- Name: COLUMN order_follow_up_export_artifacts.filename; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.filename IS '文件名';


--
-- Name: COLUMN order_follow_up_export_artifacts.sha256; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.sha256 IS '文件SHA-256';


--
-- Name: COLUMN order_follow_up_export_artifacts.size_bytes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.size_bytes IS '文件大小';


--
-- Name: COLUMN order_follow_up_export_artifacts.row_count; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.row_count IS '本批写入行数';


--
-- Name: COLUMN order_follow_up_export_artifacts.error_message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.error_message IS '错误信息';


--
-- Name: COLUMN order_follow_up_export_artifacts.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.created_at IS '创建时间';


--
-- Name: COLUMN order_follow_up_export_artifacts.finished_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_artifacts.finished_at IS '完成时间';


--
-- Name: order_follow_up_export_artifacts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.order_follow_up_export_artifacts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: order_follow_up_export_artifacts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.order_follow_up_export_artifacts_id_seq OWNED BY public.order_follow_up_export_artifacts.id;


--
-- Name: order_follow_up_export_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_follow_up_export_items (
    id integer NOT NULL,
    job_id integer NOT NULL,
    order_id integer NOT NULL,
    order_item_id integer NOT NULL,
    action character varying(40) NOT NULL,
    status character varying(40) NOT NULL,
    mapping_status character varying(40) NOT NULL,
    worksheet_row integer,
    snapshot_json jsonb NOT NULL,
    error_message text NOT NULL,
    exported_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE order_follow_up_export_items; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.order_follow_up_export_items IS 'Order follow up 导出订单商品明细';


--
-- Name: COLUMN order_follow_up_export_items.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.id IS '主键ID';


--
-- Name: COLUMN order_follow_up_export_items.job_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.job_id IS '导出任务ID';


--
-- Name: COLUMN order_follow_up_export_items.order_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.order_id IS '订单ID快照';


--
-- Name: COLUMN order_follow_up_export_items.order_item_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.order_item_id IS '订单商品ID快照';


--
-- Name: COLUMN order_follow_up_export_items.action; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.action IS 'append/update/skip';


--
-- Name: COLUMN order_follow_up_export_items.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.status IS '导出状态';


--
-- Name: COLUMN order_follow_up_export_items.mapping_status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.mapping_status IS 'mapped/missing';


--
-- Name: COLUMN order_follow_up_export_items.worksheet_row; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.worksheet_row IS '订单总表行号';


--
-- Name: COLUMN order_follow_up_export_items.snapshot_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.snapshot_json IS '导出数据快照';


--
-- Name: COLUMN order_follow_up_export_items.error_message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.error_message IS '错误信息';


--
-- Name: COLUMN order_follow_up_export_items.exported_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.exported_at IS '成功导出时间';


--
-- Name: COLUMN order_follow_up_export_items.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.created_at IS '创建时间';


--
-- Name: COLUMN order_follow_up_export_items.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_items.updated_at IS '更新时间';


--
-- Name: order_follow_up_export_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.order_follow_up_export_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: order_follow_up_export_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.order_follow_up_export_items_id_seq OWNED BY public.order_follow_up_export_items.id;


--
-- Name: order_follow_up_export_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_follow_up_export_jobs (
    id integer NOT NULL,
    scheduled_task_run_id integer,
    workbook_key character varying(255) NOT NULL,
    status character varying(40) NOT NULL,
    attempt_count integer NOT NULL,
    max_attempts integer NOT NULL,
    next_retry_at timestamp without time zone,
    claimed_by character varying(255) NOT NULL,
    claimed_at timestamp without time zone,
    lease_until timestamp without time zone,
    heartbeat_at timestamp without time zone,
    error_message text NOT NULL,
    stats_json jsonb NOT NULL,
    started_at timestamp without time zone,
    finished_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE order_follow_up_export_jobs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.order_follow_up_export_jobs IS 'Order follow up 独立导出任务';


--
-- Name: COLUMN order_follow_up_export_jobs.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.id IS '主键ID';


--
-- Name: COLUMN order_follow_up_export_jobs.scheduled_task_run_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.scheduled_task_run_id IS '来源定时任务运行ID';


--
-- Name: COLUMN order_follow_up_export_jobs.workbook_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.workbook_key IS '目标工作簿标识';


--
-- Name: COLUMN order_follow_up_export_jobs.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.status IS '任务状态';


--
-- Name: COLUMN order_follow_up_export_jobs.attempt_count; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.attempt_count IS '已执行次数';


--
-- Name: COLUMN order_follow_up_export_jobs.max_attempts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.max_attempts IS '最大执行次数';


--
-- Name: COLUMN order_follow_up_export_jobs.next_retry_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.next_retry_at IS '下次重试时间';


--
-- Name: COLUMN order_follow_up_export_jobs.claimed_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.claimed_by IS '领取任务的执行器';


--
-- Name: COLUMN order_follow_up_export_jobs.claimed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.claimed_at IS '领取时间';


--
-- Name: COLUMN order_follow_up_export_jobs.lease_until; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.lease_until IS '执行租约截止时间';


--
-- Name: COLUMN order_follow_up_export_jobs.heartbeat_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.heartbeat_at IS '执行器心跳时间';


--
-- Name: COLUMN order_follow_up_export_jobs.error_message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.error_message IS '最近一次错误';


--
-- Name: COLUMN order_follow_up_export_jobs.stats_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.stats_json IS '导出统计';


--
-- Name: COLUMN order_follow_up_export_jobs.started_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.started_at IS '首次开始时间';


--
-- Name: COLUMN order_follow_up_export_jobs.finished_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.finished_at IS '完成时间';


--
-- Name: COLUMN order_follow_up_export_jobs.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.created_at IS '创建时间';


--
-- Name: COLUMN order_follow_up_export_jobs.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_follow_up_export_jobs.updated_at IS '更新时间';


--
-- Name: order_follow_up_export_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.order_follow_up_export_jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: order_follow_up_export_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.order_follow_up_export_jobs_id_seq OWNED BY public.order_follow_up_export_jobs.id;


--
-- Name: order_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_items (
    id integer NOT NULL,
    order_id integer NOT NULL,
    sku character varying(255) NOT NULL,
    quantity integer NOT NULL,
    unit_price character varying(40),
    currency character varying(16) NOT NULL,
    raw_payload jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    platform_product_name character varying(500) DEFAULT ''::character varying
);


--
-- Name: order_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.order_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: order_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.order_items_id_seq OWNED BY public.order_items.id;


--
-- Name: order_operation_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_operation_logs (
    id integer NOT NULL,
    order_id integer NOT NULL,
    operation_type character varying(80) NOT NULL,
    operation_attribute character varying(120) NOT NULL,
    description text NOT NULL,
    operator character varying(80) NOT NULL,
    source character varying(40) NOT NULL,
    event_key character varying(180) NOT NULL,
    extra jsonb NOT NULL,
    operated_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE order_operation_logs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.order_operation_logs IS '订单操作日志表';


--
-- Name: COLUMN order_operation_logs.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_operation_logs.id IS '主键ID';


--
-- Name: COLUMN order_operation_logs.order_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_operation_logs.order_id IS '关联订单ID';


--
-- Name: COLUMN order_operation_logs.operation_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_operation_logs.operation_type IS '操作类型编码';


--
-- Name: COLUMN order_operation_logs.operation_attribute; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_operation_logs.operation_attribute IS '操作属性展示名';


--
-- Name: COLUMN order_operation_logs.description; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_operation_logs.description IS '操作描述';


--
-- Name: COLUMN order_operation_logs.operator; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_operation_logs.operator IS '操作员';


--
-- Name: COLUMN order_operation_logs.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_operation_logs.source IS '来源 manual/system/history';


--
-- Name: COLUMN order_operation_logs.event_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_operation_logs.event_key IS '幂等事件键';


--
-- Name: COLUMN order_operation_logs.extra; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_operation_logs.extra IS '扩展上下文';


--
-- Name: COLUMN order_operation_logs.operated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_operation_logs.operated_at IS '操作时间';


--
-- Name: COLUMN order_operation_logs.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.order_operation_logs.created_at IS '创建时间';


--
-- Name: order_operation_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.order_operation_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: order_operation_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.order_operation_logs_id_seq OWNED BY public.order_operation_logs.id;


--
-- Name: order_risk_handlings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_risk_handlings (
    id integer NOT NULL,
    order_id integer NOT NULL,
    handled_at timestamp without time zone NOT NULL,
    handled_by character varying(120) NOT NULL,
    note text NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE order_risk_handlings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.order_risk_handlings IS '订单发货风险跟进状态';


--
-- Name: order_risk_handlings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.order_risk_handlings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: order_risk_handlings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.order_risk_handlings_id_seq OWNED BY public.order_risk_handlings.id;


--
-- Name: orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orders (
    id integer NOT NULL,
    tenant_id character varying(80) NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    shop_id character varying(120) NOT NULL,
    shop_name character varying(160),
    site character varying(80),
    platform_order_id character varying(160) NOT NULL,
    platform_order_no character varying(160),
    posting_number character varying(160) NOT NULL,
    buyer_id character varying(120),
    buyer_name character varying(160),
    platform_status character varying(80) NOT NULL,
    biz_status character varying(40),
    local_status character varying(80) NOT NULL,
    platform_handover_deadline timestamp without time zone,
    country_code character varying(8),
    country_name_cn character varying(80),
    buyer_selected_logistics character varying(160),
    order_amount character varying(40),
    currency character varying(16),
    payment_at timestamp without time zone,
    shipping_deadline_at timestamp without time zone,
    shipment_tracking_number character varying(160),
    handover_at timestamp without time zone,
    shipped_at timestamp without time zone,
    raw_payload jsonb NOT NULL,
    error_message text NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    last_api_payload jsonb DEFAULT '{}'::jsonb,
    picking_at timestamp without time zone,
    marked_shipped_at timestamp without time zone,
    label_printed_at timestamp without time zone,
    platform_created_at timestamp without time zone,
    dispatch_deadline_at timestamp without time zone,
    internal_order_no character varying(32),
    fulfillment_type character varying(40) DEFAULT 'FBS'::character varying,
    is_overseas_warehouse boolean DEFAULT false,
    bsi_order_no character varying(160) DEFAULT ''::character varying,
    bsi_submitted_at timestamp without time zone,
    logistics_channel character varying(160) DEFAULT ''::character varying,
    logistics_carrier_code character varying(80) DEFAULT ''::character varying,
    logistics_match_rule_id integer,
    logistics_match_rule_name character varying(160) DEFAULT ''::character varying,
    logistics_match_status character varying(40) DEFAULT 'unmatched'::character varying,
    logistics_match_reason text DEFAULT ''::text,
    logistics_matched_at timestamp without time zone,
    logistics_last_synced_at timestamp without time zone
);


--
-- Name: orders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.orders_id_seq OWNED BY public.orders.id;


--
-- Name: outbound_scan_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.outbound_scan_records (
    id integer NOT NULL,
    tracking_number character varying(160) NOT NULL,
    raw_input character varying(255) NOT NULL,
    order_id integer,
    platform character varying(40) NOT NULL,
    shop_name character varying(160) NOT NULL,
    platform_order_no character varying(160) NOT NULL,
    posting_number character varying(160) NOT NULL,
    order_status character varying(40) NOT NULL,
    platform_status character varying(80) NOT NULL,
    result character varying(40) NOT NULL,
    message text NOT NULL,
    scanned_by character varying(80) NOT NULL,
    scanned_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: outbound_scan_records_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.outbound_scan_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: outbound_scan_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.outbound_scan_records_id_seq OWNED BY public.outbound_scan_records.id;


--
-- Name: platform_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_accounts (
    id integer NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    display_name character varying(160) NOT NULL,
    enabled boolean NOT NULL,
    auth_type character varying(40) NOT NULL,
    settings jsonb NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    credential_type character varying(40) DEFAULT 'api_key'::character varying,
    encrypted_credentials bytea,
    status character varying(40) DEFAULT 'active'::character varying,
    session_expires_at timestamp without time zone,
    last_sync_at timestamp without time zone,
    last_sync_status character varying(255),
    credentials_version character varying(80) DEFAULT ''::character varying,
    authorization_status character varying(40) DEFAULT 'unauthorized'::character varying,
    token_valid boolean,
    token_message text,
    last_authorized_at timestamp without time zone,
    authorization_expires_at timestamp without time zone,
    created_by character varying(80),
    created_at timestamp without time zone
);


--
-- Name: platform_accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.platform_accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: platform_accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.platform_accounts_id_seq OWNED BY public.platform_accounts.id;


--
-- Name: platform_print_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_print_settings (
    id integer NOT NULL,
    platform character varying(40) NOT NULL,
    printer_name character varying(255) NOT NULL,
    enabled boolean NOT NULL,
    remark text NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    document_type character varying(40) DEFAULT 'label'::character varying,
    printer_system character varying(40) DEFAULT ''::character varying,
    printer_device_uri character varying(500) DEFAULT ''::character varying,
    printer_driver_name character varying(255) DEFAULT ''::character varying,
    printer_port_name character varying(255) DEFAULT ''::character varying,
    printer_fingerprint character varying(80) DEFAULT ''::character varying,
    page_orientation character varying(20) DEFAULT 'auto'::character varying
);


--
-- Name: platform_print_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.platform_print_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: platform_print_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.platform_print_settings_id_seq OWNED BY public.platform_print_settings.id;


--
-- Name: platform_product_catalog_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_product_catalog_items (
    id integer NOT NULL,
    shop_id integer NOT NULL,
    product_id integer,
    pricing_rule_id integer,
    platform character varying(40) NOT NULL,
    platform_product_id character varying(255) NOT NULL,
    platform_sku character varying(255) NOT NULL,
    product_name character varying(500) NOT NULL,
    listing_status character varying(80) NOT NULL,
    warehouse_code character varying(160) NOT NULL,
    warehouse_name character varying(255) NOT NULL,
    fulfillment_type character varying(80) NOT NULL,
    logistics_type character varying(160) NOT NULL,
    available_stock integer NOT NULL,
    reserved_stock integer,
    price_amount numeric(16,4),
    price_currency character varying(12) NOT NULL,
    exchange_rate numeric(20,8),
    exchange_rate_date date,
    current_price_cny numeric(16,4),
    cost_cny numeric(16,4),
    commission_rate numeric(10,6),
    shipping_fee_cny numeric(16,4),
    target_margin_rate numeric(10,6),
    current_profit_cny numeric(16,4),
    current_margin_rate numeric(10,6),
    suggested_price_cny numeric(16,4),
    calculation_status character varying(80) NOT NULL,
    calculation_message text NOT NULL,
    raw_payload json NOT NULL,
    last_synced_at timestamp without time zone,
    last_seen_at timestamp without time zone,
    calculated_at timestamp without time zone,
    mapped_at timestamp without time zone,
    mapped_by character varying(80) NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE platform_product_catalog_items; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.platform_product_catalog_items IS '平台商品目录，按店铺、平台 SKU 与平台仓库保存可售库存';


--
-- Name: platform_product_catalog_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.platform_product_catalog_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: platform_product_catalog_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.platform_product_catalog_items_id_seq OWNED BY public.platform_product_catalog_items.id;


--
-- Name: platform_product_pricing_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_product_pricing_rules (
    id integer NOT NULL,
    name character varying(160) NOT NULL,
    platform character varying(40) NOT NULL,
    shop_id integer,
    product_id integer,
    warehouse_code character varying(160) NOT NULL,
    logistics_type character varying(160) NOT NULL,
    commission_rate numeric(10,6) NOT NULL,
    base_shipping_fee_cny numeric(16,4) NOT NULL,
    shipping_fee_per_kg_cny numeric(16,4) NOT NULL,
    target_margin_rate numeric(10,6) NOT NULL,
    price_increment_cny numeric(16,4) NOT NULL,
    priority integer NOT NULL,
    enabled boolean NOT NULL,
    remark text NOT NULL,
    created_by character varying(80) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE platform_product_pricing_rules; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.platform_product_pricing_rules IS '平台商品佣金、运费与建议价规则';


--
-- Name: platform_product_pricing_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.platform_product_pricing_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: platform_product_pricing_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.platform_product_pricing_rules_id_seq OWNED BY public.platform_product_pricing_rules.id;


--
-- Name: platform_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_settings (
    id integer NOT NULL,
    platform character varying(40) NOT NULL,
    platform_name character varying(160) NOT NULL,
    enabled boolean NOT NULL,
    sort_order integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE platform_settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.platform_settings IS '平台总开关设置';


--
-- Name: COLUMN platform_settings.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.platform_settings.id IS '主键ID';


--
-- Name: COLUMN platform_settings.platform; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.platform_settings.platform IS '平台代码';


--
-- Name: COLUMN platform_settings.platform_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.platform_settings.platform_name IS '平台名称';


--
-- Name: COLUMN platform_settings.enabled; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.platform_settings.enabled IS '是否启用';


--
-- Name: COLUMN platform_settings.sort_order; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.platform_settings.sort_order IS '显示顺序';


--
-- Name: COLUMN platform_settings.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.platform_settings.created_at IS '创建时间';


--
-- Name: COLUMN platform_settings.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.platform_settings.updated_at IS '更新时间';


--
-- Name: platform_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.platform_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: platform_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.platform_settings_id_seq OWNED BY public.platform_settings.id;


--
-- Name: product_inventory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_inventory (
    id integer NOT NULL,
    product_id integer NOT NULL,
    product_name character varying(255) NOT NULL,
    stock_qty integer NOT NULL,
    last_count_qty integer NOT NULL,
    remark text,
    updated_by character varying(80),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: product_inventory_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.product_inventory_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: product_inventory_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.product_inventory_id_seq OWNED BY public.product_inventory.id;


--
-- Name: product_shop_mappings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_shop_mappings (
    id integer NOT NULL,
    product_id integer NOT NULL,
    shop_id integer NOT NULL,
    shop_sku character varying(255) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: product_shop_mappings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.product_shop_mappings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: product_shop_mappings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.product_shop_mappings_id_seq OWNED BY public.product_shop_mappings.id;


--
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    id integer NOT NULL,
    product_code character varying(40) NOT NULL,
    internal_name character varying(255) NOT NULL,
    cost numeric(12,2),
    weight numeric(12,3),
    safety_stock integer,
    enabled boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    buyer_user_id integer,
    english_name character varying(255) DEFAULT ''::character varying,
    gross_weight numeric(12,3),
    package_length numeric(12,2),
    package_width numeric(12,2),
    package_height numeric(12,2),
    ean character varying(64) DEFAULT ''::character varying,
    description text DEFAULT ''::text,
    main_image_url text DEFAULT ''::text,
    is_slow_moving_material boolean DEFAULT false
);


--
-- Name: products_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.products_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: products_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.products_id_seq OWNED BY public.products.id;


--
-- Name: purchase_order_edit_locks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.purchase_order_edit_locks (
    id integer NOT NULL,
    purchase_order_id integer NOT NULL,
    locked_by character varying(80) NOT NULL,
    locked_at timestamp without time zone NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: purchase_order_edit_locks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.purchase_order_edit_locks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchase_order_edit_locks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.purchase_order_edit_locks_id_seq OWNED BY public.purchase_order_edit_locks.id;


--
-- Name: purchase_order_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.purchase_order_items (
    id integer NOT NULL,
    purchase_order_id integer NOT NULL,
    product_id integer,
    product_name character varying(255) NOT NULL,
    required_qty integer NOT NULL,
    buyer character varying(120),
    total_cost_record numeric(12,2),
    purchase_cost numeric(12,2),
    purchase_channel character varying(160),
    purchase_qty integer NOT NULL,
    remark text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    buyer_user_id integer
);


--
-- Name: purchase_order_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.purchase_order_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchase_order_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.purchase_order_items_id_seq OWNED BY public.purchase_order_items.id;


--
-- Name: purchase_order_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.purchase_order_logs (
    id integer NOT NULL,
    purchase_order_id integer,
    purchase_no character varying(40) NOT NULL,
    action character varying(40) NOT NULL,
    operator character varying(80),
    snapshot jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: purchase_order_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.purchase_order_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchase_order_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.purchase_order_logs_id_seq OWNED BY public.purchase_order_logs.id;


--
-- Name: purchase_order_sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.purchase_order_sources (
    id integer NOT NULL,
    purchase_order_id integer NOT NULL,
    purchase_order_item_id integer NOT NULL,
    order_id integer NOT NULL,
    order_item_id integer NOT NULL,
    product_id integer,
    product_name character varying(255) NOT NULL,
    quantity integer NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: purchase_order_sources_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.purchase_order_sources_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchase_order_sources_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.purchase_order_sources_id_seq OWNED BY public.purchase_order_sources.id;


--
-- Name: purchase_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.purchase_orders (
    id integer NOT NULL,
    purchase_no character varying(40) NOT NULL,
    status character varying(40) NOT NULL,
    source_count integer NOT NULL,
    item_count integer NOT NULL,
    total_required_qty integer NOT NULL,
    created_by character varying(80),
    remark text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    purchase_date date
);


--
-- Name: purchase_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.purchase_orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchase_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.purchase_orders_id_seq OWNED BY public.purchase_orders.id;


--
-- Name: role_menu_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_menu_permissions (
    id integer NOT NULL,
    role_id integer NOT NULL,
    menu_code character varying(80) NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: role_menu_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.role_menu_permissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: role_menu_permissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.role_menu_permissions_id_seq OWNED BY public.role_menu_permissions.id;


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    id integer NOT NULL,
    code character varying(80) NOT NULL,
    name character varying(120) NOT NULL,
    description text NOT NULL,
    is_system boolean NOT NULL,
    enabled boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: roles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.roles_id_seq OWNED BY public.roles.id;


--
-- Name: scheduled_task_run_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scheduled_task_run_orders (
    id integer NOT NULL,
    run_id integer NOT NULL,
    order_id integer NOT NULL,
    platform character varying(40) DEFAULT ''::character varying,
    purchase_order_id integer,
    pdf_generated boolean DEFAULT false,
    pdf_file_path text DEFAULT ''::text,
    printer_name character varying(255) DEFAULT ''::character varying,
    print_submitted boolean DEFAULT false,
    print_message text DEFAULT ''::text,
    status_before character varying(40) DEFAULT ''::character varying,
    status_after character varying(40) DEFAULT ''::character varying,
    needs_reprint boolean DEFAULT false,
    error_message text DEFAULT ''::text,
    created_at timestamp without time zone DEFAULT timezone('UTC'::text, now()),
    print_job_name character varying(255) DEFAULT ''::character varying
);


--
-- Name: scheduled_task_run_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scheduled_task_run_orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scheduled_task_run_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scheduled_task_run_orders_id_seq OWNED BY public.scheduled_task_run_orders.id;


--
-- Name: scheduled_task_run_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scheduled_task_run_steps (
    id integer NOT NULL,
    run_id integer NOT NULL,
    step_code character varying(80) NOT NULL,
    step_name character varying(120) NOT NULL,
    status character varying(40) DEFAULT 'running'::character varying,
    message text DEFAULT ''::text,
    stats_json jsonb DEFAULT '{}'::jsonb,
    payload_json jsonb DEFAULT '{}'::jsonb,
    started_at timestamp without time zone DEFAULT timezone('UTC'::text, now()),
    ended_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT timezone('UTC'::text, now())
);


--
-- Name: scheduled_task_run_steps_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scheduled_task_run_steps_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scheduled_task_run_steps_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scheduled_task_run_steps_id_seq OWNED BY public.scheduled_task_run_steps.id;


--
-- Name: scheduled_task_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scheduled_task_runs (
    id integer NOT NULL,
    scheduled_task_id integer,
    task_type character varying(80) NOT NULL,
    trigger_mode character varying(40) DEFAULT 'scheduler'::character varying,
    status character varying(40) DEFAULT 'running'::character varying,
    summary text DEFAULT ''::text,
    stats_json jsonb DEFAULT '{}'::jsonb,
    started_at timestamp without time zone DEFAULT timezone('UTC'::text, now()),
    ended_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT timezone('UTC'::text, now()),
    attempt_no integer DEFAULT 0,
    max_retry_count integer DEFAULT 0,
    parent_run_id integer,
    original_run_id integer,
    next_retry_at timestamp without time zone,
    retry_reason text DEFAULT ''::text,
    email_sent boolean DEFAULT false,
    email_error text DEFAULT ''::text
);


--
-- Name: scheduled_task_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scheduled_task_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scheduled_task_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scheduled_task_runs_id_seq OWNED BY public.scheduled_task_runs.id;


--
-- Name: scheduled_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scheduled_tasks (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    task_type character varying(80) DEFAULT 'auto_order_pipeline'::character varying NOT NULL,
    cron_expr character varying(120) NOT NULL,
    enabled boolean NOT NULL,
    settings jsonb NOT NULL,
    remark text NOT NULL,
    last_run_at timestamp without time zone,
    last_status character varying(40) NOT NULL,
    last_message text NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: scheduled_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scheduled_tasks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scheduled_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scheduled_tasks_id_seq OWNED BY public.scheduled_tasks.id;


--
-- Name: scheduler_heartbeats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scheduler_heartbeats (
    id integer NOT NULL,
    owner_id character varying(160) NOT NULL,
    host character varying(160) NOT NULL,
    pid integer,
    is_leader boolean NOT NULL,
    started_at timestamp without time zone NOT NULL,
    last_seen_at timestamp without time zone NOT NULL,
    message text NOT NULL
);


--
-- Name: TABLE scheduler_heartbeats; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.scheduler_heartbeats IS '调度器进程心跳表（用于确认唯一调度 owner）';


--
-- Name: COLUMN scheduler_heartbeats.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheduler_heartbeats.id IS '主键ID';


--
-- Name: COLUMN scheduler_heartbeats.owner_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheduler_heartbeats.owner_id IS '调度器 owner 标识';


--
-- Name: COLUMN scheduler_heartbeats.host; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheduler_heartbeats.host IS '主机名';


--
-- Name: COLUMN scheduler_heartbeats.pid; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheduler_heartbeats.pid IS '进程ID';


--
-- Name: COLUMN scheduler_heartbeats.is_leader; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheduler_heartbeats.is_leader IS '是否当前 leader';


--
-- Name: COLUMN scheduler_heartbeats.started_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheduler_heartbeats.started_at IS '启动时间';


--
-- Name: COLUMN scheduler_heartbeats.last_seen_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheduler_heartbeats.last_seen_at IS '最近心跳时间';


--
-- Name: COLUMN scheduler_heartbeats.message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.scheduler_heartbeats.message IS '状态说明';


--
-- Name: scheduler_heartbeats_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scheduler_heartbeats_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scheduler_heartbeats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scheduler_heartbeats_id_seq OWNED BY public.scheduler_heartbeats.id;


--
-- Name: shipments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shipments (
    id integer NOT NULL,
    order_id integer NOT NULL,
    platform_shipment_id character varying(160) NOT NULL,
    tracking_number character varying(160) NOT NULL,
    carrier character varying(120) NOT NULL,
    status character varying(80) NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: shipments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.shipments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: shipments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.shipments_id_seq OWNED BY public.shipments.id;


--
-- Name: shipping_deadline_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shipping_deadline_settings (
    id integer NOT NULL,
    platform character varying(40) NOT NULL,
    base_date_field character varying(40) NOT NULL,
    offset_days integer NOT NULL,
    enabled boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    sort_order integer DEFAULT 0
);


--
-- Name: shipping_deadline_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.shipping_deadline_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: shipping_deadline_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.shipping_deadline_settings_id_seq OWNED BY public.shipping_deadline_settings.id;


--
-- Name: sync_account_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sync_account_states (
    id integer NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    job_type character varying(80) NOT NULL,
    last_started_at timestamp without time zone,
    last_finished_at timestamp without time zone,
    last_success_at timestamp without time zone,
    last_failed_at timestamp without time zone,
    next_due_at timestamp without time zone,
    last_status character varying(40) NOT NULL,
    consecutive_failures integer NOT NULL,
    overdue_since timestamp without time zone,
    catchup_required boolean NOT NULL,
    catchup_from timestamp without time zone,
    catchup_to timestamp without time zone,
    last_message text NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE sync_account_states; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.sync_account_states IS '店铺同步运行状态表（心跳、超时、补偿状态）';


--
-- Name: COLUMN sync_account_states.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.id IS '主键ID';


--
-- Name: COLUMN sync_account_states.platform; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.platform IS '平台代码';


--
-- Name: COLUMN sync_account_states.account_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.account_id IS '平台账号标识';


--
-- Name: COLUMN sync_account_states.job_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.job_type IS '任务类型';


--
-- Name: COLUMN sync_account_states.last_started_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.last_started_at IS '最近开始时间';


--
-- Name: COLUMN sync_account_states.last_finished_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.last_finished_at IS '最近结束时间';


--
-- Name: COLUMN sync_account_states.last_success_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.last_success_at IS '最近成功时间';


--
-- Name: COLUMN sync_account_states.last_failed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.last_failed_at IS '最近失败时间';


--
-- Name: COLUMN sync_account_states.next_due_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.next_due_at IS '下次应执行时间';


--
-- Name: COLUMN sync_account_states.last_status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.last_status IS '最近状态';


--
-- Name: COLUMN sync_account_states.consecutive_failures; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.consecutive_failures IS '连续失败次数';


--
-- Name: COLUMN sync_account_states.overdue_since; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.overdue_since IS '开始超时时间';


--
-- Name: COLUMN sync_account_states.catchup_required; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.catchup_required IS '是否需要补偿同步';


--
-- Name: COLUMN sync_account_states.catchup_from; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.catchup_from IS '补偿开始时间';


--
-- Name: COLUMN sync_account_states.catchup_to; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.catchup_to IS '补偿结束时间';


--
-- Name: COLUMN sync_account_states.last_message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.last_message IS '最近消息';


--
-- Name: COLUMN sync_account_states.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_account_states.updated_at IS '更新时间';


--
-- Name: sync_account_states_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sync_account_states_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sync_account_states_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sync_account_states_id_seq OWNED BY public.sync_account_states.id;


--
-- Name: sync_audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sync_audit_logs (
    id integer NOT NULL,
    event_type character varying(80) NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    job_type character varying(80) NOT NULL,
    status character varying(40) NOT NULL,
    message text NOT NULL,
    owner_id character varying(160) NOT NULL,
    extra jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE sync_audit_logs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.sync_audit_logs IS '同步调度审计日志表';


--
-- Name: COLUMN sync_audit_logs.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_audit_logs.id IS '主键ID';


--
-- Name: COLUMN sync_audit_logs.event_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_audit_logs.event_type IS '事件类型';


--
-- Name: COLUMN sync_audit_logs.platform; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_audit_logs.platform IS '平台代码';


--
-- Name: COLUMN sync_audit_logs.account_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_audit_logs.account_id IS '平台账号标识';


--
-- Name: COLUMN sync_audit_logs.job_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_audit_logs.job_type IS '任务类型';


--
-- Name: COLUMN sync_audit_logs.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_audit_logs.status IS '状态';


--
-- Name: COLUMN sync_audit_logs.message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_audit_logs.message IS '事件说明';


--
-- Name: COLUMN sync_audit_logs.owner_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_audit_logs.owner_id IS '调度器 owner';


--
-- Name: COLUMN sync_audit_logs.extra; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_audit_logs.extra IS '扩展信息';


--
-- Name: COLUMN sync_audit_logs.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.sync_audit_logs.created_at IS '创建时间';


--
-- Name: sync_audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sync_audit_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sync_audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sync_audit_logs_id_seq OWNED BY public.sync_audit_logs.id;


--
-- Name: sync_cursors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sync_cursors (
    id integer NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    cursor_key character varying(120) NOT NULL,
    cursor_value text NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: sync_cursors_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sync_cursors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sync_cursors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sync_cursors_id_seq OWNED BY public.sync_cursors.id;


--
-- Name: sync_job_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sync_job_logs (
    id integer NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    job_type character varying(80) NOT NULL,
    status character varying(40) NOT NULL,
    message text NOT NULL,
    started_at timestamp without time zone NOT NULL,
    ended_at timestamp without time zone
);


--
-- Name: sync_job_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sync_job_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sync_job_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sync_job_logs_id_seq OWNED BY public.sync_job_logs.id;


--
-- Name: sync_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sync_settings (
    id integer NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    enabled boolean NOT NULL,
    interval_seconds integer NOT NULL,
    dry_run_fulfillment boolean NOT NULL,
    last_run_at timestamp without time zone
);


--
-- Name: sync_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sync_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sync_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sync_settings_id_seq OWNED BY public.sync_settings.id;


--
-- Name: traffic_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.traffic_metrics (
    id integer NOT NULL,
    record_key character varying(64) NOT NULL,
    platform_account_id integer NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    shop_name character varying(160) NOT NULL,
    source character varying(20) NOT NULL,
    grain character varying(30) NOT NULL,
    stat_date date NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    region character varying(40) NOT NULL,
    entity_type character varying(30) NOT NULL,
    entity_id character varying(180) NOT NULL,
    sku character varying(255) NOT NULL,
    product_name character varying(500) NOT NULL,
    impressions bigint,
    clicks bigint,
    add_to_cart bigint,
    orders bigint,
    buyers bigint,
    units_sold bigint,
    negative_reviews bigint,
    revenue numeric(20,4),
    currency character varying(16) NOT NULL,
    raw_data jsonb NOT NULL,
    synced_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE traffic_metrics; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.traffic_metrics IS '跨平台流量分析明细（按平台原始统计口径保存）';


--
-- Name: COLUMN traffic_metrics.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.id IS '主键ID';


--
-- Name: COLUMN traffic_metrics.record_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.record_key IS '标准维度幂等键';


--
-- Name: COLUMN traffic_metrics.platform_account_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.platform_account_id IS '平台店铺ID';


--
-- Name: COLUMN traffic_metrics.platform; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.platform IS '平台代码';


--
-- Name: COLUMN traffic_metrics.account_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.account_id IS '平台账号标识';


--
-- Name: COLUMN traffic_metrics.shop_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.shop_name IS '店铺名称快照';


--
-- Name: COLUMN traffic_metrics.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.source IS '流量来源 organic/ads';


--
-- Name: COLUMN traffic_metrics.grain; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.grain IS '统计口径 daily/date_range/rolling_30d';


--
-- Name: COLUMN traffic_metrics.stat_date; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.stat_date IS '统计日期或快照日期';


--
-- Name: COLUMN traffic_metrics.period_start; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.period_start IS '统计周期开始';


--
-- Name: COLUMN traffic_metrics.period_end; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.period_end IS '统计周期结束';


--
-- Name: COLUMN traffic_metrics.region; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.region IS '站点或地区';


--
-- Name: COLUMN traffic_metrics.entity_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.entity_type IS '实体类型 sku/shop/campaign';


--
-- Name: COLUMN traffic_metrics.entity_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.entity_id IS '平台商品或实体ID';


--
-- Name: COLUMN traffic_metrics.sku; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.sku IS '店铺SKU';


--
-- Name: COLUMN traffic_metrics.product_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.product_name IS '商品名称';


--
-- Name: COLUMN traffic_metrics.impressions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.impressions IS '曝光量';


--
-- Name: COLUMN traffic_metrics.clicks; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.clicks IS '点击或访问量';


--
-- Name: COLUMN traffic_metrics.add_to_cart; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.add_to_cart IS '加购量';


--
-- Name: COLUMN traffic_metrics.orders; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.orders IS '订单数';


--
-- Name: COLUMN traffic_metrics.buyers; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.buyers IS '买家数';


--
-- Name: COLUMN traffic_metrics.units_sold; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.units_sold IS '售出件数';


--
-- Name: COLUMN traffic_metrics.negative_reviews; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.negative_reviews IS '负面评价数';


--
-- Name: COLUMN traffic_metrics.revenue; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.revenue IS '成交金额';


--
-- Name: COLUMN traffic_metrics.currency; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.currency IS '币种';


--
-- Name: COLUMN traffic_metrics.raw_data; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.raw_data IS '原始口径补充信息';


--
-- Name: COLUMN traffic_metrics.synced_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.synced_at IS '同步时间';


--
-- Name: COLUMN traffic_metrics.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.created_at IS '创建时间';


--
-- Name: COLUMN traffic_metrics.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_metrics.updated_at IS '更新时间';


--
-- Name: traffic_metrics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.traffic_metrics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: traffic_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.traffic_metrics_id_seq OWNED BY public.traffic_metrics.id;


--
-- Name: traffic_sync_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.traffic_sync_runs (
    id integer NOT NULL,
    platform_account_id integer NOT NULL,
    platform character varying(40) NOT NULL,
    account_id character varying(120) NOT NULL,
    shop_name character varying(160) NOT NULL,
    status character varying(30) NOT NULL,
    date_from date NOT NULL,
    date_to date NOT NULL,
    rows_written integer NOT NULL,
    error_message text NOT NULL,
    triggered_by character varying(80) NOT NULL,
    started_at timestamp without time zone,
    finished_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE traffic_sync_runs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.traffic_sync_runs IS '流量分析平台采集运行记录';


--
-- Name: COLUMN traffic_sync_runs.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.id IS '主键ID';


--
-- Name: COLUMN traffic_sync_runs.platform_account_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.platform_account_id IS '平台店铺ID';


--
-- Name: COLUMN traffic_sync_runs.platform; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.platform IS '平台代码';


--
-- Name: COLUMN traffic_sync_runs.account_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.account_id IS '平台账号标识';


--
-- Name: COLUMN traffic_sync_runs.shop_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.shop_name IS '店铺名称快照';


--
-- Name: COLUMN traffic_sync_runs.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.status IS 'pending/running/success/partial_success/failed/timed_out';


--
-- Name: COLUMN traffic_sync_runs.date_from; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.date_from IS '当前分析周期开始';


--
-- Name: COLUMN traffic_sync_runs.date_to; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.date_to IS '当前分析周期结束';


--
-- Name: COLUMN traffic_sync_runs.rows_written; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.rows_written IS '写入明细数量';


--
-- Name: COLUMN traffic_sync_runs.error_message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.error_message IS '错误信息';


--
-- Name: COLUMN traffic_sync_runs.triggered_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.triggered_by IS '触发用户';


--
-- Name: COLUMN traffic_sync_runs.started_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.started_at IS '开始时间';


--
-- Name: COLUMN traffic_sync_runs.finished_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.finished_at IS '结束时间';


--
-- Name: COLUMN traffic_sync_runs.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.traffic_sync_runs.created_at IS '创建时间';


--
-- Name: traffic_sync_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.traffic_sync_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: traffic_sync_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.traffic_sync_runs_id_seq OWNED BY public.traffic_sync_runs.id;


--
-- Name: translation_provider_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.translation_provider_settings (
    id integer NOT NULL,
    provider character varying(40) NOT NULL,
    provider_name character varying(80) NOT NULL,
    enabled boolean NOT NULL,
    app_id character varying(160) NOT NULL,
    encrypted_secret_key bytea,
    endpoint text NOT NULL,
    source_language character varying(20) NOT NULL,
    timeout_seconds integer NOT NULL,
    max_retries integer NOT NULL,
    batch_size integer NOT NULL,
    batch_chars integer NOT NULL,
    provider_options_json text NOT NULL,
    last_test_at timestamp without time zone,
    last_test_status character varying(40) NOT NULL,
    last_test_message text NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE translation_provider_settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.translation_provider_settings IS '翻译服务配置';


--
-- Name: COLUMN translation_provider_settings.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.id IS '主键ID';


--
-- Name: COLUMN translation_provider_settings.provider; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.provider IS '翻译服务商';


--
-- Name: COLUMN translation_provider_settings.provider_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.provider_name IS '翻译服务商名称';


--
-- Name: COLUMN translation_provider_settings.enabled; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.enabled IS '是否启用';


--
-- Name: COLUMN translation_provider_settings.app_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.app_id IS '服务商应用ID';


--
-- Name: COLUMN translation_provider_settings.encrypted_secret_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.encrypted_secret_key IS '加密后的服务商密钥';


--
-- Name: COLUMN translation_provider_settings.endpoint; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.endpoint IS '翻译接口地址';


--
-- Name: COLUMN translation_provider_settings.source_language; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.source_language IS '默认源语言';


--
-- Name: COLUMN translation_provider_settings.timeout_seconds; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.timeout_seconds IS '请求超时时间（秒）';


--
-- Name: COLUMN translation_provider_settings.max_retries; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.max_retries IS '失败重试次数';


--
-- Name: COLUMN translation_provider_settings.batch_size; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.batch_size IS '单批文本数量';


--
-- Name: COLUMN translation_provider_settings.batch_chars; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.batch_chars IS '单批字符数';


--
-- Name: COLUMN translation_provider_settings.provider_options_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.provider_options_json IS '服务商扩展配置 JSON';


--
-- Name: COLUMN translation_provider_settings.last_test_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.last_test_at IS '最近测试时间';


--
-- Name: COLUMN translation_provider_settings.last_test_status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.last_test_status IS '最近测试状态';


--
-- Name: COLUMN translation_provider_settings.last_test_message; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.last_test_message IS '最近测试消息';


--
-- Name: COLUMN translation_provider_settings.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.created_at IS '创建时间';


--
-- Name: COLUMN translation_provider_settings.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.translation_provider_settings.updated_at IS '更新时间';


--
-- Name: translation_provider_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.translation_provider_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: translation_provider_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.translation_provider_settings_id_seq OWNED BY public.translation_provider_settings.id;


--
-- Name: user_menu_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_menu_permissions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    menu_code character varying(80) NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: user_menu_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_menu_permissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_menu_permissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_menu_permissions_id_seq OWNED BY public.user_menu_permissions.id;


--
-- Name: user_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_roles (
    id integer NOT NULL,
    user_id integer NOT NULL,
    role_id integer NOT NULL,
    created_at timestamp without time zone DEFAULT timezone('UTC'::text, now()) NOT NULL
);


--
-- Name: TABLE user_roles; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.user_roles IS '用户角色关联表';


--
-- Name: COLUMN user_roles.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_roles.id IS '主键ID';


--
-- Name: COLUMN user_roles.user_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_roles.user_id IS '用户ID';


--
-- Name: COLUMN user_roles.role_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_roles.role_id IS '角色ID';


--
-- Name: COLUMN user_roles.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_roles.created_at IS '创建时间';


--
-- Name: user_roles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_roles_id_seq OWNED BY public.user_roles.id;


--
-- Name: user_table_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_table_preferences (
    id integer NOT NULL,
    user_id integer NOT NULL,
    table_key character varying(160) NOT NULL,
    config_json jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE user_table_preferences; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.user_table_preferences IS '用户表格个性化配置';


--
-- Name: COLUMN user_table_preferences.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_table_preferences.id IS '主键ID';


--
-- Name: COLUMN user_table_preferences.user_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_table_preferences.user_id IS '用户ID';


--
-- Name: COLUMN user_table_preferences.table_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_table_preferences.table_key IS '表格唯一标识';


--
-- Name: COLUMN user_table_preferences.config_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_table_preferences.config_json IS '用户表格配置JSON';


--
-- Name: COLUMN user_table_preferences.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_table_preferences.created_at IS '创建时间';


--
-- Name: COLUMN user_table_preferences.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.user_table_preferences.updated_at IS '更新时间';


--
-- Name: user_table_preferences_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_table_preferences_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_table_preferences_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_table_preferences_id_seq OWNED BY public.user_table_preferences.id;


--
-- Name: wecom_robot_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wecom_robot_settings (
    id integer NOT NULL,
    encrypted_webhook_url bytea,
    timeout_seconds integer NOT NULL,
    max_retries integer NOT NULL,
    rate_limit_per_minute integer NOT NULL,
    default_mentioned_user_ids text NOT NULL,
    default_mentioned_list text NOT NULL,
    default_mentioned_mobile_list text NOT NULL,
    default_prompt text NOT NULL,
    purchase_order_notify_enabled boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: TABLE wecom_robot_settings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.wecom_robot_settings IS '企业微信群机器人配置';


--
-- Name: COLUMN wecom_robot_settings.id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.id IS '主键ID';


--
-- Name: COLUMN wecom_robot_settings.encrypted_webhook_url; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.encrypted_webhook_url IS '加密后的 webhook URL';


--
-- Name: COLUMN wecom_robot_settings.timeout_seconds; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.timeout_seconds IS '请求超时时间（秒）';


--
-- Name: COLUMN wecom_robot_settings.max_retries; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.max_retries IS '失败重试次数';


--
-- Name: COLUMN wecom_robot_settings.rate_limit_per_minute; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.rate_limit_per_minute IS '每分钟发送上限';


--
-- Name: COLUMN wecom_robot_settings.default_mentioned_user_ids; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.default_mentioned_user_ids IS '默认提醒用户ID列表 JSON';


--
-- Name: COLUMN wecom_robot_settings.default_mentioned_list; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.default_mentioned_list IS '默认提醒成员列表 JSON';


--
-- Name: COLUMN wecom_robot_settings.default_mentioned_mobile_list; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.default_mentioned_mobile_list IS '默认提醒手机号列表 JSON';


--
-- Name: COLUMN wecom_robot_settings.default_prompt; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.default_prompt IS '默认提示语';


--
-- Name: COLUMN wecom_robot_settings.purchase_order_notify_enabled; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.purchase_order_notify_enabled IS '采购单生成后是否发送群通知';


--
-- Name: COLUMN wecom_robot_settings.created_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.created_at IS '创建时间';


--
-- Name: COLUMN wecom_robot_settings.updated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.wecom_robot_settings.updated_at IS '更新时间';


--
-- Name: wecom_robot_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.wecom_robot_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wecom_robot_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.wecom_robot_settings_id_seq OWNED BY public.wecom_robot_settings.id;


--
-- Name: api_request_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_request_logs ALTER COLUMN id SET DEFAULT nextval('public.api_request_logs_id_seq'::regclass);


--
-- Name: dashboard_platform_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboard_platform_settings ALTER COLUMN id SET DEFAULT nextval('public.dashboard_platform_settings_id_seq'::regclass);


--
-- Name: email_smtp_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_smtp_settings ALTER COLUMN id SET DEFAULT nextval('public.email_smtp_settings_id_seq'::regclass);


--
-- Name: exchange_rate_currency_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exchange_rate_currency_settings ALTER COLUMN id SET DEFAULT nextval('public.exchange_rate_currency_settings_id_seq'::regclass);


--
-- Name: exchange_rates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exchange_rates ALTER COLUMN id SET DEFAULT nextval('public.exchange_rates_id_seq'::regclass);


--
-- Name: label_files id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.label_files ALTER COLUMN id SET DEFAULT nextval('public.label_files_id_seq'::regclass);


--
-- Name: local_users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users ALTER COLUMN id SET DEFAULT nextval('public.local_users_id_seq'::regclass);


--
-- Name: logistics_authorizations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logistics_authorizations ALTER COLUMN id SET DEFAULT nextval('public.logistics_authorizations_id_seq'::regclass);


--
-- Name: logistics_match_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logistics_match_rules ALTER COLUMN id SET DEFAULT nextval('public.logistics_match_rules_id_seq'::regclass);


--
-- Name: logistics_order_submissions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logistics_order_submissions ALTER COLUMN id SET DEFAULT nextval('public.logistics_order_submissions_id_seq'::regclass);


--
-- Name: model_endpoints id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_endpoints ALTER COLUMN id SET DEFAULT nextval('public.model_endpoints_id_seq'::regclass);


--
-- Name: model_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_settings ALTER COLUMN id SET DEFAULT nextval('public.model_settings_id_seq'::regclass);


--
-- Name: oauth_authorization_sessions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_authorization_sessions ALTER COLUMN id SET DEFAULT nextval('public.oauth_authorization_sessions_id_seq'::regclass);


--
-- Name: order_follow_up_export_artifacts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_artifacts ALTER COLUMN id SET DEFAULT nextval('public.order_follow_up_export_artifacts_id_seq'::regclass);


--
-- Name: order_follow_up_export_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_items ALTER COLUMN id SET DEFAULT nextval('public.order_follow_up_export_items_id_seq'::regclass);


--
-- Name: order_follow_up_export_jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_jobs ALTER COLUMN id SET DEFAULT nextval('public.order_follow_up_export_jobs_id_seq'::regclass);


--
-- Name: order_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_items ALTER COLUMN id SET DEFAULT nextval('public.order_items_id_seq'::regclass);


--
-- Name: order_operation_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_operation_logs ALTER COLUMN id SET DEFAULT nextval('public.order_operation_logs_id_seq'::regclass);


--
-- Name: order_risk_handlings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_risk_handlings ALTER COLUMN id SET DEFAULT nextval('public.order_risk_handlings_id_seq'::regclass);


--
-- Name: orders id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders ALTER COLUMN id SET DEFAULT nextval('public.orders_id_seq'::regclass);


--
-- Name: outbound_scan_records id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.outbound_scan_records ALTER COLUMN id SET DEFAULT nextval('public.outbound_scan_records_id_seq'::regclass);


--
-- Name: platform_accounts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_accounts ALTER COLUMN id SET DEFAULT nextval('public.platform_accounts_id_seq'::regclass);


--
-- Name: platform_print_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_print_settings ALTER COLUMN id SET DEFAULT nextval('public.platform_print_settings_id_seq'::regclass);


--
-- Name: platform_product_catalog_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_product_catalog_items ALTER COLUMN id SET DEFAULT nextval('public.platform_product_catalog_items_id_seq'::regclass);


--
-- Name: platform_product_pricing_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_product_pricing_rules ALTER COLUMN id SET DEFAULT nextval('public.platform_product_pricing_rules_id_seq'::regclass);


--
-- Name: platform_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_settings ALTER COLUMN id SET DEFAULT nextval('public.platform_settings_id_seq'::regclass);


--
-- Name: product_inventory id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_inventory ALTER COLUMN id SET DEFAULT nextval('public.product_inventory_id_seq'::regclass);


--
-- Name: product_shop_mappings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_shop_mappings ALTER COLUMN id SET DEFAULT nextval('public.product_shop_mappings_id_seq'::regclass);


--
-- Name: products id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products ALTER COLUMN id SET DEFAULT nextval('public.products_id_seq'::regclass);


--
-- Name: purchase_order_edit_locks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_edit_locks ALTER COLUMN id SET DEFAULT nextval('public.purchase_order_edit_locks_id_seq'::regclass);


--
-- Name: purchase_order_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items ALTER COLUMN id SET DEFAULT nextval('public.purchase_order_items_id_seq'::regclass);


--
-- Name: purchase_order_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_logs ALTER COLUMN id SET DEFAULT nextval('public.purchase_order_logs_id_seq'::regclass);


--
-- Name: purchase_order_sources id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_sources ALTER COLUMN id SET DEFAULT nextval('public.purchase_order_sources_id_seq'::regclass);


--
-- Name: purchase_orders id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_orders ALTER COLUMN id SET DEFAULT nextval('public.purchase_orders_id_seq'::regclass);


--
-- Name: role_menu_permissions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_menu_permissions ALTER COLUMN id SET DEFAULT nextval('public.role_menu_permissions_id_seq'::regclass);


--
-- Name: roles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles ALTER COLUMN id SET DEFAULT nextval('public.roles_id_seq'::regclass);


--
-- Name: scheduled_task_run_orders id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_task_run_orders ALTER COLUMN id SET DEFAULT nextval('public.scheduled_task_run_orders_id_seq'::regclass);


--
-- Name: scheduled_task_run_steps id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_task_run_steps ALTER COLUMN id SET DEFAULT nextval('public.scheduled_task_run_steps_id_seq'::regclass);


--
-- Name: scheduled_task_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_task_runs ALTER COLUMN id SET DEFAULT nextval('public.scheduled_task_runs_id_seq'::regclass);


--
-- Name: scheduled_tasks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_tasks ALTER COLUMN id SET DEFAULT nextval('public.scheduled_tasks_id_seq'::regclass);


--
-- Name: scheduler_heartbeats id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduler_heartbeats ALTER COLUMN id SET DEFAULT nextval('public.scheduler_heartbeats_id_seq'::regclass);


--
-- Name: shipments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipments ALTER COLUMN id SET DEFAULT nextval('public.shipments_id_seq'::regclass);


--
-- Name: shipping_deadline_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipping_deadline_settings ALTER COLUMN id SET DEFAULT nextval('public.shipping_deadline_settings_id_seq'::regclass);


--
-- Name: sync_account_states id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_account_states ALTER COLUMN id SET DEFAULT nextval('public.sync_account_states_id_seq'::regclass);


--
-- Name: sync_audit_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_audit_logs ALTER COLUMN id SET DEFAULT nextval('public.sync_audit_logs_id_seq'::regclass);


--
-- Name: sync_cursors id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_cursors ALTER COLUMN id SET DEFAULT nextval('public.sync_cursors_id_seq'::regclass);


--
-- Name: sync_job_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_job_logs ALTER COLUMN id SET DEFAULT nextval('public.sync_job_logs_id_seq'::regclass);


--
-- Name: sync_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_settings ALTER COLUMN id SET DEFAULT nextval('public.sync_settings_id_seq'::regclass);


--
-- Name: traffic_metrics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traffic_metrics ALTER COLUMN id SET DEFAULT nextval('public.traffic_metrics_id_seq'::regclass);


--
-- Name: traffic_sync_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traffic_sync_runs ALTER COLUMN id SET DEFAULT nextval('public.traffic_sync_runs_id_seq'::regclass);


--
-- Name: translation_provider_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.translation_provider_settings ALTER COLUMN id SET DEFAULT nextval('public.translation_provider_settings_id_seq'::regclass);


--
-- Name: user_menu_permissions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_menu_permissions ALTER COLUMN id SET DEFAULT nextval('public.user_menu_permissions_id_seq'::regclass);


--
-- Name: user_roles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles ALTER COLUMN id SET DEFAULT nextval('public.user_roles_id_seq'::regclass);


--
-- Name: user_table_preferences id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_table_preferences ALTER COLUMN id SET DEFAULT nextval('public.user_table_preferences_id_seq'::regclass);


--
-- Name: wecom_robot_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wecom_robot_settings ALTER COLUMN id SET DEFAULT nextval('public.wecom_robot_settings_id_seq'::regclass);


--
-- Name: api_request_logs api_request_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_request_logs
    ADD CONSTRAINT api_request_logs_pkey PRIMARY KEY (id);


--
-- Name: dashboard_platform_settings dashboard_platform_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboard_platform_settings
    ADD CONSTRAINT dashboard_platform_settings_pkey PRIMARY KEY (id);


--
-- Name: email_smtp_settings email_smtp_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_smtp_settings
    ADD CONSTRAINT email_smtp_settings_pkey PRIMARY KEY (id);


--
-- Name: exchange_rate_currency_settings exchange_rate_currency_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exchange_rate_currency_settings
    ADD CONSTRAINT exchange_rate_currency_settings_pkey PRIMARY KEY (id);


--
-- Name: exchange_rates exchange_rates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exchange_rates
    ADD CONSTRAINT exchange_rates_pkey PRIMARY KEY (id);


--
-- Name: label_files label_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.label_files
    ADD CONSTRAINT label_files_pkey PRIMARY KEY (id);


--
-- Name: local_users local_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_pkey PRIMARY KEY (id);


--
-- Name: logistics_authorizations logistics_authorizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logistics_authorizations
    ADD CONSTRAINT logistics_authorizations_pkey PRIMARY KEY (id);


--
-- Name: logistics_match_rules logistics_match_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logistics_match_rules
    ADD CONSTRAINT logistics_match_rules_pkey PRIMARY KEY (id);


--
-- Name: logistics_order_submissions logistics_order_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logistics_order_submissions
    ADD CONSTRAINT logistics_order_submissions_pkey PRIMARY KEY (id);


--
-- Name: model_endpoints model_endpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_endpoints
    ADD CONSTRAINT model_endpoints_pkey PRIMARY KEY (id);


--
-- Name: model_settings model_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_settings
    ADD CONSTRAINT model_settings_pkey PRIMARY KEY (id);


--
-- Name: oauth_authorization_sessions oauth_authorization_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_authorization_sessions
    ADD CONSTRAINT oauth_authorization_sessions_pkey PRIMARY KEY (id);


--
-- Name: order_follow_up_export_artifacts order_follow_up_export_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_artifacts
    ADD CONSTRAINT order_follow_up_export_artifacts_pkey PRIMARY KEY (id);


--
-- Name: order_follow_up_export_items order_follow_up_export_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_items
    ADD CONSTRAINT order_follow_up_export_items_pkey PRIMARY KEY (id);


--
-- Name: order_follow_up_export_jobs order_follow_up_export_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_jobs
    ADD CONSTRAINT order_follow_up_export_jobs_pkey PRIMARY KEY (id);


--
-- Name: order_items order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_pkey PRIMARY KEY (id);


--
-- Name: order_operation_logs order_operation_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_operation_logs
    ADD CONSTRAINT order_operation_logs_pkey PRIMARY KEY (id);


--
-- Name: order_risk_handlings order_risk_handlings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_risk_handlings
    ADD CONSTRAINT order_risk_handlings_pkey PRIMARY KEY (id);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


--
-- Name: outbound_scan_records outbound_scan_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.outbound_scan_records
    ADD CONSTRAINT outbound_scan_records_pkey PRIMARY KEY (id);


--
-- Name: platform_accounts platform_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_accounts
    ADD CONSTRAINT platform_accounts_pkey PRIMARY KEY (id);


--
-- Name: platform_print_settings platform_print_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_print_settings
    ADD CONSTRAINT platform_print_settings_pkey PRIMARY KEY (id);


--
-- Name: platform_product_catalog_items platform_product_catalog_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_product_catalog_items
    ADD CONSTRAINT platform_product_catalog_items_pkey PRIMARY KEY (id);


--
-- Name: platform_product_pricing_rules platform_product_pricing_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_product_pricing_rules
    ADD CONSTRAINT platform_product_pricing_rules_pkey PRIMARY KEY (id);


--
-- Name: platform_settings platform_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_settings
    ADD CONSTRAINT platform_settings_pkey PRIMARY KEY (id);


--
-- Name: product_inventory product_inventory_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_inventory
    ADD CONSTRAINT product_inventory_pkey PRIMARY KEY (id);


--
-- Name: product_shop_mappings product_shop_mappings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_shop_mappings
    ADD CONSTRAINT product_shop_mappings_pkey PRIMARY KEY (id);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


--
-- Name: purchase_order_edit_locks purchase_order_edit_locks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_edit_locks
    ADD CONSTRAINT purchase_order_edit_locks_pkey PRIMARY KEY (id);


--
-- Name: purchase_order_items purchase_order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_pkey PRIMARY KEY (id);


--
-- Name: purchase_order_logs purchase_order_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_logs
    ADD CONSTRAINT purchase_order_logs_pkey PRIMARY KEY (id);


--
-- Name: purchase_order_sources purchase_order_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_sources
    ADD CONSTRAINT purchase_order_sources_pkey PRIMARY KEY (id);


--
-- Name: purchase_orders purchase_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_pkey PRIMARY KEY (id);


--
-- Name: role_menu_permissions role_menu_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_menu_permissions
    ADD CONSTRAINT role_menu_permissions_pkey PRIMARY KEY (id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: scheduled_task_run_orders scheduled_task_run_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_task_run_orders
    ADD CONSTRAINT scheduled_task_run_orders_pkey PRIMARY KEY (id);


--
-- Name: scheduled_task_run_steps scheduled_task_run_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_task_run_steps
    ADD CONSTRAINT scheduled_task_run_steps_pkey PRIMARY KEY (id);


--
-- Name: scheduled_task_runs scheduled_task_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_task_runs
    ADD CONSTRAINT scheduled_task_runs_pkey PRIMARY KEY (id);


--
-- Name: scheduled_tasks scheduled_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_tasks
    ADD CONSTRAINT scheduled_tasks_pkey PRIMARY KEY (id);


--
-- Name: scheduler_heartbeats scheduler_heartbeats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduler_heartbeats
    ADD CONSTRAINT scheduler_heartbeats_pkey PRIMARY KEY (id);


--
-- Name: shipments shipments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_pkey PRIMARY KEY (id);


--
-- Name: shipping_deadline_settings shipping_deadline_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipping_deadline_settings
    ADD CONSTRAINT shipping_deadline_settings_pkey PRIMARY KEY (id);


--
-- Name: sync_account_states sync_account_states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_account_states
    ADD CONSTRAINT sync_account_states_pkey PRIMARY KEY (id);


--
-- Name: sync_audit_logs sync_audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_audit_logs
    ADD CONSTRAINT sync_audit_logs_pkey PRIMARY KEY (id);


--
-- Name: sync_cursors sync_cursors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_cursors
    ADD CONSTRAINT sync_cursors_pkey PRIMARY KEY (id);


--
-- Name: sync_job_logs sync_job_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_job_logs
    ADD CONSTRAINT sync_job_logs_pkey PRIMARY KEY (id);


--
-- Name: sync_settings sync_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_settings
    ADD CONSTRAINT sync_settings_pkey PRIMARY KEY (id);


--
-- Name: traffic_metrics traffic_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traffic_metrics
    ADD CONSTRAINT traffic_metrics_pkey PRIMARY KEY (id);


--
-- Name: traffic_sync_runs traffic_sync_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traffic_sync_runs
    ADD CONSTRAINT traffic_sync_runs_pkey PRIMARY KEY (id);


--
-- Name: translation_provider_settings translation_provider_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.translation_provider_settings
    ADD CONSTRAINT translation_provider_settings_pkey PRIMARY KEY (id);


--
-- Name: dashboard_platform_settings uq_dashboard_platform_settings_platform; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboard_platform_settings
    ADD CONSTRAINT uq_dashboard_platform_settings_platform UNIQUE (platform);


--
-- Name: exchange_rate_currency_settings uq_exchange_rate_currency_settings_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exchange_rate_currency_settings
    ADD CONSTRAINT uq_exchange_rate_currency_settings_code UNIQUE (currency_code);


--
-- Name: exchange_rates uq_exchange_rates_date_currency; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exchange_rates
    ADD CONSTRAINT uq_exchange_rates_date_currency UNIQUE (rate_date, currency_code);


--
-- Name: platform_accounts uq_local_platform_account; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_accounts
    ADD CONSTRAINT uq_local_platform_account UNIQUE (platform, account_id);


--
-- Name: logistics_authorizations uq_logistics_authorizations_carrier_account; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logistics_authorizations
    ADD CONSTRAINT uq_logistics_authorizations_carrier_account UNIQUE (carrier_code, account_name);


--
-- Name: logistics_order_submissions uq_logistics_order_submissions_customer_order; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logistics_order_submissions
    ADD CONSTRAINT uq_logistics_order_submissions_customer_order UNIQUE (tenant_id, carrier_code, customer_order_no);


--
-- Name: model_endpoints uq_model_endpoints_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_endpoints
    ADD CONSTRAINT uq_model_endpoints_name UNIQUE (name);


--
-- Name: model_settings uq_model_settings_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_settings
    ADD CONSTRAINT uq_model_settings_name UNIQUE (name);


--
-- Name: oauth_authorization_sessions uq_oauth_authorization_sessions_state; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_authorization_sessions
    ADD CONSTRAINT uq_oauth_authorization_sessions_state UNIQUE (state);


--
-- Name: order_follow_up_export_artifacts uq_order_follow_up_export_artifacts_job_type; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_artifacts
    ADD CONSTRAINT uq_order_follow_up_export_artifacts_job_type UNIQUE (job_id, artifact_type);


--
-- Name: order_follow_up_export_items uq_order_follow_up_export_items_job_item; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_items
    ADD CONSTRAINT uq_order_follow_up_export_items_job_item UNIQUE (job_id, order_item_id);


--
-- Name: order_follow_up_export_jobs uq_order_follow_up_export_jobs_run; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_jobs
    ADD CONSTRAINT uq_order_follow_up_export_jobs_run UNIQUE (scheduled_task_run_id);


--
-- Name: order_risk_handlings uq_order_risk_handling_order; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_risk_handlings
    ADD CONSTRAINT uq_order_risk_handling_order UNIQUE (order_id);


--
-- Name: orders uq_order_shop_posting; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT uq_order_shop_posting UNIQUE (shop_id, platform_order_id, posting_number);


--
-- Name: platform_product_catalog_items uq_platform_product_catalog_listing_warehouse; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_product_catalog_items
    ADD CONSTRAINT uq_platform_product_catalog_listing_warehouse UNIQUE (shop_id, platform_product_id, platform_sku, warehouse_code);


--
-- Name: platform_settings uq_platform_settings_platform; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_settings
    ADD CONSTRAINT uq_platform_settings_platform UNIQUE (platform);


--
-- Name: product_inventory uq_product_inventory_product_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_inventory
    ADD CONSTRAINT uq_product_inventory_product_id UNIQUE (product_id);


--
-- Name: products uq_products_internal_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT uq_products_internal_name UNIQUE (internal_name);


--
-- Name: products uq_products_product_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT uq_products_product_code UNIQUE (product_code);


--
-- Name: purchase_order_edit_locks uq_purchase_order_edit_locks_order; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_edit_locks
    ADD CONSTRAINT uq_purchase_order_edit_locks_order UNIQUE (purchase_order_id);


--
-- Name: purchase_order_sources uq_purchase_order_sources_order_item; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_sources
    ADD CONSTRAINT uq_purchase_order_sources_order_item UNIQUE (order_item_id);


--
-- Name: purchase_orders uq_purchase_orders_purchase_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT uq_purchase_orders_purchase_no UNIQUE (purchase_no);


--
-- Name: role_menu_permissions uq_role_menu_permission; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_menu_permissions
    ADD CONSTRAINT uq_role_menu_permission UNIQUE (role_id, menu_code);


--
-- Name: scheduler_heartbeats uq_scheduler_heartbeats_owner; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduler_heartbeats
    ADD CONSTRAINT uq_scheduler_heartbeats_owner UNIQUE (owner_id);


--
-- Name: shipping_deadline_settings uq_shipping_deadline_settings_platform; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipping_deadline_settings
    ADD CONSTRAINT uq_shipping_deadline_settings_platform UNIQUE (platform);


--
-- Name: product_shop_mappings uq_shop_sku_mapping; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_shop_mappings
    ADD CONSTRAINT uq_shop_sku_mapping UNIQUE (shop_id, shop_sku);


--
-- Name: sync_account_states uq_sync_account_state; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_account_states
    ADD CONSTRAINT uq_sync_account_state UNIQUE (platform, account_id, job_type);


--
-- Name: sync_cursors uq_sync_cursor; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_cursors
    ADD CONSTRAINT uq_sync_cursor UNIQUE (platform, account_id, cursor_key);


--
-- Name: sync_settings uq_sync_setting_account; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sync_settings
    ADD CONSTRAINT uq_sync_setting_account UNIQUE (platform, account_id);


--
-- Name: traffic_metrics uq_traffic_metrics_record_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traffic_metrics
    ADD CONSTRAINT uq_traffic_metrics_record_key UNIQUE (record_key);


--
-- Name: translation_provider_settings uq_translation_provider_settings_provider; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.translation_provider_settings
    ADD CONSTRAINT uq_translation_provider_settings_provider UNIQUE (provider);


--
-- Name: user_menu_permissions uq_user_menu_permission; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_menu_permissions
    ADD CONSTRAINT uq_user_menu_permission UNIQUE (user_id, menu_code);


--
-- Name: user_roles uq_user_roles_user_role; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT uq_user_roles_user_role UNIQUE (user_id, role_id);


--
-- Name: user_table_preferences uq_user_table_preferences_user_table; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_table_preferences
    ADD CONSTRAINT uq_user_table_preferences_user_table UNIQUE (user_id, table_key);


--
-- Name: user_menu_permissions user_menu_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_menu_permissions
    ADD CONSTRAINT user_menu_permissions_pkey PRIMARY KEY (id);


--
-- Name: user_roles user_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (id);


--
-- Name: user_table_preferences user_table_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_table_preferences
    ADD CONSTRAINT user_table_preferences_pkey PRIMARY KEY (id);


--
-- Name: wecom_robot_settings wecom_robot_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wecom_robot_settings
    ADD CONSTRAINT wecom_robot_settings_pkey PRIMARY KEY (id);


--
-- Name: idx_order_payment_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_order_payment_created ON public.orders USING btree (payment_at DESC, created_at DESC);


--
-- Name: idx_order_search_ids; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_order_search_ids ON public.orders USING btree (posting_number, platform_order_no, platform_order_id);


--
-- Name: idx_order_shop_payment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_order_shop_payment ON public.orders USING btree (shop_id, payment_at);


--
-- Name: idx_order_status_platform_payment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_order_status_platform_payment ON public.orders USING btree (biz_status, platform, payment_at);


--
-- Name: ix_api_request_logs_account_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_account_created ON public.api_request_logs USING btree (account_id, created_at DESC);


--
-- Name: ix_api_request_logs_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_account_id ON public.api_request_logs USING btree (account_id);


--
-- Name: ix_api_request_logs_account_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_account_trgm ON public.api_request_logs USING gin (account_id public.gin_trgm_ops);


--
-- Name: ix_api_request_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_created_at ON public.api_request_logs USING btree (created_at);


--
-- Name: ix_api_request_logs_created_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_created_id ON public.api_request_logs USING btree (created_at DESC, id DESC);


--
-- Name: ix_api_request_logs_error_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_error_trgm ON public.api_request_logs USING gin (error_message public.gin_trgm_ops);


--
-- Name: ix_api_request_logs_filters_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_filters_created ON public.api_request_logs USING btree (platform, operation, status, created_at DESC, id DESC);


--
-- Name: ix_api_request_logs_log_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_log_date ON public.api_request_logs USING btree (log_date);


--
-- Name: ix_api_request_logs_log_date_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_log_date_group ON public.api_request_logs USING btree (log_date, platform, account_id, operation);


--
-- Name: ix_api_request_logs_operation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_operation ON public.api_request_logs USING btree (operation);


--
-- Name: ix_api_request_logs_operation_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_operation_trgm ON public.api_request_logs USING gin (operation public.gin_trgm_ops);


--
-- Name: ix_api_request_logs_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_platform ON public.api_request_logs USING btree (platform);


--
-- Name: ix_api_request_logs_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_request_id ON public.api_request_logs USING btree (request_id);


--
-- Name: ix_api_request_logs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_status ON public.api_request_logs USING btree (status);


--
-- Name: ix_api_request_logs_url_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_request_logs_url_trgm ON public.api_request_logs USING gin (url public.gin_trgm_ops);


--
-- Name: ix_dashboard_platform_settings_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_dashboard_platform_settings_platform ON public.dashboard_platform_settings USING btree (platform);


--
-- Name: ix_exchange_rate_currency_settings_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_exchange_rate_currency_settings_enabled ON public.exchange_rate_currency_settings USING btree (enabled);


--
-- Name: ix_exchange_rates_currency_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_exchange_rates_currency_code ON public.exchange_rates USING btree (currency_code);


--
-- Name: ix_exchange_rates_currency_date_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_exchange_rates_currency_date_updated ON public.exchange_rates USING btree (currency_code, rate_date DESC, updated_at DESC);


--
-- Name: ix_exchange_rates_rate_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_exchange_rates_rate_date ON public.exchange_rates USING btree (rate_date);


--
-- Name: ix_exchange_rates_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_exchange_rates_updated_at ON public.exchange_rates USING btree (updated_at);


--
-- Name: ix_label_files_shipment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_label_files_shipment_id ON public.label_files USING btree (shipment_id);


--
-- Name: ix_label_files_shipment_id_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_label_files_shipment_id_id ON public.label_files USING btree (shipment_id, id DESC);


--
-- Name: ix_local_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_local_users_username ON public.local_users USING btree (username);


--
-- Name: ix_logistics_authorizations_carrier_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_authorizations_carrier_code ON public.logistics_authorizations USING btree (carrier_code);


--
-- Name: ix_logistics_authorizations_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_authorizations_enabled ON public.logistics_authorizations USING btree (enabled);


--
-- Name: ix_logistics_match_rules_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_match_rules_enabled ON public.logistics_match_rules USING btree (enabled);


--
-- Name: ix_logistics_match_rules_enabled_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_match_rules_enabled_priority ON public.logistics_match_rules USING btree (enabled, priority);


--
-- Name: ix_logistics_match_rules_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_match_rules_name ON public.logistics_match_rules USING btree (name);


--
-- Name: ix_logistics_match_rules_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_match_rules_platform ON public.logistics_match_rules USING btree (platform);


--
-- Name: ix_logistics_match_rules_platform_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_match_rules_platform_priority ON public.logistics_match_rules USING btree (platform, enabled, priority);


--
-- Name: ix_logistics_match_rules_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_match_rules_priority ON public.logistics_match_rules USING btree (priority);


--
-- Name: ix_logistics_order_submissions_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_order_submissions_account_id ON public.logistics_order_submissions USING btree (account_id);


--
-- Name: ix_logistics_order_submissions_carrier_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_order_submissions_carrier_code ON public.logistics_order_submissions USING btree (carrier_code);


--
-- Name: ix_logistics_order_submissions_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_order_submissions_platform ON public.logistics_order_submissions USING btree (platform);


--
-- Name: ix_logistics_order_submissions_provider_order_no; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_order_submissions_provider_order_no ON public.logistics_order_submissions USING btree (provider_order_no);


--
-- Name: ix_logistics_order_submissions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_order_submissions_status ON public.logistics_order_submissions USING btree (status);


--
-- Name: ix_logistics_order_submissions_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_order_submissions_tenant_id ON public.logistics_order_submissions USING btree (tenant_id);


--
-- Name: ix_logistics_order_submissions_transaction; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_order_submissions_transaction ON public.logistics_order_submissions USING btree (platform, account_id, transaction_id);


--
-- Name: ix_logistics_order_submissions_transaction_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_logistics_order_submissions_transaction_id ON public.logistics_order_submissions USING btree (transaction_id);


--
-- Name: ix_model_endpoints_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_endpoints_enabled ON public.model_endpoints USING btree (enabled);


--
-- Name: ix_model_endpoints_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_endpoints_name ON public.model_endpoints USING btree (name);


--
-- Name: ix_model_settings_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_settings_enabled ON public.model_settings USING btree (enabled);


--
-- Name: ix_model_settings_endpoint_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_settings_endpoint_id ON public.model_settings USING btree (endpoint_id);


--
-- Name: ix_model_settings_is_default; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_settings_is_default ON public.model_settings USING btree (is_default);


--
-- Name: ix_model_settings_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_settings_name ON public.model_settings USING btree (name);


--
-- Name: ix_oauth_authorization_sessions_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_authorization_sessions_account ON public.oauth_authorization_sessions USING btree (platform, account_id);


--
-- Name: ix_oauth_authorization_sessions_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_authorization_sessions_account_id ON public.oauth_authorization_sessions USING btree (account_id);


--
-- Name: ix_oauth_authorization_sessions_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_authorization_sessions_platform ON public.oauth_authorization_sessions USING btree (platform);


--
-- Name: ix_oauth_authorization_sessions_platform_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_authorization_sessions_platform_account_id ON public.oauth_authorization_sessions USING btree (platform_account_id);


--
-- Name: ix_oauth_authorization_sessions_state; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_oauth_authorization_sessions_state ON public.oauth_authorization_sessions USING btree (state);


--
-- Name: ix_oauth_authorization_sessions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_authorization_sessions_status ON public.oauth_authorization_sessions USING btree (status);


--
-- Name: ix_order_follow_up_export_artifacts_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_artifacts_job_id ON public.order_follow_up_export_artifacts USING btree (job_id);


--
-- Name: ix_order_follow_up_export_artifacts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_artifacts_status ON public.order_follow_up_export_artifacts USING btree (status);


--
-- Name: ix_order_follow_up_export_artifacts_status_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_artifacts_status_id ON public.order_follow_up_export_artifacts USING btree (status, id);


--
-- Name: ix_order_follow_up_export_items_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_items_job_id ON public.order_follow_up_export_items USING btree (job_id);


--
-- Name: ix_order_follow_up_export_items_mapping_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_items_mapping_status ON public.order_follow_up_export_items USING btree (mapping_status);


--
-- Name: ix_order_follow_up_export_items_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_items_order_id ON public.order_follow_up_export_items USING btree (order_id);


--
-- Name: ix_order_follow_up_export_items_order_item; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_items_order_item ON public.order_follow_up_export_items USING btree (order_item_id, status, id);


--
-- Name: ix_order_follow_up_export_items_order_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_items_order_item_id ON public.order_follow_up_export_items USING btree (order_item_id);


--
-- Name: ix_order_follow_up_export_items_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_items_status ON public.order_follow_up_export_items USING btree (status);


--
-- Name: ix_order_follow_up_export_jobs_lease_until; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_jobs_lease_until ON public.order_follow_up_export_jobs USING btree (lease_until);


--
-- Name: ix_order_follow_up_export_jobs_next_retry_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_jobs_next_retry_at ON public.order_follow_up_export_jobs USING btree (next_retry_at);


--
-- Name: ix_order_follow_up_export_jobs_scheduled_task_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_jobs_scheduled_task_run_id ON public.order_follow_up_export_jobs USING btree (scheduled_task_run_id);


--
-- Name: ix_order_follow_up_export_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_jobs_status ON public.order_follow_up_export_jobs USING btree (status);


--
-- Name: ix_order_follow_up_export_jobs_status_retry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_jobs_status_retry ON public.order_follow_up_export_jobs USING btree (status, next_retry_at, id);


--
-- Name: ix_order_follow_up_export_jobs_workbook_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_follow_up_export_jobs_workbook_key ON public.order_follow_up_export_jobs USING btree (workbook_key);


--
-- Name: ix_order_items_order_currency_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_items_order_currency_id ON public.order_items USING btree (order_id, id, currency);


--
-- Name: ix_order_items_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_items_order_id ON public.order_items USING btree (order_id);


--
-- Name: ix_order_items_order_id_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_items_order_id_id ON public.order_items USING btree (order_id, id);


--
-- Name: ix_order_items_order_quantity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_items_order_quantity ON public.order_items USING btree (order_id, quantity);


--
-- Name: ix_order_items_order_sku; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_items_order_sku ON public.order_items USING btree (order_id, sku);


--
-- Name: ix_order_items_platform_product_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_items_platform_product_name_trgm ON public.order_items USING gin (platform_product_name public.gin_trgm_ops);


--
-- Name: ix_order_items_sku; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_items_sku ON public.order_items USING btree (sku);


--
-- Name: ix_order_items_sku_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_items_sku_trgm ON public.order_items USING gin (sku public.gin_trgm_ops);


--
-- Name: ix_order_operation_logs_event_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_operation_logs_event_key ON public.order_operation_logs USING btree (event_key);


--
-- Name: ix_order_operation_logs_operated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_operation_logs_operated_at ON public.order_operation_logs USING btree (operated_at);


--
-- Name: ix_order_operation_logs_operation_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_operation_logs_operation_type ON public.order_operation_logs USING btree (operation_type);


--
-- Name: ix_order_operation_logs_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_operation_logs_order_id ON public.order_operation_logs USING btree (order_id);


--
-- Name: ix_order_risk_handlings_handled_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_risk_handlings_handled_at ON public.order_risk_handlings USING btree (handled_at);


--
-- Name: ix_order_risk_handlings_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_risk_handlings_order_id ON public.order_risk_handlings USING btree (order_id);


--
-- Name: ix_orders_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_account_id ON public.orders USING btree (account_id);


--
-- Name: ix_orders_biz_deadline; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_biz_deadline ON public.orders USING btree (biz_status, dispatch_deadline_at, shipping_deadline_at);


--
-- Name: ix_orders_biz_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_biz_status ON public.orders USING btree (biz_status);


--
-- Name: ix_orders_bsi_order_no; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_bsi_order_no ON public.orders USING btree (bsi_order_no);


--
-- Name: ix_orders_customer_history; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_customer_history ON public.orders USING btree (shop_id, buyer_id, platform_created_at, id) WHERE ((buyer_id IS NOT NULL) AND ((buyer_id)::text <> ''::text));


--
-- Name: ix_orders_dispatch_deadline_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_dispatch_deadline_at ON public.orders USING btree (dispatch_deadline_at);


--
-- Name: ix_orders_fulfillment_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_fulfillment_type ON public.orders USING btree (fulfillment_type);


--
-- Name: ix_orders_is_overseas_warehouse; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_is_overseas_warehouse ON public.orders USING btree (is_overseas_warehouse);


--
-- Name: ix_orders_local_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_local_status ON public.orders USING btree (local_status);


--
-- Name: ix_orders_logistics_last_synced_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_logistics_last_synced_at ON public.orders USING btree (logistics_last_synced_at);


--
-- Name: ix_orders_logistics_match_rule_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_logistics_match_rule_id ON public.orders USING btree (logistics_match_rule_id);


--
-- Name: ix_orders_logistics_match_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_logistics_match_status ON public.orders USING btree (logistics_match_status);


--
-- Name: ix_orders_payment_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_payment_at ON public.orders USING btree (payment_at);


--
-- Name: ix_orders_payment_at_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_payment_at_id ON public.orders USING btree (payment_at, id);


--
-- Name: ix_orders_payment_month_shop; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_payment_month_shop ON public.orders USING btree (payment_at, platform, shop_id, shop_name);


--
-- Name: ix_orders_payment_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_payment_page ON public.orders USING btree (payment_at DESC, created_at DESC, updated_at DESC, id DESC);


--
-- Name: ix_orders_pending_payment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_pending_payment ON public.orders USING btree (biz_status, payment_at) WHERE ((biz_status)::text = ANY ((ARRAY['待处理'::character varying, '配货中'::character varying])::text[]));


--
-- Name: ix_orders_picking_payment_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_picking_payment_page ON public.orders USING btree (picking_at, payment_at DESC, created_at DESC, updated_at DESC, id DESC) WHERE (picking_at IS NOT NULL);


--
-- Name: ix_orders_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_platform ON public.orders USING btree (platform);


--
-- Name: ix_orders_platform_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_platform_order_id ON public.orders USING btree (platform_order_id);


--
-- Name: ix_orders_platform_order_id_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_platform_order_id_trgm ON public.orders USING gin (platform_order_id public.gin_trgm_ops);


--
-- Name: ix_orders_platform_order_no; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_platform_order_no ON public.orders USING btree (platform_order_no);


--
-- Name: ix_orders_platform_order_no_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_platform_order_no_trgm ON public.orders USING gin (platform_order_no public.gin_trgm_ops);


--
-- Name: ix_orders_platform_payment_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_platform_payment_page ON public.orders USING btree (platform, payment_at DESC, created_at DESC, updated_at DESC, id DESC);


--
-- Name: ix_orders_posting_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_posting_number ON public.orders USING btree (posting_number);


--
-- Name: ix_orders_posting_number_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_posting_number_trgm ON public.orders USING gin (posting_number public.gin_trgm_ops);


--
-- Name: ix_orders_shipment_tracking_number_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_shipment_tracking_number_trgm ON public.orders USING gin (shipment_tracking_number public.gin_trgm_ops);


--
-- Name: ix_orders_shipping_deadline_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_shipping_deadline_at ON public.orders USING btree (shipping_deadline_at);


--
-- Name: ix_orders_shop_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_shop_id ON public.orders USING btree (shop_id);


--
-- Name: ix_orders_status_payment_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_status_payment_page ON public.orders USING btree (biz_status, payment_at DESC, created_at DESC, updated_at DESC, id DESC);


--
-- Name: ix_orders_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_tenant_id ON public.orders USING btree (tenant_id);


--
-- Name: ix_orders_traffic_account_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_traffic_account_created ON public.orders USING btree (platform, account_id, platform_created_at) WHERE (payment_at IS NULL);


--
-- Name: ix_orders_traffic_account_payment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_traffic_account_payment ON public.orders USING btree (platform, account_id, payment_at) WHERE (payment_at IS NOT NULL);


--
-- Name: ix_outbound_scan_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_order_id ON public.outbound_scan_records USING btree (order_id);


--
-- Name: ix_outbound_scan_platform_order_no_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_platform_order_no_trgm ON public.outbound_scan_records USING gin (platform_order_no public.gin_trgm_ops);


--
-- Name: ix_outbound_scan_platform_scanned; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_platform_scanned ON public.outbound_scan_records USING btree (platform, scanned_at DESC, id DESC);


--
-- Name: ix_outbound_scan_posting_number_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_posting_number_trgm ON public.outbound_scan_records USING gin (posting_number public.gin_trgm_ops);


--
-- Name: ix_outbound_scan_records_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_records_order_id ON public.outbound_scan_records USING btree (order_id);


--
-- Name: ix_outbound_scan_records_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_records_result ON public.outbound_scan_records USING btree (result);


--
-- Name: ix_outbound_scan_records_scanned_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_records_scanned_at ON public.outbound_scan_records USING btree (scanned_at);


--
-- Name: ix_outbound_scan_records_tracking_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_records_tracking_number ON public.outbound_scan_records USING btree (tracking_number);


--
-- Name: ix_outbound_scan_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_result ON public.outbound_scan_records USING btree (result);


--
-- Name: ix_outbound_scan_result_scanned; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_result_scanned ON public.outbound_scan_records USING btree (result, scanned_at DESC, id DESC);


--
-- Name: ix_outbound_scan_scanned_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_scanned_at ON public.outbound_scan_records USING btree (scanned_at);


--
-- Name: ix_outbound_scan_scanned_by_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_scanned_by_trgm ON public.outbound_scan_records USING gin (scanned_by public.gin_trgm_ops);


--
-- Name: ix_outbound_scan_scanned_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_scanned_page ON public.outbound_scan_records USING btree (scanned_at DESC, id DESC);


--
-- Name: ix_outbound_scan_shop_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_shop_name_trgm ON public.outbound_scan_records USING gin (shop_name public.gin_trgm_ops);


--
-- Name: ix_outbound_scan_success_order_scanned; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_success_order_scanned ON public.outbound_scan_records USING btree (order_id, scanned_at) WHERE ((result)::text = 'success'::text);


--
-- Name: ix_outbound_scan_tracking; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_tracking ON public.outbound_scan_records USING btree (tracking_number);


--
-- Name: ix_outbound_scan_tracking_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbound_scan_tracking_trgm ON public.outbound_scan_records USING gin (tracking_number public.gin_trgm_ops);


--
-- Name: ix_platform_accounts_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_accounts_account_id ON public.platform_accounts USING btree (account_id);


--
-- Name: ix_platform_accounts_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_accounts_platform ON public.platform_accounts USING btree (platform);


--
-- Name: ix_platform_accounts_platform_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_accounts_platform_account ON public.platform_accounts USING btree (platform, account_id);


--
-- Name: ix_platform_print_settings_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_print_settings_platform ON public.platform_print_settings USING btree (platform);


--
-- Name: ix_platform_product_catalog_calculation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_calculation ON public.platform_product_catalog_items USING btree (calculation_status);


--
-- Name: ix_platform_product_catalog_items_calculation_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_items_calculation_status ON public.platform_product_catalog_items USING btree (calculation_status);


--
-- Name: ix_platform_product_catalog_items_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_items_is_active ON public.platform_product_catalog_items USING btree (is_active);


--
-- Name: ix_platform_product_catalog_items_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_items_platform ON public.platform_product_catalog_items USING btree (platform);


--
-- Name: ix_platform_product_catalog_items_platform_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_items_platform_product_id ON public.platform_product_catalog_items USING btree (platform_product_id);


--
-- Name: ix_platform_product_catalog_items_platform_sku; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_items_platform_sku ON public.platform_product_catalog_items USING btree (platform_sku);


--
-- Name: ix_platform_product_catalog_items_pricing_rule_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_items_pricing_rule_id ON public.platform_product_catalog_items USING btree (pricing_rule_id);


--
-- Name: ix_platform_product_catalog_items_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_items_product_id ON public.platform_product_catalog_items USING btree (product_id);


--
-- Name: ix_platform_product_catalog_items_shop_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_items_shop_id ON public.platform_product_catalog_items USING btree (shop_id);


--
-- Name: ix_platform_product_catalog_platform_shop; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_platform_shop ON public.platform_product_catalog_items USING btree (platform, shop_id);


--
-- Name: ix_platform_product_catalog_product; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_product ON public.platform_product_catalog_items USING btree (product_id);


--
-- Name: ix_platform_product_catalog_sync; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_catalog_sync ON public.platform_product_catalog_items USING btree (last_synced_at);


--
-- Name: ix_platform_product_pricing_rules_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_pricing_rules_enabled ON public.platform_product_pricing_rules USING btree (enabled);


--
-- Name: ix_platform_product_pricing_rules_match; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_pricing_rules_match ON public.platform_product_pricing_rules USING btree (platform, shop_id, enabled, priority);


--
-- Name: ix_platform_product_pricing_rules_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_pricing_rules_name ON public.platform_product_pricing_rules USING btree (name);


--
-- Name: ix_platform_product_pricing_rules_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_pricing_rules_platform ON public.platform_product_pricing_rules USING btree (platform);


--
-- Name: ix_platform_product_pricing_rules_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_pricing_rules_priority ON public.platform_product_pricing_rules USING btree (priority);


--
-- Name: ix_platform_product_pricing_rules_product; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_pricing_rules_product ON public.platform_product_pricing_rules USING btree (product_id);


--
-- Name: ix_platform_product_pricing_rules_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_pricing_rules_product_id ON public.platform_product_pricing_rules USING btree (product_id);


--
-- Name: ix_platform_product_pricing_rules_shop_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_product_pricing_rules_shop_id ON public.platform_product_pricing_rules USING btree (shop_id);


--
-- Name: ix_platform_settings_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_settings_enabled ON public.platform_settings USING btree (enabled);


--
-- Name: ix_platform_settings_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_settings_platform ON public.platform_settings USING btree (platform);


--
-- Name: ix_product_inventory_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_product_inventory_product_id ON public.product_inventory USING btree (product_id);


--
-- Name: ix_product_inventory_product_id_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_inventory_product_id_id ON public.product_inventory USING btree (product_id, id);


--
-- Name: ix_product_inventory_product_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_inventory_product_name ON public.product_inventory USING btree (product_name);


--
-- Name: ix_product_inventory_product_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_inventory_product_name_trgm ON public.product_inventory USING gin (product_name public.gin_trgm_ops);


--
-- Name: ix_product_inventory_stock_product; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_inventory_stock_product ON public.product_inventory USING btree (stock_qty, product_id);


--
-- Name: ix_product_shop_mappings_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_shop_mappings_product_id ON public.product_shop_mappings USING btree (product_id);


--
-- Name: ix_product_shop_mappings_product_shop; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_shop_mappings_product_shop ON public.product_shop_mappings USING btree (product_id, shop_id, id);


--
-- Name: ix_product_shop_mappings_shop_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_shop_mappings_shop_id ON public.product_shop_mappings USING btree (shop_id);


--
-- Name: ix_product_shop_mappings_shop_sku; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_shop_mappings_shop_sku ON public.product_shop_mappings USING btree (shop_sku);


--
-- Name: ix_product_shop_mappings_shop_sku_lower_product; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_shop_mappings_shop_sku_lower_product ON public.product_shop_mappings USING btree (shop_id, lower(TRIM(BOTH FROM shop_sku)), product_id);


--
-- Name: ix_product_shop_mappings_shop_sku_product; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_shop_mappings_shop_sku_product ON public.product_shop_mappings USING btree (shop_id, shop_sku, product_id);


--
-- Name: ix_products_buyer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_buyer_user_id ON public.products USING btree (buyer_user_id);


--
-- Name: ix_products_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_enabled ON public.products USING btree (enabled);


--
-- Name: ix_products_enabled_updated_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_enabled_updated_id ON public.products USING btree (enabled, updated_at DESC, id DESC);


--
-- Name: ix_products_internal_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_products_internal_name ON public.products USING btree (internal_name);


--
-- Name: ix_products_internal_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_internal_name_trgm ON public.products USING gin (internal_name public.gin_trgm_ops);


--
-- Name: ix_products_is_slow_moving_material; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_is_slow_moving_material ON public.products USING btree (is_slow_moving_material);


--
-- Name: ix_products_product_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_products_product_code ON public.products USING btree (product_code);


--
-- Name: ix_products_product_code_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_product_code_trgm ON public.products USING gin (product_code public.gin_trgm_ops);


--
-- Name: ix_products_updated_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_updated_id ON public.products USING btree (updated_at DESC, id DESC);


--
-- Name: ix_purchase_order_edit_locks_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_edit_locks_expires_at ON public.purchase_order_edit_locks USING btree (expires_at);


--
-- Name: ix_purchase_order_edit_locks_locked_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_edit_locks_locked_by ON public.purchase_order_edit_locks USING btree (locked_by);


--
-- Name: ix_purchase_order_edit_locks_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_edit_locks_order ON public.purchase_order_edit_locks USING btree (purchase_order_id);


--
-- Name: ix_purchase_order_edit_locks_purchase_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_edit_locks_purchase_order_id ON public.purchase_order_edit_locks USING btree (purchase_order_id);


--
-- Name: ix_purchase_order_items_buyer_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_items_buyer_trgm ON public.purchase_order_items USING gin (buyer public.gin_trgm_ops);


--
-- Name: ix_purchase_order_items_buyer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_items_buyer_user_id ON public.purchase_order_items USING btree (buyer_user_id);


--
-- Name: ix_purchase_order_items_order_product; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_items_order_product ON public.purchase_order_items USING btree (purchase_order_id, product_name);


--
-- Name: ix_purchase_order_items_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_items_product_id ON public.purchase_order_items USING btree (product_id);


--
-- Name: ix_purchase_order_items_product_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_items_product_name ON public.purchase_order_items USING btree (product_name);


--
-- Name: ix_purchase_order_items_product_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_items_product_name_trgm ON public.purchase_order_items USING gin (product_name public.gin_trgm_ops);


--
-- Name: ix_purchase_order_items_purchase_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_items_purchase_order_id ON public.purchase_order_items USING btree (purchase_order_id);


--
-- Name: ix_purchase_order_items_purchase_order_id_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_items_purchase_order_id_id ON public.purchase_order_items USING btree (purchase_order_id, id);


--
-- Name: ix_purchase_order_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_logs_action ON public.purchase_order_logs USING btree (action);


--
-- Name: ix_purchase_order_logs_purchase_no; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_logs_purchase_no ON public.purchase_order_logs USING btree (purchase_no);


--
-- Name: ix_purchase_order_logs_purchase_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_logs_purchase_order_id ON public.purchase_order_logs USING btree (purchase_order_id);


--
-- Name: ix_purchase_order_sources_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_sources_order_id ON public.purchase_order_sources USING btree (order_id);


--
-- Name: ix_purchase_order_sources_order_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_purchase_order_sources_order_item_id ON public.purchase_order_sources USING btree (order_item_id);


--
-- Name: ix_purchase_order_sources_order_item_purchase; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_sources_order_item_purchase ON public.purchase_order_sources USING btree (order_item_id, purchase_order_id);


--
-- Name: ix_purchase_order_sources_product_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_sources_product_name ON public.purchase_order_sources USING btree (product_name);


--
-- Name: ix_purchase_order_sources_purchase_item_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_sources_purchase_item_order ON public.purchase_order_sources USING btree (purchase_order_id, purchase_order_item_id, order_id);


--
-- Name: ix_purchase_order_sources_purchase_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_sources_purchase_order ON public.purchase_order_sources USING btree (purchase_order_id);


--
-- Name: ix_purchase_order_sources_purchase_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_sources_purchase_order_id ON public.purchase_order_sources USING btree (purchase_order_id);


--
-- Name: ix_purchase_order_sources_purchase_order_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_order_sources_purchase_order_item_id ON public.purchase_order_sources USING btree (purchase_order_item_id);


--
-- Name: ix_purchase_orders_created_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_orders_created_id ON public.purchase_orders USING btree (created_at DESC, id DESC);


--
-- Name: ix_purchase_orders_purchase_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_orders_purchase_date ON public.purchase_orders USING btree (purchase_date);


--
-- Name: ix_purchase_orders_purchase_date_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_orders_purchase_date_created ON public.purchase_orders USING btree (purchase_date, created_at DESC, id DESC);


--
-- Name: ix_purchase_orders_purchase_no; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_purchase_orders_purchase_no ON public.purchase_orders USING btree (purchase_no);


--
-- Name: ix_purchase_orders_purchase_no_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_orders_purchase_no_trgm ON public.purchase_orders USING gin (purchase_no public.gin_trgm_ops);


--
-- Name: ix_purchase_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_purchase_orders_status ON public.purchase_orders USING btree (status);


--
-- Name: ix_role_menu_permissions_menu_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_menu_permissions_menu_code ON public.role_menu_permissions USING btree (menu_code);


--
-- Name: ix_role_menu_permissions_role_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_menu_permissions_role_id ON public.role_menu_permissions USING btree (role_id);


--
-- Name: ix_roles_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_roles_code ON public.roles USING btree (code);


--
-- Name: ix_scheduled_task_run_orders_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_run_orders_order_id ON public.scheduled_task_run_orders USING btree (order_id);


--
-- Name: ix_scheduled_task_run_orders_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_run_orders_run_id ON public.scheduled_task_run_orders USING btree (run_id);


--
-- Name: ix_scheduled_task_run_orders_run_id_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_run_orders_run_id_id ON public.scheduled_task_run_orders USING btree (run_id, id);


--
-- Name: ix_scheduled_task_run_orders_run_reprint_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_run_orders_run_reprint_id ON public.scheduled_task_run_orders USING btree (run_id, needs_reprint, id);


--
-- Name: ix_scheduled_task_run_steps_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_run_steps_run_id ON public.scheduled_task_run_steps USING btree (run_id);


--
-- Name: ix_scheduled_task_run_steps_run_id_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_run_steps_run_id_id ON public.scheduled_task_run_steps USING btree (run_id, id);


--
-- Name: ix_scheduled_task_run_steps_step_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_run_steps_step_code ON public.scheduled_task_run_steps USING btree (step_code);


--
-- Name: ix_scheduled_task_runs_next_retry_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_runs_next_retry_at ON public.scheduled_task_runs USING btree (next_retry_at);


--
-- Name: ix_scheduled_task_runs_original_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_runs_original_run_id ON public.scheduled_task_runs USING btree (original_run_id);


--
-- Name: ix_scheduled_task_runs_parent_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_runs_parent_run_id ON public.scheduled_task_runs USING btree (parent_run_id);


--
-- Name: ix_scheduled_task_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_runs_status ON public.scheduled_task_runs USING btree (status);


--
-- Name: ix_scheduled_task_runs_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_runs_task_id ON public.scheduled_task_runs USING btree (scheduled_task_id);


--
-- Name: ix_scheduled_task_runs_task_id_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_task_runs_task_id_id ON public.scheduled_task_runs USING btree (scheduled_task_id, id DESC);


--
-- Name: ix_scheduled_tasks_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_tasks_enabled ON public.scheduled_tasks USING btree (enabled);


--
-- Name: ix_scheduled_tasks_task_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduled_tasks_task_type ON public.scheduled_tasks USING btree (task_type);


--
-- Name: ix_scheduler_heartbeats_last_seen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_scheduler_heartbeats_last_seen ON public.scheduler_heartbeats USING btree (last_seen_at);


--
-- Name: ix_shipments_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_shipments_order_id ON public.shipments USING btree (order_id);


--
-- Name: ix_shipments_order_id_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_shipments_order_id_id ON public.shipments USING btree (order_id, id DESC);


--
-- Name: ix_shipments_tracking_number_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_shipments_tracking_number_trgm ON public.shipments USING gin (tracking_number public.gin_trgm_ops);


--
-- Name: ix_shipping_deadline_settings_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_shipping_deadline_settings_platform ON public.shipping_deadline_settings USING btree (platform);


--
-- Name: ix_shipping_deadline_settings_sort_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_shipping_deadline_settings_sort_order ON public.shipping_deadline_settings USING btree (sort_order);


--
-- Name: ix_sync_account_states_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_account_states_account_id ON public.sync_account_states USING btree (account_id);


--
-- Name: ix_sync_account_states_last_success; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_account_states_last_success ON public.sync_account_states USING btree (last_success_at);


--
-- Name: ix_sync_account_states_next_due; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_account_states_next_due ON public.sync_account_states USING btree (next_due_at);


--
-- Name: ix_sync_account_states_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_account_states_platform ON public.sync_account_states USING btree (platform);


--
-- Name: ix_sync_account_states_platform_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_account_states_platform_account ON public.sync_account_states USING btree (platform, account_id);


--
-- Name: ix_sync_account_states_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_account_states_status ON public.sync_account_states USING btree (last_status);


--
-- Name: ix_sync_audit_logs_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_audit_logs_account ON public.sync_audit_logs USING btree (platform, account_id);


--
-- Name: ix_sync_audit_logs_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_audit_logs_account_id ON public.sync_audit_logs USING btree (account_id);


--
-- Name: ix_sync_audit_logs_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_audit_logs_created ON public.sync_audit_logs USING btree (created_at);


--
-- Name: ix_sync_audit_logs_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_audit_logs_event_type ON public.sync_audit_logs USING btree (event_type);


--
-- Name: ix_sync_audit_logs_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_audit_logs_platform ON public.sync_audit_logs USING btree (platform);


--
-- Name: ix_sync_cursors_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_cursors_account_id ON public.sync_cursors USING btree (account_id);


--
-- Name: ix_sync_cursors_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_cursors_platform ON public.sync_cursors USING btree (platform);


--
-- Name: ix_sync_job_logs_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_job_logs_account_id ON public.sync_job_logs USING btree (account_id);


--
-- Name: ix_sync_job_logs_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_job_logs_platform ON public.sync_job_logs USING btree (platform);


--
-- Name: ix_sync_settings_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_settings_account_id ON public.sync_settings USING btree (account_id);


--
-- Name: ix_sync_settings_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sync_settings_platform ON public.sync_settings USING btree (platform);


--
-- Name: ix_traffic_metrics_account_grain_stat_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_account_grain_stat_date ON public.traffic_metrics USING btree (platform_account_id, grain, stat_date);


--
-- Name: ix_traffic_metrics_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_account_id ON public.traffic_metrics USING btree (account_id);


--
-- Name: ix_traffic_metrics_account_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_account_period ON public.traffic_metrics USING btree (platform_account_id, period_start, period_end);


--
-- Name: ix_traffic_metrics_dimensions; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_dimensions ON public.traffic_metrics USING btree (platform, account_id, source, grain, region);


--
-- Name: ix_traffic_metrics_grain_period_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_grain_period_account ON public.traffic_metrics USING btree (grain, period_start, period_end, platform_account_id);


--
-- Name: ix_traffic_metrics_grain_stat_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_grain_stat_date ON public.traffic_metrics USING btree (grain, stat_date);


--
-- Name: ix_traffic_metrics_period_end; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_period_end ON public.traffic_metrics USING btree (period_end);


--
-- Name: ix_traffic_metrics_period_start; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_period_start ON public.traffic_metrics USING btree (period_start);


--
-- Name: ix_traffic_metrics_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_platform ON public.traffic_metrics USING btree (platform);


--
-- Name: ix_traffic_metrics_platform_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_platform_account_id ON public.traffic_metrics USING btree (platform_account_id);


--
-- Name: ix_traffic_metrics_sku; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_sku ON public.traffic_metrics USING btree (sku);


--
-- Name: ix_traffic_metrics_stat_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_stat_date ON public.traffic_metrics USING btree (stat_date);


--
-- Name: ix_traffic_metrics_synced_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_metrics_synced_at ON public.traffic_metrics USING btree (synced_at);


--
-- Name: ix_traffic_sync_runs_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_sync_runs_account_id ON public.traffic_sync_runs USING btree (account_id);


--
-- Name: ix_traffic_sync_runs_account_latest; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_sync_runs_account_latest ON public.traffic_sync_runs USING btree (platform_account_id, id);


--
-- Name: ix_traffic_sync_runs_account_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_sync_runs_account_started ON public.traffic_sync_runs USING btree (platform_account_id, started_at);


--
-- Name: ix_traffic_sync_runs_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_sync_runs_platform ON public.traffic_sync_runs USING btree (platform);


--
-- Name: ix_traffic_sync_runs_platform_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_sync_runs_platform_account_id ON public.traffic_sync_runs USING btree (platform_account_id);


--
-- Name: ix_traffic_sync_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_traffic_sync_runs_status ON public.traffic_sync_runs USING btree (status);


--
-- Name: ix_translation_provider_settings_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_translation_provider_settings_enabled ON public.translation_provider_settings USING btree (enabled);


--
-- Name: ix_user_menu_permissions_menu_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_menu_permissions_menu_code ON public.user_menu_permissions USING btree (menu_code);


--
-- Name: ix_user_menu_permissions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_menu_permissions_user_id ON public.user_menu_permissions USING btree (user_id);


--
-- Name: ix_user_roles_role_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_roles_role_id ON public.user_roles USING btree (role_id);


--
-- Name: ix_user_roles_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_roles_user_id ON public.user_roles USING btree (user_id);


--
-- Name: ix_user_table_preferences_table_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_table_preferences_table_key ON public.user_table_preferences USING btree (table_key);


--
-- Name: ix_user_table_preferences_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_table_preferences_user_id ON public.user_table_preferences USING btree (user_id);


--
-- Name: uq_order_operation_logs_event_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_order_operation_logs_event_key ON public.order_operation_logs USING btree (event_key) WHERE ((event_key IS NOT NULL) AND ((event_key)::text <> ''::text));


--
-- Name: uq_orders_internal_order_no; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_orders_internal_order_no ON public.orders USING btree (internal_order_no);


--
-- Name: uq_platform_print_settings_platform_document; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_platform_print_settings_platform_document ON public.platform_print_settings USING btree (platform, document_type);


--
-- Name: uq_scheduled_task_run_orders_run_order_platform; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_scheduled_task_run_orders_run_order_platform ON public.scheduled_task_run_orders USING btree (run_id, order_id, platform);


--
-- Name: label_files label_files_shipment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.label_files
    ADD CONSTRAINT label_files_shipment_id_fkey FOREIGN KEY (shipment_id) REFERENCES public.shipments(id);


--
-- Name: local_users local_users_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey1 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey10; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey10 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey100; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey100 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey101; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey101 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey102; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey102 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey103; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey103 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey104; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey104 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey105; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey105 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey106; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey106 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey107; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey107 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey108; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey108 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey109; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey109 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey11; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey11 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey110; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey110 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey111; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey111 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey112; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey112 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey113; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey113 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey114; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey114 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey115; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey115 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey116; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey116 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey117; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey117 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey118; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey118 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey119; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey119 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey12; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey12 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey120; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey120 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey121; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey121 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey122; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey122 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey123; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey123 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey124; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey124 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey125; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey125 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey126; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey126 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey127; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey127 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey128; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey128 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey129; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey129 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey13; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey13 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey130; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey130 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey131; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey131 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey132; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey132 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey133; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey133 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey134; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey134 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey135; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey135 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey136; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey136 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey137; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey137 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey138; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey138 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey139; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey139 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey14; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey14 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey140; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey140 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey141; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey141 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey142; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey142 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey143; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey143 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey144; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey144 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey145; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey145 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey146; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey146 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey147; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey147 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey148; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey148 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey149; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey149 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey15; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey15 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey150; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey150 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey151; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey151 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey152; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey152 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey153; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey153 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey154; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey154 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey155; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey155 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey156; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey156 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey157; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey157 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey158; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey158 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey159; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey159 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey16; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey16 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey17; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey17 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey18; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey18 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey19; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey19 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey2; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey2 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey20; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey20 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey21; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey21 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey22; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey22 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey23; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey23 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey24; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey24 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey25; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey25 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey26; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey26 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey27; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey27 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey28; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey28 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey29; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey29 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey3; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey3 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey30; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey30 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey31; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey31 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey32; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey32 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey33; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey33 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey34; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey34 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey35; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey35 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey36; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey36 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey37; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey37 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey38; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey38 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey39; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey39 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey4; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey4 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey40; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey40 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey41; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey41 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey42; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey42 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey43; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey43 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey44; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey44 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey45; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey45 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey46; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey46 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey47; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey47 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey48; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey48 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey49; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey49 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey5; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey5 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey50; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey50 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey51; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey51 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey52; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey52 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey53; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey53 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey54; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey54 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey55; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey55 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey56; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey56 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey57; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey57 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey58; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey58 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey59; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey59 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey6; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey6 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey60; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey60 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey61; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey61 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey62; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey62 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey63; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey63 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey64; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey64 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey65; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey65 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey66; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey66 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey67; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey67 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey68; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey68 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey69; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey69 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey7; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey7 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey70; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey70 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey71; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey71 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey72; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey72 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey73; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey73 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey74; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey74 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey75; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey75 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey76; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey76 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey77; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey77 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey78; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey78 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey79; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey79 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey8; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey8 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey80; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey80 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey81; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey81 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey82; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey82 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey83; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey83 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey84; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey84 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey85; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey85 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey86; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey86 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey87; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey87 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey88; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey88 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey89; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey89 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey9; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey9 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey90; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey90 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey91; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey91 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey92; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey92 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey93; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey93 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey94; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey94 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey95; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey95 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey96; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey96 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey97; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey97 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey98; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey98 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: local_users local_users_role_id_fkey99; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.local_users
    ADD CONSTRAINT local_users_role_id_fkey99 FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--
-- Name: model_settings model_settings_endpoint_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_settings
    ADD CONSTRAINT model_settings_endpoint_id_fkey FOREIGN KEY (endpoint_id) REFERENCES public.model_endpoints(id);


--
-- Name: oauth_authorization_sessions oauth_authorization_sessions_platform_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_authorization_sessions
    ADD CONSTRAINT oauth_authorization_sessions_platform_account_id_fkey FOREIGN KEY (platform_account_id) REFERENCES public.platform_accounts(id) ON DELETE CASCADE;


--
-- Name: order_follow_up_export_artifacts order_follow_up_export_artifacts_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_artifacts
    ADD CONSTRAINT order_follow_up_export_artifacts_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.order_follow_up_export_jobs(id) ON DELETE CASCADE;


--
-- Name: order_follow_up_export_items order_follow_up_export_items_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_items
    ADD CONSTRAINT order_follow_up_export_items_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.order_follow_up_export_jobs(id) ON DELETE CASCADE;


--
-- Name: order_follow_up_export_jobs order_follow_up_export_jobs_scheduled_task_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_follow_up_export_jobs
    ADD CONSTRAINT order_follow_up_export_jobs_scheduled_task_run_id_fkey FOREIGN KEY (scheduled_task_run_id) REFERENCES public.scheduled_task_runs(id) ON DELETE SET NULL;


--
-- Name: order_items order_items_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: order_operation_logs order_operation_logs_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_operation_logs
    ADD CONSTRAINT order_operation_logs_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: order_risk_handlings order_risk_handlings_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_risk_handlings
    ADD CONSTRAINT order_risk_handlings_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: outbound_scan_records outbound_scan_records_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.outbound_scan_records
    ADD CONSTRAINT outbound_scan_records_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);


--
-- Name: platform_product_catalog_items platform_product_catalog_items_pricing_rule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_product_catalog_items
    ADD CONSTRAINT platform_product_catalog_items_pricing_rule_id_fkey FOREIGN KEY (pricing_rule_id) REFERENCES public.platform_product_pricing_rules(id) ON DELETE SET NULL;


--
-- Name: platform_product_catalog_items platform_product_catalog_items_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_product_catalog_items
    ADD CONSTRAINT platform_product_catalog_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE SET NULL;


--
-- Name: platform_product_catalog_items platform_product_catalog_items_shop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_product_catalog_items
    ADD CONSTRAINT platform_product_catalog_items_shop_id_fkey FOREIGN KEY (shop_id) REFERENCES public.platform_accounts(id) ON DELETE CASCADE;


--
-- Name: platform_product_pricing_rules platform_product_pricing_rules_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_product_pricing_rules
    ADD CONSTRAINT platform_product_pricing_rules_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: platform_product_pricing_rules platform_product_pricing_rules_shop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_product_pricing_rules
    ADD CONSTRAINT platform_product_pricing_rules_shop_id_fkey FOREIGN KEY (shop_id) REFERENCES public.platform_accounts(id) ON DELETE CASCADE;


--
-- Name: product_inventory product_inventory_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_inventory
    ADD CONSTRAINT product_inventory_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: product_shop_mappings product_shop_mappings_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_shop_mappings
    ADD CONSTRAINT product_shop_mappings_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: product_shop_mappings product_shop_mappings_shop_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_shop_mappings
    ADD CONSTRAINT product_shop_mappings_shop_id_fkey FOREIGN KEY (shop_id) REFERENCES public.platform_accounts(id);


--
-- Name: products products_buyer_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey1 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey10; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey10 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey100; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey100 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey101; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey101 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey102; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey102 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey103; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey103 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey104; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey104 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey105; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey105 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey106; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey106 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey107; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey107 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey108; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey108 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey109; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey109 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey11; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey11 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey110; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey110 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey111; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey111 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey112; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey112 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey113; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey113 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey114; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey114 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey115; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey115 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey116; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey116 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey117; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey117 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey118; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey118 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey119; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey119 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey12; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey12 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey120; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey120 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey121; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey121 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey122; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey122 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey123; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey123 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey124; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey124 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey125; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey125 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey126; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey126 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey127; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey127 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey128; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey128 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey129; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey129 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey13; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey13 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey130; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey130 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey131; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey131 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey132; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey132 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey133; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey133 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey134; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey134 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey135; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey135 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey136; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey136 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey137; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey137 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey138; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey138 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey139; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey139 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey14; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey14 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey140; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey140 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey141; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey141 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey142; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey142 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey143; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey143 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey144; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey144 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey145; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey145 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey146; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey146 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey147; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey147 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey148; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey148 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey149; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey149 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey15; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey15 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey150; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey150 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey151; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey151 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey152; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey152 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey153; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey153 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey154; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey154 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey155; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey155 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey156; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey156 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey16; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey16 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey17; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey17 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey18; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey18 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey19; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey19 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey2; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey2 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey20; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey20 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey21; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey21 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey22; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey22 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey23; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey23 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey24; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey24 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey25; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey25 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey26; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey26 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey27; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey27 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey28; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey28 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey29; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey29 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey3; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey3 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey30; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey30 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey31; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey31 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey32; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey32 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey33; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey33 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey34; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey34 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey35; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey35 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey36; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey36 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey37; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey37 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey38; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey38 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey39; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey39 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey4; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey4 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey40; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey40 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey41; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey41 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey42; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey42 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey43; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey43 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey44; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey44 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey45; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey45 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey46; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey46 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey47; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey47 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey48; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey48 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey49; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey49 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey5; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey5 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey50; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey50 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey51; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey51 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey52; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey52 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey53; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey53 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey54; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey54 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey55; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey55 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey56; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey56 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey57; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey57 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey58; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey58 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey59; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey59 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey6; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey6 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey60; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey60 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey61; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey61 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey62; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey62 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey63; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey63 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey64; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey64 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey65; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey65 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey66; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey66 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey67; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey67 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey68; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey68 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey69; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey69 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey7; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey7 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey70; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey70 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey71; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey71 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey72; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey72 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey73; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey73 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey74; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey74 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey75; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey75 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey76; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey76 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey77; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey77 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey78; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey78 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey79; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey79 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey8; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey8 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey80; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey80 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey81; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey81 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey82; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey82 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey83; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey83 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey84; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey84 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey85; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey85 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey86; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey86 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey87; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey87 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey88; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey88 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey89; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey89 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey9; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey9 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey90; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey90 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey91; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey91 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey92; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey92 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey93; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey93 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey94; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey94 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey95; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey95 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey96; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey96 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey97; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey97 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey98; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey98 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: products products_buyer_user_id_fkey99; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_buyer_user_id_fkey99 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_edit_locks purchase_order_edit_locks_purchase_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_edit_locks
    ADD CONSTRAINT purchase_order_edit_locks_purchase_order_id_fkey FOREIGN KEY (purchase_order_id) REFERENCES public.purchase_orders(id) ON DELETE CASCADE;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey1 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey10; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey10 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey100; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey100 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey101; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey101 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey102; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey102 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey103; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey103 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey104; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey104 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey105; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey105 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey106; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey106 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey107; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey107 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey108; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey108 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey109; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey109 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey11; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey11 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey110; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey110 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey111; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey111 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey112; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey112 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey113; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey113 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey114; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey114 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey115; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey115 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey116; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey116 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey117; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey117 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey118; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey118 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey119; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey119 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey12; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey12 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey120; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey120 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey121; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey121 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey122; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey122 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey123; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey123 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey124; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey124 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey125; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey125 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey126; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey126 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey127; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey127 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey128; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey128 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey129; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey129 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey13; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey13 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey130; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey130 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey131; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey131 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey132; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey132 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey133; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey133 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey134; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey134 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey135; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey135 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey136; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey136 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey137; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey137 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey138; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey138 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey139; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey139 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey14; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey14 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey140; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey140 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey141; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey141 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey142; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey142 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey143; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey143 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey144; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey144 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey145; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey145 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey146; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey146 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey147; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey147 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey148; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey148 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey149; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey149 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey15; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey15 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey150; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey150 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey151; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey151 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey152; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey152 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey153; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey153 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey154; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey154 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey155; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey155 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey156; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey156 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey16; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey16 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey17; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey17 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey18; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey18 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey19; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey19 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey2; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey2 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey20; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey20 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey21; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey21 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey22; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey22 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey23; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey23 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey24; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey24 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey25; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey25 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey26; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey26 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey27; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey27 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey28; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey28 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey29; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey29 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey3; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey3 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey30; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey30 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey31; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey31 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey32; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey32 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey33; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey33 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey34; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey34 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey35; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey35 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey36; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey36 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey37; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey37 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey38; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey38 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey39; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey39 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey4; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey4 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey40; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey40 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey41; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey41 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey42; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey42 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey43; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey43 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey44; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey44 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey45; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey45 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey46; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey46 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey47; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey47 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey48; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey48 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey49; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey49 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey5; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey5 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey50; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey50 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey51; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey51 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey52; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey52 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey53; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey53 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey54; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey54 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey55; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey55 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey56; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey56 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey57; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey57 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey58; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey58 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey59; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey59 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey6; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey6 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey60; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey60 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey61; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey61 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey62; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey62 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey63; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey63 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey64; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey64 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey65; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey65 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey66; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey66 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey67; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey67 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey68; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey68 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey69; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey69 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey7; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey7 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey70; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey70 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey71; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey71 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey72; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey72 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey73; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey73 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey74; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey74 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey75; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey75 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey76; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey76 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey77; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey77 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey78; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey78 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey79; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey79 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey8; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey8 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey80; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey80 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey81; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey81 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey82; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey82 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey83; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey83 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey84; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey84 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey85; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey85 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey86; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey86 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey87; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey87 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey88; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey88 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey89; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey89 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey9; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey9 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey90; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey90 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey91; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey91 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey92; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey92 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey93; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey93 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey94; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey94 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey95; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey95 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey96; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey96 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey97; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey97 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey98; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey98 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_buyer_user_id_fkey99; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_buyer_user_id_fkey99 FOREIGN KEY (buyer_user_id) REFERENCES public.local_users(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE SET NULL;


--
-- Name: purchase_order_items purchase_order_items_purchase_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_purchase_order_id_fkey FOREIGN KEY (purchase_order_id) REFERENCES public.purchase_orders(id) ON DELETE CASCADE;


--
-- Name: purchase_order_sources purchase_order_sources_purchase_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_sources
    ADD CONSTRAINT purchase_order_sources_purchase_order_id_fkey FOREIGN KEY (purchase_order_id) REFERENCES public.purchase_orders(id) ON DELETE CASCADE;


--
-- Name: purchase_order_sources purchase_order_sources_purchase_order_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_order_sources
    ADD CONSTRAINT purchase_order_sources_purchase_order_item_id_fkey FOREIGN KEY (purchase_order_item_id) REFERENCES public.purchase_order_items(id) ON DELETE CASCADE;


--
-- Name: role_menu_permissions role_menu_permissions_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_menu_permissions
    ADD CONSTRAINT role_menu_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: scheduled_task_run_orders scheduled_task_run_orders_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_task_run_orders
    ADD CONSTRAINT scheduled_task_run_orders_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.scheduled_task_runs(id) ON DELETE CASCADE;


--
-- Name: scheduled_task_run_steps scheduled_task_run_steps_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_task_run_steps
    ADD CONSTRAINT scheduled_task_run_steps_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.scheduled_task_runs(id) ON DELETE CASCADE;


--
-- Name: shipments shipments_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);


--
-- Name: traffic_metrics traffic_metrics_platform_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traffic_metrics
    ADD CONSTRAINT traffic_metrics_platform_account_id_fkey FOREIGN KEY (platform_account_id) REFERENCES public.platform_accounts(id) ON DELETE CASCADE;


--
-- Name: traffic_sync_runs traffic_sync_runs_platform_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traffic_sync_runs
    ADD CONSTRAINT traffic_sync_runs_platform_account_id_fkey FOREIGN KEY (platform_account_id) REFERENCES public.platform_accounts(id) ON DELETE CASCADE;


--
-- Name: user_menu_permissions user_menu_permissions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_menu_permissions
    ADD CONSTRAINT user_menu_permissions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.local_users(id) ON DELETE CASCADE;


--
-- Name: user_roles user_roles_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: user_roles user_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.local_users(id) ON DELETE CASCADE;


--
-- Name: user_table_preferences user_table_preferences_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_table_preferences
    ADD CONSTRAINT user_table_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.local_users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--
