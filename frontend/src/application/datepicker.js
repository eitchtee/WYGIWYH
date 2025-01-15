import AirDatepicker from 'air-datepicker';
import en from 'air-datepicker/locale/en';
import ptBr from 'air-datepicker/locale/pt-BR';
import {createPopper} from '@popperjs/core';

const locales = {
    'pt': ptBr,
    'en': en
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

window.DatePicker = function createDynamicDatePicker(element) {
    let isOnMobile = isMobile();

    let baseOpts = {
        isMobile: isOnMobile,
        timepicker: element.dataset.timepicker === 'true',
        autoClose: element.dataset.autoClose === 'true',
        buttons: element.dataset.clearButton === 'true' ? ['clear', 'today'] : ['today'],
        locale: locales[element.dataset.language],
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


window.MonthYearPicker = function createDynamicDatePicker(element) {
    let isOnMobile = isMobile();

    let baseOpts = {
        isMobile: isOnMobile,
        view: 'months',
        minView: 'months',
        dateFormat: 'MMMM yyyy',
        autoClose: element.dataset.autoClose === 'true',
        buttons: element.dataset.clearButton === 'true' ? ['clear', 'today'] : ['today'],
        locale: locales[element.dataset.language],
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
