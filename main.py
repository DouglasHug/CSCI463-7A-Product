from flask import Flask, render_template, request, session, redirect, url_for, jsonify, Blueprint
import pymysql
import uuid
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
		host="testdb.cjaay8sm4j8h.us-east-2.rds.amazonaws.com",
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
	if 'cart' not in session:
		session['cart'] = []
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
   cart = session.get('cart', [])
   if not cart:
       return render_template('checkout_error.html', errors=["Your cart is empty!"])

   conn = get_new_db_connection()
   cursor = conn.cursor()

   cart_items = {}

   try:
       for item in cart:
           part_id = item['part_id']
           quantity = item['quantity']
           cart_items[part_id] = quantity

           cursor.execute("""
               SELECT quantity
               FROM inventory
               WHERE number = %s""", (part_id,))

           results = cursor.fetchone()
           if not results or results[0] < quantity:
               return render_template('checkout_error.html', errors=["Not enough inventory for part: " + part_id])

   except Exception as e:
       conn.close()
       cursor.close()
       return render_template('checkout_error.html', errors=[str(e)])

   card_number = request.form.get('card_number')
   card_name = request.form.get('card_name')
   card_exp = request.form.get('card_exp')
   total_price = float(request.form.get('total_price'))

   customer_id = session.get('customer_id')
   if not customer_id:
        name = request.form.get('name')
        email = request.form.get('email')
        address = request.form.get('address')

        if not all([name, email]):
            return render_template('checkout_error.html', errors=["Please provide oyur name and email."])
        
        try:
            cursor.execute("""
                INSERT INTO customer (name, email, address)
                VALUES (%s, %s, %s)
            """, (name, email, address))
            conn.commit()
            customer_id = cursor.lastrowid
            session['customer_id'] = customer_id
        except Exception as e:
             conn.rollback()
             return render_template('checkout_error.html', errors=["Error creating customer record: " + str(e)])

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
           try:
               auth_response = response.json()
               if 'errors' in auth_response and auth_response['errors']:
                   return render_template('checkout_error.html', errors=auth_response['errors'])
               elif 'authorization' in auth_response:
                   try:
                       conn = get_new_db_connection()
                       cursor = conn.cursor()
                       customer_id = session.get('customer_id')

                       total_weight = 0
                       for item in cart:
                           cursor.execute("""
                               SELECT weight
                               FROM parts
                               WHERE number = %s""", (item['part_id'],))
                           row = cursor.fetchone()
                           if row is None:
                                return render_template('checkout_error.html', errors=["Part not found: " + item['part_id']])
                           weight = row[0]
                           total_weight += weight * item['quantity']

                       cursor.execute("""
                           SELECT costofbracket
                           FROM shippinghandling
                           WHERE minimumweight <= %s AND maximumweight >= %s""", (total_weight, total_weight))
                       row = cursor.fetchone()
                       if row is None:
                            return render_template('checkout_error.html', errors=["No shipping cost bracket found for total weight: " + str(total_weight)])
                       shipping_cost = row[0]

                       cursor.execute("""
                           INSERT INTO orders (customerid, totalprice, statusid, authorizationnumber, weight, shippingcost)
                           VALUES (%s, %s, (SELECT statusid FROM order_status WHERE statusname = 'AUTHORIZED'), %s, %s, %s)
                           RETURNING orderid""", 
                           (customer_id, total_price, auth_response['authorization'], total_weight, shipping_cost))
                       row = cursor.fetchone()
                       if row is None:
                            return render_template('checkout_error.html', errors=["Failed to retrieve order ID after inserting order."])
                       order_id = row[0]

                       for item in cart:
                           cursor.execute("""
                               INSERT INTO ordersparts (number, orderid, quantity)
                               VALUES (%s, %s, %s)""",
                               (item['part_id'], order_id, item['quantity']))

                           cursor.execute("""
                               UPDATE inventory
                               SET quantity = quantity - %s
                               WHERE number = %s""",
                               (item['quantity'], item['part_id']))

                       conn.commit()
                       session.clear()
                       return render_template('checkout_success.html',
                                           authorization=auth_response['authorization'],
                                           total=total_price)
                   except Exception as e:
                       conn.rollback()
                       return render_template('checkout_error.html', errors=[str(e)])
                   finally:
                        cursor.close()
                        conn.close()
           except ValueError:
               auth_response = response.text
               if 'errors:' in auth_response:
                   error_section = auth_response.split('errors:')[1].strip()
                   if '[' in error_section and ']' in error_section:
                       errors = error_section.replace('[', '').replace(']', '').replace('"', '').split(',')
                       return render_template('checkout_error.html', errors=errors)

               return render_template('checkout_success.html',
                                   authorization=auth_response,
                                   total=total_price)
       else:
           return render_template('checkout_error.html',
                               errors=["Failed to connect to authorization service."])

   except Exception as e:
       return render_template('checkout_error.html', errors=[str(e)])


@app.route('/receiving', methods=['GET', 'POST'])
def update_inventory():
	if request.method == 'POST':

		quantity = int(request.form.get('quantity'))
		input_type = int(request.form.get('inputType'))

		if input_type == 0:
			part_id = int(request.form.get('part'))
			print(part_id, quantity)
			conn = get_new_db_connection()
			cursor = conn.cursor()
			cursor.execute('SELECT * FROM inventory WHERE number = %s', part_id)
			if not cursor.fetchone():
				cursor.execute('INSERT INTO inventory (number, quantity) VALUES (%s, %s)', (part_id, quantity))
				conn.commit()
				conn.close()
				return "New item added to inventory"
			cursor.execute('UPDATE inventory SET quantity = %s WHERE number = %s', (quantity, part_id))
			conn.commit()
			conn.close()
		elif input_type == 1:
			part_name = request.form.get('part')
			#print(part_name, quantity)
			conn = get_legacy_db_connection()
			cursor = conn.cursor()
			cursor.execute('SELECT number FROM parts WHERE description = %s', part_name)
			conn.close()
			parts_list = cursor.fetchall()
			if not parts_list:
				return "This part does not exist"
			part_id = int(parts_list[0][0])
			conn = get_new_db_connection()
			cursor = conn.cursor()
			cursor.execute('SELECT * FROM inventory WHERE number = %s', part_id)
			if not cursor.fetchone():
				cursor.execute('INSERT INTO inventory (number, quantity) VALUES (%s, %s)', (part_id, quantity))
				conn.commit()
				conn.close()
				return "New item added to inventory"
			cursor.execute('UPDATE inventory SET quantity = %s WHERE number = %s', (quantity, part_id))
			conn.commit()
			conn.close()
		else:
			return "Please specify whether you are entering Part ID or Part Name"

		return "Inventory updated successfully!"


	return render_template('receiving.html')


@app.route('/authorization_failed')
def authorization_failed():
	return 0

@app.route('/authorization_successful')
def authorization_successful():
	return 1

#START ADMIN PAGE (PRAD)--------------------------------------------
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')
def admin_dashboard():
    return render_template('admin/dashboard.html')

@admin_bp.route('/api/admin/shipping-brackets', methods=['GET'])
def get_shipping_brackets():
    try:
        conn = get_new_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT bracketid, minimumweight, maximumweight, costofbracket 
            FROM shippinghandling 
            ORDER BY minimumweight
        """)
        columns = [col[0] for col in cursor.description]
        brackets = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(brackets), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/api/admin/shipping-brackets', methods=['POST'])
def add_shipping_bracket():
    try:
        data = request.json
        conn = get_new_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO shippinghandling (minimumweight, maximumweight, costofbracket)
            VALUES (%s, %s, %s)
        """, (data['minimumWeight'], data['maximumWeight'], data['costOfBracket']))
        
        conn.commit()
        new_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({"id": new_id, "message": "Shipping bracket added successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/api/admin/shipping-brackets/<int:bracket_id>', methods=['DELETE'])
def delete_shipping_bracket(bracket_id):
    try:
        conn = get_new_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shippinghandling WHERE bracketid = %s", (bracket_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "Shipping bracket deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/api/admin/orders', methods=['GET'])
def get_orders():
    try:
        conn = get_new_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT o.orderid, c.name as customer_name, o.orderdate, 
                   o.totalprice, os.statusname, o.shippingdate,
                   o.authorizationnumber, o.weight, o.shippingcost
            FROM orders o
            JOIN customer c ON o.customerid = c.customerid
            JOIN order_status os ON o.statusid = os.statusid
            WHERE 1=1
        """
        params = []
        
        if request.args.get('startDate'):
            query += " AND o.orderdate >= %s"
            params.append(request.args.get('startDate'))
        
        if request.args.get('endDate'):
            query += " AND o.orderdate <= %s"
            params.append(request.args.get('endDate'))
        
        if request.args.get('status'):
            query += " AND os.statusname = %s"
            params.append(request.args.get('status'))
        
        if request.args.get('minPrice'):
            query += " AND o.totalprice >= %s"
            params.append(float(request.args.get('minPrice')))
            
        if request.args.get('maxPrice'):
            query += " AND o.totalprice <= %s"
            params.append(float(request.args.get('maxPrice')))
            
        query += " ORDER BY o.orderdate DESC"
        
        cursor.execute(query, params)
        
        columns = [col[0] for col in cursor.description]
        orders = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        for order in orders:
            if order['orderdate']:
                order['orderdate'] = order['orderdate'].isoformat()
            if order['shippingdate']:
                order['shippingdate'] = order['shippingdate'].isoformat()
        
        cursor.close()
        conn.close()
        return jsonify(orders), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/api/admin/orders/<int:order_id>', methods=['GET'])
def get_order_details(order_id):
    try:
        conn = get_new_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT o.*, c.name as customer_name, c.email, c.address, 
                   os.statusname
            FROM orders o
            JOIN customer c ON o.customerid = c.customerid
            JOIN order_status os ON o.statusid = os.statusid
            WHERE o.orderid = %s
        """, (order_id,))
        
        columns = [col[0] for col in cursor.description]
        order = dict(zip(columns, cursor.fetchone()))
        
        if not order:
            return jsonify({"error": "Order not found"}), 404
        
        cursor.execute("""
            SELECT op.*, p.description, p.price, p.weight
            FROM ordersparts op
            JOIN parts p ON op.number = p.number
            WHERE op.orderid = %s
        """, (order_id,))
        
        columns = [col[0] for col in cursor.description]
        items = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        if order['orderdate']:
            order['orderdate'] = order['orderdate'].isoformat()
        if order['shippingdate']:
            order['shippingdate'] = order['shippingdate'].isoformat()
        
        order['items'] = items
        
        cursor.close()
        conn.close()
        return jsonify(order), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
app.register_blueprint(admin_bp)

#END ADMIN PAGE--------------------------------------------

if __name__ == '__main__':
	app.run(debug=True)
