import unittest
import os
import struct
from io_tools import load_pcap

class TestPCAPLoader(unittest.TestCase):
    """
    Suite de pruebas para validar la resiliencia del cargador de archivos PCAP.
    Se generan archivos binarios al vuelo para simular distintas capturas de red.
    """
    
    def setUp(self):
        self.test_file = "test_dummy_capture.pcap"
        
    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
            
    def create_pcap(self, link_type, payload):
        """
        Crea un archivo PCAP sintético clásico.
        link_type: 1 para Ethernet, 113 para Linux SLL, 228 para Raw IPv4
        """
        # Global Header
        # Magic, Major, Minor, thiszone, sigfigs, snaplen, network
        header = struct.pack("<IHHIIII", 0xa1b2c3d4, 2, 4, 0, 0, 65535, link_type)
        
        # Packet Header
        # ts_sec, ts_usec, incl_len, orig_len
        pkt_header = struct.pack("<IIII", 1000000000, 0, len(payload), len(payload))
        
        with open(self.test_file, 'wb') as f:
            f.write(header + pkt_header + payload)
            
    def test_load_ethernet(self):
        # DLT_EN10MB (1)
        # 14 bytes Ethernet + 20 bytes IP + 8 bytes UDP + Payload
        eth_header = b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x08\x00'
        ip_header = b'\x45\x00\x00\x1c\x00\x00\x00\x00\x40\x11\x00\x00\x7f\x00\x00\x01\x7f\x00\x00\x01'
        udp_header = b'\x04\xd2\x04\xd2\x00\x08\x00\x00'
        data = b'\x30\x00\x07\x00ASTERIX'
        
        self.create_pcap(1, eth_header + ip_header + udp_header + data)
        res = load_pcap(self.test_file)
        self.assertEqual(res, data, "No se pudo extraer la carga ASTERIX sobre Ethernet")
        
    def test_load_linux_sll(self):
        # DLT_LINUX_SLL (113)
        # 16 bytes SLL + 20 bytes IP + 8 bytes UDP + Payload
        sll_header = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\x00'
        ip_header = b'\x45\x00\x00\x1c\x00\x00\x00\x00\x40\x11\x00\x00\x7f\x00\x00\x01\x7f\x00\x00\x01'
        udp_header = b'\x04\xd2\x04\xd2\x00\x08\x00\x00'
        data = b'\x30\x00\x07\x00ASTERIX_SLL'
        
        self.create_pcap(113, sll_header + ip_header + udp_header + data)
        res = load_pcap(self.test_file)
        self.assertEqual(res, data, "No se pudo extraer la carga ASTERIX sobre Linux SLL")
        
    def test_load_raw_ip(self):
        # DLT_RAW (228) - Sin capa 2 (Común en VPNs o capturas en interfaces loopback crudas)
        # Solo 20 bytes IP + 8 bytes UDP + Payload
        ip_header = b'\x45\x00\x00\x1c\x00\x00\x00\x00\x40\x11\x00\x00\x7f\x00\x00\x01\x7f\x00\x00\x01'
        udp_header = b'\x04\xd2\x04\xd2\x00\x08\x00\x00'
        data = b'\x30\x00\x07\x00ASTERIX_RAW'
        
        self.create_pcap(228, ip_header + udp_header + data)
        res = load_pcap(self.test_file)
        self.assertEqual(res, data, "No se pudo extraer la carga ASTERIX sobre Raw IP")

    def test_corrupted_pcap_handled_gracefully(self):
        # Test para un archivo vacío o corrupto
        with open(self.test_file, 'wb') as f:
            f.write(b'GARBAGE_DATA_NOT_PCAP')
        res = load_pcap(self.test_file)
        self.assertEqual(res, b'', "Debe retornar bytes vacíos sin romper la aplicación")

if __name__ == '__main__':
    unittest.main(verbosity=2)