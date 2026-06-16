-- ================================================================
-- ADICIÓN: Zonas de altitud mínima MSAW + Perfiles de aproximación
-- ================================================================

-- ── 1. MINIMUMS ZONES (polígonos geográficos con altitud mínima) ──

-- Zona con su altitud mínima asociada
CREATE TABLE IF NOT EXISTS minimums_zones_kernel (
    identifier          VARCHAR(6)  NOT NULL PRIMARY KEY,  -- ej: 80E, 60S, 110N
    altitude            REAL        NOT NULL,               -- altitud mínima (ft)
    colour              INTEGER,
    c1                  SMALLINT,
    c2                  SMALLINT,
    c3                  SMALLINT,
    time_to_prediction  SMALLINT    -- anticipación de alerta (seg)
);

-- Vértices del polígono de cada zona
CREATE TABLE IF NOT EXISTS minimums_zones_vertices (
    zone_identifier     VARCHAR(6)  NOT NULL,  -- FK → minimums_zones_kernel.identifier
    sequence_number     SMALLINT    NOT NULL,
    latitude_image      VARCHAR(7)  NOT NULL,
    longitude_image     VARCHAR(8)  NOT NULL,
    lat_dec             VARCHAR(2),
    lon_dec             VARCHAR(2),
    PRIMARY KEY (zone_identifier, sequence_number),
    FOREIGN KEY (zone_identifier) REFERENCES minimums_zones_kernel(identifier)
);

-- ── 2. APPROACH PROFILES (supresión de MSAW en aproximación) ──────

-- Parámetros globales de tolerancia para todos los perfiles
CREATE TABLE IF NOT EXISTS profile_parameters (
    tol_heading         INTEGER,        -- tolerancia de rumbo (°) para activar perfil
    tol_altitude        DOUBLE,         -- tolerancia vertical (ft × 100)
    tol_distance        DOUBLE,         -- tolerancia lateral (NM)
    entorno_aerodrome   DOUBLE          -- radio de entorno del aeródromo (NM)
);

-- Perfiles de aproximación por aeropuerto/pista/categoría
-- kind: 'A'=Arrival (aproximación), 'D'=Departure (salida)
CREATE TABLE IF NOT EXISTS profiles_kernel (
    name                VARCHAR(7)  NOT NULL PRIMARY KEY,  -- ej: RWY01A, RWY19D
    airport             VARCHAR(4)  NOT NULL,               -- FK → airports_kernel.identifier_name
    runway              VARCHAR(3)  NOT NULL,               -- FK → airports_runways.runway_identity
    category            VARCHAR(1)  NOT NULL,               -- siempre 'G' (General)
    kind                VARCHAR(1)  NOT NULL,               -- 'A'=Arrival, 'D'=Departure
    FOREIGN KEY (airport) REFERENCES airports_kernel(identifier_name),
    FOREIGN KEY (airport, runway) REFERENCES airports_runways(airport_identity, runway_identity)
);

-- Puntos que definen el perfil (waypoints con altitud mínima decreciente hacia la pista)
-- El sistema interpola altitudes mínimas entre puntos consecutivos (seq_num)
CREATE TABLE IF NOT EXISTS profile_points (
    perfil_id           VARCHAR(7)  NOT NULL,  -- FK → profiles_kernel.name
    airport             VARCHAR(4),             -- FK → airports_kernel (redundante, para trazabilidad)
    runway              VARCHAR(3),
    point               VARCHAR(6)  NOT NULL,   -- nombre del punto ej: INICIO, MEDIO, EDNUL
    category            VARCHAR(1),
    latitude            VARCHAR(7)  NOT NULL,
    longitude           VARCHAR(8)  NOT NULL,
    distance            DOUBLE,                 -- distancia desde el umbral (NM)
    azimut              INTEGER,                -- rumbo hacia la pista (°)
    distance_lateral    DOUBLE,                 -- ancho del corredor (NM a cada lado)
    altitude            DOUBLE,                 -- altitud mínima en este punto (ft × 100)
    seq_num             SMALLINT,               -- orden del punto en el perfil
    lat_dec             VARCHAR(2),
    lon_dec             VARCHAR(2),
    PRIMARY KEY (perfil_id, point),
    FOREIGN KEY (perfil_id) REFERENCES profiles_kernel(name)
);

-- ── 3. APM APPROACH PROFILES (perfiles paramétricos por pista) ────
-- Define un corredor trapezoidal de aproximación usando pendientes y distancias.
-- El sistema usa glide_slope + lower/upper_slope para calcular altitud mínima
-- a cada distancia sin necesidad de definir puntos explícitos.

CREATE TABLE IF NOT EXISTS apm_profiles_kernel (
    airport_id          VARCHAR(4)  NOT NULL,   -- FK → airports_kernel.identifier_name
    runway_id           VARCHAR(3)  NOT NULL,   -- FK → airports_runways.runway_identity
    min_distance        REAL        NOT NULL DEFAULT 3.0,   -- distancia mínima desde umbral (NM)
    max_distance        REAL        NOT NULL DEFAULT 12.0,  -- distancia máxima (NM)
    half_wide           REAL        NOT NULL DEFAULT 1.0,   -- semiancho del corredor (NM)
    lower_slope         REAL        NOT NULL DEFAULT 2.5,   -- pendiente inferior (°) - límite bajo
    upper_slope         REAL        NOT NULL DEFAULT 4.8,   -- pendiente superior (°) - límite alto
    glide_slope         REAL,                               -- ángulo del glide slope (°) ej: 3.0
    enable_jh           VARCHAR(1)  DEFAULT 'N',            -- habilitar Jump Height
    jh                  SMALLINT    DEFAULT 0,              -- Jump Height (ft)
    lateral_dev         VARCHAR(1)  DEFAULT 'Y',            -- alertar desviación lateral
    vertical_up_dev     VARCHAR(1)  DEFAULT 'Y',            -- alertar por encima del perfil
    vertical_down_dev   VARCHAR(1)  DEFAULT 'Y',            -- alertar por debajo del perfil
    -- Coordenadas del eje de aproximación (calculadas desde pista)
    near_latitude       VARCHAR(10),   -- lat del punto próximo (umbral)
    near_longitude      VARCHAR(11),
    far_latitude        VARCHAR(10),   -- lat del punto lejano (IAF aprox)
    far_longitude       VARCHAR(11),
    PRIMARY KEY (airport_id, runway_id),
    FOREIGN KEY (airport_id) REFERENCES airports_kernel(identifier_name),
    FOREIGN KEY (airport_id, runway_id) REFERENCES airports_runways(airport_identity, runway_identity)
);

-- ── VISTAS ADICIONALES ────────────────────────────────────────────

-- Zonas MSAW con polígonos completos y coordenadas decimales
-- (conversión DMS→DD se hace en Python con dms_to_dd())
CREATE OR REPLACE VIEW v_minimums_zones_full AS
SELECT
    mzk.identifier,
    mzk.altitude,
    mzk.time_to_prediction,
    mzv.sequence_number,
    mzv.latitude_image,
    mzv.longitude_image
FROM minimums_zones_kernel mzk
LEFT JOIN minimums_zones_vertices mzv ON mzk.identifier = mzv.zone_identifier
ORDER BY mzk.identifier, mzv.sequence_number;

-- Perfiles de aproximación con puntos y altitudes (para visualizar el corredor)
CREATE OR REPLACE VIEW v_approach_profiles_full AS
SELECT
    pk.name             AS profile,
    pk.airport,
    pk.runway,
    pk.kind,            -- A=Arrival, D=Departure
    pp.seq_num,
    pp.point,
    pp.latitude,
    pp.longitude,
    pp.altitude,
    pp.distance,
    pp.azimut,
    pp.distance_lateral
FROM profiles_kernel pk
JOIN profile_points pp ON pk.name = pp.perfil_id
ORDER BY pk.name, pp.seq_num;

-- APM profiles con datos de aeropuerto para visualización del corredor
CREATE OR REPLACE VIEW v_apm_profiles_full AS
SELECT
    ap.airport_id,
    ak.latitude_image   AS airport_lat,
    ak.longitude_image  AS airport_lon,
    ak.place_altitude   AS airport_elev,
    ap.runway_id,
    ar.direction_bearing AS runway_qfu,
    ap.min_distance,
    ap.max_distance,
    ap.half_wide,
    ap.lower_slope,
    ap.upper_slope,
    ap.glide_slope,
    ap.near_latitude,
    ap.near_longitude,
    ap.far_latitude,
    ap.far_longitude
FROM apm_profiles_kernel ap
JOIN airports_kernel ak  ON ap.airport_id = ak.identifier_name
JOIN airports_runways ar ON ap.airport_id = ar.airport_identity
                        AND ap.runway_id  = ar.runway_identity;
