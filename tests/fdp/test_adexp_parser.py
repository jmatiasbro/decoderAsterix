"""Tests del parser ADEXP (decoder/adexp_parser.py).

Tramas basadas en EUROCONTROL SPEC-107 Ed. 3.3, Annex E/F.
"""
import pytest
from decoder.adexp_parser import parsear_trama

# ---------------------------------------------------------------------------
# Tramas de ejemplo
# ---------------------------------------------------------------------------

TRAMA_FPL = """\
-TITLE IFPL
-ADEP EDDF
-ADES LGTS
-ARCID KIM1
-ARCTYP B738
-WKTRC M
-EOBT 0715
-RFL F330
-ROUTE N0417F330 ANEKI8L ANEKI Y163 NATOR UN850 TRA UP131 RESIA Q333 BABAG UN606 PEVAL DCT PETAK UL607 PINDO UM603 EDASI
-ALTRNT1 LBSF
"""

TRAMA_FPL_EQPT = """\
-TITLE IFPL
-ARCID TEST1
-ADEP EDDM
-ADES LEMD
-ARCTYP B737
-EQPT B737/M-SDE1FGHIRWXY
-EOBT 1200
-RFL F350
-ROUTE N0440F350 DCT LAMSO
"""

TRAMA_CHG = """\
-TITLE CHG
-ARCID KIM1
-RFL F350
-ADES LFPG
"""

TRAMA_CNL = """\
-TITLE CNL
-ARCID KIM1
"""

TRAMA_EST = """\
-TITLE EST
-ARCID AMC101
-ADEP EGLL
-ADES LMML
-EOBT 0945
-RFL F350
-COP BNE
"""

TRAMA_CON_LISTA = """\
-TITLE IFPL
-ARCID KIM1
-ADEP EDDF
-ADES LGTS
-ARCTYP B738
-WKTRC M
-EOBT 0715
-RFL F330
-ROUTE N0417F330 ANEKI8L ANEKI Y163 NATOR UN850 TRA
-BEGIN RTEPTS
-PT -PTID EDDF -FL F004 -ETO 170729073000
-PT -PTID NATOR -FL F330 -ETO 170729074911
-PT -PTID LGTS -FL F000 -ETO 170729095713
-END RTEPTS
-ALTRNT1 LBSF
"""

# ---------------------------------------------------------------------------
# Tests FPL
# ---------------------------------------------------------------------------

def test_fpl_campos_basicos():
    d = parsear_trama(TRAMA_FPL)
    assert d["TITLE"] == "IFPL"
    assert d["ARCID"] == "KIM1"
    assert d["ADEP"] == "EDDF"
    assert d["ADES"] == "LGTS"
    assert d["EOBT"] == "0715"
    assert d["RFL"] == "F330"


def test_fpl_ruta_completa():
    d = parsear_trama(TRAMA_FPL)
    assert "N0417F330" in d["ROUTE"]
    assert "ANEKI" in d["ROUTE"]
    assert "DCT" in d["ROUTE"]
    assert "EDASI" in d["ROUTE"]


def test_fpl_aircraft_type_desde_arctyp():
    d = parsear_trama(TRAMA_FPL)
    assert d["aircraft_type"] == "B738"
    assert d["wtc"] == "M"


def test_fpl_eqpt_parsea_type_y_wtc():
    d = parsear_trama(TRAMA_FPL_EQPT)
    # EQPT = B737/M-SDE1FGHIRWXY → type=B737, wtc=M
    assert d["aircraft_type"] == "B737"
    assert d["wtc"] == "M"


def test_fpl_eqpt_no_pisa_arctyp():
    """EQPT como fuente primaria; ARCTYP solo como fallback."""
    d = parsear_trama(TRAMA_FPL_EQPT)
    assert d["aircraft_type"] == "B737"   # viene de EQPT, no de ARCTYP

# ---------------------------------------------------------------------------
# Tests CHG
# ---------------------------------------------------------------------------

def test_chg_titulo_y_arcid():
    d = parsear_trama(TRAMA_CHG)
    assert d["TITLE"] == "CHG"
    assert d["ARCID"] == "KIM1"


def test_chg_solo_campos_presentes():
    d = parsear_trama(TRAMA_CHG)
    assert d["RFL"] == "F350"
    assert d["ADES"] == "LFPG"
    assert "ADEP" not in d   # CHG parcial, no trae ADEP

# ---------------------------------------------------------------------------
# Tests CNL
# ---------------------------------------------------------------------------

def test_cnl_minimo():
    d = parsear_trama(TRAMA_CNL)
    assert d["TITLE"] == "CNL"
    assert d["ARCID"] == "KIM1"


def test_cnl_sin_ruta():
    d = parsear_trama(TRAMA_CNL)
    assert "ROUTE" not in d
    assert "RFL" not in d

# ---------------------------------------------------------------------------
# Tests EST
# ---------------------------------------------------------------------------

def test_est_cop():
    d = parsear_trama(TRAMA_EST)
    assert d["TITLE"] == "EST"
    assert d["COP"] == "BNE"
    assert d["ARCID"] == "AMC101"

# ---------------------------------------------------------------------------
# Tests campo lista (BEGIN/END)
# ---------------------------------------------------------------------------

def test_lista_rtepts_guardada():
    d = parsear_trama(TRAMA_CON_LISTA)
    assert "_LIST_RTEPTS" in d
    assert "EDDF" in d["_LIST_RTEPTS"]
    assert "LGTS" in d["_LIST_RTEPTS"]


def test_lista_no_contamina_campos():
    """Keywords dentro de BEGIN/END no deben aparecer como campos raíz."""
    d = parsear_trama(TRAMA_CON_LISTA)
    # PT, PTID, FL, ETO son keywords internos a RTEPTS
    assert "PT" not in d
    assert "PTID" not in d
    assert "ETO" not in d


def test_campos_despues_de_lista():
    """Campos tras -END RTEPTS deben parsearse correctamente."""
    d = parsear_trama(TRAMA_CON_LISTA)
    assert d["ARCID"] == "KIM1"
    assert d["ROUTE"] == "N0417F330 ANEKI8L ANEKI Y163 NATOR UN850 TRA"
    assert d.get("ALTRNT1") == "LBSF"

# ---------------------------------------------------------------------------
# Tests robustez
# ---------------------------------------------------------------------------

def test_trama_vacia():
    d = parsear_trama("")
    assert d == {}


def test_crlf_normalizado():
    trama = "-TITLE FPL\r\n-ARCID IBE123\r\n-ADEP LEMD\r\n-ADES LEBL\r\n"
    d = parsear_trama(trama)
    assert d["TITLE"] == "FPL"
    assert d["ARCID"] == "IBE123"
    assert d["ADEP"] == "LEMD"


def test_valor_con_espacios_multiples():
    trama = "-TITLE IFPL\n-ARCID   KIM1\n-ADEP  EDDF\n"
    d = parsear_trama(trama)
    assert d["ARCID"] == "KIM1"
    assert d["ADEP"] == "EDDF"
