import AirDatepicker from 'air-datepicker';
import {createPopper} from '@popperjs/core';

/**
 * Dynamically imports a language file from the locale folder.
 *
 * @param {string} langCode - The two-letter language code (e.g., 'en', 'es').
 * @returns {Promise<object>} A promise that resolves with the default export of the language file.
 */
export const getLocale = async (langCode) => {
  try {
    const localeModule = await import(`air-datepicker/locale/${langCode}.js`);
    return localeModule.default;
  } catch (error) {
    console.warn(`Could not find locale for '${langCode}'. Defaulting to English.`);
    const englishModule = await import('air-datepicker/locale/en.js');
    return englishModule.default;
  }
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
