/**
 * Converts ANY valid CSS color string (oklch, hex, hsl, etc.)
 * into a standard RGBA string that Chart.js can understand.
 * This method uses a canvas to force the browser to compute the color.
 * @param {string} colorString The color string to convert.
 * @returns {string} The computed 'rgba(r, g, b, a)' string.
 */
window.convertColorToRgba = function convertColorToRgba(colorString) {
    if (!colorString) return 'rgba(0,0,0,0.1)'; // Fallback

    console.log(colorString)

    // Create a 1x1 pixel canvas
    let canvas = document.createElement('canvas');
    canvas.width = 1;
    canvas.height = 1;
    let ctx = canvas.getContext('2d');

    // Set the fillStyle to the color string
    // The browser MUST parse the oklch string here
    ctx.fillStyle = colorString.trim();
    
    // Draw the pixel
    ctx.fillRect(0, 0, 1, 1);

    // Get the pixel data. This is ALWAYS returned as [R, G, B, A]
    // with values from 0-255.
    const data = ctx.getImageData(0, 0, 1, 1).data;
    
    // Convert the 0-255 alpha to a 0-1 float
    const a = data[3] / 255;

    console.log(data)

    // Return the standard rgba string
    return `rgba(${data[0]}, ${data[1]}, ${data[2]}, ${a})`;
}