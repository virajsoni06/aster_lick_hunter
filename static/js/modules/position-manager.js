// Position Manager Module
window.DashboardModules = window.DashboardModules || {};

window.DashboardModules.PositionManager = (function() {
    const ApiClient = window.DashboardModules.ApiClient;
    const TableBuilder = window.DashboardModules.TableBuilder;
    const UIComponents = window.DashboardModules.UIComponents;

    // Private variables
    let dashboardReference = null;

    // Private functions
    function loadPositionsPrivate() {
        return ApiClient.loadPositions().then(function(response) {
            const positions = response.data;

            const tbody = document.getElementById('positions-tbody');
            if (!tbody) return;

            tbody.innerHTML = '';

            if (positions.length === 0) {
                document.getElementById('no-positions').style.display = 'block';
                document.getElementById('positions-table').style.display = 'none';
            } else {
                document.getElementById('no-positions').style.display = 'none';
                document.getElementById('positions-table').style.display = 'table';

                positions.forEach(function(pos) {
                    const row = TableBuilder.createPositionRow(pos);
                    tbody.appendChild(row);
                });
            }
        }).catch(function(error) {
            console.error('Error loading positions:', error);
        });
    }

    function showPositionDetailsPrivate(symbol, side) {
        ApiClient.getPositionDetails(symbol, side).then(function(response) {
            const position = response.data;

            // Debug logging
            console.log('Position details response:', position);
            console.log('Tranches:', position.tranches);
            console.log('Order relationships:', position.order_relationships ? position.order_relationships.length : 0);

            const modal = document.getElementById('position-modal');
            const modalBody = document.getElementById('position-modal-body');

            // Build detailed HTML
            let html = `
                <div class="position-details">
                    <h4>Position Summary - ${symbol} ${side}</h4>
                    <div class="summary-grid">
                        <div class="summary-item">
                            <span class="label">Total Quantity:</span>
                            <span class="value">${position.summary.total_quantity.toFixed(4)}</span>
                        </div>
                        <div class="summary-item">
                            <span class="label">Avg Entry Price:</span>
                            <span class="value">$${position.summary.avg_entry_price.toFixed(4)}</span>
                        </div>
                        <div class="summary-item">
                            <span class="label">Unrealized PNL:</span>
                            <span class="value ${position.summary.unrealized_pnl >= 0 ? 'positive' : 'negative'}">
                                ${window.DashboardModules.Utils.formatCurrency(position.summary.unrealized_pnl)}
                            </span>
                        </div>
                        <div class="summary-item">
                            <span class="label">Total Margin:</span>
                            <span class="value">${window.DashboardModules.Utils.formatCurrency(position.summary.total_margin)}</span>
                        </div>
                        <div class="summary-item">
                            <span class="label">Tranches:</span>
                            <span class="value">${position.summary.num_tranches}</span>
                        </div>
                    </div>
            `;

            // Prioritize showing actual tranches over order relationships
            if (position.tranches && position.tranches.length > 0) {
                html += `
                    <h4>Tranches Breakdown</h4>
                    <div class="table-container">
                        <table class="tranches-table">
                            <thead>
                                <tr>
                                    <th>Tranche ID</th>
                                    <th>Entry Price</th>
                                    <th>Quantity</th>
                                    <th>PNL</th>
                                    <th>TP Order</th>
                                    <th>SL Order</th>
                                    <th>Created</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                position.tranches.forEach(function(tranche) {
                    const tpStatus = position.order_statuses && tranche.tp_order_id ? position.order_statuses[tranche.tp_order_id] : null;
                    const slStatus = position.order_statuses && tranche.sl_order_id ? position.order_statuses[tranche.sl_order_id] : null;
                    const pnl = tranche.unrealized_pnl || 0;
                    const pnlClass = pnl >= 0 ? 'profit' : 'loss';

                    html += `
                        <tr>
                            <td>${tranche.tranche_id || 0}</td>
                            <td>$${parseFloat(tranche.avg_entry_price || 0).toFixed(4)}</td>
                            <td>${parseFloat(tranche.total_quantity || 0).toFixed(4)}</td>
                            <td class="${pnlClass}">$${pnl.toFixed(2)}</td>
                            <td>
                                ${tranche.tp_order_id ? `
                                    <span class="order-status ${tpStatus?.status?.toLowerCase() || 'pending'}">
                                        ${tpStatus?.status || 'PENDING'}
                                    </span>
                                ` : 'None'}
                            </td>
                            <td>
                                ${tranche.sl_order_id ? `
                                    <span class="order-status ${slStatus?.status?.toLowerCase() || 'pending'}">
                                        ${slStatus?.status || 'PENDING'}
                                    </span>
                                ` : 'None'}
                            </td>
                            <td>${tranche.created_at ? window.DashboardModules.Utils.formatTime(tranche.created_at) : 'N/A'}</td>
                        </tr>
                    `;
                });

                html += `
                            </tbody>
                        </table>
                    </div>
                `;
            } else if (position.order_relationships && position.order_relationships.length > 0) {
                // Fallback to order relationships if no tranches
                html += `
                    <h4>Order Groups</h4>
                    <div class="table-container">
                        <table class="tranches-table">
                            <thead>
                                <tr>
                                    <th>Tranche</th>
                                    <th>Main Order</th>
                                    <th>TP Order</th>
                                    <th>SL Order</th>
                                    <th>Created</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                position.order_relationships.forEach(function(rel) {
                    const mainStatus = position.order_statuses && rel.main_order_id ? position.order_statuses[rel.main_order_id] : null;
                    const tpStatus = position.order_statuses && rel.tp_order_id ? position.order_statuses[rel.tp_order_id] : null;
                    const slStatus = position.order_statuses && rel.sl_order_id ? position.order_statuses[rel.sl_order_id] : null;

                    html += `
                        <tr>
                            <td>${rel.tranche_id || 0}</td>
                            <td class="order-id">
                                ${rel.main_order_id ? `
                                    ${rel.main_order_id.substring(0, 8)}...
                                    <span class="order-status ${mainStatus?.status?.toLowerCase() || 'unknown'}">
                                        ${mainStatus?.status || 'N/A'}
                                    </span>
                                ` : 'N/A'}
                            </td>
                            <td>
                                ${rel.tp_order_id ? `
                                    ${rel.tp_order_id.substring(0, 8)}...
                                    <span class="order-status ${tpStatus?.status?.toLowerCase() || 'pending'}">
                                        ${tpStatus?.status || 'PENDING'}
                                    </span>
                                ` : 'None'}
                            </td>
                            <td>
                                ${rel.sl_order_id ? `
                                    ${rel.sl_order_id.substring(0, 8)}...
                                    <span class="order-status ${slStatus?.status?.toLowerCase() || 'pending'}">
                                        ${slStatus?.status || 'PENDING'}
                                    </span>
                                ` : 'None'}
                            </td>
                            <td>${rel.created_at ? window.DashboardModules.Utils.formatTime(rel.created_at) : 'N/A'}</td>
                        </tr>
                    `;
                });

                html += `
                            </tbody>
                        </table>
                    </div>
                `;
            }

            // Add active orders
            const activeOrders = position.order_relationships ? position.order_relationships.filter(function(rel) {
                const tpStatus = position.order_statuses ? position.order_statuses[rel.tp_order_id] : null;
                const slStatus = position.order_statuses ? position.order_statuses[rel.sl_order_id] : null;
                return (tpStatus && tpStatus.status === 'NEW') || (slStatus && slStatus.status === 'NEW');
            }) : [];

            if (activeOrders.length > 0) {
                html += `
                    <h4>Active TP/SL Orders</h4>
                    <div class="table-container">
                        <table class="orders-table">
                            <thead>
                                <tr>
                                    <th>Type</th>
                                    <th>Order ID</th>
                                    <th>Price</th>
                                    <th>Quantity</th>
                                    <th>Status</th>
                                    <th>Tranche</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                activeOrders.forEach(function(rel) {
                    if (rel.tp_order_id && position.order_statuses[rel.tp_order_id]) {
                        const order = position.order_statuses[rel.tp_order_id];
                        html += `
                            <tr>
                                <td class="order-type-tp">TP</td>
                                <td class="order-id">${rel.tp_order_id}</td>
                                <td>$${parseFloat(order.price || 0).toFixed(4)}</td>
                                <td>${parseFloat(order.quantity || 0).toFixed(4)}</td>
                                <td><span class="order-status ${order.status.toLowerCase()}">${order.status}</span></td>
                                <td>${rel.tranche_id}</td>
                            </tr>
                        `;
                    }
                    if (rel.sl_order_id && position.order_statuses[rel.sl_order_id]) {
                        const order = position.order_statuses[rel.sl_order_id];
                        html += `
                            <tr>
                                <td class="order-type-sl">SL</td>
                                <td class="order-id">${rel.sl_order_id}</td>
                                <td>$${parseFloat(order.price || 0).toFixed(4)}</td>
                                <td>${parseFloat(order.quantity || 0).toFixed(4)}</td>
                                <td><span class="order-status ${order.status.toLowerCase()}">${order.status}</span></td>
                                <td>${rel.tranche_id}</td>
                            </tr>
                        `;
                    }
                });

                html += `
                            </tbody>
                        </table>
                    </div>
                `;
            }

            // Add recent trades
            if (position.trades && position.trades.length > 0) {
                const recentTrades = position.trades.slice(0, 20);
                html += `
                    <h4>Recent Trades (Last 20)</h4>
                    <div class="table-container">
                        <table class="trades-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Type</th>
                                    <th>Side</th>
                                    <th>Price</th>
                                    <th>Qty</th>
                                    <th>Status</th>
                                    <th>PNL</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                recentTrades.forEach(function(trade) {
                    const pnl = trade.realized_pnl || 0;
                    html += `
                        <tr>
                            <td>${window.DashboardModules.Utils.formatTime(trade.timestamp)}</td>
                            <td>${trade.trade_category}</td>
                            <td class="${trade.side === 'BUY' ? 'position-long' : 'position-short'}">${trade.side}</td>
                            <td>$${parseFloat(trade.price).toFixed(4)}</td>
                            <td>${parseFloat(trade.qty).toFixed(4)}</td>
                            <td><span class="status-${trade.status.toLowerCase()}">${trade.status}</span></td>
                            <td class="${pnl >= 0 ? 'positive' : 'negative'}">
                                ${pnl !== 0 ? window.DashboardModules.Utils.formatCurrency(pnl) : '-'}
                            </td>
                        </tr>
                    `;
                });

                html += `
                            </tbody>
                        </table>
                    </div>
                `;
            }

            html += '</div>';

            modalBody.innerHTML = html;
            modal.style.display = 'block';

            // Setup close handlers
            const closeBtn = modal.querySelector('.modal-close');
            closeBtn.onclick = function() { modal.style.display = 'none'; };

            // Close on outside click
            window.onclick = function(event) {
                if (event.target === modal) {
                    modal.style.display = 'none';
                }
            };

        }).catch(function(error) {
            console.error('Error loading position details:', error);
            UIComponents.showToast('Error loading position details', 'error');
        });
    }

    function closePositionPrivate(symbol, side) {
        const dashboard = dashboardReference;
        if (dashboard) {
            dashboard.showClosePositionModal(symbol, side);
        }
    }

    // Public API
    return {
        loadPositions: loadPositionsPrivate,
        showPositionDetails: showPositionDetailsPrivate,
        closePosition: closePositionPrivate,
        setDashboard: function(dashboard) {
            dashboardReference = dashboard;
        }
    };
})();
