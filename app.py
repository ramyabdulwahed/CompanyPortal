from flask import Flask, render_template, request, redirect, session
from werkzeug.security import check_password_hash
import psycopg
import os

## flask = web framework 
# render_template = Loads HTML files. 
# request = Reads form data. 
# redirect = Sends user to another page. 
# session = Stores login info. 
# check_password_hash = Verifies hashed passwords. 
# psycopg = The PostgreSQL database connection.


app = Flask(__name__)
app.secret_key = "3530databasesecretkey"


#function below connects to the database
def get_db():
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

        with get_db() as conn:
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

        return redirect("/")

    return render_template("login.html")


#logout users
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
                

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
