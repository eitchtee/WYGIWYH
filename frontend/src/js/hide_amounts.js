document.addEventListener('DOMContentLoaded', function () {
    function updateAmountsVisibility() {
        const amounts = document.querySelectorAll('.amount');
        const shouldHideAmounts = document.querySelector('#settings-hide-amounts');

        amounts.forEach(el => {
            if (shouldHideAmounts) {
                if (!el.classList.contains('revealed')) {
                    el.textContent = '•••••••••••';
                }
            } else {
                el.innerHTML = `<span>${el.dataset.originalSign}</span><span>${el.dataset.originalPrefix}</span><span>${el.dataset.originalAmount}</span><span>${el.dataset.originalSuffix}</span>`;
                el.classList.remove('revealed');
            }
        });
    }

    updateAmountsVisibility();

    document.body.addEventListener('htmx:afterSwap', updateAmountsVisibility);

    document.body.addEventListener('click', function (event) {
        const amountElement = event.target.closest('.amount');
        const shouldHideAmounts = document.querySelector('#settings-hide-amounts');

        if (amountElement && shouldHideAmounts) {
            if (amountElement.classList.contains('revealed')) {
                amountElement.textContent = '•••••••••••';
            } else {
                amountElement.innerHTML = `<span>${amountElement.dataset.originalSign}</span><span>${amountElement.dataset.originalPrefix}</span><span>${amountElement.dataset.originalAmount}</span><span>${amountElement.dataset.originalSuffix}</span>`;
            }
            amountElement.classList.toggle('revealed');
        }
    });
});
