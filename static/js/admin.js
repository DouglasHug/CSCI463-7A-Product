document.addEventListener('DOMContentLoaded', function() {
    // Load initial data
    loadShippingBrackets();
    loadOrders();

    // Add event listeners
    document.getElementById('addBracketForm').addEventListener('submit', handleAddBracket);
    document.getElementById('searchOrdersForm').addEventListener('submit', handleSearchOrders);
});

// ============= Shipping Brackets Functions =============
async function loadShippingBrackets() {
    try {
        const response = await fetch('/admin/api/admin/shipping-brackets');
        if (!response.ok) throw new Error('Failed to load shipping brackets');
        const brackets = await response.json();
        displayShippingBrackets(brackets);
    } catch (error) {
        console.error('Error loading shipping brackets:', error);
        alert('Failed to load shipping brackets. Please try again.');
    }
}

function displayShippingBrackets(brackets) {
    const tableBody = document.getElementById('shippingBracketsTable').getElementsByTagName('tbody')[0];
    tableBody.innerHTML = '';
    
    brackets.forEach(bracket => {
        const row = tableBody.insertRow();
        row.innerHTML = `
            <td>${bracket.minimumweight} - ${bracket.maximumweight} lbs</td>
            <td>$${bracket.costofbracket.toFixed(2)}</td>
            <td>
                <button onclick="deleteBracket(${bracket.bracketid})" class="delete-btn">Delete</button>
            </td>
        `;
    });
}

async function handleAddBracket(event) {
    event.preventDefault();
    
    const data = {
        minimumWeight: parseFloat(document.getElementById('minWeight').value),
        maximumWeight: parseFloat(document.getElementById('maxWeight').value),
        costOfBracket: parseFloat(document.getElementById('cost').value)
    };

    try {
        const response = await fetch('/admin/api/admin/shipping-brackets', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to add shipping bracket');
        }
        
        // Reset form and reload brackets
        event.target.reset();
        loadShippingBrackets();
        alert('Shipping bracket added successfully!');
    } catch (error) {
        console.error('Error adding shipping bracket:', error);
        alert(error.message || 'Failed to add shipping bracket. Please try again.');
    }
}

async function deleteBracket(bracketId) {
    if (!confirm('Are you sure you want to delete this shipping bracket?')) {
        return;
    }

    try {
        const response = await fetch(`/admin/api/admin/shipping-brackets/${bracketId}`, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error('Failed to delete shipping bracket');
        
        loadShippingBrackets();
        alert('Shipping bracket deleted successfully!');
    } catch (error) {
        console.error('Error deleting shipping bracket:', error);
        alert('Failed to delete shipping bracket. Please try again.');
    }
}

// ============= Orders Functions =============
async function loadOrders(searchParams = '') {
    try {
        const response = await fetch(`/admin/api/admin/orders${searchParams}`);
        if (!response.ok) throw new Error('Failed to load orders');
        const orders = await response.json();
        displayOrders(orders);
    } catch (error) {
        console.error('Error loading orders:', error);
        alert('Failed to load orders. Please try again.');
    }
}

function displayOrders(orders) {
    const tableBody = document.getElementById('ordersTable').getElementsByTagName('tbody')[0];
    tableBody.innerHTML = '';
    
    orders.forEach(order => {
        const row = tableBody.insertRow();
        const orderDate = new Date(order.orderdate).toLocaleDateString();
        row.innerHTML = `
            <td>#${order.orderid}</td>
            <td>${order.customer_name}</td>
            <td>${orderDate}</td>
            <td>$${order.totalprice.toFixed(2)}</td>
            <td>${order.statusname}</td>
            <td>
                <button onclick="viewOrderDetails(${order.orderid})">View Details</button>
            </td>
        `;
    });
}

async function handleSearchOrders(event) {
    event.preventDefault();
    
    const searchParams = new URLSearchParams();
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const status = document.getElementById('orderStatus').value;
    const minPrice = document.getElementById('minPrice').value;
    const maxPrice = document.getElementById('maxPrice').value;
    
    if (startDate) searchParams.append('startDate', startDate);
    if (endDate) searchParams.append('endDate', endDate);
    if (status) searchParams.append('status', status);
    if (minPrice) searchParams.append('minPrice', minPrice);
    if (maxPrice) searchParams.append('maxPrice', maxPrice);
    
    const queryString = searchParams.toString();
    await loadOrders(queryString ? `?${queryString}` : '');
}

async function viewOrderDetails(orderId) {
    try {
        const response = await fetch(`/admin/api/admin/orders/${orderId}`);
        if (!response.ok) throw new Error('Failed to load order details');
        const order = await response.json();
        displayOrderDetails(order);
    } catch (error) {
        console.error('Error loading order details:', error);
        alert('Failed to load order details. Please try again.');
    }
}

function displayOrderDetails(order) {
    const modal = document.getElementById('orderDetailsModal');
    const content = document.getElementById('orderDetailsContent');
    
    const orderDate = new Date(order.orderdate).toLocaleString();
    const shippingDate = order.shippingdate ? new Date(order.shippingdate).toLocaleString() : 'Not shipped yet';
    
    let itemsHtml = order.items.map(item => `
        <tr>
            <td>${item.description}</td>
            <td>${item.quantity}</td>
            <td>$${item.price.toFixed(2)}</td>
            <td>$${(item.price * item.quantity).toFixed(2)}</td>
        </tr>
    `).join('');

    content.innerHTML = `
        <h2>Order #${order.orderid}</h2>
        <div class="order-details">
            <p><strong>Customer:</strong> ${order.customer_name}</p>
            <p><strong>Email:</strong> ${order.email}</p>
            <p><strong>Address:</strong> ${order.address}</p>
            <p><strong>Order Date:</strong> ${orderDate}</p>
            <p><strong>Status:</strong> ${order.statusname}</p>
            <p><strong>Total Price:</strong> $${order.totalprice.toFixed(2)}</p>
            <p><strong>Shipping Cost:</strong> $${order.shippingcost ? order.shippingcost.toFixed(2) : '0.00'}</p>
            <p><strong>Shipping Date:</strong> ${shippingDate}</p>
            ${order.authorizationnumber ? `<p><strong>Authorization Number:</strong> ${order.authorizationnumber}</p>` : ''}
        </div>
        <h3>Order Items</h3>
        <table>
            <thead>
                <tr>
                    <th>Item</th>
                    <th>Quantity</th>
                    <th>Price</th>
                    <th>Subtotal</th>
                </tr>
            </thead>
            <tbody>
                ${itemsHtml}
            </tbody>
        </table>
    `;
    
    modal.style.display = 'block';
}