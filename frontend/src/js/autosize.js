document.addEventListener("input", function (e) {
    // Check if the element that triggered the input event is a <textarea>
    if (e.target.tagName.toLowerCase() === "textarea") {

        // Reset height to 'auto' to allow the textarea to shrink
        e.target.style.height = "auto";

        // Set the height to its scrollHeight (the full height of the content)
        e.target.style.height = (e.target.scrollHeight + 5) + "px";
    }
}, false);