#!/usr/bin/env python3
"""
Document Processing Batch Script

This script processes all documents in the data/documents directory and outputs
a detailed analysis table with document classification and patient ID extraction results.
"""

import os
import sys
import asyncio
import csv
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.document_processing_service import DocumentProcessingService

class DocumentBatchProcessor:
    """Batch processor for analyzing documents in a directory."""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.service = DocumentProcessingService()
        self.results = []
        
        # Supported file extensions for AI processing
        self.supported_extensions = {
            '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'
        }
    
    def find_documents(self) -> List[Path]:
        """Find all supported documents in the data directory."""
        documents = []
        
        if not self.data_dir.exists():
            print(f"❌ Data directory not found: {self.data_dir}")
            return documents
        
        for file_path in self.data_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in self.supported_extensions:
                documents.append(file_path)
        
        # Sort documents by name for consistent processing order
        documents.sort(key=lambda x: x.name.lower())
        return documents
    
    async def process_document(self, file_path: Path) -> Dict[str, Any]:
        """Process a single document and return analysis results."""
        try:
            # Read file content
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            filename = file_path.name
            file_size = len(file_content)
            
            print(f"  📄 Processing: {filename} ({file_size:,} bytes)")
            
            # Process with the document service
            result = await self.service.process_document(file_content, filename)
            
            # Extract key information for table display
            processed_result = {
                'filename': filename,
                'file_size': file_size,
                'file_extension': file_path.suffix.lower(),
                'detected_type': result.get('detected_type', 'unknown'),
                'processing_status': result.get('processing_status', 'unknown'),
                'provider': result.get('provider_info', {}).get('analysis_provider', 'unknown')
            }
            
            # Extract document analysis results
            doc_analysis = result.get('document_analysis', {})
            if doc_analysis and doc_analysis.get('success'):
                analysis_data = doc_analysis.get('data', {})
                processed_result.update({
                    'analysis_success': True,
                    'document_type': analysis_data.get('document_type', 'unknown'),
                    'patient_id': analysis_data.get('patient_id') or 'Not found',
                    'confidence': analysis_data.get('confidence', 0.0),
                    'description': analysis_data.get('description', 'No description')
                })
                
                # Add enhanced lien processing details if available
                enhanced_lien = analysis_data.get('enhanced_lien_analysis', {})
                if enhanced_lien:
                    processed_result.update({
                        'lien_signature_type': enhanced_lien.get('LienSignatureType', 'UNKNOWN'),
                        'lien_type': enhanced_lien.get('LienType', ''),
                        'referrer_id': enhanced_lien.get('ReferrerID', ''),
                        'barcode_found': enhanced_lien.get('barcode_found', False),
                        'signature_analysis': enhanced_lien.get('signature_analysis', '')
                    })
                    
                    # Extract raw barcode data from full enhanced lien processing result
                    enhanced_full = result.get('enhanced_lien_processing', {})
                    raw_barcode_pages = enhanced_full.get('raw_page_results', [])
                    raw_barcode_value = 'Not found'
                    
                    # Look through all pages for barcode data
                    for page in raw_barcode_pages:
                        barcode_detection = page.get('barcode_detection', {})
                        if barcode_detection.get('barcode_found') and barcode_detection.get('raw_value'):
                            raw_barcode_value = barcode_detection.get('raw_value', 'Not found')
                            break
                    
                    processed_result['raw_barcode_value'] = raw_barcode_value
                else:
                    processed_result.update({
                        'lien_signature_type': 'N/A',
                        'lien_type': 'N/A',
                        'referrer_id': 'N/A',
                        'barcode_found': False,
                        'signature_analysis': 'N/A',
                        'raw_barcode_value': 'N/A'
                    })
            else:
                error_msg = doc_analysis.get('error', 'Analysis failed') if doc_analysis else 'No analysis data'
                processed_result.update({
                    'analysis_success': False,
                    'document_type': 'failed',
                    'patient_id': 'Error',
                    'confidence': 0.0,
                    'description': f'Error: {error_msg}',
                    'error': error_msg,
                    'lien_signature_type': 'Error',
                    'lien_type': 'Error',
                    'referrer_id': 'Error',
                    'barcode_found': False,
                    'signature_analysis': 'Error',
                    'raw_barcode_value': 'Error'
                })
            
            # Add full result for CSV export
            processed_result['full_result'] = result
            
            return processed_result
            
        except Exception as e:
            print(f"    ❌ Error processing {file_path.name}: {e}")
            return {
                'filename': file_path.name,
                'file_size': 0,
                'file_extension': file_path.suffix.lower(),
                'detected_type': 'error',
                'processing_status': 'failed',
                'provider': 'none',
                'analysis_success': False,
                'document_type': 'error',
                'patient_id': 'Error',
                'confidence': 0.0,
                'description': f'Processing error: {str(e)}',
                'error': str(e),
                'lien_signature_type': 'Error',
                'lien_type': 'Error',
                'referrer_id': 'Error',
                'barcode_found': False,
                'signature_analysis': 'Error',
                'raw_barcode_value': 'Error',
                'full_result': {'error': str(e)}
            }
    
    def list_and_select_documents(self) -> List[Path]:
        """List all documents and let user select which ones to process."""
        documents = self.find_documents()
        
        if not documents:
            print(f"📁 No supported documents found in {self.data_dir}")
            return []
        
        print(f"🔍 Found {len(documents)} documents:")
        print("=" * 60)
        
        # Display numbered list of documents
        for i, doc_path in enumerate(documents, 1):
            file_size = doc_path.stat().st_size
            file_size_kb = file_size / 1024
            print(f"  {i:2d}. {doc_path.name:<40} ({file_size_kb:8.1f} KB)")
        
        print("=" * 60)
        print("\n📋 Select documents to process:")
        print("  • Enter numbers separated by commas (e.g., 1,3,5)")
        print("  • Enter 'all' to process all documents")
        print("  • Press Enter to cancel")
        
        while True:
            try:
                user_input = input("\n👉 Your selection: ").strip()
                
                if not user_input:
                    print("❌ No selection made. Exiting.")
                    return []
                
                if user_input.lower() == 'all':
                    print(f"✅ Selected all {len(documents)} documents for processing.")
                    return documents
                
                # Parse comma-separated numbers
                selected_numbers = []
                for part in user_input.split(','):
                    part = part.strip()
                    if part.isdigit():
                        num = int(part)
                        if 1 <= num <= len(documents):
                            selected_numbers.append(num)
                        else:
                            print(f"⚠️  Number {num} is out of range (1-{len(documents)})")
                    else:
                        print(f"⚠️  '{part}' is not a valid number")
                
                if not selected_numbers:
                    print("❌ No valid documents selected. Please try again.")
                    continue
                
                # Remove duplicates and sort
                selected_numbers = sorted(set(selected_numbers))
                selected_docs = [documents[i-1] for i in selected_numbers]
                
                print(f"✅ Selected {len(selected_docs)} document(s) for processing:")
                for doc in selected_docs:
                    print(f"   📄 {doc.name}")
                
                return selected_docs
                
            except KeyboardInterrupt:
                print("\n❌ Cancelled by user.")
                return []
            except Exception as e:
                print(f"❌ Error processing selection: {e}")
                continue

    async def process_selected_documents(self, selected_documents: List[Path]) -> List[Dict[str, Any]]:
        """Process the selected documents."""
        if not selected_documents:
            return []
        
        print(f"\n🚀 Processing {len(selected_documents)} selected document(s)...")
        print("=" * 60)
        
        results = []
        for i, doc_path in enumerate(selected_documents, 1):
            print(f"[{i}/{len(selected_documents)}]", end=" ")
            result = await self.process_document(doc_path)
            results.append(result)
        
        return results
    
    def print_results_table(self, results: List[Dict[str, Any]]):
        """Print a formatted table of results."""
        if not results:
            print("No results to display.")
            return
        
        print("\n" + "=" * 120)
        print("📊 DOCUMENT PROCESSING RESULTS")
        print("=" * 120)
        
        # Table headers
        headers = [
            "Filename", "Size", "Type", "Doc Type", "Patient ID", "Confidence", "Status", "Description"
        ]
        
        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for result in results:
            col_widths[0] = max(col_widths[0], len(str(result['filename'])))
            col_widths[1] = max(col_widths[1], len(f"{result['file_size']:,}"))
            col_widths[2] = max(col_widths[2], len(str(result['detected_type'])))
            col_widths[3] = max(col_widths[3], len(str(result['document_type'])))
            col_widths[4] = max(col_widths[4], len(str(result['patient_id'])))
            col_widths[5] = max(col_widths[5], len(f"{result['confidence']:.1%}"))
            col_widths[6] = max(col_widths[6], len("✅" if result['analysis_success'] else "❌"))
            col_widths[7] = max(col_widths[7], len(str(result['description'])))
        
        # Ensure minimum widths
        for i in range(len(col_widths)):
            col_widths[i] = max(col_widths[i], 8)
        
        # Print header
        header_line = " | ".join(h.ljust(w) for h, w in zip(headers, col_widths))
        print(header_line)
        print("-" * len(header_line))
        
        # Print rows
        for result in results:
            status_icon = "✅" if result['analysis_success'] else "❌"
            description = str(result['description'])
            
            row = [
                str(result['filename']),
                f"{result['file_size']:,}",
                str(result['detected_type']),
                str(result['document_type']).upper(),
                str(result['patient_id']),
                f"{result['confidence']:.1%}",
                status_icon,
                description
            ]
            
            row_line = " | ".join(val.ljust(w) for val, w in zip(row, col_widths))
            print(row_line)
        
        print("=" * 120)
        
        # Print detailed lien processing results if any lien documents were found
        lien_results = [r for r in results if r.get('document_type', '').lower() == 'lien' and r.get('analysis_success')]
        if lien_results:
            print(f"\n🔗 ENHANCED LIEN PROCESSING DETAILS")
            print("=" * 140)
            lien_headers = ["Filename", "Patient ID", "Signature Type", "Lien Type", "Referrer ID", "Barcode", "Raw Barcode", "Signature Analysis"]
            
            # Calculate lien column widths
            lien_col_widths = [len(h) for h in lien_headers]
            for result in lien_results:
                lien_col_widths[0] = max(lien_col_widths[0], len(str(result['filename'])))
                lien_col_widths[1] = max(lien_col_widths[1], len(str(result.get('patient_id', 'N/A'))))
                lien_col_widths[2] = max(lien_col_widths[2], len(str(result.get('lien_signature_type', 'N/A'))))
                lien_col_widths[3] = max(lien_col_widths[3], len(str(result.get('lien_type', 'N/A'))))
                lien_col_widths[4] = max(lien_col_widths[4], len(str(result.get('referrer_id', 'N/A'))))
                lien_col_widths[5] = max(lien_col_widths[5], len("✅" if result.get('barcode_found') else "❌"))
                raw_barcode = str(result.get('raw_barcode_value', 'N/A'))
                lien_col_widths[6] = max(lien_col_widths[6], len(raw_barcode))
                sig_analysis = str(result.get('signature_analysis', 'N/A'))
                lien_col_widths[7] = max(lien_col_widths[7], len(sig_analysis))
            
            # Ensure minimum lien column widths
            for i in range(len(lien_col_widths)):
                lien_col_widths[i] = max(lien_col_widths[i], 10)
                
            # Print lien headers
            lien_header_line = " | ".join(h.ljust(w) for h, w in zip(lien_headers, lien_col_widths))
            print(lien_header_line)
            print("-" * len(lien_header_line))
            
            # Print lien rows
            for result in lien_results:
                barcode_icon = "✅" if result.get('barcode_found') else "❌"
                raw_barcode = str(result.get('raw_barcode_value', 'N/A'))
                sig_analysis = str(result.get('signature_analysis', 'N/A'))
                
                lien_row = [
                    str(result['filename']),
                    str(result.get('patient_id', 'N/A')),
                    str(result.get('lien_signature_type', 'N/A')),
                    str(result.get('lien_type', 'N/A')),
                    str(result.get('referrer_id', 'N/A')),
                    barcode_icon,
                    raw_barcode,
                    sig_analysis
                ]
                
                lien_row_line = " | ".join(val.ljust(w) for val, w in zip(lien_row, lien_col_widths))
                print(lien_row_line)
            
            print("=" * 140)
            
            # Print detailed per-page analysis for each lien document
            self._print_per_page_lien_analysis(lien_results)
        
        # Print summary statistics
        total_docs = len(results)
        successful = sum(1 for r in results if r['analysis_success'])
        failed = total_docs - successful
        
        # Document type distribution
        doc_types = {}
        patient_ids_found = 0
        for result in results:
            if result['analysis_success']:
                doc_type = result['document_type']
                doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
                if result['patient_id'] != 'Not found' and result['patient_id'] != 'Error':
                    patient_ids_found += 1
        
        print(f"\n📈 SUMMARY STATISTICS")
        print(f"  Total documents processed: {total_docs}")
        print(f"  Successful analyses: {successful}")
        print(f"  Failed analyses: {failed}")
        print(f"  Patient IDs found: {patient_ids_found}")
        print(f"  Success rate: {successful/total_docs:.1%}")
        
        if doc_types:
            print(f"\n📋 DOCUMENT TYPE DISTRIBUTION")
            for doc_type, count in sorted(doc_types.items()):
                percentage = count / successful * 100 if successful > 0 else 0
                print(f"  {doc_type.upper()}: {count} ({percentage:.1f}%)")
    
    def _print_per_page_lien_analysis(self, lien_results: List[Dict[str, Any]]):
        """Print detailed per-page analysis for lien documents."""
        for result in lien_results:
            filename = result['filename']
            print(f"\n📄 PER-PAGE ANALYSIS: {filename}")
            print("=" * 120)
            
            # Extract raw page results from enhanced lien processing
            enhanced_full = result.get('full_result', {}).get('enhanced_lien_processing', {})
            raw_pages = enhanced_full.get('raw_page_results', [])
            
            if not raw_pages:
                print("   ⚠️  No per-page data available")
                print("=" * 120)
                continue
            
            # Per-page table headers
            page_headers = ["Page", "Barcode Found", "Raw Barcode", "Patient Sig", "Attorney Sig", "Signature Analysis"]
            
            # Calculate column widths
            page_col_widths = [len(h) for h in page_headers]
            for page in raw_pages:
                page_name = page.get('page_name', 'Unknown')
                page_col_widths[0] = max(page_col_widths[0], len(page_name))
                
                barcode_detection = page.get('barcode_detection', {})
                barcode_found = "✅" if barcode_detection.get('barcode_found') else "❌"
                page_col_widths[1] = max(page_col_widths[1], len(barcode_found))
                
                raw_barcode = str(barcode_detection.get('raw_value', 'Not found'))
                page_col_widths[2] = max(page_col_widths[2], len(raw_barcode))
                
                signature_detection = page.get('signature_detection', {})
                if signature_detection.get('success'):
                    sig_data = signature_detection.get('signature_data', {})
                    patient_sig = "✅" if sig_data.get('patient_signature_present') else "❌"
                    attorney_sig = "✅" if sig_data.get('attorney_signature_present') else "❌"
                    sig_analysis = str(sig_data.get('signature_analysis', 'N/A'))  # No truncation
                else:
                    patient_sig = "Error"
                    attorney_sig = "Error"
                    sig_analysis = "Signature detection failed"
                
                page_col_widths[3] = max(page_col_widths[3], len(patient_sig))
                page_col_widths[4] = max(page_col_widths[4], len(attorney_sig))
                page_col_widths[5] = max(page_col_widths[5], len(sig_analysis))
            
            # Ensure minimum widths
            for i in range(len(page_col_widths)):
                page_col_widths[i] = max(page_col_widths[i], 8)
            
            # Print page headers
            page_header_line = " | ".join(h.ljust(w) for h, w in zip(page_headers, page_col_widths))
            print(page_header_line)
            print("-" * len(page_header_line))
            
            # Print page rows
            for page in raw_pages:
                page_name = page.get('page_name', 'Unknown')
                
                # Barcode data
                barcode_detection = page.get('barcode_detection', {})
                barcode_found = "✅" if barcode_detection.get('barcode_found') else "❌"
                raw_barcode = str(barcode_detection.get('raw_value', 'Not found'))
                
                # Signature data
                signature_detection = page.get('signature_detection', {})
                if signature_detection.get('success'):
                    sig_data = signature_detection.get('signature_data', {})
                    patient_sig = "✅" if sig_data.get('patient_signature_present') else "❌"
                    attorney_sig = "✅" if sig_data.get('attorney_signature_present') else "❌"
                    sig_analysis = str(sig_data.get('signature_analysis', 'N/A'))
                    # No truncation - show full analysis
                else:
                    patient_sig = "Error"
                    attorney_sig = "Error"
                    sig_analysis = "Detection failed"
                
                page_row = [
                    page_name,
                    barcode_found,
                    raw_barcode,
                    patient_sig,
                    attorney_sig,
                    sig_analysis
                ]
                
                page_row_line = " | ".join(val.ljust(w) for val, w in zip(page_row, page_col_widths))
                print(page_row_line)
            
            print("=" * 120)
    
    def save_results_to_csv(self, results: List[Dict[str, Any]], output_file: Path):
        """Save results to a CSV file."""
        if not results:
            print("No results to save.")
            return
        
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                # Define CSV columns
                fieldnames = [
                    'filename', 'file_size', 'file_extension', 'detected_type',
                    'processing_status', 'provider', 'analysis_success',
                    'document_type', 'patient_id', 'confidence', 'description',
                    'lien_signature_type', 'lien_type', 'referrer_id', 'barcode_found', 'raw_barcode_value', 'signature_analysis'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for result in results:
                    # Create a clean row for CSV (exclude full_result which contains complex data)
                    csv_row = {k: v for k, v in result.items() if k in fieldnames}
                    writer.writerow(csv_row)
            
            print(f"💾 Results saved to: {output_file}")
            
        except Exception as e:
            print(f"❌ Error saving CSV file: {e}")


async def main():
    """Main function to run the batch processing."""
    print("🚀 Document Processing Batch Script")
    print("=" * 50)
    
    # Set up paths
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data" / "documents"
    output_dir = project_root / "data"
    
    print(f"📁 Processing documents from: {data_dir}")
    print(f"💾 Output directory: {output_dir}")
    
    # Create processor and let user select documents
    processor = DocumentBatchProcessor(data_dir)
    selected_documents = processor.list_and_select_documents()
    
    if not selected_documents:
        print("👋 No documents selected. Goodbye!")
        return
    
    # Process selected documents
    results = await processor.process_selected_documents(selected_documents)
    
    if results:
        # Print results table
        processor.print_results_table(results)
        
        print(f"\n✅ Batch processing completed! Processed {len(results)} documents.")
    else:
        print("\n⚠️  No documents were processed.")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())