import { Game } from './game.js';

const canvas = document.getElementById('game');
const game = new Game(canvas);
game.start();
