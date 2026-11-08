import Chart from 'chart.js/auto';
import {SankeyController, Flow} from 'chartjs-chart-sankey';
import zoomPlugin from 'chartjs-plugin-zoom';

Chart.register(SankeyController, Flow, zoomPlugin);
window.Chart = Chart;

// The theme's text color at a given strength, resolved to a value canvas can draw
// with. shortcut: read once per chart, so a theme switch shows on the next render.
window.chartInk = (percent) => {
  const probe = document.createElement('span');
  probe.style.color = `color-mix(in oklab, var(--color-base-content) ${percent}%, transparent)`;
  document.body.appendChild(probe);
  const color = getComputedStyle(probe).color;
  probe.remove();
  return color;
};

// Formats amounts with the user's separators, as the amounts elsewhere in the app.
// currency: {prefix, suffix, decimals, decimal, thousand}
window.chartMoney = (currency) => (v, decimals = currency.decimals) => {
  const [whole, fraction] = Math.abs(v).toFixed(decimals).split('.');
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, currency.thousand);
  const number = fraction ? `${grouped}${currency.decimal}${fraction}` : grouped;
  return `${v < 0 ? '-' : ''}${currency.prefix}${number}${currency.suffix}`;
};
