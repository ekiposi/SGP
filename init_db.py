from app import app, db
import os

# Ensure instance directory exists
instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)

with app.app_context():
    db.create_all()
    print("Database initialized successfully in:", app.config['SQLALCHEMY_DATABASE_URI'])
