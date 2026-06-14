-- ================================================================
-- ESQUEMA DUCKDB - Base de datos ATM (FDP INDRA / EANA)
-- Grupos: Fixpoints, Airports, Airways, SID/STAR/IAP,
--         Airspaces (R/P/D), MSAW, Aircraft Performance
--
-- Fuente: PostgreSQL dump pg_dump v15.6
-- Nota: El dump original NO tiene FOREIGN KEY declaradas.
--       Las relaciones son implícitas por convención de nombres.
--       Se implementan aquí como FK reales para DuckDB.
--       DuckDB no soporta CHAR(n) con padding; se usa VARCHAR(n).
--       Total relaciones mapeadas: 38
-- ================================================================


-- ================================================================
-- TABLAS DE SOPORTE / LOOKUP (sin FK salientes)
-- ================================================================

-- Categorías de vuelo (lookup, referenciada por códigos MSAW y SID/STAR)
CREATE TABLE IF NOT EXISTS flight_category (
    category            VARCHAR(10) NOT NULL PRIMARY KEY  -- ej: HEAD, HAZMAT, FFR
);


-- ================================================================
-- 1. FIXPOINTS  ←  base de todas las rutas y procedimientos
-- ================================================================

CREATE TABLE IF NOT EXISTS fixpoints_kernel (
    identifier_name     VARCHAR(6)  NOT NULL PRIMARY KEY,  -- ej: ADNOR, TUC, CBA
    kind_specifier      VARCHAR(2)  NOT NULL,               -- VOR, NDB, FIX, DME, RWY...
    latitude_image      VARCHAR(7)  NOT NULL,
    longitude_image     VARCHAR(8)  NOT NULL,
    lat_dec             VARCHAR(2),
    lon_dec             VARCHAR(2),
    center_situation    VARCHAR(1),
    strip_printing      VARCHAR(1),
    printablem          VARCHAR(1),
    colour              INTEGER,
    c1                  SMALLINT,
    c2                  SMALLINT,
    c3                  SMALLINT,
    compulsory          VARCHAR(1),   -- 'Y'=compulsory reporting point
    fly                 VARCHAR(1),   -- 'Y'=fly-over, 'N'=fly-by
    int_wpt             VARCHAR(1),
    aman_priority       SMALLINT,
    udpp                VARCHAR(1),
    tto                 SMALLINT,
    dvor_status         VARCHAR(1),
    dvor_status_ip      VARCHAR(15)
);

-- Fixpoints auxiliares (puntos definidos localmente, no en base ICAO)
CREATE TABLE IF NOT EXISTS aux_fixpoints_kernel (
    identifier_name     VARCHAR(6)  NOT NULL PRIMARY KEY,
    latitude_image      VARCHAR(7)  NOT NULL,
    longitude_image     VARCHAR(8)  NOT NULL,
    lat_dec             VARCHAR(2),
    lon_dec             VARCHAR(2)
    -- Nota: complementa fixpoints_kernel; identifier_name puede existir
    -- también en fixpoints_kernel (son espacios de nombres distintos)
);


-- ================================================================
-- 2. AIRPORTS
-- ================================================================

CREATE TABLE IF NOT EXISTS airports_kernel (
    identifier_name     VARCHAR(4)  NOT NULL PRIMARY KEY,  -- código ICAO: SABE, SAEZ...
    latitude_image      VARCHAR(7)  NOT NULL,
    longitude_image     VARCHAR(8)  NOT NULL,
    place_altitude      SMALLINT    NOT NULL,
    center_situation    VARCHAR(1)  NOT NULL,
    -- Pistas preferentes (soft FK hacia airports_runways.runway_identity)
    takeoff_runway      VARCHAR(3),
    landing_runway      VARCHAR(3),
    profile_asoc        VARCHAR(1)  NOT NULL,
    kind                VARCHAR(1),                        -- 'A'=aeropuerto, 'H'=helipuerto
    lat_dec             VARCHAR(2),
    lon_dec             VARCHAR(2),
    -- Flags operacionales
    apm                 VARCHAR(1),
    strip               VARCHAR(1),
    main_indicator      VARCHAR(4),
    ssr_origin          VARCHAR(1),
    ssr_as_internal     VARCHAR(1),
    awos                VARCHAR(1),
    printing            VARCHAR(4),
    departure_cfl       SMALLINT,
    adm_policy          SMALLINT,
    -- Campos APM (Airport Management): bitmasks de atributos considerados
    dep_ac_type         SMALLINT,
    dep_stand           SMALLINT,
    dep_first_point     SMALLINT,
    dep_flight_cat      SMALLINT,
    dep_ades            SMALLINT,
    dep_a_operator      SMALLINT,
    dep_ft              SMALLINT,
    arr_ac_type         SMALLINT,
    arr_stand           SMALLINT,
    arr_last_point      SMALLINT,
    arr_flight_cat      SMALLINT,
    arr_a_operator      SMALLINT,
    arr_ft              SMALLINT,
    atd_b_time          SMALLINT,
    ata_b_time          SMALLINT,
    tto_tta_upd         SMALLINT,
    tta_win             SMALLINT,
    apm_wtc_alert       VARCHAR(1),
    -- EFS (Electronic Flight Strip)
    efs_config          VARCHAR(1),
    efs_montreal_host   VARCHAR(15),
    efs_montreal_sender VARCHAR(4),
    efs_montreal_receiver VARCHAR(4),
    efs_singapore_host  VARCHAR(15),
    efs_singapore_sender VARCHAR(4),
    efs_singapore_receiver VARCHAR(4),
    efs_montreal_port   VARCHAR(6),
    efs_singapore_port  VARCHAR(6),
    efs_dest_addr       VARCHAR(7),
    efs_local_addr      VARCHAR(7)
);

-- Pistas del aeropuerto
-- PK compuesta: (airport_identity, runway_identity)
CREATE TABLE IF NOT EXISTS airports_runways (
    airport_identity    VARCHAR(4)  NOT NULL,  -- FK → airports_kernel.identifier_name
    runway_identity     VARCHAR(3)  NOT NULL,  -- ej: '01', '19', '11L'
    identifier_name     VARCHAR(7),            -- código combinado ej: SABE01
    place_altitude      SMALLINT,
    direction_bearing   SMALLINT,              -- QFU en grados
    latitude_image1     VARCHAR(7),            -- umbral cabecera 1
    longitude_image1    VARCHAR(8),
    latitude_image2     VARCHAR(7),            -- umbral cabecera 2
    longitude_image2    VARCHAR(8),
    lat1_dec            VARCHAR(2),
    lon1_dec            VARCHAR(2),
    lat2_dec            VARCHAR(2),
    lon2_dec            VARCHAR(2),
    -- Perfil de aproximación frustrada (missed approach): rangos y niveles A-E+X
    missed_app_range_a  DOUBLE,
    missed_app_level_a  SMALLINT,
    missed_app_range_b  DOUBLE,
    missed_app_level_b  SMALLINT,
    missed_app_range_c  DOUBLE,
    missed_app_level_c  SMALLINT,
    missed_app_range_d  DOUBLE,
    missed_app_level_d  SMALLINT,
    missed_app_range_e  DOUBLE,
    missed_app_level_e  SMALLINT,
    missed_app_range_x  DOUBLE,
    missed_app_level_x  SMALLINT,
    -- Habilitación por categoría OACI (A/B/C/D/E)
    cat_a_enable        SMALLINT,
    cat_b_enable        SMALLINT,
    cat_c_enable        SMALLINT,
    cat_d_enable        SMALLINT,
    cat_e_enable        SMALLINT,
    touchdown           REAL,
    head_prof_alt       REAL,
    time_to_rwy         SMALLINT,
    ils_status          VARCHAR(1),
    ils_status_ip       VARCHAR(15),
    PRIMARY KEY (airport_identity, runway_identity),
    FOREIGN KEY (airport_identity) REFERENCES airports_kernel(identifier_name)
);

-- Datos meteorológicos del aeropuerto (1:1 con airports_kernel)
CREATE TABLE IF NOT EXISTS airports_meteo (
    identifier_name     VARCHAR(4)  NOT NULL PRIMARY KEY,
    gamet_indicator     VARCHAR(1),
    display             VARCHAR(1),
    FOREIGN KEY (identifier_name) REFERENCES airports_kernel(identifier_name)
);

-- Entorno visual y de planificación del aeropuerto (1:1 con airports_kernel)
CREATE TABLE IF NOT EXISTS airport_environment (
    identifier_name     VARCHAR(4)  NOT NULL PRIMARY KEY,
    place_altitude      SMALLINT    NOT NULL,
    transition_level    SMALLINT    NOT NULL,  -- FL de transición
    base_temperature    SMALLINT    NOT NULL,
    visual_radius       SMALLINT    NOT NULL,
    visual_altitude     SMALLINT    NOT NULL,
    plan_rotation       DOUBLE      NOT NULL,
    drawing_scale       SMALLINT    NOT NULL,
    visual_x_origin     DOUBLE      NOT NULL,
    visual_y_origin     DOUBLE      NOT NULL,
    visual_rotation     DOUBLE      NOT NULL,
    place_latitude      VARCHAR(10),
    place_longitude     VARCHAR(11),
    plan_latitude       VARCHAR(10),
    plan_longitude      VARCHAR(11),
    FOREIGN KEY (identifier_name) REFERENCES airports_kernel(identifier_name)
);


-- ================================================================
-- 3. AIRWAYS (Aerovías)
-- ================================================================

CREATE TABLE IF NOT EXISTS airways_kernel (
    identifier_name     VARCHAR(6)  NOT NULL PRIMARY KEY,  -- ej: A001, B321, UL301
    minimum_altitude    SMALLINT,   -- FL mínimo de uso
    maximum_altitude    SMALLINT,   -- FL máximo de uso
    map_printing        VARCHAR(1),
    rnp_type            VARCHAR(6)  -- tipo PBN requerido
);

-- Secuencia de fixpoints que forman la aerovía
CREATE TABLE IF NOT EXISTS airways_pathpoints (
    airway_identity     VARCHAR(6)  NOT NULL,  -- FK → airways_kernel.identifier_name
    fixpoint_identity   VARCHAR(6)  NOT NULL,  -- FK → fixpoints_kernel.identifier_name
    sequence_number     SMALLINT    NOT NULL,
    direction_specifier VARCHAR(1),            -- 'F'=forward, 'B'=backward, 'A'=ambos
    PRIMARY KEY (airway_identity, fixpoint_identity, sequence_number),
    FOREIGN KEY (airway_identity)   REFERENCES airways_kernel(identifier_name),
    FOREIGN KEY (fixpoint_identity) REFERENCES fixpoints_kernel(identifier_name)
);

-- Pares de aerovías/tramos mutuamente inhibidos (evitar rutas redundantes)
CREATE TABLE IF NOT EXISTS airways_inhibition (
    id                  VARCHAR(20),
    airway1             VARCHAR(6),   -- FK → airways_kernel.identifier_name
    fix11               VARCHAR(6),   -- FK → fixpoints_kernel  (inicio tramo 1)
    fix12               VARCHAR(6),   -- FK → fixpoints_kernel  (fin tramo 1)
    airway2             VARCHAR(6),   -- FK → airways_kernel.identifier_name
    fix21               VARCHAR(6),   -- FK → fixpoints_kernel  (inicio tramo 2)
    fix22               VARCHAR(6)    -- FK → fixpoints_kernel  (fin tramo 2)
    -- FK implícitas: no se declaran formalmente por ser todas nullable
);


-- ================================================================
-- 4. SID / STAR / IAP  (Procedimientos de vuelo instrumental)
-- ================================================================

-- ── SID (Standard Instrument Departure) ──────────────────────

CREATE TABLE IF NOT EXISTS departure_procedures (
    identifier_name     VARCHAR(7)  NOT NULL,  -- código SID ej: ADNO1A
    airport_identity    VARCHAR(4)  NOT NULL,  -- FK → airports_kernel.identifier_name
    runway_identity     VARCHAR(3)  NOT NULL,  -- FK → airports_runways.runway_identity
    category            VARCHAR(1)  NOT NULL,  -- 'A','B','C','D','E' o 'N'
    turn_direction      VARCHAR(1),            -- 'L'=izquierda, 'R'=derecha
    turn_fixpoint       VARCHAR(6),            -- FK → fixpoints_kernel (nullable)
    fix_distance        SMALLINT,
    turning_level       SMALLINT,
    PRIMARY KEY (identifier_name, airport_identity, runway_identity, category),
    FOREIGN KEY (airport_identity) REFERENCES airports_kernel(identifier_name),
    FOREIGN KEY (airport_identity, runway_identity)
        REFERENCES airports_runways(airport_identity, runway_identity)
    -- turn_fixpoint: FK soft (nullable), no se declara formal
);

CREATE TABLE IF NOT EXISTS departure_pathpoints (
    route_identity      VARCHAR(7)  NOT NULL,  -- FK → departure_procedures.identifier_name
    category            VARCHAR(1)  NOT NULL,
    airport_identity    VARCHAR(4)  NOT NULL,  -- FK → airports_kernel.identifier_name
    runway_identity     VARCHAR(3)  NOT NULL,  -- FK → airports_runways
    fixpoint_identity   VARCHAR(6)  NOT NULL,  -- FK → fixpoints_kernel.identifier_name
    sequence_number     SMALLINT    NOT NULL,
    fixpoint_radial     SMALLINT,              -- radial del fix (si aplica)
    fixpoint_level      SMALLINT,              -- restricción de nivel en ese fix
    PRIMARY KEY (route_identity, category, airport_identity, runway_identity,
                 fixpoint_identity, sequence_number),
    FOREIGN KEY (route_identity, airport_identity, runway_identity, category)
        REFERENCES departure_procedures(identifier_name, airport_identity,
                                        runway_identity, category),
    FOREIGN KEY (airport_identity) REFERENCES airports_kernel(identifier_name),
    FOREIGN KEY (airport_identity, runway_identity)
        REFERENCES airports_runways(airport_identity, runway_identity),
    FOREIGN KEY (fixpoint_identity) REFERENCES fixpoints_kernel(identifier_name)
);

-- ── STAR (Standard Terminal Arrival Route) ───────────────────

CREATE TABLE IF NOT EXISTS arrival_procedures (
    identifier_name     VARCHAR(7)  NOT NULL,  -- código STAR ej: ADNO1A
    airport_identity    VARCHAR(4)  NOT NULL,  -- FK → airports_kernel.identifier_name
    runway_identity     VARCHAR(3)  NOT NULL,  -- FK → airports_runways
    category            VARCHAR(1),
    PRIMARY KEY (identifier_name, airport_identity, runway_identity),
    FOREIGN KEY (airport_identity) REFERENCES airports_kernel(identifier_name),
    FOREIGN KEY (airport_identity, runway_identity)
        REFERENCES airports_runways(airport_identity, runway_identity)
);

CREATE TABLE IF NOT EXISTS arrival_pathpoints (
    route_identity      VARCHAR(7)  NOT NULL,  -- FK → arrival_procedures.identifier_name
    category            VARCHAR(1)  NOT NULL,
    airport_identity    VARCHAR(4)  NOT NULL,
    runway_identity     VARCHAR(3)  NOT NULL,
    fixpoint_identity   VARCHAR(6)  NOT NULL,  -- FK → fixpoints_kernel.identifier_name
    sequence_number     SMALLINT    NOT NULL,
    overflight_level    SMALLINT,              -- nivel mínimo/máximo en ese fix
    PRIMARY KEY (route_identity, category, airport_identity, runway_identity,
                 fixpoint_identity, sequence_number),
    FOREIGN KEY (route_identity, airport_identity, runway_identity)
        REFERENCES arrival_procedures(identifier_name, airport_identity, runway_identity),
    FOREIGN KEY (airport_identity) REFERENCES airports_kernel(identifier_name),
    FOREIGN KEY (airport_identity, runway_identity)
        REFERENCES airports_runways(airport_identity, runway_identity),
    FOREIGN KEY (fixpoint_identity) REFERENCES fixpoints_kernel(identifier_name)
);

-- ── IAP (Instrument Approach Procedure) ──────────────────────

CREATE TABLE IF NOT EXISTS approach_routes (
    identifier_name     VARCHAR(7)  NOT NULL,
    kind_specifier      VARCHAR(1)  NOT NULL,  -- 'I'=ILS, 'V'=VOR, 'R'=RNAV/RNP, 'N'=NDB
    airport_identity    VARCHAR(4)  NOT NULL,  -- FK → airports_kernel.identifier_name
    runway_identity     VARCHAR(3)  NOT NULL,  -- FK → airports_runways
    gatepoint_name      VARCHAR(6)  NOT NULL,  -- FK → fixpoints_kernel (FAF/IF)
    def_dep             VARCHAR(7),            -- procedimiento de salida por frustrada
    def_arr             VARCHAR(7),            -- STAR por defecto asociada
    rnp_type            VARCHAR(6),
    priority            SMALLINT,
    status              VARCHAR(1)  DEFAULT '1',
    iaf                 VARCHAR(6),            -- FK → fixpoints_kernel (IAF, nullable)
    PRIMARY KEY (identifier_name, kind_specifier),
    FOREIGN KEY (airport_identity) REFERENCES airports_kernel(identifier_name),
    FOREIGN KEY (airport_identity, runway_identity)
        REFERENCES airports_runways(airport_identity, runway_identity),
    FOREIGN KEY (gatepoint_name) REFERENCES fixpoints_kernel(identifier_name)
    -- iaf: FK soft (nullable), no se declara formal
);

CREATE TABLE IF NOT EXISTS approach_pathpoints (
    route_identity      VARCHAR(7)  NOT NULL,  -- FK → approach_routes.identifier_name
    fixpoint_identity   VARCHAR(6)  NOT NULL,  -- FK → fixpoints_kernel.identifier_name
    sequence_number     SMALLINT    NOT NULL,
    PRIMARY KEY (route_identity, fixpoint_identity, sequence_number),
    FOREIGN KEY (route_identity) REFERENCES approach_routes(identifier_name),
    FOREIGN KEY (fixpoint_identity) REFERENCES fixpoints_kernel(identifier_name)
);


-- ================================================================
-- 5. RESTRICTED AIRSPACES (Restringidas R / Prohibidas P / Peligrosas D)
-- ================================================================

CREATE TABLE IF NOT EXISTS restricted_airspaces (
    identifier_name     VARCHAR(8)  NOT NULL PRIMARY KEY,  -- ej: LRA001, LRD015
    area_kind           VARCHAR(1),   -- 'R'=Restricted, 'P'=Prohibited, 'D'=Danger
    matter_specifier    VARCHAR(20),  -- descripción textual del tipo
    standing_purpose    VARCHAR(12),
    kind_identifier     VARCHAR(8),
    -- Límites verticales
    lower_altitude      SMALLINT,
    upper_altitude      SMALLINT,
    lower_unit          VARCHAR(1),   -- 'F'=FL, 'M'=MSL (ft), 'A'=AGL (ft)
    upper_unit          VARCHAR(1),
    -- Geometría
    contour_figure      VARCHAR(1),   -- 'P'=Polígono, 'C'=Círculo
    circle_radius       DOUBLE,       -- radio si es círculo
    radius_unit         VARCHAR(1),   -- 'N'=NM, 'K'=KM
    -- Activación
    scheduled_flag      VARCHAR(1),   -- 'Y'=tiene horario, 'N'=siempre activa
    permanent           VARCHAR(1),   -- 'Y'=permanente
    prediction_time     SMALLINT,     -- tiempo de predicción anticipada (min)
    -- Vigencia
    starting_date       VARCHAR(6),   -- DDMMYY
    ending_date         VARCHAR(6),
    starting_time       VARCHAR(4),   -- HHMM UTC
    ending_time         VARCHAR(4),
    -- Días de actividad
    monday_activity     VARCHAR(1),
    tuesday_activity    VARCHAR(1),
    wednesday_activity  VARCHAR(1),
    thursday_activity   VARCHAR(1),
    friday_activity     VARCHAR(1),
    saturday_activity   VARCHAR(1),
    sunday_activity     VARCHAR(1),
    class_identifier    VARCHAR(1)    -- clase del espacio aéreo (A-G)
);

-- Vértices del polígono del espacio restringido (cuando contour_figure='P')
CREATE TABLE IF NOT EXISTS restricted_vertices (
    airspace_identity   VARCHAR(8)  NOT NULL,  -- FK → restricted_airspaces.identifier_name
    sequence_number     SMALLINT    NOT NULL,
    latitude_image      VARCHAR(7)  NOT NULL,
    longitude_image     VARCHAR(8)  NOT NULL,
    lat_dec             VARCHAR(2),
    lon_dec             VARCHAR(2),
    visual              SMALLINT,
    PRIMARY KEY (airspace_identity, sequence_number),
    FOREIGN KEY (airspace_identity) REFERENCES restricted_airspaces(identifier_name)
);

-- Parámetros globales de presentación de airspaces (tabla singleton)
CREATE TABLE IF NOT EXISTS restricted_airspaces_parameters (
    raw_presentation    VARCHAR(3)   -- modo de visualización en HMI
);


-- ================================================================
-- 6. MSAW (Minimum Safe Altitude Warning)
-- ================================================================

-- Parámetros globales del algoritmo MSAW (tabla singleton)
CREATE TABLE IF NOT EXISTS msaw_parameters (
    time_to_prediction  SMALLINT,  -- anticipación de la alerta (seg)
    rocd                SMALLINT,  -- Rate Of Change of altitude mínimo (ft/min)
    cfl_thold           SMALLINT   -- umbral de CFL para activar predicción (ft)
);

-- Códigos SSR excluidos de las alertas MSAW
-- (vuelos especiales: militares, VFR conocidos, etc.)
CREATE TABLE IF NOT EXISTS codes_msaw (
    code                VARCHAR(4)  NOT NULL,  -- código SSR (octal 4 dígitos)
    category            VARCHAR(2)  NOT NULL,  -- 'NA'=no aplicable, 'MI'=militar, etc.
    PRIMARY KEY (code, category)
);

-- Zonas de mínimos radar para el cálculo MSAW
-- Define la altitud mínima segura en sectores polares alrededor del radar
CREATE TABLE IF NOT EXISTS radar_minimums_zones (
    radar_number        SMALLINT    NOT NULL,  -- identity_number del radar (ver radars_kernel)
    zone_identity       VARCHAR(6)  NOT NULL,
    initial_rho         REAL        NOT NULL,  -- distancia mínima desde radar (NM)
    final_rho           REAL        NOT NULL,  -- distancia máxima desde radar (NM)
    initial_theta       REAL        NOT NULL,  -- azimuth inicial (°)
    final_theta         REAL        NOT NULL,  -- azimuth final (°)
    PRIMARY KEY (radar_number, zone_identity)
    -- radar_number → radars_kernel.identity_number (fuera de scope; FK comentada)
);


-- ================================================================
-- 7. AIRCRAFT PERFORMANCE
-- ================================================================

-- Grupos de performance: agrupan tipos ICAO con comportamiento similar
CREATE TABLE IF NOT EXISTS aircraft_groups_kernel (
    identifier_name     VARCHAR(4)  NOT NULL PRIMARY KEY,  -- ej: B73H, A32M
    maximum_altitude    SMALLINT    NOT NULL,  -- FL máximo (ft/100)
    minimum_speed       SMALLINT    NOT NULL,  -- kt CAS mínima
    maximum_speed       SMALLINT    NOT NULL,  -- kt CAS máxima
    cruise_speed        SMALLINT    NOT NULL,  -- kt CAS crucero
    wake_turbulence     VARCHAR(1)  NOT NULL,  -- J/H/M/L (RECAT) o H/M/L (OACI)
    maximum_cas         SMALLINT,
    maximum_mach        DOUBLE
);

-- Performance del grupo por capas de altitud (climb/descent por FL)
CREATE TABLE IF NOT EXISTS aircraft_groups_layers (
    group_identity      VARCHAR(4)  NOT NULL,  -- FK → aircraft_groups_kernel.identifier_name
    upper_altitude      SMALLINT    NOT NULL,  -- FL techo de esta capa
    climb_speed         SMALLINT    NOT NULL,
    descent_speed       SMALLINT    NOT NULL,
    climb_rate          SMALLINT    NOT NULL,  -- ft/min
    descent_rate        SMALLINT    NOT NULL,
    PRIMARY KEY (group_identity, upper_altitude),
    FOREIGN KEY (group_identity) REFERENCES aircraft_groups_kernel(identifier_name)
);

-- Tipos de aeronave ICAO (designadores: B738, A320, C172...)
CREATE TABLE IF NOT EXISTS aircraft_types (
    designator          VARCHAR(4)  NOT NULL PRIMARY KEY,  -- designador ICAO
    group_name          VARCHAR(4)  NOT NULL,  -- FK → aircraft_groups_kernel.identifier_name
    recat               VARCHAR(1),            -- categoría RECAT-EU
    FOREIGN KEY (group_name) REFERENCES aircraft_groups_kernel(identifier_name)
);

-- Subtipos dentro de un tipo ICAO (variantes de peso o configuración)
CREATE TABLE IF NOT EXISTS aircraft_subtypes (
    identifier_name     VARCHAR(4)  NOT NULL,  -- FK → aircraft_types.designator
    st                  VARCHAR(1)  NOT NULL,  -- subtipo: 'H'=heavy, 'M'=medium, etc.
    group_identity      VARCHAR(4)  NOT NULL,  -- FK → aircraft_groups_kernel.identifier_name
    PRIMARY KEY (identifier_name, st),
    FOREIGN KEY (identifier_name) REFERENCES aircraft_types(designator),
    FOREIGN KEY (group_identity)  REFERENCES aircraft_groups_kernel(identifier_name)
);

-- Performance detallada por tipo (para simulación, AMAN y cálculos de trayectoria)
CREATE TABLE IF NOT EXISTS air_performances_kernel (
    identifier_name     VARCHAR(4)  NOT NULL PRIMARY KEY,  -- ej: B738 (igual que aircraft_types.designator)
    kind_specifier      VARCHAR(2)  NOT NULL,
    category            VARCHAR(1),    -- categoría de aproximación OACI (A/B/C/D)
    landing_gear        VARCHAR(1)  NOT NULL,
    fuselage_length     SMALLINT    NOT NULL,  -- metros
    wings_span_width    SMALLINT    NOT NULL,  -- metros
    nominal_height      SMALLINT    NOT NULL,  -- metros
    wake_turbulence     VARCHAR(1)  NOT NULL,
    -- Velocidades en tierra (kt)
    stand_taxi_speed    SMALLINT    NOT NULL,
    maxi_taxi_speed     SMALLINT    NOT NULL,
    reverse_speed       SMALLINT    NOT NULL,
    touch_go_speed      SMALLINT    NOT NULL,
    decision_speed      SMALLINT    NOT NULL,
    takeoff_speed       SMALLINT    NOT NULL,
    landing_speed       SMALLINT    NOT NULL,
    inter_app_speed     SMALLINT    NOT NULL,
    final_app_speed     SMALLINT    NOT NULL,
    -- Aceleraciones (m/s²)
    stand_taxi_accel    DOUBLE      NOT NULL,
    stand_taxi_decel    DOUBLE      NOT NULL,
    emergency_decel     DOUBLE      NOT NULL,
    takeoff_accel       DOUBLE      NOT NULL,
    landing_decel       DOUBLE      NOT NULL,
    -- Performance en vuelo
    maximum_altitude    SMALLINT    NOT NULL,
    minimum_speed       SMALLINT    NOT NULL,
    maximum_speed       SMALLINT    NOT NULL,
    maxi_climb_rate     SMALLINT    NOT NULL,  -- ft/min
    max_descent_rate    SMALLINT    NOT NULL,
    maxi_bank_angle     SMALLINT    NOT NULL,  -- grados
    -- Geometría de maniobra
    mini_turn_radius    SMALLINT    NOT NULL,
    outer_limitation    DOUBLE      NOT NULL,
    final_point         DOUBLE      NOT NULL,
    vertical_accel      SMALLINT    NOT NULL,
    -- Ángulos de pitch por fase de vuelo (grados)
    takeoff_pitch       SMALLINT    NOT NULL,
    landing_pitch       SMALLINT    NOT NULL,
    climb_pitch         SMALLINT    NOT NULL,
    descent_pitch       SMALLINT    NOT NULL,
    approach_pitch      SMALLINT    NOT NULL,
    flapless_pitch      SMALLINT    NOT NULL,
    pitching_rate       DOUBLE      NOT NULL,
    rolling_rate        DOUBLE      NOT NULL,
    crossover           SMALLINT    NOT NULL,  -- FL de transición CAS→Mach
    ads_b_period        SMALLINT
);

-- Performance detallada por capa de altitud (para trayectorias 4D)
CREATE TABLE IF NOT EXISTS air_performances_layers (
    group_identity      VARCHAR(4)  NOT NULL,  -- FK → air_performances_kernel.identifier_name
    upper_altitude      SMALLINT    NOT NULL,
    cruise_speed        SMALLINT    NOT NULL,
    holding_speed       SMALLINT    NOT NULL,
    stand_climb_speed   SMALLINT    NOT NULL,
    maxi_climb_speed    SMALLINT    NOT NULL,
    stand_descent_speed SMALLINT    NOT NULL,
    maxi_descent_speed  SMALLINT    NOT NULL,
    stand_acceleration  DOUBLE      NOT NULL,
    maxi_acceleration   DOUBLE      NOT NULL,
    stand_deceleration  DOUBLE      NOT NULL,
    maxi_deceleration   DOUBLE      NOT NULL,
    standard_climb_rate SMALLINT    NOT NULL,
    maximum_climb_rate  SMALLINT    NOT NULL,
    stand_descent_rate  SMALLINT    NOT NULL,
    maxi_descent_rate   SMALLINT    NOT NULL,
    standard_bank_angle SMALLINT    NOT NULL,
    min_speed_l         SMALLINT,
    max_speed_l         SMALLINT,
    PRIMARY KEY (group_identity, upper_altitude),
    FOREIGN KEY (group_identity) REFERENCES air_performances_kernel(identifier_name)
);


-- ================================================================
-- VISTAS ANALÍTICAS
-- ================================================================

-- Aerovía completa con coordenadas de cada fixpoint
CREATE OR REPLACE VIEW v_airways_full AS
SELECT
    ak.identifier_name      AS airway,
    ak.minimum_altitude,
    ak.maximum_altitude,
    ak.rnp_type,
    ap.sequence_number,
    ap.direction_specifier,
    fk.identifier_name      AS fixpoint,
    fk.kind_specifier       AS fix_kind,
    fk.latitude_image,
    fk.longitude_image,
    fk.compulsory
FROM airways_kernel ak
JOIN airways_pathpoints ap  ON ak.identifier_name = ap.airway_identity
JOIN fixpoints_kernel fk    ON ap.fixpoint_identity = fk.identifier_name
ORDER BY ak.identifier_name, ap.sequence_number;

-- SID completo con aeropuerto, pista y fixpoints
CREATE OR REPLACE VIEW v_sid_full AS
SELECT
    dp.identifier_name      AS sid,
    dp.airport_identity,
    dp.runway_identity,
    dp.category,
    dp.turn_direction,
    pp.sequence_number,
    fk.identifier_name      AS fixpoint,
    fk.kind_specifier       AS fix_kind,
    fk.latitude_image,
    fk.longitude_image,
    pp.fixpoint_level,
    pp.fixpoint_radial
FROM departure_procedures dp
JOIN departure_pathpoints pp
    ON  dp.identifier_name  = pp.route_identity
    AND dp.airport_identity = pp.airport_identity
    AND dp.runway_identity  = pp.runway_identity
    AND dp.category         = pp.category
JOIN fixpoints_kernel fk ON pp.fixpoint_identity = fk.identifier_name
ORDER BY dp.identifier_name, dp.airport_identity, pp.sequence_number;

-- STAR completo con aeropuerto, pista y fixpoints
CREATE OR REPLACE VIEW v_star_full AS
SELECT
    ap.identifier_name      AS star,
    ap.airport_identity,
    ap.runway_identity,
    ap.category,
    pp.sequence_number,
    fk.identifier_name      AS fixpoint,
    fk.kind_specifier       AS fix_kind,
    fk.latitude_image,
    fk.longitude_image,
    pp.overflight_level
FROM arrival_procedures ap
JOIN arrival_pathpoints pp
    ON  ap.identifier_name  = pp.route_identity
    AND ap.airport_identity = pp.airport_identity
    AND ap.runway_identity  = pp.runway_identity
JOIN fixpoints_kernel fk ON pp.fixpoint_identity = fk.identifier_name
ORDER BY ap.identifier_name, ap.airport_identity, pp.sequence_number;

-- IAP con aeropuerto y fixpoints
CREATE OR REPLACE VIEW v_approach_full AS
SELECT
    ar.identifier_name      AS iap,
    ar.kind_specifier       AS approach_type,
    ar.airport_identity,
    ar.runway_identity,
    ar.gatepoint_name       AS faf_fix,
    ar.iaf,
    ar.rnp_type,
    ap.sequence_number,
    fk.identifier_name      AS fixpoint,
    fk.kind_specifier       AS fix_kind,
    fk.latitude_image,
    fk.longitude_image
FROM approach_routes ar
JOIN approach_pathpoints ap ON ar.identifier_name = ap.route_identity
JOIN fixpoints_kernel fk    ON ap.fixpoint_identity = fk.identifier_name
ORDER BY ar.identifier_name, ap.sequence_number;

-- Espacios restringidos con polígono completo
CREATE OR REPLACE VIEW v_restricted_airspaces_full AS
SELECT
    ra.identifier_name,
    ra.area_kind,            -- R / P / D
    ra.matter_specifier,
    ra.lower_altitude,
    ra.upper_altitude,
    ra.lower_unit,
    ra.upper_unit,
    ra.permanent,
    ra.scheduled_flag,
    ra.contour_figure,
    ra.circle_radius,
    ra.radius_unit,
    rv.sequence_number,
    rv.latitude_image,
    rv.longitude_image
FROM restricted_airspaces ra
LEFT JOIN restricted_vertices rv ON ra.identifier_name = rv.airspace_identity
ORDER BY ra.identifier_name, rv.sequence_number;

-- Performance de aeronave consolidada
CREATE OR REPLACE VIEW v_aircraft_performance AS
SELECT
    at2.designator,
    at2.recat,
    agk.identifier_name     AS perf_group,
    agk.wake_turbulence,
    agk.cruise_speed        AS group_cruise_kt,
    agk.maximum_altitude    AS group_max_fl,
    apk.takeoff_speed       AS tof_speed_kt,
    apk.landing_speed       AS ldg_speed_kt,
    apk.final_app_speed     AS fap_speed_kt,
    apk.maxi_climb_rate     AS max_climb_fpm,
    apk.max_descent_rate    AS max_desc_fpm,
    apk.crossover           AS crossover_fl,
    apk.category            AS approach_cat
FROM aircraft_types at2
LEFT JOIN aircraft_groups_kernel agk ON at2.group_name       = agk.identifier_name
LEFT JOIN air_performances_kernel apk ON at2.group_name      = apk.identifier_name;

