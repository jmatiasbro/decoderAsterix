import os

pdf_path = r"c:\documentos\decode_asterix\PASS\0105500000000IT17_A0_IT #21.pdf"

# Intentar importar librerías comunes de extracción de PDF
try:
    import pypdf
    print("pypdf available")
    reader = pypdf.PdfReader(pdf_path)
    print(f"Total pages: {len(reader.pages)}")
    # Extraer páginas 2, 3, 4, 5 (0-indexed: 1, 2, 3, 4)
    for p_idx in [2, 3, 4]:
        if p_idx < len(reader.pages):
            print(f"--- PAGE {p_idx + 1} ---")
            print(reader.pages[p_idx].extract_text()[:4000])
except ImportError:
    try:
        import PyPDF2
        print("PyPDF2 available")
        reader = PyPDF2.PdfReader(pdf_path)
        print(f"Total pages: {len(reader.pages)}")
        for p_idx in [2, 3, 4]:
            if p_idx < len(reader.pages):
                print(f"--- PAGE {p_idx + 1} ---")
                print(reader.pages[p_idx].extract_text()[:4000])
    except ImportError:
        try:
            import fitz  # PyMuPDF
            print("PyMuPDF available")
            doc = fitz.open(pdf_path)
            print(f"Total pages: {len(doc)}")
            for p_idx in [2, 3, 4]:
                if p_idx < len(doc):
                    print(f"--- PAGE {p_idx + 1} ---")
                    print(doc[p_idx].get_text()[:4000])
        except ImportError:
            print("No standard PDF libraries available. Installing pypdf...")
