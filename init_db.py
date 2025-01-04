from app import app, db
import os

# Ensure instance directory exists with proper permissions
instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path, mode=0o777)

# Initialize database
with app.app_context():
    try:
        db.create_all()
        print("Database initialized successfully in:", app.config['SQLALCHEMY_DATABASE_URI'])
    except Exception as e:
        print("Error initializing database:", str(e))
        # Try to create with different permissions
        db_path = os.path.join(instance_path, 'attendance.db')
        if not os.path.exists(db_path):
            open(db_path, 'a').close()
            os.chmod(db_path, 0o666)
        db.create_all()
        print("Database initialized after permission fix in:", app.config['SQLALCHEMY_DATABASE_URI'])
