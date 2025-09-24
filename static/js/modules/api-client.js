// API Client Module
window.DashboardModules = window.DashboardModules || {};

window.DashboardModules.ApiClient = (function() {
    // Private variables

    // Private functions
    function getPrivate(endpoint) {
        return axios.get(endpoint);
    }

    function postPrivate(endpoint, data = {}) {
        return axios.post(endpoint, data);
    }

    // Public API
    return {
        // Account
        loadAccount: function() {
            return getPrivate('/api/account');
        },

        // Positions
        loadPositions: function() {
            return getPrivate('/api/positions');
        },

        closePosition: function(symbol, side) {
            return postPrivate(`/api/positions/${symbol}/${side}/close`);
        },

        getPositionDetails: function(symbol, side) {
            return getPrivate(`/api/positions/${symbol}/${side}`);
        },

        // Trades
        loadTrades: function(limit = 20) {
            return getPrivate(`/api/trades?limit=${limit}`);
        },

        getTradeDetails: function(tradeId) {
            return getPrivate(`/api/trades/${tradeId}`);
        },

        // Stats
        loadStats: function(hours = 24) {
            return getPrivate(`/api/stats?hours=${hours}`);
        },

        // Liquidations
        loadLiquidations: function(limit = 20) {
            return getPrivate(`/api/liquidations?limit=${limit}`);
        },

        // PNL
        loadPNLStats: function(days = 7) {
            return getPrivate(`/api/pnl/stats?days=${days}`);
        },

        loadSymbolPerformance: function(days = 7) {
            return getPrivate(`/api/pnl/symbols?days=${days}`);
        },

        syncPNL: function(hours = 168) {
            return postPrivate('/api/pnl/sync', { hours });
        },

        // Config
        loadConfig: function() {
            return getPrivate('/api/config');
        },

        saveConfig: function(config) {
            return postPrivate('/api/config', config);
        },

        saveSymbolConfig: function(symbol, config) {
            return postPrivate('/api/config/symbol', { symbol, config });
        },

        addSymbol: function(symbol) {
            return postPrivate('/api/config/symbol/add', { symbol });
        },

        removeSymbol: function(symbol) {
            return postPrivate('/api/config/symbol/remove', { symbol });
        },

        // Exchange
        getExchangeSymbols: function() {
            return getPrivate('/api/exchange/symbols');
        }
    };
})();
