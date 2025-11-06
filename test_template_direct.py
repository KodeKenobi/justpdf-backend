#!/usr/bin/env python
"""Direct test of template rendering with actual Flask app context"""
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the Flask app
from app import app

# Create test context
with app.test_request_context('/convert/test.pdf?mobile=true'):
    # Test template rendering
    from flask import render_template
    
    # Sample pages data
    pages_data = [
        {
            'html': '<div class="pdf-page" data-page="1">Test Page</div>',
            'width': 595,
            'height': 842
        }
    ]
    
    try:
        print("🧪 Testing template rendering with Flask app context...")
        print(f"📁 Template folder: {app.template_folder}")
        print(f"📁 Template folder exists: {os.path.exists(app.template_folder)}")
        
        template_name = "converted-mobile-simple.html"
        template_path = os.path.join(app.template_folder, template_name)
        print(f"📄 Template path: {template_path}")
        print(f"📄 Template exists: {os.path.exists(template_path)}")
        
        # Clear cache
        if hasattr(app, 'jinja_env'):
            app.jinja_env.cache.clear()
            print("✅ Cleared Jinja2 cache")
        
        # Try to render
        print(f"🔄 Rendering template: {template_name}")
        result = render_template(template_name, 
                                filename="test.pdf",
                                pages=pages_data)
        
        print(f"✅ Template rendered successfully!")
        print(f"📏 Rendered size: {len(result)} bytes")
        print(f"📝 First 300 chars:\n{result[:300]}...")
        
    except Exception as e:
        print(f"❌ Template rendering failed!")
        print(f"Error: {str(e)}")
        import traceback
        print(f"Traceback:\n{traceback.format_exc()}")

print("\n✅ Test complete!")

