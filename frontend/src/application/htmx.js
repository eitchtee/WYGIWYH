import htmx from "htmx.org";
import _hyperscript from 'hyperscript.org/dist/_hyperscript.min';
import Alpine from "alpinejs";
import mask from '@alpinejs/mask';

window.htmx = htmx;
window.Alpine = Alpine;

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
    let thousandSeparator = Intl.NumberFormat(locale).format(11111).replace(/\p{Number}/gu, '');
    let decimalSeparator = Intl.NumberFormat(locale).format(1.1).replace(/\p{Number}/gu, '');

    return parseFloat(stringNumber
        .replace(new RegExp('\\' + thousandSeparator, 'g'), '')
        .replace(new RegExp('\\' + decimalSeparator), '.')
    );
};
