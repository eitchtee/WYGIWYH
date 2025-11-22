import {delegate} from 'tippy.js';
import 'tippy.js/dist/tippy.css';
import '../styles/_toasts.scss'

function initiateTooltips() {
    delegate(document.body, {
        target: '[data-tippy-content]',
        theme: "wygiwyh",
        zIndex: 1089,
        content(reference) {
            return reference.getAttribute('data-tippy-content');
        },
    });
}

// Call it once on page load
initiateTooltips();
