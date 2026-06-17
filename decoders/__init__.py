"""
Módulo de decodificadores ASTERIX por categoría.

Cada archivo implementa una función `decode_catXXX` que procesa un payload
de bytes para una categoría específica y retorna una lista de registros decodificados.
"""
from .cat001 import decode as decode_cat001
from .cat021 import decode as decode_cat021
from .cat048 import decode as decode_cat048
from .cat062 import decode as decode_cat062

__all__ = ["decode_cat001", "decode_cat021", "decode_cat048", "decode_cat062"]
