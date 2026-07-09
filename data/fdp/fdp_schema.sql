CREATE TABLE IF NOT EXISTS flight_plans (
    arcid         TEXT PRIMARY KEY,
    adep          TEXT,
    ades          TEXT,
    aircraft_type TEXT,
    wtc           TEXT,
    requested_fl  TEXT,
    route         TEXT,
    eobt          TEXT,
    cop           TEXT,
    status        TEXT DEFAULT 'ACTIVE',
    raw_msg       TEXT,
    created_at    TIMESTAMP DEFAULT current_localtimestamp(),
    updated_at    TIMESTAMP DEFAULT current_localtimestamp()
);

CREATE TABLE IF NOT EXISTS fdp_log (
    ts       TIMESTAMP DEFAULT current_localtimestamp(),
    msg_type TEXT,
    arcid    TEXT,
    raw      TEXT
);
