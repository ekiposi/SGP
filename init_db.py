from app import app, db, DB_PATH
from models import User
import os
import sqlite3

def init_db():
    print("Database path:", DB_PATH)
    
    # Ensure instance directory exists with proper permissions
    instance_path = os.path.dirname(DB_PATH)
    if not os.path.exists(instance_path):
        os.makedirs(instance_path, mode=0o777)
        print("Created instance directory with permissions 777")
    
    # Remove existing database if it exists
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("Removed existing database")
    
    # Initialize database
    with app.app_context():
        try:
            db.create_all()
            print("Database tables created successfully!")
            
            # Create default admin user
            admin = User(username='admin', is_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created successfully!")
            
            # Verify database permissions
            os.chmod(DB_PATH, 0o666)
            print(f"Database file permissions set to 666")
            print(f"Database exists: {os.path.exists(DB_PATH)}")
            print(f"Database permissions: {oct(os.stat(DB_PATH).st_mode)}")
            
        except Exception as e:
            print("Error during database initialization:", str(e))
            if os.path.exists(DB_PATH):
                print("Attempting to fix database permissions...")
                os.chmod(DB_PATH, 0o666)
            raise

if __name__ == '__main__':
    init_db()
