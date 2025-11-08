# PDF to HTML Conversion Setup

This document explains how to set up PDF to HTML conversion with layout preservation.

## Available Methods

The backend supports two methods for PDF to HTML conversion:

### 1. PyMuPDF (Default - Already Installed)

- **Status**: ✅ Already available (installed via requirements.txt)
- **Method**: Uses PyMuPDF's built-in HTML export
- **Pros**:
  - No additional installation needed
  - Fast conversion
  - Good layout preservation
- **Cons**:
  - May not preserve complex layouts as perfectly as pdf2htmlEX

### 2. pdf2htmlEX (Optional - Higher Fidelity)

- **Status**: ⚠️ Requires system installation
- **Method**: External command-line tool
- **Pros**:
  - Excellent layout preservation
  - Handles complex PDFs better
  - Industry-standard tool
- **Cons**:
  - Requires system-level installation
  - Slightly slower

## Installation Instructions

### Windows

1. Download pdf2htmlEX from: https://github.com/coolwanglu/pdf2htmlEX/releases
2. Extract the ZIP file
3. Add the `bin` directory to your system PATH
4. Verify installation:
   ```powershell
   pdf2htmlEX --version
   ```

### Linux (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install pdf2htmlEX
```

### Linux (CentOS/RHEL)

```bash
sudo yum install pdf2htmlEX
```

### macOS

```bash
brew install pdf2htmlEX
```

## Usage

### API Endpoint

**POST** `/convert_pdf_to_html`

**Request:**

- `pdf`: PDF file (multipart/form-data)
- `method`: Optional. Either `"pymupdf"` (default) or `"pdf2htmlex"`

**Response:**

```json
{
  "status": "success",
  "message": "PDF converted to HTML successfully using PyMuPDF",
  "converted_filename": "document_converted.html",
  "original_format": "PDF",
  "converted_format": "HTML",
  "method_used": "PyMuPDF",
  "original_size": 123456,
  "html_size": 234567,
  "download_url": "/download_converted/document_converted.html",
  "preview_url": "/preview_html/document_converted.html"
}
```

### Example cURL

```bash
# Using PyMuPDF (default)
curl -X POST http://localhost:5000/convert_pdf_to_html \
  -F "pdf=@document.pdf"

# Using pdf2htmlEX
curl -X POST http://localhost:5000/convert_pdf_to_html \
  -F "pdf=@document.pdf" \
  -F "method=pdf2htmlex"
```

## How It Works

1. If `method=pdf2htmlex` is specified, the system tries pdf2htmlEX first
2. If pdf2htmlEX fails or is not available, it automatically falls back to PyMuPDF
3. The converted HTML file is saved to the `saved_html` folder
4. The response includes download and preview URLs

## Notes

- The system automatically falls back to PyMuPDF if pdf2htmlEX is not available
- Both methods preserve layout, but pdf2htmlEX generally provides better results for complex PDFs
- Converted HTML files are automatically cleaned up after 1 hour (configurable)
