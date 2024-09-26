// Import all of Bootstrap's JS
import * as bootstrap from 'bootstrap'; // eslint-disable-line no-unused-vars
window.bootstrap = bootstrap;

const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
[...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));  // eslint-disable-line no-undef


function initiateTooltips() {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl, {trigger: 'hover', container: 'body'}));  // eslint-disable-line no-undef
}

document.addEventListener('updated.bs.modal', initiateTooltips, false);
document.addEventListener('htmx:afterSwap', initiateTooltips, false);
initiateTooltips();


function initiateToasts() {
    const toastElList = document.querySelectorAll('.toast');
    const toastList = [...toastElList].map(toastEl => new bootstrap.Toast(toastEl));  // eslint-disable-line no-undef

    for (let i = 0; i < toastList.length; i++) {
        toastList[i].show();
        toastList[i]._element.addEventListener('hidden.bs.toast', (event) => {
            event.target.remove();
        });
    }
}

document.addEventListener('htmx:afterSwap', initiateToasts, false);
initiateToasts();

(function ($bs) {
    const CLASS_NAME = 'has-child-dropdown-show';
    $bs.Dropdown.prototype.toggle = function (_orginal) {
        return function () {
            document.querySelectorAll('.' + CLASS_NAME).forEach(function (e) {
                e.classList.remove(CLASS_NAME);
            });
            let dd = this._element.closest('.dropdown').parentNode.closest('.dropdown');
            for (; dd && dd !== document; dd = dd.parentNode.closest('.dropdown')) {
                dd.classList.add(CLASS_NAME);
            }
            return _orginal.call(this);
        };
    }($bs.Dropdown.prototype.toggle);

    document.querySelectorAll('.dropdown').forEach(function (dd) {
        dd.addEventListener('hide.bs.dropdown', function (e) {
            if (this.classList.contains(CLASS_NAME)) {
                this.classList.remove(CLASS_NAME);
                e.preventDefault();
            }
            e.stopPropagation(); // do not need pop in multi level mode
        });
    });

    // for hover
    document.querySelectorAll('.dropdown-hover, .dropdown-hover-all .dropdown').forEach(function (dd) {
        dd.addEventListener('mouseenter', function (e) {
            let toggle = e.target.querySelector(':scope>[data-bs-toggle="dropdown"]');
            if (!toggle.classList.contains('show')) {
                $bs.Dropdown.getOrCreateInstance(toggle).toggle();
                dd.classList.add(CLASS_NAME);
                $bs.Dropdown.clearMenus(e);
            }
        });
        dd.addEventListener('mouseleave', function (e) {
            let toggle = e.target.querySelector(':scope>[data-bs-toggle="dropdown"]');
            if (toggle.classList.contains('show')) {
                $bs.Dropdown.getOrCreateInstance(toggle).toggle();
            }
        });
    });
})(bootstrap);
