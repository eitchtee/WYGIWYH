import htmx from "htmx.org";
import _hyperscript from 'hyperscript.org/dist/_hyperscript.min';
import Alpine from "alpinejs";
import mask from '@alpinejs/mask';
window.Alpine = Alpine;

Alpine.start();
Alpine.plugin(mask);
_hyperscript.browserInit();

let modalEle = document.getElementById("modal");

if (modalEle) {
    const modal = new bootstrap.Modal(modalEle); // eslint-disable-line no-undef

    htmx.on("htmx:beforeSwap", (e) => {
        // Empty response targeting #dialog => hide the modal
        if (e.detail.target.id === "dialog" && !e.detail.xhr.response) {
            modal.hide();
            e.detail.shouldSwap = false;
        }
    });

    htmx.on("hidden.bs.modal", () => {
        document.getElementById("dialog").innerHTML = "";
    });
}

const successAudio = new Audio("/static/sounds/success.mp3");
const popAudio = new Audio("/static/sounds/pop.mp3");
window.paidSound = successAudio;
window.unpaidSound = popAudio;

// htmx.on("paid", () => {
//     successAudio.pause();
//     successAudio.currentTime = 0;
//     successAudio.play();
// });
//
// htmx.on("unpaid", () => {
//     popAudio.pause();
//     popAudio.currentTime = 0;
//     popAudio.play();
// });

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
