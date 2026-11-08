import TomSelect from "tom-select";
import * as Popper from "@popperjs/core";
import '../styles/_tom-select.scss'


// Mini version of cotton/transaction/item.html, used by TransactionSelect
function renderTransaction(data, escape, compact) {
    if (!data.date) {
        return `<div>${escape(data.text)}</div>`;
    }
    const kind = data.type === 'EX' ? 'expense' : 'income';
    const meta = [
        data.category && `<span><i class="fa-solid fa-icons fa-fw"></i>${escape(data.category)}</span>`,
        data.tags && data.tags.length && `<span><i class="fa-solid fa-hashtag fa-fw"></i>${escape(data.tags.join(', '))}</span>`,
        data.entities && data.entities.length && `<span><i class="fa-solid fa-user-group fa-fw"></i>${escape(data.entities.join(', '))}</span>`,
    ].filter(Boolean).join('');
    return `<div class="ts-tx ts-tx-${kind}${compact ? ' ts-tx-compact' : ''}">
        <i class="ts-tx-paid fa-regular ${data.is_paid ? 'fa-circle-check' : 'fa-circle'}"></i>
        <div class="ts-tx-main">
            <div class="ts-tx-date"><i class="fa-solid fa-calendar fa-fw"></i>${escape(data.date)}</div>
            <div class="ts-tx-desc">${escape(data.description || '')}</div>
            ${meta && !compact ? `<div class="ts-tx-meta">${meta}</div>` : ''}
        </div>
        <div class="ts-tx-side">
            <div class="ts-tx-amount text-${kind}">${escape(data.amount)}</div>
            <div class="ts-tx-account">${escape(data.account)}</div>
        </div>
    </div>`;
}

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
            if (this.settings.mode === 'multi') {
                this.setTextboxValue();
                this.refreshOptions(false);
            }
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

    if (element.dataset.render === 'transaction') {
        config.dataAttr = 'data'; // dataset key of the data-data attribute
        config.render.option = (data, escape) => renderTransaction(data, escape, false);
        config.render.item = (data, escape) => renderTransaction(data, escape, true);
    }

    if (element.dataset.load) {
        // The server searches and orders; don't let tom-select re-filter or re-sort the results
        config.score = () => () => 1;
        config.sortField = [{field: '$order'}];
        config.preload = 'focus';
        config.shouldLoad = () => true;
        config.load = function (query, callback) {
            let url = element.dataset.load + '?q=' + encodeURIComponent(query);
            fetch(url)
                .then(response => response.json())
                .then(json => {
                    // Drop results from the previous query, keeping the selected item
                    this.clearOptions();
                    callback(json);
                }).catch(() => {
                    callback();
                });
        };
    }

    // Create and return the TomSelect instance
    return new TomSelect(element, config);
};
