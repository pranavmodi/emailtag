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
            else:
                error_msg = doc_analysis.get('error', 'Analysis failed') if doc_analysis else 'No analysis data'
                processed_result.update({
                    'analysis_success': False,
                    'document_type': 'failed',
                    'patient_id': 'Error',
                    'confidence': 0.0,
                    'description': f'Error: {error_msg}',
                    'error': error_msg
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
                'full_result': {'error': str(e)}
            }
    
    async def process_all_documents(self) -> List[Dict[str, Any]]:
        """Process all documents in the directory."""
        documents = self.find_documents()
        
        if not documents:
            print(f"📁 No supported documents found in {self.data_dir}")
            return []
        
        print(f"🔍 Found {len(documents)} documents to process")
        print("=" * 60)
        
        results = []
        for doc_path in documents:
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
            col_widths[7] = max(col_widths[7], min(len(str(result['description'])), 40))
        
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
            if len(description) > 40:
                description = description[:37] + "..."
            
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
                    'document_type', 'patient_id', 'confidence', 'description'
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
    
    # Create processor and run
    processor = DocumentBatchProcessor(data_dir)
    results = await processor.process_all_documents()
    
    if results:
        # Print results table
        processor.print_results_table(results)
        
        # Save to CSV with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = output_dir / f"document_processing_results_{timestamp}.csv"
        processor.save_results_to_csv(results, csv_file)
        
        print(f"\n✅ Batch processing completed! Processed {len(results)} documents.")
    else:
        print("\n⚠️  No documents were processed.")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())