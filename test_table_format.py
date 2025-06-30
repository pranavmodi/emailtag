#!/usr/bin/env python3

from typing import List, Dict, Any

def _create_lien_status_table(lien_statuses: List[Dict[str, Any]]) -> str:
    """Creates an HTML table for lien statuses that renders properly in email clients."""
    if not lien_statuses:
        return "No lien information available"
    
    # Create HTML table for proper email rendering
    html_parts = []
    html_parts.append('<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; font-family: monospace; margin: 10px 0;">')
    html_parts.append('<thead>')
    html_parts.append('<tr style="background-color: #f0f0f0; font-weight: bold;">')
    html_parts.append('<th style="text-align: left; padding: 8px; border: 1px solid #ccc;">Lien type</th>')
    html_parts.append('<th style="text-align: left; padding: 8px; border: 1px solid #ccc;">Patient Signature</th>')
    html_parts.append('<th style="text-align: left; padding: 8px; border: 1px solid #ccc;">Attorney Signature</th>')
    html_parts.append('</tr>')
    html_parts.append('</thead>')
    html_parts.append('<tbody>')
    
    for lien in lien_statuses:
        lien_type = lien.get('lienType', 'Unknown')
        
        # Use the boolean flags as the source of truth for signature status
        if lien.get('hasPatientSigned', False):
            patient_date = lien.get('patientSignedLienDate', '')
            # Only show date if it exists and is not None/empty/null
            if patient_date and str(patient_date).lower() not in ['none', 'null', '']:
                # Clean up the date format if it's too long
                if len(patient_date) > 20:
                    # Try to extract just the date part (first 10 characters usually)
                    patient_date = patient_date[:10] if '/' in patient_date[:10] or '-' in patient_date[:10] else patient_date[:20]
                patient_sig = f"Signed {patient_date}"
            else:
                patient_sig = "Signed"
        else:
            patient_sig = "Not Signed"
            
        if lien.get('hasAttorneySigned', False):
            attorney_date = lien.get('attorneySignedDate', '')
            # Only show date if it exists and is not None/empty/null
            if attorney_date and str(attorney_date).lower() not in ['none', 'null', '']:
                # Clean up the date format if it's too long
                if len(attorney_date) > 20:
                    attorney_date = attorney_date[:10] if '/' in attorney_date[:10] or '-' in attorney_date[:10] else attorney_date[:20]
                attorney_sig = f"Signed {attorney_date}"
            else:
                attorney_sig = "Signed"
        else:
            attorney_sig = "Not Signed"
        
        # Add table row
        html_parts.append('<tr>')
        html_parts.append(f'<td style="padding: 8px; border: 1px solid #ccc;">{lien_type}</td>')
        html_parts.append(f'<td style="padding: 8px; border: 1px solid #ccc;">{patient_sig}</td>')
        html_parts.append(f'<td style="padding: 8px; border: 1px solid #ccc;">{attorney_sig}</td>')
        html_parts.append('</tr>')
    
    html_parts.append('</tbody>')
    html_parts.append('</table>')
    
    return ''.join(html_parts)

# Test data from the user's example
test_data = [
    {
        'lienType': 'Technical Lien (Imaging)',
        'hasPatientSigned': True,
        'patientSignedLienDate': '09/15/2023 13:01:03',
        'hasAttorneySigned': False,
        'attorneySignedDate': None
    },
    {
        'lienType': 'Medical Lien (Radiologist)',
        'hasPatientSigned': False,
        'patientSignedLienDate': None,
        'hasAttorneySigned': False,
        'attorneySignedDate': None
    }
]

if __name__ == "__main__":
    result = _create_lien_status_table(test_data)
    print("HTML Table Output:")
    print(result)
    print("\n" + "="*80 + "\n")
    
    # Also create a simple HTML file to test in browser
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Lien Status Table Test</title>
</head>
<body>
    <h2>Lien Status Table</h2>
    {result}
</body>
</html>
"""
    
    with open("test_table.html", "w") as f:
        f.write(html_content)
    
    print("HTML file created: test_table.html")
    print("You can open this file in a browser to see how the table renders.") 