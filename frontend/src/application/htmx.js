import htmx from "htmx.org";
import _hyperscript from 'hyperscript.org/dist/_hyperscript.min';

_hyperscript.browserInit();

let modalEle = document.getElementById("modal");

if (modalEle) {
    const modal = new bootstrap.Modal(modalEle); // eslint-disable-line no-undef

    htmx.on("htmx:beforeSwap", (e) => {
        // Empty response targeting #dialog => hide the modal
        if (e.detail.target.id === "dialog" && !e.detail.xhr.response) {
            modal.hide();
            e.detail.shouldSwap = false;
        }
    });

    htmx.on("hidden.bs.modal", () => {
        document.getElementById("dialog").innerHTML = "";
    });
}

let successAudio = new Audio("/static/sounds/success.mp3");
let popAudio = new Audio("/static/sounds/pop.mp3");

htmx.on("paid", () => {
    successAudio.pause();
    successAudio.currentTime = 0;
    successAudio.play();
});

htmx.on("unpaid", () => {
    popAudio.pause();
    popAudio.currentTime = 0;
    popAudio.play();
});
