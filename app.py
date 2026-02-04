# Version: 2.0.1 - Fixed Playwright installation for live campaign monitoring
from flask import Flask, render_template, request, send_file, redirect, url_for, jsonify, Response, make_response
from flask_cors import CORS
from flask_sock import Sock
from werkzeug.utils import secure_filename
import os
import fitz
import base64
from io import BytesIO
import json
from datetime import datetime, timedelta
import glob
import uuid
import time
import subprocess
import shutil
import threading

# Try to import HTML to PDF conversion libraries
WEASYPRINT_AVAILABLE = False
XHTML2PDF_AVAILABLE = False
PLAYWRIGHT_AVAILABLE = False

# Try WeasyPrint (requires GTK+ on Windows - often problematic)
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
    print("[OK] WeasyPrint available")
except (ImportError, OSError) as e:
    print(f"[WARN] WeasyPrint not available: {e}")

# Try xhtml2pdf (pure Python, works on Windows)
try:
    from xhtml2pdf import pisa
    XHTML2PDF_AVAILABLE = True
    print("[OK] xhtml2pdf available")
except ImportError:
    print("[WARN] xhtml2pdf not available")

# Try Playwright (browser-based, most accurate but requires browser installation)
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
    print("[OK] Playwright available")
except ImportError:
    print("[WARN] Playwright not available")

# Import new API modules
import sys
import os

# Add current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Load .env so DATABASE_URL / SUPABASE_DATABASE_URL are set when running locally
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(current_dir, ".env"))
except ImportError:
    pass

# Import database and auth modules
print("[LOAD] Importing modules...")
try:
    from database import init_db
    print("[OK] Database module imported successfully")
    from models import *  # Import all models to register them with SQLAlchemy
    print("[OK] Models imported successfully")
    # Explicitly import Notification to ensure it's registered
    from models import Notification
    print("[OK] Notification model imported successfully")
    from auth import jwt
    print("[OK] Auth module imported successfully")
except ImportError as e:
    print(f"[ERROR] Import error: {e}")
    print(f"Current directory: {current_dir}")
    print(f"Python path: {sys.path}")
    print(f"Files in current directory: {os.listdir(current_dir)}")
    import traceback
    traceback.print_exc()
    raise

# Create Flask app FIRST, before importing blueprints
app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching

# Initialize WebSocket support
sock = Sock(app)

# Health check endpoint (must be defined early, before any heavy initialization)
@app.route("/health", methods=["GET"])
def health_check():
    """Simple health check for Railway deployment with Trevnoctilla backlink"""
    try:
        response = jsonify({
            "status": "healthy",
            "message": "Backend is running",
            "service": "Trevnoctilla API Backend",
            "website": "https://www.trevnoctilla.com",
            "powered_by": "Trevnoctilla - Free Online PDF Editor & File Converter"
        })
        # Add backlink in headers
        response.headers["X-Powered-By"] = "Trevnoctilla"
        response.headers["X-Service-URL"] = "https://www.trevnoctilla.com"
        response.headers["Link"] = '<https://www.trevnoctilla.com>; rel="canonical"'
        return response, 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/env-check", methods=["GET"])
def env_check():
    """Safe check for deployment: database type only (no secrets). Use to verify Railway env."""
    try:
        uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
        if uri.startswith("sqlite"):
            database = "sqlite"
            ok = False
        else:
            database = "postgres"
            ok = True
        return jsonify({
            "ok": ok,
            "database": database,
            "message": "Use Postgres in production (set SUPABASE_DATABASE_URL or DATABASE_URL)." if not ok else "Database env looks good.",
        }), 200
    except Exception as e:
        return jsonify({"ok": False, "database": "unknown", "message": str(e)}), 500


# Import blueprints with error handling (non-critical for health endpoint)
print("[LOAD] Importing blueprints...")
try:
    from auth_routes import auth_bp
    print("[OK] auth_bp imported")
except Exception as e:
    print(f"[WARN] Failed to import auth_bp: {e}")
    auth_bp = None

try:
    from api.v1.routes import api_v1
    print("[OK] api_v1 imported")
except Exception as e:
    print(f"[WARN] Failed to import api_v1: {e}")
    api_v1 = None

try:
    from api.admin.routes import admin_api
    print("[OK] admin_api imported")
except Exception as e:
    print(f"[WARN] Failed to import admin_api: {e}")
    admin_api = None

try:
    from api.admin.backup_routes import backup_admin_api
    print("[OK] backup_admin_api imported")
except Exception as e:
    print(f"[WARN] Failed to import backup_admin_api: {e}")
    backup_admin_api = None

try:
    from api.admin.ad_service_routes import ad_service_admin_api
    print("[OK] ad_service_admin_api imported")
except Exception as e:
    print(f"[WARN] Failed to import ad_service_admin_api: {e}")
    ad_service_admin_api = None

try:
    from api.client.routes import client_api
    print("[OK] client_api imported")
except Exception as e:
    print(f"[WARN] Failed to import client_api: {e}")
    client_api = None

try:
    from api.payment.routes import payment_api
    print("[OK] payment_api imported")
except Exception as e:
    print(f"[WARN] Failed to import payment_api: {e}")
    payment_api = None

try:
    from api.analytics.routes import analytics_api
    print("[OK] analytics_api imported")
except Exception as e:
    print(f"[WARN] Failed to import analytics_api: {e}")
    analytics_api = None

try:
    from api.campaigns.routes import campaigns_api
    print("[OK] campaigns_api imported")
except Exception as e:
    print(f"[WARN] Failed to import campaigns_api: {e}")
    import traceback
    traceback.print_exc()
    campaigns_api = None

try:
    from api.rules.routes import rules_api
    print("[OK] rules_api imported")
except Exception as e:
    print(f"[WARN] Failed to import rules_api: {e}")
    rules_api = None

try:
    from api.enterprise.routes import enterprise_api
    print("[OK] enterprise_api imported")
except Exception as e:
    print(f"[WARN] Failed to import enterprise_api: {e}")
    enterprise_api = None

try:
    from test_routes import test_bp
    print("[OK] test_bp imported")
except Exception as e:
    print(f"[WARN] Failed to import test_bp: {e}")
    test_bp = None

try:
    from debug_routes import debug_bp
    print("[OK] debug_bp imported")
except Exception as e:
    print(f"[WARN] Failed to import debug_bp: {e}")
    debug_bp = None

# Configuration: use only Railway backend vars. Derive secrets from SUPABASE_SERVICE_ROLE_KEY when set.
def _derived_secret(suffix: str) -> str:
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if key:
        import hashlib
        return hashlib.sha256((key + suffix).encode()).hexdigest()[:64]
    return 'your-secret-key-change-in-production'
app.config['SECRET_KEY'] = _derived_secret('secret')
app.config['JWT_SECRET_KEY'] = _derived_secret('jwt')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)
app.config['JWT_IDENTITY_CLAIM'] = 'sub'
app.config['JWT_JSON_KEY'] = 'access_token'
app.config['JWT_ALGORITHM'] = 'HS256'
app.config['JWT_TOKEN_LOCATION'] = ['headers']
app.config['JWT_HEADER_NAME'] = 'Authorization'
app.config['JWT_HEADER_TYPE'] = 'Bearer'

# Initialize extensions
try:
    jwt.init_app(app)
    print("[OK] JWT extension initialized")
except Exception as e:
    print(f"[WARN] Failed to initialize JWT: {e}")
    # Continue anyway - health endpoint doesn't need JWT

# Add backlink headers to all responses
@app.after_request
def add_backlink_headers(response):
    """Add Trevnoctilla backlink headers to all API responses"""
    # Only add if not already set (to avoid overriding specific routes)
    if 'X-Powered-By' not in response.headers:
        response.headers['X-Powered-By'] = 'Trevnoctilla'
    if 'X-Service-URL' not in response.headers:
        response.headers['X-Service-URL'] = 'https://www.trevnoctilla.com'
    # Add Link header for SEO backlink
    existing_link = response.headers.get('Link', '')
    if 'trevnoctilla.com' not in existing_link:
        link_header = '<https://www.trevnoctilla.com>; rel="canonical"'
        if existing_link:
            response.headers['Link'] = f'{existing_link}, {link_header}'
        else:
            response.headers['Link'] = link_header
    return response

# Initialize database synchronously (required for admin endpoints)
try:
    print("[RELOAD] Initializing database...")
    init_db(app)
    print("[OK] Database initialized successfully")
except Exception as e:
    print(f"[WARN] Database initialization failed: {e}")
    print("[WARN] App will continue to start, but database features may not work")
    import traceback
    traceback.print_exc()

CORS(app, origins=[
    "https://web-production-ef253.up.railway.app",
    "https://web-production-471ae.up.railway.app",
    "https://trevnoctilla.com",
    "https://www.trevnoctilla.com",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8080"
], supports_credentials=True, 
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    expose_headers=["Content-Type", "Content-Length"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])  # Enable CORS for specific origins with custom headers

# Define folder constants before they are used
UPLOAD_FOLDER = "uploads"
EDITED_FOLDER = "edited"
HTML_FOLDER = "saved_html"
VIDEO_FOLDER = "converted_videos"
AUDIO_FOLDER = "converted_audio"

# Create necessary directories
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EDITED_FOLDER, exist_ok=True)
os.makedirs(HTML_FOLDER, exist_ok=True)
os.makedirs(VIDEO_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

# PDF Upload endpoint for frontend tools
@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Upload PDF file for processing"""
    try:
        if "pdf" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files["pdf"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400
        
        # Secure filename and make unique
        filename = secure_filename(file.filename)
        # Add unique prefix to prevent conflicts
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Save file
        file.save(filepath)
        
        return jsonify({
            "success": True,
            "filename": unique_filename,
            "message": "File uploaded successfully"
        }), 200
        
    except Exception as e:
        print(f"ERROR: Failed to upload file: {str(e)}")
        return jsonify({"error": f"Failed to upload file: {str(e)}"}), 500

@app.route("/test-ffmpeg")
def test_ffmpeg():
    """Test if FFmpeg is working properly"""
    try:
        import subprocess
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            return jsonify({
                "status": "ok",
                "message": "FFmpeg is working",
                "version": version_line,
                "return_code": result.returncode
            })
        else:
            return jsonify({
                "status": "error",
                "message": "FFmpeg command failed",
                "return_code": result.returncode,
                "stderr": result.stderr
            })
    except FileNotFoundError:
        return jsonify({
            "status": "error",
            "message": "FFmpeg not found in PATH"
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            "status": "error",
            "message": "FFmpeg command timed out"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error testing FFmpeg: {str(e)}"
        })

# Global progress tracking
conversion_progress = {}

# Global process tracking for cancellation
running_processes = {}

# File cleanup system
def cleanup_old_files():
    """Clean up files older than 1 hour from all output directories"""
    try:
        current_time = time.time()
        cleanup_directories = [UPLOAD_FOLDER, EDITED_FOLDER, HTML_FOLDER, VIDEO_FOLDER, AUDIO_FOLDER]
        
        for directory in cleanup_directories:
            if os.path.exists(directory):
                for filename in os.listdir(directory):
                    file_path = os.path.join(directory, filename)
                    if os.path.isfile(file_path):
                        file_age = current_time - os.path.getmtime(file_path)
                        # Delete files older than 1 hour
                        if file_age > 3600:  # 1 hour in seconds
                            try:
                                os.remove(file_path)
                                print(f"Cleaned up old file: {file_path}")
                            except Exception as e:
                                print(f"Error deleting file {file_path}: {e}")
    except Exception as e:
        print(f"Error in cleanup_old_files: {e}")

def cleanup_specific_file(file_path):
    """Clean up a specific file after download completion"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Cleaned up file after download: {file_path}")
            return True
    except Exception as e:
        print(f"Error deleting file {file_path}: {e}")
    return False

def cleanup_session_files(session_id):
    """Clean up all files for a specific session"""
    try:
        cleanup_directories = [UPLOAD_FOLDER, EDITED_FOLDER, HTML_FOLDER, VIDEO_FOLDER, AUDIO_FOLDER]
        
        for directory in cleanup_directories:
            if os.path.exists(directory):
                pattern = os.path.join(directory, f"*{session_id}*")
                files_to_delete = glob.glob(pattern)
                for file_path in files_to_delete:
                    try:
                        os.remove(file_path)
                        print(f"Cleaned up session file: {file_path}")
                    except Exception as e:
                        print(f"Error deleting session file {file_path}: {e}")
    except Exception as e:
        print(f"Error in cleanup_session_files: {e}")

# Start background cleanup thread
def background_cleanup():
    """Background thread that runs cleanup every 30 minutes"""
    while True:
        time.sleep(1800)  # 30 minutes
        cleanup_old_files()

# Start the background cleanup thread
cleanup_thread = threading.Thread(target=background_cleanup, daemon=True)
cleanup_thread.start()

# Add cleanup endpoints
@app.route('/cleanup-file', methods=['POST'])
def cleanup_file_endpoint():
    """Clean up a specific file after download completion"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({'success': False, 'error': 'No file path provided'}), 400
        
        success = cleanup_specific_file(file_path)
        
        if success:
            return jsonify({'success': True, 'message': 'File cleaned up successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to clean up file'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/cleanup-session', methods=['POST'])
def cleanup_session_endpoint():
    """Clean up all files for a specific session"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'success': False, 'error': 'No session ID provided'}), 400
        
        cleanup_session_files(session_id)
        return jsonify({'success': True, 'message': 'Session files cleaned up successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/cleanup-all', methods=['POST'])
def cleanup_all_endpoint():
    """Manually trigger cleanup of all old files"""
    try:
        cleanup_old_files()
        return jsonify({'success': True, 'message': 'All old files cleaned up successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        print(f"DEBUG: Upload endpoint called")
        print(f"DEBUG: Upload folder: {UPLOAD_FOLDER}")
        print(f"DEBUG: Upload folder exists: {os.path.exists(UPLOAD_FOLDER)}")
        print(f"DEBUG: Upload folder contents before: {os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else 'Folder does not exist'}")
        
        if "pdf" not in request.files:
            print("ERROR: No pdf file in request")
            return "No file uploaded", 400
        file = request.files["pdf"]
        if file.filename == "":
            print("ERROR: No filename provided")
            return "No selected file", 400

        print(f"DEBUG: Uploading file: {file.filename}")
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        print(f"DEBUG: Saving to: {filepath}")
        
        try:
            file.save(filepath)
            print(f"DEBUG: File saved successfully")
            print(f"DEBUG: File exists after save: {os.path.exists(filepath)}")
            print(f"DEBUG: Upload folder contents after: {os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else 'Folder does not exist'}")
        except Exception as e:
            print(f"ERROR: Failed to save file: {str(e)}")
            return f"Failed to save file: {str(e)}", 500
            
        return redirect(url_for("convert_pdf", filename=file.filename))
    
    # For GET requests, return API info with backlinks
    if request.headers.get('Accept', '').startswith('application/json'):
        response = jsonify({
            "service": "Trevnoctilla API Backend",
            "description": "Free Online PDF Editor & File Converter API",
            "website": "https://www.trevnoctilla.com",
            "api_docs": "https://www.trevnoctilla.com/api-docs",
            "features": [
                "PDF editing and manipulation",
                "Video, audio, and image conversion",
                "QR code generation",
                "File processing APIs"
            ],
            "status": "operational"
        })
        # Add backlink headers
        response.headers["X-Powered-By"] = "Trevnoctilla"
        response.headers["X-Service-URL"] = "https://www.trevnoctilla.com"
        response.headers["Link"] = '<https://www.trevnoctilla.com>; rel="canonical", <https://www.trevnoctilla.com/api-docs>; rel="documentation"'
        return response
    
    return render_template("index.html")

@app.route("/get_page_count", methods=["POST"])
def get_page_count():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file to uploads folder for later use
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        print(f"DEBUG: Saved file as {file.filename}")
        
        # Open PDF and get page count
        doc = fitz.open(filepath)
        page_count = len(doc)
        doc.close()
        
        response_data = {"page_count": page_count, "filename": file.filename}
        print(f"DEBUG: Returning response: {response_data}")
        return jsonify(response_data)
    except Exception as e:
        print(f"DEBUG: Error in get_page_count: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/pdf_preview", methods=["POST"])
def pdf_preview():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file temporarily
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # Open PDF and get first page as image
        doc = fitz.open(filepath)
        page = doc[0]  # Get first page
        
        # Render page as image
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        
        doc.close()
        
        # Clean up temporary file
        os.remove(filepath)
        
        # Return base64 encoded image
        img_base64 = base64.b64encode(img_data).decode()
        return jsonify({"preview_image": f"data:image/png;base64,{img_base64}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/pdf_info/<filename>")
def get_pdf_info(filename):
    """Get PDF information including page count"""
    print(f"DEBUG: pdf_info called with filename: {filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    print(f"DEBUG: Looking for file at: {filepath}")
    print(f"DEBUG: File exists: {os.path.exists(filepath)}")
    print(f"DEBUG: Upload folder contents: {os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else 'Folder does not exist'}")
    
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        return jsonify({"error": f"File not found: {filename}"}), 404
    
    try:
        doc = fitz.open(filepath)
        page_count = len(doc)
        doc.close()
        print(f"DEBUG: Successfully got page count: {page_count}")
        return jsonify({
            "filename": filename,
            "page_count": page_count
        })
    except Exception as e:
        print(f"ERROR: Exception in get_pdf_info: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/pdf_thumbnail/<filename>/<int:page_num>")
def get_pdf_thumbnail(filename, page_num):
    """Get thumbnail image for a specific page"""
    print(f"DEBUG: thumbnail called with filename: {filename}, page: {page_num}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    print(f"DEBUG: File path: {filepath}")
    print(f"DEBUG: File exists: {os.path.exists(filepath)}")
    
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        return jsonify({"error": f"File not found: {filename}"}), 404
    
    try:
        doc = fitz.open(filepath)
        if page_num < 1 or page_num > len(doc):
            return jsonify({"error": "Invalid page number"}), 400
        
        page = doc[page_num - 1]  # Convert to 0-based index
        
        # Check if high quality is requested
        quality = request.args.get('quality', 'normal')
        
        if quality == 'high':
            # High quality for preview - use higher resolution
            mat = fitz.Matrix(2.0, 2.0)  # 2x resolution for crisp display
            pix = page.get_pixmap(matrix=mat)
            # If too large, scale down proportionally but keep it high quality
            if pix.width > 2000:
                scale = 2000 / pix.width
                mat = fitz.Matrix(2.0 * scale, 2.0 * scale)
                pix = page.get_pixmap(matrix=mat)
        else:
            # Normal thumbnail size
            mat = fitz.Matrix(0.3, 0.3)  # Scale down to 30% for thumbnail
        
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        
        doc.close()
        
        return Response(img_data, mimetype="image/png")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/split_pdf", methods=["POST"])
def split_pdf():
    """Split PDF into individual pages"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        pages = data.get('pages', [])
        
        if not filename or not pages:
            return jsonify({"error": "Filename and pages are required"}), 400
        
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "PDF file not found"}), 404
        
        # Open the PDF
        doc = fitz.open(filepath)
        total_pages = len(doc)
        
        # Validate page numbers
        valid_pages = [p for p in pages if 1 <= p <= total_pages]
        if not valid_pages:
            return jsonify({"error": "No valid pages to split"}), 400
        
        download_urls = []
        
        # Create individual PDFs for each selected page
        for page_num in valid_pages:
            # Create a new PDF with just this page
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=page_num-1, to_page=page_num-1)
            
            # Generate filename for this page
            base_name = os.path.splitext(filename)[0]
            page_filename = f"{base_name}_page_{page_num}.pdf"
            page_filepath = os.path.join(EDITED_FOLDER, page_filename)
            
            # Save the page
            new_doc.save(page_filepath)
            new_doc.close()
            
            # Add download URL
            download_urls.append(f"/download_split/{page_filename}")
        
        doc.close()
        
        # Generate view URLs for each split page
        base_name = os.path.splitext(filename)[0]
        view_urls = [f"/view_split/{base_name}_page_{page_num}.pdf" for page_num in valid_pages]
        
        return jsonify({
            "success": True,
            "message": f"PDF split into {len(valid_pages)} pages",
            "downloadUrls": download_urls,
            "viewUrls": view_urls,
            "pages": valid_pages
        })
        
    except Exception as e:
        print(f"Error splitting PDF: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/download_split/<path:filename>")
def download_split_page(filename):
    """Download a split PDF page"""
    try:
        # URL decode the filename to handle spaces and special characters
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        filepath = os.path.join(EDITED_FOLDER, decoded_filename)
        
        if not os.path.exists(filepath):
            return jsonify({"error": f"File not found: {decoded_filename}"}), 404
        
        return send_file(filepath, as_attachment=True, download_name=decoded_filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/view_split/<path:filename>")
def view_split_page(filename):
    """View a split PDF page in browser"""
    try:
        # URL decode the filename to handle spaces and special characters
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        filepath = os.path.join(EDITED_FOLDER, decoded_filename)
        
        if not os.path.exists(filepath):
            return jsonify({"error": f"File not found: {decoded_filename}"}), 404
        
        return send_file(filepath, as_attachment=False, download_name=decoded_filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert/<filename>")
def convert_pdf(filename):
    print(f"DEBUG: Convert endpoint called with filename: {filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    page_num = request.args.get('page', type=int, default=None)  # No default page
    print(f"DEBUG: File path: {filepath}")
    print(f"DEBUG: Page number (0-based): {page_num}")
    print(f"DEBUG: File exists: {os.path.exists(filepath)}")
    print(f"DEBUG: Upload folder contents: {os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else 'Folder does not exist'}")
    
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        return jsonify({"error": f"File not found: {filename}"}), 404
    
    try:
        doc = fitz.open(filepath)
        print(f"DEBUG: PDF opened successfully, total pages: {len(doc)}")
        pages_data = []
        image_counter = 0
        
        # If page number is specified, only show that page, otherwise show all pages
        if page_num is not None and page_num >= 1 and page_num <= len(doc):
            page_range = [page_num - 1]  # Convert to 0-based index
            print(f"DEBUG: Showing specific page {page_num}")
        else:
            page_range = range(len(doc))
            print(f"DEBUG: Showing all pages, range: {list(range(1, len(doc) + 1))}")
        
        for page_idx in page_range:
            print(f"DEBUG: Processing page {page_idx + 1}")
            page = doc[page_idx]
            page_dict = page.get_text("dict")
            print(f"DEBUG: Page {page_idx + 1} has {len(page_dict['blocks'])} blocks")
            
            page_html = f'<div class="pdf-page" data-page="{page_idx + 1}" data-width="{page.rect.width}" data-height="{page.rect.height}">'
            
            for block in page_dict["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        line_html = '<div class="text-line">'
                        for span in line["spans"]:
                            text = span["text"]
                            if text.strip():
                                bbox = span["bbox"]
                                font = span["font"]
                                size = span["size"]
                                flags = span["flags"]
                                
                                style = f"position: absolute; left: {bbox[0]}px; top: {bbox[1]}px; font-size: {size}px; font-family: {font};"
                                if flags & 2**4:
                                    style += " font-weight: bold;"
                                if flags & 2**1:
                                    style += " font-style: italic;"
                                
                                line_html += f'<span class="text-span editable-text" data-text="{text}" style="{style}">{text}</span>'
                        line_html += '</div>'
                        page_html += line_html
                
                elif "image" in block:
                    image_counter += 1
                    bbox = block["bbox"]
                    image_data = block["image"]
                    image_base64 = base64.b64encode(image_data).decode()
                    
                    style = f"position: absolute; left: {bbox[0]}px; top: {bbox[1]}px; width: {bbox[2] - bbox[0]}px; height: {bbox[3] - bbox[1]}px;"
                    page_html += f'<img class="editable-image" data-image-id="{image_counter}" src="data:image/png;base64,{image_base64}" style="{style}">'
            
            page_html += '</div>'
            pages_data.append({
                'html': page_html,
                'width': page.rect.width,
                'height': page.rect.height
            })
            print(f"DEBUG: Page {page_idx + 1} HTML length: {len(page_html)}")
        
        doc.close()
        print(f"DEBUG: Total pages processed: {len(pages_data)}")
        print(f"DEBUG: Rendering template with {len(pages_data)} pages")
        
        # Force template reload - clear all caches
        import flask.templating
        import jinja2
        # Clear Jinja2 template cache
        if hasattr(app, 'jinja_env'):
            app.jinja_env.cache.clear()
        # Clear Flask template cache if it exists
        try:
            if hasattr(flask.templating, '_template_cache'):
                flask.templating._template_cache.clear()
        except:
            pass
        # Check if mobile request - check both query param and request args
        mobile_param = request.args.get('mobile', 'false')
        is_mobile = str(mobile_param).lower() == 'true'
        
        print(f" [TEMPLATE SELECTION] Mobile param: '{mobile_param}', is_mobile: {is_mobile}")
        print(f" [TEMPLATE SELECTION] All request args: {dict(request.args)}")
        
        # Force reload by touching the template file
        template_name = "converted-mobile.html" if is_mobile else "converted.html"
        template_path = os.path.join(app.template_folder, template_name)
        print(f" [TEMPLATE SELECTION] Selected template: {template_name}")
        print(f" [TEMPLATE SELECTION] Template folder: {app.template_folder}")
        print(f" [TEMPLATE SELECTION] Template path: {template_path}")
        print(f" [TEMPLATE SELECTION] Template exists: {os.path.exists(template_path)}")
        
        # Fallback to desktop template if mobile template doesn't exist
        if is_mobile and not os.path.exists(template_path):
            print(f"[WARN] [TEMPLATE SELECTION] WARNING: Mobile template not found, falling back to desktop template")
            template_name = "converted.html"
            template_path = os.path.join(app.template_folder, template_name)
            is_mobile = False  # Reset flag since we're using desktop template
        
        if not os.path.exists(template_path):
            print(f"ERROR: Template not found: {template_path}")
            return jsonify({"error": f"Template not found: {template_name}"}), 500
        
        # Force clear template cache
        if hasattr(app, 'jinja_env'):
            app.jinja_env.cache.clear()
        os.utime(template_path, None)  # Touch the file
        
        print(f"DEBUG: Rendering template: {template_name} with {len(pages_data)} pages")
        try:
            response = make_response(render_template(template_name, 
                                                      filename=filename, 
                                                      pages=pages_data))
            print(f"DEBUG: Template rendered successfully")
        except Exception as render_error:
            print(f"ERROR: Template rendering failed: {str(render_error)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return jsonify({"error": f"Template rendering failed: {str(render_error)}"}), 500
        # Add cache-busting headers
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['X-Template-Name'] = template_name  # Debug header
        response.headers['X-Is-Mobile'] = str(is_mobile)  # Debug header
        return response
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        error_msg = str(e)
        print(f"ERROR converting PDF: {error_msg}")
        print(f"Traceback:\n{error_trace}")
        # Return error with details for debugging - ensure it's JSON
        try:
            return jsonify({
                "error": f"Error converting PDF: {error_msg}",
                "error_type": type(e).__name__,
                "traceback_lines": error_trace.split('\n')[-10:] if error_trace else []
            }), 500
        except:
            # Fallback if jsonify fails
            return f"Error converting PDF: {error_msg}", 500

@app.route("/editor/<filename>")
def convert_pdf_for_editor(filename):
    print(f"DEBUG: Editor endpoint called with filename: {filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    print(f"DEBUG: File path: {filepath}")
    print(f"DEBUG: File exists: {os.path.exists(filepath)}")
    
    try:
        doc = fitz.open(filepath)
        print(f"DEBUG: PDF opened successfully, total pages: {len(doc)}")
        pages_data = []
        image_counter = 0
        
        # Show all pages for editor
        page_range = range(len(doc))
        print(f"DEBUG: Showing all pages, range: {list(range(1, len(doc) + 1))}")
        
        for page_idx in page_range:
            print(f"DEBUG: Processing page {page_idx + 1}")
            page = doc[page_idx]
            page_dict = page.get_text("dict")
            print(f"DEBUG: Page {page_idx + 1} has {len(page_dict['blocks'])} blocks")
            
            page_html = f'<div class="pdf-page" data-page="{page_idx + 1}" data-width="{page.rect.width}" data-height="{page.rect.height}">'
            
            for block in page_dict["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        line_html = '<div class="text-line">'
                        for span in line["spans"]:
                            text = span["text"]
                            if text.strip():
                                bbox = span["bbox"]
                                font = span["font"]
                                size = span["size"]
                                flags = span["flags"]
                                
                                style = f"position: absolute; left: {bbox[0]}px; top: {bbox[1]}px; font-size: {size}px; font-family: {font};"
                                if flags & 2**4:
                                    style += " font-weight: bold;"
                                if flags & 2**1:
                                    style += " font-style: italic;"
                                
                                line_html += f'<span class="text-span editable-text" data-text="{text}" style="{style}">{text}</span>'
                        line_html += '</div>'
                        page_html += line_html
                
                elif "image" in block:
                    image_counter += 1
                    bbox = block["bbox"]
                    image_data = block["image"]
                    image_base64 = base64.b64encode(image_data).decode()
                    
                    style = f"position: absolute; left: {bbox[0]}px; top: {bbox[1]}px; width: {bbox[2] - bbox[0]}px; height: {bbox[3] - bbox[1]}px;"
                    page_html += f'<img class="editable-image" data-image-id="{image_counter}" src="data:image/png;base64,{image_base64}" style="{style}">'
            
            page_html += '</div>'
            pages_data.append({
                'html': page_html,
                'width': page.rect.width,
                'height': page.rect.height
            })
            print(f"DEBUG: Page {page_idx + 1} HTML length: {len(page_html)}")
        
        doc.close()
        print(f"DEBUG: Total pages processed: {len(pages_data)}")
        print(f"DEBUG: Rendering editor template with {len(pages_data)} pages")
        
        return render_template("editor.html", 
                             filename=filename, 
                             pages=pages_data)
    
    except Exception as e:
        return f"Error converting PDF: {str(e)}", 500

@app.route("/convert_signature/<filename>")
def convert_pdf_for_signature(filename):
    print(f"DEBUG: Convert signature endpoint called with filename: {filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    print(f"DEBUG: File path: {filepath}")
    print(f"DEBUG: File exists: {os.path.exists(filepath)}")
    
    try:
        doc = fitz.open(filepath)
        print(f"DEBUG: PDF opened successfully, total pages: {len(doc)}")
        
        # Always show all pages for signature positioning
        page_range = range(len(doc))
        print(f"DEBUG: Showing all pages, range: {list(page_range)}")
        
        # Create a multi-page HTML for signature positioning
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    margin: 0;
                    padding: 20px;
                    background: #f5f5f5;
                    font-family: Arial, sans-serif;
                }
                .pdf-container {
                    display: flex;
                    flex-direction: column;
                    gap: 20px;
                    max-width: 1200px;
                    margin: 0 auto;
                }
                .pdf-page {
                    position: relative;
                    background: white;
                    transform-origin: top left;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    border-radius: 4px;
                    overflow: hidden;
                }
                .page-header {
                    background: #e9ecef;
                    padding: 8px 12px;
                    font-size: 12px;
                    color: #6c757d;
                    border-bottom: 1px solid #dee2e6;
                    cursor: pointer;
                    user-select: none;
                }
                .page-header:hover {
                    background: #dee2e6;
                }
                .page-header.selected {
                    background: #007bff;
                    color: white;
                }
                .page-content {
                    position: relative;
                }
                .text-span {
                    position: absolute;
                    white-space: nowrap;
                }
                .editable-image {
                    position: absolute;
                }
            </style>
        </head>
        <body>
        <div class="pdf-container">
        """
        
        for page_idx in page_range:
            print(f"DEBUG: Processing page {page_idx + 1} for signature")
            page = doc[page_idx]
            page_dict = page.get_text("dict")
            print(f"DEBUG: Page {page_idx + 1} has {len(page_dict['blocks'])} blocks")
            
            # Scale factor to fit pages nicely (max width 800px)
            scale_factor = min(800 / page.rect.width, 1.0)
            scaled_width = page.rect.width * scale_factor
            scaled_height = page.rect.height * scale_factor
            
            page_html = f'''
            <div class="pdf-page" data-page="{page_idx + 1}" style="width: {scaled_width}px;">
                <div class="page-header" onclick="selectPage({page_idx + 1})">Page {page_idx + 1}</div>
                <div class="page-content" style="width: {scaled_width}px; height: {scaled_height}px;">
            '''
            
            for block in page_dict["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        line_html = '<div class="text-line">'
                        for span in line["spans"]:
                            text = span["text"]
                            if text.strip():
                                bbox = span["bbox"]
                                font = span["font"]
                                size = span["size"]
                                flags = span["flags"]
                                
                                style = f"position: absolute; left: {bbox[0] * scale_factor}px; top: {bbox[1] * scale_factor}px; font-size: {size * scale_factor}px; font-family: {font};"
                                if flags & 2**4:
                                    style += " font-weight: bold;"
                                if flags & 2**1:
                                    style += " font-style: italic;"
                                
                                line_html += f'<span class="text-span" style="{style}">{text}</span>'
                        line_html += '</div>'
                        page_html += line_html
                
                elif "image" in block:
                    bbox = block["bbox"]
                    image_data = block["image"]
                    image_base64 = base64.b64encode(image_data).decode()
                    
                    style = f"position: absolute; left: {bbox[0] * scale_factor}px; top: {bbox[1] * scale_factor}px; width: {(bbox[2] - bbox[0]) * scale_factor}px; height: {(bbox[3] - bbox[1]) * scale_factor}px;"
                    page_html += f'<img class="editable-image" src="data:image/png;base64,{image_base64}" style="{style}">'
            
            page_html += '''
                </div>
            </div>
            '''
            html_content += page_html
            print(f"DEBUG: Page {page_idx + 1} HTML length: {len(page_html)}")
        
        html_content += """
        </div>
        <script>
            function selectPage(pageNum) {
                // Remove previous selection
                document.querySelectorAll('.page-header').forEach(header => {
                    header.classList.remove('selected');
                });
                
                // Add selection to clicked page
                const clickedHeader = document.querySelector(`[data-page="${pageNum}"] .page-header`);
                clickedHeader.classList.add('selected');
                
                // Notify parent window about page selection
                window.parent.postMessage({
                    type: 'pageSelected',
                    page: pageNum
                }, '*');
            }
        </script>
        </body>
        </html>
        """
        
        doc.close()
        print(f"DEBUG: Returning multi-page HTML for signature positioning")
        
        return html_content
    
    except Exception as e:
        return f"Error converting PDF for signature: {str(e)}", 500

@app.route("/save_edits/<filename>", methods=["POST"])
def save_edits(filename):
    try:
        # Get the request data
        data = request.get_json()
        edits = data.get("edits", []) if data else []
        
        print(f"Received edits for {filename}: {len(edits)} edits")
        
        if not edits:
            return jsonify({"status": "success", "message": "No edits to save"})
            
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        if not os.path.exists(filepath):
            return jsonify({"status": "error", "message": f"Original file {filename} not found"}), 404
            
        edited_path = os.path.join(EDITED_FOLDER, f"edited_{filename}")

        doc = fitz.open(filepath)
        
        for edit in edits:
            try:
                if not isinstance(edit, dict):
                    print(f"Skipping invalid edit: {edit}")
                    continue
                    
                page_num = edit.get("page", 1) - 1
                edit_type = edit.get("type", "")
                
                if page_num < 0 or page_num >= len(doc):
                    print(f"Skipping edit for invalid page: {page_num}")
                    continue
                    
                page = doc[page_num]
                
                if edit_type == "text":
                    old_text = edit.get("old_text", "")
                    new_text = edit.get("new_text", "")
                    
                    if old_text and new_text:
                        text_instances = page.search_for(old_text)
                        for inst in text_instances:
                            rect = fitz.Rect(inst)
                            page.add_redact_annot(rect)
                            page.apply_redactions()
                            page.insert_text((inst.x0, inst.y1), new_text, fontsize=12)
                
                elif edit_type == "image":
                    image_id = edit.get("image_id")
                    new_image_data = edit.get("image_data")
                    
                    if image_id and new_image_data:
                        image_list = page.get_images()
                        if 1 <= image_id <= len(image_list):
                            xref = image_list[image_id - 1][0]
                            if ',' in new_image_data:
                                image_data = base64.b64decode(new_image_data.split(',')[1])
                                doc.update_stream(xref, image_data)
                        
            except Exception as edit_error:
                print(f"Error processing individual edit: {edit_error}")
                continue
        
        doc.save(edited_path)
        doc.close()
        
        return jsonify({"status": "success", "message": "Edits saved successfully"})
    
    except Exception as e:
        print(f"Error in save_edits: {str(e)}")  # Debug logging
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/save_html/<filename>", methods=["POST"])
def save_html(filename):
    try:
        data = request.json
        html_content = data.get("html_content")
        session_id = data.get("session_id")
        
        if not html_content:
            return jsonify({"status": "error", "message": "No HTML content provided"}), 400
        
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())[:8]  # Short session ID
        
        # Create a clean filename with session ID
        base_name = os.path.splitext(filename)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_filename = f"session_{session_id}_{base_name}_{timestamp}.html"
        html_path = os.path.join(HTML_FOLDER, html_filename)
        
        # Save the HTML file
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return jsonify({
            "status": "success", 
            "message": "HTML saved successfully",
            "html_filename": html_filename,
            "session_id": session_id
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/cleanup_session/<session_id>", methods=["POST"])
def cleanup_session(session_id):
    """Clean up all HTML files for a specific session"""
    try:
        deleted_count = cleanup_session_files(session_id)
        return jsonify({
            "status": "success",
            "message": f"Cleaned up {deleted_count} files for session {session_id}",
            "deleted_count": deleted_count
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/view_html/<html_filename>")
def view_html(html_filename):
    try:
        html_path = os.path.join(HTML_FOLDER, html_filename)
        if not os.path.exists(html_path):
            return "HTML file not found", 404
        
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        return html_content
    
    except Exception as e:
        return f"Error loading HTML: {str(e)}", 500

@app.route("/download_pdf/<html_filename>")
def download_pdf(html_filename):
    try:
        html_path = os.path.join(HTML_FOLDER, html_filename)
        if not os.path.exists(html_path):
            return jsonify({"status": "error", "message": "HTML file not found"}), 404
        
        # Convert HTML to PDF
        pdf_filename = html_filename.replace('.html', '.pdf')
        pdf_path = os.path.join(HTML_FOLDER, pdf_filename)
        
        # Read HTML content
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Parse HTML to extract page content using regex
        import re
        
        # Extract page divs with their content
        page_pattern = r'<div[^>]*class="[^"]*pdf-page[^"]*"[^>]*data-page="(\d+)"[^>]*>(.*?)</div>'
        pages = re.findall(page_pattern, html_content, re.IGNORECASE | re.DOTALL)
        
        # Create PDF with proper formatting
        doc = fitz.open()
        
        for page_num, page_content in pages:
            # Create a new page for each PDF page
            page = doc.new_page(width=595, height=842)  # A4 size
            y_position = 50
            
            # Extract text spans from this page
            text_span_pattern = r'<span[^>]*class="[^"]*editable-text[^"]*"[^>]*style="[^"]*left: ([^;]+)px; top: ([^;]+)px;[^"]*"[^>]*>([^<]*)</span>'
            text_spans = re.findall(text_span_pattern, page_content, re.IGNORECASE)
            
            # Extract images from this page
            image_pattern = r'<img[^>]*class="[^"]*editable-image[^"]*"[^>]*style="[^"]*left: ([^;]+)px; top: ([^;]+)px; width: ([^;]+)px; height: ([^;]+)px;[^"]*"[^>]*src="data:image/png;base64,([^"]*)"[^>]*>'
            images = re.findall(image_pattern, page_content, re.IGNORECASE)
            
            # Add text content to PDF page
            for left, top, text_content in text_spans:
                if text_content and text_content.strip():
                    try:
                        x_pos = float(left)
                        y_pos = float(top)
                        clean_text = text_content.strip()
                        # Decode HTML entities
                        clean_text = clean_text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
                        
                        # Convert PDF coordinates (top-left origin) to PyMuPDF coordinates
                        # Scale positions to fit A4 page
                        scale_x = 595 / 800  # Adjust based on your PDF page width
                        scale_y = 842 / 1000  # Adjust based on your PDF page height
                        
                        pdf_x = x_pos * scale_x
                        pdf_y = y_pos * scale_y
                        
                        # Ensure text fits within page bounds
                        if pdf_x < 0:
                            pdf_x = 50
                        if pdf_y < 0:
                            pdf_y = 50
                        if pdf_x > 545:
                            pdf_x = 545
                        if pdf_y > 792:
                            pdf_y = 792
                        
                        page.insert_text((pdf_x, pdf_y), clean_text, fontsize=10)
                    except (ValueError, TypeError):
                        # If position parsing fails, just add text sequentially
                        page.insert_text((50, y_position), clean_text, fontsize=10)
                        y_position += 15
            
            # Add images to PDF page
            for left, top, width, height, image_data in images:
                try:
                    x_pos = float(left)
                    y_pos = float(top)
                    img_width = float(width)
                    img_height = float(height)
                    
                    # Scale positions to fit A4 page
                    scale_x = 595 / 800
                    scale_y = 842 / 1000
                    
                    pdf_x = x_pos * scale_x
                    pdf_y = y_pos * scale_y
                    pdf_width = img_width * scale_x
                    pdf_height = img_height * scale_y
                    
                    # Ensure image fits within page bounds
                    if pdf_x < 0:
                        pdf_x = 50
                    if pdf_y < 0:
                        pdf_y = 50
                    if pdf_x + pdf_width > 545:
                        pdf_width = 545 - pdf_x
                    if pdf_y + pdf_height > 792:
                        pdf_height = 792 - pdf_y
                    
                    if pdf_width > 0 and pdf_height > 0:
                        # Decode base64 image and insert
                        import base64
                        image_bytes = base64.b64decode(image_data)
                        rect = fitz.Rect(pdf_x, pdf_y, pdf_x + pdf_width, pdf_y + pdf_height)
                        page.insert_image(rect, pixmap=fitz.Pixmap(fitz.csRGB, image_bytes))
                except (ValueError, TypeError, Exception):
                    # Skip problematic images
                    continue
        
        doc.save(pdf_path)
        doc.close()
        
        # Send PDF file for download
        return send_file(pdf_path, as_attachment=True, download_name=pdf_filename)
    
    except Exception as e:
        print(f"Error in download_pdf: {str(e)}")  # Debug logging
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/extract_text", methods=["POST"])
def extract_text():
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Save the uploaded file
        filename = file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        doc = fitz.open(filepath)
        extracted_text = ""
        page_count = len(doc)
        
        for page_num in range(page_count):
            page = doc[page_num]
            page_text = page.get_text()
            if page_text.strip():
                extracted_text += f"--- Page {page_num + 1} ---\n"
                extracted_text += page_text + "\n\n"
        
        doc.close()
        
        return jsonify({
            "status": "success",
            "filename": filename,
            "text": extracted_text,
            "page_count": page_count
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/extract_images", methods=["POST"])
def extract_images():
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Save the uploaded file
        filename = file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        doc = fitz.open(filepath)
        images_data = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                
                if pix.n - pix.alpha < 4:  # GRAY or RGB
                    img_data = pix.tobytes("png")
                    img_base64 = base64.b64encode(img_data).decode()
                    
                    images_data.append({
                        "page": page_num + 1,
                        "image_index": img_index + 1,
                        "width": pix.width,
                        "height": pix.height,
                        "data": img_base64
                    })
                
                pix = None
        
        doc.close()
        
        return jsonify({
            "status": "success",
            "filename": filename,
            "images": images_data,
            "total_images": len(images_data)
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/merge_pdfs", methods=["POST"])
def merge_pdfs():
    try:
        print(f"DEBUG: Merge endpoint called")
        print(f"DEBUG: Request files: {request.files}")
        print(f"DEBUG: Request form: {request.form}")
        print(f"DEBUG: Request content type: {request.content_type}")
        print(f"DEBUG: Request content length: {request.content_length}")
        
        files = request.files.getlist('files')
        print(f"DEBUG: Files list length: {len(files)}")
        
        # Debug each file
        for i, file in enumerate(files):
            print(f"DEBUG: File {i}: filename='{file.filename}', content_length={file.content_length}, content_type={file.content_type}")
            if hasattr(file, 'stream'):
                print(f"DEBUG: File {i} stream position: {file.stream.tell()}")
        
        # Check if files are empty or invalid
        valid_files = []
        for i, file in enumerate(files):
            print(f"DEBUG: File {i}: filename='{file.filename}', content_length={file.content_length}")
            if file and file.filename and file.filename.strip():
                valid_files.append(file)
            else:
                print(f"DEBUG: Skipping empty/invalid file at index {i}")
        
        print(f"DEBUG: Valid files count: {len(valid_files)}")
        
        if len(valid_files) < 2:
            print(f"DEBUG: Not enough valid files: {len(valid_files)}")
            return jsonify({"status": "error", "message": f"At least 2 valid PDF files are required for merging. Found {len(valid_files)} valid files."}), 400
        
        files = valid_files
        
        # Create merged document
        merged_doc = fitz.open()
        
        for file in files:
            print(f"DEBUG: Processing file: {file.filename}")
            if file and file.filename and file.filename.endswith('.pdf'):
                # Save temporary file
                temp_path = os.path.join(UPLOAD_FOLDER, f"temp_{file.filename}")
                file.save(temp_path)
                print(f"DEBUG: Saved temp file: {temp_path}")
                
                # Open and add pages to merged document
                temp_doc = fitz.open(temp_path)
                merged_doc.insert_pdf(temp_doc)
                temp_doc.close()
                print(f"DEBUG: Added pages from {file.filename}")
                
                # Remove temporary file
                os.remove(temp_path)
            else:
                print(f"DEBUG: Skipping invalid file: {file.filename if file else 'None'}")
        
        # Generate merged filename
        merged_filename = f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        merged_path = os.path.join(HTML_FOLDER, merged_filename)
        
        # Get page count before closing
        page_count = len(merged_doc)
        
        # Save merged document
        merged_doc.save(merged_path)
        merged_doc.close()
        
        return jsonify({
            "status": "success",
            "message": f"Successfully merged {len(files)} PDF files",
            "merged_filename": merged_filename,
            "download_url": f"/download_merged/{merged_filename}",
            "file_count": len(files),
            "page_count": page_count
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download_merged/<merged_filename>")
def download_merged(merged_filename):
    try:
        merged_path = os.path.join(HTML_FOLDER, merged_filename)
        if not os.path.exists(merged_path):
            return "Merged PDF file not found", 404
        
        # Check if it's a download request (has download parameter)
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
            return send_file(merged_path, as_attachment=True, download_name=merged_filename)
        else:
            return send_file(merged_path, as_attachment=False)
    
    except Exception as e:
        return f"Error downloading merged PDF: {str(e)}", 500




@app.route('/download_split/<split_folder>/<split_filename>')
def download_split(split_folder, split_filename):
    try:
        split_path = os.path.join(HTML_FOLDER, split_folder, split_filename)
        if not os.path.exists(split_path):
            return "Split PDF file not found", 404
        
        # Check if it's a download request (has download parameter)
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
            return send_file(split_path, as_attachment=True, download_name=split_filename)
        else:
            return send_file(split_path, as_attachment=False)
    
    except Exception as e:
        return f"Error downloading split PDF: {str(e)}", 500


@app.route('/add_signature', methods=['POST'])
def add_signature():
    try:
        print(f"DEBUG: Request files: {list(request.files.keys())}")
        print(f"DEBUG: Request form: {list(request.form.keys())}")
        
        if 'pdf' not in request.files:
            return jsonify({"status": "error", "message": "No PDF file provided"}), 400
        
        pdf_file = request.files['pdf']
        if pdf_file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Get signature data and position
        signature_data = request.form.get('signature_data', '')
        page_number = int(request.form.get('page_number', 1))
        x_position = float(request.form.get('x_position', 100))
        y_position = float(request.form.get('y_position', 100))
        width = float(request.form.get('width', 200))
        height = float(request.form.get('height', 100))
        
        print(f"DEBUG: Signature data length: {len(signature_data) if signature_data else 0}")
        print(f"DEBUG: Page number: {page_number}, Position: ({x_position}, {y_position}), Size: ({width}, {height})")
        
        if not signature_data:
            return jsonify({"status": "error", "message": "No signature data provided"}), 400
        
        # Save uploaded PDF
        original_filename = pdf_file.filename
        safe_filename = "".join(c for c in original_filename if c.isalnum() or c in '._-')
        if not safe_filename.endswith('.pdf'):
            safe_filename += '.pdf'
        pdf_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        pdf_file.save(pdf_path)
        
        # Open PDF document
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        if page_number < 1 or page_number > total_pages:
            doc.close()
            os.remove(pdf_path)
            return jsonify({"status": "error", "message": f"Invalid page number. PDF has {total_pages} pages"}), 400
        
        # Get the specific page
        page = doc[page_number - 1]
        page_rect = page.rect
        
        # Convert signature data from base64 to image
        import base64
        import io
        from PIL import Image
        
        # Remove data URL prefix if present
        if signature_data.startswith('data:image'):
            signature_data = signature_data.split(',')[1]
        
        # Decode base64 image
        signature_bytes = base64.b64decode(signature_data)
        signature_image = Image.open(io.BytesIO(signature_bytes))
        
        # Convert PIL image to bytes
        img_byte_arr = io.BytesIO()
        signature_image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        
        # Create a temporary image file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_img_path = os.path.join(UPLOAD_FOLDER, f"temp_signature_{timestamp}.png")
        with open(temp_img_path, 'wb') as f:
            f.write(img_byte_arr)
        
        # Create signature rectangle
        signature_rect = fitz.Rect(x_position, y_position, x_position + width, y_position + height)
        
        # Insert signature image into PDF
        page.insert_image(signature_rect, filename=temp_img_path)
        
        # Generate output filename
        base_name = os.path.splitext(safe_filename)[0]
        signed_filename = f"{base_name}_signed.pdf"
        signed_path = os.path.join(HTML_FOLDER, signed_filename)
        
        # Save the signed PDF
        doc.save(signed_path)
        doc.close()
        
        # Clean up temporary files
        os.remove(pdf_path)
        os.remove(temp_img_path)
        
        return jsonify({
            "status": "success",
            "message": f"Signature added successfully to page {page_number}",
            "signed_filename": signed_filename,
            "download_url": f"/download_signed/{signed_filename}",
            "page_number": page_number,
            "total_pages": total_pages
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error adding signature: {str(e)}"}), 500


@app.route('/add_watermark', methods=['POST'])
def add_watermark():
    try:
        print(f"DEBUG: Watermark request files: {list(request.files.keys())}")
        print(f"DEBUG: Watermark request form: {list(request.form.keys())}")

        if 'pdf' not in request.files:
            return jsonify({"status": "error", "message": "No PDF file provided"}), 400

        pdf_file = request.files['pdf']
        if pdf_file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400

        # Get watermark data and settings
        watermark_type = request.form.get('watermark_type', 'text')  # 'text' or 'image'
        watermark_text = request.form.get('watermark_text', '')
        watermark_image_data = request.form.get('watermark_image_data', '')
        page_number = int(request.form.get('page_number', 1))
        x_position = float(request.form.get('x_position', 100))
        y_position = float(request.form.get('y_position', 100))
        width = float(request.form.get('width', 200))
        height = float(request.form.get('height', 100))
        opacity = float(request.form.get('opacity', 0.5))
        rotation = float(request.form.get('rotation', 0))
        apply_to_all = request.form.get('apply_to_all', 'false').lower() == 'true'

        print(f"DEBUG: Watermark type: {watermark_type}")
        print(f"DEBUG: Page number: {page_number}, Position: ({x_position}, {y_position}), Size: ({width}, {height})")
        print(f"DEBUG: Opacity: {opacity}, Rotation: {rotation}, Apply to all: {apply_to_all}")

        if watermark_type == 'text' and not watermark_text:
            return jsonify({"status": "error", "message": "No watermark text provided"}), 400
        if watermark_type == 'image' and not watermark_image_data:
            return jsonify({"status": "error", "message": "No watermark image provided"}), 400

        # Save the uploaded PDF
        original_filename = pdf_file.filename
        safe_filename = "".join(c for c in original_filename if c.isalnum() or c in '._-')
        if not safe_filename.endswith('.pdf'):
            safe_filename += '.pdf'
        pdf_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        pdf_file.save(pdf_path)

        # Open the PDF
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        # Determine which pages to watermark
        if apply_to_all:
            pages_to_watermark = range(total_pages)
        else:
            if page_number < 1 or page_number > total_pages:
                doc.close()
                os.remove(pdf_path)
                return jsonify({"status": "error", "message": f"Invalid page number. PDF has {total_pages} pages"}), 400
            pages_to_watermark = [page_number - 1]
        
        # Process each page
        for page_idx in pages_to_watermark:
            page = doc[page_idx]
            page_rect = page.rect
            
            if watermark_type == 'text':
                # Add text watermark
                # Calculate font size based on height
                font_size = int(height * 0.8)  # Adjust multiplier as needed
                
                # Create text insertion point
                point = fitz.Point(x_position, y_position + height)
                
                # Insert text with rotation
                page.insert_text(
                    point,
                    watermark_text,
                    fontsize=font_size,
                    color=(0.5, 0.5, 0.5),  # Gray color for watermark
                    rotate=rotation
                )
                
            elif watermark_type == 'image':
                # Add image watermark
                if watermark_image_data.startswith('data:image'):
                    watermark_image_data = watermark_image_data.split(',')[1]
                
                watermark_bytes = base64.b64decode(watermark_image_data)
                
                # Process image with PIL for better control
                from PIL import Image
                import io
                
                watermark_image = Image.open(io.BytesIO(watermark_bytes))
                
                # Apply opacity if needed
                if opacity < 1.0:
                    # Create a new image with alpha channel
                    watermark_image = watermark_image.convert("RGBA")
                    # Apply opacity
                    alpha = watermark_image.split()[-1]
                    alpha = alpha.point(lambda p: int(p * opacity))
                    watermark_image.putalpha(alpha)
                
                # Convert back to bytes
                img_byte_arr = io.BytesIO()
                watermark_image.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
                
                # Create a temporary image file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                temp_img_path = os.path.join(UPLOAD_FOLDER, f'temp_watermark_{page_idx}_{timestamp}.png')
                with open(temp_img_path, 'wb') as f:
                    f.write(img_byte_arr)
                
                # Create image rectangle
                img_rect = fitz.Rect(x_position, y_position, x_position + width, y_position + height)
                
                # Insert the watermark image
                page.insert_image(img_rect, filename=temp_img_path, rotate=rotation)
                
                # Clean up temporary file
                if os.path.exists(temp_img_path):
                    os.remove(temp_img_path)
        
        # Generate output filename
        base_name = os.path.splitext(safe_filename)[0]
        watermarked_filename = f"{base_name}_watermarked.pdf"
        watermarked_path = os.path.join(HTML_FOLDER, watermarked_filename)
        
        # Save the modified PDF
        doc.save(watermarked_path)
        doc.close()
        
        # Clean up uploaded PDF
        os.remove(pdf_path)
        
        pages_watermarked = len(pages_to_watermark)
        return jsonify({
            "status": "success",
            "message": f"Watermark added successfully to {pages_watermarked} page(s)",
            "watermarked_filename": watermarked_filename,
            "download_url": f"/download_watermarked/{watermarked_filename}",
            "pages_watermarked": pages_watermarked
        })
        
    except Exception as e:
        print(f"ERROR in add_watermark: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/download_watermarked/<watermarked_filename>')
def download_watermarked(watermarked_filename):
    try:
        watermarked_path = os.path.join(HTML_FOLDER, watermarked_filename)
        if not os.path.exists(watermarked_path):
            return "Watermarked PDF file not found", 404
        
        # Check if it's a download request (has download parameter)
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
            return send_file(watermarked_path, as_attachment=True, download_name=watermarked_filename)
        else:
            return send_file(watermarked_path, as_attachment=False)
    
    except Exception as e:
        return f"Error downloading watermarked PDF: {str(e)}", 500


@app.route('/download_signed/<signed_filename>')
def download_signed(signed_filename):
    try:
        signed_path = os.path.join(HTML_FOLDER, signed_filename)
        if not os.path.exists(signed_path):
            return "Signed PDF file not found", 404
        
        # Check if it's a download request (has download parameter)
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
            return send_file(signed_path, as_attachment=True, download_name=signed_filename)
        else:
            return send_file(signed_path, as_attachment=False)
    
    except Exception as e:
        return f"Error downloading signed PDF: {str(e)}", 500


@app.route("/convert_pdf_to_word", methods=["POST"])
def convert_pdf_to_word():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # Use the EXACT same conversion logic as /convert/<filename>
        doc = fitz.open(filepath)
        pages_data = []
        image_counter = 0
        
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_dict = page.get_text("dict")
            
            page_html = f'<div class="pdf-page" data-page="{page_idx + 1}" data-width="{page.rect.width}" data-height="{page.rect.height}">'
            
            for block in page_dict["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        line_html = '<div class="text-line">'
                        for span in line["spans"]:
                            text = span["text"]
                            if text.strip():
                                bbox = span["bbox"]
                                font = span["font"]
                                size = span["size"]
                                flags = span["flags"]
                                
                                style = f"position: absolute; left: {bbox[0]}px; top: {bbox[1]}px; font-size: {size}px; font-family: {font};"
                                if flags & 2**4:
                                    style += " font-weight: bold;"
                                if flags & 2**1:
                                    style += " font-style: italic;"
                                
                                line_html += f'<span class="text-span editable-text" data-text="{text}" style="{style}">{text}</span>'
                        line_html += '</div>'
                        page_html += line_html
                
                elif "image" in block:
                    image_counter += 1
                    bbox = block["bbox"]
                    image_data = block["image"]
                    image_base64 = base64.b64encode(image_data).decode()
                    
                    style = f"position: absolute; left: {bbox[0]}px; top: {bbox[1]}px; width: {bbox[2] - bbox[0]}px; height: {bbox[3] - bbox[1]}px;"
                    page_html += f'<img class="editable-image" data-image-id="{image_counter}" src="data:image/png;base64,{image_base64}" style="{style}">'
            
            page_html += '</div>'
            pages_data.append({
                'html': page_html,
                'width': page.rect.width,
                'height': page.rect.height
            })
        
        doc.close()
        
        # Use the EXACT same template rendering as /convert/<filename>
        html_filename = f"{file.filename.replace('.pdf', '')}_converted.html"
        html_filepath = os.path.join(HTML_FOLDER, html_filename)
        
        # Clear template cache like convert_pdf does
        import flask.templating
        import jinja2
        if hasattr(app, 'jinja_env'):
            app.jinja_env.cache.clear()
        try:
            if hasattr(flask.templating, '_template_cache'):
                flask.templating._template_cache.clear()
        except:
            pass
        
        # Use desktop template (same as convert_pdf default)
        template_name = "converted.html"
        template_path = os.path.join(app.template_folder, template_name)
        
        # Force clear template cache and touch file
        if hasattr(app, 'jinja_env'):
            app.jinja_env.cache.clear()
        if os.path.exists(template_path):
            os.utime(template_path, None)
        
        # Render using the EXACT same method as convert_pdf
        rendered_html = render_template(template_name, 
                                       filename=file.filename, 
                                       pages=pages_data)
        
        # Save the rendered HTML to file with UTF-8 encoding
        with open(html_filepath, 'w', encoding='utf-8') as f:
            f.write(rendered_html)
        
        return jsonify({
            "status": "success",
            "message": "PDF converted to HTML successfully",
            "converted_filename": html_filename,
            "original_format": "PDF",
            "converted_format": "HTML",
            "download_url": f"/download_converted/{html_filename}",
            "preview_url": f"/preview_html/{html_filename}"
        })
        
    except Exception as e:
        import traceback
        print(f"Error converting PDF to HTML: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/convert_word_to_pdf", methods=["POST"])
def convert_word_to_pdf():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # For Word to PDF, we'll return the original file for now
        # This can be enhanced with proper Word to PDF conversion
        return jsonify({
            "status": "success",
            "message": "Word document processed successfully",
            "converted_filename": file.filename,
            "original_format": "Word",
            "converted_format": "PDF",
            "download_url": f"/download_converted/{file.filename}"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert_html_to_pdf", methods=["POST"])
def convert_html_to_pdf():
    """Convert HTML to PDF while preserving layout"""
    if "html" not in request.files and "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    # Accept both "html" and "file" as field names
    file = request.files.get("html") or request.files.get("file")
    if not file or file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file with unique filename
        original_filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{unique_id}_{original_filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Validate HTML file was saved and has content
        if not os.path.exists(filepath):
            return jsonify({
                "status": "error",
                "message": "Failed to save HTML file",
                "error": "HTML file was not saved to server"
            }), 500
        
        html_size = os.path.getsize(filepath)
        if html_size < 100:
            return jsonify({
                "status": "error",
                "message": "HTML file is too small or empty",
                "error": f"HTML file is only {html_size} bytes"
            }), 400
        
        # Read and validate HTML content
        with open(filepath, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        if len(html_content.strip()) < 100:
            return jsonify({
                "status": "error",
                "message": "HTML content is too short or empty",
                "error": f"HTML content is only {len(html_content)} characters"
            }), 400
        
        # Check if HTML has basic structure
        if "<html" not in html_content.lower() and "<body" not in html_content.lower():
            print("WARNING: HTML file may not have proper HTML structure")
        
        print(f"[OK] HTML file validated: {html_size} bytes, {len(html_content)} characters")
        
        # Generate output filename
        base_name = os.path.splitext(original_filename)[0]
        pdf_filename = f"{base_name}_converted.pdf"
        pdf_path = os.path.join(EDITED_FOLDER, pdf_filename)
        
        # Convert HTML to PDF - use step-by-step PyMuPDF method first (most accurate for our HTML format)
        # This method parses the HTML and recreates the PDF using the same library that created it
        conversion_success = False
        
        # Method 1: Try step-by-step PyMuPDF reconstruction (best for HTML generated from PDF)
        try:
            conversion_success = convert_html_to_pdf_pymupdf_step_by_step(filepath, pdf_path)
            if conversion_success:
                print("[OK] Successfully converted using PyMuPDF step-by-step method")
        except Exception as e:
            print(f"PyMuPDF step-by-step conversion error: {e}")
        
        # Method 2: Try Playwright (most accurate, browser-based)
        if not conversion_success and PLAYWRIGHT_AVAILABLE:
            try:
                conversion_success = convert_html_to_pdf_playwright(filepath, pdf_path)
                if conversion_success:
                    print("[OK] Successfully converted using Playwright")
            except Exception as e:
                print(f"Playwright conversion error: {e}")
        
        # Method 3: Try WeasyPrint (good CSS support, but requires GTK+ on Windows)
        if not conversion_success and WEASYPRINT_AVAILABLE:
            try:
                conversion_success = convert_html_to_pdf_weasyprint(filepath, pdf_path)
                if conversion_success:
                    print("[OK] Successfully converted using WeasyPrint")
            except Exception as e:
                print(f"WeasyPrint conversion error: {e}")
        
        # Method 4: Try xhtml2pdf (pure Python, works on Windows)
        if not conversion_success and XHTML2PDF_AVAILABLE:
            try:
                conversion_success = convert_html_to_pdf_xhtml2pdf(filepath, pdf_path)
                if conversion_success:
                    print("[OK] Successfully converted using xhtml2pdf")
            except Exception as e:
                print(f"xhtml2pdf conversion error: {e}")
        
        # Method 5: Fallback to PyMuPDF insert_htmlbox
        if not conversion_success:
            print("Trying PyMuPDF insert_htmlbox fallback...")
            conversion_success = convert_html_to_pdf_pymupdf(filepath, pdf_path)
        
        if not conversion_success:
            return jsonify({
                "status": "error",
                "message": "HTML to PDF conversion failed",
                "error": "Could not convert HTML to PDF"
            }), 500
        
        # Validate PDF was created and has content
        if not os.path.exists(pdf_path):
            return jsonify({
                "status": "error",
                "message": "PDF file was not created",
                "error": "Conversion succeeded but PDF file not found"
            }), 500
        
        pdf_size = os.path.getsize(pdf_path)
        if pdf_size < 1000:  # PDF should be at least 1KB
            return jsonify({
                "status": "error",
                "message": "PDF file is too small (likely empty)",
                "error": f"PDF file is only {pdf_size} bytes, conversion likely failed"
            }), 500
        
        # Verify PDF has pages with content
        try:
            pdf_doc = fitz.open(pdf_path)
            page_count = len(pdf_doc)
            if page_count == 0:
                pdf_doc.close()
                return jsonify({
                    "status": "error",
                    "message": "PDF has no pages",
                    "error": "Conversion created empty PDF with no pages"
                }), 500
            
            # Check if pages have content by checking text extraction
            total_text = 0
            for page_num in range(page_count):
                page = pdf_doc[page_num]
                text = page.get_text()
                total_text += len(text.strip())
            
            pdf_doc.close()
            
            if total_text == 0:
                # Check if there are images instead
                pdf_doc = fitz.open(pdf_path)
                has_images = False
                for page_num in range(page_count):
                    page = pdf_doc[page_num]
                    image_list = page.get_images()
                    if len(image_list) > 0:
                        has_images = True
                        break
                pdf_doc.close()
                
                if not has_images:
                    return jsonify({
                        "status": "error",
                        "message": "PDF has no content (no text or images)",
                        "error": "Conversion created PDF with pages but no visible content"
                    }), 500
            
            print(f"[OK] PDF validation passed: {page_count} pages, {total_text} chars of text")
            
        except Exception as e:
            print(f"WARNING: Could not validate PDF content: {e}")
            # Continue anyway if validation fails
        
        # Get file sizes
        original_size = os.path.getsize(filepath)
        
        return jsonify({
            "status": "success",
            "message": "HTML converted to PDF successfully",
            "converted_filename": pdf_filename,
            "original_format": "HTML",
            "converted_format": "PDF",
            "original_size": original_size,
            "pdf_size": pdf_size,
            "download_url": f"/download_edited/{pdf_filename}"
        })
        
    except Exception as e:
        print(f"ERROR: HTML to PDF conversion failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Conversion failed: {str(e)}",
            "error": str(e)
        }), 500

def convert_html_to_pdf_playwright(html_path, output_path):
    """Convert HTML to PDF using Playwright - most accurate, browser-based rendering"""
    try:
        # Read HTML content first to check structure
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Get the directory of the HTML file for resolving relative paths (images, CSS, etc.)
        html_dir = os.path.dirname(os.path.abspath(html_path))
        # Convert to file:// URL format (Windows compatible)
        if os.sep == '\\':
            # Fix: Cannot use backslash in f-string expression, so do replace first
            html_dir_normalized = html_dir.replace('\\', '/')
            base_url = f"file:///{html_dir_normalized}/"
        else:
            base_url = f"file://{html_dir}/"
        
        with sync_playwright() as p:
            # Launch browser with proper settings for accurate rendering
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )
            
            # Create a new page - use device scale factor of 1 to ensure 1:1 pixel mapping
            browser_page = browser.new_page(
                viewport={'width': 4000, 'height': 4000},  # Very large to avoid clipping
                device_scale_factor=1  # Ensure 1:1 pixel mapping
            )
            
            # Inject CSS to remove any transforms/scaling that might affect layout
            # and ensure pages are visible and properly positioned
            prepended_css = """
            <style id="pdf-conversion-override">
                /* Remove all transforms that might affect layout */
                .pdf-page, .page {
                    transform: none !important;
                    transform-origin: unset !important;
                    margin: 0 !important;
                    padding: 0 !important;
                    display: block !important;
                    visibility: visible !important;
                    opacity: 1 !important;
                    position: relative !important;
                    width: auto !important;
                    height: auto !important;
                }
                /* Ensure container doesn't add padding/margins */
                .pdf-container {
                    padding: 0 !important;
                    margin: 0 !important;
                    width: auto !important;
                    height: auto !important;
                }
                /* Ensure body doesn't add spacing */
                body {
                    margin: 0 !important;
                    padding: 0 !important;
                    width: auto !important;
                    height: auto !important;
                }
                /* Ensure absolute positioned elements maintain their positions */
                .text-span, .editable-text, .editable-image {
                    position: absolute !important;
                }
            </style>
            """
            
            # Prepend the override CSS to the HTML
            html_with_override = html_content.replace('<head>', f'<head>{prepended_css}')
            
            # Load HTML content - this preserves all CSS and absolute positioning
            browser_page.set_content(html_with_override, base_url=base_url, wait_until="networkidle", timeout=60000)
            
            # Wait for rendering to complete
            browser_page.wait_for_timeout(3000)
            
            # Get page information - use data attributes if available, otherwise detect
            page_info = browser_page.evaluate("""
                () => {
                    // Find all page containers
                    const pageElements = document.querySelectorAll('.pdf-page, .page');
                    
                    if (pageElements.length === 0) {
                        // Single page - use body dimensions
                        const body = document.body;
                        const rect = body.getBoundingClientRect();
                        return {
                            singlePage: true,
                            width: Math.max(rect.width, body.scrollWidth, 595),
                            height: Math.max(rect.height, body.scrollHeight, 842)
                        };
                    }
                    
                    // Try to get dimensions from data attributes first (most accurate)
                    const firstPage = pageElements[0];
                    let width = parseFloat(firstPage.getAttribute('data-width'));
                    let height = parseFloat(firstPage.getAttribute('data-height'));
                    
                    // If data attributes not available, use rendered dimensions
                    if (!width || !height || isNaN(width) || isNaN(height)) {
                        const rect = firstPage.getBoundingClientRect();
                        width = rect.width;
                        height = rect.height;
                        
                        // Get the actual content bounds within the page
                        const content = firstPage.querySelector('.page-content');
                        if (content) {
                            const contentRect = content.getBoundingClientRect();
                            width = Math.max(contentRect.width, rect.width);
                            height = Math.max(contentRect.height, rect.height);
                        }
                    }
                    
                    // Ensure minimum A4 size
                    width = Math.max(width, 595);
                    height = Math.max(height, 842);
                    
                    return {
                        singlePage: false,
                        pageCount: pageElements.length,
                        width: width,
                        height: height
                    };
                }
            """)
            
            page_width = int(page_info.get('width', 595))
            page_height = int(page_info.get('height', 842))
            is_single_page = page_info.get('singlePage', True)
            page_count = page_info.get('pageCount', 1)
            
            print(f"Detected: {page_count} page(s), dimensions: {page_width}x{page_height}px")
            
            # For multi-page HTML, we need to create a multi-page PDF
            # Playwright's PDF generation can handle this if we set the right height
            # But we might need to handle each page separately
            
            if not is_single_page and page_count > 1:
                # Multi-page: calculate total height
                total_height = page_height * page_count
                print(f"Multi-page document: total height = {total_height}px")
                
                # Generate PDF with full document height
                pdf_options = {
                    "path": output_path,
                    "print_background": True,
                    "margin": {"top": "0", "right": "0", "bottom": "0", "left": "0"},
                    "width": f"{page_width}px",
                    "height": f"{total_height}px",  # Full document height
                    "scale": 1.0,
                    "prefer_css_page_size": False
                }
            else:
                # Single page
                pdf_options = {
                    "path": output_path,
                    "print_background": True,
                    "margin": {"top": "0", "right": "0", "bottom": "0", "left": "0"},
                    "width": f"{page_width}px",
                    "height": f"{page_height}px",
                    "scale": 1.0,
                    "prefer_css_page_size": False
                }
            
            browser_page.pdf(**pdf_options)
            browser.close()
        
        # Verify the PDF was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"Successfully converted HTML to PDF using Playwright: {output_path}")
            print(f"PDF size: {os.path.getsize(output_path)} bytes")
            return True
        else:
            print("Playwright conversion failed: PDF file not created or empty")
            return False
            
    except Exception as e:
        print(f"Error in Playwright conversion: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def convert_html_to_pdf_xhtml2pdf(html_path, output_path):
    """Convert HTML to PDF using xhtml2pdf - pure Python, works on Windows"""
    try:
        from xhtml2pdf import pisa
        
        # Read HTML content
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # Convert HTML to PDF
        with open(output_path, "wb") as pdf_file:
            pisa_status = pisa.CreatePDF(
                html_content,
                dest=pdf_file,
                encoding='utf-8'
            )
        
        # Check for errors
        if pisa_status.err:
            print(f"xhtml2pdf conversion errors: {pisa_status.err}")
            return False
        
        # Verify the PDF was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"Successfully converted HTML to PDF using xhtml2pdf: {output_path}")
            return True
        else:
            print("xhtml2pdf conversion failed: PDF file not created or empty")
            return False
            
    except Exception as e:
        print(f"Error in xhtml2pdf conversion: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def convert_html_to_pdf_weasyprint(html_path, output_path):
    """Convert HTML to PDF using WeasyPrint - best for preserving CSS and layout"""
    try:
        # Read HTML content
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Get the directory of the HTML file for resolving relative paths (images, CSS, etc.)
        html_dir = os.path.dirname(os.path.abspath(html_path))
        # Convert Windows path to file:// URL format
        if os.sep == '\\':
            # Fix: Cannot use backslash in f-string expression, so do replace first
            html_dir_normalized = html_dir.replace('\\', '/')
            base_url = f"file:///{html_dir_normalized}/"
        else:
            base_url = f"file://{html_dir}/"
        
        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # Convert HTML to PDF using WeasyPrint
        # WeasyPrint supports modern CSS features and preserves layout accurately
        # It handles:
        # - CSS positioning (absolute, relative, fixed)
        # - Flexbox and Grid layouts
        # - Fonts and typography
        # - Colors and backgrounds
        # - Images (including base64 encoded)
        # - Page breaks and pagination
        
        html_doc = HTML(
            string=html_content,
            base_url=base_url  # Helps resolve relative URLs in HTML (images, CSS files, etc.)
        )
        
        # Write PDF with default settings (good quality)
        html_doc.write_pdf(
            output_path,
            # Optional: You can add stylesheets here if needed
            # stylesheets=[CSS(string='@page { size: A4; margin: 0; }')]
        )
        
        # Verify the PDF was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"Successfully converted HTML to PDF using WeasyPrint: {output_path}")
            print(f"PDF size: {os.path.getsize(output_path)} bytes")
            return True
        else:
            print("WeasyPrint conversion failed: PDF file not created or empty")
            return False
            
    except Exception as e:
        print(f"Error in WeasyPrint conversion: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def convert_html_to_pdf_pymupdf_step_by_step(html_path, output_path):
    """
    Convert HTML to PDF by parsing the HTML structure and recreating the PDF page by page.
    This method extracts absolute positioned elements and places them exactly where they were.
    This is the most accurate method for HTML generated from PDF using PyMuPDF.
    """
    try:
        import re
        from html import unescape
        
        # Read HTML content
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Create new PDF document
        doc = fitz.open()
        
        # Find all page divs - HTML can use either .pdf-page with data attributes OR .page with style attributes
        pages = []
        
        # Method 1: Try to find .pdf-page divs with data attributes (from convert_pdf_to_html endpoint)
        page_openings = []
        for match in re.finditer(r'<div[^>]*class="[^"]*pdf-page[^"]*"[^>]*data-page="(\d+)"[^>]*data-width="([\d.]+)"[^>]*data-height="([\d.]+)"[^>]*>', html_content, re.IGNORECASE):
            page_num = int(match.group(1))
            page_width = float(match.group(2))
            page_height = float(match.group(3))
            start_pos = match.end()
            page_openings.append((page_num, page_width, page_height, start_pos))
        
        if page_openings:
            # Extract content for each page
            for i, (page_num, page_width, page_height, start_pos) in enumerate(page_openings):
                if i + 1 < len(page_openings):
                    end_pos = page_openings[i + 1][3] - len('<div')
                    closing_match = re.search(r'</div>\s*(?=<div[^>]*class="[^"]*pdf-page)', html_content[start_pos:end_pos], re.IGNORECASE)
                    if closing_match:
                        end_pos = start_pos + closing_match.start()
                else:
                    closing_match = re.search(r'</div>\s*(?=</div>\s*</div>\s*</div>|$)', html_content[start_pos:], re.IGNORECASE)
                    if closing_match:
                        end_pos = start_pos + closing_match.start()
                    else:
                        end_pos = len(html_content)
                
                page_html = html_content[start_pos:end_pos]
                pages.append((page_num, page_width, page_height, page_html))
        else:
            # Method 2: Find .page divs with style attributes (from convert_with_pymupdf)
            page_matches = list(re.finditer(r'<div[^>]*class="[^"]*page[^"]*"[^>]*style="[^"]*width:\s*([\d.]+)pt[^"]*min-height:\s*([\d.]+)pt[^"]*"[^>]*>', html_content, re.IGNORECASE))
            
            if not page_matches:
                # Try alternative pattern without min-height
                page_matches = list(re.finditer(r'<div[^>]*class="[^"]*page[^"]*"[^>]*style="[^"]*width:\s*([\d.]+)pt[^"]*"[^>]*>', html_content, re.IGNORECASE))
            
            if page_matches:
                for i, match in enumerate(page_matches):
                    page_width = float(match.group(1))
                    
                    # Get page content div to extract height
                    start_pos = match.end()
                    content_match = re.search(r'<div[^>]*class="[^"]*page-content[^"]*"[^>]*style="[^"]*height:\s*([\d.]+)pt', html_content[start_pos:], re.IGNORECASE)
                    if content_match:
                        page_height = float(content_match.group(1))
                        start_pos = start_pos + content_match.end()
                    else:
                        # Try to get from min-height in page div
                        page_height = float(match.group(2)) if len(match.groups()) > 1 else 842.0  # Default A4 height
                        # Find page-content div start
                        content_match = re.search(r'<div[^>]*class="[^"]*page-content[^"]*"[^>]*>', html_content[start_pos:], re.IGNORECASE)
                        if content_match:
                            start_pos = start_pos + content_match.end()
                    
                    # Find end of page
                    if i + 1 < len(page_matches):
                        end_pos = page_matches[i + 1].start()
                    else:
                        end_pos = len(html_content)
                    
                    # Find closing divs
                    closing_match = re.search(r'</div>\s*</div>\s*(?=<div[^"]*class="[^"]*page|$)', html_content[start_pos:end_pos], re.IGNORECASE)
                    if closing_match:
                        end_pos = start_pos + closing_match.start()
                    
                    page_html = html_content[start_pos:end_pos]
                    pages.append((i + 1, page_width, page_height, page_html))
        
        print(f"Found {len(pages)} pages in HTML")
        
        if not pages:
            print("No pages found in HTML, trying single page approach")
            # Single page - extract dimensions from body or first page element
            width_match = re.search(r'data-width="([\d.]+)"', html_content)
            height_match = re.search(r'data-height="([\d.]+)"', html_content)
            width = float(width_match.group(1)) if width_match else 595.0
            height = float(height_match.group(1)) if height_match else 842.0
            
            page = doc.new_page(width=width, height=height)
            _add_elements_to_page(html_content, page, width, height)
        else:
            # Process each page
            for page_num, page_width_str, page_height_str, page_html in pages:
                page_num = int(page_num)
                page_width = float(page_width_str)
                page_height = float(page_height_str)
                
                print(f"Processing page {page_num}: {page_width}x{page_height}pt")
                
                # Create new PDF page with exact dimensions
                page = doc.new_page(width=page_width, height=page_height)
                
                # Add all elements to this page
                _add_elements_to_page(page_html, page, page_width, page_height)
        
        # Save PDF
        doc.save(output_path)
        doc.close()
        
        # Verify the PDF was created and has content
        if not os.path.exists(output_path):
            print("Step-by-step conversion failed: PDF file not created")
            return False
        
        pdf_size = os.path.getsize(output_path)
        if pdf_size < 1000:  # PDF should be at least 1KB
            print(f"Step-by-step conversion failed: PDF file is too small ({pdf_size} bytes)")
            return False
        
        # Verify PDF has pages with content
        try:
            verify_doc = fitz.open(output_path)
            page_count = len(verify_doc)
            if page_count == 0:
                verify_doc.close()
                print("Step-by-step conversion failed: PDF has no pages")
                return False
            
            # Check if pages have content
            total_text = 0
            total_images = 0
            for page_num in range(page_count):
                page = verify_doc[page_num]
                text = page.get_text()
                total_text += len(text.strip())
                images = page.get_images()
                total_images += len(images)
            
            verify_doc.close()
            
            if total_text == 0 and total_images == 0:
                print(f"Step-by-step conversion failed: PDF has {page_count} pages but no content (no text or images)")
                return False
            
            print(f"[OK] Successfully converted HTML to PDF using step-by-step method: {output_path}")
            print(f"PDF size: {pdf_size} bytes, {page_count} pages, {total_text} chars text, {total_images} images")
            return True
        except Exception as e:
            print(f"Error verifying PDF content: {e}")
            # If verification fails, still return True if file exists and has size
            if pdf_size > 1000:
                print(f"PDF file exists and has size ({pdf_size} bytes), assuming success despite verification error")
                return True
            return False
            
    except Exception as e:
        print(f"Error in step-by-step conversion: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def _add_elements_to_page(page_html, page, page_width, page_height):
    """Helper function to add text spans and images to a PDF page"""
    import re
    from html import unescape
    from io import BytesIO
    
    # Extract all text spans with absolute positioning
    # Pattern: <span style="position: absolute; left: Xpt; top: Ypt; font-size: Spt; font-family: F;">text</span>
    # Note: HTML uses 'pt' units, not 'px' - coordinates are already in points (PyMuPDF units)
    text_pattern = r'<span[^>]*style="([^"]*)"[^>]*>(.*?)</span>'
    
    all_spans = re.findall(text_pattern, page_html, re.DOTALL | re.IGNORECASE)
    text_spans = []
    
    for style_attr, text_content in all_spans:
        # Check if it's an absolute positioned span
        if 'position: absolute' not in style_attr and 'position:absolute' not in style_attr:
            continue
        
        # Extract coordinates and font info from style - handle both 'pt' and 'px' units
        left_match = re.search(r'left:\s*([\d.]+)(pt|px)', style_attr, re.IGNORECASE)
        top_match = re.search(r'top:\s*([\d.]+)(pt|px)', style_attr, re.IGNORECASE)
        size_match = re.search(r'font-size:\s*([\d.]+)(pt|px)', style_attr, re.IGNORECASE)
        font_match = re.search(r"font-family:\s*['\"]?([^;'\"]+)['\"]?", style_attr, re.IGNORECASE)
        
        if left_match and top_match and size_match:
            left_val = float(left_match.group(1))
            top_val = float(top_match.group(1))
            size_val = float(size_match.group(1))
            
            # Coordinates are already in points (pt), so use directly
            # If px units are found, we'd need to convert, but HTML from PDF uses pt
            text_spans.append((
                str(left_val),
                str(top_val),
                str(size_val),
                font_match.group(1).strip() if font_match else 'Arial',
                style_attr,
                text_content
            ))
    
    # Process text spans
    for left_str, top_str, size_str, font_family, style_attr, text_content in text_spans:
        try:
            left = float(left_str)
            top = float(top_str)
            size = float(size_str)
            
            # Extract font-weight and font-style from style
            is_bold = 'font-weight: bold' in style_attr or 'font-weight:bold' in style_attr or 'font-weight:700' in style_attr
            is_italic = 'font-style: italic' in style_attr or 'font-style:italic' in style_attr
            
            # Decode HTML entities
            text = unescape(text_content)
            text = text.replace('&nbsp;', ' ')
            text = text.strip()
            
            if text:
                # Insert text at exact position
                # The HTML uses 'pt' (points) units, which is the same unit PyMuPDF uses
                # So coordinates are already in the correct format - use directly
                point = fitz.Point(left, top)
                
                # Clean up font name - remove variants like 'Arial,Bold' -> 'Arial'
                font_name = font_family.split(',')[0].strip().strip("'\"")
                # Remove any variant suffixes
                font_name = re.sub(r'[,;].*$', '', font_name).strip()
                
                # Map common font names to PyMuPDF font names
                font_map = {
                    'Arial': 'helv',
                    'Helvetica': 'helv',
                    'Times': 'times',
                    'Times New Roman': 'times',
                    'Courier': 'cour',
                    'Courier New': 'cour',
                    'ArialMT': 'helv',
                    'Arial,Bold': 'helv',
                    'Arial,Italic': 'helv'
                }
                
                pdf_font = font_map.get(font_name, 'helv')
                
                # Build font flags
                font_flags = 0
                if is_bold:
                    font_flags |= 16  # Bold flag
                if is_italic:
                    font_flags |= 2   # Italic flag
                
                # Insert text with proper font and flags
                try:
                    page.insert_text(
                        point,
                        text,
                        fontsize=size,
                        fontname=pdf_font,
                        render_mode=0,  # Fill text
                        fontfile=None
                    )
                    elements_added += 1
                    # Apply font flags if needed
                    if font_flags:
                        # Note: PyMuPDF's insert_text doesn't directly support flags, 
                        # but we can use insert_font and insert_textbox for better control
                        # For now, we'll use the basic method
                        pass
                except Exception as e:
                    print(f"Warning: Could not insert text with font {pdf_font}, trying default: {e}")
                    # Fallback to default font
                    try:
                        page.insert_text(point, text, fontsize=size, fontname='helv', render_mode=0)
                        elements_added += 1
                    except Exception as e2:
                        print(f"Error inserting text even with default font: {e2}")
        except Exception as e:
            print(f"Error adding text span: {e}")
            continue
    
    print(f"Added {len(text_spans)} text spans to page, {elements_added} successfully inserted")
    
    # Extract all images with absolute positioning
    # Pattern: <img style="position: absolute; left: Xpt; top: Ypt; width: Wpt; height: Hpt;" src="data:image/png;base64,...">
    # Note: HTML uses 'pt' units, not 'px'
    # The src attribute might come before or after style, so we need a more flexible pattern
    img_pattern = r'<img[^>]*src="data:image/([^;]+);base64,([^"]+)"[^>]*style="([^"]*)"'
    img_pattern2 = r'<img[^>]*style="([^"]*)"[^>]*src="data:image/([^;]+);base64,([^"]+)"'
    
    all_images = re.findall(img_pattern, page_html, re.IGNORECASE)
    all_images2 = re.findall(img_pattern2, page_html, re.IGNORECASE)
    
    # Combine both patterns
    all_image_matches = []
    for match in all_images:
        all_image_matches.append((match[2], match[0], match[1]))  # style, format, data
    for match in all_images2:
        all_image_matches.append((match[0], match[1], match[2]))  # style, format, data
    
    images = []
    print(f"Found {len(all_image_matches)} image tags in HTML")
    
    for style_attr, img_format, base64_data in all_image_matches:
        # Check if it's an absolute positioned image
        if 'position: absolute' not in style_attr and 'position:absolute' not in style_attr:
            continue
        
        # Extract coordinates and dimensions from style - handle both 'pt' and 'px' units
        left_match = re.search(r'left:\s*([\d.]+)(pt|px)', style_attr, re.IGNORECASE)
        top_match = re.search(r'top:\s*([\d.]+)(pt|px)', style_attr, re.IGNORECASE)
        width_match = re.search(r'width:\s*([\d.]+)(pt|px)', style_attr, re.IGNORECASE)
        height_match = re.search(r'height:\s*([\d.]+)(pt|px)', style_attr, re.IGNORECASE)
        
        if left_match and top_match and width_match and height_match:
            left_val = float(left_match.group(1))
            top_val = float(top_match.group(1))
            width_val = float(width_match.group(1))
            height_val = float(height_match.group(1))
            
            # Coordinates are already in points (pt), so use directly
            images.append((
                str(left_val),
                str(top_val),
                str(width_val),
                str(height_val),
                img_format,
                base64_data
            ))
        else:
            print(f"Warning: Image missing required style attributes. Style: {style_attr[:100]}")
    
    print(f"Extracted {len(images)} images with absolute positioning")
    
    for left_str, top_str, width_str, height_str, img_format, base64_data in images:
        try:
            left = float(left_str)
            top = float(top_str)
            width = float(width_str)
            height = float(height_str)
            
            # Decode base64 image
            image_data = base64.b64decode(base64_data)
            
            # Create rectangle for image placement
            rect = fitz.Rect(left, top, left + width, top + height)
            
            # Insert image - use stream parameter for base64 decoded data
            page.insert_image(rect, stream=image_data, keep_proportion=False)
            elements_added += 1
            print(f"Inserted image at ({left}, {top}) with size {width}x{height}")
        except Exception as e:
            print(f"Error adding image at ({left_str}, {top_str}): {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"Total elements added to page: {elements_added} (text spans: {len(text_spans)}, images: {len(images)})")
    
    if elements_added == 0:
        print(f"[WARN] WARNING: No elements were added to the page! Page HTML length: {len(page_html)}")
        print(f"Page HTML preview (first 500 chars): {page_html[:500]}")
        print(f"Text spans found: {len(text_spans)}, Images found: {len(images)}")

def convert_html_to_pdf_pymupdf(html_path, output_path):
    """Convert HTML to PDF using PyMuPDF"""
    try:
        # Read HTML content
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        # Create a new PDF document
        doc = fitz.open()
        
        # Create a page (A4 size: 595 x 842 points)
        page = doc.new_page(width=595, height=842)
        rect = page.rect
        
        # Use PyMuPDF's insert_htmlbox to render HTML
        # This method renders HTML content into the PDF
        try:
            # Insert HTML content into the page
            # insert_htmlbox renders HTML with CSS support
            # Parameters: rect, text (HTML content), css (optional)
            page.insert_htmlbox(
                rect,  # Rectangle to fill
                html_content,  # HTML content (parameter name is 'text' but accepts HTML)
                css=""  # Additional CSS if needed
            )
            
        except Exception as e:
            print(f"Warning: insert_htmlbox failed, trying alternative: {e}")
            # Fallback: Try with file path instead
            try:
                # Convert to absolute path for file:// URL
                abs_html_path = os.path.abspath(html_path)
                file_url = f"file:///{abs_html_path.replace(os.sep, '/')}"
                
                # Try rendering from file URL
                page.insert_htmlbox(rect, file_url)
                
            except Exception as e2:
                print(f"Warning: File URL method failed, using text extraction: {e2}")
                # Last resort: Extract text and add as plain text
                import re
                from html import unescape
                # Remove HTML tags and decode entities
                text_content = re.sub(r'<[^>]+>', ' ', html_content)
                text_content = unescape(text_content)
                # Clean up whitespace
                text_content = ' '.join(text_content.split())
                
                # Insert text with basic formatting
                if text_content:
                    page.insert_text((50, 50), text_content[:10000], fontsize=11)
                else:
                    print("ERROR: No text content extracted from HTML")
                    return False
        
        # Save PDF
        doc.save(output_path)
        doc.close()
        
        return True
        
    except Exception as e:
        print(f"ERROR in HTML to PDF conversion: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

@app.route("/convert_image_to_pdf", methods=["POST"])
def convert_image_to_pdf():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # For image to PDF, we'll return the original file for now
        # This can be enhanced with proper image to PDF conversion
        return jsonify({
            "status": "success",
            "message": "Image file processed successfully",
            "converted_filename": file.filename,
            "original_format": "Image",
            "converted_format": "PDF",
            "download_url": f"/download_converted/{file.filename}"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert_pdf_to_images", methods=["POST"])
def convert_pdf_to_images():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # Convert PDF to images
        doc = fitz.open(filepath)
        images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            img_base64 = base64.b64encode(img_data).decode()
            images.append({
                "page": page_num + 1,
                "data": img_base64
            })
        
        doc.close()
        
        return jsonify({
            "status": "success",
            "message": f"PDF converted to {len(images)} images successfully",
            "converted_filename": f"{file.filename.replace('.pdf', '')}_images.zip",
            "original_format": "PDF",
            "converted_format": "Images",
            "total_images": len(images),
            "image_files": images,
            "download_url": f"/download_images/{file.filename.replace('.pdf', '')}_images.zip"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert_pdf_to_html", methods=["POST"])
def convert_pdf_to_html():
    """Convert PDF to HTML while preserving layout"""
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    
    # Get conversion method preference (default: pymupdf)
    method = request.form.get("method", "pymupdf").lower()
    
    try:
        # Save file with unique filename
        original_filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{unique_id}_{original_filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Generate output filename
        base_name = os.path.splitext(original_filename)[0]
        html_filename = f"{base_name}_converted.html"
        html_path = os.path.join(HTML_FOLDER, html_filename)
        
        conversion_success = False
        conversion_method_used = None
        error_message = None
        
        # Try pdf2htmlEX first if requested (higher fidelity)
        if method == "pdf2htmlex":
            try:
                conversion_success = convert_with_pdf2htmlex(filepath, html_path)
                if conversion_success:
                    conversion_method_used = "pdf2htmlEX"
            except Exception as e:
                error_message = f"pdf2htmlEX conversion failed: {str(e)}"
                print(f"WARNING: {error_message}")
        
        # Fallback to PyMuPDF if pdf2htmlEX failed or not requested
        if not conversion_success:
            try:
                conversion_success = convert_with_pymupdf(filepath, html_path)
                if conversion_success:
                    conversion_method_used = "PyMuPDF"
            except Exception as e:
                error_message = f"PyMuPDF conversion failed: {str(e)}"
                print(f"ERROR: {error_message}")
        
        if not conversion_success:
            return jsonify({
                "status": "error",
                "message": f"Conversion failed. {error_message}",
                "error": error_message
            }), 500
        
        # Get file sizes
        original_size = os.path.getsize(filepath)
        html_size = os.path.getsize(html_path)
        
        return jsonify({
            "status": "success",
            "message": f"PDF converted to HTML successfully using {conversion_method_used}",
            "converted_filename": html_filename,
            "original_format": "PDF",
            "converted_format": "HTML",
            "method_used": conversion_method_used,
            "original_size": original_size,
            "html_size": html_size,
            "download_url": f"/download_converted/{html_filename}",
            "preview_url": f"/preview_html/{html_filename}"
        })
        
    except Exception as e:
        print(f"ERROR: PDF to HTML conversion failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Conversion failed: {str(e)}",
            "error": str(e)
        }), 500

def convert_with_pymupdf(pdf_path, output_path):
    """Convert PDF to HTML with EXACT layout preservation using absolute positioning"""
    try:
        doc = fitz.open(pdf_path)
        html_parts = []
        
        # Create HTML structure
        html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Converted PDF</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        html, body {
            margin: 0;
            padding: 0;
            background: white;
            width: 100%;
            height: 100%;
            overflow: auto;
        }
        .pdf-container {
            margin: 0;
            padding: 0;
            background: white;
        }
        .page {
            background: transparent;
            margin: 0;
            padding: 0;
            border: 0;
            box-shadow: none;
            outline: none;
            position: relative;
            overflow: visible;
        }
        .page-content {
            position: relative;
            background: transparent;
        }
    </style>
</head>
<body>
<div class="pdf-container">
""")
        
        # Convert each page with EXACT positioning
        total_text_spans = 0
        total_images = 0
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            rect = page.rect
            page_width = rect.width
            page_height = rect.height
            
            html_parts.append(f'<div class="page" style="width: {page_width}pt; min-height: {page_height}pt;">')
            html_parts.append(f'<div class="page-content" style="width: {page_width}pt; height: {page_height}pt; position: relative;">')
            
            # Get ALL text with exact positions - use dict for text extraction
            blocks = page.get_text("dict")
            
            # Collect all text spans with their exact positions
            text_spans = []
            images = []
            
            for block in blocks.get("blocks", []):
                if "lines" in block:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "")
                            if not text or not text.strip():
                                continue
                            
                            bbox = span.get("bbox", [0, 0, 0, 0])
                            x0, y0, x1, y1 = bbox
                            
                            # Get all styling info
                            font = span.get("font", "Arial")
                            size = span.get("size", 12)
                            flags = span.get("flags", 0)
                            color = span.get("color", 0)
                            
                            # Convert color
                            if isinstance(color, int):
                                r = (color >> 16) & 0xFF
                                g = (color >> 8) & 0xFF
                                b = color & 0xFF
                                color_hex = f"#{r:02x}{g:02x}{b:02x}"
                            else:
                                color_hex = "#000000"
                            
                            text_spans.append({
                                "text": text,
                                "x": x0,
                                "y": y0,
                                "font": font,
                                "size": size,
                                "color": color_hex,
                                "flags": flags
                            })
                
                elif "image" in block:  # Image block
                    try:
                        img = block["image"]
                        img_data = base64.b64encode(img).decode()
                        bbox = block.get("bbox", [0, 0, 0, 0])
                        x0, y0, x1, y1 = bbox
                        width = x1 - x0
                        height = y1 - y0
                        
                        images.append({
                            "data": img_data,
                            "x": x0,
                            "y": y0,
                            "width": width,
                            "height": height
                        })
                    except Exception as e:
                        print(f"Warning: Could not process image: {e}")
            
            # Render images first (background layer)
            for img in images:
                html_parts.append(
                    f'<img src="data:image/png;base64,{img["data"]}" '
                    f'style="position: absolute; left: {img["x"]}pt; top: {img["y"]}pt; '
                    f'width: {img["width"]}pt; height: {img["height"]}pt; z-index: 0;" alt="" />'
                )
            
            # Render text spans with exact positioning (foreground layer)
            for span in text_spans:
                style_parts = [
                    f"position: absolute",
                    f"left: {span['x']}pt",
                    f"top: {span['y']}pt",
                    f"font-family: '{span['font']}', Arial, sans-serif",
                    f"font-size: {span['size']}pt",
                    f"color: {span['color']}",
                    f"white-space: pre",
                    f"z-index: 1"
                ]
                
                if span["flags"] & 16:  # Bold
                    style_parts.append("font-weight: bold")
                if span["flags"] & 2:  # Italic
                    style_parts.append("font-style: italic")
                if span["flags"] & 8:  # Underline
                    style_parts.append("text-decoration: underline")
                
                style = "; ".join(style_parts)
                
                # Escape HTML
                text_escaped = (span["text"]
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;")
                    .replace("'", "&#39;"))
                
                html_parts.append(f'<span style="{style}">{text_escaped}</span>')
            
            total_text_spans += len(text_spans)
            total_images += len(images)
            
            html_parts.append('</div>')
            html_parts.append('</div>')
        
        html_parts.append("""
</div>
</body>
</html>
""")
        
        # Write HTML file
        html_content = "\n".join(html_parts)
        
        # Validate that HTML has actual content (not just structure)
        # Check if we have any pages with content
        if len(doc) == 0:
            print("ERROR: PDF has no pages")
            doc.close()
            return False
        
        # Check if we extracted any content
        if total_text_spans == 0 and total_images == 0:
            print(f"WARNING: No text or images extracted from PDF (pages: {len(doc)}, text spans: {total_text_spans}, images: {total_images})")
            # Still create the HTML file with empty pages, but log a warning
        
        # Check if HTML has meaningful content (more than just the structure)
        # The minimum HTML structure is about 500 chars, so if we have less than 1000, it's likely empty
        if len(html_content) < 1000:
            print(f"WARNING: Generated HTML is very short ({len(html_content)} chars), might be empty")
            # Still write it, but log a warning
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        # Verify file was written and has content
        if not os.path.exists(output_path):
            print(f"ERROR: HTML file was not created at {output_path}")
            doc.close()
            return False
        
        file_size = os.path.getsize(output_path)
        if file_size < 100:
            print(f"ERROR: HTML file is too small ({file_size} bytes), conversion likely failed")
            doc.close()
            return False
        
        doc.close()
        print(f"[OK] Successfully created HTML file: {output_path} ({file_size} bytes)")
        return True
        
    except Exception as e:
        print(f"ERROR in PyMuPDF conversion: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def convert_with_pdf2htmlex(pdf_path, output_path):
    """Convert PDF to HTML using pdf2htmlEX (external tool)"""
    try:
        # Check if pdf2htmlEX is available
        result = subprocess.run(
            ["pdf2htmlEX", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            print("pdf2htmlEX not found or not working")
            return False
        
        # Run pdf2htmlEX conversion
        cmd = [
            "pdf2htmlEX",
            "--zoom", "1.5",
            "--embed", "css",
            "--embed", "font",
            "--dest-dir", os.path.dirname(output_path),
            "--embed-image", "1",
            pdf_path,
            os.path.basename(output_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=os.path.dirname(output_path)
        )
        
        if result.returncode == 0:
            # pdf2htmlEX might add .html extension or use different naming
            # Check if the file exists with expected name
            if os.path.exists(output_path):
                return True
            
            # Try to find the generated file
            base_name = os.path.splitext(os.path.basename(output_path))[0]
            possible_names = [
                output_path,
                os.path.join(os.path.dirname(output_path), base_name + ".html"),
                os.path.join(os.path.dirname(output_path), os.path.basename(pdf_path).replace(".pdf", ".html"))
            ]
            
            for possible_path in possible_names:
                if os.path.exists(possible_path):
                    # Rename to expected output path
                    if possible_path != output_path:
                        shutil.move(possible_path, output_path)
                    return True
            
            print(f"pdf2htmlEX completed but output file not found. stderr: {result.stderr}")
            return False
        else:
            print(f"pdf2htmlEX failed with return code {result.returncode}")
            print(f"stderr: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print("pdf2htmlEX not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        print("pdf2htmlEX conversion timed out")
        return False
    except Exception as e:
        print(f"ERROR in pdf2htmlEX conversion: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

@app.route("/download_converted/<filename>")
def download_converted(filename):
    filepath = os.path.join(HTML_FOLDER, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    else:
        return "File not found", 404

@app.route("/preview_html/<filename>")
def preview_html(filename):
    """Serve the converted HTML file for preview"""
    try:
        from urllib.parse import unquote
        
        # Decode URL-encoded filename
        filename = unquote(filename)
        
        # Serve the converted HTML file directly
        html_filepath = os.path.join(HTML_FOLDER, filename)
        
        if not os.path.exists(html_filepath):
            # Try to find the file with different encodings or variations
            print(f"HTML file not found at: {html_filepath}")
            print(f"HTML_FOLDER: {HTML_FOLDER}")
            print(f"Looking for: {filename}")
            
            # List files in HTML_FOLDER for debugging
            if os.path.exists(HTML_FOLDER):
                files = os.listdir(HTML_FOLDER)
                print(f"Files in HTML_FOLDER: {files[:10]}")  # Show first 10 files
                # Try to find a matching file
                for f in files:
                    if filename.lower() in f.lower() or f.lower() in filename.lower():
                        print(f"Found similar file: {f}")
                        html_filepath = os.path.join(HTML_FOLDER, f)
                        break
            
            if not os.path.exists(html_filepath):
                return f"HTML file not found: {filename}", 404
        
        # Check file size
        file_size = os.path.getsize(html_filepath)
        if file_size < 100:
            return f"HTML file is empty or too small ({file_size} bytes)", 500
        
        return send_file(html_filepath, mimetype='text/html')
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error serving HTML file: {str(e)}", 500

@app.route("/download_images/<filename>")
def download_images(filename):
    """Extract all images from PDF and return as zip file"""
    try:
        import zipfile
        from urllib.parse import unquote
        
        # Decode URL-encoded filename
        filename = unquote(filename)
        
        # Find the PDF file
        pdf_path = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(pdf_path):
            # Try with .pdf extension if not present
            if not filename.endswith('.pdf'):
                pdf_path = os.path.join(UPLOAD_FOLDER, filename + '.pdf')
            if not os.path.exists(pdf_path):
                return "PDF file not found", 404
        
        # Open PDF and extract images
        doc = fitz.open(pdf_path)
        
        # Create zip file in memory
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            image_count = 0
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)
                    
                    if pix.n - pix.alpha < 4:  # GRAY or RGB
                        img_data = pix.tobytes("png")
                        # Create filename: page_X_image_Y.png
                        img_filename = f"page_{page_num + 1}_image_{img_index + 1}.png"
                        zip_file.writestr(img_filename, img_data)
                        image_count += 1
                    
                    pix = None
        
        doc.close()
        
        if image_count == 0:
            return "No images found in PDF", 404
        
        # Prepare zip file for download
        zip_buffer.seek(0)
        base_name = os.path.splitext(filename)[0]
        zip_filename = f"{base_name}_images.zip"
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error creating zip file: {str(e)}", 500

@app.route("/compress_pdf", methods=["POST"])
def compress_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        compression_level = request.form.get('compression_level', 'medium')
        
        # Save the uploaded file
        filename = file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Open the PDF
        doc = fitz.open(filepath)
        
        # Set compression level
        if compression_level == "low":
            compression_quality = 0.8
        elif compression_level == "medium":
            compression_quality = 0.6
        else:  # high
            compression_quality = 0.4
        
        # Create compressed PDF
        compressed_filename = f"compressed_{filename}"
        compressed_path = os.path.join(EDITED_FOLDER, compressed_filename)
        
        # Save with compression
        doc.save(compressed_path, garbage=4, deflate=True, clean=True)
        doc.close()
        
        # Get file sizes
        original_size = os.path.getsize(filepath)
        compressed_size = os.path.getsize(compressed_path)
        compression_ratio = (1 - compressed_size / original_size) * 100
        
        return jsonify({
            "status": "success",
            "filename": compressed_filename,
            "original_size": original_size,
            "compressed_size": compressed_size,
            "compression_ratio": round(compression_ratio, 2),
            "download_url": f"/download_compressed/{compressed_filename}"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download_compressed/<filename>")
def download_compressed(filename):
    try:
        compressed_path = os.path.join(EDITED_FOLDER, filename)
        if os.path.exists(compressed_path):
            return send_file(compressed_path, as_attachment=True, download_name=filename)
        else:
            return "Compressed file not found", 404
    except Exception as e:
        return f"Error downloading compressed file: {str(e)}", 500

@app.route("/save_edit_fill_sign/<filename>", methods=["POST"])
def save_edit_fill_sign(filename):
    try:
        print(f"DEBUG: Save edit fill sign endpoint called with filename: {filename}")
        
        if 'pdf' not in request.files:
            return jsonify({"status": "error", "message": "No PDF file provided"}), 400
        
        pdf_file = request.files['pdf']
        if pdf_file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        elements_data = request.form.get('elements', '{}')
        elements = json.loads(elements_data)
        
        print(f"DEBUG: Elements data: {elements}")
        
        text_elements = elements.get('textElements', [])
        signature_elements = elements.get('signatureElements', [])
        image_elements = elements.get('imageElements', [])
        total_pages = elements.get('totalPages', 1)
        
        print(f"DEBUG: Text elements: {len(text_elements)}, Signature elements: {len(signature_elements)}, Image elements: {len(image_elements)}")
        
        if not text_elements and not signature_elements and not image_elements:
            return jsonify({"status": "error", "message": "No elements to save"}), 400
        
        # Save the uploaded PDF
        original_filename = pdf_file.filename
        safe_filename = "".join(c for c in original_filename if c.isalnum() or c in '._-')
        if not safe_filename.endswith('.pdf'):
            safe_filename += '.pdf'
        pdf_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        pdf_file.save(pdf_path)
        
        # Open the PDF
        doc = fitz.open(pdf_path)
        
        # Process text elements
        for text_element in text_elements:
            page_num = text_element.get('page', 1) - 1
            if 0 <= page_num < len(doc):
                page = doc[page_num]
                text = text_element.get('text', '')
                x = text_element.get('x', 0)
                y = text_element.get('y', 0)
                font_size = text_element.get('fontSize', 12)
                color = text_element.get('color', '#000000')
                
                # Convert color to RGB
                if color.startswith('#'):
                    color = color[1:]
                    r = int(color[0:2], 16) / 255.0
                    g = int(color[2:4], 16) / 255.0
                    b = int(color[4:6], 16) / 255.0
                    color_rgb = (r, g, b)
                else:
                    color_rgb = (0, 0, 0)
                
                # Insert text at the specified position (coordinates are already in PDF space)
                page.insert_text((x, y), text, fontsize=font_size, color=color_rgb)
        
        # Process signature elements
        for sig_element in signature_elements:
            page_num = sig_element.get('page', 1) - 1
            if 0 <= page_num < len(doc):
                page = doc[page_num]
                signature_data = sig_element.get('data', '')
                x = sig_element.get('x', 0)
                y = sig_element.get('y', 0)
                width = sig_element.get('width', 200)
                height = sig_element.get('height', 100)
                
                if signature_data:
                    # Remove data URL prefix if present
                    if signature_data.startswith('data:image'):
                        signature_data = signature_data.split(',')[1]
                    
                    # Decode base64 image
                    signature_bytes = base64.b64decode(signature_data)
                    
                    # Create signature rectangle
                    signature_rect = fitz.Rect(x, y, x + width, y + height)
                    
                    # Create a temporary image file
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    temp_img_path = os.path.join(UPLOAD_FOLDER, f"temp_signature_{timestamp}.png")
                    with open(temp_img_path, 'wb') as f:
                        f.write(signature_bytes)
                    
                    # Insert signature image
                    page.insert_image(signature_rect, filename=temp_img_path)
                    
                    # Clean up temporary file
                    if os.path.exists(temp_img_path):
                        os.remove(temp_img_path)
        
        # Process image elements
        for img_element in image_elements:
            page_num = img_element.get('page', 1) - 1
            if 0 <= page_num < len(doc):
                page = doc[page_num]
                image_data = img_element.get('data', '')
                x = img_element.get('x', 0)
                y = img_element.get('y', 0)
                width = img_element.get('width', 200)
                height = img_element.get('height', 150)
                
                if image_data:
                    # Remove data URL prefix if present
                    if image_data.startswith('data:image'):
                        image_data = image_data.split(',')[1]
                    
                    # Decode base64 image
                    image_bytes = base64.b64decode(image_data)
                    
                    # Create image rectangle
                    image_rect = fitz.Rect(x, y, x + width, y + height)
                    
                    # Create a temporary image file
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    temp_img_path = os.path.join(UPLOAD_FOLDER, f"temp_image_{timestamp}.png")
                    with open(temp_img_path, 'wb') as f:
                        f.write(image_bytes)
                    
                    # Insert image
                    page.insert_image(image_rect, filename=temp_img_path)
                    
                    # Clean up temporary file
                    if os.path.exists(temp_img_path):
                        os.remove(temp_img_path)
        
        # Generate output filename
        base_name = os.path.splitext(safe_filename)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        edited_filename = f"{base_name}_filled_signed_{timestamp}.pdf"
        edited_path = os.path.join(HTML_FOLDER, edited_filename)
        
        # Save the modified PDF
        doc.save(edited_path)
        doc.close()
        
        # Clean up uploaded PDF
        os.remove(pdf_path)
        
        return jsonify({
            "status": "success",
            "message": f"PDF updated successfully with {len(text_elements)} text elements, {len(signature_elements)} signatures, and {len(image_elements)} images",
            "filename": edited_filename,
            "download_url": f"/download_edited/{edited_filename}",
            "text_elements": len(text_elements),
            "signature_elements": len(signature_elements),
            "image_elements": len(image_elements)
        })
        
    except Exception as e:
        print(f"ERROR in save_edit_fill_sign: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download_edited/<filename>")
def download_edited(filename):
    try:
        # Check in EDITED_FOLDER first (for HTML to PDF conversions and edited PDFs)
        edited_path = os.path.join(EDITED_FOLDER, filename)
        if not os.path.exists(edited_path):
            # Fallback to HTML_FOLDER for backward compatibility
            edited_path = os.path.join(HTML_FOLDER, filename)
            if not os.path.exists(edited_path):
                return "Edited PDF file not found", 404
        
        return send_file(edited_path, as_attachment=True, download_name=filename)
    
    except Exception as e:
        return f"Error downloading edited PDF: {str(e)}", 500

@app.route("/convert-video", methods=["POST"])
def convert_video():
    try:
        print(f"DEBUG: Video conversion endpoint called")
        print(f"DEBUG: Request files: {list(request.files.keys())}")
        print(f"DEBUG: Request form: {list(request.form.keys())}")
        
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No video file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Get conversion parameters
        output_format = request.form.get('outputFormat', 'mp4')
        quality = int(request.form.get('quality', 80))
        compression = request.form.get('compression', 'medium')
        
        print(f"DEBUG: Converting to {output_format}, quality: {quality}%, compression: {compression}")
        print(f"DEBUG: Quality type: {type(quality)}, Quality value: {quality}")
        print(f"DEBUG: Quality from form: {request.form.get('quality')}")
        print(f"DEBUG: Quality as int: {int(request.form.get('quality', 80))}")
        
        # Save the uploaded file with unique filename to prevent conflicts
        import uuid
        original_filename = file.filename
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{unique_id}_{original_filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        print(f"DEBUG: Video file saved: {filepath}")
        
        # Generate output filename
        base_name = os.path.splitext(filename)[0]
        converted_filename = f"{base_name}_converted.{output_format}"
        converted_path = os.path.join(VIDEO_FOLDER, converted_filename)
        
        # Get original file size
        original_size = os.path.getsize(filepath)
        print(f"DEBUG: Original file size: {original_size} bytes ({original_size / 1024 / 1024:.2f} MB)")
        
        # REAL video compression using FFmpeg
        import subprocess
        import shutil
        
        # Map quality to CRF (Constant Rate Factor) for H.264
        # LOWER CRF = HIGHER QUALITY = LARGER FILE
        # HIGHER CRF = LOWER QUALITY = SMALLER FILE
        quality_map = {
            95: 18,  # Ultra High - larger file
            85: 23,  # High - larger file  
            75: 28,  # Medium - balanced
            60: 32,  # Low - smaller file
            40: 36   # Very Low - much smaller file
        }
        
        # Map compression to preset
        preset_map = {
            'none': 'ultrafast',
            'light': 'fast',
            'medium': 'medium',
            'heavy': 'slow',
            'web': 'veryslow'
        }
        
        crf = quality_map.get(quality, 28)
        preset = preset_map.get(compression, 'medium')
        
        print(f"DEBUG: Quality mapping - Input quality: {quality}, Mapped CRF: {crf}")
        print(f"DEBUG: Compression mapping - Input compression: {compression}, Mapped preset: {preset}")
        print(f"DEBUG: Starting FFmpeg compression with CRF={crf}, preset={preset}")
        
        # Initialize progress tracking using unique filename
        conversion_progress[filename] = {
            "status": "processing",
            "progress": 0,
            "message": "Initializing video compression..."
        }
        print(f"DEBUG: Initialized progress tracking for {filename}")
        
        # Start conversion in background thread
        import threading
        conversion_thread = threading.Thread(target=convert_video_background, args=(filename, filepath, converted_path, crf, preset))
        conversion_thread.daemon = True
        conversion_thread.start()
        
        # Wait a moment to ensure background thread has started
        import time
        time.sleep(0.1)
        
        # Return immediately with success status
        response_data = {
            "status": "success",
            "message": "Video upload successful, conversion started",
            "unique_filename": filename,
            "original_size": original_size,
            # converted_size will be updated by background thread when conversion completes
            "original_format": "MP4",
            "converted_format": output_format.upper(),
            "quality": quality,
            "compression": compression,
            "converted_filename": converted_filename,
            "download_url": f"/download_converted_video/{converted_filename}"
        }
        
        print(f"DEBUG: Returning immediate response: {response_data}")
        print(f"DEBUG: ASYNC MODE - Video conversion started in background thread")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"ERROR in convert_video: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

def convert_video_background(filename, filepath, converted_path, crf, preset):
    """Background video conversion function"""
    try:
        print(f"DEBUG: Starting background conversion for {filename}")
        print(f"DEBUG: Using CRF={crf}, preset={preset}")
        
        # Update progress to 0% only if not already set
        if filename not in conversion_progress or conversion_progress[filename]["progress"] == 0:
            conversion_progress[filename] = {
                "status": "processing",
                "progress": 0,
                "message": "Initializing video compression..."
            }
        
        # Get output format from the converted path
        output_format = os.path.splitext(converted_path)[1][1:]  # Remove the dot
        
        # FFmpeg command using user-selected quality and compression settings
        # Choose codec based on output format
        if output_format.lower() == 'webm':
            video_codec = 'libvpx-vp9'
            audio_codec = 'libvorbis'
            quality_param = '-crf'
        elif output_format.lower() == 'mp4':
            video_codec = 'libx264'
            audio_codec = 'aac'
            quality_param = '-crf'
        elif output_format.lower() == 'avi':
            video_codec = 'libx264'
            audio_codec = 'aac'
            quality_param = '-crf'
        elif output_format.lower() == 'mov':
            video_codec = 'libx264'
            audio_codec = 'aac'
            quality_param = '-crf'
        elif output_format.lower() == 'mkv':
            video_codec = 'libx264'
            audio_codec = 'aac'
            quality_param = '-crf'
        elif output_format.lower() == 'flv':
            video_codec = 'libx264'
            audio_codec = 'aac'
            quality_param = '-crf'
        elif output_format.lower() == 'wmv':
            video_codec = 'wmv2'
            audio_codec = 'wmav2'
            quality_param = '-q:v'
        elif output_format.lower() == 'm4v':
            video_codec = 'libx264'
            audio_codec = 'aac'
            quality_param = '-crf'
        elif output_format.lower() == '3gp':
            video_codec = 'libx264'
            audio_codec = 'aac'
            quality_param = '-crf'
        elif output_format.lower() == 'ogv':
            video_codec = 'libtheora'
            audio_codec = 'libvorbis'
            quality_param = '-q:v'
        elif output_format.lower() == 'mp3':
            # MP3 is audio-only, no video codec needed
            video_codec = None
            audio_codec = 'libmp3lame'
            quality_param = '-q:a'  # Audio quality instead of video
        else:
            # Default to MP4 settings
            video_codec = 'libx264'
            audio_codec = 'aac'
            quality_param = '-crf'
        
        # Build FFmpeg command based on output format
        if output_format.lower() == 'mp3':
            # MP3 is audio-only, no video processing needed
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', filepath,
                '-vn',  # No video
                '-c:a', audio_codec,
                quality_param, str(crf),  # Use audio quality
                '-b:a', '128k',
                '-y',  # Overwrite output file
                converted_path
            ]
        else:
            # Video conversion with both video and audio codecs
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', filepath,
                '-c:v', video_codec,
                quality_param, str(crf),  # Use user-selected CRF value
                '-preset', preset,  # Use user-selected preset
                '-c:a', audio_codec,
                '-b:a', '128k',
                '-y',  # Overwrite output file
                converted_path
            ]
        
        print(f"DEBUG: Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
        print(f"DEBUG: Input file: {filepath}")
        print(f"DEBUG: Output file: {converted_path}")
        print(f"DEBUG: Input file exists: {os.path.exists(filepath)}")
        print(f"DEBUG: Input file size: {os.path.getsize(filepath) if os.path.exists(filepath) else 'N/A'}")
        print(f"DEBUG: Output directory: {os.path.dirname(converted_path)}")
        print(f"DEBUG: Output directory exists: {os.path.exists(os.path.dirname(converted_path))}")
        print(f"DEBUG: Output filename: {os.path.basename(converted_path)}")
        
        # Check if FFmpeg is available first
        try:
            ffmpeg_check = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
            if ffmpeg_check.returncode != 0:
                print(f"ERROR: FFmpeg is not working! Return code: {ffmpeg_check.returncode}")
                print(f"ERROR: FFmpeg stderr: {ffmpeg_check.stderr}")
                raise FileNotFoundError("FFmpeg is not working properly")
            else:
                print(f"DEBUG: FFmpeg is available and working")
        except FileNotFoundError:
            print(f"ERROR: FFmpeg not found in PATH")
            raise
        except Exception as e:
            print(f"ERROR: FFmpeg check failed: {e}")
            raise
        
        # Update progress to show FFmpeg is starting
        conversion_progress[filename] = {
            "status": "processing",
            "progress": 1,
            "message": "Starting FFmpeg compression..."
        }
        print(f"DEBUG: Progress set to 1% - FFmpeg starting")
        
        # Run FFmpeg with real-time output for progress tracking
        print(f"DEBUG: Input file exists: {os.path.exists(filepath)}")
        print(f"DEBUG: Input file size: {os.path.getsize(filepath) if os.path.exists(filepath) else 'N/A'}")
        print(f"DEBUG: Output path: {converted_path}")
        print(f"DEBUG: Output directory exists: {os.path.exists(os.path.dirname(converted_path))}")
        
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True,
            bufsize=1
        )
        
        # Track the process for potential cancellation
        running_processes[filename] = {
            'process': process,
            'start_time': time.time(),
            'filepath': filepath,
            'converted_path': converted_path
        }
        print(f"DEBUG: Process tracked for cancellation: {filename} (PID: {process.pid})")
        
        # Real-time progress tracking from FFmpeg output
        start_time = time.time()
        last_update = start_time
        total_duration = None
        current_time_pos = 0
        
        # First, get video duration
        try:
            duration_cmd = [
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', filepath
            ]
            duration_result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
            if duration_result.returncode == 0:
                total_duration = float(duration_result.stdout.strip())
                print(f"DEBUG: Video duration: {total_duration:.2f} seconds")
        except:
            print("DEBUG: Could not get video duration, using fallback progress")
        
        # FFmpeg outputs progress to stderr
        stderr_output = []
        while True:
            output = process.stderr.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                line = output.strip()
                stderr_output.append(line)
                current_time = time.time()
                elapsed_time = current_time - start_time
                
                # Debug: Print all FFmpeg output to see what we're getting
                print(f"DEBUG: FFmpeg output: {line}")
                
                # Parse FFmpeg output for real progress
                if 'time=' in line:
                    try:
                        time_part = [part for part in line.split() if part.startswith('time=')][0]
                        time_str = time_part.split('=')[1]
                        # Parse time format (HH:MM:SS.mmm)
                        time_parts = time_str.split(':')
                        if len(time_parts) == 3:
                            hours, minutes, seconds = time_parts
                            current_time_pos = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                            
                            # Calculate real progress percentage
                            if total_duration and total_duration > 0:
                                progress = max(1, min(99, int((current_time_pos / total_duration) * 100)))
                                conversion_progress[filename]["message"] = f"Processing video... {time_str} ({progress}%)"
                                conversion_progress[filename]["progress"] = progress
                                print(f"DEBUG: Real progress: {progress}% - {time_str} / {total_duration:.2f}s")
                            else:
                                # Fallback to time-based if no duration
                                progress = min(95, max(1, 1 + int(elapsed_time * 3.2)))
                                conversion_progress[filename]["message"] = f"Processing video... {time_str} ({elapsed_time:.0f}s)"
                                conversion_progress[filename]["progress"] = progress
                                print(f"DEBUG: Fallback progress: {progress}% - {elapsed_time:.0f}s")
                    except Exception as e:
                        print(f"DEBUG: Error parsing time: {e}")
                
                elif 'frame=' in line:
                    try:
                        frame_part = [part for part in line.split() if part.startswith('frame=')][0]
                        frame_num = int(frame_part.split('=')[1])
                        conversion_progress[filename]["message"] = f"Processing frame {frame_num}... ({elapsed_time:.0f}s)"
                    except:
                        pass
                
                # Update every 2 seconds as fallback
                elif current_time - last_update >= 2.0:
                    if not total_duration:
                        progress = min(95, max(1, 1 + int(elapsed_time * 3.2)))
                        conversion_progress[filename]["message"] = f"Processing video... {elapsed_time:.0f}s elapsed"
                        conversion_progress[filename]["progress"] = progress
                        print(f"DEBUG: Fallback progress update: {progress}% - {elapsed_time:.0f}s elapsed")
                    last_update = current_time
        
        # Set progress to 99% before waiting for completion
        conversion_progress[filename]["progress"] = 99
        conversion_progress[filename]["message"] = "Finalizing conversion..."
        print(f"DEBUG: Progress set to 99% - finalizing conversion")
        
        # Wait for process to complete with timeout
        return_code = -1  # Initialize return_code
        try:
            print(f"DEBUG: Waiting for FFmpeg process to complete...")
            print(f"DEBUG: Process PID: {process.pid}")
            print(f"DEBUG: Process is still running: {process.poll() is None}")
            
            return_code = process.wait(timeout=300)  # 5 minute timeout for large videos
            print(f"DEBUG: FFmpeg process completed with return code: {return_code}")
        except subprocess.TimeoutExpired:
            print(f"DEBUG: FFmpeg process timed out after 5 minutes")
            print(f"DEBUG: Killing FFmpeg process...")
            process.kill()
            return_code = -1
        except Exception as e:
            print(f"DEBUG: FFmpeg process error: {e}")
            return_code = -1
        
        print(f"DEBUG: FFmpeg return code: {return_code}")
        print(f"DEBUG: Process is still running after wait: {process.poll() is None}")
        print(f"DEBUG: FFmpeg process completed, checking output file...")
        print(f"DEBUG: Expected output path: {converted_path}")
        print(f"DEBUG: Output directory exists: {os.path.exists(os.path.dirname(converted_path))}")
        print(f"DEBUG: Output file exists: {os.path.exists(converted_path)}")
        
        # Print full stderr output for debugging
        print(f"DEBUG: Full FFmpeg stderr output:")
        for i, line in enumerate(stderr_output[-10:]):  # Show last 10 lines
            print(f"DEBUG: stderr[{i}]: {line}")
        
        # List files in the output directory for debugging
        try:
            output_dir = os.path.dirname(converted_path)
            if os.path.exists(output_dir):
                files_in_dir = os.listdir(output_dir)
                print(f"DEBUG: Files in output directory: {files_in_dir}")
            else:
                print(f"DEBUG: Output directory does not exist: {output_dir}")
        except Exception as e:
            print(f"DEBUG: Error listing output directory: {e}")
        
        if return_code != 0:
            print(f"ERROR: FFmpeg failed with return code: {return_code}")
            # Don't try to read stderr again as it's already been consumed during progress tracking
        
        if return_code == 0:
            print(f"DEBUG: FFmpeg compression completed successfully")
            # Check if output file was created and get its size
            if os.path.exists(converted_path):
                output_size = os.path.getsize(converted_path)
                input_size = os.path.getsize(filepath)
                compression_ratio = ((input_size - output_size) / input_size) * 100
                print(f"DEBUG: Output file created successfully")
                print(f"DEBUG: Input size: {input_size} bytes")
                print(f"DEBUG: Output size: {output_size} bytes")
                print(f"DEBUG: Compression ratio: {compression_ratio:.2f}%")
                print(f"DEBUG: Converted file path: {converted_path}")
                print(f"DEBUG: Converted file exists: {os.path.exists(converted_path)}")
                print(f"DEBUG: Converted file size: {os.path.getsize(converted_path) if os.path.exists(converted_path) else 'N/A'}")
                
                # Check if compression actually occurred
                print(f"DEBUG: Comparing sizes - Output: {output_size}, Input: {input_size}, Comparison: {output_size >= input_size}")
                if output_size >= input_size:
                    print(f"WARNING: No compression occurred! Output size ({output_size}) >= Input size ({input_size})")
                    print(f"WARNING: This might indicate FFmpeg failed to compress or the file is already optimized")
                    # Try a more aggressive compression
                    print(f"DEBUG: Attempting more aggressive compression...")
                    if output_format.lower() == 'mp3':
                        # MP3 aggressive compression (audio-only)
                        aggressive_cmd = [
                            'ffmpeg',
                            '-i', filepath,
                            '-vn',  # No video
                            '-c:a', audio_codec,
                            quality_param, '9',  # Much higher audio quality for smaller file
                            '-b:a', '64k',  # Very low audio bitrate
                            '-y',
                            converted_path
                        ]
                    else:
                        # Video aggressive compression
                        aggressive_cmd = [
                            'ffmpeg',
                            '-i', filepath,
                            '-c:v', video_codec,
                            quality_param, '35',  # Much higher CRF for smaller file
                            '-preset', 'ultrafast',
                            '-c:a', audio_codec,
                            '-b:a', '16k',  # Very low audio bitrate
                            '-maxrate', '200k',  # Very low max bitrate
                            '-bufsize', '400k',
                            '-y',
                            converted_path
                        ]
                    print(f"DEBUG: Running aggressive FFmpeg command: {' '.join(aggressive_cmd)}")
                    aggressive_result = subprocess.run(aggressive_cmd, capture_output=True, text=True, timeout=60)
                    print(f"DEBUG: Aggressive FFmpeg return code: {aggressive_result.returncode}")
                    print(f"DEBUG: Aggressive FFmpeg stdout: {aggressive_result.stdout}")
                    print(f"DEBUG: Aggressive FFmpeg stderr: {aggressive_result.stderr}")
                    
                    if aggressive_result.returncode == 0 and os.path.exists(converted_path):
                        new_output_size = os.path.getsize(converted_path)
                        new_compression_ratio = ((input_size - new_output_size) / input_size) * 100
                        print(f"DEBUG: Aggressive compression result: {new_output_size} bytes ({new_compression_ratio:.2f}% reduction)")
                        if new_output_size < input_size:
                            output_size = new_output_size
                            compression_ratio = new_compression_ratio
                            print(f"DEBUG: Aggressive compression successful!")
                        else:
                            print(f"WARNING: Even aggressive compression failed to reduce file size")
                    else:
                        print(f"ERROR: Aggressive compression failed! Return code: {aggressive_result.returncode}")
                        print(f"ERROR: This suggests FFmpeg is not working properly on Railway")
                        # Force a smaller file by using a different approach
                        print(f"DEBUG: Trying to force compression by reducing resolution...")
                        if output_format.lower() == 'mp3':
                            # MP3 force compression (audio-only)
                            force_cmd = [
                                'ffmpeg',
                                '-i', filepath,
                                '-vn',  # No video
                                '-c:a', audio_codec,
                                quality_param, '9',  # Very high audio quality
                                '-b:a', '32k',  # Very low audio bitrate
                                '-y',
                                converted_path
                            ]
                        else:
                            # Video force compression
                            force_cmd = [
                                'ffmpeg',
                                '-i', filepath,
                                '-vf', 'scale=320:240',  # Force smaller resolution
                                '-c:v', video_codec,
                                quality_param, '40',  # Very high CRF
                                '-preset', 'ultrafast',
                                '-c:a', audio_codec,
                                '-b:a', '8k',  # Very low audio
                                '-y',
                                converted_path
                            ]
                        print(f"DEBUG: Running force compression command: {' '.join(force_cmd)}")
                        force_result = subprocess.run(force_cmd, capture_output=True, text=True, timeout=60)
                        print(f"DEBUG: Force compression return code: {force_result.returncode}")
                        print(f"DEBUG: Force compression stdout: {force_result.stdout}")
                        print(f"DEBUG: Force compression stderr: {force_result.stderr}")
                        
                        if force_result.returncode == 0 and os.path.exists(converted_path):
                            force_output_size = os.path.getsize(converted_path)
                            force_compression_ratio = ((input_size - force_output_size) / input_size) * 100
                            print(f"DEBUG: Force compression result: {force_output_size} bytes ({force_compression_ratio:.2f}% reduction)")
                            if force_output_size < input_size:
                                output_size = force_output_size
                                compression_ratio = force_compression_ratio
                                print(f"DEBUG: Force compression successful!")
                            else:
                                print(f"ERROR: Even force compression failed! FFmpeg is not working on Railway!")
                        else:
                            print(f"ERROR: Force compression also failed! FFmpeg is definitely not working on Railway!")
                    
                    # Set final progress
                    conversion_progress[filename] = {
                        "status": "completed",
                        "progress": 100,
                        "message": f"Video compression completed! Size reduced by {compression_ratio:.1f}%",
                        "original_size": input_size,
                        "converted_size": output_size,
                        "compression_ratio": compression_ratio,
                        "converted_filename": os.path.basename(converted_path)
                    }
                    print(f"DEBUG: Progress set to 100% - conversion completed with sizes: {input_size} -> {output_size}")
                else:
                    # Compression was successful, no need for aggressive compression
                    print(f"DEBUG: Compression successful! No aggressive compression needed.")
                    # Set final progress
                    conversion_progress[filename] = {
                        "status": "completed",
                        "progress": 100,
                        "message": f"Video compression completed! Size reduced by {compression_ratio:.1f}%",
                        "original_size": input_size,
                        "converted_size": output_size,
                        "compression_ratio": compression_ratio,
                        "converted_filename": os.path.basename(converted_path)
                    }
                    print(f"DEBUG: Progress set to 100% - conversion completed with sizes: {input_size} -> {output_size}")
                    return  # Exit the function here to prevent fallback logic
            else:  # This 'else' corresponds to 'if os.path.exists(converted_path):' at line 2323
                print(f"DEBUG: Output file not created, falling back to copy")
                import shutil
                shutil.copy2(filepath, converted_path)
                # Get file sizes for fallback
                input_size = os.path.getsize(filepath)
                output_size = os.path.getsize(converted_path)
                conversion_progress[filename] = {
                    "status": "completed",
                    "progress": 100,
                    "message": "Video processing completed (fallback mode)",
                    "original_size": input_size,
                    "converted_size": output_size,
                    "compression_ratio": 0.0,
                    "converted_filename": os.path.basename(converted_path)
                }
                print(f"DEBUG: Progress set to 100% - fallback completed")
            
    except subprocess.TimeoutExpired:
        print(f"DEBUG: FFmpeg timeout after 2 minutes, falling back to copy")
        import shutil
        shutil.copy2(filepath, converted_path)
    except FileNotFoundError:
        print(f"DEBUG: FFmpeg not found in PATH, falling back to copy")
        print(f"DEBUG: Please install FFmpeg: https://ffmpeg.org/download.html")
        import shutil
        shutil.copy2(filepath, converted_path)
    except Exception as e:
        print(f"DEBUG: FFmpeg error: {e}, falling back to copy")
        import shutil
        shutil.copy2(filepath, converted_path)
    
    # Clean up process tracking
    if filename in running_processes:
        del running_processes[filename]
        print(f"DEBUG: Process tracking cleaned up for {filename}")
    
    print(f"DEBUG: Background conversion completed for {filename}")

@app.route("/download_converted_video/<path:filename>")
def download_converted_video(filename):
    try:
        # Decode URL-encoded filename
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        
        # Use absolute path to avoid any path resolution issues
        file_path = os.path.abspath(os.path.join(VIDEO_FOLDER, decoded_filename))
        print(f"DEBUG: Download request for filename: {filename}")
        print(f"DEBUG: Decoded filename: {decoded_filename}")
        print(f"DEBUG: VIDEO_FOLDER: {VIDEO_FOLDER}")
        print(f"DEBUG: VIDEO_FOLDER absolute path: {os.path.abspath(VIDEO_FOLDER)}")
        print(f"DEBUG: Looking for file: {file_path}")
        print(f"DEBUG: File exists: {os.path.exists(file_path)}")
        print(f"DEBUG: Current working directory: {os.getcwd()}")
        print(f"DEBUG: VIDEO_FOLDER exists: {os.path.exists(VIDEO_FOLDER)}")
        print(f"DEBUG: VIDEO_FOLDER is directory: {os.path.isdir(VIDEO_FOLDER)}")
        
        if not os.path.exists(file_path):
            print(f"DEBUG: File not found: {file_path}")
            # List files in the directory to debug
            try:
                video_dir = os.path.abspath(VIDEO_FOLDER)
                files_in_dir = os.listdir(video_dir)
                print(f"DEBUG: Files in {video_dir}: {files_in_dir}")
                print(f"DEBUG: Looking for: {decoded_filename}")
            except Exception as e:
                print(f"DEBUG: Error listing directory: {e}")
            return "Converted video file not found", 404
        
        print(f"DEBUG: File found, sending: {file_path}")
        return send_file(file_path, as_attachment=True, download_name=decoded_filename)
    
    except Exception as e:
        print(f"ERROR in download_converted_video: {str(e)}")
        return f"Error downloading converted video: {str(e)}", 500

@app.route("/conversion_progress/<filename>")
def get_conversion_progress(filename):
    """Get the progress of a video conversion"""
    try:
        # Decode URL-encoded filename
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        
        # Try to find progress by exact match first
        progress = conversion_progress.get(decoded_filename)
        
        # If not found, try to find by partial match (for unique filenames)
        if not progress:
            for key, value in conversion_progress.items():
                if decoded_filename in key or key in decoded_filename:
                    progress = value
                    print(f"DEBUG: Found progress by partial match: {key} -> {decoded_filename}")
                    break
        
        if not progress:
            progress = {
                "status": "not_found",
                "progress": 0,
                "message": "Conversion not found"
            }
        
        # Add converted_filename to the progress response if conversion is completed
        if progress.get("status") == "completed" and "converted_filename" not in progress:
            # Extract the converted filename from the original filename
            base_name = os.path.splitext(decoded_filename)[0]
            # Get the output format from the progress data or default to mp4
            output_format = progress.get("converted_format", "mp4").lower()
            converted_filename = f"{base_name}_converted.{output_format}"
            progress["converted_filename"] = converted_filename
        
        print(f"DEBUG: Progress request for {decoded_filename}: {progress}")
        return jsonify(progress)
    except Exception as e:
        print(f"DEBUG: Progress error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/cancel_conversion/<filename>", methods=["POST"])
def cancel_conversion(filename):
    """Cancel a running video conversion"""
    try:
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        
        print(f"DEBUG: Cancellation request for {decoded_filename}")
        
        # Find the process by filename (exact or partial match)
        process_to_kill = None
        for key, process_info in running_processes.items():
            if decoded_filename in key or key in decoded_filename:
                process_to_kill = process_info
                print(f"DEBUG: Found process to cancel: {key}")
                break
        
        if process_to_kill and 'process' in process_to_kill:
            process = process_to_kill['process']
            if process.poll() is None:  # Process is still running
                print(f"DEBUG: Terminating FFmpeg process PID: {process.pid}")
                process.terminate()
                
                # Wait a bit for graceful termination
                try:
                    process.wait(timeout=5)
                    print(f"DEBUG: Process terminated gracefully")
                except subprocess.TimeoutExpired:
                    print(f"DEBUG: Process didn't terminate gracefully, killing it")
                    process.kill()
                    process.wait()
                
                # Update progress to cancelled
                conversion_progress[decoded_filename] = {
                    "status": "cancelled",
                    "progress": 0,
                    "message": "Conversion cancelled by user"
                }
                
                # Clean up the process from tracking
                for key in list(running_processes.keys()):
                    if decoded_filename in key or key in decoded_filename:
                        del running_processes[key]
                        break
                
                print(f"DEBUG: Conversion cancelled successfully for {decoded_filename}")
                return jsonify({
                    "status": "success",
                    "message": "Conversion cancelled successfully"
                })
            else:
                print(f"DEBUG: Process already completed for {decoded_filename}")
                return jsonify({
                    "status": "already_completed",
                    "message": "Conversion already completed"
                })
        else:
            print(f"DEBUG: No running process found for {decoded_filename}")
            return jsonify({
                "status": "not_found",
                "message": "No running conversion found"
            }), 404
            
    except Exception as e:
        print(f"ERROR in cancel_conversion: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error cancelling conversion: {str(e)}"
        }), 500

# Audio Conversion Functions
def allowed_audio_file(filename):
    """Check if file extension is allowed for audio"""
    ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a', 'wma', 'aiff', 'au', 'opus'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS

def convert_audio_file(input_path, output_path, output_format, bitrate=192, sample_rate=44100, channels="stereo", quality=80):
    """Convert audio using FFmpeg"""
    try:
        print(f"DEBUG: Starting audio conversion from {input_path} to {output_path}")
        print(f"DEBUG: Format: {output_format}, Bitrate: {bitrate}, Sample Rate: {sample_rate}, Channels: {channels}, Quality: {quality}")
        
        # Build FFmpeg command based on output format
        cmd = ['ffmpeg', '-i', input_path]
        
        # Audio codec selection
        if output_format == 'mp3':
            cmd.extend(['-acodec', 'libmp3lame'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'aac':
            cmd.extend(['-acodec', 'aac'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'flac':
            cmd.extend(['-acodec', 'flac'])
        elif output_format == 'ogg':
            cmd.extend(['-acodec', 'libvorbis'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'opus':
            cmd.extend(['-acodec', 'libopus'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'wav':
            cmd.extend(['-acodec', 'pcm_s16le'])
        elif output_format == 'aiff':
            cmd.extend(['-acodec', 'pcm_s16be'])
        elif output_format == 'm4a':
            cmd.extend(['-acodec', 'aac'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'wma':
            cmd.extend(['-acodec', 'wmav2'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        else:
            # Default to libmp3lame for unknown formats
            cmd.extend(['-acodec', 'libmp3lame'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        
        # Sample rate
        cmd.extend(['-ar', str(sample_rate)])
        
        # Channel configuration
        if channels == 'mono':
            cmd.extend(['-ac', '1'])
        elif channels == 'stereo':
            cmd.extend(['-ac', '2'])
        elif channels == 'surround':
            cmd.extend(['-ac', '6'])  # 5.1 surround
        # For 'original', don't specify channels
        
        # Quality settings for lossy formats
        if output_format in ['mp3', 'aac', 'ogg', 'opus', 'm4a', 'wma']:
            if quality < 50:
                cmd.extend(['-q:a', '9'])  # Low quality
            elif quality < 70:
                cmd.extend(['-q:a', '6'])  # Medium quality
            elif quality < 90:
                cmd.extend(['-q:a', '3'])  # High quality
            else:
                cmd.extend(['-q:a', '0'])  # Maximum quality
        
        # Overwrite output file
        cmd.extend(['-y', output_path])
        
        print(f"DEBUG: Running FFmpeg command: {' '.join(cmd)}")
        
        # Run FFmpeg command
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print(f"DEBUG: FFmpeg return code: {result.returncode}")
        print(f"DEBUG: FFmpeg stdout: {result.stdout}")
        print(f"DEBUG: FFmpeg stderr: {result.stderr}")
        
        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")
        
        # Check if output file was created and has content
        if not os.path.exists(output_path):
            raise Exception("Output file was not created")
        
        output_size = os.path.getsize(output_path)
        print(f"DEBUG: Output file size: {output_size} bytes")
        
        if output_size == 0:
            raise Exception("Output file is empty")
        
        return True
        
    except Exception as e:
        print(f"Audio conversion error: {str(e)}")
        return False

@app.route('/convert-image', methods=['POST'])
def convert_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Get conversion settings
    output_format = request.form.get('outputFormat', 'jpg')
    quality = int(request.form.get('quality', 85))
    resize = request.form.get('resize', 'false').lower() == 'true'
    width = int(request.form.get('width', 1920))
    height = int(request.form.get('height', 1080))
    maintain_aspect_ratio = request.form.get('maintainAspectRatio', 'true').lower() == 'true'
    compression = request.form.get('compression', 'medium')
    
    try:
        # Create uploads directory if it doesn't exist
        uploads_dir = 'converted_images'
        uploads_dir = os.path.abspath(uploads_dir)  # Get absolute path
        os.makedirs(uploads_dir, exist_ok=True)
        print(f"DEBUG: Created/verified directory: {uploads_dir}")
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())[:8]
        original_filename = secure_filename(file.filename)
        name, ext = os.path.splitext(original_filename)
        filename = f"{unique_id}_{name}_converted.{output_format}"
        filepath = os.path.join(uploads_dir, filename)
        
        print(f"DEBUG: Target filepath: {filepath}")
        print(f"DEBUG: Directory exists: {os.path.exists(uploads_dir)}")
        
        # Save uploaded file
        temp_path = os.path.join(uploads_dir, f"temp_{unique_id}_{original_filename}")
        print(f"DEBUG: Temp filepath: {temp_path}")
        file.save(temp_path)
        
        # Get original file size
        original_size = os.path.getsize(temp_path)
        
        # Handle PDF conversion separately
        if output_format == 'pdf':
            try:
                from PIL import Image
                import fitz  # PyMuPDF
                
                # Open image with PIL
                img = Image.open(temp_path)
                
                # Convert image to RGB if necessary (PDF doesn't support RGBA directly)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create a white background
                    rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = rgb_img
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Get image dimensions
                img_width, img_height = img.size
                
                # Create PDF with PyMuPDF
                pdf_doc = fitz.open()
                # Convert pixels to points (assuming 72 DPI: 1 point = 1/72 inch)
                # For better quality, we can use the actual image DPI if available
                # Default to 72 DPI if not specified
                dpi = 72
                page_width = img_width * 72 / dpi  # Convert pixels to points
                page_height = img_height * 72 / dpi
                
                # Use A4 size if image is too large, otherwise use image size
                # A4 size in points: 595 x 842
                if page_width > 595 or page_height > 842:
                    # Scale to fit A4 while maintaining aspect ratio
                    scale = min(595 / page_width, 842 / page_height)
                    page_width = page_width * scale
                    page_height = page_height * scale
                
                page = pdf_doc.new_page(width=page_width, height=page_height)
                
                # Convert PIL image to bytes
                import io
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='PNG')
                img_bytes.seek(0)
                
                # Insert image into PDF page
                img_rect = fitz.Rect(0, 0, page_width, page_height)
                page.insert_image(img_rect, stream=img_bytes.getvalue())
                
                # Save PDF
                pdf_doc.save(filepath)
                pdf_doc.close()
                
                # Verify PDF file was created
                if not os.path.exists(filepath):
                    raise Exception(f"PDF file was not created at {filepath}")
                
                print(f"DEBUG: PDF file created successfully at: {filepath}")
                print(f"DEBUG: PDF file size: {os.path.getsize(filepath)} bytes")
                
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                # Get converted file size
                converted_size = os.path.getsize(filepath)
                compression_ratio = ((original_size - converted_size) / original_size) * 100
                
                # Create download URL
                download_url = f"/download/{filename}"
                
                print(f"DEBUG: Download URL: {download_url}")
                print(f"DEBUG: Full filepath for download: {os.path.abspath(filepath)}")
                
                return jsonify({
                    'success': True,
                    'downloadUrl': download_url,
                    'originalSize': original_size,
                    'convertedSize': converted_size,
                    'compressionRatio': compression_ratio,
                    'message': 'Image converted to PDF successfully'
                })
            except Exception as e:
                print(f"DEBUG: PDF conversion error: {str(e)}")
                import traceback
                traceback.print_exc()
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return jsonify({
                    'success': False,
                    'error': f'PDF conversion failed: {str(e)}'
                }), 500
        
        # Build FFmpeg command for image conversion (non-PDF formats)
        ffmpeg_cmd = ['ffmpeg', '-i', temp_path]
        
        # Add resize parameters if requested
        if resize:
            if maintain_aspect_ratio:
                ffmpeg_cmd.extend(['-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease'])
            else:
                ffmpeg_cmd.extend(['-vf', f'scale={width}:{height}'])
        
        # Add format-specific parameters
        if output_format in ['jpg', 'jpeg']:
            ffmpeg_cmd.extend(['-q:v', str(100 - quality)])  # FFmpeg uses inverse quality
        elif output_format == 'png':
            ffmpeg_cmd.extend(['-compression_level', str(9 - (quality // 10))])
        elif output_format == 'webp':
            ffmpeg_cmd.extend(['-quality', str(quality)])
        elif output_format == 'bmp':
            ffmpeg_cmd.extend(['-pix_fmt', 'bgr24'])
        elif output_format == 'tiff':
            ffmpeg_cmd.extend(['-compression', 'lzw'])
        elif output_format == 'gif':
            ffmpeg_cmd.extend(['-pix_fmt', 'pal8'])
        
        ffmpeg_cmd.extend(['-update', '1', '-y', filepath])  # Overwrite output file, single image
        
        print(f"DEBUG: Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
        
        try:
            # Run FFmpeg
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=60)
            print(f"DEBUG: FFmpeg return code: {result.returncode}")
            print(f"DEBUG: FFmpeg stdout: {result.stdout}")
            print(f"DEBUG: FFmpeg stderr: {result.stderr}")
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            if result.returncode == 0:
                # Check if output file was created
                if os.path.exists(filepath):
                    # Get converted file size
                    converted_size = os.path.getsize(filepath)
                    compression_ratio = ((original_size - converted_size) / original_size) * 100
                    
                    # Create download URL
                    download_url = f"/download/{filename}"
                    
                    return jsonify({
                        'success': True,
                        'downloadUrl': download_url,
                        'originalSize': original_size,
                        'convertedSize': converted_size,
                        'compressionRatio': compression_ratio,
                        'message': 'Image converted successfully'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'FFmpeg completed but no output file was created'
                    }), 500
            else:
                return jsonify({
                    'success': False,
                    'error': f'FFmpeg error: {result.stderr}'
                }), 500
        except subprocess.TimeoutExpired:
            return jsonify({
                'success': False,
                'error': 'FFmpeg process timed out'
            }), 500
        except Exception as e:
            print(f"DEBUG: Exception in FFmpeg execution: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'FFmpeg execution error: {str(e)}'
            }), 500
            
    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Conversion timed out'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Conversion failed: {str(e)}'
        }), 500

@app.route('/generate-qr', methods=['POST'])
def generate_qr():
    """Generate QR code from provided data"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        qr_type = data.get('type', 'text')
        qr_data = data.get('data', {})
        
        # Import qrcode here to avoid import errors if not installed
        try:
            import qrcode
            from io import BytesIO
            import base64
        except ImportError as e:
            print(f"DEBUG: Import error: {e}")
            return jsonify({
                'success': False,
                'error': f'QR code library not installed: {str(e)}'
            }), 500
        
        # Generate QR code content based on type
        qr_content = ""
        
        if qr_type == 'url':
            qr_content = qr_data.get('url', '')
        elif qr_type == 'text':
            qr_content = qr_data.get('text', '')
        elif qr_type == 'wifi':
            ssid = qr_data.get('ssid', '')
            password = qr_data.get('password', '')
            encryption = qr_data.get('encryption', 'WPA')
            hidden = qr_data.get('hidden', False)
            qr_content = f"WIFI:T:{encryption};S:{ssid};P:{password};H:{str(hidden).lower()};;"
        elif qr_type == 'email':
            email = qr_data.get('email', '')
            subject = qr_data.get('subject', '')
            body = qr_data.get('body', '')
            qr_content = f"mailto:{email}?subject={subject}&body={body}"
        elif qr_type == 'sms':
            phone = qr_data.get('phoneNumber', '')
            message = qr_data.get('message', '')
            qr_content = f"sms:{phone}:{message}"
        elif qr_type == 'phone':
            phone = qr_data.get('phone', '')
            qr_content = f"tel:{phone}"
        elif qr_type == 'vcard':
            name = qr_data.get('name', '')
            organization = qr_data.get('organization', '')
            title = qr_data.get('vcardTitle', '')
            phone = qr_data.get('vcardPhone', '')
            email = qr_data.get('email', '')
            website = qr_data.get('website', '')
            address = qr_data.get('address', '')
            
            vcard = f"BEGIN:VCARD\nVERSION:3.0\n"
            if name: vcard += f"FN:{name}\n"
            if organization: vcard += f"ORG:{organization}\n"
            if title: vcard += f"TITLE:{title}\n"
            if phone: vcard += f"TEL:{phone}\n"
            if email: vcard += f"EMAIL:{email}\n"
            if website: vcard += f"URL:{website}\n"
            if address: vcard += f"ADR:{address}\n"
            vcard += "END:VCARD"
            qr_content = vcard
        elif qr_type == 'location':
            latitude = qr_data.get('latitude', 0)
            longitude = qr_data.get('longitude', 0)
            qr_content = f"geo:{latitude},{longitude}"
        elif qr_type == 'calendar':
            title = qr_data.get('calendarTitle', '')
            description = qr_data.get('description', '')
            start_date = qr_data.get('startDate', '')
            end_date = qr_data.get('endDate', '')
            location = qr_data.get('location', '')
            
            # Create a simple calendar event format
            qr_content = f"BEGIN:VEVENT\nSUMMARY:{title}\nDESCRIPTION:{description}\nDTSTART:{start_date}\nDTEND:{end_date}\nLOCATION:{location}\nEND:VEVENT"
        else:
            qr_content = str(qr_data.get('text', ''))
        
        if not qr_content:
            return jsonify({
                'success': False,
                'error': 'No content to generate QR code for'
            }), 400
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_content)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'qr_code': f"data:image/png;base64,{img_str}",
            'content': qr_content,
            'type': qr_type
        })
        
    except Exception as e:
        print(f"ERROR: QR generation failed: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'QR generation failed: {str(e)}'
        }), 500

@app.route('/download/<filename>')
def download_file(filename):
    """Download converted files"""
    try:
        # Check in converted_images directory first
        converted_images_path = os.path.abspath(os.path.join('converted_images', filename))
        print(f"DEBUG: Looking for file at: {converted_images_path}")
        print(f"DEBUG: File exists: {os.path.exists(converted_images_path)}")
        print(f"DEBUG: Current working directory: {os.getcwd()}")
        print(f"DEBUG: Absolute path: {converted_images_path}")
        
        if os.path.exists(converted_images_path):
            print(f"DEBUG: Sending file: {converted_images_path}")
            # Determine MIME type based on file extension
            mimetype = None
            if filename.lower().endswith('.pdf'):
                mimetype = 'application/pdf'
            elif filename.lower().endswith(('.jpg', '.jpeg')):
                mimetype = 'image/jpeg'
            elif filename.lower().endswith('.png'):
                mimetype = 'image/png'
            elif filename.lower().endswith('.webp'):
                mimetype = 'image/webp'
            elif filename.lower().endswith('.gif'):
                mimetype = 'image/gif'
            
            return send_file(
                converted_images_path, 
                as_attachment=True, 
                download_name=filename,
                mimetype=mimetype
            )
        
        # Check in other directories if needed
        converted_videos_path = os.path.abspath(os.path.join('converted_videos', filename))
        if os.path.exists(converted_videos_path):
            print(f"DEBUG: Sending file from videos: {converted_videos_path}")
            return send_file(converted_videos_path, as_attachment=True, download_name=filename)
        
        # List files in converted_images directory for debugging
        converted_images_dir = os.path.abspath('converted_images')
        if os.path.exists(converted_images_dir):
            files_in_dir = os.listdir(converted_images_dir)
            print(f"DEBUG: Files in converted_images directory: {files_in_dir}")
            
        return jsonify({'error': f'File not found: {filename}'}), 404
    except Exception as e:
        print(f"DEBUG: Download error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/convert-audio', methods=['POST'])
def convert_audio():
    """Convert audio to different format"""
    try:
        # Check if file is provided
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Check file type
        if not allowed_audio_file(file.filename):
            return jsonify({"status": "error", "message": "Invalid file type"}), 400
        
        # Get parameters
        output_format = request.form.get('outputFormat', 'mp3')
        bitrate = int(request.form.get('bitrate', 192))
        sample_rate = int(request.form.get('sampleRate', 44100))
        channels = request.form.get('channels', 'stereo')
        quality = int(request.form.get('quality', 80))
        
        print(f"DEBUG: Received request - Format: {output_format}, Bitrate: {bitrate}, Sample Rate: {sample_rate}, Channels: {channels}, Quality: {quality}")
        
        # Generate unique filenames
        unique_id = str(uuid.uuid4())[:8]
        original_filename = file.filename
        base_name = os.path.splitext(original_filename)[0]
        
        # Input file path
        input_filename = f"{unique_id}_{original_filename}"
        input_path = os.path.join(AUDIO_FOLDER, input_filename)
        
        # Output file path
        output_filename = f"{unique_id}_{base_name}_converted.{output_format}"
        output_path = os.path.join(AUDIO_FOLDER, output_filename)
        
        print(f"DEBUG: Input path: {input_path}")
        print(f"DEBUG: Output path: {output_path}")
        
        # Save uploaded file
        file.save(input_path)
        print(f"DEBUG: File saved successfully")
        
        # Get original file size
        original_size = os.path.getsize(input_path)
        print(f"DEBUG: Original file size: {original_size} bytes")
        
        # Convert audio
        print(f"DEBUG: Starting conversion...")
        success = convert_audio_file(input_path, output_path, output_format, bitrate, sample_rate, channels, quality)
        print(f"DEBUG: Conversion result: {success}")
        
        if not success:
            # Clean up input file
            if os.path.exists(input_path):
                os.remove(input_path)
            return jsonify({"status": "error", "message": "Conversion failed"}), 500
        
        # Get converted file size
        converted_size = os.path.getsize(output_path)
        
        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)
        
        # Return success response
        return jsonify({
            "status": "success",
            "message": f"Audio conversion completed successfully",
            "original_filename": original_filename,
            "converted_filename": output_filename,
            "original_size": original_size,
            "converted_size": converted_size,
            "download_url": f"/download_converted_audio/{output_filename}",
            "output_format": output_format,
            "bitrate": bitrate,
            "sample_rate": sample_rate,
            "channels": channels,
            "quality": quality
        })
        
    except Exception as e:
        print(f"Error in convert_audio: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/download_converted_audio/<filename>')
def download_converted_audio(filename):
    """Download converted audio file"""
    try:
        # Decode URL-encoded filename
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        
        file_path = os.path.abspath(os.path.join(AUDIO_FOLDER, decoded_filename))
        print(f"DEBUG: Looking for audio file: {file_path}")
        
        if not os.path.exists(file_path):
            print(f"DEBUG: Audio file not found: {file_path}")
            return "Converted audio file not found", 404
        
        print(f"DEBUG: Audio file found, sending: {file_path}")
        return send_file(file_path, as_attachment=True, download_name=decoded_filename)
        
    except Exception as e:
        print(f"ERROR in download_converted_audio: {str(e)}")
        return f"Error downloading converted audio: {str(e)}", 500


def cleanup_all_processes():
    """Clean up all running processes on shutdown"""
    print("DEBUG: Cleaning up all running processes...")
    for filename, process_info in running_processes.items():
        try:
            process = process_info['process']
            if process.poll() is None:  # Process is still running
                print(f"DEBUG: Terminating process for {filename} (PID: {process.pid})")
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
        except Exception as e:
            print(f"DEBUG: Error cleaning up process for {filename}: {e}")
    running_processes.clear()

def cleanup_abandoned_processes():
    """Clean up processes that have been running for too long (1 hour)"""
    current_time = time.time()
    abandoned = []
    for filename, process_info in running_processes.items():
        if current_time - process_info['start_time'] > 3600:  # 1 hour
            abandoned.append(filename)
    
    for filename in abandoned:
        try:
            process = running_processes[filename]['process']
            if process.poll() is None:
                print(f"DEBUG: Cleaning up abandoned process for {filename}")
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
            del running_processes[filename]
        except Exception as e:
            print(f"DEBUG: Error cleaning up abandoned process for {filename}: {e}")

# Register API blueprints (only if they were imported successfully)
if auth_bp:
    app.register_blueprint(auth_bp)
    print("[OK] auth_bp registered")
if api_v1:
    app.register_blueprint(api_v1)
    print("[OK] api_v1 registered")
if admin_api:
    app.register_blueprint(admin_api)
    print("[OK] admin_api registered")
if client_api:
    app.register_blueprint(client_api)
    print("[OK] client_api registered")
if payment_api:
    app.register_blueprint(payment_api)
    print("[OK] payment_api registered")
if analytics_api:
    app.register_blueprint(analytics_api)
    print("[OK] analytics_api registered")
if campaigns_api:
    app.register_blueprint(campaigns_api)
    print("[OK] campaigns_api registered")
if rules_api:
    app.register_blueprint(rules_api)
    print("[OK] rules_api registered")

if enterprise_api:
    app.register_blueprint(enterprise_api)
    print("[OK] enterprise_api registered")

# Register WebSocket routes for live monitoring
try:
    from api.campaigns.websocket import register_websocket_routes
    register_websocket_routes(sock)
    print("[OK] WebSocket routes registered for live monitoring")
except Exception as e:
    print(f"[WARN] Failed to register WebSocket routes: {e}")

# Initialize WebSocket Manager for live campaign monitoring
try:
    from websocket_manager import ws_manager
    ws_manager.init_app(app)
    print("[OK] WebSocket manager initialized for live monitoring")
except Exception as e:
    print(f"[WARN] WebSocket manager initialization failed: {e}")
if test_bp:
    app.register_blueprint(test_bp)
    print("[OK] test_bp registered")
if debug_bp:
    app.register_blueprint(debug_bp)
    print("[OK] debug_bp registered")

# Register cleanup on shutdown
import atexit
atexit.register(cleanup_all_processes)

if __name__ == "__main__":
    print("[START] Starting Flask application...")
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if db_uri.startswith("sqlite"):
        print(f"[INFO] Database: SQLite")
    else:
        masked = db_uri.split("@")[-1] if "@" in db_uri else db_uri[:50]
        print(f"[INFO] Database: PostgreSQL ...@{masked}")
    print(f"[KEY] Secrets derived from SUPABASE_SERVICE_ROLE_KEY: {bool(os.getenv('SUPABASE_SERVICE_ROLE_KEY'))}")
    
    # Database is already initialized above
    
    print(f"[OK] All dependencies loaded successfully")

    # Initialize automated services
    try:
        from backup_service import schedule_daily_backups
        print("[BACKUP] Starting daily backup scheduler...")
        schedule_daily_backups()
    except Exception as e:
        print(f"[WARN] Failed to start backup service: {e}")

    # Register additional admin blueprints
    if backup_admin_api:
        app.register_blueprint(backup_admin_api)
        print("[OK] Backup admin routes registered")
    if ad_service_admin_api:
        app.register_blueprint(ad_service_admin_api)
        print("[OK] Ad service admin routes registered")

    # Get port from environment variable (Railway provides this)
    port = int(os.getenv('PORT', 5000))
    print(f" Starting server on port {port}")

    app.run(debug=False, host='0.0.0.0', port=port)
