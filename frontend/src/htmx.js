import _hyperscript from 'hyperscript.org/dist/_hyperscript.min';
import './_htmx.js';
import Alpine from "alpinejs";
import mask from '@alpinejs/mask';
import {create, all} from 'mathjs';

window.Alpine = Alpine;
window._hyperscript = _hyperscript;
window.math = create(all, {
    number: 'BigNumber',      // Default type of number:
                              // 'number' (default), 'BigNumber', or 'Fraction'
    precision: 64,            // Number of significant digits for BigNumbers
    relTol: 1e-60,
    absTol: 1e-63
});

Alpine.plugin(mask);
Alpine.start();
_hyperscript.browserInit();


const successAudio = new Audio("/static/sounds/success.mp3");
const popAudio = new Audio("/static/sounds/pop.mp3");
window.paidSound = successAudio;
window.unpaidSound = popAudio;

/**
 * Parse a localized number to a float.
 * @param {string} stringNumber - the localized number
 * @param {string} locale - [optional] the locale that the number is represented in. Omit this parameter to use the current locale.
 */
window.parseLocaleNumber = function parseLocaleNumber(stringNumber, locale) {
    let thousandSeparator = Intl.NumberFormat(locale).format(11111).replace(/\d/g, '');
    let decimalSeparator = Intl.NumberFormat(locale).format(1.1).replace(/\d/g, '');

    return parseFloat(stringNumber
        .replace(new RegExp('\\' + thousandSeparator, 'g'), '')
        .replace(new RegExp('\\' + decimalSeparator), '.')
    );
};
