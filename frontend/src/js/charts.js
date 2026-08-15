import Chart from 'chart.js/auto';
import {SankeyController, Flow} from 'chartjs-chart-sankey';
import zoomPlugin from 'chartjs-plugin-zoom';

Chart.register(SankeyController, Flow, zoomPlugin);
window.Chart = Chart;
