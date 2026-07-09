"""Banco de pruebas para CAT048 (target reports SSR/PSR/Mode S) y CAT062 (SDPS system tracks).

REQ-DEC-1 (CAT048) y REQ-DEC-2 (CAT062) de la matriz de trazabilidad de certificación.

Fórmulas LSB de referencia:
- Rango         1/256 NM/LSB            (CAT048 I048/040)
- Azimuth       360/2¹⁶ °/LSB           (CAT048 I048/040)
- ToD           1/128 s/LSB             (CAT048/062)
- FL            1/4 FL/LSB (signed 14b) (CAT048 I048/090)
- Pos WGS84-62  180/2²⁵ °/LSB (4B sig) (CAT062 I062/105)
- Vel cartesian 0.25 m/s/LSB            (CAT062 I062/185)
- FL-62         1/4 FL/LSB (signed)     (CAT062 I062/136)
- Alt-62        6.25 ft/LSB             (CAT062 I062/130)
- Pos Cartesian 1852/128 m/LSB          (CAT048 I048/042)
"""
import math
import struct
import pytest

from decoder.decoders import cat048
from decoder.decoders import cat062


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def fspec(*frns: int) -> bytes:
    """FSPEC con los FRNs activos dados, extendido automáticamente con bits FX."""
    if not frns:
        return b'\x00'
    n_bytes = max(1, (max(frns) + 6) // 7)
    result = bytearray(n_bytes)
    for frn in frns:
        byte_idx = (frn - 1) // 7
        bit_pos = 7 - ((frn - 1) % 7)
        result[byte_idx] |= (1 << bit_pos)
    for i in range(n_bytes - 1):
        result[i] |= 0x01
    return bytes(result)


def frame(cat: int, records: bytes):
    bl = 3 + len(records)
    hdr = bytes([cat, (bl >> 8) & 0xFF, bl & 0xFF])
    return hdr + records, 3, bl


def tod_bytes(seconds: float) -> bytes:
    return struct.pack('>I', round(seconds * 128))[1:]


def rho_bytes(range_nm: float) -> bytes:
    return struct.pack('>H', round(range_nm * 256))


def theta_bytes(az_deg: float) -> bytes:
    return struct.pack('>H', round(az_deg * 65536 / 360))


# Callsign 'AAAAAAAA' en ICAO 6-bit (A=index 1 = 000001 × 8):
CALLSIGN_AAA_BYTES = bytes([0x04, 0x10, 0x41, 0x04, 0x10, 0x41])


# ────────────────────────────────────────────────────────────────────────────
# CAT048 — Monoradar Target Reports (SSR / PSR / Mode S)
# ────────────────────────────────────────────────────────────────────────────

class TestCat048:

    def _decode(self, records: bytes):
        payload, off, bl = frame(48, records)
        return cat048.decode(payload, off, bl, 48)

    # ── FRN1: SAC/SIC ────────────────────────────────────────────────────────

    def test_sac_sic(self):
        rec = fspec(1, 2) + bytes([226, 210]) + tod_bytes(0.0)
        r = self._decode(rec)
        assert r[0]['sac'] == 226 and r[0]['sic'] == 210

    # ── FRN2: Time of Day ────────────────────────────────────────────────────

    def test_timestamp_formula(self):
        # ToD = 3600 s → raw = 3600 * 128 = 460800 = 0x070800
        rec = fspec(1, 2) + bytes([1, 1]) + tod_bytes(3600.0)
        r = self._decode(rec)
        assert r[0]['timestamp'] == pytest.approx(3600.0, abs=0.01)

    def test_timestamp_medianoche(self):
        rec = fspec(1, 2) + bytes([1, 1]) + tod_bytes(0.0)
        r = self._decode(rec)
        assert r[0]['timestamp'] == pytest.approx(0.0, abs=0.01)

    # ── FRN3: Target Report Descriptor ───────────────────────────────────────

    def test_detection_type_combined(self):
        # I048/020: TYP=3 (PSR+SSR combined) → byte = (3<<5) = 0x60, FX=0
        rec = fspec(1, 3) + bytes([1, 1, 0x60])
        r = self._decode(rec)
        assert r[0]['detection_type'] == 3

    def test_spi_flag(self):
        # bit2 = SPI → byte = (3<<5) | 0x04 = 0x64
        rec = fspec(1, 3) + bytes([1, 1, 0x64])
        r = self._decode(rec)
        assert r[0]['spi'] is True

    def test_spi_false_when_not_set(self):
        rec = fspec(1, 3) + bytes([1, 1, 0x60])
        r = self._decode(rec)
        assert r[0]['spi'] is False

    # ── FRN4: Posición polar ─────────────────────────────────────────────────

    def test_rango_azimut_formula(self):
        # range=100 NM, azimuth=90°
        rec = fspec(1, 4) + bytes([1, 1]) + rho_bytes(100.0) + theta_bytes(90.0)
        r = self._decode(rec)
        assert r[0]['raw_range'] == pytest.approx(100.0, abs=0.01)
        assert r[0]['raw_azimuth'] == pytest.approx(90.0, abs=0.01)

    def test_rango_azimut_norte(self):
        rec = fspec(1, 4) + bytes([1, 1]) + rho_bytes(60.0) + theta_bytes(0.0)
        r = self._decode(rec)
        assert r[0]['raw_range'] == pytest.approx(60.0, abs=0.01)
        assert r[0]['raw_azimuth'] == pytest.approx(0.0, abs=0.01)

    def test_rango_azimut_oeste(self):
        rec = fspec(1, 4) + bytes([1, 1]) + rho_bytes(30.0) + theta_bytes(270.0)
        r = self._decode(rec)
        assert r[0]['raw_azimuth'] == pytest.approx(270.0, abs=0.02)

    # ── FRN5: Mode 3/A ───────────────────────────────────────────────────────

    def test_mode3a_decodificado(self):
        # mode3a = 0o2375 (decimal 1277 = 0x04FD)
        rec = fspec(1, 5) + bytes([1, 1]) + struct.pack('>H', 0o2375 & 0x0FFF)
        r = self._decode(rec)
        assert r[0]['mode_3a'] == 0o2375

    def test_mode3a_7000(self):
        rec = fspec(1, 5) + bytes([1, 1]) + struct.pack('>H', 0o7000)
        r = self._decode(rec)
        assert r[0]['mode_3a'] == 0o7000

    def test_mode3a_garbled_flag(self):
        # bit14=1 (G) en el raw → garbled=True
        raw = 0x4000 | (0o1234 & 0x0FFF)
        rec = fspec(1, 5) + bytes([1, 1]) + struct.pack('>H', raw)
        r = self._decode(rec)
        assert r[0]['garbled'] is True

    def test_mode3a_validated_flag(self):
        # bit15=0 (V=0 = validated)
        rec = fspec(1, 5) + bytes([1, 1]) + struct.pack('>H', 0x0100)
        r = self._decode(rec)
        assert r[0]['mode3a_validated'] is True

    # ── FRN6: Flight Level ───────────────────────────────────────────────────

    def test_flight_level_positivo(self):
        # FL=250 → fl_14bit=1000=0x03E8
        fl_14bit = round(250.0 / 0.25)  # 1000
        rec = fspec(1, 6) + bytes([1, 1]) + struct.pack('>H', fl_14bit)
        r = self._decode(rec)
        assert r[0]['flight_level'] == pytest.approx(250.0, abs=0.1)

    def test_flight_level_bajo_cero_no_guarda(self):
        # FL negativo → fl_val < 0 → no se guarda en el dict
        fl_14bit = round(-50.0 / 0.25)  # -200
        raw = (fl_14bit + 0x4000) & 0x3FFF  # representación complemento 14 bits
        rec = fspec(1, 6) + bytes([1, 1]) + struct.pack('>H', raw)
        r = self._decode(rec)
        assert 'flight_level' not in r[0]

    # ── FRN8: Aircraft Address (Mode S) ──────────────────────────────────────

    def test_mode_s_hex(self):
        rec = fspec(1, 8) + bytes([1, 1]) + bytes([0x7C, 0x12, 0x34])
        r = self._decode(rec)
        assert r[0]['mode_s'] == '7C1234'

    def test_mode_s_mayusculas(self):
        rec = fspec(1, 8) + bytes([1, 1]) + bytes([0xAB, 0xCD, 0xEF])
        r = self._decode(rec)
        assert r[0]['mode_s'] == 'ABCDEF'

    # ── FRN9: Aircraft Identification (callsign) ──────────────────────────────

    def test_callsign_decodificado(self):
        # CALLSIGN_AAA_BYTES → 'AAAAAAAA'
        rec = fspec(1, 9) + bytes([1, 1]) + CALLSIGN_AAA_BYTES
        r = self._decode(rec)
        assert r[0]['callsign'] == 'AAAAAAAA'

    # ── FRN11: Track Number ───────────────────────────────────────────────────

    def test_track_number(self):
        rec = fspec(1, 11) + bytes([1, 1]) + struct.pack('>H', 1234)
        r = self._decode(rec)
        assert r[0]['track_number'] == 1234

    # ── FRN12: Posición cartesiana calculada ──────────────────────────────────

    def test_posicion_cartesiana(self):
        # I048/042: x_raw=1280 → x=1280*1852/128=18520.0 m; y_raw=256 → y=256*1852/128=3704.0 m
        x_raw, y_raw = 1280, 256
        rec = fspec(1, 12) + bytes([1, 1]) + struct.pack('>hh', x_raw, y_raw)
        r = self._decode(rec)
        assert r[0]['x'] == pytest.approx(x_raw * 1852.0 / 128.0, abs=1.0)
        assert r[0]['y'] == pytest.approx(y_raw * 1852.0 / 128.0, abs=1.0)

    # ── FRN13: Velocidad y rumbo ──────────────────────────────────────────────

    def test_velocidad_y_rumbo(self):
        # I048/200: cgs_raw=400 → GS=400*0.2197265625=87.89 kt; chdg_raw=16384 → hdg=90°
        cgs_raw, chdg_raw = 400, round(90.0 * 65536 / 360)
        rec = fspec(1, 13) + bytes([1, 1]) + struct.pack('>HH', cgs_raw, chdg_raw)
        r = self._decode(rec)
        assert r[0]['extra_data']['track_angle'] == pytest.approx(90.0, abs=0.01)
        assert r[0]['extra_data']['ground_speed_nms'] == pytest.approx(
            cgs_raw * 0.2197265625 / 3600.0, abs=1e-5)

    # ── Plot completo con varios campos ───────────────────────────────────────

    def test_plot_completo(self):
        fl_raw = round(350.0 / 0.25) & 0x3FFF
        rec = (fspec(1, 2, 4, 5, 6, 8) +
               bytes([226, 210]) +
               tod_bytes(43200.0) +
               rho_bytes(120.5) + theta_bytes(315.0) +
               struct.pack('>H', 0o7700 & 0x0FFF) +             # mode3a
               struct.pack('>H', fl_raw) +                       # FL 350
               bytes([0x7C, 0x12, 0x34]))                        # mode_s
        r = self._decode(rec)
        assert r[0]['sac'] == 226
        assert r[0]['timestamp'] == pytest.approx(43200.0, abs=0.01)
        assert r[0]['raw_range'] == pytest.approx(120.5, abs=0.01)
        assert r[0]['raw_azimuth'] == pytest.approx(315.0, abs=0.02)
        assert r[0]['mode_s'] == '7C1234'
        assert r[0]['flight_level'] == pytest.approx(350.0, abs=0.5)

    def test_dos_plots_consecutivos(self):
        r1 = fspec(1, 4) + bytes([1, 1]) + rho_bytes(50.0) + theta_bytes(0.0)
        r2 = fspec(1, 4) + bytes([1, 2]) + rho_bytes(100.0) + theta_bytes(180.0)
        r = self._decode(r1 + r2)
        assert len(r) == 2
        assert r[0]['raw_range'] == pytest.approx(50.0, abs=0.01)
        assert r[1]['raw_range'] == pytest.approx(100.0, abs=0.01)

    # ── Robustez ──────────────────────────────────────────────────────────────

    def test_payload_vacio_no_falla(self):
        assert self._decode(b'') == []

    def test_payload_truncado_no_falla(self):
        rec = fspec(1, 4) + bytes([1, 1]) + bytes([0x64])  # faltan 3 bytes de rho/theta
        payload, off, bl = frame(48, rec)
        result = cat048.decode(payload, off, bl, 48)
        assert isinstance(result, list)

    def test_plot_solo_con_category_no_se_incluye(self):
        # FSPEC indica FRN que no existe → plot solo tiene 'category' → no se añade
        rec = fspec(1) + bytes([])  # fspec sin datos siguientes → loop aborta
        result = self._decode(rec)
        assert isinstance(result, list)


# ────────────────────────────────────────────────────────────────────────────
# CAT062 — SDPS System Track Messages
# ────────────────────────────────────────────────────────────────────────────

def _lat_bytes_62(lat_deg: float) -> bytes:
    """Latitud CAT062: 4 bytes signed, 180/2²⁵ °/LSB."""
    return struct.pack('>i', round(lat_deg * 33554432.0 / 180.0))


def _lon_bytes_62(lon_deg: float) -> bytes:
    return _lat_bytes_62(lon_deg)


class TestCat062:

    def _decode(self, records: bytes):
        payload, off, bl = frame(62, records)
        return cat062.decode(payload, off, bl, 62)

    # ── FRN1: SAC/SIC ────────────────────────────────────────────────────────

    def test_sac_sic(self):
        rec = fspec(1) + bytes([226, 210])
        r = self._decode(rec)
        assert r[0]['sac'] == 226 and r[0]['sic'] == 210

    # ── FRN4: ToD ────────────────────────────────────────────────────────────

    def test_timestamp(self):
        rec = fspec(1, 4) + bytes([1, 1]) + tod_bytes(7200.0)
        r = self._decode(rec)
        assert r[0]['timestamp'] == pytest.approx(7200.0, abs=0.01)

    # ── FRN5: Posición WGS-84 ────────────────────────────────────────────────

    def test_posicion_ecuatorial(self):
        rec = fspec(1, 5) + bytes([1, 1]) + bytes(8)
        r = self._decode(rec)
        assert r[0]['latitude'] == pytest.approx(0.0, abs=1e-4)
        assert r[0]['longitude'] == pytest.approx(0.0, abs=1e-4)
        assert r[0]['valid_position'] is True

    def test_posicion_hemisferio_norte(self):
        rec = fspec(1, 5) + bytes([1, 1]) + _lat_bytes_62(45.0) + _lon_bytes_62(90.0)
        r = self._decode(rec)
        assert r[0]['latitude'] == pytest.approx(45.0, abs=0.001)
        assert r[0]['longitude'] == pytest.approx(90.0, abs=0.001)

    def test_posicion_hemisferio_sur(self):
        rec = fspec(1, 5) + bytes([1, 1]) + _lat_bytes_62(-34.82) + _lon_bytes_62(-58.54)
        r = self._decode(rec)
        assert r[0]['latitude'] == pytest.approx(-34.82, abs=0.001)
        assert r[0]['longitude'] == pytest.approx(-58.54, abs=0.001)

    # ── FRN7: Velocidad cartesiana ────────────────────────────────────────────

    def test_velocidad_este(self):
        # vx=100 m/s (Este), vy=0 → GS=100 m/s, track_angle=90°
        vx_raw, vy_raw = round(100.0 / 0.25), 0
        rec = fspec(1, 7) + bytes([1, 1]) + struct.pack('>hh', vx_raw, vy_raw)
        r = self._decode(rec)
        gs_kts = math.sqrt(100.0**2) * 1.94384
        assert r[0]['extra_data']['ground_speed_kts'] == pytest.approx(gs_kts, abs=0.5)
        assert r[0]['extra_data']['track_angle'] == pytest.approx(90.0, abs=0.1)

    def test_velocidad_norte(self):
        # vx=0, vy=200 m/s → track_angle=0°
        rec = fspec(1, 7) + bytes([1, 1]) + struct.pack('>hh', 0, round(200.0 / 0.25))
        r = self._decode(rec)
        assert r[0]['extra_data']['track_angle'] == pytest.approx(0.0, abs=0.1)

    # ── FRN9: Mode 3/A ───────────────────────────────────────────────────────

    def test_mode3a(self):
        rec = fspec(1, 9) + bytes([1, 1]) + struct.pack('>H', 0o7700 & 0x0FFF)
        r = self._decode(rec)
        assert r[0]['mode_3a'] == 0o7700

    # ── FRN10: Target Identification ─────────────────────────────────────────

    def test_callsign(self):
        # 1 byte status + 6 bytes callsign ('AAAAAAAA')
        rec = fspec(1, 10) + bytes([1, 1]) + bytes([0x00]) + CALLSIGN_AAA_BYTES
        r = self._decode(rec)
        assert r[0]['callsign'] == 'AAAAAAAA'

    # ── FRN11: Aircraft Derived (ADR = Mode S address) ───────────────────────

    def test_mode_s_via_380_adr(self):
        # sub_fspec: ADR only (bit7 de la sub_fspec, sin FX) → [0x80] + 3 bytes address
        sub_fs = bytes([0x80])   # i=0 (ADR) present, FX=0
        adr_bytes = bytes([0x7C, 0x12, 0x34])
        rec = fspec(1, 11) + bytes([1, 1]) + sub_fs + adr_bytes
        r = self._decode(rec)
        assert r[0]['mode_s'] == '7C1234'

    # ── FRN12: Track Number ───────────────────────────────────────────────────

    def test_track_number(self):
        rec = fspec(1, 12) + bytes([1, 1]) + struct.pack('>H', 5678)
        r = self._decode(rec)
        assert r[0]['track_number'] == 5678

    # ── FRN17: Measured Flight Level ─────────────────────────────────────────

    def test_measured_fl(self):
        # FL=300 → fl_raw=1200 signed
        fl_raw = round(300.0 / 0.25)
        rec = fspec(1, 17) + bytes([1, 1]) + struct.pack('>h', fl_raw)
        r = self._decode(rec)
        assert r[0]['flight_level'] == pytest.approx(300.0, abs=0.1)

    def test_measured_fl_negativo(self):
        # FL=-10 (debajo del nivel del mar) → se almacena sin restricción (a diferencia de CAT048)
        fl_raw = round(-10.0 / 0.25)  # -40
        rec = fspec(1, 17) + bytes([1, 1]) + struct.pack('>h', fl_raw)
        r = self._decode(rec)
        assert r[0]['flight_level'] == pytest.approx(-10.0, abs=0.1)

    # ── FRN18: Geometric Altitude ─────────────────────────────────────────────

    def test_geometric_altitude(self):
        # alt=10000 ft → alt_raw=10000/6.25=1600
        alt_raw = round(10000.0 / 6.25)
        rec = fspec(1, 18) + bytes([1, 1]) + struct.pack('>h', alt_raw)
        r = self._decode(rec)
        assert r[0]['altitude'] == pytest.approx(10000.0, abs=1.0)

    # ── FRN3: Service ID ─────────────────────────────────────────────────────

    def test_service_id(self):
        rec = fspec(1, 3) + bytes([1, 1]) + bytes([42])
        r = self._decode(rec)
        assert r[0]['extra_data']['service_id'] == 42

    # ── Track completo con campos típicos de operación ────────────────────────

    def test_track_completo(self):
        rec = (fspec(1, 4, 5, 9, 12, 17) +
               bytes([226, 210]) +
               tod_bytes(50000.0) +
               _lat_bytes_62(-31.315) + _lon_bytes_62(-64.215) +
               struct.pack('>H', 0o2375 & 0x0FFF) +
               struct.pack('>H', 4321) +
               struct.pack('>h', round(350.0 / 0.25)))
        r = self._decode(rec)
        assert r[0]['sac'] == 226 and r[0]['sic'] == 210
        assert r[0]['timestamp'] == pytest.approx(50000.0, abs=0.01)
        assert r[0]['latitude'] == pytest.approx(-31.315, abs=0.001)
        assert r[0]['longitude'] == pytest.approx(-64.215, abs=0.001)
        assert r[0]['mode_3a'] == 0o2375
        assert r[0]['track_number'] == 4321
        assert r[0]['flight_level'] == pytest.approx(350.0, abs=0.5)

    def test_dos_tracks_consecutivos(self):
        t1 = fspec(1, 12) + bytes([1, 1]) + struct.pack('>H', 100)
        t2 = fspec(1, 12) + bytes([1, 1]) + struct.pack('>H', 200)
        r = self._decode(t1 + t2)
        assert len(r) == 2
        assert r[0]['track_number'] == 100
        assert r[1]['track_number'] == 200

    # ── Robustez ──────────────────────────────────────────────────────────────

    def test_payload_vacio_no_falla(self):
        assert self._decode(b'') == []

    def test_payload_truncado_no_falla(self):
        # FSPEC indica FRN5 (8 bytes) pero solo hay 4
        rec = fspec(1, 5) + bytes([1, 1]) + bytes(4)
        payload, off, bl = frame(62, rec)
        result = cat062.decode(payload, off, bl, 62)
        assert isinstance(result, list)
