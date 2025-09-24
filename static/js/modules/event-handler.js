// Event Handler Module - SSE and Real-time Events
window.DashboardModules = window.DashboardModules || {};

window.DashboardModules.EventHandler = (function() {
    const UIComponents = window.DashboardModules.UIComponents;

    // Private variables
    let eventSource = null;
    let dashboardReference = null;

    // Private functions
    function connectSSEPrivate() {
        eventSource = new EventSource('/api/stream');

        eventSource.onopen = function() {
            updateConnectionStatusPrivate('connected');
        };

        eventSource.onerror = function() {
            updateConnectionStatusPrivate('error');
        };

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            handleRealtimeEventPrivate(data);
        };
    }

    function handleRealtimeEventPrivate(event) {
        const dashboard = dashboardReference;
        if (!dashboard) return;

        switch(event.type) {
            case 'new_liquidation':
                dashboard.addLiquidationRow(event.data);
                const usdtValue = event.data.usdt_value ? `$${parseFloat(event.data.usdt_value).toLocaleString()}` : 'N/A';
                UIComponents.showToast(`New liquidation: ${event.data.symbol} - ${usdtValue}`, 'info');
                break;
            case 'new_trade':
                dashboard.addTradeRow(event.data);
                UIComponents.showToast(`Trade executed: ${event.data.symbol}`, 'success');
                break;
            case 'config_updated':
                UIComponents.showToast(event.data.message, 'success');
                break;
            case 'symbol_added':
                UIComponents.showToast(event.data.message, 'success');
                dashboard.loadConfig(); // Reload config to update selectors
                break;
            case 'symbol_removed':
                UIComponents.showToast(event.data.message, 'warning');
                dashboard.loadConfig(); // Reload config to update selectors
                break;
            case 'pnl_sync_started':
                UIComponents.showSyncIndicator();
                break;
            case 'pnl_sync_completed':
                UIComponents.hideSyncIndicator();
                window.DashboardModules.Utils.updateLastUpdated();
                break;
            case 'pnl_updated':
                UIComponents.showToast(event.data.message, 'info');
                // Reload PNL data and trades with updated PNL
                dashboard.loadPNLData();
                dashboard.loadTrades();
                break;
            case 'trade_pnl_synced':
                // Refresh trades to show updated PNL
                dashboard.loadTrades();
                // Also update PNL summary
                dashboard.loadPNLData();
                break;
            case 'heartbeat':
                // Keep connection alive
                break;
        }
    }

    function updateConnectionStatusPrivate(status) {
        window.DashboardModules.Utils.updateConnectionStatus(status);
    }

    // Public API
    return {
        connectSSE: connectSSEPrivate,
        disconnectSSE: function() {
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
        },
        setDashboard: function(dashboard) {
            dashboardReference = dashboard;
        }
    };
})();
