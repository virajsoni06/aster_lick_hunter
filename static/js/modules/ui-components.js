// UI Components Module
window.DashboardModules = window.DashboardModules || {};

window.DashboardModules.UIComponents = (function() {
    const Utils = window.DashboardModules.Utils;

    // Private variables
    let openModal = null;

    // Private functions
    function showToastPrivate(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        toast.innerHTML = `
            <span>${message}</span>
            <span class="toast-close">✕</span>
        `;

        container.appendChild(toast);

        // Auto remove after 5 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 5000);

        // Close button
        const closeBtn = toast.querySelector('.toast-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                toast.remove();
            });
        }
    }

    function showSyncIndicatorPrivate() {
        const indicator = document.getElementById('loading-indicator');
        if (indicator) {
            indicator.style.display = 'flex';
        }
    }

    function hideSyncIndicatorPrivate() {
        const indicator = document.getElementById('loading-indicator');
        if (indicator) {
            indicator.style.display = 'none';
        }
    }

    // Modal management
    function showModalPrivate(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'block';
            openModal = modal;

            // Setup close handlers
            const closeBtn = modal.querySelector('.modal-close');
            if (closeBtn) {
                closeBtn.onclick = () => hideModalPrivate();

                // Also handle outside click to close
                modal.onclick = (event) => {
                    if (event.target === modal) {
                        hideModalPrivate();
                    }
                };
            }
        }
    }

    function hideModalPrivate() {
        if (openModal) {
            openModal.style.display = 'none';
            openModal = null;
        }
    }

    function createSymbolCardPrivate(symbolInfo, isConfigured) {
        const card = document.createElement('div');
        card.className = `symbol-card ${isConfigured ? 'configured' : ''}`;
        card.dataset.symbol = symbolInfo.symbol;

        card.innerHTML = `
            <div>
                <div class="symbol-name">${symbolInfo.symbol}</div>
                <div class="symbol-base">${symbolInfo.baseAsset}</div>
            </div>
            <div class="symbol-actions">
                ${isConfigured ?
                    '<span class="btn-small btn-configured">Configured</span>' :
                    `<button class="btn-small btn-add" onclick="dashboard.addSymbol('${symbolInfo.symbol}')">Add</button>`
                }
            </div>
        `;

        return card;
    }

    // Public API
    return {
        showToast: showToastPrivate,
        showSyncIndicator: showSyncIndicatorPrivate,
        hideSyncIndicator: hideSyncIndicatorPrivate,
        showModal: showModalPrivate,
        hideModal: hideModalPrivate,
        createSymbolCard: createSymbolCardPrivate
    };
})();
