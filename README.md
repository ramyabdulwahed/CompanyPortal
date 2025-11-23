.\.venv\Scripts\activate  

## to connect to database

1. psql -U postgres -h localhost -p 5432 -d company_portal_db
2. password: postgres
3. $env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/company_portal_db"


# CIS*3530 Company Portal – Team Project

This project is a Flask + PostgreSQL web application implementing:
- Employee Overview
- Project Portfolio Summary
- Project Details with Upsert Logic
- CSV Export
- Managers Overview
- User Authentication with Password Hashing
- (Bonus) Role-Based Access Control (Admin vs Viewer)

---

# 1. Environment Setup

## 1.1 Create Virtual Environment
    In the company portal directory:
    1. python3 -m venv .venv
    2. .\.venv\Scripts\activate


## 1.2 Install Dependencies

    In the company portal directory:
    1. pip install -r requirements.txt



---

# 2. Database Setup

## 2.1 Create PostgreSQL Database
Replace `<username>` and `<password>` with your own PostgreSQL user.
createdb company_portal_db


## 2.2 Set DATABASE_URL Environment Variable

    Mac/Linux:
        1.export DATABASE_URL="postgresql://<username>:<password>@localhost:5432/company_portal_db"
    Windows PowerShell:
        1. $env:DATABASE_URL="postgresql://<username>:<password>@localhost:5432/company_portal_db"


---

# 3. Load Schema (Base Company Schema)
    1. psql -d $env:DATABASE_URL -f company_v3.02.sql


# 4. Load Custom Additions (team_setup.sql)
This file contains:
- app_user table
- initial admin + viewer accounts
- any additional views
- our two required indexes

    1. psql -d $env:DATABASE_URL -f team_setup.sql


---

# 5. Run the Application
    1. flask run
    2. click on the link in the terminal

# 6. Index Justification


1. idx_employee_name (Lname, Fname)

    CREATE INDEX IF NOT EXISTS idx_employee_name ON Employee (Lname, Fname);

    Reason: This index improves performance of the Employee Overview page (A2).

    On this page, we allow the user to:

        1. Search by first or last name

        2. Sort employees alphabetically (ORDER BY e.Lname, e.Fname)

    Because the query frequently filters or orders by Lname, Fname, this index allows PostgreSQL to avoid scanning the entire Employee table and instead use a sorted index to retrieve matching rows efficiently.

2. dx_workson_pno (Works_On Pno) 
    CREATE INDEX IF NOT EXISTS idx_workson_pno ON Works_On (Pno); 
    
    Reason: This index improves performance of: Projects Portfolio page (A3) Project Details page (A4) 
    Both pages repeatedly run aggregate queries like:
        1. SELECT COUNT(w.Essn), SUM(w.Hours) FROM Works_On w WHERE w.Pno = ...
        2. JOIN Works_On w ON p.Pnumber = w.Pno
    Because these queries filter and group by Pno, indexing Pno significantly speeds up lookups and reduces full-table scans of Works_On.


---

# 7. Default Login Accounts (from team_setup.sql)

    **Admin Account**
    - username: admin
    - password: admin123

    **Viewer Account**
    - username: viewer1
    - password: viewer123
