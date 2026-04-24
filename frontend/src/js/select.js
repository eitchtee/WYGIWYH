import TomSelect from "tom-select";
import * as Popper from "@popperjs/core";
import '../styles/_tom-select.scss'


window.TomSelect = function createDynamicTomSelect(element) {
    const schedulePopperUpdate = function (instance) {
        // Wait for TomSelect DOM updates before recalculating dropdown position.
        requestAnimationFrame(() => {
            if (instance.popper) {
                instance.popper.update();
            }
        });
    };

    // Basic configuration
    const config = {
        plugins: {},
        maxOptions: null,

        // Extract 'create' option from data attribute
        create: element.dataset.create === 'true',
        copyClassesToDropdown: true,
        loadingClass: "ts-loading",
        allowEmptyOption: element.dataset.allowEmptyOption === 'true',
        render: {
            no_results: function () {
                return `<div class="no-results">${element.dataset.txtNoResults || 'No results...'}</div>`;
            },
            option_create: function (data, escape) {
                return `<div class="create">${element.dataset.txtCreate || 'Add'} <strong>${escape(data.input)}</strong>&hellip;</div>`;
            },
        },

        onInitialize: function () {
            this.popper = Popper.createPopper(this.control, this.dropdown, {
                placement: "bottom-start",
                modifiers: [
                    {
                        name: "offset",
                        options: {
                            offset: [0, 4],
                        },
                    },
                    {
                        name: "sameWidth",
                        enabled: true,
                        fn: ({ state }) => {
                            state.styles.popper.width = `${state.rects.reference.width}px`;
                        },
                        phase: "beforeWrite",
                        requires: ["computeStyles"],
                    },
                    {
                        name: 'flip',
                        options: {
                            fallbackPlacements: ['top-start'],
                        },
                    },
                ]

            });

        },
        onDropdownOpen: function () {
            schedulePopperUpdate(this);
        },
        onItemAdd: function () {
            schedulePopperUpdate(this);
        },
        onItemRemove: function () {
            schedulePopperUpdate(this);
        },
        onClear: function () {
            schedulePopperUpdate(this);
        },
    };

    if (element.dataset.checkboxes === 'true') {
        config.plugins.checkbox_options = {
            'checkedClassNames': ['ts-checked', "checkbox", "checkbox-xs"],
            'uncheckedClassNames': ['ts-checked', "checkbox", "checkbox-xs"],
        };
    }

    if (element.dataset.clearButton === 'true') {
        config.plugins.clear_button = {
            'title': element.dataset.txtClear || 'Clear',
        };
    }

    if (element.dataset.removeButton === 'true') {
        config.plugins.remove_button = {
            'title': element.dataset.txtRemove || 'Remove',
        };
    }

    if (element.dataset.load) {
        config.load = function (query, callback) {
            let url = element.dataset.load + '?q=' + encodeURIComponent(query);
            fetch(url)
                .then(response => response.json())
                .then(json => {
                    callback(json);
                }).catch(() => {
                    callback();
                });
        };
    }

    // Create and return the TomSelect instance
    return new TomSelect(element, config);
};
