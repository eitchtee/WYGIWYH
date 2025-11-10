import { delegate } from 'tippy.js';
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

    delegate(document.body, {
        target: '[data-tippy-content]',
        theme: theme,
        zIndex: 1100,
        content(reference) {
            return reference.getAttribute('data-tippy-content');
        },
    });
}

// Call it once on page load
initiateTooltips();
