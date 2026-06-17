from io_tools import load_pcap
from native_asterix import parse_payload
import sys

data = load_pcap("Martescordoba_radar2.pcap")
print(f"Loaded {len(data)} bytes")
# this is wrong, load_pcap might return raw bytes but parse_payload expects a single packet. Wait, load_pcap returns concatenated payload?
