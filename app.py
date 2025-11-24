from flask import Flask, render_template, request, redirect, session, url_for, Response
from werkzeug.security import check_password_hash
import psycopg
import os
import csv
import io
import database
from functools import wraps
import pandas as pd

## flask = web framework 
# render_template = Loads HTML files. 
# request = Reads form data. 
# redirect = Sends user to another page. 
# session = Stores login info. 
# check_password_hash = Verifies hashed passwords. 
# psycopg = The PostgreSQL database connection
# csv= To export CSV files
# io= To handle in-memory file operations
# pandas= To handle excel imports


app = Flask(__name__)
app.secret_key = "3530databasesecretkey"

database.init_app(app)

#function below connects to the database
def get_database():
    #in the terminal we specify DATABASE_URL which is the address to the database
    #os.environ["DATABASE_URL"] = connection string to the database. think of it as address of lib
    return psycopg.connect(conninfo=os.environ["DATABASE_URL"])

#function to check if the user is admin
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        if session.get("role") != "admin":
            return "Access Denied (Admin Only)", 403
        return f(*args, **kwargs)
    return wrapper


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
                cur.execute ('SELECT id, password_hash, role FROM app_user WHERE username = %s', (username,))
                user = cur.fetchone()

        if user is None:
            return "Invalid username or password"
    
        user_id, password_hash,role = user

        if not check_password_hash(password_hash, password):
            return "Invalid username or password"

        session["user_id"] = user_id
        session["username"] = username
        session["role"] = role
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
            COALESCE(wo.total_hours, 0) as total_hours,
            e.Ssn
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
@admin_required
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

@app.route("/managers")
def managers():
    if not login_required():
        return redirect("/login")

    conn = database.get_database()
    cur = conn.cursor()
    
    query = """
        SELECT 
            d.Dnumber,
            d.Dname,
            m.Fname,
            m.Minit,
            m.Lname,
            COUNT(DISTINCT e.Ssn) AS employee_count,
            COALESCE(SUM(w.Hours), 0) AS total_hours
        FROM Department d
        LEFT JOIN Employee m ON d.Mgr_ssn = m.Ssn
        LEFT JOIN Employee e ON d.Dnumber = e.Dno
        LEFT JOIN Works_On w ON e.Ssn = w.Essn
        GROUP BY d.Dnumber, d.Dname, m.Fname, m.Minit, m.Lname
        ORDER BY d.Dname
    """
    
    cur.execute(query)
    raw_data = cur.fetchall()
    
    # Format data using helper function
    departments = []
    for row in raw_data:
        dnumber, dname, fname, minit, lname, emp_count, total_hours = row
        manager_name = format_employee_name(fname, minit, lname)
        departments.append((dnumber, dname, manager_name, emp_count, total_hours))
    
    return render_template("managers.html", departments=departments)

def format_employee_name(fname, minit, lname):
    """Helper function to format employee names consistently"""
    if not fname or not lname:
        return "N/A"
    
    if minit and minit.strip():
        return f"{fname} {minit}. {lname}"
    else:
        return f"{fname} {lname}"

@app.route("/employee/edit/<ssn>", methods=["GET", "POST"])
@admin_required
def edit_employee(ssn):
    if not login_required():
        return redirect("/login")
    
    conn = database.get_database()
    cur = conn.cursor()
    
    if request.method == "GET":
        cur.execute("""
            SELECT Ssn, Fname, Minit, Lname, BDate, Address, Sex, Salary, Super_ssn, Dno
            FROM Employee
            WHERE Ssn = %s
        """, (ssn,))

        employee = cur.fetchone()
        
        if not employee:
            return redirect("/")
        
        cur.execute("SELECT Dnumber, Dname FROM Department ORDER BY Dname")
        departments = cur.fetchall()
        
        return render_template("employee_edit.html", employee=employee, departments=departments, error=None, success=None)
    
    # POST - Update employee (only Address, Salary, Dno as per requirements)
    try:
        address = request.form["address"].strip()
        salary = request.form["salary"]
        dno = request.form["dno"]
        
        cur.execute("""
            UPDATE Employee
            SET Address = %s, Salary = %s, Dno = %s
            WHERE Ssn = %s
        """, (address, salary, dno, ssn))
        
        conn.commit()
        return redirect("/")
        
    except Exception as e:
        conn.rollback()
        error_msg = str(e).lower()
        
        if "foreign key" in error_msg:
            error = "Error: Invalid department selected."
        else:
            error = "An error occurred while updating the employee."
        
        cur.execute("SELECT Ssn, Fname, Minit, Lname, BDate, Address, Sex, Salary, Super_ssn, Dno FROM Employee WHERE Ssn = %s", (ssn,))
        employee = cur.fetchone()
        cur.execute("SELECT Dnumber, Dname FROM Department ORDER BY Dname")
        departments = cur.fetchall()
        
        return render_template("employee_edit.html", employee=employee, departments=departments, error=error, success=None)


@app.route("/employee/delete/<ssn>", methods=["POST"])
@admin_required
def delete_employee(ssn):
    if not login_required():
        return redirect("/login")
    
    conn = database.get_database()
    cur = conn.cursor()
    
    try:
        cur.execute("DELETE FROM Employee WHERE Ssn = %s", (ssn,))
        conn.commit()
        return redirect("/")
        
    except Exception as e:
        conn.rollback()
        error_msg = str(e).lower()
        
        # Find error
        if "foreign key" in error_msg or "violates" in error_msg or "restrict" in error_msg:
            # Get employee name
            cur.execute("SELECT Fname, Lname FROM Employee WHERE Ssn = %s", (ssn,))
            emp = cur.fetchone()
            if emp is not None:
                name = f"{emp[0]} {emp[1]}"
            else:
                emp = "This employee"
            
            error = f"Cannot delete {name}: They are still assigned to projects, have dependents listed, or are a manager/supervisor. Please remove these associations first."
        else:
            error = "An unexpected error occurred while deleting the employee."
        
        # Show error
        cur.execute("SELECT Ssn, Fname, Minit, Lname, BDate, Address, Sex, Salary, Super_ssn, Dno FROM Employee WHERE Ssn = %s", (ssn,))
        employee = cur.fetchone()
        cur.execute("SELECT Dnumber, Dname FROM Department ORDER BY Dname")
        departments = cur.fetchall()
        
        return render_template("employee_edit.html", employee=employee, departments=departments, error=error, success=None)

@app.route("/employee/add", methods=["GET", "POST"])
@admin_required
def create_employee():
    if not login_required():
        return redirect("/login")
    
    conn = database.get_database()
    cur = conn.cursor()
    
    if request.method == "GET":
        # Get departments
        cur.execute("SELECT Dnumber, Dname FROM Department ORDER BY Dname")
        departments = cur.fetchall()
        
        # Get supervisors
        cur.execute("SELECT Ssn, Fname, Lname FROM Employee ORDER BY Lname, Fname")
        supervisors = cur.fetchall()
        
        return render_template("employee_add.html", departments=departments, supervisors=supervisors, error=None)
    
    # Create employee
    try:
        ssn = request.form["ssn"].strip()
        fname = request.form["fname"].strip()
        minit = request.form.get("minit", "").strip() or " "
        lname = request.form["lname"].strip()
        bdate = request.form.get("bdate") or None
        address = request.form["address"].strip()
        sex = request.form["sex"]
        salary = request.form["salary"]
        super_ssn = request.form.get("super_ssn") or None
        dno = request.form["dno"]
        empdate = request.form.get("empdate") or None
        
        cur.execute("""
            INSERT INTO Employee (Ssn, Fname, Minit, Lname, BDate, Address, Sex, Salary, Super_ssn, Dno, EmpDate)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (ssn, fname, minit, lname, bdate, address, sex, salary, super_ssn, dno, empdate))
        
        conn.commit()
        return redirect("/")
        
    except Exception as e:
        conn.rollback()
        error_msg = str(e).lower()
        
        # Find and handle specific errors
        if "unique" in error_msg or "duplicate" in error_msg:
            error = f"Error: SSN {ssn} already exists"
        elif "foreign key" in error_msg:
            error = "Error: Invalid department or supervisor selected"
        elif "check" in error_msg:
            error = "Error: Invalid sex value"
        else:
            error = "An error occurred while adding the employee"
        
        cur.execute("SELECT Dnumber, Dname FROM Department ORDER BY Dname")
        departments = cur.fetchall()
        cur.execute("SELECT Ssn, Fname, Lname FROM Employee ORDER BY Lname, Fname")
        supervisors = cur.fetchall()
        
        return render_template("employee_add.html", departments=departments, supervisors=supervisors, error=error)

@app.route("/import", methods=["GET", "POST"])
@admin_required
def import_excel():
    if not login_required():
        return redirect("/login")

    if request.method == "GET":
        return render_template("import_excel.html", error=None, success=None)

    if 'file' not in request.files:
        return render_template("import_excel.html", error="No file uploaded", success=None)

    file = request.files['file']
    table_choice = request.form.get('table')

    if file.filename == '':
        return render_template("import_excel.html", error="No file selected", success=None)

    if not file.filename.endswith('.xlsx'):
        return render_template("import_excel.html", error="File must be .xlsx", success=None)

    if not table_choice:
        return render_template("import_excel.html", error="Please select a table", success=None)

    try:
        # Remove blanks
        df = pd.read_excel(file).dropna(how="all")

        if table_choice == "employee":
            result = import_employees_df(df)
        elif table_choice == "dependent":
            result = import_dependents_df(df)
        elif table_choice == "project":
            result = import_projects_df(df)
        else:
            return render_template("import_excel.html", error="Invalid table", success=None)

        if result["success"]:
            return render_template("import_excel.html", error=None, success=f"Imported {result['count']} rows into {table_choice}")

        return render_template("import_excel.html", error=result["error"], success=None)

    except Exception as e:
        return render_template("import_excel.html", error=f"Error reading file: {str(e)}", success=None)
    
def import_employees_df(df):
    conn = database.get_database()
    cur = conn.cursor()

    required = ["Ssn", "Fname", "Minit", "Lname", "Address", "Sex", "Salary", "Super_ssn", "Dno", "BDate", "EmpDate"]

    missing = [c for c in required if c not in df.columns]
    if missing:
        return {"success": False, "error": "Missing columns: " + ", ".join(missing)}

    errors = []
    valid = []

    for idx, row in df.iterrows():
        excel_row = idx + 2

        ssn = str(row["Ssn"]).strip()
        print("SSN: ", ssn)
        fname = str(row["Fname"]).strip()
        minit = str(row["Minit"]).strip()[:1] if pd.notna(row["Minit"]) else " "
        lname = str(row["Lname"]).strip()
        address = str(row["Address"]).strip()
        sex = str(row["Sex"]).upper()
        salary = row["Salary"]

        # Remove .0 from the super ssn
        if pd.notna(row["Super_ssn"]):
            super_ssn = row["Super_ssn"]
            if isinstance(super_ssn, float):
                super_ssn = str(int(super_ssn))
            else:
                super_ssn = str(super_ssn).strip()
        else:
            super_ssn = None

        dno = row["Dno"]
        bdate = row["BDate"]
        empdate = row["EmpDate"]

        # Validate fields
        if len(ssn) != 9:
            errors.append(f"Row {excel_row}: SSN must be 9 digits")
            continue

        if sex not in ["M", "F"]:
            errors.append(f"Row {excel_row}: Sex must be M or F")
            continue

        try:
            salary = int(salary)
        except:
            errors.append(f"Row {excel_row}: Salary must be an integer")
            continue

        if salary < 0:
            errors.append(f"Row {excel_row}: Salary must be positive")
            continue

        cur.execute("SELECT COUNT(*) FROM Department WHERE Dnumber=%s", (dno,))
        if cur.fetchone()[0] == 0:
            errors.append(f"Row {excel_row}: Department {dno} does not exist")
            continue

        if super_ssn:
            print(f"Checking supervisor SSN: '{super_ssn}'")
            cur.execute("SELECT COUNT(*) FROM Employee WHERE Ssn=%s", (super_ssn,))
            print(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM Employee WHERE Ssn=%s", (super_ssn,))
            if cur.fetchone()[0] == 0:
                errors.append(f"Row {excel_row}: Supervisor {super_ssn} does not exist")
                continue

        
        valid.append((
            fname, minit, lname, ssn, address, sex, salary,
            super_ssn, dno, bdate, empdate
        ))

    if errors:
        conn.rollback()
        return {"success": False,
                "error": "Validation failed:\n" + "\n".join(errors)}

    try:
        cur.executemany("""
            INSERT INTO Employee(Fname, Minit, Lname, Ssn, Address, Sex, Salary, Super_ssn, Dno, BDate, EmpDate)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, valid)
        conn.commit()
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": f"Database error: {str(e)}"}

    return {"success": True, "count": len(valid)}

def import_dependents_df(df):
    conn = database.get_database()
    cur = conn.cursor()

    required = ["Essn", "Dependent_name", "Sex", "Bdate", "Relationship"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {"success": False, "error": "Missing columns: " + ", ".join(missing)}

    errors = []
    valid = []

    for idx, row in df.iterrows():
        excel_row = idx + 2

        essn = str(row["Essn"]).strip()
        dep = str(row["Dependent_name"]).strip()
        sex = str(row["Sex"]).upper()
        bdate = row["Bdate"]
        rel = str(row["Relationship"]).strip()

        if sex not in ["M", "F"]:
            errors.append(f"Row {excel_row}: Sex must be M or F")
            continue

        # Check employee exists
        cur.execute("SELECT COUNT(*) FROM Employee WHERE Ssn=%s", (essn,))
        if cur.fetchone()[0] == 0:
            errors.append(f"Row {excel_row}: Employee {essn} does not exist")
            continue

        valid.append((essn, dep, sex, bdate, rel))

    if errors:
        conn.rollback()
        return {"success": False, "error": "Validation failed:\n" + "\n".join(errors)}

    try:
        cur.executemany("""
            INSERT INTO Dependent(Essn, Dependent_name, Sex, Bdate, Relationship)
            VALUES (%s, %s, %s, %s, %s)
        """, valid)
        conn.commit()
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": f"Database error: {str(e)}"}

    return {"success": True, "count": len(valid)}

def import_projects_df(df):
    conn = database.get_database()
    cur = conn.cursor()

    required = ["Pnumber", "Pname", "Plocation", "Dnum"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {"success": False, "error": "Missing columns: " + ", ".join(missing)}

    errors = []
    valid = []

    for idx, row in df.iterrows():
        excel_row = idx + 2

        try:
            pnumber = int(row["Pnumber"])
        except:
            errors.append(f"Row {excel_row}: Pnumber must be an integer")
            continue

        pname = str(row["Pname"]).strip()
        ploc = str(row["Plocation"]).strip()
        dnum = row["Dnum"]

        cur.execute("SELECT COUNT(*) FROM Department WHERE Dnumber=%s", (dnum,))
        if cur.fetchone()[0] == 0:
            errors.append(f"Row {excel_row}: Department {dnum} does not exist")
            continue

        valid.append((pname, pnumber, ploc, dnum))

    if errors:
        conn.rollback()
        return {"success": False, "error": "Validation failed:\n" + "\n".join(errors)}

    try:
        cur.executemany("""
            INSERT INTO Project(Pname, Pnumber, Plocation, Dnum)
            VALUES (%s, %s, %s, %s)
        """, valid)
        conn.commit()
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": f"Database error: {str(e)}"}

    return {"success": True, "count": len(valid)}

if __name__ == "__main__":
    app.run(debug=True)
