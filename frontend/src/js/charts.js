import Chart from 'chart.js/auto';
import {SankeyController, Flow} from 'chartjs-chart-sankey';

Chart.register(SankeyController, Flow);
window.Chart = Chart;
