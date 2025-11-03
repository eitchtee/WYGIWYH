import './js/_tooltip.js';
import 'bootstrap/js/dist/dropdown';
import Toast from 'bootstrap/js/dist/toast';
import 'bootstrap/js/dist/dropdown';
import 'bootstrap/js/dist/collapse';
import Offcanvas from 'bootstrap/js/dist/offcanvas';

window.Offcanvas = Offcanvas;


function initiateToasts() {
    const toastElList = document.querySelectorAll('.toasty');
    const toastList = [...toastElList].map(toastEl => new Toast(toastEl));  // eslint-disable-line no-undef

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