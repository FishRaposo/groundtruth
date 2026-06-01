"""OCR service for document processing.

Extracts text from PDFs, images, and scanned documents using Tesseract
and layout-preserving extraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


from app.models.document import Document


try:
    import pytesseract
    from PIL import Image
    from pdf2image import convert_from_path
    _OCR_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore[assignment]
    Image = None  # type: ignore[assignment]
    convert_from_path = None  # type: ignore[assignment]
    _OCR_AVAILABLE = False


@dataclass
class OCRBlock:
    """A block of extracted text with position information."""
    text: str
    x: int
    y: int
    width: int
    height: int
    page: int
    block_type: str  # paragraph, header, table, signature
    confidence: float


@dataclass
class OCResult:
    """Result of OCR processing."""
    text: str
    blocks: list[OCRBlock]
    total_pages: int
    confidence: float
    language: str
    metadata: dict[str, Any]


class OCRService:
    """Service for extracting text from documents using OCR.
    
    Supports:
    - PDF documents (text-based and scanned)
    - Image files (PNG, JPG, TIFF)
    - Layout preservation (headers, paragraphs, tables)
    - Multi-language support
    """
    
    def __init__(self, dpi: int = 300) -> None:
        """Initialize OCR service.
        
        Args:
            dpi: Resolution for image conversion (higher = better accuracy).
        """
        self.dpi = dpi
    
    async def process_document(
        self,
        document: Document,
        language: str = "eng",
        preserve_layout: bool = True,
    ) -> OCResult:
        """Process a document with OCR.

        Args:
            document: Document to process.
            language: OCR language code (default: English).
            preserve_layout: Whether to preserve document layout.

        Returns:
            OCResult with extracted text and blocks.
        """
        if not _OCR_AVAILABLE:
            raise RuntimeError(
                "OCR dependencies not installed. "
                "Install with: pip install pytesseract pillow pdf2image"
            )
        file_path = Path(document.file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Document file not found: {file_path}")
        
        suffix = file_path.suffix.lower()
        
        if suffix == ".pdf":
            return await self._process_pdf(file_path, language, preserve_layout)
        elif suffix in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}:
            return await self._process_image(file_path, language)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")
    
    async def _process_pdf(
        self,
        file_path: Path,
        language: str,
        preserve_layout: bool,
    ) -> OCResult:
        """Process PDF document."""
        # Convert PDF to images
        images = convert_from_path(str(file_path), dpi=self.dpi)
        
        all_blocks: list[OCRBlock] = []
        full_text_parts: list[str] = []
        total_confidence = 0.0
        
        for page_num, image in enumerate(images, start=1):
            page_blocks = await self._extract_from_image(image, language, page_num)
            all_blocks.extend(page_blocks)
            
            page_text = "\n".join(b.text for b in page_blocks)
            full_text_parts.append(page_text)
            
            if page_blocks:
                total_confidence += sum(b.confidence for b in page_blocks) / len(page_blocks)
        
        full_text = "\n\n".join(full_text_parts)
        avg_confidence = total_confidence / len(images) if images else 0.0
        
        if preserve_layout:
            all_blocks = self._classify_blocks(all_blocks)
        
        return OCResult(
            text=full_text,
            blocks=all_blocks,
            total_pages=len(images),
            confidence=avg_confidence,
            language=language,
            metadata={
                "dpi": self.dpi,
                "preserve_layout": preserve_layout,
                "file_type": "pdf",
            },
        )
    
    async def _process_image(
        self,
        file_path: Path,
        language: str,
    ) -> OCResult:
        """Process single image."""
        image = Image.open(file_path)
        blocks = await self._extract_from_image(image, language, page=1)
        
        full_text = "\n".join(b.text for b in blocks)
        avg_confidence = sum(b.confidence for b in blocks) / len(blocks) if blocks else 0.0
        
        return OCResult(
            text=full_text,
            blocks=blocks,
            total_pages=1,
            confidence=avg_confidence,
            language=language,
            metadata={
                "file_type": file_path.suffix.lower(),
            },
        )
    
    async def _extract_from_image(
        self,
        image: Image.Image,
        language: str,
        page: int,
    ) -> list[OCRBlock]:
        """Extract text blocks from image using Tesseract."""
        # Get detailed OCR data
        data = pytesseract.image_to_data(
            image,
            lang=language,
            output_type=pytesseract.Output.DICT,
        )
        
        blocks: list[OCRBlock] = []
        n_boxes = len(data["text"])
        
        for i in range(n_boxes):
            text = data["text"][i].strip()
            if not text:
                continue
            
            confidence = float(data["conf"][i])
            if confidence < 30:  # Skip low confidence
                continue
            
            block = OCRBlock(
                text=text,
                x=data["left"][i],
                y=data["top"][i],
                width=data["width"][i],
                height=data["height"][i],
                page=page,
                block_type="paragraph",  # Will be classified later
                confidence=confidence / 100.0,
            )
            blocks.append(block)
        
        return blocks
    
    def _classify_blocks(self, blocks: list[OCRBlock]) -> list[OCRBlock]:
        """Classify blocks by type based on position and formatting."""
        if not blocks:
            return blocks
        
        # Sort by position
        sorted_blocks = sorted(blocks, key=lambda b: (b.page, b.y, b.x))
        
        # Detect headers (top of page, larger font)
        avg_height = sum(b.height for b in sorted_blocks) / len(sorted_blocks)
        
        for i, block in enumerate(sorted_blocks):
            # Header detection: top of page, larger height
            if block.y < 100 and block.height > avg_height * 1.3:
                block.block_type = "header"
            # Table detection: aligned columns
            elif self._is_table_row(block, sorted_blocks, i):
                block.block_type = "table"
            # Signature detection: bottom right
            elif block.y > 700 and block.x > 400:
                block.block_type = "signature"
            else:
                block.block_type = "paragraph"
        
        return sorted_blocks
    
    def _is_table_row(
        self,
        block: OCRBlock,
        all_blocks: list[OCRBlock],
        index: int,
    ) -> bool:
        """Detect if block is part of a table row."""
        # Simple heuristic: check if there are other blocks at similar y-coordinate
        same_y = [b for b in all_blocks if abs(b.y - block.y) < 10 and b != block]
        return len(same_y) >= 2  # At least 3 blocks in a row = table
    
    def extract_tables(self, result: OCResult) -> list[list[list[str]]]:
        """Extract table data from OCR result.
        
        Returns:
            List of tables, each table is list of rows, each row is list of cells.
        """
        tables: list[list[list[str]]] = []
        current_table: list[list[str]] = []
        current_row: list[str] = []
        last_y = 0
        
        table_blocks = [b for b in result.blocks if b.block_type == "table"]
        table_blocks = sorted(table_blocks, key=lambda b: (b.y, b.x))
        
        for block in table_blocks:
            if abs(block.y - last_y) > 15:
                # New row
                if current_row:
                    current_table.append(current_row)
                current_row = [block.text]
                last_y = block.y
            else:
                # Same row
                current_row.append(block.text)
        
        if current_row:
            current_table.append(current_row)
        
        if current_table:
            tables.append(current_table)
        
        return tables
    
    def extract_signatures(self, result: OCResult) -> list[OCRBlock]:
        """Extract signature blocks from OCR result."""
        return [b for b in result.blocks if b.block_type == "signature"]
