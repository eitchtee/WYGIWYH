import autosize from "autosize/dist/autosize";

let autosize_textareas = document.querySelectorAll('textarea[autosize]');

autosize(autosize_textareas);

document.addEventListener('shown.bs.collapse', function () {
    autosize.update(autosize_textareas);
});

// UPDATE AUTOSIZE TEXT AREAS FOR FORMS INSIDE HTMX MODALS
document.addEventListener('updated.bs.modal', function () {
    let new_autosize_textareas = document.querySelectorAll('textarea[autosize]');
    autosize(new_autosize_textareas);
});

let charcount_textareas = document.querySelectorAll('textarea[countchars], input[countchars]');
charcount_textareas.forEach(formElement => {
    countTextArea(formElement);
    formElement.addEventListener('input', () => countTextArea(formElement));
});

function countTextArea(formElement) {
    let name = formElement.name;

    let max_chars = null;
    if (formElement.dataset.maxChars) {
        max_chars = formElement.dataset.maxChars;
    } else if (formElement.hasAttribute("maxlength")) {
        max_chars = formElement.getAttribute("maxlength");
    }

    let cur_chars = formElement.value.length;

    let wrapper = document.querySelector(`#charcount-${name}`);
    let char_counter = document.querySelector(`#char-counter-${name}`);
    let max_counter = document.querySelector(`#max-counter-${name}`);

    char_counter.textContent = cur_chars;
    if (max_counter) {
        max_counter.textContent = max_chars;
        wrapper.classList.remove("text-bg-warning", "text-bg-normal", "text-bg-success", "text-bg-danger");

        if (cur_chars === 0) {
            wrapper.classList.add("text-bg-secondary");
        } else if (cur_chars > max_chars - 1) {
            wrapper.classList.add("text-bg-danger");
        } else if (cur_chars < max_chars && cur_chars > max_chars * (90 / 100)) {
            wrapper.classList.add("text-bg-warning");
        } else if (cur_chars < max_chars - ((max_chars * (10 / 100)) - 1)) {
            wrapper.classList.add("text-bg-success");
        }
    }
}