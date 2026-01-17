#!/usr/bin/env python
"""Test script to check mobile template rendering"""
import os
import sys
from flask import Flask
from jinja2 import Environment, FileSystemLoader

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Initialize Flask app
app = Flask(__name__)

# Check template folder
template_folder = app.template_folder
print(f" Template folder: {template_folder}")
print(f" Template folder exists: {os.path.exists(template_folder)}")

# Check if mobile template exists
mobile_template_path = os.path.join(template_folder, "converted-mobile-simple.html")
print(f" Mobile template path: {mobile_template_path}")
print(f" Mobile template exists: {os.path.exists(mobile_template_path)}")

if os.path.exists(mobile_template_path):
    print(f"[OK] Mobile template file found!")
    # Read and check template content
    with open(mobile_template_path, 'r', encoding='utf-8') as f:
        content = f.read()
        print(f" Template size: {len(content)} bytes")
        print(f" Template preview (first 200 chars):\n{content[:200]}...")
        
        # Check for common issues
        if '{% for page in pages %}' in content:
            print("[OK] Found Jinja2 loop syntax")
        else:
            print("[ERROR] Jinja2 loop syntax not found!")
        
        if '{{ page.html | safe }}' in content:
            print("[OK] Found page.html variable")
        else:
            print("[ERROR] page.html variable not found!")
        
        if '{{ filename }}' in content:
            print("[OK] Found filename variable")
        else:
            print("[ERROR] filename variable not found!")
else:
    print(f"[ERROR] Mobile template file NOT found!")

# Try to render template with sample data
print("\n Testing template rendering...")
try:
    env = Environment(loader=FileSystemLoader(template_folder))
    template = env.get_template("converted-mobile-simple.html")
    
    # Sample data
    test_data = {
        'filename': 'test.pdf',
        'pages': [
            {
                'html': '<div class="pdf-page" data-page="1"><div class="text-line"><span class="text-span">Test Page 1</span></div></div>',
                'width': 595,
                'height': 842
            }
        ]
    }
    
    rendered = template.render(**test_data)
    print(f"[OK] Template rendered successfully!")
    print(f" Rendered size: {len(rendered)} bytes")
    print(f" Rendered preview (first 300 chars):\n{rendered[:300]}...")
    
except Exception as e:
    print(f"[ERROR] Template rendering failed!")
    print(f"Error: {str(e)}")
    import traceback
    print(f"Traceback:\n{traceback.format_exc()}")

print("\n[OK] Test complete!")

