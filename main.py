from app import app

# This is what Gunicorn will import
application = app
app = application  # This ensures both 'app' and 'application' are available

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
