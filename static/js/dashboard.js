// Dashboard JavaScript
class Dashboard {
    constructor() {
        this.eventSource = null;
        this.volumeChart = null;
        this.currentConfig = null;
        this.refreshInterval = null;
        this.init();
    }

    async init() {
        // Initialize event listeners
        this.setupEventListeners();

        // Initialize SSE connection
        this.connectSSE();

        // Load initial data
        await this.loadAllData();

        // Set up refresh interval (every 5 seconds)
        this.refreshInterval = setInterval(() => this.refreshData(), 5000);

        // Initialize charts
        this.initCharts();

        // Load PNL data
        await this.loadPNLData();
    }

    setupEventListeners() {
        // Refresh button
        document.getElementById('refresh-btn').addEventListener('click', () => this.loadAllData());

        // Config tabs
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
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

        // PNL sync button
        const syncBtn = document.getElementById('sync-pnl-btn');
        if (syncBtn) {
            syncBtn.addEventListener('click', () => this.syncPNLData());
        }
    }

    connectSSE() {
        this.eventSource = new EventSource('/api/stream');

        this.eventSource.onopen = () => {
            this.updateConnectionStatus('connected');
        };

        this.eventSource.onerror = () => {
            this.updateConnectionStatus('error');
        };

        this.eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleRealtimeEvent(data);
        };
    }

    handleRealtimeEvent(event) {
        switch(event.type) {
            case 'new_liquidation':
                this.addLiquidationRow(event.data);
                this.showToast('New liquidation detected', 'info');
                break;
            case 'new_trade':
                this.addTradeRow(event.data);
                this.showToast(`Trade executed: ${event.data.symbol}`, 'success');
                break;
            case 'config_updated':
                this.showToast(event.data.message, 'success');
                break;
            case 'symbol_added':
                this.showToast(event.data.message, 'success');
                this.loadConfig(); // Reload config to update selectors
                break;
            case 'symbol_removed':
                this.showToast(event.data.message, 'warning');
                this.loadConfig(); // Reload config to update selectors
                break;
            case 'heartbeat':
                // Keep connection alive
                break;
        }
    }

    async loadAllData() {
        try {
            await Promise.all([
                this.loadAccount(),
                this.loadPositions(),
                this.loadStats(),
                this.loadLiquidations(),
                this.loadTrades(),
                this.loadConfig()
            ]);
        } catch (error) {
            console.error('Error loading data:', error);
            this.showToast('Error loading data', 'error');
        }
    }

    async refreshData() {
        try {
            await Promise.all([
                this.loadAccount(),
                this.loadPositions(),
                this.loadStats()
            ]);
        } catch (error) {
            console.error('Error refreshing data:', error);
        }
    }

    async loadAccount() {
        try {
            const response = await axios.get('/api/account');
            const data = response.data;

            if (data.error) {
                console.error('Account error:', data.error);
                return;
            }

            // Update account display
            this.updateElement('wallet-balance', this.formatCurrency(data.totalWalletBalance));
            this.updateElement('unrealized-pnl', this.formatCurrency(data.totalUnrealizedProfit), data.totalUnrealizedProfit);
            this.updateElement('margin-used', this.formatCurrency(data.totalPositionInitialMargin));
            this.updateElement('available-balance', this.formatCurrency(data.availableBalance));
        } catch (error) {
            console.error('Error loading account:', error);
        }
    }

    async loadPositions() {
        try {
            const response = await axios.get('/api/positions');
            const positions = response.data;

            const tbody = document.getElementById('positions-tbody');
            tbody.innerHTML = '';

            if (positions.length === 0) {
                document.getElementById('no-positions').style.display = 'block';
                document.getElementById('positions-table').style.display = 'none';
            } else {
                document.getElementById('no-positions').style.display = 'none';
                document.getElementById('positions-table').style.display = 'table';

                positions.forEach(pos => {
                    const row = this.createPositionRow(pos);
                    tbody.appendChild(row);
                });
            }
        } catch (error) {
            console.error('Error loading positions:', error);
        }
    }

    createPositionRow(position) {
        const row = document.createElement('tr');
        const pnl = parseFloat(position.unrealizedPnl || 0);
        const pnlPct = position.positionValue > 0 ? (pnl / position.positionValue * 100) : 0;
        const sideClass = position.side === 'LONG' ? 'position-long' : 'position-short';

        row.innerHTML = `
            <td>${position.symbol}</td>
            <td class="${sideClass}">${position.side}</td>
            <td>${Math.abs(position.positionAmt).toFixed(4)}</td>
            <td>$${parseFloat(position.entryPrice).toFixed(4)}</td>
            <td>$${parseFloat(position.markPrice).toFixed(4)}</td>
            <td class="${pnl >= 0 ? 'positive' : 'negative'}">
                ${this.formatCurrency(pnl)}
            </td>
            <td class="${pnl >= 0 ? 'positive' : 'negative'}">
                ${pnlPct.toFixed(2)}%
            </td>
            <td>${this.formatCurrency(position.initialMargin)}</td>
        `;
        return row;
    }

    async loadStats() {
        try {
            const response = await axios.get('/api/stats?hours=24');
            const stats = response.data;

            // Update trading stats
            this.updateElement('total-trades', stats.trades.total_trades);
            this.updateElement('success-rate', stats.trades.success_rate.toFixed(1) + '%');
            this.updateElement('liquidations-count', stats.liquidations.total_liquidations);
            this.updateElement('volume-processed', this.formatCurrency(stats.liquidations.total_liquidation_volume));

            // Update volume chart
            if (this.volumeChart && stats.hourly_volume) {
                this.updateVolumeChart(stats.hourly_volume);
            }
        } catch (error) {
            console.error('Error loading stats:', error);
        }
    }

    async loadLiquidations() {
        try {
            const response = await axios.get('/api/liquidations?limit=20');
            const liquidations = response.data;

            const tbody = document.getElementById('liquidations-tbody');
            tbody.innerHTML = '';

            liquidations.forEach(liq => {
                const row = this.createLiquidationRow(liq);
                tbody.appendChild(row);
            });
        } catch (error) {
            console.error('Error loading liquidations:', error);
        }
    }

    createLiquidationRow(liquidation) {
        const row = document.createElement('tr');
        const sideClass = liquidation.side === 'BUY' ? 'position-long' : 'position-short';

        row.innerHTML = `
            <td>${this.formatTime(liquidation.timestamp)}</td>
            <td>${liquidation.symbol}</td>
            <td class="${sideClass}">${liquidation.side}</td>
            <td>${parseFloat(liquidation.qty).toFixed(4)}</td>
            <td>$${parseFloat(liquidation.price).toFixed(4)}</td>
            <td>${this.formatCurrency(liquidation.usdt_value)}</td>
        `;
        return row;
    }

    addLiquidationRow(liquidation) {
        const tbody = document.getElementById('liquidations-tbody');
        const row = this.createLiquidationRow(liquidation);

        // Add to top of table
        tbody.insertBefore(row, tbody.firstChild);

        // Remove last row if too many
        if (tbody.children.length > 20) {
            tbody.removeChild(tbody.lastChild);
        }
    }

    async loadTrades() {
        try {
            const response = await axios.get('/api/trades?limit=20');
            const trades = response.data;

            const tbody = document.getElementById('trades-tbody');
            tbody.innerHTML = '';

            trades.forEach(trade => {
                const row = this.createTradeRow(trade);
                tbody.appendChild(row);
            });
        } catch (error) {
            console.error('Error loading trades:', error);
        }
    }

    createTradeRow(trade) {
        const row = document.createElement('tr');
        const sideClass = trade.side === 'BUY' ? 'position-long' : 'position-short';
        const statusClass = trade.status === 'SUCCESS' ? 'badge-success' :
                           trade.status === 'SIMULATED' ? 'badge-warning' : 'badge-danger';

        row.innerHTML = `
            <td>${this.formatTime(trade.timestamp)}</td>
            <td>${trade.symbol}</td>
            <td class="${sideClass}">${trade.side}</td>
            <td>${parseFloat(trade.qty).toFixed(4)}</td>
            <td>$${parseFloat(trade.price).toFixed(4)}</td>
            <td><span class="badge ${statusClass}">${trade.status}</span></td>
            <td>${trade.order_type || 'LIMIT'}</td>
        `;
        return row;
    }

    addTradeRow(trade) {
        const tbody = document.getElementById('trades-tbody');
        const row = this.createTradeRow(trade);

        // Add to top of table
        tbody.insertBefore(row, tbody.firstChild);

        // Remove last row if too many
        if (tbody.children.length > 20) {
            tbody.removeChild(tbody.lastChild);
        }
    }

    async loadConfig() {
        try {
            const response = await axios.get('/api/config');
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
            this.showToast('Error loading configuration', 'error');
        }
    }

    loadSymbolConfig(symbol) {
        const config = this.currentConfig.symbols[symbol];
        const container = document.getElementById('symbol-config');

        if (!config) return;

        container.innerHTML = '';

        // Create input fields for each config option
        const configFields = [
            { key: 'volume_threshold', label: 'Volume Threshold', type: 'number', step: '0.01' },
            { key: 'leverage', label: 'Leverage', type: 'number', step: '1' },
            { key: 'margin_type', label: 'Margin Type', type: 'select', options: ['ISOLATED', 'CROSSED'] },
            { key: 'trade_side', label: 'Trade Side', type: 'select', options: ['OPPOSITE', 'SAME'] },
            { key: 'trade_value_usdt', label: 'Trade Value (USDT)', type: 'number', step: '0.01' },
            { key: 'price_offset_pct', label: 'Price Offset %', type: 'number', step: '0.01' },
            { key: 'max_position_usdt', label: 'Max Position (USDT)', type: 'number', step: '0.01' },
            { key: 'take_profit_enabled', label: 'Take Profit Enabled', type: 'select', options: ['true', 'false'] },
            { key: 'take_profit_pct', label: 'Take Profit %', type: 'number', step: '0.01' },
            { key: 'stop_loss_enabled', label: 'Stop Loss Enabled', type: 'select', options: ['true', 'false'] },
            { key: 'stop_loss_pct', label: 'Stop Loss %', type: 'number', step: '0.01' }
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
                    if (config[field.key] == opt || config[field.key].toString() == opt) {
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

            if (activeTab === 'config-global') {
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

                const response = await axios.post('/api/config', this.currentConfig);
                if (response.data.success) {
                    this.showToast('Global configuration saved', 'success');
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

                const response = await axios.post('/api/config/symbol', { symbol, config });
                if (response.data.success) {
                    this.showToast(`${symbol} configuration saved`, 'success');
                    // Update local config
                    this.currentConfig.symbols[symbol] = config;
                }
            }
        } catch (error) {
            console.error('Error saving config:', error);
            this.showToast('Error saving configuration', 'error');
        }
    }

    switchTab(tab) {
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `config-${tab}`);
        });
    }

    async loadPNLData() {
        try {
            // Load PNL stats
            const response = await axios.get('/api/pnl/stats?days=7');
            const data = response.data;

            if (data.summary) {
                // Update PNL summary
                this.updateElement('total-pnl', this.formatCurrency(data.summary.total_pnl), data.summary.total_pnl);
                this.updateElement('realized-pnl', this.formatCurrency(data.summary.total_realized_pnl), data.summary.total_realized_pnl);
                this.updateElement('win-rate', data.summary.win_rate.toFixed(1) + '%');
                this.updateElement('pnl-trades', data.summary.total_trades);
            }

            // Update PNL chart
            if (data.daily_stats && this.pnlChart) {
                this.updatePNLChart(data.daily_stats);
            }

            // Load symbol performance
            await this.loadSymbolPerformance();
        } catch (error) {
            console.error('Error loading PNL data:', error);
        }
    }

    async loadSymbolPerformance() {
        try {
            const response = await axios.get('/api/pnl/symbols?days=7');
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
                    const row = this.createSymbolPerformanceRow(perf);
                    tbody.appendChild(row);
                });
            }
        } catch (error) {
            console.error('Error loading symbol performance:', error);
        }
    }

    createSymbolPerformanceRow(perf) {
        const row = document.createElement('tr');
        const pnlClass = perf.total_pnl >= 0 ? 'positive' : 'negative';

        row.innerHTML = `
            <td>${perf.symbol}</td>
            <td class="${pnlClass}">${this.formatCurrency(perf.total_pnl)}</td>
            <td class="${perf.realized_pnl >= 0 ? 'positive' : 'negative'}">${this.formatCurrency(perf.realized_pnl)}</td>
            <td class="negative">${this.formatCurrency(perf.commissions)}</td>
            <td>${perf.total_trades}</td>
            <td class="${perf.win_rate >= 50 ? 'positive' : 'negative'}">${perf.win_rate.toFixed(1)}%</td>
        `;
        return row;
    }

    async syncPNLData() {
        const btn = document.getElementById('sync-pnl-btn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Syncing...';
        }

        try {
            const response = await axios.post('/api/pnl/sync', { hours: 168 }); // Sync 7 days

            if (response.data.success) {
                this.showToast(response.data.message, 'success');
                // Reload PNL data
                await this.loadPNLData();
            } else {
                this.showToast('Failed to sync PNL data', 'error');
            }
        } catch (error) {
            console.error('Error syncing PNL:', error);
            this.showToast('Error syncing PNL data', 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Sync PNL Data';
            }
        }
    }

    updatePNLChart(dailyStats) {
        if (!this.pnlChart || !dailyStats) return;

        // Sort by date
        dailyStats.sort((a, b) => new Date(a.date) - new Date(b.date));

        const labels = dailyStats.map(d => {
            const date = new Date(d.date);
            return (date.getMonth() + 1) + '/' + date.getDate();
        });

        const pnlData = dailyStats.map(d => d.total_pnl || 0);
        const realizedData = dailyStats.map(d => d.realized_pnl || 0);

        this.pnlChart.data.labels = labels;
        this.pnlChart.data.datasets = [
            {
                label: 'Total PNL',
                data: pnlData,
                borderColor: 'rgba(59, 130, 246, 1)',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                borderWidth: 2,
                tension: 0.1
            },
            {
                label: 'Realized PNL',
                data: realizedData,
                borderColor: 'rgba(34, 197, 94, 1)',
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                borderWidth: 2,
                tension: 0.1
            }
        ];
        this.pnlChart.update();
    }

    initCharts() {
        // Volume chart (removed since we deleted that section)

        // PNL chart
        const pnlCtx = document.getElementById('pnl-chart')?.getContext('2d');
        if (pnlCtx) {
            this.pnlChart = new Chart(pnlCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: []
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top'
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    let label = context.dataset.label || '';
                                    if (label) {
                                        label += ': ';
                                    }
                                    label += '$' + context.parsed.y.toFixed(2);
                                    return label;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)'
                            },
                            ticks: {
                                color: '#a1a1aa'
                            }
                        },
                        y: {
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)'
                            },
                            ticks: {
                                color: '#a1a1aa',
                                callback: function(value) {
                                    return '$' + value.toLocaleString();
                                }
                            }
                        }
                    }
                }
            });
        }

        // Old volume chart code (kept for compatibility if needed later)
        const ctx = document.getElementById('volume-chart')?.getContext('2d');
        if (ctx) {
            this.volumeChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Liquidation Volume (USDT)',
                    data: [],
                    backgroundColor: 'rgba(59, 130, 246, 0.5)',
                    borderColor: 'rgba(59, 130, 246, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#a1a1aa'
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#a1a1aa',
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });
        }
    }

    updateVolumeChart(hourlyData) {
        if (!this.volumeChart) return;

        // Sort by hour and take last 24
        hourlyData.sort((a, b) => a.hour - b.hour);
        const last24 = hourlyData.slice(-24);

        const labels = last24.map(h => {
            const date = new Date(h.hour);
            return date.getHours() + ':00';
        });

        const data = last24.map(h => h.volume || 0);

        this.volumeChart.data.labels = labels;
        this.volumeChart.data.datasets[0].data = data;
        this.volumeChart.update();
    }

    updateConnectionStatus(status) {
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

    updateElement(id, value, compareValue = null) {
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

    formatCurrency(value) {
        if (value === null || value === undefined) return '$0.00';
        const num = parseFloat(value);
        return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    formatTime(timestamp) {
        const date = new Date(parseInt(timestamp));
        return date.toLocaleTimeString('en-US', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        toast.innerHTML = `
            <span>${message}</span>
            <span class="toast-close">✕</span>
        `;

        container.appendChild(toast);

        // Auto remove after 5 seconds
        setTimeout(() => {
            toast.remove();
        }, 5000);

        // Close button
        toast.querySelector('.toast-close').addEventListener('click', () => {
            toast.remove();
        });
    }

    async fetchAvailableSymbols() {
        try {
            this.showToast('Fetching available symbols...', 'info');

            const response = await axios.get('/api/exchange/symbols');
            const data = response.data;

            if (data.error) {
                this.showToast('Error fetching symbols: ' + data.error, 'error');
                return;
            }

            // Update symbol count
            document.getElementById('symbol-count').textContent =
                `${data.total} symbols available, ${data.configured.length} configured`;

            // Display symbols
            this.displayAvailableSymbols(data.symbols, data.configured);

            this.showToast(`Loaded ${data.total} symbols`, 'success');
        } catch (error) {
            console.error('Error fetching symbols:', error);
            this.showToast('Error fetching symbols', 'error');
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
            const card = this.createSymbolCard(symbolInfo, isConfigured);
            container.appendChild(card);
        });
    }

    createSymbolCard(symbolInfo, isConfigured) {
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

    async addSymbol(symbol) {
        try {
            const response = await axios.post('/api/config/symbol/add', { symbol });

            if (response.data.success) {
                this.showToast(response.data.message, 'success');

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
                this.showToast(response.data.error || 'Failed to add symbol', 'error');
            }
        } catch (error) {
            console.error('Error adding symbol:', error);
            this.showToast('Error adding symbol', 'error');
        }
    }

    async removeSymbol() {
        const symbol = document.getElementById('symbol-selector').value;
        if (!symbol) {
            this.showToast('Please select a symbol', 'warning');
            return;
        }

        if (!confirm(`Are you sure you want to remove ${symbol} from configuration?`)) {
            return;
        }

        try {
            const response = await axios.post('/api/config/symbol/remove', { symbol });

            if (response.data.success) {
                this.showToast(response.data.message, 'success');

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
                this.showToast(response.data.error || 'Failed to remove symbol', 'error');
            }
        } catch (error) {
            console.error('Error removing symbol:', error);
            this.showToast('Error removing symbol', 'error');
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
            const card = this.createSymbolCard(symbolInfo, isConfigured);
            container.appendChild(card);
        });
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new Dashboard();
});