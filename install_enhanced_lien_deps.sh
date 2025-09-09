#!/bin/bash

# Installation script for enhanced lien processing dependencies
# Run this script to install the required packages for barcode reading and image processing

echo "Installing enhanced lien processing dependencies..."

# Activate virtual environment if it exists
if [ -d "emailtag" ]; then
    echo "Activating virtual environment..."
    source emailtag/bin/activate
fi

# Install Python packages
echo "Installing Python packages..."
pip install opencv-python==4.10.0.84
pip install pyzbar==0.1.9
pip install Pillow==11.1.0

# Install system dependencies for barcode reading
echo "Installing system dependencies..."

# For Ubuntu/Debian
if command -v apt-get &> /dev/null; then
    echo "Detected Ubuntu/Debian system. Installing zbar library..."
    sudo apt-get update
    sudo apt-get install -y libzbar0 libzbar-dev
fi

# For CentOS/RHEL/Fedora
if command -v yum &> /dev/null; then
    echo "Detected CentOS/RHEL system. Installing zbar library..."
    sudo yum install -y zbar-devel
fi

if command -v dnf &> /dev/null; then
    echo "Detected Fedora system. Installing zbar library..."
    sudo dnf install -y zbar-devel
fi

# For macOS
if command -v brew &> /dev/null; then
    echo "Detected macOS system. Installing zbar library..."
    brew install zbar
fi

echo "✅ Enhanced lien processing dependencies installed successfully!"
echo ""
echo "📋 Summary of installed packages:"
echo "  - opencv-python: Computer vision and image processing"
echo "  - pyzbar: Barcode reading library"
echo "  - Pillow: Python Imaging Library"
echo "  - libzbar: System library for barcode reading"
echo ""
echo "🔍 New capabilities:"
echo "  - Barcode detection and parsing with ^ separator"
echo "  - Signature detection using OpenAI Vision API"
echo "  - Enhanced lien document classification"
echo "  - Automatic PSL/ASL determination based on signatures"
echo ""
echo "🚀 The enhanced lien processing is now ready to use!"