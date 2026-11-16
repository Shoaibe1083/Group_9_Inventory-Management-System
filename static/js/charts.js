/* Chart.js presets shared by Dashboard and Reports.
   Colours come from the active theme's CSS tokens (--chart-1…8 are the
   validated categorical order, stepped per theme) and are re-applied
   whenever the theme changes. Series are assigned by slot, never cycled. */
(function () {
  const charts = [];

  function tokens() {
    const css = getComputedStyle(document.documentElement);
    const v = (name) => css.getPropertyValue(name).trim();
    return {
      series: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => v('--chart-' + i)),
      ink: v('--text-2'),
      muted: v('--muted'),
      grid: v('--chart-grid'),
      axis: v('--chart-axis'),
      surface: v('--surface'),
      tooltip: v('--tooltip-bg'),
    };
  }

  Chart.defaults.font.family = "'Inter', -apple-system, 'Segoe UI', sans-serif";
  Chart.defaults.font.size = 12;

  const compact = (v) => {
    const a = Math.abs(v);
    if (a >= 1e7) return '৳' + (v / 1e7).toFixed(1).replace(/\.0$/, '') + 'Cr';
    if (a >= 1e5) return '৳' + (v / 1e5).toFixed(1).replace(/\.0$/, '') + 'L';
    return '৳' + v.toLocaleString('en-US');
  };

  function tooltip(t) {
    return {
      backgroundColor: t.tooltip,
      titleColor: '#fff',
      bodyColor: 'rgba(255,255,255,.85)',
      padding: 10,
      cornerRadius: 10,
      boxPadding: 5,
      usePointStyle: true,
      titleFont: { weight: '600' },
    };
  }

  // Vertical hover line for line charts.
  const crosshair = {
    id: 'crosshair',
    afterDatasetsDraw(chart) {
      const active = chart.tooltip && chart.tooltip.getActiveElements();
      if (!active || !active.length) return;
      const { ctx, chartArea } = chart;
      ctx.save();
      ctx.strokeStyle = tokens().axis;
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(active[0].element.x, chartArea.top);
      ctx.lineTo(active[0].element.x, chartArea.bottom);
      ctx.stroke();
      ctx.restore();
    },
  };

  // Value label at the end of each horizontal bar.
  const barValues = {
    id: 'barValues',
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.fillStyle = tokens().ink;
      ctx.font = '500 12px ' + Chart.defaults.font.family;
      ctx.textBaseline = 'middle';
      chart.getDatasetMeta(0).data.forEach((bar, i) => {
        ctx.fillText(chart.data.datasets[0].data[i].toLocaleString('en-US'), bar.x + 8, bar.y);
      });
      ctx.restore();
    },
  };

  // Each chart kind knows how to paint itself with the current tokens.
  const painters = {
    line(chart, t) {
      chart.data.datasets.forEach((ds) => {
        const c = t.series[ds.slot];
        Object.assign(ds, { borderColor: c, backgroundColor: c, pointBackgroundColor: c, pointBorderColor: t.surface });
      });
      const o = chart.options;
      o.plugins.tooltip = { ...o.plugins.tooltip, ...tooltip(t) };
      o.scales.y.grid.color = t.grid;
      o.scales.y.ticks.color = t.muted;
      o.scales.x.ticks.color = t.muted;
      o.scales.x.border.color = t.axis;
    },
    hbar(chart, t) {
      chart.data.datasets[0].backgroundColor = t.series[0];
      const o = chart.options;
      o.plugins.tooltip = { ...o.plugins.tooltip, ...tooltip(t) };
      o.scales.x.grid.color = t.grid;
      o.scales.y.ticks.color = t.ink;
      o.scales.y.border.color = t.axis;
    },
    donut(chart, t) {
      const ds = chart.data.datasets[0];
      ds.backgroundColor = chart.data.labels.map((_, i) => t.series[i]);
      ds.borderColor = t.surface;
      chart.options.plugins.tooltip = { ...chart.options.plugins.tooltip, ...tooltip(t) };
    },
  };

  // Paint the config before Chart.js builds it: some chart types cache
  // their resolved colours at creation time.
  function make(kind, id, config) {
    painters[kind](config, tokens());
    const chart = new Chart(document.getElementById(id), config);
    chart.$kind = kind;
    charts.push(chart);
    return chart;
  }

  window.addEventListener('si:theme', () => {
    // Wait a frame so the new theme's CSS variables are in effect.
    requestAnimationFrame(() => {
      const t = tokens();
      charts.forEach((c) => { painters[c.$kind](c, t); c.update(); });
      window.dispatchEvent(new CustomEvent('si:charts-repainted'));
    });
  });

  function line(id, labels, series) {
    return make('line', id, {
      type: 'line',
      data: {
        labels,
        datasets: series.map((s) => ({
          label: s.label,
          slot: s.slot,
          data: s.data,
          borderWidth: 2,
          tension: 0.35,
          pointRadius: labels.length <= 14 ? 3 : 0,
          pointHoverRadius: 5,
          pointBorderWidth: 2,
          fill: false,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => ' ' + c.dataset.label + ': ' + SI.money(c.parsed.y) } },
        },
        scales: {
          y: {
            beginAtZero: true,
            border: { display: false },
            grid: { drawTicks: false },
            ticks: { padding: 10, maxTicksLimit: 5, callback: compact },
          },
          x: {
            border: {},
            grid: { display: false },
            ticks: { padding: 8, maxRotation: 0, autoSkip: true, maxTicksLimit: window.innerWidth < 640 ? 6 : 15 },
          },
        },
      },
      plugins: [crosshair],
    });
  }

  function hbar(id, labels, values, tip) {
    return make('hbar', id, {
      type: 'bar',
      data: {
        labels,
        datasets: [{ data: values, borderRadius: 4, borderSkipped: 'start', barThickness: 18 }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { right: 36 } },
        plugins: {
          legend: { display: false },
          tooltip: { displayColors: false, callbacks: { label: (c) => tip(c.dataIndex) } },
        },
        scales: {
          x: { beginAtZero: true, border: { display: false }, grid: { drawTicks: false }, ticks: { display: false } },
          y: {
            border: {},
            grid: { display: false },
            ticks: {
              padding: 8,
              callback(value) {
                const label = this.getLabelForValue(value);
                return label.length > 26 ? label.slice(0, 25) + '…' : label;
              },
            },
          },
        },
      },
      plugins: [barValues],
    });
  }

  function donut(id, labels, values, shares) {
    return make('donut', id, {
      type: 'doughnut',
      data: { labels, datasets: [{ data: values, borderWidth: 2, hoverOffset: 4 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => ' ' + c.label + ': ' + SI.money(c.parsed, 0) + ' (' + shares[c.dataIndex] + '%)' } },
        },
      },
    });
  }

  window.SIChart = { line, hbar, donut, color: (slot) => tokens().series[slot] };
})();
