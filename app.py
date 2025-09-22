from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from db_config import MYSQL_CONFIG
import re

app = Flask(__name__)
app.secret_key = "change_this_secret"  # change for production


def get_db():
    return mysql.connector.connect(**MYSQL_CONFIG)


def valid_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)


def password_ok(pw):
    # at least 6 chars, include letter and digit
    return len(pw) >= 6 and re.search(r"\d", pw) and re.search(r"[A-Za-z]", pw)


@app.route('/')
def index():
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT p.*, u.agency_name FROM plans p JOIN users u ON p.agency_id=u.id ORDER BY p.created_at DESC")
    plans = cur.fetchall()
    cur.close(); conn.close()
    return render_template('index.html', plans=plans)


@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        email = request.form.get('email','').strip()
        role = request.form.get('role','customer')
        agency_name = request.form.get('agency_name') or None

        if not username or not password:
            flash('Username and password are required', 'error'); return redirect(url_for('register'))
        if email and not valid_email(email):
            flash('Invalid email format', 'error'); return redirect(url_for('register'))
        if not password_ok(password):
            flash('Password must be 6+ chars and include letters and numbers', 'error'); return redirect(url_for('register'))

        hashed = generate_password_hash(password)
        conn = get_db(); cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username,password,email,role,agency_name) VALUES (%s,%s,%s,%s,%s)",
                        (username, hashed, email if email else None, role, agency_name))
            conn.commit()
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError as e:
            # handle duplicate username/email
            err = str(e)
            if 'username' in err or 'UNIQUE' in err:
                flash('Username or email already exists.', 'error')
            else:
                flash('Registration failed.', 'error')
            return redirect(url_for('register'))
        finally:
            cur.close(); conn.close()
    return render_template('register.html')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        if not username or not password:
            flash('Username and password required', 'error'); return redirect(url_for('login'))

        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute('SELECT * FROM users WHERE username=%s', (username,))
        user = cur.fetchone()
        cur.close(); conn.close()
        if not user:
            flash('User not found. Please register.', 'error'); return redirect(url_for('register'))
        if check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Logged in successfully', 'success')
            return redirect(url_for('agency_dashboard') if user['role']=='agency' else url_for('customer_dashboard'))
        else:
            flash('Invalid credentials', 'error'); return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear(); flash('Logged out', 'info'); return redirect(url_for('index'))


@app.route('/agency_dashboard')
def agency_dashboard():
    if 'user_id' not in session or session.get('role')!='agency':
        flash('Please login as agency', 'error'); return redirect(url_for('login'))
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute('SELECT * FROM plans WHERE agency_id=%s ORDER BY created_at DESC', (session['user_id'],))
    plans = cur.fetchall()
    cur.close(); conn.close()
    return render_template('agency_dashboard.html', plans=plans)


@app.route('/agency/plan/new', methods=['GET','POST'])
def new_plan():
    if 'user_id' not in session or session.get('role')!='agency':
        return redirect(url_for('login'))
    if request.method=='POST':
        title = request.form.get('title','').strip()
        price = request.form.get('price','').strip()
        if not title or not price:
            flash('Title and price required', 'error'); return redirect(url_for('new_plan'))
        conn = get_db(); cur = conn.cursor()
        cur.execute('INSERT INTO plans (agency_id,title,description,destination,duration,price) VALUES (%s,%s,%s,%s,%s,%s)',
                    (session['user_id'], title, request.form.get('description'), request.form.get('destination'),
                     request.form.get('duration'), price))
        conn.commit(); cur.close(); conn.close(); flash('Plan added', 'success'); return redirect(url_for('agency_dashboard'))
    return render_template('agency_edit_plan.html', plan=None)


@app.route('/agency/plan/edit/<int:plan_id>', methods=['GET','POST'])
def edit_plan(plan_id):
    if 'user_id' not in session or session.get('role')!='agency':
        return redirect(url_for('login'))
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute('SELECT * FROM plans WHERE id=%s AND agency_id=%s', (plan_id, session['user_id']))
    plan = cur.fetchone()
    if not plan:
        cur.close(); conn.close(); flash('Plan not found', 'error'); return redirect(url_for('agency_dashboard'))
    if request.method=='POST':
        cur.execute('UPDATE plans SET title=%s, description=%s, destination=%s, duration=%s, price=%s WHERE id=%s',
                    (request.form.get('title'), request.form.get('description'), request.form.get('destination'),
                     request.form.get('duration'), request.form.get('price'), plan_id))
        conn.commit(); cur.close(); conn.close(); flash('Plan updated', 'success'); return redirect(url_for('agency_dashboard'))
    cur.close(); conn.close()
    return render_template('agency_edit_plan.html', plan=plan)


@app.route('/agency/plan/delete/<int:plan_id>', methods=['POST'])
def delete_plan(plan_id):
    if 'user_id' not in session or session.get('role')!='agency':
        return redirect(url_for('login'))
    conn = get_db(); cur = conn.cursor()
    cur.execute('DELETE FROM plans WHERE id=%s AND agency_id=%s', (plan_id, session['user_id']))
    conn.commit(); cur.close(); conn.close(); flash('Plan deleted', 'info'); return redirect(url_for('agency_dashboard'))


@app.route('/customer_dashboard')
def customer_dashboard():
    if 'user_id' not in session or session.get('role')!='customer':
        flash('Please login as customer', 'error'); return redirect(url_for('login'))
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute('SELECT p.*, u.agency_name FROM plans p JOIN users u ON p.agency_id=u.id ORDER BY p.created_at DESC')
    plans = cur.fetchall()
    cur.execute('SELECT b.*, p.title, p.price FROM bookings b LEFT JOIN plans p ON b.plan_id=p.id WHERE b.customer_id=%s ORDER BY b.booking_date DESC', (session['user_id'],))
    bookings = cur.fetchall()
    cur.close(); conn.close()
    return render_template('customer_dashboard.html', plans=plans, bookings=bookings)


@app.route('/plan/<int:plan_id>')
def view_plan(plan_id):
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute('SELECT p.*, u.agency_name FROM plans p JOIN users u ON p.agency_id=u.id WHERE p.id=%s', (plan_id,))
    plan = cur.fetchone(); cur.close(); conn.close()
    if not plan:
        flash('Plan not found', 'error'); return redirect(url_for('index'))
    return render_template('view_plan.html', plan=plan)


@app.route('/book', methods=['POST'])
def book():
    if 'user_id' not in session or session.get('role')!='customer':
        flash('Please login as customer', 'error'); return redirect(url_for('login'))
    plan_id = request.form.get('plan_id'); travel_date = request.form.get('travel_date'); seats = int(request.form.get('seats',1))
    if not plan_id or not travel_date:
        flash('Plan and travel date required', 'error'); return redirect(url_for('customer_dashboard'))
    conn = get_db(); cur = conn.cursor()
    cur.execute('INSERT INTO bookings (customer_id, plan_id, travel_date, seats, status) VALUES (%s,%s,%s,%s,%s)',
                (session['user_id'], plan_id, travel_date, seats, 'pending'))
    conn.commit(); cur.close(); conn.close(); flash('Booking created (pending payment)', 'success'); return redirect(url_for('customer_dashboard'))


@app.route('/booking/cancel/<int:booking_id>', methods=['POST'])
def cancel_booking(booking_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db(); cur = conn.cursor()
    cur.execute('DELETE FROM bookings WHERE id=%s AND customer_id=%s', (booking_id, session['user_id']))
    conn.commit(); cur.close(); conn.close(); flash('Booking cancelled', 'info'); return redirect(url_for('customer_dashboard'))


@app.route('/payment/<int:booking_id>', methods=['GET','POST'])
def payment(booking_id):
    if 'user_id' not in session or session.get('role')!='customer':
        flash('Please login as customer', 'error'); return redirect(url_for('login'))
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute('SELECT b.*, p.title, p.price FROM bookings b JOIN plans p ON b.plan_id=p.id WHERE b.id=%s AND b.customer_id=%s', (booking_id, session['user_id']))
    booking = cur.fetchone(); cur.close(); conn.close()
    if not booking:
        flash('Booking not found', 'error'); return redirect(url_for('customer_dashboard'))
    if request.method=='POST':
        conn2 = get_db(); cur2 = conn2.cursor(); cur2.execute('UPDATE bookings SET payment_status=%s, status=%s WHERE id=%s', ('paid','paid', booking_id)); conn2.commit(); cur2.close(); conn2.close(); flash('Payment successful. Booking confirmed!', 'success'); return redirect(url_for('customer_dashboard'))
    return render_template('payment.html', booking=booking)


if __name__=='__main__':
    app.run(debug=True)
