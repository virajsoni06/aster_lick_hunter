// Trade Manager Module
window.DashboardModules = window.DashboardModules || {};

window.DashboardModules.TradeManager = (function() {
    const ApiClient = window.DashboardModules.ApiClient;
    const TableBuilder = window.DashboardModules.TableBuilder;
    const UIComponents = window.DashboardModules.UIComponents;

    // Private variables
    let dashboardReference = null;

    // Private functions
    function loadTradesPrivate() {
        return ApiClient.loadTrades().then(function(response) {
            const trades = response.data;

            const tbody = document.getElementById('trades-tbody');
            tbody.innerHTML = '';

            trades.forEach(function(trade) {
                const row = TableBuilder.createTradeRow(trade);
                tbody.appendChild(row);
            });
        }).catch(function(error) {
            console.error('Error loading trades:', error);
        });
    }

    function addTradeRowPrivate(trade) {
        const tbody = document.getElementById('trades-tbody');
        const row = TableBuilder.createTradeRow(trade);

        // Add to top of table
        tbody.insertBefore(row, tbody.firstChild);

        // Remove last row if too many
        if (tbody.children.length > 20) {
            tbody.removeChild(tbody.lastChild);
        }
    }

    function showTradeDetailsPrivate(tradeId) {
        ApiClient.getTradeDetails(tradeId).then(function(response) {
            const trade = response.data;

            const modal = document.getElementById('trade-modal');
            const modalBody = document.getElementById('trade-modal-body');

            const Utils = window.DashboardModules.Utils;

            // Build detailed HTML
            let html = `
                <div class="trade-details">
                    <div class="trade-info">
                        <h4>Trade Information</h4>
                        <div class="info-grid">
                            <div class="info-item">
                                <label>Symbol:</label>
                                <span>${trade.symbol}</span>
                            </div>
                            <div class="info-item">
                                <label>Side:</label>
                                <span class="${trade.side === 'BUY' ? 'position-long' : 'position-short'}">${trade.side}</span>
                            </div>
                            <div class="info-item">
                                <label>Quantity:</label>
                                <span>${parseFloat(trade.qty).toFixed(4)}</span>
                            </div>
                            <div class="info-item">
                                <label>Price:</label>
                                <span>$${parseFloat(trade.price).toFixed(4)}</span>
                            </div>
                            <div class="info-item">
                                <label>Status:</label>
                                <span>${trade.status}</span>
                            </div>
                            <div class="info-item">
                                <label>Time:</label>
                                <span>${Utils.formatTime(trade.timestamp)}</span>
                            </div>
                        </div>
                    </div>

                    <div class="pnl-breakdown">
                        <h4>PnL Breakdown</h4>
                        <div class="pnl-grid">
                            <div class="pnl-item">
                                <label>Realized PnL:</label>
                                <span class="${trade.pnl_breakdown?.realized_pnl >= 0 ? 'positive' : 'negative'}">
                                    ${Utils.formatCurrency(trade.pnl_breakdown?.realized_pnl || 0)}
                                </span>
                            </div>
                            <div class="pnl-item">
                                <label>Commission:</label>
                                <span class="negative">${Utils.formatCurrency(trade.pnl_breakdown?.commission || 0)}</span>
                            </div>
                            <div class="pnl-item">
                                <label>Funding Fee:</label>
                                <span class="${trade.pnl_breakdown?.funding_fee >= 0 ? 'positive' : 'negative'}">
                                    ${Utils.formatCurrency(trade.pnl_breakdown?.funding_fee || 0)}
                                </span>
                            </div>
                            <div class="pnl-item">
                                <label>Total PnL:</label>
                                <span class="${trade.pnl_breakdown?.total_pnl >= 0 ? 'positive' : 'negative'}">
                                    ${Utils.formatCurrency(trade.pnl_breakdown?.total_pnl || 0)}
                                </span>
                            </div>
                        </div>
                    </div>
            `;

            // Add related trades if any
            if (trade.related_trades && trade.related_trades.length > 0) {
                html += `
                    <div class="related-trades">
                        <h4>Related Orders (TP/SL)</h4>
                        <table class="related-trades-table">
                            <thead>
                                <tr>
                                    <th>Type</th>
                                    <th>Side</th>
                                    <th>Quantity</th>
                                    <th>Price</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                trade.related_trades.forEach(function(rt) {
                    html += `
                        <tr>
                            <td>${rt.order_type || 'LIMIT'}</td>
                            <td>${rt.side}</td>
                            <td>${parseFloat(rt.qty).toFixed(4)}</td>
                            <td>$${parseFloat(rt.price).toFixed(4)}</td>
                            <td>${rt.status}</td>
                        </tr>
                    `;
                });

                html += `
                            </tbody>
                        </table>
                    </div>
                `;
            }

            // Add income details if available
            if (trade.pnl_breakdown?.details && trade.pnl_breakdown.details.length > 0) {
                html += `
                    <div class="income-details">
                        <h4>Income History</h4>
                        <table class="income-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Type</th>
                                    <th>Amount</th>
                                </tr>
                            </thead>
                            <tbody>
                `;

                trade.pnl_breakdown.details.forEach(function(detail) {
                    const amountClass = detail.income >= 0 ? 'positive' : 'negative';
                    html += `
                        <tr>
                            <td>${Utils.formatTime(detail.timestamp)}</td>
                            <td>${detail.income_type}</td>
                            <td class="${amountClass}">${Utils.formatCurrency(detail.income)}</td>
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
            console.error('Error loading trade details:', error);
            UIComponents.showToast('Error loading trade details', 'error');
        });
    }

    // Public API
    return {
        loadTrades: loadTradesPrivate,
        addTradeRow: addTradeRowPrivate,
        showTradeDetails: showTradeDetailsPrivate,
        setDashboard: function(dashboard) {
            dashboardReference = dashboard;
        }
    };
})();
