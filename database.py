from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os

db = SQLAlchemy()
migrate = Migrate()

def init_db(app):
    """Initialize database with the Flask app"""
    # Database configuration
    database_url = os.getenv('DATABASE_URL', 'sqlite:///justpdf_api.db')
    
    # Handle PostgreSQL URL format for SQLAlchemy
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    
    return db

def create_tables():
    """Create all database tables"""
    with db.app.app_context():
        db.create_all()
