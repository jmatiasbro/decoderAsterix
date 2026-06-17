import pypdf

pdf_path = r"c:\documentos\decode_asterix\PASS\0105500000000IT17_A0_IT #21.pdf"
reader = pypdf.PdfReader(pdf_path)

# Buscar páginas que contengan "Apéndice B" o "B. PERFORMANCE" o similar
found_pages = []
for idx, page in enumerate(reader.pages):
    text = page.extract_text()
    if "ANÁLISIS PASS" in text or "Apéndice B" in text or "APÉNDICE B" in text or "B.1 INTRODUCCIÓN" in text or "B. PERFORMANCE" in text:
        found_pages.append(idx)

print(f"Found keyword on pages (0-indexed): {found_pages}")

# Imprimir las páginas alrededor de las encontradas
for p_idx in sorted(list(set(found_pages))):
    print(f"\n=====================================")
    print(f"PAGE {p_idx + 1}")
    print(f"=====================================")
    print(reader.pages[p_idx].extract_text()[:4000])

# Vamos a listar también el texto de las páginas al final del documento (donde suele estar el Apéndice B)
# Si es el final, imprimamos las últimas 15 páginas
print(f"\nScanning last 15 pages of the document (total pages: {len(reader.pages)}):")
for p_idx in range(len(reader.pages) - 15, len(reader.pages)):
    text = reader.pages[p_idx].extract_text()
    if "Apéndice B" in text or "APÉNDICE B" in text or "B." in text or "B-1" in text or "B-2" in text or "B-3" in text or "B-4" in text:
        print(f"\n--- LAST PAGE {p_idx + 1} ---")
        print(text[:4000])
