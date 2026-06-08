"""
decoder — Librería pura de decodificación ASTERIX (sin dependencias Qt)
======================================================================
Soporta categorías: CAT 001, 002, 021, 034, 048, 062
"""
from .data_engine import DataEngine, AsterixPlot, SystemTrack
from .asterix_router import AsterixRouter
from .native_asterix import parse_payload
