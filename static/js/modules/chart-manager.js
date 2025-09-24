// Chart Manager Module
window.DashboardModules = window.DashboardModules || {};

window.DashboardModules.ChartManager = (function() {
    // Private variables
    let volumeChart = null;
    let pnlChart = null;
    const Utils = window.DashboardModules.Utils;

    // Private functions
    function initChartsPrivate() {
        initVolumeChartPrivate();
        initPNLChartPrivate();
    }

    function initVolumeChartPrivate() {
        const ctx = document.getElementById('volume-chart')?.getContext('2d');
        if (ctx) {
            volumeChart = new Chart(ctx, {
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

    function initPNLChartPrivate() {
        const pnlCtx = document.getElementById('pnl-chart')?.getContext('2d');
        if (pnlCtx) {
            pnlChart = new Chart(pnlCtx, {
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
    }

    function updateVolumeChartPrivate(hourlyData) {
        if (!volumeChart) return;

        // Sort by hour and take last 24
        hourlyData.sort(function(a, b) { return a.hour - b.hour; });
        const last24 = hourlyData.slice(-24);

        const labels = last24.map(function(h) {
            const date = new Date(h.hour);
            return date.getHours() + ':00';
        });

        const data = last24.map(function(h) { return h.volume || 0; });

        volumeChart.data.labels = labels;
        volumeChart.data.datasets[0].data = data;
        volumeChart.update();
    }

    function updatePNLChartPrivate(dailyStats) {
        if (!pnlChart || !dailyStats) return;

        // Sort by date
        dailyStats.sort(function(a, b) { return new Date(a.date) - new Date(b.date); });

        const labels = dailyStats.map(function(d) {
            const date = new Date(d.date);
            return (date.getMonth() + 1) + '/' + date.getDate();
        });

        const realizedData = dailyStats.map(function(d) { return d.realized_pnl || 0; });

        pnlChart.data.labels = labels;
        pnlChart.data.datasets = [
            {
                label: 'Realized PNL',
                data: realizedData,
                borderColor: 'rgba(34, 197, 94, 1)',
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                borderWidth: 2,
                tension: 0.1,
                fill: true
            }
        ];
        pnlChart.update();
    }

    // Public API
    return {
        initCharts: initChartsPrivate,
        updateVolumeChart: updateVolumeChartPrivate,
        updatePNLChart: updatePNLChartPrivate,
        getVolumeChart: function() { return volumeChart; },
        getPNLChart: function() { return pnlChart; }
    };
})();
