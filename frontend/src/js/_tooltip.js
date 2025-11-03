import tippy from 'tippy.js';
import 'tippy.js/dist/tippy.css';
import 'tippy.js/themes/light-border.css';


function initiateTooltips() {
    const currentDataTheme = document.documentElement.getAttribute('data-theme') || '';
    let theme;

    if (currentDataTheme.endsWith('_dark')) {
        theme = 'light-border';
    } else if (currentDataTheme.endsWith('_light')) {
        theme = 'dark';
    }

    tippy('[data-tippy-content]', {
        theme: theme
    });
}

window.initiateTooltips = initiateTooltips;