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
    
    # Create tables
    with app.app_context():
        try:
            db.create_all()
            print("✅ Database tables created successfully")
            
            # Create default admin user if none exists
            from models import User
            admin_user = User.query.filter_by(email='admin@justpdf.com').first()
            if not admin_user:
                admin_user = User(
                    email='admin@justpdf.com',
                    role='admin',
                    is_active=True
                )
                admin_user.set_password('admin123')  # Default password
                db.session.add(admin_user)
                db.session.commit()
                print("✅ Default admin user created (email: admin@justpdf.com, password: admin123)")
            else:
                print("✅ Admin user already exists")
                
        except Exception as e:
            print(f"❌ Error creating database tables: {e}")
            raise
    
    return db

def create_tables():
    """Create all database tables"""
    with db.app.app_context():
        db.create_all()
