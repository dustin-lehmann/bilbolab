import {Babylon, BabylonContainer} from "./babylon.js";
import {Engine} from "@babylonjs/core";

// once the DOM is ready, kick everything off
window.addEventListener("DOMContentLoaded", () => {
    const canvas = document.getElementById("renderCanvas");
    // an empty config; you can pass your own here
    const babylon_container = new BabylonContainer('babylon', canvas, {})
});
