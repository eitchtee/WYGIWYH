import { play } from "cuelume";


// User volume is stored as 0-10 (0 = muted); cuelume expects a 0-1 gain.
// Loudness is perceived logarithmically, so a linear mapping makes adjacent
// steps sound nearly identical. Squaring spreads them out (10 → 0dB, 5 → -12dB, 1 → -40dB).
// Pass `volume` to override the user's saved volume (e.g. to preview a new value).
window.playSound = (name, volume) => {
  volume ??= JSON.parse(document.getElementById("volume")?.textContent ?? "10");
  play(name, { volume: (volume / 10) ** 2 });
};
