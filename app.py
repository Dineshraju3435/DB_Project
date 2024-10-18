from bson import ObjectId
from flask import Flask, render_template, request, redirect, session, url_for, flash
from pymongo import MongoClient
import re

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# MongoDB connection
client = MongoClient('localhost', 27031)
db = client['student_db']  # creating the database
users = db['users']  # creating a collection for users
todos_collection = db['todos'] #creating the collection fro todos
finances_collection = db['finances']  # Creating the collection for finances

# Email regex pattern
EMAIL_REGEX = r'^[A-Za-z0-9]+@[a-z]+\.[a-z]{3}$'

@app.route("/", methods=('GET', 'POST'))
def index():
    return render_template('index.html')

# Route for Sign-Up Page
@app.route("/signup", methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        rollno = request.form['roll_no']
        university_id = request.form['university_id']
        department = request.form['department']

        # Validate email format
        if not re.match(EMAIL_REGEX, email):
            flash('Invalid email format! Please enter a valid email.')
            return redirect(url_for('signup'))

        # Check if email already exists
        existing_user = users.find_one({'email': email})
        if existing_user:
            flash('Email already exists. Please login.')
            return redirect(url_for('login'))

        # Creating a user entry in MongoDB
        users.insert_one({
            'name': name,
            'email': email,
            'password': password,
            'rollno':rollno,
            'university_id': university_id,
            'department': department,
        })
        
        flash('Sign-Up Successful! Please login.')
        return redirect(url_for('dashboard'))

    return render_template('signup.html')

# Route for Login Page
@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Validate email format
        if not re.match(EMAIL_REGEX, email):
            flash('Invalid email format! Please enter a valid email.')
            return redirect(url_for('login'))

        # Finding the user in MongoDB
        user = users.find_one({'email': email})
        
        if user and user['password'] == password:
            session['user_email'] = email  # Set the user email in session
            flash('Login successful!')
            return redirect(url_for('dashboard'))
        else:
            flash('Login failed. Check your email or password.')
    
    return render_template('login.html')

# Route for performance page
@app.route("/performance", methods=['GET', 'POST'])
def performance():
    if 'user_email' not in session:
        flash('You need to log in first.')
        return redirect(url_for('login'))

    user_email = session['user_email']

    if request.method == 'POST':
        semester = request.form.get('semester')
        session['current_semester'] = semester  # Store the current semester in session
        
        num_courses = int(request.form.get('num_courses', 0))

        courses = []
        total_gpa = 0
        grade_points = {
            "O": 10,
            "A+": 9,
            "A": 8,
            "B+": 7,
            "B": 6,
            "C": 5
        }
        valid_grades = []

        for i in range(num_courses):
            grade = request.form.get(f'grade_{i}')
            credit_hours = int(request.form.get(f'credit_hours_{i}'))

            if grade in grade_points:
                valid_grades.append((grade_points[grade], credit_hours))

            course_data = {
                'course_name': request.form.get(f'course_name_{i}'),
                'course_code': request.form.get(f'course_code_{i}'),
                'credit_hours': credit_hours,
                'grade': grade,
                'attendance': request.form.get(f'attendance_{i}')
            }
            courses.append(course_data)

        # Calculate CGPA
        total_gpa = sum(gpa * credits for gpa, credits in valid_grades)
        total_credit_hours = sum(credits for _, credits in valid_grades)
        cgpa = total_gpa / total_credit_hours if total_credit_hours > 0 else 0

        # Update the user's courses and CGPA in the database
        users.update_one(
            {'email': user_email},
            {'$push': {'semesters': {'semester': semester, 'cgpa': cgpa, 'courses': courses}}}
        )

        flash('Courses added/updated successfully!')
        return redirect(url_for('performance'))

    # Retrieve previously added courses
    user_data = users.find_one({'email': user_email})
    semesters = user_data.get('semesters', []) if user_data else []

    return render_template('performance.html', semesters=semesters)

# Route for dashboard page
@app.route("/dashboard", methods=['GET', 'POST'])
def dashboard():
    if 'user_email' not in session:
        flash('You need to log in first.')
        return redirect(url_for('login'))

    user_email = session['user_email']
    user_data = users.find_one({'email': user_email})

    if user_data:
        user_name = user_data.get('name')
        semesters = user_data.get('semesters', [])

        # Calculate the CGPA for each semester
        semester_gpas = {}
        for semester in semesters:
            semester_name = semester['semester']
            if semester_name not in semester_gpas:
                semester_gpas[semester_name] = {
                    'total_credits': 0,
                    'total_points': 0,
                    'courses': []
                }

            courses = semester.get('courses', [])
            for course in courses:
                credit_hours = course['credit_hours']
                grade = course['grade']
                points = grade_to_points(grade)

                semester_gpas[semester_name]['total_credits'] += credit_hours
                semester_gpas[semester_name]['total_points'] += credit_hours * points
                semester_gpas[semester_name]['courses'].append(course)

        # Calculate final CGPA for each semester
        final_semester_gpas = {}
        for semester_name, data in semester_gpas.items():
            total_credits = data['total_credits']
            total_points = data['total_points']
            cgpa = round(total_points / total_credits, 2) if total_credits > 0 else 0
            final_semester_gpas[semester_name] = cgpa

        # Prepare data for the chart
        semester_names = list(final_semester_gpas.keys())
        cgpa_values = list(final_semester_gpas.values())

        # Retrieve completed tasks
        completed_tasks = todos_collection.find({
            'email': user_email,
            'is_completed': True
        })

        return render_template('dashboard.html', user_name=user_name,
                               semester_gpas=final_semester_gpas,
                               semester_names=semester_names,
                               cgpa_values=cgpa_values,
                               completed_tasks=completed_tasks)  # Pass completed tasks

    flash('User data not found.')
    return redirect(url_for('login'))

@app.route("/todo", methods=['GET', 'POST'])
def todo():
    if 'user_email' not in session:
        flash('You need to log in first.')
        return redirect(url_for('login'))

    user_email = session['user_email']

    if request.method == 'POST':
        task_name = request.form.get('task_name')

        if task_name:
            # Add task to the todos collection in the database
            todos_collection.insert_one({
                'email': user_email,  # Store the user's email
                'task': task_name,
                'is_completed': False  # New attribute to track completion status
            })
            flash('Task added successfully!')

        return redirect(url_for('todo'))

    # Retrieve user's to-do tasks
    user_todos = todos_collection.find({'email': user_email})  # Find tasks by user's email
    todos = list(user_todos)  # Convert cursor to a list

    return render_template('todo.html', todos=todos)

@app.route("/update_task/<task_id>", methods=['POST'])
def update_task(task_id):
    new_task_name = request.form.get('new_task_name')

    if new_task_name:
        # Update the task in the database
        todos_collection.update_one(
            {'_id': ObjectId(task_id)},  # Match the task by its ID
            {'$set': {'task': new_task_name}}  # Update the task field
        )
        flash('Task updated successfully!')

    return redirect(url_for('todo'))

@app.route("/delete_task/<task_id>", methods=['POST'])
def delete_task(task_id):
    # Delete the task from the database
    todos_collection.delete_one({'_id': ObjectId(task_id)})
    flash('Task deleted successfully!')
    return redirect(url_for('todo'))

@app.route("/complete_task/<task_id>", methods=['POST'])
def complete_task(task_id):
    # Toggle the completion status of the task
    task = todos_collection.find_one({'_id': ObjectId(task_id)})

    if task:
        # Update the is_completed attribute based on the current status
        new_status = not task.get('is_completed', False)
        todos_collection.update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {'is_completed': new_status}}
        )
        flash('Task completion status updated successfully!')

    return redirect(url_for('todo'))

@app.route("/finance_tracker", methods=['GET', 'POST'])
def finance_tracker():
    if 'user_email' not in session:
        flash('You need to log in first.')
        return redirect(url_for('login'))

    user_email = session['user_email']

    if request.method == 'POST':
        # This block handles adding a new expenditure
        title = request.form.get('title')
        amount = request.form.get('amount')
        date = request.form.get('date')
        category = request.form.get('category')
        semester = request.form.get('semester')

        if title and amount and date and category and semester:
            # Insert the expenditure into the finance_collection
            finances_collection.insert_one({
                'email': user_email,
                'title': title,
                'amount': float(amount),
                'date': date,
                'category': category,
                'semester': semester
            })
            flash('Expenditure added successfully!')
            return redirect(url_for('finance_tracker'))

    # Retrieve expenditures from the finance_collection
    expenditures = list(finances_collection.find({'email': user_email}))

    # Aggregation to calculate total expenditures per semester
    pipeline = [
        {"$match": {"email": user_email}},  # Match the user
        {"$group": {
            "_id": "$semester",  # Group by semester
            "total": {"$sum": "$amount"}  # Sum the amounts
        }},
        {"$sort": {"total": 1}}  # Sort by total expenditure ascending for graph purposes
    ]

    # Fetch the aggregated results
    aggregation_result = list(finances_collection.aggregate(pipeline))

    # Prepare data for the graph
    semesters = [entry['_id'] for entry in aggregation_result]
    totals = [entry['total'] for entry in aggregation_result]

    max_semester = None
    max_amount = 0
    min_semester = None
    min_amount = float('inf')

    # Determine max and min semester expenditures from the aggregation result
    for entry in aggregation_result:
        if entry['total'] > max_amount:
            max_amount = entry['total']
            max_semester = entry['_id']
        if entry['total'] < min_amount:
            min_amount = entry['total']
            min_semester = entry['_id']

    # Handle the case where there are no expenditures
    if max_semester is None:
        max_semester = min_semester = "N/A"
        max_amount = min_amount = 0

    # Render the finance tracker page with expenditures and analysis
    return render_template(
        'finance_tracker.html',
        expenditures=expenditures,
        max_semester=max_semester,
        max_amount=max_amount,
        min_semester=min_semester,
        min_amount=min_amount,
        semesters=semesters,
        totals=totals
    )

@app.route("/add_expenditure", methods=['POST'])
def add_expenditure():
    if 'user_email' not in session:
        flash('You need to log in first.')
        return redirect(url_for('login'))

    title = request.form.get('title')
    amount = request.form.get('amount')
    date = request.form.get('date')
    category = request.form.get('category')
    semester = request.form.get('semester')  # Retrieve semester from the form

    user_email = session['user_email']

    # Insert the expenditure into the finance_collection
    finances_collection.insert_one({
        'email': user_email,
        'title': title,
        'amount': float(amount),
        'date': date,
        'category': category,
        'semester': semester  # Add the current semester to the finance record
    })

    flash('Expenditure added successfully!')
    return redirect(url_for('finance_tracker'))


def grade_to_points(grade):
    grade_map = {
        'O': 10,
        'A+': 9,
        'A': 8,
        'B+': 7,
        'B': 6,
        'C': 5
    }
    return grade_map.get(grade, 0)

# logging out i.e. deleting the session.
@app.route('/logout')
def logout():
    # Logic to log out the user, e.g., clearing session data
    session.pop('user_email', None)  # Assuming you're using sessions
    return redirect(url_for('index'))  # Redirect to the login page

if __name__ == '__main__':
    app.run(debug=True)
