from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import os
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['lms_database']
users_collection = db['users']
courses_collection = db['courses']

# Admin credentials (static)
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

UPLOAD_FOLDER = os.path.join('static', 'videos')
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def landing():
    return render_template('landing.html')

# Admin Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            session['user_type'] = 'admin'
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials')
    
    return render_template('admin/login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    courses = list(courses_collection.find())
    total_students = users_collection.count_documents({'role': 'student'})
    
    return render_template('admin/dashboard.html', 
                         courses=courses, 
                         total_students=total_students)

@app.route('/admin/create-course', methods=['GET', 'POST'])
def create_course():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        course_data = {
            'title': request.form['title'],
            'description': request.form['description'],
            'instructor': request.form['instructor'],
            'created_at': datetime.now(),
            'lessons': []
        }
        
        course_id = courses_collection.insert_one(course_data).inserted_id
        flash('Course created successfully!')
        return redirect(url_for('course_details', course_id=course_id))
    
    return render_template('admin/create_course.html')

@app.route('/admin/course/<course_id>')
def course_details(course_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    course = courses_collection.find_one({'_id': ObjectId(course_id)})
    if not course:
        flash('Course not found')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin/course_details.html', course=course)

@app.route('/admin/course/<course_id>/add-video', methods=['POST'])
def add_video(course_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    title = request.form['title']
    duration = request.form['duration']
    file = request.files.get('video_file')
    video_url = None
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        video_url = f'/static/videos/{filename}'
    else:
        flash('Invalid file type or no file uploaded!')
        return redirect(url_for('course_details', course_id=course_id))
    lesson_data = {
        'title': title,
        'video_url': video_url,
        'duration': duration,
        'added_at': datetime.now()
    }
    courses_collection.update_one(
        {'_id': ObjectId(course_id)},
        {'$push': {'lessons': lesson_data}}
    )
    flash('Video added successfully!')
    return redirect(url_for('course_details', course_id=course_id))

# Student Routes
@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Check if user already exists
        if users_collection.find_one({'$or': [{'username': username}, {'email': email}]}):
            flash('Username or email already exists')
            return render_template('student/register.html')
        
        # Create new user
        user_data = {
            'username': username,
            'email': email,
            'password': generate_password_hash(password),
            'role': 'student',
            'created_at': datetime.now(),
            'enrolled_courses': []
        }
        
        users_collection.insert_one(user_data)
        flash('Registration successful! Please login.')
        return redirect(url_for('student_login'))
    
    return render_template('student/register.html')

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = users_collection.find_one({'username': username})
        
        if user and check_password_hash(user['password'], password):
            session['student_id'] = str(user['_id'])
            session['username'] = user['username']
            session['user_type'] = 'student'
            return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid credentials')
    
    return render_template('student/login.html')

@app.route('/student/dashboard')
def student_dashboard():
    if not session.get('student_id'):
        return redirect(url_for('student_login'))
    
    courses = list(courses_collection.find())
    user = users_collection.find_one({'_id': ObjectId(session['student_id'])})
    enrolled_courses = user.get('enrolled_courses', [])
    
    return render_template('student/dashboard.html', 
                         courses=courses, 
                         enrolled_courses=enrolled_courses)

@app.route('/student/course/<course_id>')
def view_course(course_id):
    if not session.get('student_id'):
        return redirect(url_for('student_login'))
    
    course = courses_collection.find_one({'_id': ObjectId(course_id)})
    if not course:
        flash('Course not found')
        return redirect(url_for('student_dashboard'))
    
    # Auto-enroll student if not already enrolled
    user = users_collection.find_one({'_id': ObjectId(session['student_id'])})
    if course_id not in user.get('enrolled_courses', []):
        users_collection.update_one(
            {'_id': ObjectId(session['student_id'])},
            {'$addToSet': {'enrolled_courses': course_id}}
        )
    
    return render_template('student/course_page.html', course=course)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))

if __name__ == '__main__':
    app.run(debug=True)