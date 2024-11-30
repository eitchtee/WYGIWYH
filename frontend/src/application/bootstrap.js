// Import all of Bootstrap's JS
import * as bootstrap from 'bootstrap'; // eslint-disable-line no-unused-vars
window.bootstrap = bootstrap;

function initiateToasts() {
    const toastElList = document.querySelectorAll('.toast');
    const toastList = [...toastElList].map(toastEl => new bootstrap.Toast(toastEl));  // eslint-disable-line no-undef

    for (let i = 0; i < toastList.length; i++) {
        if (toastList[i].isShown() === false) {
            toastList[i].show();
            toastList[i]._element.addEventListener('hidden.bs.toast', (event) => {
                event.target.remove();
            });
        }
    }
}

document.addEventListener('DOMContentLoaded', initiateToasts, false);
document.addEventListener('htmx:afterSwap', initiateToasts, false);
initiateToasts();
