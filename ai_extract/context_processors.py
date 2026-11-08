from django.conf import settings


def ocr_engine(request):
    """Name the configured OCR readers; this is configuration, not a health check."""
    engine = getattr(settings, 'OCR_TEXT_ENGINE', 'surya')
    labels = dict(auto='Surya layout · VietOCR hoặc Surya theo ngôn ngữ', vietocr='Surya layout · VietOCR')
    return dict(ocr_engine_label=labels.get(engine, 'Surya OCR'))
