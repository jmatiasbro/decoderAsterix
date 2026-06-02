import os
import time
import struct
import tarfile
from typing import Optional

try:
    import dpkt
except ImportError:
    dpkt = None

def load_pcap(file_path: str, gui_progress_callback: Optional[callable] = None) -> bytes:
    """Extrae datos ASTERIX de un archivo PCAP sin estado de clase asociado."""
    if not dpkt:
        raise ImportError("El módulo 'dpkt' no está instalado. Ejecute: pip install dpkt")
        
    file_size = os.path.getsize(file_path)
    asterix_data = bytearray()
    last_update_time = time.time()
    
    with open(file_path, 'rb') as f:
        try:
            pcap = dpkt.pcap.Reader(f)
        except ValueError:
            # Si falla como PCAP clásico, intentar leer como la versión moderna PCAPNG
            f.seek(0)
            pcap = dpkt.pcapng.Reader(f)
            
        for timestamp, buf in pcap:
            try:
                eth = dpkt.ethernet.Ethernet(buf)
                ip_pkt = eth.data
                
                # Si la capa 2 no es Ethernet (ej. captura en interfaz "any" / Linux Cooked Capture SLL)
                if not isinstance(ip_pkt, dpkt.ip.IP):
                    try:
                        sll = dpkt.sll.SLL(buf)
                        ip_pkt = sll.data
                    except Exception:
                        pass
                        
                if isinstance(ip_pkt, dpkt.ip.IP) and isinstance(ip_pkt.data, dpkt.udp.UDP):
                    # Depuración: Descomentar para ver paquetes UDP detectados
                    # print(f"Paquete detectado: IP {dpkt.utils.inet_to_str(ip_pkt.src)}:{ip_pkt.data.sport} -> {dpkt.utils.inet_to_str(ip_pkt.dst)}:{ip_pkt.data.dport}")
                    udp_payload = ip_pkt.data.data
                    # No asume puerto fijo, solo busca paquetes UDP con carga útil > 10 bytes
                    if len(udp_payload) > 10:
                        asterix_data.extend(ip_pkt.data.data)
            except Exception:
                continue
                
            now = time.time()
            if now - last_update_time > 0.1 and gui_progress_callback:
                gui_progress_callback(f.tell(), file_size, prefix='Cargando PCAP:', suffix='Completado')
                time.sleep(0.001)  # Ceder el GIL a la GUI
                last_update_time = now
                
    if gui_progress_callback:
        gui_progress_callback(file_size, file_size, prefix='Cargando PCAP:', suffix='Completado')
        
    return bytes(asterix_data)

def export_forensic_log(data_bytes: bytes, filename: str):
    """Exporta logs decodificados con prefijo aircon_saco- en formato comprimido."""
    prefixed_name = f"aircon_saco-{filename}.tar.gz"
    with tarfile.open(prefixed_name, "w:gz") as tar:
        import io
        info = tarfile.TarInfo(name=filename)
        info.size = len(data_bytes)
        tar.addfile(info, io.BytesIO(data_bytes))
    return prefixed_name

def load_ast(file_path: str) -> bytes:
    """Carga datos de un archivo AST en crudo."""
    with open(file_path, 'rb') as f:
        return f.read()
