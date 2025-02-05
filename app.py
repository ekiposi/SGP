from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from models import db, User, Employee, Attendance
import qrcode
from sqlalchemy import func, or_
import json
import base64
from io import BytesIO
from PIL import Image
# Make face recognition optional
try:
    import face_recognition
    FACE_RECOGNITION_ENABLED = True
except ImportError:
    FACE_RECOGNITION_ENABLED = False
    print("Face recognition is not available")
import shutil
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.config['SECRET_KEY'] = '0667akk7'  # Change this to a secure secret key

# Set up database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'attendance.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder)

# Ensure instance directory exists with proper permissions
instance_path = os.path.dirname(DB_PATH)
os.makedirs(instance_path, mode=0o777, exist_ok=True)

# Touch the database file to ensure it exists with proper permissions
if not os.path.exists(DB_PATH):
    with open(DB_PATH, 'a') as f:
        pass
    os.chmod(DB_PATH, 0o666)

# Initialize Flask extensions
db.init_app(app)

# Create backup directory if it doesn't exist
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backup')
os.makedirs(BACKUP_DIR, mode=0o777, exist_ok=True)

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Initialize database
with app.app_context():
    db.create_all()

def create_backup_file():
    """Create a backup of the database"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f'database_backup_{timestamp}.db'
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    # Create backup by copying the database file
    try:
        shutil.copy2(DB_PATH, backup_path)
        cleanup_old_backups()
        return backup_path
    except Exception as e:
        print(f"Backup failed: {str(e)}")
        return None

def cleanup_old_backups():
    """Remove backups older than retention period"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = "retention_period"')
            result = cursor.fetchone()
            retention_days = int(result[0]) if result else 30
    except:
        retention_days = 30

    cutoff_date = datetime.now() - timedelta(days=retention_days)
    
    for filename in os.listdir(BACKUP_DIR):
        if filename.startswith('database_backup_'):
            file_path = os.path.join(BACKUP_DIR, filename)
            # Parse the timestamp from filename (YYYYMMDD_HHMMSS)
            timestamp_str = filename.replace('database_backup_', '').replace('.db', '')
            file_date = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
            if file_date < cutoff_date:
                os.remove(file_path)

def schedule_backup(frequency='daily'):
    """Schedule automatic backups"""
    # Remove existing backup jobs
    for job in scheduler.get_jobs():
        if job.id == 'backup_job':
            scheduler.remove_job('backup_job')
    
    # Schedule new backup job
    if frequency == 'daily':
        scheduler.add_job(create_backup_file, 'interval', days=1, id='backup_job')
    elif frequency == 'weekly':
        scheduler.add_job(create_backup_file, 'interval', weeks=1, id='backup_job')
    elif frequency == 'monthly':
        scheduler.add_job(create_backup_file, 'interval', days=30, id='backup_job')

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin'))
        return redirect(url_for('profile'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Connection réussie.', 'success')
            return redirect(url_for('index'))
            
        flash('Identifiant ou mot de passe invalide.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        return redirect(url_for('profile'))
    return render_template('admin.html')

@app.route('/update-admin-credentials', methods=['POST'])
def update_admin_credentials():
    if current_user.is_admin:
        try:
            data = request.get_json()
            new_username = data.get('username')
            new_password = data.get('password')

            if not new_username or not new_password:
                return jsonify({'status': 'error', 'message': 'Le nom d\'utilisateur et le mot de passe sont requis.'})
            
            admin_data = User.query.filter_by(username=current_user.username).first()
            if admin_data:
                admin_data.username = new_username
                admin_data.set_password(new_password)
                db.session.commit()
                return jsonify({'status': 'success', 'message': 'Les informations de l\'administrateur ont été mis à jour avec succès'})
            else:
                return jsonify({'status': 'error', 'message': 'Aucun utilisateur trouvé.'})

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})

@app.route('/general', methods=['GET', 'POST'])
@login_required
def general():
    if not current_user.is_admin:
        return redirect(url_for('profile'))
    
    if request.method == 'POST':
        with open('config.json') as config_file:
            config_data = json.load(config_file)
        if request.get_json().get('face-recg', False):
            config_data['face-recg'] = True
        else:
            config_data['face-recg'] = False

        # print(request.get_json())
        with open('config.json', 'w') as config_file:
            json.dump(config_data, config_file, indent=4)
        
        return jsonify({"success":True, "face-recg":config_data['face-recg']}), 200

    with open('config.json') as config_file:
        config_data = json.load(config_file)
    face_recg_enabled = config_data.get('face-recg', False)
    print("Face Recognition:", face_recg_enabled)
    attendance_data = []

    attendances = Attendance.query.all()
    
    for attendance in attendances:
        employee = attendance.employee
        if attendance.check_out:
            total_hours = (attendance.check_out - attendance.check_in).total_seconds() / 3600
            total_hours_str = f"{int(total_hours)}:{int((total_hours % 1) * 60):02d}"
        else:
            total_hours_str = None
        
        attendance_data.append({
            "employee": employee.full_name,
            "photo": employee.photo,
            "id": employee.pluri_id,
            "department": employee.department,
            "check_in": attendance.check_in.strftime('%I:%M %p'),
            "face_validation": True,  # Default to True since it's not in the table
            "check_out": attendance.check_out.strftime('%I:%M %p') if attendance.check_out else None,
            "total_hours": total_hours_str,
            "status": "Terminé" if attendance.check_out else "En cours",
        })
    return render_template('general.html', face_recg_enabled=face_recg_enabled, attendance_data=attendance_data)


@app.route('/employees', methods=['GET', 'POST'])
@login_required
def employees():
    if not current_user.is_admin:
        return redirect(url_for('profile'))
        
    if request.method == 'POST':
        # Debug print
        print("Form data:", request.form)
        
        # Generate unique employee ID
        pluri_id = Employee.generate_pluri_id()
        
        # Split full name into first and last name
        full_name = request.form.get('full_name', '').strip()
        names = full_name.split(' ', 1)
        first_name = names[0]
        last_name = names[1] if len(names) > 1 else ''
        
        # Get role from form
        role = request.form.get('role')
        print("Selected role:", role)  # Debug print

        profile = request.files.get('profile_picture')
        if profile and profile.filename:
            filename = secure_filename(profile.filename)
            extension = os.path.splitext(filename)[1]
            new_filename = f"{pluri_id}{extension}"
            upload_folder = os.path.join(app.config['UPLOAD_FOLDER'],'uploads', 'profiles')
            os.makedirs(upload_folder, exist_ok=True)
            profile.save(os.path.join(upload_folder, new_filename))
            photo_path = f"uploads/profiles/{new_filename}"
        else:
            photo_path = None
        
        # Create new employee
        employee = Employee(
            pluri_id=pluri_id,
            first_name=first_name,
            photo = photo_path,
            last_name=last_name,
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            gender=request.form.get('gender'),
            department=request.form.get('department'),
            position=role,  # Save the role in the position field
            hire_date=datetime.strptime(request.form.get('hire_date'), '%Y-%m-%d').date(),
            dob=datetime.strptime(request.form.get('dob'), '%Y-%m-%d').date()
        )
        
        # Generate QR code
        employee.generate_qr_code()
        
        # Create user account for employee
        user = User(
            username=f"user_{pluri_id}",
            is_admin=False
        )
        user.set_password(pluri_id)  # Initial password is their employee ID
        
        # Link user and employee
        employee.user = user
        
        db.session.add(employee)
        db.session.add(user)
        db.session.commit()
        
        print("Saved employee position:", employee.position)  # Debug print
        
        flash(f'L\'employé {employee.full_name} a été ajouté avec succès.', 'success')
        return redirect(url_for('employees'))
    
    # GET request - show all employees
    employees_list = Employee.query.all()
    for emp in employees_list:  # Debug print
        print(f"Employee: {emp.full_name}, Position: {emp.position}")
    return render_template('employees.html', employees=employees_list)

@app.route('/employee/<int:employee_id>/update', methods=['GET', 'POST'])
def update_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    
    if request.method == 'POST':
        # Update fields from the form
        employee.first_name = request.form.get('first_name')
        employee.last_name = request.form.get('last_name')
        employee.email = request.form.get('email')
        employee.phone = request.form.get('phone')
        employee.gender = request.form.get('gender')
        employee.department = request.form.get('department')
        employee.position = request.form.get('role')
        employee.hire_date = datetime.strptime(request.form.get('hire_date'), '%Y-%m-%d').date()
        employee.dob = datetime.strptime(request.form.get('dob'), '%Y-%m-%d').date()

        # Handle photo upload
        if 'photo' in request.files:
            photo = request.files['photo']
            if photo.filename != '':
                filename = secure_filename(photo.filename)
                extension = os.path.splitext(filename)[1]
                new_filename = f"{employee.pluri_id}{extension}"
                upload_folder = os.path.join(app.config['UPLOAD_FOLDER'],'uploads', 'profiles')
                os.makedirs(upload_folder, exist_ok=True)
                photo.save(os.path.join(upload_folder, new_filename))
                photo_path = f"uploads/profiles/{new_filename}"

        db.session.commit()
        flash('Employee details updated successfully!', 'success')
        return redirect(url_for('employees'))

    return render_template('update.html', employee=employee)

@app.route('/employee/<int:employee_id>/delete', methods=['GET'])
def delete_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)

    try:
        # First delete all attendance records for this employee
        Attendance.query.filter_by(employee_id=employee_id).delete()

        # Then delete employee's files
        if employee.photo:
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], employee.photo)
            if os.path.exists(photo_path):
                os.remove(photo_path)
        qr_path = os.path.join('static', 'uploads', 'qrcodes', f'qr_{employee.pluri_id}')
        if os.path.exists(qr_path):
            os.remove(qr_path)

        # Finally delete the employee
        db.session.delete(employee)
        db.session.commit()
        flash('Employé et tous les enregistrements associés supprimés avec succès!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Une erreur est survenue lors de la suppression: {str(e)}', 'danger')

    return redirect(url_for('employees'))

def handle_attendance(employee):
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Check for existing attendance today
    attendance = Attendance.query.filter(
        Attendance.employee_id == employee.id,
        Attendance.check_in >= today_start,
        Attendance.check_in <= today_end
    ).first()
    
    if attendance:
        if not attendance.check_out:
            # Check out
            attendance.check_out = now
            attendance.total_hours = (attendance.check_out - attendance.check_in).total_seconds() / 3600
            db.session.commit()
            return {
                'status': 'success',
                'message': f'Check-out effectué avec succès à {now.strftime("%I:%M %p")}',
                'type': 'check_out'
            }
        else:
            return {
                'status': 'error',
                'message': 'Vous avez déjà effectué votre check-out aujourd’hui. Merci de revenir demain.',
                'type': 'check_out'
            }
    else:
        # Check in
        attendance = Attendance(
            employee_id=employee.id,
            check_in=now
        )
        db.session.add(attendance)
        db.session.commit()
        return {
            'status': 'success',
            'message': f'Check-in effectué avec succès à  {now.strftime("%I:%M %p")}',
            'type': 'check_in'
        }

@app.route('/scan', methods=['GET', 'POST'])
@login_required
def scan():
    if not current_user.is_admin:
        return redirect(url_for('profile'))
        
    if request.method == 'POST':
        try:
            with open('config.json') as config_file:
                config_data = json.load(config_file)
            
            data = request.json
            qr_data = data.get('qr_data')
            
            # Find employee by QR data
            employee = Employee.query.filter_by(qr_data=qr_data).first()
            if not employee:
                return jsonify({'status': 'error', 'message': 'Code QR Invalide'}), 400
            
            if not config_data['face-recg']:
                attendance_response = handle_attendance(employee)
                
                return jsonify({
                    **attendance_response,
                    'faceEnabled': config_data['face-recg'],
                    'empId': employee.pluri_id
                }), 200
            else:
                return jsonify({
                    'status':'success',
                    'faceEnabled': config_data['face-recg'],
                    'empId': employee.pluri_id
                }), 200
                
        except Exception as e:
            print(f"Error in scan: {str(e)}")
            return jsonify({'status': 'error', 'message': 'Erreur du serveur.'}), 500
            
    return render_template('thing.html')


@app.route('/facial-recognition', methods=['POST'])
def facial_recognition():
    if not FACE_RECOGNITION_ENABLED:
        flash('La reconnaissance faciale n\'est pas disponible.', 'error')
        return redirect(url_for('scan'))

    if 'file' not in request.files:
        flash('Aucune image n\'a été téléchargée.', 'error')
        return redirect(url_for('scan'))
    
    data = request.json
    image_data = data.get('image_data')
    emp_id = data.get('emp_id')

    if not image_data or not emp_id:
        return jsonify({'status': 'error', 'message': 'Les données fournies sont invalides.'}), 400

    image = Image.open(BytesIO(base64.b64decode(image_data.split(',')[1])))
    image.save(f'static/uploads/face_snapshots/{emp_id}_face.jpg')
    profile_pic = None
    for i in os.listdir("static/uploads/profiles/"):
        if emp_id in i:
            profile_pic = i
            break
    if not profile_pic:
        return jsonify({'status': 'error', 'message': 'Veuillez fournir une image de profil valide.'}), 404
    
    known_image = face_recognition.load_image_file("static/uploads/profiles/" + profile_pic)
    unknown_image = face_recognition.load_image_file(f'static/uploads/face_snapshots/{emp_id}_face.jpg')
    biden_encoding = face_recognition.face_encodings(known_image)[0]
    unknown_encoding = face_recognition.face_encodings(unknown_image)[0]
    if len(biden_encoding) == 0 or len(unknown_encoding) == 0:
        return jsonify({'status': 'error', 'message': 'Aucune face détectée dans une des images'}), 404
    results = face_recognition.compare_faces([biden_encoding], unknown_encoding, tolerance=0.4)
    if os.path.exists(f'static/uploads/face_snapshots/{emp_id}_face.jpg'):
        os.remove(f'static/uploads/face_snapshots/{emp_id}_face.jpg')
    if results[0]:
        employee = Employee.query.filter_by(pluri_id=emp_id).first()
        if not employee:
                return jsonify({'status': 'error', 'message': 'Code Qr Invalide'}), 400
        attendance_response = handle_attendance(employee)
        
        return jsonify({
            **attendance_response,
        })
    else:
        return jsonify({'status': 'error', 'message': 'Les visages ne correspondent pas. Veuillez assurer la visibilité du visage'}), 400


@app.route('/today_attendance')
@login_required
def today_attendance():
    today = datetime.now()
    today_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Get all attendance records for today
    attendance_records = Attendance.query.filter(
        Attendance.check_in >= today_start,
        Attendance.check_in <= today_end
    ).order_by(Attendance.check_in.desc()).all()
    
    # Format the records for JSON response
    records = []
    for attendance in attendance_records:
        # Calculate total hours if check_out exists
        total_hours = None
        if attendance.check_out:
            duration = attendance.check_out - attendance.check_in
            total_hours = duration.total_seconds() / 3600  # Convert to hours
        
        record = {
            'pluri_id': attendance.employee.pluri_id,
            'department': attendance.employee.department,
            'position': attendance.employee.position,
            'employee_name': attendance.employee.full_name,
            'check_in': attendance.check_in.strftime('%I:%M %p'),
            'check_out': attendance.check_out.strftime('%I:%M %p') if attendance.check_out else None,
            'total_hours': round(total_hours, 2) if total_hours is not None else None
        }
        records.append(record)
    
    return jsonify(records)

@app.route('/report')
@login_required
def report():
    if not current_user.is_admin:
        return redirect(url_for('profile'))
    return render_template('report.html')

@app.route('/credits')
@login_required
def credits():
    if not current_user.is_admin:
        return redirect(url_for('profile'))
    return render_template('credits.html')

@app.route('/backup')
@login_required
def backup():
    if not current_user.is_admin:
        return redirect(url_for('profile'))
    
    # Get list of backups
    backups = []
    for filename in os.listdir(BACKUP_DIR):
        if filename.startswith('database_backup_'):
            file_path = os.path.join(BACKUP_DIR, filename)
            file_stats = os.stat(file_path)
            # Parse the timestamp from filename (YYYYMMDD_HHMMSS)
            timestamp_str = filename.replace('database_backup_', '').replace('.db', '')
            file_date = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
            backups.append({
                'id': filename,
                'date': file_date,
                'size': f"{file_stats.st_size / (1024*1024):.2f} MB"
            })
    
    # Sort backups by date, newest first
    backups.sort(key=lambda x: x['date'], reverse=True)
    
    # Get backup settings
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = "backup_frequency"')
            frequency = cursor.fetchone()
            cursor.execute('SELECT value FROM settings WHERE key = "retention_period"')
            retention = cursor.fetchone()
            
            settings = {
                'frequency': frequency[0] if frequency else 'daily',
                'retention_period': retention[0] if retention else 30
            }
    except:
        settings = {'frequency': 'daily', 'retention_period': 30}
    
    return render_template('backup.html', backups=backups, settings=settings)

@app.route('/backup/create', methods=['POST'])
@login_required
def create_backup():
    if not current_user.is_admin:
        return redirect(url_for('profile'))
    
    backup_path = create_backup_file()
    if backup_path:
        flash('Sauvegarde créée avec succès', 'success')
    else:
        flash('Erreur lors de la création de la sauvegarde', 'error')
    
    return redirect(url_for('backup'))

@app.route('/backup/settings', methods=['POST'])
@login_required
def update_backup_settings():
    if not current_user.is_admin:
        return redirect(url_for('profile'))
    
    frequency = request.form.get('backup_frequency', 'daily')
    retention_period = request.form.get('retention_period', '30')
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                         ('backup_frequency', frequency))
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                         ('retention_period', retention_period))
            conn.commit()
            
        # Update backup schedule
        schedule_backup(frequency)
        cleanup_old_backups()
        
        flash('Paramètres de sauvegarde mis à jour', 'success')
    except Exception as e:
        flash(f'Erreur lors de la mise à jour des paramètres: {str(e)}', 'error')
    
    return redirect(url_for('backup'))

@app.route('/backup/delete/<backup_id>', methods=['POST'])
@login_required
def delete_backup(backup_id):
    if not current_user.is_admin:
        return redirect(url_for('profile'))
    
    try:
        backup_path = os.path.join(BACKUP_DIR, backup_id)
        if os.path.exists(backup_path):
            os.remove(backup_path)
            flash('Sauvegarde supprimée', 'success')
        else:
            flash('Sauvegarde non trouvée', 'error')
    except Exception as e:
        flash(f'Erreur lors de la suppression: {str(e)}', 'error')
    
    return redirect(url_for('backup'))

@app.route('/api/report_data')
@login_required
def report_data():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    # Get filter parameters
    employee_name = request.args.get('employee_name', '')
    pluri_id = request.args.get('pluri_id', '')
    department = request.args.get('department', '')
    function = request.args.get('function', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    # Start with base query
    query = db.session.query(
        Employee.pluri_id,
        Employee.first_name,
        Employee.last_name,
        Employee.department,
        Employee.position,
        func.sum(
            func.coalesce(
                (func.julianday(Attendance.check_out) - func.julianday(Attendance.check_in)) * 24 * 60 * 60,
                0
            )
        ).label('total_seconds')
    ).join(Attendance, Employee.id == Attendance.employee_id).group_by(
        Employee.pluri_id,
        Employee.first_name,
        Employee.last_name,
        Employee.department,
        Employee.position
    )

    # Apply filters
    if employee_name:
        query = query.filter(
            db.or_(
                Employee.first_name.ilike(f'%{employee_name}%'),
                Employee.last_name.ilike(f'%{employee_name}%')
            )
        )
    if pluri_id:
        query = query.filter(Employee.pluri_id == pluri_id)
    if department:
        query = query.filter(Employee.department == department)
    if function:
        query = query.filter(Employee.position == function)
    if date_from:
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        query = query.filter(Attendance.check_in >= date_from)
    if date_to:
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        query = query.filter(Attendance.check_in <= date_to)

    # Execute query and format results
    records = []
    for record in query.all():
        total_hours = round(record.total_seconds / 3600, 2)  # Convert seconds to hours
        records.append({
            'pluri_id': record.pluri_id,
            'full_name': f'{record.first_name} {record.last_name}',
            'department': record.department,
            'function': record.position,
            'total_hours': total_hours
        })

    return jsonify({'data': records})


@app.route('/profile')
@login_required
def profile():
    today = datetime.now()
    today_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Get today's attendance
    today_attendance = Attendance.query.filter(
        Attendance.employee_id == current_user.employee.id,
        Attendance.check_in >= today_start,
        Attendance.check_in <= today_end
    ).first()
    
    # Get past attendance records (excluding today)
    past_attendance = Attendance.query.filter(
        Attendance.employee_id == current_user.employee.id,
        Attendance.check_in < today_start
    ).order_by(Attendance.check_in.desc()).all()
    
    return render_template('profile.html', 
                         today=today,
                         today_attendance=today_attendance,
                         past_attendance=past_attendance)

@app.route('/filter_attendance', methods=['GET'])
def filter_attendance():
    filter_type = request.args.get('filter')
    employee_id = 1

    today = datetime.utcnow()
    start_date = None

    if filter_type == 'week':
        start_date = today - timedelta(days=7)
    elif filter_type == 'month':
        start_date = today - timedelta(days=30)

    query = Attendance.query.filter(Attendance.employee_id == employee_id)
    if start_date:
        query = query.filter(Attendance.check_in >= start_date)

    records = query.order_by(Attendance.check_in.desc()).all()

    attendance_data = []
    for record in records:
        attendance_data.append({
            'date': record.check_in.strftime('%Y-%m-%d'),
            'check_in': record.check_in.strftime('%I:%M %p'),
            'check_out': record.check_out.strftime('%I:%M %p') if record.check_out else '-',
            'total_hours': f"{record.total_hours:.2f}" if record.total_hours else '-',
        })

    return jsonify(attendance_data)


@app.route('/dashboard')
@login_required
def dashboard():
    with open('config.json') as config_file:
        config_data = json.load(config_file)

    # Convert inTime and outTime from config to time objects
    in_time = datetime.strptime(config_data['inTime'], "%H:%M:%S").time()
    out_time = datetime.strptime(config_data['outTime'], "%H:%M:%S").time()

    total_employees = Employee.query.count()

    present_employees = Attendance.query.filter(
        Attendance.check_in >= datetime.now().replace(hour=0, minute=0, second=0)
    ).count()

    if config_data['lateComers']:
        latecomers = Attendance.query.filter(
            Attendance.check_in >= datetime.now().replace(hour=0, minute=0, second=0),
            func.time(Attendance.check_in) > in_time
        ).count()
    else:
        latecomers = 0

    # Logic for employees on leave
    employees_on_leave = Employee.query.filter(
        ~Employee.id.in_(
            db.session.query(Attendance.employee_id).filter(
                or_(
                    func.time(Attendance.check_in).between(in_time, out_time),
                    func.time(Attendance.check_out).between(in_time, out_time)
                ),
                Attendance.check_in >= datetime.now().replace(hour=0, minute=0, second=0)
            )
        )
    ).count()

    male_employees = Employee.query.filter_by(gender='male').count()
    female_employees = Employee.query.filter_by(gender='female').count()

    # Weekly activity data
    activity_labels = []
    activity_data = []
    for i in range(7):
        day = datetime.now().date() - timedelta(days=i)
        activity_labels.append(day.strftime('%A'))
        activity_data.append(
            Attendance.query.filter(
                Attendance.check_in >= day,
                Attendance.check_in < day + timedelta(days=1)
            ).count()
        )
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0)
    today_attendance = Attendance.query.filter(Attendance.check_in >= today_start).all()

    return render_template(
        'dashboard.html',
        total_employees=total_employees,
        present_employees=present_employees,
        latecomers=latecomers,
        employees_on_leave=employees_on_leave,
        male_employees=male_employees,
        female_employees=female_employees,
        activity_labels=activity_labels[::-1],
        activity_data=activity_data[::-1],
        today_attendance=today_attendance
    )

@app.route('/activity-data', methods=['GET'])
def activity_data():
    # Get the period parameter (day, week, month, year)
    period = request.args.get('period', 'week').lower()
    
    activity_labels = []
    activity_data = []
    
    if period == 'day':
        # Group data by hour for the current day
        current_date = datetime.now().date()
        for hour in range(24):
            start_time = datetime.combine(current_date, datetime.min.time()) + timedelta(hours=hour)
            end_time = start_time + timedelta(hours=1)
            activity_labels.append(f"{hour}:00")
            activity_data.append(
                Attendance.query.filter(
                    Attendance.check_in >= start_time,
                    Attendance.check_in < end_time
                ).count()
            )
    elif period == 'week':
        # Group data by last 7 days
        for i in range(7):
            day = datetime.now().date() - timedelta(days=i)
            activity_labels.insert(0, day.strftime('%A'))  # Add to the start for correct order
            activity_data.insert(0, 
                Attendance.query.filter(
                    Attendance.check_in >= day,
                    Attendance.check_in < day + timedelta(days=1)
                ).count()
            )
    elif period == 'month':
        # Group data by days in the current month
        current_date = datetime.now()
        start_of_month = datetime(current_date.year, current_date.month, 1)
        num_days = (datetime(current_date.year, current_date.month + 1, 1) - start_of_month).days
        for day in range(num_days):
            start_time = start_of_month + timedelta(days=day)
            end_time = start_time + timedelta(days=1)
            activity_labels.append(start_time.strftime('%d %b'))
            activity_data.append(
                Attendance.query.filter(
                    Attendance.check_in >= start_time,
                    Attendance.check_in < end_time
                ).count()
            )
    elif period == 'year':
        # Group data by months in the current year
        current_year = datetime.now().year
        for month in range(1, 13):
            start_time = datetime(current_year, month, 1)
            if month == 12:
                end_time = datetime(current_year + 1, 1, 1)
            else:
                end_time = datetime(current_year, month + 1, 1)
            activity_labels.append(start_time.strftime('%b'))
            activity_data.append(
                Attendance.query.filter(
                    Attendance.check_in >= start_time,
                    Attendance.check_in < end_time
                ).count()
            )
    
    return jsonify({
        "labels": activity_labels,
        "data": activity_data
    })


@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not current_user.check_password(current_password):
        flash('Current password is incorrect.', 'error')
        return redirect(url_for('profile'))
        
    if new_password != confirm_password:
        flash('New passwords do not match.', 'error')
        return redirect(url_for('profile'))
        
    current_user.set_password(new_password)
    db.session.commit()
    flash('Password changed successfully.', 'success')
    return redirect(url_for('profile'))

if __name__ == '__main__':
    app.run(debug=True, port=os.getenv("PORT", default=5000))
else:
    # This is the entry point Gunicorn will use
    application = app
