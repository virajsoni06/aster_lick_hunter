// Refactored Dashboard - Main Orchestrator
// Uses modular architecture with separate concerns
window.DashboardModules = window.DashboardModules || {};

class Dashboard {
    constructor() {
        // Initialize references to modules
        this.Utils = window.DashboardModules.Utils;
        this.ApiClient = window.DashboardModules.ApiClient;
        this.UIComponents = window.DashboardModules.UIComponents;
        this.TableBuilder = window.DashboardModules.TableBuilder;
        this.PositionManager = window.DashboardModules.PositionManager;
        this.TradeManager = window.DashboardModules.TradeManager;
        this.EventHandler = window.DashboardModules.EventHandler;
        this.ChartManager = window.DashboardModules.ChartManager;

        // Set up module references to this dashboard
        this.PositionManager.setDashboard(this);
        this.TradeManager.setDashboard(this);
        this.EventHandler.setDashboard(this);

        // Core state
        this.currentConfig = null;
        this.refreshInterval = null;
        this.walletBalance = 0;
        this.availableBalance = 0;
        this.minNotionalIssues = [];

        this.init();
    }

    async init() {
        // Initialize event listeners
        this.setupEventListeners();

        // Initialize SSE connection
        this.EventHandler.connectSSE();

        // Load initial data
        await this.loadAllData();

        // Set up refresh interval (every 5 seconds)
        this.refreshInterval = setInterval(() => this.refreshData(), 5000);

        // Initialize charts
        this.ChartManager.initCharts();

        // Load PNL data
        await this.loadPNLData();
    }

    setupEventListeners() {
        // Refresh button
        document.getElementById('refresh-btn').addEventListener('click', () => this.loadAllData());

        // Config tabs
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchTab(e.target));
        });

        // Save config button
        document.getElementById('save-config-btn').addEventListener('click', () => this.saveConfig());

        // Symbol selector
        document.getElementById('symbol-selector').addEventListener('change', (e) => {
            this.loadSymbolConfig(e.target.value);
        });

        // Symbol management
        document.getElementById('fetch-symbols-btn').addEventListener('click', () => this.fetchAvailableSymbols());
        document.getElementById('remove-symbol-btn').addEventListener('click', () => this.removeSymbol());
        document.getElementById('symbol-search').addEventListener('input', (e) => this.filterSymbols(e.target.value));

        // Settings button
        document.getElementById('settings-btn').addEventListener('click', () => this.openSettingsModal());

        // Position close handlers - this will be called from table builder
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('close-position-btn')) {
                const symbol = e.target.dataset.symbol;
                const side = e.target.dataset.side;
                this.PositionManager.closePosition(symbol, side);
            }
        });

        // Trade row clicks - handled by table builder
        document.addEventListener('click', (e) => {
            if (e.target.closest('tr[data-trade-id]')) {
                const tradeId = e.target.closest('tr').dataset.tradeId;
                this.TradeManager.showTradeDetails(tradeId);
            }
        });

        // Position row clicks
        document.addEventListener('click', (e) => {
            if (e.target.closest('.positions-table tr') && !e.target.classList.contains('close-position-btn')) {
                const row = e.target.closest('tr');
                const symbol = row.children[0]?.textContent;
                const sideCell = row.children[1]?.textContent;
                if (symbol && sideCell) {
                    const side = sideCell.trim();
                    this.PositionManager.showPositionDetails(symbol, side);
                }
            }
        });
    }

    async loadAllData() {
        try {
            // Load account first to get wallet balance
            await this.loadAccount();

            // Then load other data in parallel
            await Promise.all([
                this.PositionManager.loadPositions(),
                this.loadStats(),
                this.loadLiquidations(),
                this.TradeManager.loadTrades(),
                this.loadConfig()
            ]);
        } catch (error) {
            console.error('Error loading data:', error);
            this.UIComponents.showToast('Error loading data', 'error');
        }
    }

    async refreshData() {
        try {
            // Load account first to get wallet balance
            await this.loadAccount();

            // Then load positions and pnl data
            await Promise.all([
                this.PositionManager.loadPositions(),
                this.loadStats()
            ]);
        } catch (error) {
            console.error('Error refreshing data:', error);
        }
    }

    async loadAccount() {
        try {
            const response = await this.ApiClient.loadAccount();
            const data = response.data;

            if (data.error) {
                console.error('Account error:', data.error);
                return;
            }

            // Store wallet and available balance for PNL percentage calculation
            this.walletBalance = parseFloat(data.totalWalletBalance) || 0;
            this.availableBalance = parseFloat(data.availableBalance) || 0;

            // Update account display
            this.Utils.updateElement('wallet-balance', this.Utils.formatCurrency(data.totalWalletBalance));
            this.Utils.updateElement('unrealized-pnl', this.Utils.formatCurrency(data.totalUnrealizedProfit), data.totalUnrealizedProfit);
            this.Utils.updateElement('margin-used', this.Utils.formatCurrency(data.totalPositionInitialMargin));
            this.Utils.updateElement('available-balance', this.Utils.formatCurrency(data.availableBalance));
        } catch (error) {
            console.error('Error loading account:', error);
        }
    }

    async loadStats() {
        try {
            const response = await this.ApiClient.loadStats();
            const stats = response.data;

            // Update trading stats
            this.Utils.updateElement('total-trades', stats.trades.total_trades);
            this.Utils.updateElement('success-rate', stats.trades.success_rate.toFixed(1) + '%');
            this.Utils.updateElement('liquidations-count', stats.liquidations.total_liquidations);
            this.Utils.updateElement('volume-processed', this.Utils.formatCurrency(stats.liquidations.total_liquidation_volume));

            // Update volume chart
            if (this.ChartManager.getVolumeChart() && stats.hourly_volume) {
                this.ChartManager.updateVolumeChart(stats.hourly_volume);
            }
        } catch (error) {
            console.error('Error loading stats:', error);
        }
    }

    async loadLiquidations() {
        try {
            const response = await this.ApiClient.loadLiquidations();
            const liquidations = response.data;

            const tbody = document.getElementById('liquidations-tbody');
            if (!tbody) {
                console.warn('Liquidations table body not found');
                return;
            }

            tbody.innerHTML = '';

            liquidations.forEach(liq => {
                const row = this.TableBuilder.createLiquidationRow(liq);
                tbody.appendChild(row);
            });
        } catch (error) {
            console.error('Error loading liquidations:', error);
        }
    }

    addLiquidationRow(liquidation) {
        const tbody = document.getElementById('liquidations-tbody');
        if (!tbody) {
            console.warn('Liquidations table body not found');
            return;
        }

        const row = this.TableBuilder.createLiquidationRow(liquidation);

        // Add to top of table
        tbody.insertBefore(row, tbody.firstChild);

        // Remove last row if too many
        if (tbody.children.length > 20) {
            tbody.removeChild(tbody.lastChild);
        }
    }

    async loadConfig() {
        try {
            const response = await this.ApiClient.loadConfig();
            this.currentConfig = response.data;

            // Load global config
            if (this.currentConfig.globals) {
                Object.keys(this.currentConfig.globals).forEach(key => {
                    const element = document.getElementById(key);
                    if (element) {
                        element.value = this.currentConfig.globals[key];
                    }
                });
            }

            // Populate symbol selector
            const selector = document.getElementById('symbol-selector');
            selector.innerHTML = '';

            if (this.currentConfig.symbols) {
                Object.keys(this.currentConfig.symbols).forEach(symbol => {
                    const option = document.createElement('option');
                    option.value = symbol;
                    option.textContent = symbol;
                    selector.appendChild(option);
                });

                // Load first symbol config
                if (selector.options.length > 0) {
                    this.loadSymbolConfig(selector.options[0].value);
                }
            }
        } catch (error) {
            console.error('Error loading config:', error);
            this.UIComponents.showToast('Error loading configuration', 'error');
        }
    }

    // Config methods
    loadSymbolConfig(symbol) {
        const config = this.currentConfig.symbols[symbol];
        const container = document.getElementById('symbol-config');

        if (!config) return;

        container.innerHTML = '';

        // Create input fields for each config option
        const configFields = [
            { key: 'volume_threshold_long', label: 'Volume Threshold (Long)', type: 'number', step: '0.01' },
            { key: 'volume_threshold_short', label: 'Volume Threshold (Short)', type: 'number', step: '0.01' },
            { key: 'leverage', label: 'Leverage', type: 'number', step: '1' },
            { key: 'margin_type', label: 'Margin Type', type: 'select', options: ['ISOLATED', 'CROSSED'] },
            { key: 'trade_side', label: 'Trade Side', type: 'select', options: ['OPPOSITE', 'SAME'] },
            { key: 'trade_value_usdt', label: 'Trade Value (USDT)', type: 'number', step: '0.01' },
            { key: 'price_offset_pct', label: 'Price Offset %', type: 'number', step: '0.01' },
            { key: 'max_position_usdt', label: 'Max Position (USDT)', type: 'number', step: '0.01' },
            { key: 'take_profit_enabled', label: 'Take Profit Enabled', type: 'select', options: ['true', 'false'] },
            { key: 'take_profit_pct', label: 'Take Profit %', type: 'number', step: '0.01' },
            { key: 'stop_loss_enabled', label: 'Stop Loss Enabled', type: 'select', options: ['true', 'false'] },
            { key: 'stop_loss_pct', label: 'Stop Loss %', type: 'number', step: '0.01' },
            { key: 'working_type', label: 'Working Type', type: 'select', options: ['CONTRACT_PRICE', 'MARK_PRICE'] },
            { key: 'price_protect', label: 'Price Protect', type: 'select', options: ['true', 'false'] }
        ];

        configFields.forEach(field => {
            const item = document.createElement('div');
            item.className = 'config-item';

            const label = document.createElement('label');
            label.textContent = field.label;
            item.appendChild(label);

            if (field.type === 'select') {
                const select = document.createElement('select');
                select.className = 'config-input';
                select.id = `symbol_${field.key}`;

                field.options.forEach(opt => {
                    const option = document.createElement('option');
                    option.value = opt;
                    option.textContent = opt;
                    if (config[field.key] == opt || config[field.key]?.toString() == opt) {
                        option.selected = true;
                    }
                    select.appendChild(option);
                });

                item.appendChild(select);
            } else {
                const input = document.createElement('input');
                input.type = field.type;
                input.className = 'config-input';
                input.id = `symbol_${field.key}`;
                input.value = config[field.key] || '';
                if (field.step) input.step = field.step;

                item.appendChild(input);
            }

            container.appendChild(item);
        });
    }

    async saveConfig() {
        try {
            const activeTab = document.querySelector('.tab-content.active').id;

            if (activeTab === 'global') {
                // Save global config
                const globals = {};
                Object.keys(this.currentConfig.globals).forEach(key => {
                    const element = document.getElementById(key);
                    if (element) {
                        const value = element.value;
                        // Convert to appropriate type
                        if (value === 'true') globals[key] = true;
                        else if (value === 'false') globals[key] = false;
                        else if (!isNaN(value) && value !== '') globals[key] = parseFloat(value);
                        else globals[key] = value;
                    }
                });

                this.currentConfig.globals = globals;

                const response = await this.ApiClient.saveConfig(this.currentConfig);
                if (response.data.success) {
                    this.UIComponents.showToast('Global configuration saved', 'success');
                }
            } else {
                // Save symbol config
                const symbol = document.getElementById('symbol-selector').value;
                const config = {};

                // Get all symbol config fields
                document.querySelectorAll('#symbol-config .config-item').forEach(item => {
                    const input = item.querySelector('input, select');
                    if (input && input.id) {
                        const key = input.id.replace('symbol_', '');
                        const value = input.value;

                        // Convert to appropriate type
                        if (value === 'true') config[key] = true;
                        else if (value === 'false') config[key] = false;
                        else if (!isNaN(value) && value !== '') config[key] = parseFloat(value);
                        else config[key] = value;
                    }
                });

                const response = await this.ApiClient.saveSymbolConfig(symbol, { symbol, config });
                if (response.data.success) {
                    this.UIComponents.showToast(`${symbol} configuration saved`, 'success');
                    // Update local config
                    this.currentConfig.symbols[symbol] = config;
                }
            }
        } catch (error) {
            console.error('Error saving config:', error);
            this.UIComponents.showToast('Error saving configuration', 'error');
        }
    }

    switchTab(tabElement) {
        const tab = tabElement.dataset.tab;
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn === tabElement);
        });

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === tab);
        });
    }

    async fetchAvailableSymbols() {
        try {
            this.UIComponents.showToast('Fetching available symbols...', 'info');

            const response = await this.ApiClient.getExchangeSymbols();
            const data = response.data;

            if (data.error) {
                this.UIComponents.showToast('Error fetching symbols: ' + data.error, 'error');
                return;
            }

            // Update symbol count
            document.getElementById('symbol-count').textContent =
                `${data.total} symbols available, ${data.configured.length} configured`;

            // Display symbols
            this.displayAvailableSymbols(data.symbols, data.configured);

            this.UIComponents.showToast(`Loaded ${data.total} symbols`, 'success');
        } catch (error) {
            console.error('Error fetching symbols:', error);
            this.UIComponents.showToast('Error fetching symbols', 'error');
        }
    }

    displayAvailableSymbols(symbols, configured) {
        const container = document.getElementById('available-symbols');
        container.innerHTML = '';

        // Store for filtering
        this.availableSymbols = symbols;
        this.configuredSymbols = configured;

        symbols.forEach(symbolInfo => {
            const isConfigured = configured.includes(symbolInfo.symbol);
            const card = this.UIComponents.createSymbolCard(symbolInfo, isConfigured);
            container.appendChild(card);
        });
    }

    async addSymbol(symbol) {
        try {
            const response = await this.ApiClient.addSymbol(symbol);

            if (response.data.success) {
                this.UIComponents.showToast(response.data.message, 'success');

                // Update the symbol card to show as configured
                const card = document.querySelector(`[data-symbol="${symbol}"]`);
                if (card) {
                    card.classList.add('configured');
                    const actionsDiv = card.querySelector('.symbol-actions');
                    actionsDiv.innerHTML = '<span class="btn-small btn-configured">Configured</span>';
                }

                // Reload configuration to update symbol selector
                await this.loadConfig();

                // Add to configured list
                if (!this.configuredSymbols.includes(symbol)) {
                    this.configuredSymbols.push(symbol);
                }

                // Update count
                document.getElementById('symbol-count').textContent =
                    `${this.availableSymbols.length} symbols available, ${this.configuredSymbols.length} configured`;
            } else {
                this.UIComponents.showToast(response.data.error || 'Failed to add symbol', 'error');
            }
        } catch (error) {
            console.error('Error adding symbol:', error);
            this.UIComponents.showToast('Error adding symbol', 'error');
        }
    }

    async removeSymbol() {
        const symbol = document.getElementById('symbol-selector').value;
        if (!symbol) {
            this.UIComponents.showToast('Please select a symbol', 'warning');
            return;
        }

        if (!confirm(`Are you sure you want to remove ${symbol} from configuration?`)) {
            return;
        }

        try {
            const response = await this.ApiClient.removeSymbol(symbol);

            if (response.data.success) {
                this.UIComponents.showToast(response.data.message, 'success');

                // Update the symbol card if visible
                const card = document.querySelector(`[data-symbol="${symbol}"]`);
                if (card) {
                    card.classList.remove('configured');
                    const actionsDiv = card.querySelector('.symbol-actions');
                    actionsDiv.innerHTML = `<button class="btn-small btn-add" onclick="dashboard.addSymbol('${symbol}')">Add</button>`;
                }

                // Reload configuration
                await this.loadConfig();

                // Remove from configured list
                const index = this.configuredSymbols.indexOf(symbol);
                if (index > -1) {
                    this.configuredSymbols.splice(index, 1);
                }

                // Update count if symbols are loaded
                if (this.availableSymbols) {
                    document.getElementById('symbol-count').textContent =
                        `${this.availableSymbols.length} symbols available, ${this.configuredSymbols.length} configured`;
                }
            } else {
                this.UIComponents.showToast(response.data.error || 'Failed to remove symbol', 'error');
            }
        } catch (error) {
            console.error('Error removing symbol:', error);
            this.UIComponents.showToast('Error removing symbol', 'error');
        }
    }

    filterSymbols(searchTerm) {
        if (!this.availableSymbols) return;

        const container = document.getElementById('available-symbols');
        const term = searchTerm.toLowerCase();

        // Filter and redisplay
        const filtered = this.availableSymbols.filter(s =>
            s.symbol.toLowerCase().includes(term) ||
            s.baseAsset.toLowerCase().includes(term)
        );

        container.innerHTML = '';
        filtered.forEach(symbolInfo => {
            const isConfigured = this.configuredSymbols.includes(symbolInfo.symbol);
            const card = this.UIComponents.createSymbolCard(symbolInfo, isConfigured);
            container.appendChild(card);
        });
    }

    openSettingsModal() {
        const modal = document.getElementById('settings-modal');
        modal.style.display = 'block';

        // Load config to ensure fresh data
        this.loadConfig();

        // Setup close handlers
        const closeBtn = modal.querySelector('.modal-close');
        closeBtn.onclick = () => this.UIComponents.hideModal();

        // Close on outside click
        window.onclick = (event) => {
            if (event.target === modal) {
                this.UIComponents.hideModal();
            }
        };
    }

    loadTrades() {
        return this.TradeManager.loadTrades();
    }

    async loadPNLData() {
        try {
            // Load PNL stats
            const response = await this.ApiClient.loadPNLStats();
            const data = response.data;

            if (data.summary) {
                // Update PNL summary
                const totalPnl = data.summary.total_pnl;
                const realizedPnl = data.summary.total_realized_pnl;

                this.Utils.updateElement('total-pnl', this.Utils.formatCurrency(totalPnl), totalPnl);
                this.Utils.updateElement('realized-pnl', this.Utils.formatCurrency(realizedPnl), realizedPnl);
                this.Utils.updateElement('win-rate', data.summary.win_rate.toFixed(1) + '%');
                this.Utils.updateElement('pnl-trades', data.summary.total_trades);

                // Calculate and display percentage gains
                // Use total balance (wallet + available) as the base for percentage calculation
                if (this.walletBalance !== 0 && this.availableBalance !== 0) {
                    // Total account balance is wallet balance + available balance
                    const totalBalance = this.walletBalance + this.availableBalance;

                    if (totalBalance > 0) {
                        // Calculate percentage based on total balance
                        const totalPnlPct = (totalPnl / totalBalance * 100).toFixed(2);
                        const realizedPnlPct = (realizedPnl / totalBalance * 100).toFixed(2);

                        // Update percentage displays
                        const totalPctElement = document.getElementById('total-pnl-pct');
                        const realizedPctElement = document.getElementById('realized-pnl-pct');

                        if (totalPctElement) {
                            totalPctElement.textContent = `(${totalPnlPct >= 0 ? '+' : ''}${totalPnlPct}%)`;
                            totalPctElement.className = `stat-percent ${totalPnl >= 0 ? 'positive' : 'negative'}`;
                        }

                        if (realizedPctElement) {
                            realizedPctElement.textContent = `(${realizedPnlPct >= 0 ? '+' : ''}${realizedPnlPct}%)`;
                            realizedPctElement.className = `stat-percent ${realizedPnl >= 0 ? 'positive' : 'negative'}`;
                        }
                    }
                }
            }

            // Update PNL chart
            if (data.daily_stats && this.ChartManager.getPNLChart()) {
                this.ChartManager.updatePNLChart(data.daily_stats);
            }

            // Load symbol performance
            await this.loadSymbolPerformance();
        } catch (error) {
            console.error('Error loading PNL data:', error);
        }
    }

    async loadSymbolPerformance() {
        try {
            const response = await this.ApiClient.loadSymbolPerformance();
            const performance = response.data;

            const tbody = document.getElementById('symbol-performance-tbody');
            const noData = document.getElementById('no-performance');

            if (!tbody) return;

            tbody.innerHTML = '';

            if (performance.length === 0) {
                if (noData) noData.style.display = 'block';
                document.getElementById('symbol-performance-table').style.display = 'none';
            } else {
                if (noData) noData.style.display = 'none';
                document.getElementById('symbol-performance-table').style.display = 'table';

                performance.forEach(perf => {
                    const row = this.TableBuilder.createSymbolPerformanceRow(perf);
                    tbody.appendChild(row);
                });
            }
        } catch (error) {
            console.error('Error loading symbol performance:', error);
        }
    }

    async syncPNLData() {
        const btn = document.getElementById('sync-pnl-btn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Syncing...';
        }

        try {
            const response = await this.ApiClient.syncPNL();

            if (response.data.success) {
                this.UIComponents.showToast(response.data.message, 'success');
                // Reload PNL data
                await this.loadPNLData();
            } else {
                this.UIComponents.showToast('Failed to sync PNL data', 'error');
            }
        } catch (error) {
            console.error('Error syncing PNL:', error);
            this.UIComponents.showToast('Error syncing PNL data', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Sync PNL Data';
            }
        }
    }

    showClosePositionModal(symbol, side) {
        // Store the position details for later use
        this.confirmCloseSymbol = symbol;
        this.confirmCloseSide = side;

        // Update modal content
        const symbolSideElement = document.getElementById('close-symbol-side');
        if (symbolSideElement) {
            symbolSideElement.textContent = `${symbol} ${side}`;
        }

        // Show modal
        const modal = document.getElementById('close-position-modal');
        modal.style.display = 'block';

        // Setup event listeners
        const confirmBtn = document.getElementById('confirm-close-btn');
        if (confirmBtn) {
            // Remove any existing listener to avoid duplicates
            confirmBtn.removeEventListener('click', this.handleConfirmClose);
            confirmBtn.addEventListener('click', () => {
                this.closePositionConfirmed();
            });
        }

        // Setup modal close handlers
        const modalCloseBtn = modal.querySelector('.modal-close');
        if (modalCloseBtn) {
            modalCloseBtn.onclick = () => this.closeClosePositionModal();
        }

        // Close on outside click
        window.onclick = (event) => {
            if (event.target === modal) {
                this.closeClosePositionModal();
            }
        };
    }

    closeClosePositionModal() {
        const modal = document.getElementById('close-position-modal');
        modal.style.display = 'none';
        // Clear stored data
        this.confirmCloseSymbol = null;
        this.confirmCloseSide = null;
    }

    async closePositionConfirmed() {
        const symbol = this.confirmCloseSymbol;
        const side = this.confirmCloseSide;

        if (!symbol || !side) {
            this.UIComponents.showToast('Position details not available', 'error');
            return;
        }

        // Close modal
        this.closeClosePositionModal();

        try {
            // Make API call to close position
            const response = await this.ApiClient.closePosition(symbol, side);

            if (response.data.success) {
                if (response.data.simulated) {
                    // Simulation mode
                    this.UIComponents.showToast(response.data.message, 'info');
                } else {
                    // Real close order placed
                    this.UIComponents.showToast(`Close order placed for ${symbol} ${side}`, 'success');
                }

                // Refresh positions data after successful close
                setTimeout(() => {
                    this.loadAllData();
                }, 1000); // Small delay to allow order to execute
            } else {
                this.UIComponents.showToast(response.data.error || 'Failed to close position', 'error');
            }
        } catch (error) {
            console.error('Error closing position:', error);
            this.UIComponents.showToast('Error closing position', 'error');
        }
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new Dashboard();
});
