from flask import Flask, render_template, request, redirect, session, url_for, Response
from werkzeug.security import check_password_hash
import psycopg
import os
import csv
import io

## flask = web framework 
# render_template = Loads HTML files. 
# request = Reads form data. 
# redirect = Sends user to another page. 
# session = Stores login info. 
# check_password_hash = Verifies hashed passwords. 
# psycopg = The PostgreSQL database connection
# csv= To export CSV files
# io= To handle in-memory file operations


app = Flask(__name__)
app.secret_key = "3530databasesecretkey"


#function below connects to the database
def get_database():
    #in the terminal we specify DATABASE_URL which is the address to the database
    #os.environ["DATABASE_URL"] = connection string to the database. think of it as address of lib
    return psycopg.connect(conninfo=os.environ["DATABASE_URL"])


def login_required():
    if "user_id" not in session:
        return False
    return True

#functio handles login page and accepts both GET and POST requests for user visiting and submitting form
@app.route("/login", methods = ["GET", "POST"])
def login():
    if request.method == "POST":

        #grab values from html form
        username = request.form["username"]
        password = request.form["password"]

        with get_database() as conn:
            with conn.cursor() as cur: #cur is a cursor/worker to execute queries
                cur.execute ('SELECT id, password_hash FROM app_user WHERE username = %s', (username,))
                user = cur.fetchone()

        if user is None:
            return "Invalid username or password"
    
        user_id, password_hash = user

        if not check_password_hash(password_hash, password):
            return "Invalid username or password"

        session["user_id"] = user_id
        session["username"] = username
        #how we remeber who the user is in between page loads

        return redirect(url_for('index'))

    return render_template("login.html")


#logout users
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
                

#A2 Home, Employee Overview
@app.route("/")
def index():
    #check if user is logged in
    if not login_required():
        return redirect(url_for('login'))

    db = get_database()
    cursor = db.cursor()

    #get departments for the filter dropdown
    cursor.execute("SELECT Dnumber, Dname FROM Department ORDER BY Dname")
    departments = cursor.fetchall()

    #get search and sort settings from URL
    search_name = request.args.get('search', '').strip()
    filter_dept = request.args.get('dept', '')
    sort_by = request.args.get('sort_by', 'name')
    order = request.args.get('order', 'asc')

    #define allowed sort columns
    valid_sorts = {
        'name': 'e.Lname, e.Fname',
        'total_hours': 'total_hours'
    }
    valid_orders = {'asc': 'ASC', 'desc': 'DESC'}
    
    #set sort column and direction
    sql_sort_col = valid_sorts.get(sort_by, 'e.Lname, e.Fname')
    sql_sort_dir = valid_orders.get(order.lower(), 'ASC')

    #build query to get employee stats (dependents, projects, hours)
    query = """
        SELECT 
            e.Fname, e.Lname, d.Dname, 
            COALESCE(dep.dep_count, 0) as num_dependents,
            COALESCE(wo.proj_count, 0) as num_projects,
            COALESCE(wo.total_hours, 0) as total_hours
        FROM Employee e
        JOIN Department d ON e.Dno = d.Dnumber
        LEFT JOIN (
            SELECT Essn, COUNT(*) as dep_count 
            FROM Dependent GROUP BY Essn
        ) dep ON e.Ssn = dep.Essn
        LEFT JOIN (
            SELECT Essn, COUNT(*) as proj_count, SUM(Hours) as total_hours 
            FROM Works_On GROUP BY Essn
        ) wo ON e.Ssn = wo.Essn
        WHERE 1=1
    """
    
    params = []

    #add search filter if user typed a name
    if search_name:
        query += " AND (e.Fname ILIKE %s OR e.Lname ILIKE %s)"
        params.extend([f"%{search_name}%", f"%{search_name}%"])
    
    #add department filter if selected
    if filter_dept and filter_dept.isdigit():
        query += " AND e.Dno = %s"
        params.append(int(filter_dept))

    #add sorting to query
    query += f" ORDER BY {sql_sort_col} {sql_sort_dir}"

    # do query and get results
    cursor.execute(query, tuple(params))
    employees = cursor.fetchall()
    cursor.close()
    db.close()

    # show the home page
    return render_template("home.html", 
                           employees=employees, 
                           departments=departments,
                           current_search=search_name,
                           current_dept=filter_dept,
                           current_sort=sort_by,
                           current_order=order)

# A3: Projects , Portfolio Summary 
@app.route("/projects")
def projects():
    #check login
    if not login_required():
        return redirect(url_for('login'))

    # get sort settings
    sort_by = request.args.get('sort_by', 'pname')
    order = request.args.get('order', 'asc')

    #define allowed sort columns
    valid_sorts = {
        'pname': 'p.Pname',
        'headcount': 'headcount',
        'total_hours': 'total_hours'
    }
    valid_orders = {'asc': 'ASC', 'desc': 'DESC'}

    sql_sort_col = valid_sorts.get(sort_by, 'p.Pname')
    sql_sort_dir = valid_orders.get(order.lower(), 'ASC')

    db = get_database()
    cursor = db.cursor()

    # query project stats (headcount, total hours)
    query = f"""
        SELECT p.Pnumber, p.Pname, d.Dname, 
               COUNT(w.Essn) as headcount, 
               COALESCE(SUM(w.Hours), 0) as total_hours
        FROM Project p
        JOIN Department d ON p.Dnum = d.Dnumber
        LEFT JOIN Works_On w ON p.Pnumber = w.Pno
        GROUP BY p.Pnumber, p.Pname, d.Dname
        ORDER BY {sql_sort_col} {sql_sort_dir}
    """
    
    cursor.execute(query)
    projects_data = cursor.fetchall()
    cursor.close()
    db.close()

    #show projects page
    return render_template("projects.html", projects=projects_data, current_sort=sort_by, current_order=order)

# A4: Project Details 
@app.route("/project/<int:pno>")
def project_details(pno):
    if not login_required():
        return redirect(url_for('login'))

    db = get_database()
    cursor = db.cursor()

    #get project info
    cursor.execute("""
        SELECT p.Pname, d.Dname, p.Pnumber
        FROM Project p 
        JOIN Department d ON p.Dnum = d.Dnumber 
        WHERE p.Pnumber = %s
    """, (pno,))
    project = cursor.fetchone()

    # return 404 if project not found
    if not project:
        db.close()
        return "Project not found", 404

    # get employees assigned to this project
    cursor.execute("""
        SELECT e.Fname, e.Lname, w.Hours
        FROM Employee e
        JOIN Works_On w ON e.Ssn = w.Essn
        WHERE w.Pno = %s
        ORDER BY e.Lname, e.Fname
    """, (pno,))
    assigned_employees = cursor.fetchall()

    # get all employees for the dropdown list
    cursor.execute("SELECT Ssn, Fname, Lname FROM Employee ORDER BY Lname, Fname")
    all_employees = cursor.fetchall()
    
    cursor.close()
    db.close()

    #show details page
    return render_template("project_details.html", 
                           project=project, pno=pno, 
                           assigned=assigned_employees, 
                           all_employees=all_employees)

# A4: upsert Logic
@app.route("/project/<int:pno>/assign", methods=["POST"])
def assign_hours(pno):
    if not login_required():
        return redirect(url_for('login'))

    # Get form data
    essn = request.form.get('essn')
    hours = request.form.get('hours')

    # Validate input (makes sure input hour is fixed not a float)
    if not essn or not hours:
        return "Missing data", 400

    try:
        hours_val = float(hours)
    except ValueError:
        return "Invalid hours", 400

    db = get_database()
    cursor = db.cursor()

    try:
        #insert new assignment or update existing hours (Upsert)
        cursor.execute("""
            INSERT INTO Works_On (Essn, Pno, Hours)
            VALUES (%s, %s, %s) 
            ON CONFLICT (Essn, Pno)
            DO UPDATE SET Hours = Works_On.Hours + EXCLUDED.Hours;
        """, (essn, pno, hours_val))
        
        db.commit() # save changes

    except Exception as e:
        #rollback: if any error occurs, cancel so the database isn't left half-broken (taught in lecture)
        db.rollback() 

        #return a 500 error to the user
        return f"An error occurred: {e}", 500
        
    finally:
        # slose the cursor and connection
        #prevents "connection leaks" which can crash the database server
        cursor.close()
        db.close()

    #redirect back to details page
    return redirect(url_for('project_details', pno=pno))

# --- Extra: Export CSV ---
@app.route("/export")
def export_csv():
    if not login_required():
        return redirect(url_for('login'))

    db = get_database()
    cursor = db.cursor()

    #reuse the exact same logic as index()
    search_name = request.args.get('search', '').strip()
    filter_dept = request.args.get('dept', '')
    sort_by = request.args.get('sort_by', 'name')
    order = request.args.get('order', 'asc')

    valid_sorts = {
        'name': 'e.Lname, e.Fname',
        'total_hours': 'total_hours'
    }
    valid_orders = {'asc': 'ASC', 'desc': 'DESC'}
    
    sql_sort_col = valid_sorts.get(sort_by, 'e.Lname, e.Fname')
    sql_sort_dir = valid_orders.get(order.lower(), 'ASC')

    query = """
        SELECT 
            e.Fname, e.Lname, d.Dname, 
            COALESCE(dep.dep_count, 0) as num_dependents,
            COALESCE(wo.proj_count, 0) as num_projects,
            COALESCE(wo.total_hours, 0) as total_hours
        FROM Employee e
        JOIN Department d ON e.Dno = d.Dnumber
        LEFT JOIN (
            SELECT Essn, COUNT(*) as dep_count 
            FROM Dependent GROUP BY Essn
        ) dep ON e.Ssn = dep.Essn
        LEFT JOIN (
            SELECT Essn, COUNT(*) as proj_count, SUM(Hours) as total_hours 
            FROM Works_On GROUP BY Essn
        ) wo ON e.Ssn = wo.Essn
        WHERE 1=1
    """
    
    params = []

    if search_name:
        query += " AND (e.Fname ILIKE %s OR e.Lname ILIKE %s)"
        params.extend([f"%{search_name}%", f"%{search_name}%"])
    
    if filter_dept and filter_dept.isdigit():
        query += " AND e.Dno = %s"
        params.append(int(filter_dept))

    query += f" ORDER BY {sql_sort_col} {sql_sort_dir}"

    cursor.execute(query, tuple(params))
    employees = cursor.fetchall()
    cursor.close()
    db.close()

    #genereate CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    #write header
    writer.writerow(['First Name', 'Last Name', 'Department', 'Dependents', 'Projects', 'Total Hours'])
    
    #write data
    for row in employees:
        writer.writerow(row)
    
    output.seek(0)
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=employee_list.csv"}
    )

if __name__ == "__main__":
    app.run(debug=True)
