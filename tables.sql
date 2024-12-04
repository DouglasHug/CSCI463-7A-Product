-- customer table
CREATE TABLE customer (
    customerid INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL,
    address VARCHAR(100),
    createdat DATETIME DEFAULT CURRENT_TIMESTAMP
);

--order_status table
CREATE TABLE order_status (
    statusid INT AUTO_INCREMENT PRIMARY KEY,
    statusname VARCHAR(50) NOT NULL
);

INSERT INTO order_status (statusname) VALUES 
    ('PENDING'),
    ('AUTHORIZED'),
    ('SHIPPED'),
    ('CANCELLED');

-- orders table
CREATE TABLE orders (
    orderid INT AUTO_INCREMENT PRIMARY KEY,
    customerid INT NOT NULL,
    totalprice FLOAT NOT NULL,
    statusid INT NOT NULL, 
    weight FLOAT,
    orderdate DATETIME DEFAULT CURRENT_TIMESTAMP,
    shippingcost FLOAT,
    authorizationnumber VARCHAR(50),
    shippingdate DATETIME,
    FOREIGN KEY (customerid) REFERENCES customer(customerid),
    FOREIGN KEY (statusid) REFERENCES order_status(statusid)
);

-- parts table
CREATE TABLE parts (
    number INT AUTO_INCREMENT PRIMARY KEY,
    description VARCHAR(300),
    price FLOAT(8,2),
    weight FLOAT(4,2),
    pictureurl VARCHAR(255)
);

-- inventory table
CREATE TABLE inventory (
    number INT NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (number),
    FOREIGN KEY (number) REFERENCES parts(number)
);

-- shipping/handling table
CREATE TABLE shippinghandling (
    bracketid INT AUTO_INCREMENT PRIMARY KEY,
    minimumweight FLOAT NOT NULL,
    maximumweight FLOAT NOT NULL,
    costofbracket FLOAT NOT NULL
);

-- cart table 
CREATE TABLE cart (
    cartid INT AUTO_INCREMENT PRIMARY KEY,
    customerid INT NOT NULL,
    number INT NOT NULL,
    quantity INT NOT NULL,
    FOREIGN KEY (customerid) REFERENCES customer(customerid),
    FOREIGN KEY (number) REFERENCES parts(number)
)

-- ordersparts table
CREATE TABLE ordersparts(
    number INT NOT NULL,
    orderid INT NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (orderid, number),
    FOREIGN KEY (number) REFERENCES parts(number),
    FOREIGN KEY (orderid) REFERENCES orders(orderid)
)