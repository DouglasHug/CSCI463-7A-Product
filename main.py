from dask.sizeof import sizeof
from flask import Flask, render_template, request, session, redirect, url_for
import pymysql
import uuid
from datetime import datetime
from flask_session import Session
import requests

# constants
VENDOR_ID = "VE001-99"
CREDIT_CARD_URL = "http://blitz.cs.niu.edu/CreditCard/"

app = Flask(__name__)

# Session config stuff
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SECRET_KEY'] = 'your-secret-key'
Session(app)


# Database connections
def get_legacy_db_connection():
	conn = pymysql.connect(
		host="blitz.cs.niu.edu",
		user="student",
		password="student",
		database="csci467"
	)
	return conn


def get_new_db_connection():
	conn = pymysql.connect(
		host="database-1.cvcyq6uosq31.us-east-2.rds.amazonaws.com",
		port=3306,
		user="admin",
		password="admin12345",
		database="my_database"
	)
	return conn


@app.route('/')
def index():
	return "Welcome to the Parts Store!"


@app.route('/browse')
def browse_catalog():
	#Get parts list from legacy database
	conn = get_legacy_db_connection()
	cursor = conn.cursor()
	cursor.execute('SELECT * FROM parts')
	conn.close()

	#Put query results into a dictionary
	columns = [col[0] for col in cursor.description]
	parts = [dict(zip(columns, row)) for row in cursor.fetchall()]

	#Get part IDs from dictionary
	part_nums = [part['number'] for part in parts]

	inv_conn = get_new_db_connection()
	inv_cursor = inv_conn.cursor()

	query = f"SELECT number, quantity FROM inventory WHERE number IN ({','.join(['%s'] * len(part_nums))})"
	inv_cursor.execute(query, part_nums)
	inv_data = {row[0]: row[1] for row in inv_cursor.fetchall()}
	inv_conn.close()

	for part in parts:
		part['quantity'] = inv_data.get(part['number'], 0)


	return render_template('browse.html', parts=parts, cartsize = len(session.get('cart')))


@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
	part_id = request.form.get('submit_part')
	quantity = int(request.form.get(f'partamount_{part_id}', 1))
	cart = session.get('cart', [])

	for item in cart:
		if item['part_id'] == part_id:
			item['quantity'] += quantity
			break
	else:
		cart.append({'part_id': part_id, 'quantity': quantity})


	#session['cart'] = []
	print(cart)
	return redirect(url_for('browse_catalog'))


@app.route('/checkout', methods=['GET'])
def checkout():
	cart = session.get('cart', [])
	if not cart:
		return "Your cart is empty!"

	conn = get_new_db_connection()
	cursor = conn.cursor()

	part_ids = [item['part_id'] for item in cart]
	format_strings = ','.join(['%s'] * len(part_ids))
	query = f"SELECT * FROM parts WHERE number IN ({format_strings})"
	cursor.execute(query, part_ids)

	parts = cursor.fetchall()
	conn.close()

	total_price = 0
	detailed_cart = []
	for item in cart:
		for part in parts:
			if part[0] == int(item['part_id']):
				subtotal = part[2] * item['quantity']
				total_price += subtotal
				detailed_cart.append({
					'description': part[1],
					'price': part[2],
					'quantity': item['quantity'],
					'subtotal': subtotal
				})
				break

	return render_template('checkout.html', cart=detailed_cart, total=total_price)


@app.route('/authorize_payment', methods=['POST'])
def authorize_payment():
	card_number = request.form.get('card_number')
	card_name = request.form.get('card_name')
	card_exp = request.form.get('card_exp')
	total_price = float(request.form.get('total_price'))

	transaction_id = f"{uuid.uuid4()}"

	payload = {
		'vendor': VENDOR_ID,
		'trans': transaction_id,
		'cc': card_number,
		'name': card_name,
		'exp': card_exp,
		'amount': f"{total_price:.2f}"
	}

	try:
		headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
		response = requests.post(CREDIT_CARD_URL, json=payload, headers=headers)

		if response.status_code == 200:
			auth_response = response.text
			if auth_response.startswith("Error"):
				return render_template('checkout_error.html', errors=[auth_response])
			else:
				auth_number = auth_response
				session['cart'] = []
				return render_template('checkout_success.html', authorization=auth_number, total=total_price)
		else:
			return render_template('checkout_error.html', errors=["Failed to connect to authorization service."])

	except Exception as e:
		return render_template('checkout_error.html', errors=[str(e)])


@app.route('/receiving', methods=['GET', 'POST'])
def update_inventory():
	if request.method == 'POST':
		part_id = request.form.get('part')
		quantity = request.form.get('quantity')
		print(part_id, quantity)
		return "Inventory updated successfully!"
	return render_template('receiving.html')


@app.route('/authorization_failed')
def authorization_failed():
	return 0

@app.route('/authorization_successful')
def authorization_successful():
	return 1


if __name__ == '__main__':
	app.run(debug=True)
