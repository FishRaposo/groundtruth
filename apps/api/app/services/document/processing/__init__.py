"""Document processing services for GroundTruth.

Includes OCR, template extraction, form filling, and approval workflows.
"""

from __future__ import annotations

from app.services.document.processing.approval import ApprovalWorkflowEngine
from app.services.document.processing.forms import FormFiller
from app.services.document.processing.ocr import OCRService
from app.services.document.processing.templates import TemplateExtractor

__all__ = [
    "OCRService",
    "TemplateExtractor",
    "FormFiller",
    "ApprovalWorkflowEngine",
]
