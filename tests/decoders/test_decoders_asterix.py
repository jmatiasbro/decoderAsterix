"""Banco de pruebas de los decodificadores ASTERIX por categoría.

Cubre REQ-DEC-1..5 (CAT001, CAT002, CAT021, CAT034) —
funciones de núcleo SWAL 2 hasta ahora sin verificación automatizada.
Ver documentacion/certificacion/04_matriz_trazabilidad.md.

Cada test construye un payload binario mínimo y válido conforme a las
especificaciones EUROCONTROL (LSB, escalados, UAP) y verifica los campos
decodificados contra los oráculos calculados analíticamente.

Unidades de referencia:
- Rango: 1/256 NM/LSB  (CAT001 I001/040)
- Azimuth: 360/65536 °/LSB  (CAT001 I001/040)
- ToD: 1/128 s/LSB  (CAT001/002/034)
- FL/altitude: 1/4 FL/LSB  (CAT001 I001/090)
- Posición WGS-84 v2.4: 180/2²³ °/LSB  (3 bytes por coord, CAT021 I021/130)
- Posición WGS-84 v0.26: 180/2²⁵ °/LSB  (4 bytes por coord, CAT021 I021/130)
"""
import struct
import pytest

from decoder.decoders import cat001, cat002, cat034, cat021


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def fspec(*frns: int) -> bytes:
    """Construye bytes FSPEC con los FRNs activos, activando bits FX de extensión."""
    if not frns:
        return b'\x00'
    n_bytes = max(1, (max(frns) + 6) // 7)
    result = bytearray(n_bytes)
    for frn in frns:
        byte_idx = (frn - 1) // 7
        bit_pos = 7 - ((frn - 1) % 7)
        result[byte_idx] |= (1 << bit_pos)
    for i in range(n_bytes - 1):
        result[i] |= 0x01   # FX = extensión
    return bytes(result)


def frame(cat: int, records: bytes):
    """Construye un payload ASTERIX completo (header + records).
    Devuelve (payload, offset=3, block_length).
    """
    bl = 3 + len(records)
    hdr = bytes([cat, (bl >> 8) & 0xFF, bl & 0xFF])
    return hdr + records, 3, bl


def tod_bytes(seconds: float) -> bytes:
    """3 bytes de ToD a 1/128 s/LSB."""
    raw = int(seconds * 128)
    return struct.pack('>I', raw)[1:]   # big-endian, descartar byte más significativo


# ────────────────────────────────────────────────────────────────────────────
# CAT002 — Monoradar Service Messages
# ────────────────────────────────────────────────────────────────────────────

class TestCat002:

    def _decode(self, records: bytes):
        payload, off, bl = frame(2, records)
        return cat002.decode(payload, off, bl, 2)

    def test_north_mark_campos_basicos(self):
        # FRN1(SAC/SIC) + FRN2(msg_type) + FRN4(ToD)
        rec = fspec(1, 2, 4) + bytes([226, 210, 1]) + tod_bytes(3600.0)
        r = self._decode(rec)
        assert len(r) == 1
        assert r[0]['sac'] == 226 and r[0]['sic'] == 210
        assert r[0]['msg_type'] == 1
        assert r[0]['extra_data']['is_north_mark'] is True
        assert r[0]['timestamp'] == pytest.approx(3600.0, abs=0.01)

    def test_sector_change_azimuth(self):
        # FRN1 + FRN2(msg_type=2) + FRN3(sector_number)
        # sector_number=128 → azimuth = 128 * (360/256) = 180.0°
        rec = fspec(1, 2, 3) + bytes([1, 1, 2, 128])
        r = self._decode(rec)
        assert len(r) == 1
        assert r[0]['msg_type'] == 2
        assert r[0]['extra_data']['is_sector_change'] is True
        assert r[0]['sector_number'] == 128
        assert r[0]['azimuth'] == pytest.approx(180.0, abs=0.01)

    def test_rotation_period_y_rpm(self):
        # FRN5: ARP (2B). Período = 12.0 s → raw = 12 * 128 = 1536 = 0x0600
        # RPM = 60/12 = 5.0
        rec = fspec(1, 5) + bytes([226, 210]) + bytes([0x06, 0x00])
        r = self._decode(rec)
        assert r[0]['rotation_period'] == pytest.approx(12.0, abs=0.01)
        assert r[0]['extra_data']['antenna_rpm'] == pytest.approx(5.0, abs=0.01)

    def test_dos_registros_consecutivos(self):
        bloque = fspec(1, 2) + bytes([1, 1, 1])      # North mark
        bloque += fspec(1, 2) + bytes([1, 2, 2])     # Sector change
        r = self._decode(bloque)
        assert len(r) == 2
        assert r[0]['msg_type'] == 1
        assert r[1]['msg_type'] == 2

    def test_payload_vacio_no_falla(self):
        assert self._decode(b'') == []

    def test_payload_truncado_no_falla(self):
        rec = fspec(1, 2, 4) + bytes([226, 210, 1])  # falta ToD
        r = self._decode(rec)
        assert isinstance(r, list)     # no debe lanzar excepción


# ────────────────────────────────────────────────────────────────────────────
# CAT034 — Monoradar Service Messages (siguiente versión de CAT002)
# ────────────────────────────────────────────────────────────────────────────

class TestCat034:

    def _decode(self, records: bytes):
        payload, off, bl = frame(34, records)
        return cat034.decode(payload, off, bl, 34)

    def test_north_mark_campos_basicos(self):
        # FRN1(SAC/SIC) + FRN2(msg_type=1) + FRN3(ToD)
        # CAT034 ToD: 1/128 s/LSB (mismo que CAT002)
        rec = fspec(1, 2, 3) + bytes([226, 210, 1]) + tod_bytes(7200.0)
        r = self._decode(rec)
        assert len(r) == 1
        assert r[0]['sac'] == 226 and r[0]['sic'] == 210
        assert r[0]['msg_type'] == 1
        assert r[0]['extra_data']['is_north_mark'] is True
        assert r[0]['timestamp'] == pytest.approx(7200.0, abs=0.01)

    def test_sector_number_y_azimuth(self):
        # FRN4: sector_number → azimuth = sector * 1.40625 (360/256)
        # sector=64 → azimuth = 90.0°
        rec = fspec(1, 2, 3, 4) + bytes([1, 1, 1]) + tod_bytes(0.0) + bytes([64])
        r = self._decode(rec)
        assert r[0]['sector_number'] == 64
        assert r[0]['azimuth'] == pytest.approx(90.0, abs=0.01)

    def test_rotation_speed(self):
        # FRN5: 2B, período = 12.5 s → raw = int(12.5 / 0.0078125) = 1600 = 0x0640
        # RPM = 60/12.5 = 4.8
        raw = int(12.5 / 0.0078125)   # 1600
        rec = fspec(1, 5) + bytes([1, 1]) + struct.pack('>H', raw)
        r = self._decode(rec)
        assert r[0]['rotation_period'] == pytest.approx(12.5, abs=0.01)
        assert r[0]['extra_data']['antenna_rpm'] == pytest.approx(4.8, abs=0.01)

    def test_sistema_nogo(self):
        # FRN6: I034/050 compound. Primary=0x80 (has_COM, no FX), COM=0x80 (NOGO=1)
        rec = fspec(1, 2, 3, 6) + bytes([226, 210, 1]) + tod_bytes(0.0) + bytes([0x80, 0x80])
        r = self._decode(rec)
        assert r[0]['sys_nogo'] is True

    def test_sistema_ok_no_nogo(self):
        # COM=0x00: todos los flags en False
        rec = fspec(1, 2, 3, 6) + bytes([226, 210, 1]) + tod_bytes(0.0) + bytes([0x80, 0x00])
        r = self._decode(rec)
        assert r[0]['sys_nogo'] is False
        assert r[0]['time_invalid'] is False

    def test_payload_vacio_no_falla(self):
        assert self._decode(b'') == []

    def test_payload_truncado_no_falla(self):
        rec = fspec(1, 2, 3) + bytes([226, 210])   # falta msg_type y ToD
        r = self._decode(rec)
        assert isinstance(r, list)


# ────────────────────────────────────────────────────────────────────────────
# CAT001 — Monoradar Target Reports
# ────────────────────────────────────────────────────────────────────────────

def _rho_bytes(range_nm: float) -> bytes:
    """Rango en NM → 2 bytes big-endian (1/256 NM/LSB)."""
    return struct.pack('>H', round(range_nm * 256))


def _theta_bytes(azimuth_deg: float) -> bytes:
    """Azimuth en grados → 2 bytes big-endian (360/65536 °/LSB)."""
    return struct.pack('>H', round(azimuth_deg * 65536 / 360))


def _fl_bytes(fl: float) -> bytes:
    """Flight Level → 2 bytes (1/4 FL/LSB, bit14=garbled, bit13=signo)."""
    fl_14bit = round(fl / 0.25)
    if fl_14bit < 0:
        fl_14bit += 0x4000      # representación complemento en 14 bits
    return struct.pack('>H', fl_14bit & 0x3FFF)


class TestCat001Plot:

    def _decode(self, records: bytes):
        payload, off, bl = frame(1, records)
        return cat001.decode(payload, off, bl, 1)

    def _plot_record(self, *, sac=226, sic=210, typ_byte=0x40,
                     range_nm=None, az_deg=None, m3a=None, fl=None):
        """Construye registros de bytes para un plot CAT001."""
        frns = [1, 2]
        data = bytes([sac, sic, typ_byte])
        if range_nm is not None and az_deg is not None:
            frns.append(3)
            data += _rho_bytes(range_nm) + _theta_bytes(az_deg)
        if m3a is not None:
            frns.append(4)
            data += struct.pack('>H', m3a & 0x0FFF)
        if fl is not None:
            frns.append(5)
            data += _fl_bytes(fl)
        return fspec(*frns) + data

    def test_plot_sac_sic_y_tipo(self):
        rec = self._plot_record(sac=226, sic=210, typ_byte=0x40)
        r = self._decode(rec)
        assert len(r) == 1
        assert r[0]['sac'] == 226 and r[0]['sic'] == 210
        assert r[0]['type'] == 'plot'

    def test_rango_azimut_formula(self):
        # range=100 NM, azimuth=90° → verificar conversión LSB exacta
        rec = self._plot_record(range_nm=100.0, az_deg=90.0)
        r = self._decode(rec)
        assert r[0]['raw_range'] == pytest.approx(100.0, abs=0.01)
        assert r[0]['raw_azimuth'] == pytest.approx(90.0, abs=0.01)

    def test_rango_azimut_norte(self):
        rec = self._plot_record(range_nm=50.0, az_deg=0.0)
        r = self._decode(rec)
        assert r[0]['raw_range'] == pytest.approx(50.0, abs=0.01)
        assert r[0]['raw_azimuth'] == pytest.approx(0.0, abs=0.01)

    def test_mode3a_decodificado(self):
        # mode3a octal 1234 = decimal 668
        rec = self._plot_record(m3a=0o1234)
        r = self._decode(rec)
        assert r[0]['mode3a'] == '1234'

    def test_mode3a_7000(self):
        rec = self._plot_record(m3a=0o7000)
        r = self._decode(rec)
        assert r[0]['mode3a'] == '7000'

    def test_altitud_positiva(self):
        # FL100 → altitude=10000 ft
        rec = self._plot_record(fl=100.0)
        r = self._decode(rec)
        assert r[0]['flight_level'] == pytest.approx(100.0, abs=0.1)
        assert r[0]['altitude'] == pytest.approx(10000.0, abs=10)

    def test_altitud_negativa(self):
        # FL-10 (underground, below MSL) → altitude=-1000 ft
        rec = self._plot_record(fl=-10.0)
        r = self._decode(rec)
        assert r[0]['flight_level'] == pytest.approx(-10.0, abs=0.1)
        assert r[0]['altitude'] == pytest.approx(-1000.0, abs=10)

    def test_altitud_garbled_flag(self):
        # bit14=1 → garbled=True
        raw_garbled = 0x4190   # bit14 set, 0x0190=400 (FL100)
        rec = fspec(1, 2, 5) + bytes([226, 210, 0x40]) + struct.pack('>H', raw_garbled)
        r = self._decode(rec)
        assert r[0].get('garbled') is True

    def test_todos_campos_juntos(self):
        rec = self._plot_record(range_nm=75.5, az_deg=135.0, m3a=0o2375, fl=250.0)
        r = self._decode(rec)
        assert r[0]['raw_range'] == pytest.approx(75.5, abs=0.01)
        assert r[0]['raw_azimuth'] == pytest.approx(135.0, abs=0.02)
        assert r[0]['mode3a'] == '2375'
        assert r[0]['flight_level'] == pytest.approx(250.0, abs=0.1)

    def test_dos_plots_consecutivos(self):
        r1 = self._plot_record(range_nm=100.0, az_deg=0.0, m3a=0o1234)
        r2 = self._plot_record(range_nm=50.0, az_deg=180.0, m3a=0o7000)
        r = self._decode(r1 + r2)
        assert len(r) == 2
        assert r[0]['raw_range'] == pytest.approx(100.0, abs=0.01)
        assert r[1]['raw_range'] == pytest.approx(50.0, abs=0.01)

    def test_payload_vacio_no_falla(self):
        payload, off, bl = frame(1, b'')
        assert cat001.decode(payload, off, bl, 1) == []

    def test_payload_truncado_no_falla(self):
        # FSPEC indica FRN3 (4 bytes) pero solo hay 2 bytes de datos → no cuelga
        rec = fspec(1, 2, 3) + bytes([226, 210, 0x40, 0x64])  # faltan 2 bytes de rho/theta
        payload, off, bl = frame(1, rec)
        result = cat001.decode(payload, off, bl, 1)
        assert isinstance(result, list)


class TestCat001Track:

    def _decode(self, records: bytes):
        payload, off, bl = frame(1, records)
        return cat001.decode(payload, off, bl, 1)

    def test_track_detectado_por_typ(self):
        # I001/020 TYP=4 (SSR track): byte = (4 << 5) = 0x80
        rec = fspec(1, 2) + bytes([226, 210, 0x80])
        r = self._decode(rec)
        assert r[0]['type'] == 'track'

    def test_track_number(self):
        # FRN3 en track UAP = I001/161 Track Number (2B)
        # track_number = 1234
        rec = fspec(1, 2, 3) + bytes([226, 210, 0x80]) + struct.pack('>H', 1234)
        r = self._decode(rec)
        assert r[0]['track_number'] == 1234

    def test_track_posicion_medida(self):
        # FRN4 en track UAP = I001/040 Measured Position (4B)
        rec = (fspec(1, 2, 4) + bytes([226, 210, 0x80])
               + _rho_bytes(80.0) + _theta_bytes(270.0))
        r = self._decode(rec)
        assert r[0]['type'] == 'track'
        assert r[0]['raw_range'] == pytest.approx(80.0, abs=0.01)
        assert r[0]['raw_azimuth'] == pytest.approx(270.0, abs=0.02)

    def test_track_altitud(self):
        # FRN8 en track UAP = I001/090 Mode-C
        rec = fspec(1, 2, 8) + bytes([226, 210, 0x80]) + _fl_bytes(350.0)
        r = self._decode(rec)
        assert r[0]['type'] == 'track'
        assert r[0]['flight_level'] == pytest.approx(350.0, abs=0.5)

    def test_plot_no_confunde_con_track(self):
        # TYP=2 (PSR plot): 0x40 → type=='plot', no 'track'
        rec = fspec(1, 2) + bytes([226, 210, 0x40])
        r = self._decode(rec)
        assert r[0]['type'] == 'plot'


# ────────────────────────────────────────────────────────────────────────────
# CAT021 — ADS-B
# ────────────────────────────────────────────────────────────────────────────

def _lat_bytes_v24(lat_deg: float) -> bytes:
    """Latitud → 3 bytes big-endian signed (180/2²³ °/LSB, CAT021 v2.4)."""
    raw = round(lat_deg * (2**23) / 180.0)
    return struct.pack('>i', raw)[1:]   # descartamos el byte más significativo


def _lon_bytes_v24(lon_deg: float) -> bytes:
    return _lat_bytes_v24(lon_deg)      # mismo escalado


def _lat_bytes_v026(lat_deg: float) -> bytes:
    """Latitud → 4 bytes big-endian signed (180/2²⁵ °/LSB, CAT021 v0.26)."""
    raw = round(lat_deg * (2**25) / 180.0)
    return struct.pack('>i', raw)


def _fl_bytes_v21(fl: float) -> bytes:
    """Flight Level → 2 bytes signed big-endian (1/4 FL/LSB, CAT021)."""
    return struct.pack('>h', round(fl / 0.25))


class TestCat021V24:
    """CAT021 edición 2.4 (SAC≠226 o SIC≠103)."""

    def _decode(self, records: bytes):
        payload, off, bl = frame(21, records)
        return cat021.decode(payload, off, bl, 21)

    def test_sac_sic(self):
        # FRN1 (2B). SAC=1, SIC=2 → no activa la ruta v0.26
        rec = fspec(1) + bytes([1, 2])
        r = self._decode(rec)
        assert r[0]['sac'] == 1 and r[0]['sic'] == 2

    def test_posicion_ecuatorial(self):
        # FRN6 (I021/130): lat=0, lon=0 (caso base, tres bytes a cero)
        rec = fspec(1, 6) + bytes([1, 2]) + bytes(6)
        r = self._decode(rec)
        assert r[0]['latitude'] == pytest.approx(0.0, abs=1e-4)
        assert r[0]['longitude'] == pytest.approx(0.0, abs=1e-4)

    def test_posicion_no_trivial(self):
        # lat=45.0, lon=90.0 — valores con representación entera exacta
        rec = (fspec(1, 6) + bytes([1, 2])
               + _lat_bytes_v24(45.0) + _lon_bytes_v24(90.0))
        r = self._decode(rec)
        assert r[0]['latitude'] == pytest.approx(45.0, abs=0.001)
        assert r[0]['longitude'] == pytest.approx(90.0, abs=0.001)

    def test_posicion_hemisferio_sur(self):
        rec = (fspec(1, 6) + bytes([1, 2])
               + _lat_bytes_v24(-34.82) + _lon_bytes_v24(-58.54))
        r = self._decode(rec)
        assert r[0]['latitude'] == pytest.approx(-34.82, abs=0.001)
        assert r[0]['longitude'] == pytest.approx(-58.54, abs=0.001)

    def test_target_address_mode_s(self):
        # FRN11 (I021/080): 3 bytes → hex uppercase
        rec = fspec(1, 11) + bytes([1, 2]) + bytes([0x7C, 0x12, 0x34])
        r = self._decode(rec)
        assert r[0]['mode_s'] == '7C1234'

    def test_flight_level(self):
        # FRN21 (I021/145): 2B signed. FL150 → 600 → [0x02, 0x58]
        rec = fspec(1, 21) + bytes([1, 2]) + _fl_bytes_v21(150.0)
        r = self._decode(rec)
        assert r[0]['flight_level'] == pytest.approx(150.0, abs=0.1)

    def test_flight_level_no_decodifica_invalido(self):
        # fl_raw = -32768 (0x8000) → valor reservado "no disponible"
        rec = fspec(1, 21) + bytes([1, 2]) + struct.pack('>h', -32768)
        r = self._decode(rec)
        assert 'flight_level' not in r[0]

    def test_flight_level_negativo_se_omite(self):
        # FL-5 < 0.0 → no se guarda
        rec = fspec(1, 21) + bytes([1, 2]) + _fl_bytes_v21(-5.0)
        r = self._decode(rec)
        assert 'flight_level' not in r[0]

    def test_modo3a(self):
        # FRN19 (I021/070): 2B. mode3a = 0o7700
        raw = 0o7700 & 0x0FFF
        rec = fspec(1, 19) + bytes([1, 2]) + struct.pack('>H', raw)
        r = self._decode(rec)
        assert r[0]['mode_3a'] == 0o7700

    def test_payload_vacio_no_falla(self):
        payload, off, bl = frame(21, b'')
        assert cat021.decode(payload, off, bl, 21) == []

    def test_payload_truncado_no_falla(self):
        # FSPEC indica FRN6 (6 bytes) pero solo hay 3
        rec = fspec(1, 6) + bytes([1, 2]) + bytes([0x20, 0x00, 0x00])
        payload, off, bl = frame(21, rec)
        result = cat021.decode(payload, off, bl, 21)
        assert isinstance(result, list)


class TestCat021V026:
    """CAT021 v0.26 (Paraná SAC=226, SIC=103) — ruta de decodificación heredada."""

    SAC, SIC = 226, 103

    def _decode(self, records: bytes):
        payload, off, bl = frame(21, records)
        return cat021.decode(payload, off, bl, 21)

    def test_deteccion_version_v026(self):
        # SAC=226, SIC=103 → activa decode_cat021_v026; posición usa 4+4 bytes
        rec = (fspec(1, 4, 5) + bytes([self.SAC, self.SIC])
               + _lat_bytes_v026(0.0) + _lat_bytes_v026(0.0)
               + bytes([0x7C, 0x12, 0x34]))
        r = self._decode(rec)
        assert r[0]['sac'] == 226 and r[0]['sic'] == 103

    def test_posicion_wgs84_v026_escalado(self):
        # v0.26: 4 bytes por coord, 180/2²⁵ °/LSB
        rec = (fspec(1, 4) + bytes([self.SAC, self.SIC])
               + _lat_bytes_v026(-31.315) + _lat_bytes_v026(-64.215))
        r = self._decode(rec)
        assert r[0]['latitude'] == pytest.approx(-31.315, abs=0.001)
        assert r[0]['longitude'] == pytest.approx(-64.215, abs=0.001)

    def test_mode_s_v026(self):
        rec = (fspec(1, 5) + bytes([self.SAC, self.SIC])
               + bytes([0xAB, 0xCD, 0xEF]))
        r = self._decode(rec)
        assert r[0]['mode_s'] == 'ABCDEF'

    def test_timestamp_v026(self):
        # FRN3: ToD a 1/128 s/LSB
        rec = fspec(1, 3) + bytes([self.SAC, self.SIC]) + tod_bytes(1800.0)
        r = self._decode(rec)
        assert r[0]['timestamp'] == pytest.approx(1800.0, abs=0.01)

    def test_v24_no_usa_ruta_v026(self):
        # SAC=1 (≠226) → escoge decodificador v2.4
        rec = (fspec(1, 6) + bytes([1, 2])
               + _lat_bytes_v24(45.0) + _lon_bytes_v24(90.0))
        r = self._decode(rec)
        # v2.4 usa 3+3 bytes, v0.26 usaría 4+4 → si el escalado es correcto
        # sabemos que tomó la ruta v2.4 porque lat≈45.0 y no un valor extraño
        assert r[0]['latitude'] == pytest.approx(45.0, abs=0.5)
