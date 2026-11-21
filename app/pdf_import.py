"""Strict text-PDF import. Teachers approve the extracted answer key before publishing."""
import io
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pypdf import PdfReader
from .auth import teacher
from .schemas import ItemCreate

router = APIRouter(prefix='/api')
MAX_BYTES = 3 * 1024 * 1024


from .pdf_parser import parse_questions


@router.post('/question-bank/import-pdf')
async def import_pdf(file: UploadFile = File(...), account=Depends(teacher)):
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, 'Choose a PDF smaller than 3 MB.')
    if not content.startswith(b'%PDF-'):
        raise HTTPException(422, 'Upload a valid PDF document.')
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError('Remove password protection before importing.')
        if len(reader.pages) > 100:
            raise ValueError('Import at most 100 PDF pages.')
        items = parse_questions('\n'.join(page.extract_text() or '' for page in reader.pages))
    except Exception as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else 'This PDF could not be read. Export a text PDF and try again.')
    return {'items': items, 'count': len(items), 'message': 'Review every question and correct answer before publishing.'}
