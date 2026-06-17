from utils.geo import obtener_centros_control

test_cases = [
    # (name, sac, sic, expected_accs)
    ("Radar Bahía Blanca", 226, 206, ["Comodoro", "Ezeiza"]),
    ("ADS-B Bahía Blanca", 226, 106, ["Comodoro", "Ezeiza"]),
    ("Radar Bariloche", 226, 204, ["Comodoro", "Ezeiza"]),
    ("Radar Comodoro Rivadavia", 226, 240, ["Comodoro"]),
    ("Radar Córdoba", 226, 210, ["Córdoba", "Ezeiza", "Mendoza"]),
    ("Radar Corrientes", 226, 230, ["Córdoba", "Resistencia"]),
    ("Radar Esquel", 226, 242, ["Comodoro", "Ezeiza"]),
    ("Radar La Rioja", 226, 212, ["Córdoba", "Mendoza"]),
    ("Radar Malargüe", 226, 222, ["Ezeiza", "Mendoza"]),
    ("Radar Morteros", 226, 213, ["Córdoba", "Ezeiza", "Resistencia"]),
    ("Radar Neuquén", 226, 207, ["Comodoro", "Córdoba", "Ezeiza", "Mendoza"]),
    ("Radar Pehuajó", 226, 209, ["Ezeiza", "Mendoza"]),
    ("Radar Posadas", 226, 231, ["Resistencia"]),
    ("Radar Puerto Madryn", 226, 243, ["Comodoro"]),
    ("Radar Quilmes", 226, 205, ["Córdoba", "Ezeiza"]),
    ("Radar Río Gallegos", 226, 241, ["Comodoro"]),
    ("Radar Saenz Peña", 226, 232, ["Córdoba", "Ezeiza", "Resistencia"]),
    ("Radar Salta", 226, 214, ["Córdoba", "Resistencia"]),
    ("Radar San Luis", 226, 221, ["Córdoba", "Ezeiza", "Mendoza"]),
    ("Radar Santa Rosa", 226, 208, ["Córdoba", "Ezeiza", "Mendoza"]),
    ("Radar Tucumán", 226, 211, ["Córdoba", "Resistencia"]),
    ("Radar Ushuaia", 226, 245, ["Comodoro"]),
    # Paraná
    ("Radar Parana", 226, 203, ["Córdoba", "Ezeiza", "Resistencia"]),
    ("ADS-B Parana", 226, 103, ["Córdoba", "Ezeiza", "Resistencia"]),
    # Mendoza
    ("Radar Mendoza", 153, 6, ["Córdoba", "Mendoza"]),
    # Test text configs or edge cases
    ("bahiablanca", None, None, ["Comodoro", "Ezeiza"]),
    ("mamboreta", None, None, ["Córdoba", "Ezeiza", "Resistencia"]),
    ("ezeiza", None, None, ["Ezeiza"]),
]

failures = 0
for name, sac, sic, expected in test_cases:
    result = obtener_centros_control(name, sac, sic)
    # Check if sets are equal
    if set(result) != set(expected):
        print(f"FAIL: '{name}' ({sac}/{sic}) -> Got: {result}, Expected: {expected}")
        failures += 1
    else:
        print(f"OK  : '{name}' ({sac}/{sic}) -> {result}")

if failures == 0:
    print("\n[OK] ALL TESTS PASSED SUCCESSFULLY!")
else:
    print(f"\n[FAIL] {failures} TESTS FAILED.")
