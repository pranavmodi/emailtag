"""Document processing endpoints."""

import logging
from typing import List, Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Form, status
from fastapi.responses import JSONResponse

from app.services.document_processing_service import DocumentProcessingService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/process")
async def process_document(
    file: UploadFile = File(...),
    provider: Optional[str] = Form(None)
):
    """
    Process a single document and return structured analysis.
    
    Args:
        file: Uploaded document file
        provider: Optional strikethrough detection provider (google|roboflow|openai)
        
    Returns:
        JSON response with document analysis results
    """
    try:
        # Read file content
        file_content = await file.read()
        filename = file.filename or "unknown_document"
        
        logger.info(f"Processing uploaded document: {filename} ({len(file_content)} bytes)")
        
        # Process the document
        service = DocumentProcessingService(strikethrough_provider=provider)
        result = await service.process_document(file_content, filename)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "data": result
            }
        )
        
    except Exception as e:
        logger.error(f"Error processing document {filename}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document processing failed: {str(e)}"
        )


@router.post("/process-batch")
async def process_documents_batch(
    files: List[UploadFile] = File(...),
    provider: Optional[str] = Form(None)
):
    """
    Process multiple documents and return structured analysis for each.
    
    Args:
        files: List of uploaded document files
        provider: Optional strikethrough detection provider (google|roboflow|openai)
        
    Returns:
        JSON response with analysis results for all documents
    """
    try:
        if not files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No files provided"
            )
        
        if len(files) > 10:  # Reasonable limit for batch processing
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many files. Maximum 10 files per batch."
            )
        
        logger.info(f"Processing batch of {len(files)} documents")
        
        # Prepare documents for processing
        documents = []
        for file in files:
            content = await file.read()
            filename = file.filename or f"document_{len(documents)+1}"
            documents.append({
                "content": content,
                "filename": filename
            })
        
        # Process all documents
        service = DocumentProcessingService(strikethrough_provider=provider)
        results = await service.process_multiple_documents(documents)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "total_documents": len(files),
                "data": results
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing document batch: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch processing failed: {str(e)}"
        )


@router.get("/providers")
async def get_processing_providers():
    """
    Get information about available document processing providers.
    
    Returns:
        JSON response with provider information
    """
    try:
        from app.services.pdf_strikethrough_service import get_provider_status
        
        provider_status = get_provider_status()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "providers": provider_status
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting provider information: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get provider information: {str(e)}"
        )


@router.get("/supported-types")
async def get_supported_document_types():
    """
    Get list of supported document types and their capabilities.
    
    Returns:
        JSON response with supported document types
    """
    supported_types = {
        "pdf": {
            "description": "Portable Document Format",
            "capabilities": ["text_extraction", "strikethrough_detection"],
            "supported_extensions": [".pdf"]
        },
        "image": {
            "description": "Image files",
            "capabilities": ["text_extraction"],
            "supported_extensions": [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"]
        },
        "text": {
            "description": "Plain text files",
            "capabilities": ["text_extraction", "content_analysis"],
            "supported_extensions": [".txt"]
        },
        "word_document": {
            "description": "Microsoft Word documents",
            "capabilities": ["basic_metadata"],
            "supported_extensions": [".doc", ".docx"],
            "note": "Limited processing - text extraction not supported for Office documents"
        },
        "excel_document": {
            "description": "Microsoft Excel spreadsheets",
            "capabilities": ["basic_metadata"],
            "supported_extensions": [".xls", ".xlsx"],
            "note": "Limited processing - text extraction not supported for Office documents"
        }
    }
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "supported_types": supported_types,
            "note": "Text extraction and strikethrough detection primarily work with PDF and image files"
        }
    )