// Table Builder Module
window.DashboardModules = window.DashboardModules || {};

window.DashboardModules.TableBuilder = (function() {
    const Utils = window.DashboardModules.Utils;

    // Private variables

    // Private functions
    function createPositionRowPrivate(position) {
        const row = document.createElement('tr');
        const pnl = parseFloat(position.unrealizedPnl || 0);
        const pnlPct = position.positionValue > 0 ? (pnl / position.positionValue * 100) : 0;
        const sideClass = position.side === 'LONG' ? 'position-long' : 'position-short';

        // Calculate liquidation risk
        const liqPrice = parseFloat(position.liquidationPrice || 0);
        const markPrice = parseFloat(position.markPrice || 0);
        let liqPriceClass = '';
        let liqPriceDisplay = liqPrice > 0 ? `$${liqPrice.toFixed(4)}` : '-';

        if (liqPrice > 0 && markPrice > 0) {
            // Calculate percentage distance to liquidation
            const liqDistance = position.side === 'LONG'
                ? ((markPrice - liqPrice) / markPrice * 100)
                : ((liqPrice - markPrice) / markPrice * 100);

            // Add warning class if within 10% of liquidation
            if (liqDistance < 10) {
                liqPriceClass = 'liquidation-warning';
            } else if (liqDistance < 20) {
                liqPriceClass = 'liquidation-caution';
            }
        }

        // Format TP/SL prices with visual indicators
        const tpPrice = position.takeProfitPrice;
        const slPrice = position.stopLossPrice;

        let tpDisplay = '-';
        let slDisplay = '-';
        let tpClass = '';
        let slClass = '';

        if (tpPrice && tpPrice > 0) {
            // Calculate distance percentage to TP
            let tpDistance = 0;
            if (position.side === 'LONG') {
                tpDistance = ((tpPrice - markPrice) / markPrice * 100);
            } else if (position.side === 'SHORT') {
                tpDistance = ((markPrice - tpPrice) / markPrice * 100);
            }

            // Format display with price and percentage
            tpDisplay = `$${tpPrice.toFixed(4)} <span class="tp-distance">(${tpDistance >= 0 ? '+' : ''}${tpDistance.toFixed(2)}%)</span>`;
            tpClass = 'tp-price';

            // Check if TP is close to being hit
            if (Math.abs(tpDistance) <= 2) {
                tpClass += ' tp-near';
            }
        }

        if (slPrice && slPrice > 0) {
            // Calculate distance percentage to SL
            let slDistance = 0;
            if (position.side === 'LONG') {
                slDistance = ((markPrice - slPrice) / markPrice * 100);
            } else if (position.side === 'SHORT') {
                slDistance = ((slPrice - markPrice) / markPrice * 100);
            }

            slDisplay = `$${slPrice.toFixed(4)}`;
            slClass = 'sl-price';

            // Check if SL is close to being hit
            if (slDistance <= 2 && slDistance >= 0) {
                slClass += ' sl-near';
            }
        }

        row.innerHTML = `
            <td>${position.symbol}</td>
            <td class="${sideClass}">${position.side}</td>
            <td>${Math.abs(position.positionAmt).toFixed(4)}</td>
            <td>$${parseFloat(position.entryPrice).toFixed(4)}</td>
            <td>$${parseFloat(position.markPrice).toFixed(4)}</td>
            <td class="${liqPriceClass}">${liqPriceDisplay}</td>
            <td class="${tpClass}">${tpDisplay}</td>
            <td class="${slClass}">${slDisplay}</td>
            <td class="${pnl >= 0 ? 'positive' : 'negative'}">
                ${Utils.formatCurrency(pnl)}
            </td>
            <td class="${pnl >= 0 ? 'positive' : 'negative'}">
                ${pnlPct.toFixed(2)}%
            </td>
            <td>${Utils.formatCurrency(position.initialMargin)}</td>
            <td>${position.leverage}x</td>
            <td>
                <button class="btn btn-danger btn-small close-position-btn" data-symbol="${position.symbol}" data-side="${position.side}">
                    Close
                </button>
            </td>
        `;

        // Add click handler for close button
        const closeBtn = row.querySelector('.close-position-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', function(e) {
                e.stopPropagation(); // Prevent row click from firing
                // Trigger the close position action directly
                const symbol = e.target.dataset.symbol;
                const side = e.target.dataset.side;
                if (window.dashboard && window.dashboard.PositionManager) {
                    window.dashboard.PositionManager.closePosition(symbol, side);
                }
            });
        }

        return row;
    }

    function createTradeRowPrivate(trade) {
        const row = document.createElement('tr');
        const sideClass = trade.side === 'BUY' ? 'position-long' : 'position-short';
        const statusClass = trade.status === 'SUCCESS' ? 'badge-success' :
                           trade.status === 'SIMULATED' ? 'badge-warning' :
                           trade.status === 'NEW' ? 'badge-info' :
                           trade.status === 'CANCELED' ? 'badge-secondary' : 'badge-danger';

        // Safely parse PnL values
        const realizedPnl = parseFloat(trade.realized_pnl || 0);
        const commission = parseFloat(trade.commission || 0);
        const netPnl = parseFloat(trade.net_pnl || 0);
        const qty = parseFloat(trade.qty || 0);
        const price = parseFloat(trade.price || 0);

        // Only show PnL for completed trades
        const showPnl = trade.status === 'SUCCESS' || trade.status === 'FILLED';

        const pnlClass = realizedPnl >= 0 ? 'positive' : 'negative';
        const netPnlClass = netPnl >= 0 ? 'positive' : 'negative';

        row.innerHTML = `
            <td>${Utils.formatTime(trade.timestamp)}</td>
            <td>${trade.symbol || ''}</td>
            <td class="${sideClass}">${trade.side || ''}</td>
            <td>${!isNaN(qty) ? qty.toFixed(4) : '0.0000'}</td>
            <td>${!isNaN(price) ? '$' + price.toFixed(4) : '$0.0000'}</td>
            <td class="${showPnl ? pnlClass : ''}">${showPnl ? Utils.formatCurrency(realizedPnl) : '-'}</td>
            <td class="${showPnl ? 'negative' : ''}">${showPnl ? Utils.formatCurrency(commission) : '-'}</td>
            <td class="${showPnl ? netPnlClass : ''}">${showPnl ? Utils.formatCurrency(netPnl) : '-'}</td>
            <td><span class="badge ${statusClass}">${trade.status || 'UNKNOWN'}</span></td>
            <td>${trade.order_type || 'LIMIT'}</td>
        `;

        // Make row clickable for trade details
        row.style.cursor = 'pointer';
        row.addEventListener('click', function() {
            // This will be handled by the dashboard
        });

        return row;
    }

    function createSymbolPerformanceRowPrivate(perf) {
        const row = document.createElement('tr');
        const pnlClass = perf.total_pnl >= 0 ? 'positive' : 'negative';

        row.innerHTML = `
            <td>${perf.symbol}</td>
            <td class="${pnlClass}">${Utils.formatCurrency(perf.total_pnl)}</td>
            <td class="${perf.realized_pnl >= 0 ? 'positive' : 'negative'}">${Utils.formatCurrency(perf.realized_pnl)}</td>
            <td class="negative">${Utils.formatCurrency(perf.commissions)}</td>
            <td>${perf.total_trades}</td>
            <td class="${perf.win_rate >= 50 ? 'positive' : 'negative'}">${perf.win_rate.toFixed(1)}%</td>
        `;
        return row;
    }

    function createLiquidationRowPrivate(liquidation) {
        const row = document.createElement('tr');
        const sideClass = liquidation.side === 'BUY' ? 'position-long' : 'position-short';

        row.innerHTML = `
            <td>${Utils.formatTime(liquidation.timestamp)}</td>
            <td>${liquidation.symbol}</td>
            <td class="${sideClass}">${liquidation.side}</td>
            <td>${parseFloat(liquidation.qty).toFixed(4)}</td>
            <td>$${parseFloat(liquidation.price).toFixed(4)}</td>
            <td>${Utils.formatCurrency(liquidation.usdt_value)}</td>
        `;
        return row;
    }

    // Public API
    return {
        createPositionRow: createPositionRowPrivate,
        createTradeRow: createTradeRowPrivate,
        createSymbolPerformanceRow: createSymbolPerformanceRowPrivate,
        createLiquidationRow: createLiquidationRowPrivate
    };
})();
