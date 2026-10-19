-- Requires a PostgreSQL role permitted to install PostGIS (or an administrator can run this first).
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS cascadeshield_meta;

CREATE TABLE IF NOT EXISTS cascadeshield_meta.imports (
    processed_path text PRIMARY KEY,
    source_asset text NOT NULL,
    raw_sha256 text NOT NULL,
    processed_sha256 text NOT NULL,
    row_count bigint NOT NULL,
    table_schema text NOT NULL,
    table_name text NOT NULL,
    provenance jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);

-- Preserve invalid source text in staging; typed views expose NULL on failed conversion.
CREATE OR REPLACE FUNCTION cascadeshield_meta.safe_double(value text)
RETURNS double precision LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE result double precision;
BEGIN
    IF btrim(value) = '' THEN RETURN NULL; END IF;
    result := value::double precision;
    IF result::text IN ('Infinity', '-Infinity', 'NaN') THEN RETURN NULL; END IF;
    RETURN result;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION cascadeshield_meta.wgs84_point(latitude text, longitude text)
RETURNS geometry(Point,4326) LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT CASE WHEN cascadeshield_meta.safe_double(latitude) BETWEEN -90 AND 90
                     AND cascadeshield_meta.safe_double(longitude) BETWEEN -180 AND 180
                THEN ST_SetSRID(ST_MakePoint(cascadeshield_meta.safe_double(longitude),
                                            cascadeshield_meta.safe_double(latitude)),4326)
                ELSE NULL END;
$$;
