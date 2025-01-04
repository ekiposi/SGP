from app import app, db, DB_PATH
from models import User
import os

# Ensure instance directory exists with proper permissions
instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path, mode=0o777)

print("Database path:", DB_PATH)
print("Database directory exists:", os.path.exists(os.path.dirname(DB_PATH)))
print("Database directory permissions:", oct(os.stat(os.path.dirname(DB_PATH)).st_mode))

# Initialize database
with app.app_context():
    try:
        db.create_all()
        print("Database initialized successfully!")
        
        # Create default admin user if it doesn't exist
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', is_admin=True)
            admin.set_password('admin123')  # Set a default password
            db.session.add(admin)
            db.session.commit()
            print("Default admin user created")
        
        # Verify database was created
        if os.path.exists(DB_PATH):
            print("Database file exists at:", DB_PATH)
            print("Database file permissions:", oct(os.stat(DB_PATH).st_mode))
        else:
            print("Warning: Database file was not created at:", DB_PATH)
            
    except Exception as e:
        print("Error initializing database:", str(e))
        raise
