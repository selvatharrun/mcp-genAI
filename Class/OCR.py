from google.cloud import documentai
from google.cloud import storage
import os
from PIL import Image
import matplotlib.pyplot as plt


# Configure Document AI client
project_id = "sodium-coil-470706-f4"  
location = "us"  # Change if using different region
processor_id = "18d898182b219656"

# Initialize the client
client_options = {"api_endpoint": f"{location}-documentai.googleapis.com"}
client = documentai.DocumentProcessorServiceClient(client_options=client_options)

def process_document(gcs_uri):
    """Process a document using Document AI. Accepts GCS URI (gs://) as input."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError("Input must be a GCS URI starting with 'gs://'")
    
    name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"

    # Use GCS input config for Document AI
    gcs_document = documentai.GcsDocument(
        gcs_uri=gcs_uri,
        mime_type="application/pdf"  # Update mime type if needed
    )

    request = documentai.ProcessRequest(
        name=name,
        gcs_document=gcs_document
    )
    result = client.process_document(request=request)
    return result.document

def extract_text_with_pages(document):
    """Extract text with page-wise breakdown and return structured data"""
    result = {
        "full_text": document.text,
        "pages": [],
        "form_fields": [],
        "confidence_score": None
    }
    
    # Process each page
    for page_num, page in enumerate(document.pages, 1):
        page_info = {
            "page_number": page_num,
            "text": "",
            "form_fields": [],
            "confidence": None,
            "detected_languages": []
        }
        
        # Extract page-level confidence if available
        if hasattr(page, 'layout') and hasattr(page.layout, 'confidence'):
            page_info["confidence"] = page.layout.confidence
            # Use the first page's confidence as overall document confidence if not set
            if result["confidence_score"] is None:
                result["confidence_score"] = page.layout.confidence
        
        # Extract detected languages for this page
        if hasattr(page, 'detected_languages'):
            for lang in page.detected_languages:
                page_info["detected_languages"].append({
                    "language_code": lang.language_code,
                    "confidence": lang.confidence
                })
        
        # Extract page text using the page's text anchor
        if hasattr(page, 'layout') and hasattr(page.layout, 'text_anchor'):
            page_text_segments = []
            for segment in page.layout.text_anchor.text_segments:
                start_index = getattr(segment, 'start_index', 0)
                end_index = getattr(segment, 'end_index', len(document.text))
                page_text_segments.append(document.text[start_index:end_index])
            page_info["text"] = "".join(page_text_segments)
        else:
            # Fallback: if this is a single page document, use the full text
            if len(document.pages) == 1:
                page_info["text"] = document.text
        
        # Extract form fields for this page if they exist
        if hasattr(page, 'form_fields'):
            for field in page.form_fields:
                field_name = get_text(field.field_name, document) if hasattr(field, 'field_name') and field.field_name else ""
                field_value = get_text(field.field_value, document) if hasattr(field, 'field_value') and field.field_value else ""
                
                field_info = {
                    "name": field_name,
                    "value": field_value
                }
                page_info["form_fields"].append(field_info)
                result["form_fields"].append({
                    "page": page_num,
                    "name": field_name,
                    "value": field_value
                })
        
        result["pages"].append(page_info)
    
    return result

def display_results(document):
    """Display the extracted text and other information (legacy function for backwards compatibility)"""
    print("Full text extracted:")
    print("="*50)
    print(document.text)
    
    print("\nForm fields found:")
    print("="*50)
    for page in document.pages:
        for field in page.form_fields:
            name = get_text(field.field_name, document)
            value = get_text(field.field_value, document)
            print(f"{name}: {value}")
            
def get_text(doc_element, document):
    """Extract text from a document element"""
    if not doc_element or not hasattr(doc_element, 'text_anchor') or not doc_element.text_anchor:
        return ""
    
    if not hasattr(doc_element.text_anchor, 'text_segments') or not doc_element.text_anchor.text_segments:
        return ""
    
    text = ""
    for segment in doc_element.text_anchor.text_segments:
        start_index = getattr(segment, 'start_index', 0)
        end_index = getattr(segment, 'end_index', len(document.text))
        text += document.text[start_index:end_index]
    return text.strip()

def process_pdf_with_document_ai(gcs_uri):
    """
    Main function to process a PDF from GCS URI using Document AI.
    Returns structured text data with page details for MCP app usage.
    
    Args:
        gcs_uri (str): GCS URI of the PDF file (e.g., 'gs://bucket-name/file.pdf')
    
    Returns:
        dict: Structured data containing:
            - full_text: Complete extracted text
            - pages: List of page-wise text, form fields, confidence, and detected languages
            - form_fields: All form fields with page numbers
            - confidence_score: Document quality confidence score
            - total_pages: Number of pages processed
            - total_characters: Total number of characters extracted
            - success: Boolean indicating success
            - error: Error message if any
    """
    try:
        # Validate input
        if not gcs_uri or not isinstance(gcs_uri, str):
            return {
                "success": False,
                "error": "Invalid GCS URI provided",
                "full_text": "",
                "pages": [],
                "form_fields": [],
                "confidence_score": None,
                "total_pages": 0,
                "total_characters": 0
            }
        
        # Process the document
        processed_doc = process_document(gcs_uri)
        
        # Extract structured text with page details
        result = extract_text_with_pages(processed_doc)
        
        # Add success flag and additional metadata
        result["success"] = True
        result["error"] = None
        result["total_pages"] = len(result["pages"])
        result["total_characters"] = len(result["full_text"])
        result["document_uri"] = getattr(processed_doc, 'uri', '') if hasattr(processed_doc, 'uri') else ''
        result["mime_type"] = getattr(processed_doc, 'mime_type', '') if hasattr(processed_doc, 'mime_type') else ''
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Document processing failed: {str(e)}",
            "full_text": "",
            "pages": [],
            "form_fields": [],
            "confidence_score": None,
            "total_pages": 0,
            "total_characters": 0
        }

# Example usage (commented out for production use)
# if __name__ == "__main__":
#     # Example GCS URI
#     test_gcs_uri = "gs://your-bucket/your-file.pdf"
#     result = process_pdf_with_document_ai(test_gcs_uri)
#     print("Processing result:", result)