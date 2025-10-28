import AirDatepicker from 'air-datepicker';
import {createPopper} from '@popperjs/core';

// --- Static Locale Imports ---
// We import all locales statically to ensure Vite transforms them correctly.
import localeAr from 'air-datepicker/locale/ar.js';
import localeBg from 'air-datepicker/locale/bg.js';
import localeCa from 'air-datepicker/locale/ca.js';
import localeCs from 'air-datepicker/locale/cs.js';
import localeDa from 'air-datepicker/locale/da.js';
import localeDe from 'air-datepicker/locale/de.js';
import localeEl from 'air-datepicker/locale/el.js';
import localeEn from 'air-datepicker/locale/en.js';
import localeEs from 'air-datepicker/locale/es.js';
import localeEu from 'air-datepicker/locale/eu.js';
import localeFi from 'air-datepicker/locale/fi.js';
import localeFr from 'air-datepicker/locale/fr.js';
import localeHr from 'air-datepicker/locale/hr.js';
import localeHu from 'air-datepicker/locale/hu.js';
import localeId from 'air-datepicker/locale/id.js';
import localeIt from 'air-datepicker/locale/it.js';
import localeJa from 'air-datepicker/locale/ja.js';
import localeKo from 'air-datepicker/locale/ko.js';
import localeNb from 'air-datepicker/locale/nb.js';
import localeNl from 'air-datepicker/locale/nl.js';
import localePl from 'air-datepicker/locale/pl.js';
import localePtBr from 'air-datepicker/locale/pt-BR.js';
import localePt from 'air-datepicker/locale/pt.js';
import localeRo from 'air-datepicker/locale/ro.js';
import localeRu from 'air-datepicker/locale/ru.js';
import localeSi from 'air-datepicker/locale/si.js';
import localeSk from 'air-datepicker/locale/sk.js';
import localeSl from 'air-datepicker/locale/sl.js';
import localeSv from 'air-datepicker/locale/sv.js';
import localeTh from 'air-datepicker/locale/th.js';
import localeTr from 'air-datepicker/locale/tr.js';
import localeUk from 'air-datepicker/locale/uk.js';
import localeZh from 'air-datepicker/locale/zh.js';

// Map language codes to their imported locale objects
const allLocales = {
  'ar': localeAr,
  'bg': localeBg,
  'ca': localeCa,
  'cs': localeCs,
  'da': localeDa,
  'de': localeDe,
  'el': localeEl,
  'en': localeEn,
  'es': localeEs,
  'eu': localeEu,
  'fi': localeFi,
  'fr': localeFr,
  'hr': localeHr,
  'hu': localeHu,
  'id': localeId,
  'it': localeIt,
  'ja': localeJa,
  'ko': localeKo,
  'nb': localeNb,
  'nl': localeNl,
  'pl': localePl,
  'pt-BR': localePtBr,
  'pt': localePt,
  'ro': localeRo,
  'ru': localeRu,
  'si': localeSi,
  'sk': localeSk,
  'sl': localeSl,
  'sv': localeSv,
  'th': localeTh,
  'tr': localeTr,
  'uk': localeUk,
  'zh': localeZh
};
// --- End of Locale Imports ---


/**
 * Selects a pre-imported language file from the locale map.
 *
 * @param {string} langCode - The two-letter language code (e.g., 'en', 'es').
 * @returns {Promise<object>} A promise that resolves with the locale object.
 */
export const getLocale = async (langCode) => {
  const locale = allLocales[langCode];

  if (locale) {
    return locale;
  }

  console.warn(`Could not find locale for '${langCode}'. Defaulting to English.`);
  return allLocales['en']; // Default to English
};

function isMobileDevice() {
    const mobileRegex = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i;
    return mobileRegex.test(navigator.userAgent);
}

function isTouchDevice() {
    return ('ontouchstart' in window) || (navigator.maxTouchPoints > 0) || (navigator.msMaxTouchPoints > 0);
}

function isMobile() {
    return isMobileDevice() || isTouchDevice();
}

window.DatePicker = async function createDynamicDatePicker(element) {
    let todayButton = {
        content: element.dataset.nowButtonTxt,
        onClick: (dp) => {
            let date = new Date();
            dp.selectDate(date, {updateTime: true});
            dp.setViewDate(date);
        }
    };
    let isOnMobile = isMobile();
    let baseOpts = {
        isMobile: isOnMobile,
        dateFormat: element.dataset.dateFormat,
        timeFormat: element.dataset.timeFormat,
        timepicker: element.dataset.timepicker === 'true',
        toggleSelected: element.dataset.toggleSelected === 'true',
        autoClose: element.dataset.autoClose === 'true',
        buttons: element.dataset.clearButton === 'true' ? ['clear', todayButton] : [todayButton],
        locale: await getLocale(element.dataset.language),
        onSelect: ({date, formattedDate, datepicker}) => {
            const _event = new CustomEvent("change", {
                bubbles: true,
            });
            datepicker.$el.dispatchEvent(_event);
        }
    };
    const positionConfig = !isOnMobile ? {
        position({$datepicker, $target, $pointer, done}) {
            let popper = createPopper($target, $datepicker, {
                placement: 'bottom',
                modifiers: [
                    {
                        name: 'flip',
                        options: {
                            padding: {
                                top: 64
                            }
                        }
                    },
                    {
                        name: 'offset',
                        options: {
                            offset: [0, 20]
                        }
                    },
                    {
                        name: 'arrow',
                        options: {
                            element: $pointer
                        }
                     }
                ]
            });
            return function completeHide() {
                popper.destroy();
                done();
            };
        }
    } : {};
    let opts = {...baseOpts, ...positionConfig};
    if (element.dataset.value) {
        opts["selectedDates"] = [element.dataset.value];
        opts["startDate"] = [element.dataset.value];
    }
    return new AirDatepicker(element, opts);
};

window.MonthYearPicker = async function createDynamicDatePicker(element) {
    let todayButton = {
        content: element.dataset.nowButtonTxt,
        onClick: (dp) => {
            let date = new Date();
            dp.selectDate(date, {updateTime: true});
            dp.setViewDate(date);
        }
    };
    let isOnMobile = isMobile();
    let baseOpts = {
        isMobile: isOnMobile,
        view: 'months',
        minView: 'months',
        dateFormat: 'MMMM yyyy',
        toggleSelected: element.dataset.toggleSelected === 'true',
        autoClose: element.dataset.autoClose === 'true',
        buttons: element.dataset.clearButton === 'true' ? ['clear', todayButton] : [todayButton],
        locale: await getLocale(element.dataset.language),
        onSelect: ({date, formattedDate, datepicker}) => {
            const _event = new CustomEvent("change", {
                bubbles: true,
            });
            datepicker.$el.dispatchEvent(_event);
        }
    };
    const positionConfig = !isOnMobile ? {
        position({$datepicker, $target, $pointer, done}) {
            let popper = createPopper($target, $datepicker, {
                placement: 'bottom',
                modifiers: [
                    {
                        name: 'flip',
                        options: {
                            padding: {
                                top: 64
                            }
                        }
                    },
                    {
                        name: 'offset',
                        options: {
                            offset: [0, 20]
                        }
                    },
                    {
                        name: 'arrow',
                        options: {
                            element: $pointer
                        }
                    }
                ]
            });
            return function completeHide() {
                popper.destroy();
                done();
            };
        }
    } : {};
    let opts = {...baseOpts, ...positionConfig};
    if (element.dataset.value) {
        opts["selectedDates"] = [new Date(element.dataset.value + "T00:00:00")];
        opts["startDate"] = [new Date(element.dataset.value + "T00:00:00")];
    }
    return new AirDatepicker(element, opts);
};

window.YearPicker = async function createDynamicDatePicker(element) {
    let todayButton = {
        content: element.dataset.nowButtonTxt,
        onClick: (dp) => {
            let date = new Date();
            dp.selectDate(date, {updateTime: true});
            dp.setViewDate(date);
        }
    };
    let isOnMobile = isMobile();
    let baseOpts = {
        isMobile: isOnMobile,
        view: 'years',
        minView: 'years',
        dateFormat: 'yyyy',
        toggleSelected: element.dataset.toggleSelected === 'true',
        autoClose: element.dataset.autoClose === 'true',
        buttons: element.dataset.clearButton === 'true' ? ['clear', todayButton] : [todayButton],
        locale: await getLocale(element.dataset.language),
        onSelect: ({date, formattedDate, datepicker}) => {
            const _event = new CustomEvent("change", {
                bubbles: true,
            });
            datepicker.$el.dispatchEvent(_event);
        }
    };
    const positionConfig = !isOnMobile ? {
        position({$datepicker, $target, $pointer, done}) {
            let popper = createPopper($target, $datepicker, {
                placement: 'bottom',
                modifiers: [
                    {
                        name: 'flip',
                        options: {
                            padding: {
                                top: 64
                            }
                        }
                    },
                    {
                        name: 'offset',
                        options: {
                            offset: [0, 20]
                        }
                    },
                    {
                        name: 'arrow',
                        options: {
                            element: $pointer
                        }
                    }
                ]
            });
            return function completeHide() {
                popper.destroy();
                done();
            };
        }
    } : {};
    let opts = {...baseOpts, ...positionConfig};
    if (element.dataset.value) {
        opts["selectedDates"] = [new Date(element.dataset.value + "T00:00:00")];
        opts["startDate"] = [new Date(element.dataset.value + "T00:00:00")];
    }
    return new AirDatepicker(element, opts);
};
