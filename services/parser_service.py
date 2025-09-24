import fitz
try:
    import pytesseract
    from PIL import Image
    OCR_DISPONIVEL = True
except ImportError:
    OCR_DISPONIVEL = False

def extrair_texto_pdf(file_stream):
    try:
        doc = fitz.open(stream=file_stream.read(), filetype="pdf")
        texto = ""
        for page in doc:
            texto += page.get_text()
        if not texto.strip() and OCR_DISPONIVEL:
            texto = ""
            for page in doc:
                pix = page.get_pixmap()
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                texto += pytesseract.image_to_string(img)
        return texto
    except Exception as e:
        print(f"Erro ao extrair texto PDF: {e}")
        return ""
