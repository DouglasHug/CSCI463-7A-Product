-- Drop tables in correct order to handle foreign key constraints
DROP TABLE IF EXISTS ordersparts;
DROP TABLE IF EXISTS cart;
DROP TABLE IF EXISTS shippinghandling;
DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS parts;
DROP TABLE IF EXISTS order_status;
DROP TABLE IF EXISTS customer;