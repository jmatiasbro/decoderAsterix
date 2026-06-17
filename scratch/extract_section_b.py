import pypdf

pdf_path = r"c:\documentos\decode_asterix\PASS\0105500000000IT17_A0_IT #21.pdf"
reader = pypdf.PdfReader(pdf_path)

output_path = r"c:\documentos\decode_asterix\scratch\section_b_extracted.txt"

with open(output_path, "w", encoding="utf-8") as f:
    f.write("=== APÉNDICE B: PERFORMANCE ASSESSMENT OF SURVEILLANCE SYSTEMS (PASS) ===\n\n")
    # Apéndice B está en las páginas indexadas de la 86 a la 91 (páginas 87 a 92 del documento)
    for page_idx in range(86, 92):
        if page_idx < len(reader.pages):
            f.write(f"\n=====================================\n")
            f.write(f"PÁGINA DOCUMENTO: {page_idx + 1} (Página Apéndice: B-{page_idx - 85})\n")
            f.write(f"=====================================\n\n")
            text = reader.pages[page_idx].extract_text()
            f.write(text)
            f.write("\n")

print(f"Extraction completed! Content saved to {output_path}")
