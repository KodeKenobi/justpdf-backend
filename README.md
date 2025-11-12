# Trevnoctilla Backend

Flask backend for the Trevnoctilla application.

## Installation

1. Navigate to the backend directory:

```bash
cd trevnoctilla-backend
```

2. Install Python dependencies:

If you have pip issues, try these methods in order:

Method 1 - Using py launcher:

```bash
py -m pip install -r requirements.txt
```

Method 2 - Direct pip:

```bash
pip install -r requirements.txt
```

Method 3 - Using py -m pip (alternative):

```bash
py -m pip install -r requirements.txt
```

Method 4 - If pip is not available, install pip first:

```bash
py -m ensurepip --upgrade
py -m pip install -r requirements.txt
```

Method 5 - Manual installation (if all else fails):

```bash
py -m pip install Flask==3.1.2
py -m pip install Werkzeug==3.0.3
py -m pip install PyMuPDF==1.24.3
py -m pip install Pillow==10.4.0
py -m pip install moviepy==1.0.3
py -m pip install pydub==0.25.1
```

3. Run the Flask application:

```bash
py app.py
```

## Dependencies

- Flask==3.1.2
- Other dependencies listed in requirements.txt

## Usage

The backend provides API endpoints for PDF processing, file conversion, and other tools used by the frontend application.
