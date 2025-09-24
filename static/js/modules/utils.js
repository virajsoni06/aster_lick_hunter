// Dashboard Utility Functions
window.DashboardModules = window.DashboardModules || {};

window.DashboardModules.Utils = (function() {
    // Private variables

    // Private functions
    function formatCurrencyPrivate(value) {
        if (value === null || value === undefined) return '$0.00';
        const num = parseFloat(value);
        return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function formatTimePrivate(timestamp) {
        const date = new Date(parseInt(timestamp));
        return date.toLocaleTimeString('en-US', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    function updateElementPrivate(id, value, compareValue = null) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;

            // Add positive/negative class if compareValue provided
            if (compareValue !== null) {
                element.classList.remove('positive', 'negative');
                if (compareValue > 0) {
                    element.classList.add('positive');
                } else if (compareValue < 0) {
                    element.classList.add('negative');
                }
            }
        }
    }

    function updateConnectionStatusPrivate(status) {
        const dot = document.querySelector('.status-dot');
        const text = document.querySelector('.status-text');

        dot.classList.remove('connected', 'error');

        if (status === 'connected') {
            dot.classList.add('connected');
            text.textContent = 'Connected';
        } else if (status === 'error') {
            dot.classList.add('error');
            text.textContent = 'Disconnected';
        } else {
            text.textContent = 'Connecting...';
        }
    }

    function updateLastUpdatedPrivate() {
        const element = document.getElementById('last-updated');
        if (element) {
            const now = new Date();
            const timeString = now.toLocaleTimeString('en-US', {
                hour12: false,
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
            element.textContent = `Last updated: ${timeString}`;
        }
    }

    // Public API
    return {
        formatCurrency: formatCurrencyPrivate,
        formatTime: formatTimePrivate,
        updateElement: updateElementPrivate,
        updateConnectionStatus: updateConnectionStatusPrivate,
        updateLastUpdated: updateLastUpdatedPrivate
    };
})();
