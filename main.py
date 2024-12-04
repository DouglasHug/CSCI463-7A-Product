from flask import Flask, render_template, request, session, redirect, url_for, jsonify, Blueprint
import pymysql
import uuid
from flask_session import Session
import requests
import os
import glob

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
    return render_template('mainpage.html')


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
        return render_template('cart_empty.html')

    legacy_conn = get_legacy_db_connection()
    legacy_cursor = legacy_conn.cursor()

    new_conn = get_new_db_connection()
    new_cursor = new_conn.cursor()

    try:
        part_ids = [item['part_id'] for item in cart]
        format_strings = ','.join(['%s'] * len(part_ids))
        query = f"SELECT * FROM parts WHERE number IN ({format_strings})"
        legacy_cursor.execute(query, part_ids)

        parts = legacy_cursor.fetchall()

        total_price = 0
        total_weight = 0
        detailed_cart = []
        
        for item in cart:
            for part in parts:
                if part[0] == int(item['part_id']):
                    subtotal = part[2] * item['quantity']
                    item_weight = part[3] * item['quantity']
                    total_price += subtotal
                    total_weight += item_weight
                    detailed_cart.append({
                        'description': part[1],
                        'price': part[2],
                        'quantity': item['quantity'],
                        'subtotal': subtotal,
                        'weight': item_weight
                    })
                    break

        new_cursor.execute("""
            SELECT costofbracket
            FROM shippinghandling
            WHERE minimumweight <= %s AND maximumweight >= %s""", 
            (total_weight, total_weight))
        
        shipping_cost = new_cursor.fetchone()
        if not shipping_cost:
            return "Unable to calculate shipping cost for this order. Please contact support."
        
        shipping_cost = shipping_cost[0]
        final_total = total_price + shipping_cost

        session['order_shipping_cost'] = shipping_cost
        session['order_weight'] = total_weight
        session['order_subtotal'] = total_price
        session['order_total'] = final_total

        return render_template('checkout.html', 
                             cart=detailed_cart, 
                             subtotal=total_price,
                             shipping_cost=shipping_cost,
                             total=final_total,
                             weight=total_weight,
                             cartsize=len(cart))

    finally:
        legacy_cursor.close()
        legacy_conn.close()
        new_cursor.close()
        new_conn.close()


def validate_cart_inventory(cart, cursor):
    """Validates that all items in cart have sufficient inventory."""
    cart_items = {}
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
            raise ValueError(f"Not enough inventory for part: {part_id}")
    
    return cart_items

#START OF CREDIT CARD AUTHORIZATION AND INVENTORY MANAGEMENT (prad)----------------------------

def create_customer_record(cursor, name, email, address):
    """Creates a new customer record in the database."""
    if not all([name, email]):
        raise ValueError("Please provide your name and email.")
    
    cursor.execute("""
        INSERT INTO customer (name, email, address)
        VALUES (%s, %s, %s)
    """, (name, email, address))
    
    return cursor.lastrowid

def process_credit_card(total_price, card_number, card_name, card_exp):
    """Processes credit card payment through external service."""
    transaction_id = f"{uuid.uuid4()}"
    payload = {
        'vendor': VENDOR_ID,
        'trans': transaction_id,
        'cc': card_number,
        'name': card_name,
        'exp': card_exp,
        'amount': f"{total_price:.2f}"
    }
    
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    response = requests.post(CREDIT_CARD_URL, json=payload, headers=headers)
    
    if response.status_code != 200:
        raise ValueError("Failed to connect to authorization service.")
    
    return response

def calculate_shipping_cost(cart, legacy_cursor, new_cursor):
    """Calculates total weight and shipping cost for order."""
    total_weight = 0
    for item in cart:
        legacy_cursor.execute("""
            SELECT weight
            FROM parts
            WHERE number = %s""", (item['part_id'],))
        row = legacy_cursor.fetchone()
        if row is None:
            raise ValueError(f"Part not found: {item['part_id']}")
        weight = row[0]
        total_weight += weight * item['quantity']

    new_cursor.execute("""
        SELECT costofbracket
        FROM shippinghandling
        WHERE minimumweight <= %s AND maximumweight >= %s""", (total_weight, total_weight))
    row = new_cursor.fetchone()
    if row is None:
        raise ValueError(f"No shipping cost bracket found for total weight: {total_weight}")
    
    return total_weight, row[0]

def create_order_record(cursor, customer_id, total_price, authorization, total_weight, shipping_cost):
    """Creates the order record in the database."""
    cursor.execute("""
        INSERT INTO orders (customerid, totalprice, statusid, authorizationnumber, weight, shippingcost)
        VALUES (%s, %s, (SELECT statusid FROM order_status WHERE statusname = 'AUTHORIZED'), %s, %s, %s)""", 
        (customer_id, total_price, authorization, total_weight, shipping_cost))
    
    order_id = cursor.lastrowid
    if not order_id:
        raise ValueError("Failed to retrieve order ID after inserting order.")
    
    return order_id

def process_order_items(cursor, cart, order_id):
    """Processes individual items in the order and updates inventory."""
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

def clear_session_data(app, session):
    """Clears session data and removes session files."""
    session_id = session.sid
    session.clear()
    session_file_pattern = os.path.join(
        app.config['SESSION_FILE_DIR'] if 'SESSION_FILE_DIR' in app.config else './flask_session',
        f'sess_{session_id}*'
    )
    for session_file in glob.glob(session_file_pattern):
        try:
            os.remove(session_file)
        except OSError as e:
            print(f"Error deleting session file: {e}")

@app.route('/authorize_payment', methods=['POST'])
def authorize_payment():
    cart = session.get('cart', [])
    if not cart:
        return render_template('checkout_error.html', errors=["Your cart is empty!"])

    shipping_cost = session.get('order_shipping_cost')
    total_weight = session.get('order_weight')
    total_price = session.get('order_total')

    if not all([shipping_cost, total_weight, total_price]):
        return render_template('checkout_error.html', 
                             errors=["Please return to checkout to calculate shipping."])

    conn = get_new_db_connection()
    cursor = conn.cursor()

    try:
        validate_cart_inventory(cart, cursor)

        customer_id = session.get('customer_id')
        if not customer_id:
            customer_id = create_customer_record(
                cursor,
                request.form.get('name'),
                request.form.get('email'),
                request.form.get('address')
            )
            session['customer_id'] = customer_id
            conn.commit()

        response = process_credit_card(
            total_price,
            request.form.get('card_number'),
            request.form.get('card_name'),
            request.form.get('card_exp')
        )

        auth_response = response.json()
        if 'errors' in auth_response and auth_response['errors']:
            return render_template('checkout_error.html', errors=auth_response['errors'])
        
        if 'authorization' in auth_response:
            order_id = create_order_record(
                cursor,
                customer_id,
                total_price,
                auth_response['authorization'],
                total_weight,
                shipping_cost
            )

            process_order_items(cursor, cart, order_id)
            
            conn.commit()
            clear_session_data(app, session)

            subtotal = session.get('order_subtotal', total_price - shipping_cost)
            return render_template('checkout_success.html',
                               authorization=auth_response['authorization'],
                               subtotal=subtotal,
                               shipping_cost=shipping_cost,
                               total=total_price)

    except ValueError as e:
        return render_template('checkout_error.html', errors=[str(e)])
    except Exception as e:
        conn.rollback()
        return render_template('checkout_error.html', errors=["An error occurred: " + str(e)])
    finally:
        cursor.close()
        conn.close()

#END OF CREDIT CARD AUTHORIZATION AND INVENTORY MANAGEMENT ----------------------------

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
        min_weight = float(data['minimumWeight'])
        max_weight = float(data['maximumWeight'])
        cost = float(data['costOfBracket'])

        if min_weight >= max_weight:
            return jsonify({
                "error": "Minimum weight must be less than maximum weight"
            }), 400

        if min_weight < 0 or max_weight < 0 or cost < 0:
            return jsonify({
                "error": "Weights and cost must be non-negative values"
            }), 400

        conn = get_new_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT bracketid, minimumweight, maximumweight 
            FROM shippinghandling 
            WHERE (
                (%s BETWEEN minimumweight AND maximumweight) OR
                (%s BETWEEN minimumweight AND maximumweight) OR
                (minimumweight BETWEEN %s AND %s) OR
                (maximumweight BETWEEN %s AND %s)
            )
        """, (min_weight, max_weight, min_weight, max_weight, min_weight, max_weight))
        
        conflicts = cursor.fetchall()
        if conflicts:
            return jsonify({
                "error": "This weight range overlaps with existing brackets",
                "conflicts": [
                    {
                        "bracketId": row[0],
                        "minimumWeight": row[1],
                        "maximumWeight": row[2]
                    } for row in conflicts
                ]
            }), 409
        
        cursor.execute("""
            INSERT INTO shippinghandling (minimumweight, maximumweight, costofbracket)
            VALUES (%s, %s, %s)
        """, (min_weight, max_weight, cost))
        
        conn.commit()
        new_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({
            "id": new_id,
            "message": "Shipping bracket added successfully",
            "data": {
                "bracketId": new_id,
                "minimumWeight": min_weight,
                "maximumWeight": max_weight,
                "costOfBracket": cost
            }
        }), 201

    except ValueError as e:
        return jsonify({
            "error": "Invalid numeric values provided"
        }), 400
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

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
    new_conn = None
    legacy_conn = None
    try:
        new_conn = get_new_db_connection()
        new_cursor = new_conn.cursor()
        
        new_cursor.execute("""
            SELECT o.*, c.name as customer_name, c.email, c.address, 
                   os.statusname
            FROM orders o
            JOIN customer c ON o.customerid = c.customerid
            JOIN order_status os ON o.statusid = os.statusid
            WHERE o.orderid = %s
        """, (order_id,))
        
        columns = [col[0] for col in new_cursor.description]
        order_data = new_cursor.fetchone()
        
        if not order_data:
            return jsonify({"error": "Order not found"}), 404
            
        order = dict(zip(columns, order_data))

        legacy_conn = get_legacy_db_connection()
        legacy_cursor = legacy_conn.cursor()
        
        new_cursor.execute("""
            SELECT op.number, op.orderid, op.quantity
            FROM ordersparts op
            WHERE op.orderid = %s
        """, (order_id,))
        
        order_items = []
        for item in new_cursor.fetchall():
            part_number = item[0]
            quantity = item[2]
            
            legacy_cursor.execute("""
                SELECT description, price, weight
                FROM parts
                WHERE number = %s
            """, (part_number,))
            
            part_info = legacy_cursor.fetchone()
            if part_info:
                order_items.append({
                    'number': part_number,
                    'orderid': order_id,
                    'quantity': quantity,
                    'description': part_info[0],
                    'price': float(part_info[1]),
                    'weight': float(part_info[2]),
                    'subtotal': float(part_info[1]) * quantity
                })
        
        if order['orderdate']:
            order['orderdate'] = order['orderdate'].isoformat()
        if order['shippingdate']:
            order['shippingdate'] = order['shippingdate'].isoformat()
        
        order['items'] = order_items
        
        legacy_cursor.close()
        legacy_conn.close()
        new_cursor.close()
        new_conn.close()
        
        return jsonify(order), 200
        
    except Exception as e:
        print(f"Error in get_order_details: {str(e)}")
        if legacy_conn:
            legacy_conn.close()
        if new_conn:
            new_conn.close()
        return jsonify({"error": f"Failed to load order details: {str(e)}"}), 500
    
app.register_blueprint(admin_bp)

#END ADMIN PAGE--------------------------------------------

if __name__ == '__main__':
	app.run(debug=True)
