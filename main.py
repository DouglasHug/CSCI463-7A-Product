import mariadb
import pymysql

from flask import Flask, render_template, request, redirect

app = Flask(__name__)


def get_legacy_db_connection():
	conn = pymysql.connect(
		host="blitz.cs.niu.edu",
		user="student",
		password="student",
		database="csci467"
	)
	return conn


def get_new_db_connection():
	conn = mariadb.connect(
		host="",
		user="",
		password="",
		database=""
	)
	return conn


@app.route('/')
def index():
	return "Placeholder"


@app.route('/browse')
def browse_catalog():
	conn = get_legacy_db_connection()
	cursor = conn.cursor()
	cursor.execute('SELECT * FROM parts')

	columns = [col[0] for col in cursor.description]
	parts = [dict(zip(columns, row)) for row in cursor.fetchall()]
	conn.close()

	return render_template('browse.html', parts=parts)


@app.route('/checkout')
def checkout():
	return "Placeholder"


if __name__ == '__main__':
	app.run(debug=True)