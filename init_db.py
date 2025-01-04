from app import app, db, DB_PATH
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
        
        # Verify database was created
        if os.path.exists(DB_PATH):
            print("Database file exists at:", DB_PATH)
            print("Database file permissions:", oct(os.stat(DB_PATH).st_mode))
        else:
            print("Warning: Database file was not created at:", DB_PATH)
            
    except Exception as e:
        print("Error initializing database:", str(e))
        raise
