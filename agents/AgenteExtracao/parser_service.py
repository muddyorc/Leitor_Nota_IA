import fitz
import shutil

try:
    import pytesseract
    from PIL import Image

    _tesseract_bin = shutil.which("tesseract")
    OCR_DISPONIVEL = _tesseract_bin is not None
    if not OCR_DISPONIVEL:
        # Evita tentar OCR quando o binário do tesseract não está disponível
        print("Aviso: 'tesseract' não encontrado no PATH. OCR será desabilitado.")
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
        elif not texto.strip() and not OCR_DISPONIVEL:
            # Sem texto embutido e sem OCR disponível: informar claramente no log
            print("Observação: PDF sem texto extraível e OCR desabilitado por ausência do 'tesseract'.")
        return texto
    except Exception as e:
        print(f"Erro ao extrair texto PDF: {e}")
        return ""
