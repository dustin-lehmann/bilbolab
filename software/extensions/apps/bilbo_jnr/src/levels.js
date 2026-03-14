/**
 * BILBO Jump & Run — Level Definitions
 *
 * 5 discrete levels, each with unique parallax backgrounds, ground, platforms,
 * and atmospheric effects inspired by Middle-earth locations.
 *
 * 1. The Shire — Lush daylight, rolling green hills, rivers
 * 2. Misty Mountains — Snowy peaks, blizzard, grey skies
 * 3. Moria — Dark caves, torches, glowing eyes
 * 4. Mordor — Mount Doom, red sky, embers, ground shake
 * 5. Lothlorien — Golden trees, ethereal light, fireflies
 */

import { VISUAL } from './dynamics.js';
import {
  SCALE, ParallaxLayer, hash, roundRect,
  drawBilbo, drawHUD, drawTokens, drawParticles, drawSpeedLines,
  setTime,
} from './renderer_lotr.js';

// Re-export shared functions
export {
  drawBilbo, drawHUD, drawTokens, drawParticles, drawSpeedLines,
  setTime, SCALE,
};

let _time = 0;
export function setLevelTime(t) { _time = t; }

// =====================================================================================================================
// 1. THE SHIRE
// =====================================================================================================================

const shire = {
  name: 'The Shire',
  index: 1,

  createParallaxLayers() {
    // Layer 0: Bright blue sky with fluffy clouds
    const sky = new ParallaxLayer(0, (ctx, ox, cw, ch) => {
      const grad = ctx.createLinearGradient(0, 0, 0, ch);
      grad.addColorStop(0, '#4a8ac7');
      grad.addColorStop(0.25, '#6ba3d6');
      grad.addColorStop(0.45, '#8dbce0');
      grad.addColorStop(0.65, '#b0d4ea');
      grad.addColorStop(0.80, '#d4e8c8');
      grad.addColorStop(1.0, '#a8cc88');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, cw, ch);

      // Sun
      const sunX = cw * 0.8;
      const sunY = ch * 0.12;
      const sunGlow = ctx.createRadialGradient(sunX, sunY, 8, sunX, sunY, 120);
      sunGlow.addColorStop(0, 'rgba(255, 240, 180, 0.9)');
      sunGlow.addColorStop(0.15, 'rgba(255, 230, 150, 0.4)');
      sunGlow.addColorStop(0.5, 'rgba(255, 220, 120, 0.1)');
      sunGlow.addColorStop(1, 'rgba(255, 220, 120, 0)');
      ctx.fillStyle = sunGlow;
      ctx.beginPath();
      ctx.arc(sunX, sunY, 120, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#fff8d0';
      ctx.beginPath();
      ctx.arc(sunX, sunY, 14, 0, Math.PI * 2);
      ctx.fill();

      // Fluffy clouds
      _drawShireClouds(ctx, cw, ch, _time);
    });

    // Layer 1: Far rolling hills — very distant, pale green
    const farHills = new ParallaxLayer(0.05, (ctx, ox, cw, ch) => {
      _drawRollingHills(ctx, ox, cw, ch, {
        seed: 100, baseY: ch * 0.72, amplitude: 60, wavelength: 200,
        color1: '#8ab878', color2: '#7aaa68', fogAlpha: 0.15,
      });
    });

    // Layer 2: Mid hills with occasional hobbit-holes
    const midHills = new ParallaxLayer(0.15, (ctx, ox, cw, ch) => {
      _drawRollingHills(ctx, ox, cw, ch, {
        seed: 250, baseY: ch * 0.80, amplitude: 45, wavelength: 150,
        color1: '#6a9a50', color2: '#5a8a40', fogAlpha: 0.08,
      });
      _drawHobbitHoles(ctx, ox, cw, ch * 0.80);
    });

    // Layer 3: Near hills with hedgerows — in front of hobbit holes, partially covering them
    const nearHills = new ParallaxLayer(0.35, (ctx, ox, cw, ch) => {
      _drawRollingHills(ctx, ox, cw, ch, {
        seed: 450, baseY: ch * 0.82, amplitude: 35, wavelength: 100,
        color1: '#4a8030', color2: '#3a7020', fogAlpha: 0,
      });
      _drawHedgerows(ctx, ox, cw, ch * 0.82);
    });

    // Layer 4: River that meanders across the foreground
    const river = new ParallaxLayer(0.5, (ctx, ox, cw, ch) => {
      _drawShireRiver(ctx, ox, cw, ch * 0.88, _time);
    });

    return [sky, farHills, midHills, nearHills, river];
  },

  drawGround(ctx, cameraX, canvasW, canvasH, groundY) {
    // Lush green earth
    const earthGrad = ctx.createLinearGradient(0, groundY, 0, canvasH);
    earthGrad.addColorStop(0, '#4a7a30');
    earthGrad.addColorStop(0.1, '#3a6a20');
    earthGrad.addColorStop(0.4, '#2a5a14');
    earthGrad.addColorStop(1, '#1a4a0a');
    ctx.fillStyle = earthGrad;
    ctx.fillRect(0, groundY, canvasW, canvasH - groundY);

    // Dense grass top
    const grassStart = Math.floor(cameraX * SCALE / 3);
    const grassEnd = grassStart + Math.ceil(canvasW / 3) + 1;
    for (let i = grassStart; i < grassEnd; i++) {
      const gx = i * 3 - cameraX * SCALE;
      const h = hash(i * 41 + 2222);
      const grassH = 2 + Math.floor(h * 5);
      const shade = 0.3 + h * 0.5;
      ctx.fillStyle = `rgba(${60 + shade * 50 | 0}, ${110 + shade * 50 | 0}, ${30 + shade * 25 | 0}, 1)`;
      ctx.fillRect(Math.floor(gx), Math.floor(groundY - grassH), 3, grassH + 1);
    }

    // Wildflowers
    for (let i = grassStart; i < grassEnd; i++) {
      const h = hash(i * 61 + 8888);
      if (h > 0.88) {
        const gx = i * 3 - cameraX * SCALE;
        const fy = groundY - 3 - h * 6;
        const colors = ['#e8d040', '#e06080', '#d080e0', '#60a0e0', '#ff8040'];
        ctx.fillStyle = colors[Math.floor(hash(i * 73 + 9999) * colors.length)];
        ctx.fillRect(Math.floor(gx), Math.floor(fy), 2, 2);
        // Stem
        ctx.fillStyle = '#3a7020';
        ctx.fillRect(Math.floor(gx), Math.floor(fy + 2), 1, 3);
      }
    }

    // Dirt path patches
    const patchStart = Math.floor(cameraX * SCALE / 50);
    const patchEnd = patchStart + Math.ceil(canvasW / 50) + 2;
    for (let i = patchStart; i < patchEnd; i++) {
      const h = hash(i * 89 + 3333);
      if (h > 0.65) {
        const px = i * 50 - cameraX * SCALE + hash(i * 97 + 4444) * 20;
        const pw = 12 + hash(i * 101 + 5555) * 35;
        ctx.fillStyle = `rgba(140, 120, 80, ${0.12 + h * 0.12})`;
        ctx.fillRect(Math.floor(px), groundY + 1, Math.floor(pw), 3);
      }
    }
  },

  drawPlatform(ctx, platform, cameraX, groundY) {
    const px = platform.x * SCALE - cameraX * SCALE;
    const pw = platform.w * SCALE;
    const py = groundY - platform.y * SCALE;
    const ph = 18;
    const isBoost = platform.boost;

    // Wooden bridge/fence style pillars
    const pillarW = 5;
    ctx.fillStyle = isBoost ? 'rgba(100, 80, 40, 0.4)' : 'rgba(90, 70, 45, 0.3)';
    ctx.fillRect(px + 4, py + ph, pillarW, groundY - py - ph);
    ctx.fillRect(px + pw - 4 - pillarW, py + ph, pillarW, groundY - py - ph);

    if (isBoost) {
      // Party Tree platform — festive wood with lanterns
      const grad = ctx.createLinearGradient(px, py, px, py + ph);
      grad.addColorStop(0, '#8a7040');
      grad.addColorStop(0.5, '#7a6035');
      grad.addColorStop(1, '#6a502a');
      ctx.fillStyle = grad;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

      // Festive colored top edge
      ctx.fillStyle = '#c8a848';
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 3);

      // Little lanterns
      for (let x = px + 12; x < px + pw - 12; x += 20) {
        const lanternPulse = 0.7 + 0.3 * Math.sin(_time * 3 + x * 0.1);
        ctx.shadowColor = `rgba(255, 200, 80, ${lanternPulse})`;
        ctx.shadowBlur = 8;
        ctx.fillStyle = `rgba(255, 210, 100, ${lanternPulse})`;
        ctx.fillRect(Math.floor(x), Math.floor(py - 4), 4, 4);
        ctx.shadowBlur = 0;
      }
    } else {
      // Cobblestone/wooden bridge
      const grad = ctx.createLinearGradient(px, py, px, py + ph);
      grad.addColorStop(0, '#8a7a5a');
      grad.addColorStop(0.4, '#7a6a4a');
      grad.addColorStop(1, '#6a5a3a');
      ctx.fillStyle = grad;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

      // Wood plank lines (index-based to avoid flickering)
      const pseed = Math.floor(platform.x * 1000);
      ctx.fillStyle = 'rgba(50, 40, 25, 0.25)';
      let xOff = 8;
      for (let i = 0; xOff < pw - 5; i++) {
        ctx.fillRect(Math.floor(px + xOff), Math.floor(py), 1, ph);
        xOff += 12 + hash(i * 31 + pseed + 777) * 8;
      }

      // Top railing
      ctx.fillStyle = '#9a8a68';
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 2);

      // Moss
      ctx.fillStyle = 'rgba(60, 100, 30, 0.3)';
      for (let mi = 0; mi * 7 + 3 < pw - 5; mi++) {
        const h = hash(mi * 53 + pseed + 456);
        if (h > 0.5) {
          ctx.fillRect(Math.floor(px + 3 + mi * 7), Math.floor(py + ph - 3), Math.floor(3 + h * 4), 3);
        }
      }
    }
  },

  drawAtmosphere(ctx, cw, ch, groundY, gameTime) {
    // Butterflies
    for (let i = 0; i < 6; i++) {
      const bx = (hash(i * 31 + 1111) * cw + Math.sin(gameTime * 0.8 + i * 4) * 40) % cw;
      const by = groundY - 40 - hash(i * 47 + 2222) * (ch * 0.3) + Math.sin(gameTime * 1.5 + i * 3) * 15;
      const wingPhase = Math.sin(gameTime * 8 + i * 5);
      const wingW = 3 * Math.abs(wingPhase);

      ctx.fillStyle = i % 2 === 0 ? 'rgba(255, 200, 80, 0.6)' : 'rgba(220, 120, 180, 0.6)';
      ctx.fillRect(Math.floor(bx - wingW), Math.floor(by), Math.ceil(wingW), 2);
      ctx.fillRect(Math.floor(bx + 1), Math.floor(by), Math.ceil(wingW), 2);
      ctx.fillStyle = 'rgba(60, 40, 20, 0.5)';
      ctx.fillRect(Math.floor(bx), Math.floor(by), 1, 2);
    }

    // Soft morning haze near ground
    const hazeGrad = ctx.createLinearGradient(0, groundY - 40, 0, groundY + 5);
    hazeGrad.addColorStop(0, 'rgba(180, 210, 230, 0)');
    hazeGrad.addColorStop(0.6, `rgba(180, 210, 230, ${0.04 + 0.02 * Math.sin(gameTime * 0.3)})`);
    hazeGrad.addColorStop(1, `rgba(180, 210, 230, ${0.06 + 0.03 * Math.sin(gameTime * 0.4)})`);
    ctx.fillStyle = hazeGrad;
    ctx.fillRect(0, groundY - 40, cw, 45);

    // Dandelion seeds floating
    for (let i = 0; i < 8; i++) {
      const dx = (hash(i * 71 + 3333) * cw * 2 + gameTime * (10 + i * 3)) % (cw + 200) - 100;
      const dy = ch * 0.3 + hash(i * 83 + 4444) * (ch * 0.4) + Math.sin(gameTime * 0.6 + i * 2) * 20;
      const alpha = 0.2 + 0.15 * Math.sin(gameTime * 0.5 + i);
      ctx.fillStyle = `rgba(255, 255, 240, ${alpha})`;
      ctx.fillRect(Math.floor(dx), Math.floor(dy), 2, 2);
      // Tiny seed lines
      ctx.strokeStyle = `rgba(255, 255, 240, ${alpha * 0.5})`;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(dx, dy);
      ctx.lineTo(dx - 2, dy - 3);
      ctx.moveTo(dx + 1, dy);
      ctx.lineTo(dx + 3, dy - 2);
      ctx.stroke();
    }
  },

  platforms: [
    { x: -1.0, w: 2.5, y: 0, boost: false },
    { x: 2.0, w: 0.6, y: 0.15, boost: false },
    { x: 3.0, w: 0.5, y: 0.25, boost: false },
    { x: 3.8, w: 0.8, y: 0, boost: false },
    { x: 5.0, w: 0.4, y: 0.2, boost: false },
    { x: 5.6, w: 0.4, y: 0.35, boost: false },
    { x: 6.5, w: 0.6, y: 0, boost: true },
    { x: 7.5, w: 0.5, y: 0.4, boost: false },
    { x: 8.5, w: 1.0, y: 0, boost: false },
    { x: 10.0, w: 0.5, y: 0.15, boost: false },
    { x: 10.8, w: 0.5, y: 0.3, boost: false },
    { x: 11.8, w: 0.7, y: 0, boost: false },
  ],

  tokens: [
    { x: 2.3, y: 0.28, collected: false, collectTime: 0 },
    { x: 3.25, y: 0.38, collected: false, collectTime: 0 },
    { x: 5.8, y: 0.48, collected: false, collectTime: 0 },
    { x: 6.8, y: 0.7, collected: false, collectTime: 0 },
    { x: 7.75, y: 0.53, collected: false, collectTime: 0 },
    { x: 10.25, y: 0.28, collected: false, collectTime: 0 },
  ],

  enemies: [],

  arrowPickups: [
    { x: 1.5, y: 0.05, count: 3 },
    { x: 4.2, y: 0.05, count: 3 },
    { x: 6.8, y: 0.7, count: 3 },
    { x: 9.0, y: 0.05, count: 3 },
    { x: 11.0, y: 0.05, count: 3 },
  ],
};

// --- Shire helpers ---

function _drawShireClouds(ctx, cw, ch, time) {
  for (let i = 0; i < 8; i++) {
    const baseX = (hash(i * 97 + 100) * cw * 1.5 + time * (2 + hash(i * 113 + 200) * 3)) % (cw + 400) - 200;
    const baseY = ch * (0.08 + hash(i * 131 + 300) * 0.2);
    const scale = 0.6 + hash(i * 149 + 400) * 0.8;

    ctx.fillStyle = `rgba(255, 255, 255, ${0.5 + hash(i * 157 + 500) * 0.3})`;
    // Cluster of overlapping circles
    for (let j = 0; j < 5; j++) {
      const cx = baseX + (j - 2) * 18 * scale + hash(i * 163 + j * 7 + 600) * 8;
      const cy = baseY + hash(i * 173 + j * 11 + 700) * 8 - 4;
      const r = (12 + hash(i * 181 + j * 13 + 800) * 14) * scale;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function _drawRollingHills(ctx, offsetX, cw, ch, config) {
  const { seed, baseY, amplitude, wavelength, color1, color2, fogAlpha } = config;
  const step = 4;
  const startX = Math.floor(offsetX * SCALE / step) * step - step;
  const endX = startX + cw + step * 4;

  ctx.beginPath();
  ctx.moveTo(-50, ch);

  for (let x = startX; x <= endX; x += step) {
    const worldI = x / wavelength;
    const h1 = Math.sin(worldI * 2.3 + seed * 0.1) * 0.4;
    const h2 = Math.sin(worldI * 4.7 + seed * 0.3) * 0.25;
    const h3 = Math.sin(worldI * 1.1 + seed * 0.7) * 0.35;
    const hillH = (h1 + h2 + h3) * amplitude;
    ctx.lineTo(x - startX, baseY - Math.max(0, hillH));
  }
  ctx.lineTo(cw + 100, ch);
  ctx.closePath();

  const grad = ctx.createLinearGradient(0, baseY - amplitude, 0, baseY + 20);
  grad.addColorStop(0, color1);
  grad.addColorStop(1, color2);
  ctx.fillStyle = grad;
  ctx.fill();

  if (fogAlpha > 0) {
    const fog = ctx.createLinearGradient(0, baseY - amplitude * 0.5, 0, baseY);
    fog.addColorStop(0, `rgba(180, 210, 230, 0)`);
    fog.addColorStop(1, `rgba(180, 210, 230, ${fogAlpha})`);
    ctx.fillStyle = fog;
    ctx.fillRect(0, baseY - amplitude, cw + 100, amplitude + 20);
  }
}

function _drawHobbitHoles(ctx, offsetX, cw, baseY) {
  const spacing = 250;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 67 + 5000);
    if (h < 0.4) continue;
    const hx = i * spacing + hash(i * 79 + 5100) * 60;
    const hillH = 15 + hash(i * 83 + 5200) * 20;

    // Green mound
    ctx.fillStyle = '#5a9038';
    ctx.beginPath();
    ctx.arc(hx, baseY, hillH * 1.5, Math.PI, 0);
    ctx.fill();

    // Door (round)
    const doorR = 5 + h * 3;
    ctx.fillStyle = '#6a4020';
    ctx.beginPath();
    ctx.arc(hx, baseY - doorR * 0.3, doorR, 0, Math.PI * 2);
    ctx.fill();

    // Door frame
    ctx.strokeStyle = '#4a2a10';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(hx, baseY - doorR * 0.3, doorR, 0, Math.PI * 2);
    ctx.stroke();

    // Window
    if (h > 0.6) {
      ctx.fillStyle = '#e8d080';
      ctx.beginPath();
      ctx.arc(hx + hillH, baseY - hillH * 0.4, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function _drawHedgerows(ctx, offsetX, cw, baseY) {
  const spacing = 35;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 47 + 6000);
    if (h > 0.5) continue;
    const hx = i * spacing;
    const hh = 6 + h * 10;

    ctx.fillStyle = `rgba(${50 + h * 30 | 0}, ${90 + h * 30 | 0}, ${25 + h * 15 | 0}, 0.8)`;
    ctx.beginPath();
    ctx.arc(hx, baseY - hh * 0.3, hh, 0, Math.PI * 2);
    ctx.fill();
  }
}

function _drawShireRiver(ctx, offsetX, cw, groundY, time) {
  // Meandering river below the ground line — visible as gaps in the terrain
  const riverSections = [];
  const spacing = 400;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 43 + 7000);
    if (h > 0.35) continue;
    const rx = i * spacing + hash(i * 53 + 7100) * 100;
    const rw = 40 + h * 60;

    // River water
    const shimmer = 0.6 + 0.2 * Math.sin(time * 2 + rx * 0.01);
    const riverGrad = ctx.createLinearGradient(rx, groundY - 2, rx, groundY + 8);
    riverGrad.addColorStop(0, `rgba(80, 140, 200, ${shimmer * 0.4})`);
    riverGrad.addColorStop(0.5, `rgba(60, 120, 180, ${shimmer * 0.5})`);
    riverGrad.addColorStop(1, `rgba(40, 100, 160, ${shimmer * 0.3})`);
    ctx.fillStyle = riverGrad;
    ctx.fillRect(Math.floor(rx), groundY - 1, Math.floor(rw), 6);

    // Sparkles on water
    for (let s = 0; s < 4; s++) {
      const sx = rx + hash(i * 61 + s * 71 + 7200) * rw;
      const sparkle = Math.sin(time * 4 + sx * 0.05 + s) * 0.5 + 0.5;
      if (sparkle > 0.7) {
        ctx.fillStyle = `rgba(220, 240, 255, ${sparkle * 0.4})`;
        ctx.fillRect(Math.floor(sx), groundY, 2, 1);
      }
    }
  }
}

// =====================================================================================================================
// 2. MISTY MOUNTAINS
// =====================================================================================================================

const mistyMountains = {
  name: 'Misty Mountains',
  index: 2,

  createParallaxLayers() {
    // Layer 0: Overcast grey sky
    const sky = new ParallaxLayer(0, (ctx, ox, cw, ch) => {
      const grad = ctx.createLinearGradient(0, 0, 0, ch);
      grad.addColorStop(0, '#3a4050');
      grad.addColorStop(0.2, '#4a5565');
      grad.addColorStop(0.4, '#5a6575');
      grad.addColorStop(0.6, '#6a7585');
      grad.addColorStop(0.8, '#7a8595');
      grad.addColorStop(1.0, '#8a95a0');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, cw, ch);

      // Faint clouds/mist bands
      for (let i = 0; i < 5; i++) {
        const cy = ch * (0.1 + i * 0.12) + Math.sin(_time * 0.2 + i * 3) * 8;
        const alpha = 0.04 + hash(i * 31 + 111) * 0.06;
        ctx.fillStyle = `rgba(180, 190, 200, ${alpha})`;
        ctx.fillRect(0, cy, cw, 20 + hash(i * 41 + 222) * 30);
      }
    });

    // Layer 1: Massive distant peaks — pale, enormous
    const farPeaks = new ParallaxLayer(0.06, (ctx, ox, cw, ch) => {
      _drawMistyPeaks(ctx, ox, cw, ch, {
        seed: 55, baseY: ch * 0.65, minH: 200, maxH: 450, peakW: 350,
        color: '#5a6570', snowAlpha: 0.35,
      });
    });

    // Layer 2: Mid-range peaks with snow
    const midPeaks = new ParallaxLayer(0.15, (ctx, ox, cw, ch) => {
      _drawMistyPeaks(ctx, ox, cw, ch, {
        seed: 170, baseY: ch * 0.75, minH: 140, maxH: 320, peakW: 250,
        color: '#4a5560', snowAlpha: 0.5,
      });
      // Heavy mist between peaks
      const mistGrad = ctx.createLinearGradient(0, ch * 0.55, 0, ch * 0.82);
      mistGrad.addColorStop(0, 'rgba(100, 110, 125, 0)');
      mistGrad.addColorStop(0.5, 'rgba(100, 110, 125, 0.2)');
      mistGrad.addColorStop(1, 'rgba(100, 110, 125, 0.45)');
      ctx.fillStyle = mistGrad;
      ctx.fillRect(0, ch * 0.55, cw, ch * 0.27);
    });

    // Layer 3: Near rocky ridges
    const nearRidges = new ParallaxLayer(0.3, (ctx, ox, cw, ch) => {
      _drawMistyPeaks(ctx, ox, cw, ch, {
        seed: 340, baseY: ch * 0.85, minH: 60, maxH: 180, peakW: 160,
        color: '#3a4550', snowAlpha: 0.25,
      });
    });

    // Layer 4: Foreground rocky terrain
    const rocks = new ParallaxLayer(0.5, (ctx, ox, cw, ch) => {
      _drawRockyTerrain(ctx, ox, cw, ch * 0.88);
    });

    return [sky, farPeaks, midPeaks, nearRidges, rocks];
  },

  drawGround(ctx, cameraX, canvasW, canvasH, groundY) {
    // Rocky/snowy ground
    const earthGrad = ctx.createLinearGradient(0, groundY, 0, canvasH);
    earthGrad.addColorStop(0, '#5a5e64');
    earthGrad.addColorStop(0.15, '#4a4e54');
    earthGrad.addColorStop(0.4, '#3a3e44');
    earthGrad.addColorStop(1, '#2a2e34');
    ctx.fillStyle = earthGrad;
    ctx.fillRect(0, groundY, canvasW, canvasH - groundY);

    // Snow-dusted top edge
    const snowStart = Math.floor(cameraX * SCALE / 4);
    const snowEnd = snowStart + Math.ceil(canvasW / 4) + 1;
    for (let i = snowStart; i < snowEnd; i++) {
      const sx = i * 4 - cameraX * SCALE;
      const h = hash(i * 37 + 8000);
      const snowH = 1 + Math.floor(h * 3);
      ctx.fillStyle = `rgba(${200 + h * 40 | 0}, ${205 + h * 40 | 0}, ${215 + h * 30 | 0}, ${0.5 + h * 0.3})`;
      ctx.fillRect(Math.floor(sx), Math.floor(groundY - snowH), 4, snowH + 1);
    }

    // Occasional rocks
    const rockStart = Math.floor(cameraX * SCALE / 20);
    const rockEnd = rockStart + Math.ceil(canvasW / 20) + 2;
    for (let i = rockStart; i < rockEnd; i++) {
      const h = hash(i * 53 + 8500);
      if (h > 0.7) {
        const rx = i * 20 - cameraX * SCALE;
        const rw = 6 + h * 12;
        const rh = 3 + h * 6;
        ctx.fillStyle = `rgba(70, 75, 80, ${0.4 + h * 0.3})`;
        ctx.fillRect(Math.floor(rx), Math.floor(groundY - rh), Math.floor(rw), Math.floor(rh));
      }
    }
  },

  drawPlatform(ctx, platform, cameraX, groundY) {
    const px = platform.x * SCALE - cameraX * SCALE;
    const pw = platform.w * SCALE;
    const py = groundY - platform.y * SCALE;
    const ph = 20;
    const isBoost = platform.boost;

    // Ice/stone pillars
    ctx.fillStyle = isBoost ? 'rgba(100, 140, 180, 0.3)' : 'rgba(80, 85, 90, 0.25)';
    ctx.fillRect(px + 4, py + ph, 5, groundY - py - ph);
    ctx.fillRect(px + pw - 9, py + ph, 5, groundY - py - ph);

    if (isBoost) {
      // Icy crystal platform
      const grad = ctx.createLinearGradient(px, py, px, py + ph);
      grad.addColorStop(0, '#8ab8d8');
      grad.addColorStop(0.5, '#6a98b8');
      grad.addColorStop(1, '#4a7898');
      ctx.fillStyle = grad;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

      // Crystalline glow
      ctx.shadowColor = '#a0d0ff';
      ctx.shadowBlur = 15;
      ctx.fillStyle = '#c0e0ff';
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 2);
      ctx.shadowBlur = 0;

      // Ice crystal facets
      ctx.fillStyle = 'rgba(180, 220, 255, 0.2)';
      for (let x = px + 6; x < px + pw - 6; x += 14) {
        ctx.beginPath();
        ctx.moveTo(x, py + 3);
        ctx.lineTo(x + 4, py + ph - 2);
        ctx.lineTo(x + 8, py + 3);
        ctx.closePath();
        ctx.fill();
      }
    } else {
      // Grey mountain stone
      const grad = ctx.createLinearGradient(px, py, px, py + ph);
      grad.addColorStop(0, '#6a6e74');
      grad.addColorStop(0.3, '#5a5e64');
      grad.addColorStop(1, '#4a4e54');
      ctx.fillStyle = grad;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

      // Snow on top
      ctx.fillStyle = 'rgba(210, 215, 225, 0.5)';
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 3);

      // Stone cracks (index-based)
      const pseed = Math.floor(platform.x * 1000);
      ctx.fillStyle = 'rgba(30, 32, 36, 0.25)';
      ctx.fillRect(Math.floor(px), Math.floor(py + ph * 0.5), Math.ceil(pw), 1);
      let crackOff = 12;
      for (let ci = 0; crackOff < pw - 8; ci++) {
        ctx.fillRect(Math.floor(px + crackOff), Math.floor(py), 1, ph);
        crackOff += 18 + hash(ci * 51 + pseed + 999) * 10;
      }

      // Icicles hanging (index-based)
      let iceOff = 8;
      for (let ii = 0; iceOff < pw - 5; ii++) {
        const fx = px + iceOff;
        const icicleH = 4 + hash(ii * 43 + pseed + 5678) * 8;
        ctx.fillStyle = 'rgba(180, 200, 220, 0.35)';
        ctx.beginPath();
        ctx.moveTo(fx - 1, py + ph);
        ctx.lineTo(fx + 1, py + ph);
        ctx.lineTo(fx, py + ph + icicleH);
        ctx.closePath();
        ctx.fill();
        iceOff += 10 + hash(ii * 37 + pseed + 1234) * 8;
      }
    }
  },

  drawAtmosphere(ctx, cw, ch, groundY, gameTime, cameraX = 0) {
    // Heavy snowfall — blizzard (world-space so snow stays in place)
    const camPx = cameraX * SCALE;
    for (let i = 0; i < 250; i++) {
      const windSway = Math.sin(gameTime * 0.6 + i * 0.3) * 40 + Math.sin(gameTime * 1.1 + i * 0.7) * 15;
      // World-space X: snow has fixed world positions, offset by camera
      const worldX = hash(i * 31 + 9000) * cw * 3 + gameTime * (20 + hash(i * 41 + 9100) * 35) + windSway;
      const sx = ((worldX - camPx * 0.7) % (cw + 200) + cw + 200) % (cw + 200) - 100;
      const sy = (hash(i * 53 + 9200) * ch + gameTime * (40 + hash(i * 61 + 9300) * 60)) % ch;
      const size = 1 + hash(i * 71 + 9400) * 3;
      const alpha = 0.25 + hash(i * 79 + 9500) * 0.55;
      ctx.fillStyle = `rgba(220, 225, 235, ${alpha})`;
      ctx.fillRect(Math.floor(sx), Math.floor(sy), Math.ceil(size), Math.ceil(size));
    }

    // Snow streaks for blizzard feel (world-space)
    ctx.strokeStyle = 'rgba(200, 210, 225, 0.06)';
    ctx.lineWidth = 1;
    for (let i = 0; i < 30; i++) {
      const worldX = hash(i * 43 + 9550) * cw * 2 + gameTime * 50;
      const sx = ((worldX - camPx * 0.7) % (cw + 200) + cw + 200) % (cw + 200) - 100;
      const sy = (hash(i * 59 + 9560) * ch + gameTime * 80) % ch;
      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.lineTo(sx + 15 + hash(i * 67 + 9570) * 20, sy + 8 + hash(i * 71 + 9580) * 10);
      ctx.stroke();
    }

    // Wind mist streaks
    for (let i = 0; i < 8; i++) {
      const mx = (hash(i * 97 + 9600) * cw * 2 + gameTime * (20 + i * 8)) % (cw + 400) - 200;
      const my = groundY - 20 - hash(i * 107 + 9700) * 120;
      const mw = 120 + hash(i * 113 + 9800) * 200;
      const alpha = 0.04 + 0.04 * Math.sin(gameTime * 0.4 + i * 2);
      const grad = ctx.createRadialGradient(mx + mw / 2, my, 0, mx + mw / 2, my, mw / 2);
      grad.addColorStop(0, `rgba(180, 190, 210, ${alpha})`);
      grad.addColorStop(1, 'rgba(180, 190, 210, 0)');
      ctx.fillStyle = grad;
      ctx.fillRect(mx, my - 30, mw, 60);
    }

    // Heavy ground fog
    const fogGrad = ctx.createLinearGradient(0, groundY - 50, 0, groundY + 10);
    fogGrad.addColorStop(0, 'rgba(160, 170, 190, 0)');
    fogGrad.addColorStop(0.5, `rgba(160, 170, 190, ${0.06 + 0.03 * Math.sin(gameTime * 0.3)})`);
    fogGrad.addColorStop(1, `rgba(140, 150, 170, ${0.1 + 0.04 * Math.sin(gameTime * 0.5)})`);
    ctx.fillStyle = fogGrad;
    ctx.fillRect(0, groundY - 50, cw, 60);

    // Overall atmospheric haze
    const hazeAlpha = 0.03 + 0.015 * Math.sin(gameTime * 0.2);
    ctx.fillStyle = `rgba(150, 160, 180, ${hazeAlpha})`;
    ctx.fillRect(0, 0, cw, ch);
  },

  platforms: [
    // --- Opening ground section ---
    { x: -1.0, w: 2.5, y: 0, boost: false },
    { x: 2.0, w: 0.5, y: 0.18, boost: false },
    { x: 2.8, w: 0.4, y: 0.32, boost: false },
    { x: 3.5, w: 0.6, y: 0.15, boost: false },

    // --- First climb: staircase up the mountain face ---
    { x: 4.2, w: 0.5, y: 0.30, boost: false },
    { x: 4.9, w: 0.4, y: 0.55, boost: false },
    { x: 4.3, w: 0.4, y: 0.80, boost: false },
    { x: 5.0, w: 0.5, y: 1.05, boost: false },
    { x: 4.4, w: 0.4, y: 1.30, boost: false },
    { x: 5.1, w: 0.5, y: 1.55, boost: true },   // boost to reach the peak

    // --- Mountain peak ledge ---
    { x: 5.8, w: 0.8, y: 1.80, boost: false },

    // --- Descent: staggered platforms down ---
    { x: 6.8, w: 0.4, y: 1.50, boost: false },
    { x: 7.4, w: 0.4, y: 1.15, boost: false },
    { x: 7.0, w: 0.5, y: 0.80, boost: false },
    { x: 7.7, w: 0.4, y: 0.45, boost: false },
    { x: 8.3, w: 0.6, y: 0, boost: false },

    // --- Second climb: tighter zigzag ---
    { x: 9.2, w: 0.4, y: 0.25, boost: false },
    { x: 9.8, w: 0.35, y: 0.50, boost: false },
    { x: 9.3, w: 0.35, y: 0.75, boost: false },
    { x: 9.9, w: 0.4, y: 1.00, boost: false },
    { x: 9.4, w: 0.35, y: 1.25, boost: false },
    { x: 10.0, w: 0.5, y: 1.50, boost: true },   // boost for final push

    // --- Summit: highest point ---
    { x: 10.7, w: 0.7, y: 1.80, boost: false },

    // --- Final descent to end ---
    { x: 11.6, w: 0.4, y: 1.40, boost: false },
    { x: 12.2, w: 0.4, y: 1.00, boost: false },
    { x: 11.8, w: 0.5, y: 0.60, boost: false },
    { x: 12.5, w: 0.4, y: 0.25, boost: false },
    { x: 13.2, w: 0.6, y: 0, boost: false },
  ],

  tokens: [
    { x: 2.25, y: 0.31, collected: false, collectTime: 0 },
    { x: 3.0, y: 0.45, collected: false, collectTime: 0 },
    // Rewards on the first climb
    { x: 5.25, y: 1.18, collected: false, collectTime: 0 },
    { x: 6.1, y: 1.93, collected: false, collectTime: 0 },   // peak reward
    // Rewards on descent
    { x: 7.2, y: 0.93, collected: false, collectTime: 0 },
    // Rewards on second climb
    { x: 9.55, y: 0.88, collected: false, collectTime: 0 },
    { x: 11.0, y: 1.93, collected: false, collectTime: 0 },   // summit reward
    // Final descent
    { x: 12.0, y: 1.13, collected: false, collectTime: 0 },
  ],

  enemies: [
    { x: 3.8, y: 0, patrolLeft: 3.5, patrolRight: 4.5, speed: 0.15, type: 'troll1' },
    { x: 8.5, y: 0, patrolLeft: 8.3, patrolRight: 8.9, speed: 0.12, type: 'troll2' },
    { x: 13.4, y: 0, patrolLeft: 13.2, patrolRight: 13.8, speed: 0.18, type: 'troll3' },
  ],

  arrowPickups: [
    { x: 1.2, y: 0.05, count: 3 },
    { x: 3.0, y: 0.28, count: 3 },
    // Arrows on first climb
    { x: 4.5, y: 0.43, count: 3 },
    { x: 5.1, y: 0.93, count: 3 },
    { x: 4.6, y: 1.43, count: 3 },
    { x: 6.0, y: 1.93, count: 3 },
    // Arrows on descent
    { x: 7.0, y: 1.63, count: 3 },
    { x: 7.9, y: 0.58, count: 3 },
    { x: 8.5, y: 0.05, count: 3 },
    // Arrows on second climb
    { x: 9.4, y: 0.38, count: 3 },
    { x: 10.1, y: 1.13, count: 3 },
    { x: 9.6, y: 1.38, count: 3 },
    { x: 10.9, y: 1.93, count: 3 },
    // Arrows on final descent
    { x: 11.8, y: 1.53, count: 3 },
    { x: 12.4, y: 0.38, count: 3 },
  ],
};

// --- Misty Mountains helpers ---

function _drawMistyPeaks(ctx, offsetX, cw, ch, config) {
  const { seed, baseY, minH, maxH, peakW, color, snowAlpha } = config;
  const step = peakW * 0.55;
  const startI = Math.floor(offsetX * SCALE / step) - 3;
  const endI = startI + Math.ceil(cw * 1.5 / step) + 6;

  ctx.beginPath();
  ctx.moveTo(-100, ch);

  for (let i = startI; i <= endI; i++) {
    const h0 = hash(i * 73 + seed);
    const h1 = hash(i * 137 + seed + 500);
    const peakH = minH + h0 * (maxH - minH);
    const px = i * step + h1 * step * 0.4;
    const py = baseY - peakH;

    if (i === startI) ctx.lineTo(px - peakW * 0.5, baseY);

    // Jagged peaks
    const midH = peakH * (0.35 + hash(i * 211 + seed + 800) * 0.25);
    ctx.lineTo(px - peakW * 0.35, baseY - midH);
    // Sub-ridge
    const subRidge = peakH * (0.6 + hash(i * 179 + seed + 300) * 0.25);
    ctx.lineTo(px - peakW * 0.1, baseY - subRidge);
    ctx.lineTo(px, py);
    ctx.lineTo(px + peakW * 0.08, py + peakH * 0.1);
    ctx.lineTo(px + peakW * 0.2, baseY - midH * 0.85);
    ctx.lineTo(px + peakW * 0.4, baseY);
  }

  ctx.lineTo(cw + 200, ch);
  ctx.closePath();

  const grad = ctx.createLinearGradient(0, baseY - maxH, 0, baseY);
  grad.addColorStop(0, color);
  grad.addColorStop(1, _adjustColor(color, -15));
  ctx.fillStyle = grad;
  ctx.fill();

  // Snow caps
  for (let i = startI; i <= endI; i++) {
    const h0 = hash(i * 73 + seed);
    const h1 = hash(i * 137 + seed + 500);
    const peakH = minH + h0 * (maxH - minH);
    if (peakH < maxH * 0.5) continue;
    const px = i * step + h1 * step * 0.4;
    const py = baseY - peakH;
    const snowH = peakH * 0.25;

    ctx.fillStyle = `rgba(210, 215, 225, ${snowAlpha})`;
    ctx.beginPath();
    ctx.moveTo(px - peakW * 0.15, py + snowH);
    ctx.lineTo(px - peakW * 0.05, py + snowH * 0.3);
    ctx.lineTo(px, py);
    ctx.lineTo(px + peakW * 0.04, py + snowH * 0.2);
    ctx.lineTo(px + peakW * 0.12, py + snowH);
    ctx.closePath();
    ctx.fill();
  }
}

function _drawRockyTerrain(ctx, offsetX, cw, groundY) {
  const spacing = 20;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 59 + 10000);
    if (h < 0.5) continue;
    const rx = i * spacing + hash(i * 67 + 10100) * 10;
    const rw = 8 + h * 15;
    const rh = 4 + h * 10;

    ctx.fillStyle = `rgba(60, 65, 70, ${0.3 + h * 0.3})`;
    ctx.beginPath();
    ctx.moveTo(rx, groundY);
    ctx.lineTo(rx + rw * 0.2, groundY - rh);
    ctx.lineTo(rx + rw * 0.5, groundY - rh * 0.8);
    ctx.lineTo(rx + rw * 0.8, groundY - rh * 1.1);
    ctx.lineTo(rx + rw, groundY);
    ctx.closePath();
    ctx.fill();
  }
}

function _adjustColor(hex, amount) {
  const r = Math.max(0, Math.min(255, parseInt(hex.slice(1, 3), 16) + amount));
  const g = Math.max(0, Math.min(255, parseInt(hex.slice(3, 5), 16) + amount));
  const b = Math.max(0, Math.min(255, parseInt(hex.slice(5, 7), 16) + amount));
  return `rgb(${r}, ${g}, ${b})`;
}

// =====================================================================================================================
// 3. MORIA
// =====================================================================================================================

const moria = {
  name: 'Mines of Moria',
  index: 3,

  createParallaxLayers() {
    // Layer 0: Deep dark cave ceiling
    const ceiling = new ParallaxLayer(0, (ctx, ox, cw, ch) => {
      const grad = ctx.createLinearGradient(0, 0, 0, ch);
      grad.addColorStop(0, '#0a0a0e');
      grad.addColorStop(0.3, '#0e0e14');
      grad.addColorStop(0.5, '#121218');
      grad.addColorStop(0.7, '#14141c');
      grad.addColorStop(1.0, '#181820');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, cw, ch);

      // Stalactites from ceiling
      _drawStalactites(ctx, cw, ch);
    });

    // Layer 1: Deep background — vast cavern walls with faint carved pillars
    const deepWall = new ParallaxLayer(0.05, (ctx, ox, cw, ch) => {
      _drawCavernWall(ctx, ox, cw, ch, {
        seed: 60, baseAlpha: 0.08, pillarSpacing: 200, pillarColor: '#1a1a22',
      });
    });

    // Layer 2: Mid-depth — Dwarven columns, archways
    const midWall = new ParallaxLayer(0.15, (ctx, ox, cw, ch) => {
      _drawDwarvenColumns(ctx, ox, cw, ch, {
        seed: 180, spacing: 140, height: ch * 0.7, width: 16,
        color: '#1e1e28',
      });
    });

    // Layer 3: Near cave wall with holes and glowing eyes
    const nearWall = new ParallaxLayer(0.35, (ctx, ox, cw, ch) => {
      _drawCaveWallWithEyes(ctx, ox, cw, ch, _time);
    });

    // Layer 4: Torches on walls
    const torches = new ParallaxLayer(0.5, (ctx, ox, cw, ch) => {
      _drawTorches(ctx, ox, cw, ch * 0.88, _time);
    });

    return [ceiling, deepWall, midWall, nearWall, torches];
  },

  drawGround(ctx, cameraX, canvasW, canvasH, groundY) {
    // Dark stone floor
    const earthGrad = ctx.createLinearGradient(0, groundY, 0, canvasH);
    earthGrad.addColorStop(0, '#2a2a30');
    earthGrad.addColorStop(0.15, '#222228');
    earthGrad.addColorStop(0.4, '#1a1a20');
    earthGrad.addColorStop(1, '#101014');
    ctx.fillStyle = earthGrad;
    ctx.fillRect(0, groundY, canvasW, canvasH - groundY);

    // Stone tile edges
    const tileStart = Math.floor(cameraX * SCALE / 30);
    const tileEnd = tileStart + Math.ceil(canvasW / 30) + 1;
    for (let i = tileStart; i < tileEnd; i++) {
      const tx = i * 30 - cameraX * SCALE;
      ctx.fillStyle = 'rgba(15, 15, 20, 0.4)';
      ctx.fillRect(Math.floor(tx), groundY, 1, 6);
    }
    ctx.fillStyle = 'rgba(40, 40, 50, 0.2)';
    ctx.fillRect(0, groundY, canvasW, 1);
    ctx.fillStyle = 'rgba(15, 15, 20, 0.3)';
    ctx.fillRect(0, groundY + 6, canvasW, 1);

    // Scattered debris / bones
    const debrisStart = Math.floor(cameraX * SCALE / 40);
    const debrisEnd = debrisStart + Math.ceil(canvasW / 40) + 2;
    for (let i = debrisStart; i < debrisEnd; i++) {
      const h = hash(i * 73 + 11000);
      if (h > 0.65) {
        const dx = i * 40 - cameraX * SCALE + hash(i * 83 + 11100) * 15;
        ctx.fillStyle = `rgba(45, 40, 35, ${0.2 + h * 0.2})`;
        ctx.fillRect(Math.floor(dx), groundY - 1, Math.floor(2 + h * 4), 2);
      }
    }
  },

  drawPlatform(ctx, platform, cameraX, groundY) {
    const px = platform.x * SCALE - cameraX * SCALE;
    const pw = platform.w * SCALE;
    const py = groundY - platform.y * SCALE;
    const ph = 22;
    const isBoost = platform.boost;

    // Heavy stone pillars
    ctx.fillStyle = isBoost ? 'rgba(60, 50, 80, 0.4)' : 'rgba(40, 40, 48, 0.35)';
    ctx.fillRect(px + 3, py + ph, 8, groundY - py - ph);
    ctx.fillRect(px + pw - 11, py + ph, 8, groundY - py - ph);

    // Dwarven rune glow on pillars
    if (isBoost) {
      for (let sy = py + ph + 15; sy < groundY - 10; sy += 20) {
        const pulse = 0.3 + 0.3 * Math.sin(_time * 2 + sy * 0.1);
        ctx.fillStyle = `rgba(100, 80, 200, ${pulse})`;
        ctx.fillRect(px + 5, sy, 4, 6);
        ctx.fillRect(px + pw - 9, sy, 4, 6);
      }
    }

    if (isBoost) {
      // Mithril platform — silver-blue glow
      const grad = ctx.createLinearGradient(px, py, px, py + ph);
      grad.addColorStop(0, '#5a5a7a');
      grad.addColorStop(0.5, '#4a4a6a');
      grad.addColorStop(1, '#3a3a5a');
      ctx.fillStyle = grad;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

      // Mithril glow
      const pulse = 0.6 + 0.4 * Math.sin(_time * 2.5);
      ctx.shadowColor = `rgba(120, 100, 220, ${pulse})`;
      ctx.shadowBlur = 12;
      ctx.fillStyle = `rgba(140, 120, 240, ${pulse * 0.6})`;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 2);
      ctx.shadowBlur = 0;

      // Dwarven runes
      ctx.fillStyle = `rgba(140, 120, 240, ${pulse * 0.3})`;
      for (let x = px + 8; x < px + pw - 8; x += 14) {
        ctx.fillRect(Math.floor(x), Math.floor(py + 8), 2, 8);
        ctx.fillRect(Math.floor(x - 1), Math.floor(py + 10), 4, 2);
        ctx.fillRect(Math.floor(x + 1), Math.floor(py + 14), 3, 1);
      }
    } else {
      // Dark carved stone
      const grad = ctx.createLinearGradient(px, py, px, py + ph);
      grad.addColorStop(0, '#3a3a44');
      grad.addColorStop(0.3, '#30303a');
      grad.addColorStop(1, '#282830');
      ctx.fillStyle = grad;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

      // Carved top edge
      ctx.fillStyle = '#4a4a54';
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 3);

      // Block lines (index-based)
      const pseed = Math.floor(platform.x * 1000);
      ctx.fillStyle = 'rgba(15, 15, 20, 0.3)';
      ctx.fillRect(Math.floor(px), Math.floor(py + ph * 0.45), Math.ceil(pw), 1);
      let blockOff = 14;
      for (let bi = 0; blockOff < pw - 10; bi++) {
        ctx.fillRect(Math.floor(px + blockOff), Math.floor(py), 1, ph);
        blockOff += 22 + hash(bi * 41 + pseed + 888) * 12;
      }

      // Dwarven carving detail (index-based)
      ctx.fillStyle = 'rgba(60, 60, 70, 0.2)';
      for (let di = 0; di * 10 + 6 < pw - 6; di++) {
        const h = hash(di * 59 + pseed + 1111);
        if (h > 0.6) {
          const dx = px + 6 + di * 10;
          ctx.fillRect(Math.floor(dx), Math.floor(py + 5), 3, 1);
          ctx.fillRect(Math.floor(dx + 1), Math.floor(py + 7), 1, 3);
        }
      }
    }
  },

  drawAtmosphere(ctx, cw, ch, groundY, gameTime) {
    // Dust particles in torch light
    for (let i = 0; i < 30; i++) {
      const px = (hash(i * 41 + 12000) * cw + Math.sin(gameTime * 0.3 + i * 2) * 20);
      const py = ch * 0.2 + hash(i * 53 + 12100) * (ch * 0.6);
      const drift = Math.sin(gameTime * 0.5 + i * 3) * 10;
      const alpha = 0.05 + 0.08 * Math.sin(gameTime * 0.8 + i * 1.5);

      ctx.fillStyle = `rgba(180, 160, 120, ${alpha})`;
      ctx.fillRect(Math.floor(px + drift) % cw, Math.floor(py), 1, 1);
    }

    // Occasional dripping water
    for (let i = 0; i < 3; i++) {
      const dx = hash(i * 67 + 12200) * cw;
      const phase = (gameTime * 0.5 + hash(i * 71 + 12300) * 10) % 3;
      if (phase < 0.15) {
        const dy = phase / 0.15 * groundY;
        ctx.fillStyle = `rgba(100, 120, 180, ${0.3 * (1 - phase / 0.15)})`;
        ctx.fillRect(Math.floor(dx), Math.floor(dy), 1, 2);
      }
    }

    // Deep cave ambient glow from below (chasms)
    const chasmGrad = ctx.createLinearGradient(0, groundY, 0, ch);
    chasmGrad.addColorStop(0, 'rgba(0, 0, 0, 0)');
    chasmGrad.addColorStop(0.5, 'rgba(20, 10, 5, 0.1)');
    chasmGrad.addColorStop(1, 'rgba(40, 15, 5, 0.15)');
    ctx.fillStyle = chasmGrad;
    ctx.fillRect(0, groundY, cw, ch - groundY);

    // Drifting cave fog
    for (let i = 0; i < 5; i++) {
      const mx = (hash(i * 89 + 12400) * cw * 1.5 + gameTime * (3 + i * 2)) % (cw + 300) - 150;
      const my = groundY - 30 - hash(i * 97 + 12500) * 60;
      const mw = 80 + hash(i * 103 + 12600) * 120;
      const alpha = 0.03 + 0.02 * Math.sin(gameTime * 0.3 + i * 1.7);
      const grad = ctx.createRadialGradient(mx + mw / 2, my, 0, mx + mw / 2, my, mw / 2);
      grad.addColorStop(0, `rgba(30, 25, 40, ${alpha})`);
      grad.addColorStop(1, 'rgba(30, 25, 40, 0)');
      ctx.fillStyle = grad;
      ctx.fillRect(mx, my - 25, mw, 50);
    }

    // General darkness vignette
    const vigAlpha = 0.08 + 0.03 * Math.sin(gameTime * 0.15);
    ctx.fillStyle = `rgba(5, 5, 10, ${vigAlpha})`;
    ctx.fillRect(0, 0, cw, ch * 0.2);
    ctx.fillRect(0, 0, cw * 0.05, ch);
    ctx.fillRect(cw * 0.95, 0, cw * 0.05, ch);
  },

  platforms: [
    // --- Entrance hall ---
    { x: -1.0, w: 2.5, y: 0, boost: false },
    { x: 2.0, w: 0.5, y: 0.15, boost: false },
    { x: 2.8, w: 0.6, y: 0.30, boost: false },

    // --- First ascent: broken dwarven staircase ---
    { x: 3.6, w: 0.4, y: 0.15, boost: false },
    { x: 4.1, w: 0.45, y: 0.40, boost: false },
    { x: 3.5, w: 0.4, y: 0.65, boost: false },
    { x: 4.2, w: 0.5, y: 0.90, boost: false },
    { x: 3.6, w: 0.4, y: 1.15, boost: false },
    { x: 4.3, w: 0.5, y: 1.40, boost: true },    // boost to reach upper bridge

    // --- Upper bridge of Khazad-dûm ---
    { x: 5.0, w: 1.0, y: 1.65, boost: false },

    // --- Descent into the deep ---
    { x: 6.2, w: 0.4, y: 1.35, boost: false },
    { x: 6.8, w: 0.4, y: 1.00, boost: false },
    { x: 6.3, w: 0.5, y: 0.65, boost: false },
    { x: 6.9, w: 0.4, y: 0.30, boost: false },
    { x: 7.5, w: 0.7, y: 0, boost: false },

    // --- Second ascent: mine shaft pillars ---
    { x: 8.5, w: 0.35, y: 0.25, boost: false },
    { x: 9.0, w: 0.4, y: 0.50, boost: false },
    { x: 8.4, w: 0.4, y: 0.75, boost: false },
    { x: 9.1, w: 0.45, y: 1.00, boost: false },
    { x: 8.5, w: 0.4, y: 1.25, boost: false },
    { x: 9.2, w: 0.5, y: 1.50, boost: true },     // boost to Balin's tomb

    // --- Balin's tomb ledge ---
    { x: 9.9, w: 0.8, y: 1.75, boost: false },

    // --- Final descent to exit ---
    { x: 10.9, w: 0.4, y: 1.40, boost: false },
    { x: 11.5, w: 0.4, y: 1.05, boost: false },
    { x: 11.0, w: 0.5, y: 0.65, boost: false },
    { x: 11.7, w: 0.4, y: 0.30, boost: false },
    { x: 12.4, w: 0.7, y: 0, boost: false },
  ],

  tokens: [
    { x: 2.25, y: 0.28, collected: false, collectTime: 0 },
    // Staircase rewards
    { x: 4.45, y: 1.03, collected: false, collectTime: 0 },
    { x: 5.4, y: 1.78, collected: false, collectTime: 0 },    // bridge reward
    // Descent
    { x: 6.5, y: 1.13, collected: false, collectTime: 0 },
    // Mine shaft rewards
    { x: 8.65, y: 0.88, collected: false, collectTime: 0 },
    { x: 10.2, y: 1.88, collected: false, collectTime: 0 },   // tomb reward
    // Final descent
    { x: 11.25, y: 1.18, collected: false, collectTime: 0 },
    { x: 12.6, y: 0.13, collected: false, collectTime: 0 },
  ],

  enemies: [
    { x: 3.8, y: 0, patrolLeft: 3.5, patrolRight: 4.5, speed: 0.3, type: 'orc1' },
    { x: 7.8, y: 0, patrolLeft: 7.5, patrolRight: 8.2, speed: 0.35, type: 'orc2' },
    { x: 12.6, y: 0, patrolLeft: 12.4, patrolRight: 13.1, speed: 0.25, type: 'orc3' },
  ],

  arrowPickups: [
    { x: 1.0, y: 0.05, count: 3 },
    { x: 2.5, y: 0.18, count: 3 },
    // First staircase
    { x: 3.7, y: 0.28, count: 3 },
    { x: 4.4, y: 0.53, count: 3 },
    { x: 3.7, y: 0.78, count: 3 },
    { x: 4.5, y: 1.53, count: 3 },
    { x: 5.3, y: 1.78, count: 3 },
    // Descent
    { x: 6.4, y: 1.48, count: 3 },
    { x: 7.1, y: 0.43, count: 3 },
    { x: 7.8, y: 0.05, count: 3 },
    // Second ascent
    { x: 8.6, y: 0.38, count: 3 },
    { x: 9.3, y: 1.13, count: 3 },
    { x: 8.7, y: 1.38, count: 3 },
    { x: 10.1, y: 1.88, count: 3 },
    // Final descent
    { x: 11.1, y: 1.53, count: 3 },
    { x: 11.9, y: 0.43, count: 3 },
  ],
};

// --- Moria helpers ---

function _drawStalactites(ctx, cw, ch) {
  for (let i = 0; i < 30; i++) {
    const sx = hash(i * 37 + 13000) * cw;
    const sLen = 15 + hash(i * 43 + 13100) * 50;
    const sw = 2 + hash(i * 53 + 13200) * 5;

    ctx.fillStyle = `rgba(25, 25, 30, ${0.4 + hash(i * 59 + 13300) * 0.4})`;
    ctx.beginPath();
    ctx.moveTo(sx - sw, 0);
    ctx.lineTo(sx + sw, 0);
    ctx.lineTo(sx + sw * 0.3, sLen * 0.6);
    ctx.lineTo(sx, sLen);
    ctx.lineTo(sx - sw * 0.3, sLen * 0.6);
    ctx.closePath();
    ctx.fill();
  }
}

function _drawCavernWall(ctx, offsetX, cw, ch, config) {
  const { seed, baseAlpha, pillarSpacing, pillarColor } = config;

  // Faint wall texture
  ctx.fillStyle = `rgba(20, 20, 26, ${baseAlpha})`;
  ctx.fillRect(0, 0, cw, ch);

  // Giant pillars in deep background
  const startI = Math.floor(offsetX * SCALE / pillarSpacing) - 1;
  const endI = startI + Math.ceil(cw / pillarSpacing) + 2;
  for (let i = startI; i <= endI; i++) {
    const px = i * pillarSpacing + hash(i * 71 + seed) * 30;
    const pw = 20 + hash(i * 79 + seed + 100) * 15;

    ctx.fillStyle = pillarColor;
    ctx.fillRect(Math.floor(px), 0, Math.floor(pw), ch);

    // Capital at top
    ctx.fillRect(Math.floor(px - 5), 0, Math.floor(pw + 10), 15);
    // Base
    ctx.fillRect(Math.floor(px - 4), ch * 0.85, Math.floor(pw + 8), ch * 0.15);
  }
}

function _drawDwarvenColumns(ctx, offsetX, cw, ch, config) {
  const { seed, spacing, height, width, color } = config;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 67 + seed);
    if (h < 0.3) continue;
    const cx = i * spacing + hash(i * 73 + seed + 100) * 40;
    const colW = width + hash(i * 79 + seed + 200) * 8;
    const topY = ch * 0.1 + hash(i * 83 + seed + 300) * (ch * 0.15);

    // Column shaft
    ctx.fillStyle = color;
    ctx.fillRect(Math.floor(cx), Math.floor(topY), Math.floor(colW), height - topY);

    // Carved bands
    ctx.fillStyle = `rgba(35, 35, 45, 0.5)`;
    for (let y = topY + 20; y < topY + height - 20; y += 30) {
      ctx.fillRect(Math.floor(cx - 2), Math.floor(y), Math.floor(colW + 4), 3);
    }

    // Capital
    ctx.fillStyle = `rgba(30, 30, 40, 0.8)`;
    ctx.fillRect(Math.floor(cx - 4), Math.floor(topY), Math.floor(colW + 8), 8);
    ctx.fillRect(Math.floor(cx - 6), Math.floor(topY), Math.floor(colW + 12), 3);
  }
}

function _drawCaveWallWithEyes(ctx, offsetX, cw, ch, time) {
  // Rough cave wall texture
  const startI = Math.floor(offsetX * SCALE / 50) - 1;
  const endI = startI + Math.ceil(cw / 50) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 53 + 14000);
    const wx = i * 50 + hash(i * 61 + 14100) * 20;

    // Wall protrusions
    if (h > 0.4) {
      const ww = 15 + h * 25;
      const wy = ch * 0.3 + hash(i * 67 + 14200) * (ch * 0.4);
      const wh = 20 + h * 40;
      ctx.fillStyle = `rgba(22, 22, 28, ${0.3 + h * 0.3})`;
      ctx.fillRect(Math.floor(wx), Math.floor(wy), Math.floor(ww), Math.floor(wh));
    }

    // Dark holes with glowing eyes
    if (h > 0.75) {
      const hx = wx + 5;
      const hy = ch * 0.4 + hash(i * 71 + 14300) * (ch * 0.35);
      const hr = 6 + h * 8;

      // Dark hole
      ctx.fillStyle = '#06060a';
      ctx.beginPath();
      ctx.arc(hx, hy, hr, 0, Math.PI * 2);
      ctx.fill();

      // Blinking eyes (not always visible)
      const blink = Math.sin(time * (0.5 + hash(i * 79 + 14400) * 1.5) + i * 7);
      if (blink > 0.2) {
        const eyeAlpha = (blink - 0.2) * 0.8;
        const eyeColor = hash(i * 83 + 14500) > 0.5 ? `rgba(200, 60, 30, ${eyeAlpha})` : `rgba(140, 200, 40, ${eyeAlpha})`;
        ctx.fillStyle = eyeColor;
        ctx.fillRect(Math.floor(hx - 3), Math.floor(hy - 1), 2, 2);
        ctx.fillRect(Math.floor(hx + 1), Math.floor(hy - 1), 2, 2);
      }
    }
  }
}

function _drawTorches(ctx, offsetX, cw, groundY, time) {
  const spacing = 180;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 43 + 15000);
    if (h < 0.3) continue;
    const tx = i * spacing + hash(i * 53 + 15100) * 40;
    const ty = groundY - 50 - hash(i * 61 + 15200) * 60;

    // Torch bracket
    ctx.fillStyle = '#2a2820';
    ctx.fillRect(Math.floor(tx - 1), Math.floor(ty), 3, 20);

    // Flame
    const flicker = 0.6 + 0.4 * Math.sin(time * 8 + i * 5) * Math.sin(time * 12 + i * 3);
    const flameH = 8 + flicker * 6;

    // Glow
    ctx.shadowColor = `rgba(255, 150, 50, ${flicker * 0.6})`;
    ctx.shadowBlur = 25;

    // Flame body
    const flameGrad = ctx.createRadialGradient(tx, ty - flameH * 0.3, 0, tx, ty - flameH * 0.3, flameH);
    flameGrad.addColorStop(0, `rgba(255, 220, 100, ${flicker})`);
    flameGrad.addColorStop(0.3, `rgba(255, 150, 50, ${flicker * 0.7})`);
    flameGrad.addColorStop(0.6, `rgba(200, 80, 20, ${flicker * 0.3})`);
    flameGrad.addColorStop(1, 'rgba(200, 80, 20, 0)');
    ctx.fillStyle = flameGrad;
    ctx.beginPath();
    ctx.arc(tx, ty - flameH * 0.3, flameH, 0, Math.PI * 2);
    ctx.fill();

    ctx.shadowBlur = 0;

    // Light pool on ground
    const lightW = 60 + flicker * 30;
    const lightGrad = ctx.createRadialGradient(tx, groundY, 0, tx, groundY, lightW);
    lightGrad.addColorStop(0, `rgba(200, 120, 40, ${flicker * 0.08})`);
    lightGrad.addColorStop(1, 'rgba(200, 120, 40, 0)');
    ctx.fillStyle = lightGrad;
    ctx.fillRect(tx - lightW, groundY - lightW * 0.3, lightW * 2, lightW);
  }
}

// =====================================================================================================================
// 4. MORDOR
// =====================================================================================================================

const mordor = {
  name: 'Mordor',
  index: 4,

  createParallaxLayers() {
    // Layer 0: Dark volcanic sky
    const sky = new ParallaxLayer(0, (ctx, ox, cw, ch) => {
      const grad = ctx.createLinearGradient(0, 0, 0, ch);
      grad.addColorStop(0, '#0a0505');
      grad.addColorStop(0.15, '#1a0808');
      grad.addColorStop(0.3, '#2a0e0a');
      grad.addColorStop(0.45, '#3a1510');
      grad.addColorStop(0.6, '#301008');
      grad.addColorStop(0.8, '#200a05');
      grad.addColorStop(1.0, '#180808');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, cw, ch);

      // Mount Doom — always visible
      _drawMountDoom(ctx, cw, ch, _time);

      // Ash clouds
      _drawAshClouds(ctx, cw, ch, _time);
    });

    // Layer 1: Distant dark ridges
    const farRidges = new ParallaxLayer(0.08, (ctx, ox, cw, ch) => {
      _drawMordorRidges(ctx, ox, cw, ch, {
        seed: 80, baseY: ch * 0.7, minH: 80, maxH: 200, peakW: 100,
        color1: '#1a0a08', color2: '#120605',
      });
    });

    // Layer 2: Mid volcanic terrain
    const midTerrain = new ParallaxLayer(0.2, (ctx, ox, cw, ch) => {
      _drawMordorRidges(ctx, ox, cw, ch, {
        seed: 220, baseY: ch * 0.8, minH: 50, maxH: 120, peakW: 70,
        color1: '#200e0a', color2: '#150808',
      });
      // Lava rivers between ridges
      _drawLavaRivers(ctx, ox, cw, ch * 0.82, _time);
    });

    // Layer 3: Near dark towers/spires
    const nearSpires = new ParallaxLayer(0.4, (ctx, ox, cw, ch) => {
      _drawDarkSpires(ctx, ox, cw, ch * 0.88);
    });

    // Layer 4: Ground-level lava glow
    const lavaGlow = new ParallaxLayer(0.55, (ctx, ox, cw, ch) => {
      _drawGroundLavaGlow(ctx, ox, cw, ch * 0.88, _time);
    });

    return [sky, farRidges, midTerrain, nearSpires, lavaGlow];
  },

  drawGround(ctx, cameraX, canvasW, canvasH, groundY) {
    // Cracked volcanic rock
    const earthGrad = ctx.createLinearGradient(0, groundY, 0, canvasH);
    earthGrad.addColorStop(0, '#2a1a14');
    earthGrad.addColorStop(0.15, '#221410');
    earthGrad.addColorStop(0.4, '#1a0e0a');
    earthGrad.addColorStop(1, '#100805');
    ctx.fillStyle = earthGrad;
    ctx.fillRect(0, groundY, canvasW, canvasH - groundY);

    // Cracked surface
    const crackStart = Math.floor(cameraX * SCALE / 15);
    const crackEnd = crackStart + Math.ceil(canvasW / 15) + 1;
    for (let i = crackStart; i < crackEnd; i++) {
      const h = hash(i * 43 + 16000);
      if (h > 0.5) {
        const cx = i * 15 - cameraX * SCALE;
        // Lava crack glow
        const glowPulse = 0.3 + 0.3 * Math.sin(_time * 1.5 + i * 0.3);
        ctx.fillStyle = `rgba(200, 80, 20, ${glowPulse * h * 0.15})`;
        ctx.fillRect(Math.floor(cx), groundY, 1, 3);
      }
    }

    // Dark top edge
    ctx.fillStyle = 'rgba(30, 15, 10, 0.6)';
    ctx.fillRect(0, groundY, canvasW, 2);
  },

  drawPlatform(ctx, platform, cameraX, groundY) {
    const px = platform.x * SCALE - cameraX * SCALE;
    const pw = platform.w * SCALE;
    const py = groundY - platform.y * SCALE;
    const ph = 20;
    const isBoost = platform.boost;

    // Obsidian pillars
    ctx.fillStyle = isBoost ? 'rgba(100, 30, 15, 0.4)' : 'rgba(30, 20, 15, 0.35)';
    ctx.fillRect(px + 3, py + ph, 6, groundY - py - ph);
    ctx.fillRect(px + pw - 9, py + ph, 6, groundY - py - ph);

    if (isBoost) {
      // Lava-infused platform
      const grad = ctx.createLinearGradient(px, py, px, py + ph);
      grad.addColorStop(0, '#4a2018');
      grad.addColorStop(0.5, '#3a1810');
      grad.addColorStop(1, '#2a1008');
      ctx.fillStyle = grad;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

      // Molten lava glow
      const pulse = 0.5 + 0.5 * Math.sin(_time * 3);
      ctx.shadowColor = `rgba(255, 100, 20, ${pulse})`;
      ctx.shadowBlur = 15;
      ctx.fillStyle = `rgba(255, 120, 30, ${pulse * 0.7})`;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 3);
      ctx.shadowBlur = 0;

      // Lava veins
      ctx.strokeStyle = `rgba(255, 80, 20, ${pulse * 0.3})`;
      ctx.lineWidth = 1;
      for (let x = px + 8; x < px + pw - 8; x += 16) {
        ctx.beginPath();
        ctx.moveTo(x, py + 4);
        ctx.lineTo(x + 3, py + ph - 2);
        ctx.stroke();
      }
    } else {
      // Dark obsidian stone
      const grad = ctx.createLinearGradient(px, py, px, py + ph);
      grad.addColorStop(0, '#2a2220');
      grad.addColorStop(0.3, '#221a18');
      grad.addColorStop(1, '#1a1210');
      ctx.fillStyle = grad;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

      // Sharp edges
      ctx.fillStyle = '#3a302a';
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 2);

      // Cracks with lava glow
      ctx.fillStyle = 'rgba(10, 8, 6, 0.4)';
      ctx.fillRect(Math.floor(px), Math.floor(py + ph * 0.5), Math.ceil(pw), 1);

      const pseed = Math.floor(platform.x * 1000);
      let crOff = 10;
      for (let ci = 0; crOff < pw - 8; ci++) {
        const fx = px + crOff;
        ctx.fillRect(Math.floor(fx), Math.floor(py), 1, ph);
        // Faint lava in crack
        const glow = 0.1 + 0.1 * Math.sin(_time * 2 + ci * 0.8);
        ctx.fillStyle = `rgba(180, 60, 15, ${glow})`;
        ctx.fillRect(Math.floor(fx), Math.floor(py + 2), 1, ph - 4);
        ctx.fillStyle = 'rgba(10, 8, 6, 0.4)';
        crOff += 16 + hash(ci * 61 + pseed + 777) * 10;
      }

      // Scorch marks (index-based)
      ctx.fillStyle = 'rgba(15, 10, 8, 0.25)';
      for (let si = 0; si * 6 + 4 < pw - 4; si++) {
        const h = hash(si * 67 + pseed + 2222);
        if (h > 0.7) {
          ctx.fillRect(Math.floor(px + 4 + si * 6), Math.floor(py + ph - 3), Math.floor(2 + h * 3), 3);
        }
      }
    }
  },

  drawAtmosphere(ctx, cw, ch, groundY, gameTime) {
    // Flying embers / ash
    for (let i = 0; i < 50; i++) {
      const ex = (hash(i * 37 + 17000) * cw * 1.5 + gameTime * (5 + hash(i * 41 + 17100) * 15)) % (cw + 200) - 100;
      const ey = (hash(i * 53 + 17200) * ch - gameTime * (8 + hash(i * 59 + 17300) * 20));
      const wy = ((ey % ch) + ch) % ch; // Wrap
      const isEmber = hash(i * 61 + 17400) > 0.4;
      const alpha = 0.3 + hash(i * 67 + 17500) * 0.5;

      if (isEmber) {
        const pulse = 0.5 + 0.5 * Math.sin(gameTime * 5 + i * 3);
        ctx.fillStyle = `rgba(255, ${120 + pulse * 80 | 0}, ${20 + pulse * 30 | 0}, ${alpha * pulse})`;
      } else {
        ctx.fillStyle = `rgba(80, 70, 60, ${alpha * 0.5})`;
      }
      const size = 1 + hash(i * 71 + 17600) * 2;
      ctx.fillRect(Math.floor(ex), Math.floor(wy), Math.ceil(size), Math.ceil(size));
    }

    // Occasional ground shake effect (screen tint)
    const shake = Math.sin(gameTime * 0.3) * Math.sin(gameTime * 0.7);
    if (shake > 0.8) {
      ctx.fillStyle = `rgba(100, 30, 10, ${(shake - 0.8) * 0.15})`;
      ctx.fillRect(0, 0, cw, ch);
    }

    // Heat distortion at ground level
    const heatGrad = ctx.createLinearGradient(0, groundY - 40, 0, groundY);
    heatGrad.addColorStop(0, 'rgba(0, 0, 0, 0)');
    heatGrad.addColorStop(0.5, `rgba(80, 30, 10, ${0.03 + 0.02 * Math.sin(gameTime * 2)})`);
    heatGrad.addColorStop(1, `rgba(120, 40, 10, ${0.08 + 0.04 * Math.sin(gameTime * 1.5)})`);
    ctx.fillStyle = heatGrad;
    ctx.fillRect(0, groundY - 40, cw, 40);

    // Ash/smoke haze across screen
    const smokeAlpha = 0.04 + 0.02 * Math.sin(gameTime * 0.25);
    const smokeGrad = ctx.createLinearGradient(0, 0, 0, ch);
    smokeGrad.addColorStop(0, `rgba(20, 10, 5, ${smokeAlpha * 1.5})`);
    smokeGrad.addColorStop(0.5, `rgba(30, 15, 8, ${smokeAlpha})`);
    smokeGrad.addColorStop(1, `rgba(15, 8, 5, ${smokeAlpha * 0.5})`);
    ctx.fillStyle = smokeGrad;
    ctx.fillRect(0, 0, cw, ch);

    // Drifting smoke wisps
    for (let i = 0; i < 4; i++) {
      const sx = (hash(i * 73 + 17650) * cw * 1.5 + gameTime * (4 + i * 3)) % (cw + 400) - 200;
      const sy = ch * 0.2 + hash(i * 79 + 17660) * ch * 0.4;
      const sw = 100 + hash(i * 83 + 17670) * 150;
      const sa = 0.03 + 0.02 * Math.sin(gameTime * 0.35 + i * 2);
      const grad = ctx.createRadialGradient(sx + sw / 2, sy, 0, sx + sw / 2, sy, sw / 2);
      grad.addColorStop(0, `rgba(40, 20, 10, ${sa})`);
      grad.addColorStop(1, 'rgba(40, 20, 10, 0)');
      ctx.fillStyle = grad;
      ctx.fillRect(sx, sy - 30, sw, 60);
    }
  },

  platforms: [
    // --- Opening ground ---
    { x: -1.0, w: 2.5, y: 0, boost: false },
    { x: 2.0, w: 0.4, y: 0.15, boost: false },
    { x: 2.8, w: 0.5, y: 0.28, boost: false },
    { x: 3.6, w: 0.6, y: 0, boost: false },

    // --- First vertical climb: crumbling obsidian staircase ---
    { x: 4.4, w: 0.4, y: 0.22, boost: false },
    { x: 5.0, w: 0.4, y: 0.47, boost: false },
    { x: 4.3, w: 0.4, y: 0.72, boost: false },
    { x: 5.0, w: 0.45, y: 0.97, boost: false },
    { x: 4.4, w: 0.4, y: 1.22, boost: false },
    { x: 5.1, w: 0.5, y: 1.47, boost: true },    // boost to reach the summit

    // --- Dark Tower ledge (high point) ---
    { x: 5.8, w: 0.7, y: 1.70, boost: false },

    // --- Descent from tower ---
    { x: 6.7, w: 0.4, y: 1.40, boost: false },
    { x: 7.3, w: 0.4, y: 1.05, boost: false },
    { x: 6.8, w: 0.5, y: 0.70, boost: false },
    { x: 7.5, w: 0.4, y: 0.35, boost: false },
    { x: 8.1, w: 0.7, y: 0, boost: false },

    // --- Second vertical climb: Mount Doom ascent ---
    { x: 9.2, w: 0.35, y: 0.25, boost: false },
    { x: 9.7, w: 0.4, y: 0.50, boost: false },
    { x: 9.1, w: 0.4, y: 0.75, boost: false },
    { x: 9.8, w: 0.4, y: 1.00, boost: false },
    { x: 9.2, w: 0.35, y: 1.25, boost: false },
    { x: 9.9, w: 0.5, y: 1.50, boost: true },     // boost for final push

    // --- Mordor summit ---
    { x: 10.6, w: 0.7, y: 1.75, boost: false },

    // --- Final descent ---
    { x: 11.5, w: 0.4, y: 1.35, boost: false },
    { x: 12.1, w: 0.4, y: 0.95, boost: false },
    { x: 11.6, w: 0.5, y: 0.55, boost: false },
    { x: 12.3, w: 0.4, y: 0.20, boost: false },
    { x: 13.0, w: 0.7, y: 0, boost: false },
  ],

  tokens: [
    { x: 3.05, y: 0.41, collected: false, collectTime: 0 },
    { x: 4.7, y: 0.60, collected: false, collectTime: 0 },
    { x: 6.1, y: 1.83, collected: false, collectTime: 0 },
    { x: 7.1, y: 1.18, collected: false, collectTime: 0 },
    { x: 9.5, y: 0.63, collected: false, collectTime: 0 },
    { x: 10.9, y: 1.88, collected: false, collectTime: 0 },
    { x: 11.8, y: 0.68, collected: false, collectTime: 0 },
  ],

  enemies: [
    { x: 7.0, y: 0, patrolLeft: 4.0, patrolRight: 10.0, speed: 0.2, type: 'dragon' },
  ],

  arrowPickups: [
    { x: 1.5, y: 0.05, count: 3 },
    { x: 3.8, y: 0.05, count: 3 },
    { x: 4.5, y: 0.85, count: 3 },
    { x: 5.3, y: 1.60, count: 3 },
    { x: 7.0, y: 1.18, count: 3 },
    { x: 7.7, y: 0.48, count: 3 },
    { x: 8.3, y: 0.05, count: 3 },
    { x: 9.4, y: 0.88, count: 3 },
    { x: 10.1, y: 1.63, count: 3 },
    { x: 11.8, y: 1.08, count: 3 },
    { x: 12.5, y: 0.33, count: 3 },
    { x: 13.2, y: 0.05, count: 3 },
  ],
};

// --- Mordor helpers ---

function _drawMountDoom(ctx, cw, ch, time) {
  const mx = cw * 0.55;
  const baseY = ch * 0.65;
  const peakY = ch * 0.12;

  // Volcano shape
  ctx.beginPath();
  ctx.moveTo(mx - 200, baseY);
  ctx.lineTo(mx - 80, baseY - 120);
  ctx.lineTo(mx - 30, peakY + 30);
  ctx.lineTo(mx - 15, peakY);
  ctx.lineTo(mx + 15, peakY + 5);
  ctx.lineTo(mx + 25, peakY + 25);
  ctx.lineTo(mx + 70, baseY - 100);
  ctx.lineTo(mx + 180, baseY);
  ctx.closePath();

  const volGrad = ctx.createLinearGradient(mx, peakY, mx, baseY);
  volGrad.addColorStop(0, '#1a0a05');
  volGrad.addColorStop(0.3, '#200e08');
  volGrad.addColorStop(1, '#150808');
  ctx.fillStyle = volGrad;
  ctx.fill();

  // Lava glow at crater
  const lavaPulse = 0.5 + 0.5 * Math.sin(time * 1.5);
  const craterGlow = ctx.createRadialGradient(mx, peakY + 10, 5, mx, peakY + 10, 60);
  craterGlow.addColorStop(0, `rgba(255, 120, 30, ${lavaPulse * 0.6})`);
  craterGlow.addColorStop(0.3, `rgba(200, 60, 10, ${lavaPulse * 0.3})`);
  craterGlow.addColorStop(1, 'rgba(200, 60, 10, 0)');
  ctx.fillStyle = craterGlow;
  ctx.beginPath();
  ctx.arc(mx, peakY + 10, 60, 0, Math.PI * 2);
  ctx.fill();

  // Smoke plume
  for (let i = 0; i < 6; i++) {
    const sx = mx + Math.sin(time * 0.5 + i * 2) * 15 + i * 8;
    const sy = peakY - 10 - i * 20 - Math.sin(time * 0.3 + i) * 5;
    const sr = 10 + i * 8;
    const alpha = (0.15 - i * 0.02) * (0.7 + 0.3 * Math.sin(time * 0.4 + i * 3));
    ctx.fillStyle = `rgba(40, 30, 25, ${alpha})`;
    ctx.beginPath();
    ctx.arc(sx, sy, sr, 0, Math.PI * 2);
    ctx.fill();
  }

  // Lava streaks down the side
  for (let i = 0; i < 3; i++) {
    const lx = mx + (hash(i * 31 + 16500) - 0.5) * 40;
    const ly = peakY + 20;
    const lLen = 30 + hash(i * 37 + 16600) * 50;
    const pulse = 0.3 + 0.3 * Math.sin(time * 2 + i * 4);

    ctx.strokeStyle = `rgba(255, 100, 20, ${pulse})`;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(lx, ly);
    ctx.quadraticCurveTo(lx + hash(i * 41 + 16700) * 15, ly + lLen * 0.5, lx + 5, ly + lLen);
    ctx.stroke();
  }
}

function _drawAshClouds(ctx, cw, ch, time) {
  for (let i = 0; i < 6; i++) {
    const cx = (hash(i * 47 + 16000) * cw * 1.5 + time * (1 + i * 0.5)) % (cw + 500) - 250;
    const cy = hash(i * 53 + 16100) * ch * 0.35;
    const cr = 30 + hash(i * 59 + 16200) * 50;
    const alpha = 0.06 + hash(i * 61 + 16300) * 0.08;

    ctx.fillStyle = `rgba(30, 20, 15, ${alpha})`;
    ctx.beginPath();
    ctx.arc(cx, cy, cr, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cx + cr * 0.6, cy - cr * 0.2, cr * 0.7, 0, Math.PI * 2);
    ctx.fill();
  }
}

function _drawMordorRidges(ctx, offsetX, cw, ch, config) {
  const { seed, baseY, minH, maxH, peakW, color1, color2 } = config;
  const step = peakW * 0.5;
  const startI = Math.floor(offsetX * SCALE / step) - 3;
  const endI = startI + Math.ceil(cw * 1.5 / step) + 6;

  ctx.beginPath();
  ctx.moveTo(-100, ch);

  for (let i = startI; i <= endI; i++) {
    const h0 = hash(i * 73 + seed);
    const h1 = hash(i * 137 + seed + 500);
    const peakH = minH + h0 * (maxH - minH);
    const px = i * step + h1 * step * 0.4;

    if (i === startI) ctx.lineTo(px - peakW * 0.5, baseY);
    // Sharp jagged ridges
    ctx.lineTo(px - peakW * 0.2, baseY - peakH * 0.4);
    ctx.lineTo(px - peakW * 0.05, baseY - peakH * 0.9);
    ctx.lineTo(px, baseY - peakH);
    ctx.lineTo(px + peakW * 0.08, baseY - peakH * 0.85);
    ctx.lineTo(px + peakW * 0.25, baseY - peakH * 0.3);
    ctx.lineTo(px + peakW * 0.4, baseY);
  }

  ctx.lineTo(cw + 200, ch);
  ctx.closePath();

  const grad = ctx.createLinearGradient(0, baseY - maxH, 0, baseY);
  grad.addColorStop(0, color1);
  grad.addColorStop(1, color2);
  ctx.fillStyle = grad;
  ctx.fill();
}

function _drawLavaRivers(ctx, offsetX, cw, baseY, time) {
  const spacing = 300;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 47 + 16800);
    if (h > 0.4) continue;
    const rx = i * spacing + hash(i * 53 + 16900) * 80;
    const rw = 20 + h * 40;
    const pulse = 0.4 + 0.3 * Math.sin(time * 2 + rx * 0.01);

    const lavaGrad = ctx.createLinearGradient(rx, baseY - 3, rx, baseY + 5);
    lavaGrad.addColorStop(0, `rgba(255, 120, 20, ${pulse * 0.3})`);
    lavaGrad.addColorStop(0.5, `rgba(255, 80, 10, ${pulse * 0.4})`);
    lavaGrad.addColorStop(1, `rgba(200, 40, 5, ${pulse * 0.2})`);
    ctx.fillStyle = lavaGrad;
    ctx.fillRect(Math.floor(rx), Math.floor(baseY - 2), Math.floor(rw), 5);

    // Glow above lava
    const glowGrad = ctx.createRadialGradient(rx + rw / 2, baseY, 0, rx + rw / 2, baseY, rw);
    glowGrad.addColorStop(0, `rgba(255, 100, 20, ${pulse * 0.08})`);
    glowGrad.addColorStop(1, 'rgba(255, 100, 20, 0)');
    ctx.fillStyle = glowGrad;
    ctx.fillRect(rx - rw, baseY - rw, rw * 3, rw * 2);
  }
}

function _drawDarkSpires(ctx, offsetX, cw, groundY) {
  const spacing = 250;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 61 + 17700);
    if (h < 0.4) continue;
    const sx = i * spacing + hash(i * 67 + 17800) * 60;
    const sh = 30 + h * 80;
    const sw = 4 + h * 6;

    ctx.fillStyle = `rgba(15, 10, 8, ${0.5 + h * 0.3})`;
    ctx.beginPath();
    ctx.moveTo(sx - sw, groundY);
    ctx.lineTo(sx - sw * 0.3, groundY - sh * 0.7);
    ctx.lineTo(sx, groundY - sh);
    ctx.lineTo(sx + sw * 0.3, groundY - sh * 0.7);
    ctx.lineTo(sx + sw, groundY);
    ctx.closePath();
    ctx.fill();
  }
}

function _drawGroundLavaGlow(ctx, offsetX, cw, groundY, time) {
  const spacing = 200;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 71 + 17900);
    if (h > 0.35) continue;
    const gx = i * spacing + hash(i * 79 + 18000) * 80;
    const pulse = 0.3 + 0.3 * Math.sin(time * 1.5 + gx * 0.005);

    const glowGrad = ctx.createRadialGradient(gx, groundY, 0, gx, groundY, 40);
    glowGrad.addColorStop(0, `rgba(200, 60, 10, ${pulse * 0.1})`);
    glowGrad.addColorStop(1, 'rgba(200, 60, 10, 0)');
    ctx.fillStyle = glowGrad;
    ctx.fillRect(gx - 40, groundY - 30, 80, 60);
  }
}

// =====================================================================================================================
// 5. LOTHLORIEN
// =====================================================================================================================

const lothlorien = {
  name: 'Lothlórien',
  index: 5,

  createParallaxLayers() {
    // Layer 0: Ethereal golden-green sky
    const sky = new ParallaxLayer(0, (ctx, ox, cw, ch) => {
      const grad = ctx.createLinearGradient(0, 0, 0, ch);
      grad.addColorStop(0, '#1a2a20');
      grad.addColorStop(0.15, '#1e3028');
      grad.addColorStop(0.3, '#243830');
      grad.addColorStop(0.5, '#2a4038');
      grad.addColorStop(0.7, '#304a3a');
      grad.addColorStop(0.85, '#2a4030');
      grad.addColorStop(1.0, '#1e3020');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, cw, ch);

      // Faint stars through canopy
      for (let i = 0; i < 40; i++) {
        const sx = hash(i * 31 + 20000) * cw;
        const sy = hash(i * 37 + 20100) * ch * 0.3;
        const twinkle = 0.2 + 0.3 * Math.sin(_time * (0.5 + hash(i * 41 + 20200) * 1.5) + i * 3);
        ctx.fillStyle = `rgba(200, 220, 180, ${twinkle})`;
        ctx.fillRect(Math.floor(sx), Math.floor(sy), 1, 1);
      }

      // Golden light shafts through canopy
      _drawLightShafts(ctx, cw, ch, _time);
    });

    // Layer 1: Deep background — massive mallorn trunks, very far
    const farTrees = new ParallaxLayer(0.06, (ctx, ox, cw, ch) => {
      _drawMallornTrees(ctx, ox, cw, ch, {
        seed: 90, spacing: 350, trunkW: 55, trunkColor: '#1a2418',
        canopyY: ch * 0.05, baseY: ch * 0.9, alpha: 0.3,
      });
    });

    // Layer 2: Mid mallorn trees with golden leaves
    const midTrees = new ParallaxLayer(0.18, (ctx, ox, cw, ch) => {
      _drawMallornTrees(ctx, ox, cw, ch, {
        seed: 210, spacing: 260, trunkW: 40, trunkColor: '#1e2a1a',
        canopyY: ch * 0.0, baseY: ch * 0.88, alpha: 0.5,
      });
      // Hanging golden leaves
      _drawHangingLeaves(ctx, ox, cw, ch, _time);
    });

    // Layer 3: Near silver-barked trees with glowing moss
    const nearTrees = new ParallaxLayer(0.35, (ctx, ox, cw, ch) => {
      _drawMallornTrees(ctx, ox, cw, ch, {
        seed: 370, spacing: 180, trunkW: 30, trunkColor: '#2a3824',
        canopyY: ch * -0.05, baseY: ch * 0.88, alpha: 0.7,
      });
    });

    // Layer 4: Foreground roots, ferns, flowers
    const ferns = new ParallaxLayer(0.5, (ctx, ox, cw, ch) => {
      _drawElvenFerns(ctx, ox, cw, ch * 0.88, _time);
    });

    return [sky, farTrees, midTrees, nearTrees, ferns];
  },

  drawGround(ctx, cameraX, canvasW, canvasH, groundY) {
    // Mossy forest floor
    const earthGrad = ctx.createLinearGradient(0, groundY, 0, canvasH);
    earthGrad.addColorStop(0, '#2a3a1e');
    earthGrad.addColorStop(0.1, '#223218');
    earthGrad.addColorStop(0.4, '#1a2a12');
    earthGrad.addColorStop(1, '#12200a');
    ctx.fillStyle = earthGrad;
    ctx.fillRect(0, groundY, canvasW, canvasH - groundY);

    // Soft moss and grass
    const grassStart = Math.floor(cameraX * SCALE / 3);
    const grassEnd = grassStart + Math.ceil(canvasW / 3) + 1;
    for (let i = grassStart; i < grassEnd; i++) {
      const gx = i * 3 - cameraX * SCALE;
      const h = hash(i * 41 + 21000);
      const grassH = 1 + Math.floor(h * 4);
      // Golden-green tones
      const gold = hash(i * 53 + 21100);
      const r = 50 + gold * 80;
      const g = 90 + gold * 60;
      const b = 20 + (1 - gold) * 30;
      ctx.fillStyle = `rgba(${r | 0}, ${g | 0}, ${b | 0}, ${0.6 + h * 0.3})`;
      ctx.fillRect(Math.floor(gx), Math.floor(groundY - grassH), 3, grassH + 1);
    }

    // Elanor and Niphredil flowers (golden and white)
    for (let i = grassStart; i < grassEnd; i++) {
      const h = hash(i * 67 + 21200);
      if (h > 0.9) {
        const gx = i * 3 - cameraX * SCALE;
        const fy = groundY - 2 - h * 5;
        const isGolden = hash(i * 79 + 21300) > 0.5;
        ctx.fillStyle = isGolden ? '#e8c040' : '#e0e8f0';
        ctx.fillRect(Math.floor(gx), Math.floor(fy), 2, 2);
        ctx.fillStyle = '#4a7030';
        ctx.fillRect(Math.floor(gx), Math.floor(fy + 2), 1, 2);
      }
    }

    // Leaf litter — golden fallen leaves
    const leafStart = Math.floor(cameraX * SCALE / 12);
    const leafEnd = leafStart + Math.ceil(canvasW / 12) + 1;
    for (let i = leafStart; i < leafEnd; i++) {
      const h = hash(i * 89 + 21400);
      if (h > 0.6) {
        const lx = i * 12 - cameraX * SCALE + hash(i * 97 + 21500) * 8;
        ctx.fillStyle = `rgba(${180 + h * 40 | 0}, ${140 + h * 40 | 0}, ${40 + h * 30 | 0}, ${0.15 + h * 0.15})`;
        ctx.fillRect(Math.floor(lx), groundY + 1, 3, 1);
      }
    }
  },

  drawPlatform(ctx, platform, cameraX, groundY) {
    const px = platform.x * SCALE - cameraX * SCALE;
    const pw = platform.w * SCALE;
    const py = groundY - platform.y * SCALE;
    const ph = 18;
    const isBoost = platform.boost;

    // Living wood supports — winding branches
    ctx.strokeStyle = isBoost ? 'rgba(80, 100, 50, 0.4)' : 'rgba(60, 80, 40, 0.3)';
    ctx.lineWidth = 3;
    // Left vine/branch
    ctx.beginPath();
    ctx.moveTo(px + 8, py + ph);
    ctx.quadraticCurveTo(px + 2, py + ph + (groundY - py - ph) * 0.4, px + 6, groundY);
    ctx.stroke();
    // Right vine/branch
    ctx.beginPath();
    ctx.moveTo(px + pw - 8, py + ph);
    ctx.quadraticCurveTo(px + pw - 2, py + ph + (groundY - py - ph) * 0.5, px + pw - 6, groundY);
    ctx.stroke();

    if (isBoost) {
      // Elven platform — silver-gold with starlight
      const grad = ctx.createLinearGradient(px, py, px, py + ph);
      grad.addColorStop(0, '#5a6a48');
      grad.addColorStop(0.5, '#4a5a38');
      grad.addColorStop(1, '#3a4a28');
      ctx.fillStyle = grad;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

      // Elven glow — starlight silver
      const pulse = 0.6 + 0.4 * Math.sin(_time * 2);
      ctx.shadowColor = `rgba(180, 200, 140, ${pulse})`;
      ctx.shadowBlur = 14;
      ctx.fillStyle = `rgba(200, 220, 160, ${pulse * 0.6})`;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 2);
      ctx.shadowBlur = 0;

      // Elven vine/leaf carvings
      ctx.fillStyle = `rgba(160, 200, 100, ${pulse * 0.25})`;
      for (let x = px + 8; x < px + pw - 8; x += 12) {
        // Leaf motif
        ctx.beginPath();
        ctx.ellipse(x + 3, py + ph / 2, 4, 2, 0.3, 0, Math.PI * 2);
        ctx.fill();
      }
    } else {
      // Living wood platform — organic
      const grad = ctx.createLinearGradient(px, py, px, py + ph);
      grad.addColorStop(0, '#5a6840');
      grad.addColorStop(0.4, '#4a5830');
      grad.addColorStop(1, '#3a4820');
      ctx.fillStyle = grad;
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

      // Bark texture (index-based)
      const pseed = Math.floor(platform.x * 1000);
      ctx.fillStyle = 'rgba(35, 45, 20, 0.25)';
      let barkOff = 5;
      for (let bi = 0; barkOff < pw - 5; bi++) {
        ctx.fillRect(Math.floor(px + barkOff), Math.floor(py), 1, ph);
        barkOff += 8 + hash(bi * 41 + pseed + 555) * 5;
      }

      // Silver bark highlights
      ctx.fillStyle = 'rgba(180, 190, 170, 0.12)';
      ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 2);

      // Small leaves growing (index-based)
      ctx.fillStyle = 'rgba(100, 140, 50, 0.3)';
      for (let li = 0; li * 10 + 4 < pw - 4; li++) {
        const h = hash(li * 59 + pseed + 3333);
        if (h > 0.5) {
          ctx.beginPath();
          ctx.ellipse(px + 4 + li * 10, py - 1, 3, 1.5, h * 1, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Golden leaf on top (index-based)
      for (let gi = 0; gi * 15 + 6 < pw - 6; gi++) {
        const h = hash(gi * 71 + pseed + 4444);
        if (h > 0.65) {
          ctx.fillStyle = `rgba(${180 + h * 40 | 0}, ${140 + h * 30 | 0}, ${40 + h * 20 | 0}, 0.35)`;
          ctx.fillRect(Math.floor(px + 6 + gi * 15), Math.floor(py - 1), 3, 2);
        }
      }
    }
  },

  drawAtmosphere(ctx, cw, ch, groundY, gameTime) {
    // Fireflies — many, warm golden
    for (let i = 0; i < 35; i++) {
      const baseX = hash(i * 53 + 22000) * cw;
      const baseY = groundY - 20 - hash(i * 67 + 22100) * (ch * 0.5);
      const wobbleX = Math.sin(gameTime * (0.4 + hash(i * 71 + 22200) * 1.2) + i * 3) * 20;
      const wobbleY = Math.cos(gameTime * (0.3 + hash(i * 79 + 22300) * 0.8) + i * 5) * 12;
      const pulse = 0.2 + 0.8 * Math.max(0, Math.sin(gameTime * (0.8 + hash(i * 83 + 22400) * 2) + i * 4));

      if (pulse > 0.3) {
        ctx.shadowColor = `rgba(200, 200, 100, ${pulse * 0.5})`;
        ctx.shadowBlur = 8 * pulse;
        ctx.fillStyle = `rgba(220, 220, 120, ${pulse * 0.6})`;
        ctx.fillRect(Math.floor(baseX + wobbleX), Math.floor(baseY + wobbleY), 2, 2);
      }
    }
    ctx.shadowBlur = 0;

    // Floating golden leaves
    for (let i = 0; i < 12; i++) {
      const lx = (hash(i * 41 + 22500) * cw * 1.5 + gameTime * (3 + hash(i * 47 + 22600) * 5)) % (cw + 200) - 100;
      const ly = hash(i * 53 + 22700) * ch * 0.8 + Math.sin(gameTime * 0.5 + i * 2) * 15;
      const spin = gameTime * (1 + hash(i * 59 + 22800) * 2) + i;
      const alpha = 0.25 + 0.15 * Math.sin(gameTime * 0.3 + i);

      ctx.save();
      ctx.translate(lx, ly);
      ctx.rotate(spin);
      ctx.fillStyle = `rgba(200, 170, 50, ${alpha})`;
      ctx.beginPath();
      ctx.ellipse(0, 0, 4, 2, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // Ethereal ground mist
    const mistGrad = ctx.createLinearGradient(0, groundY - 50, 0, groundY + 5);
    mistGrad.addColorStop(0, 'rgba(160, 180, 120, 0)');
    mistGrad.addColorStop(0.5, `rgba(160, 180, 120, ${0.05 + 0.03 * Math.sin(gameTime * 0.4)})`);
    mistGrad.addColorStop(1, `rgba(140, 170, 100, ${0.08 + 0.04 * Math.sin(gameTime * 0.3)})`);
    ctx.fillStyle = mistGrad;
    ctx.fillRect(0, groundY - 50, cw, 55);

    // Drifting golden mist wisps
    for (let i = 0; i < 5; i++) {
      const mx = (hash(i * 91 + 22900) * cw * 1.5 + gameTime * (2 + i * 1.5)) % (cw + 300) - 150;
      const my = groundY - 25 - hash(i * 101 + 22910) * 50;
      const mw = 80 + hash(i * 107 + 22920) * 120;
      const ma = 0.03 + 0.02 * Math.sin(gameTime * 0.35 + i * 2);
      const grad = ctx.createRadialGradient(mx + mw / 2, my, 0, mx + mw / 2, my, mw / 2);
      grad.addColorStop(0, `rgba(180, 190, 100, ${ma})`);
      grad.addColorStop(1, 'rgba(180, 190, 100, 0)');
      ctx.fillStyle = grad;
      ctx.fillRect(mx, my - 20, mw, 40);
    }

    // Shimmering light overlay — subtle
    const shimmer = 0.02 + 0.01 * Math.sin(gameTime * 0.8);
    const shimmerGrad = ctx.createLinearGradient(0, 0, cw, ch);
    shimmerGrad.addColorStop(0, `rgba(200, 200, 120, ${shimmer})`);
    shimmerGrad.addColorStop(0.5, `rgba(180, 200, 100, 0)`);
    shimmerGrad.addColorStop(1, `rgba(200, 200, 120, ${shimmer})`);
    ctx.fillStyle = shimmerGrad;
    ctx.fillRect(0, 0, cw, ch);
  },

  platforms: [
    { x: -1.0, w: 2.5, y: 0, boost: false },
    { x: 2.0, w: 0.6, y: 0.12, boost: false },
    { x: 3.0, w: 0.5, y: 0.25, boost: false },
    { x: 3.8, w: 0.4, y: 0.4, boost: false },
    { x: 4.6, w: 0.7, y: 0.15, boost: false },
    { x: 5.8, w: 0.4, y: 0.3, boost: true },
    { x: 6.8, w: 0.5, y: 0.2, boost: false },
    { x: 7.6, w: 0.6, y: 0, boost: false },
    { x: 8.8, w: 0.5, y: 0.22, boost: false },
    { x: 9.5, w: 0.4, y: 0.38, boost: false },
    { x: 10.5, w: 0.7, y: 0, boost: false },
    { x: 11.5, w: 0.5, y: 0.28, boost: false },
  ],

  tokens: [
    { x: 3.25, y: 0.38, collected: false, collectTime: 0 },
    { x: 4.0, y: 0.53, collected: false, collectTime: 0 },
    { x: 6.0, y: 0.6, collected: false, collectTime: 0 },
    { x: 7.05, y: 0.33, collected: false, collectTime: 0 },
    { x: 9.05, y: 0.35, collected: false, collectTime: 0 },
    { x: 9.7, y: 0.51, collected: false, collectTime: 0 },
  ],

  arrowPickups: [
    { x: 1.5, y: 0.05, count: 3 },
    { x: 3.5, y: 0.05, count: 3 },
    { x: 6.0, y: 0.35, count: 3 },
    { x: 8.0, y: 0.05, count: 3 },
    { x: 10.8, y: 0.05, count: 3 },
  ],
};

// --- Lothlorien helpers ---

function _drawLightShafts(ctx, cw, ch, time) {
  for (let i = 0; i < 5; i++) {
    const shaftX = cw * (0.15 + hash(i * 41 + 23000) * 0.7);
    const shaftW = 20 + hash(i * 47 + 23100) * 40;
    const alpha = (0.03 + 0.02 * Math.sin(time * 0.3 + i * 2)) * (0.7 + 0.3 * Math.sin(time * 0.5 + i * 4));

    const grad = ctx.createLinearGradient(shaftX, 0, shaftX + shaftW * 0.5, ch);
    grad.addColorStop(0, `rgba(220, 210, 140, ${alpha})`);
    grad.addColorStop(0.3, `rgba(200, 200, 120, ${alpha * 0.7})`);
    grad.addColorStop(0.7, `rgba(180, 190, 100, ${alpha * 0.3})`);
    grad.addColorStop(1, `rgba(160, 180, 80, 0)`);
    ctx.fillStyle = grad;

    ctx.beginPath();
    ctx.moveTo(shaftX, 0);
    ctx.lineTo(shaftX + shaftW, 0);
    ctx.lineTo(shaftX + shaftW * 1.5, ch);
    ctx.lineTo(shaftX - shaftW * 0.3, ch);
    ctx.closePath();
    ctx.fill();
  }
}

function _drawMallornTrees(ctx, offsetX, cw, ch, config) {
  const { seed, spacing, trunkW, trunkColor, canopyY, baseY, alpha } = config;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw * 1.3 / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 67 + seed);
    if (h < 0.2) continue;
    const tx = i * spacing + hash(i * 73 + seed + 100) * spacing * 0.4;
    const tw = trunkW + hash(i * 79 + seed + 200) * 10;

    // Massive trunk — silver bark
    ctx.fillStyle = trunkColor;
    ctx.globalAlpha = alpha;

    // Trunk with slight taper
    ctx.beginPath();
    ctx.moveTo(tx - tw * 0.6, baseY);
    ctx.lineTo(tx - tw * 0.4, baseY - (baseY - canopyY) * 0.3);
    ctx.quadraticCurveTo(tx - tw * 0.35, canopyY + 50, tx - tw * 0.2, canopyY);
    ctx.lineTo(tx + tw * 0.2, canopyY);
    ctx.quadraticCurveTo(tx + tw * 0.35, canopyY + 50, tx + tw * 0.4, baseY - (baseY - canopyY) * 0.3);
    ctx.lineTo(tx + tw * 0.6, baseY);
    ctx.closePath();
    ctx.fill();

    // Silver bark highlights
    ctx.fillStyle = `rgba(160, 170, 150, ${alpha * 0.15})`;
    ctx.fillRect(Math.floor(tx - tw * 0.1), canopyY, Math.floor(tw * 0.15), baseY - canopyY);

    // Root spread at base
    for (let r = -1; r <= 1; r += 2) {
      ctx.fillStyle = trunkColor;
      ctx.beginPath();
      ctx.moveTo(tx + r * tw * 0.4, baseY);
      ctx.quadraticCurveTo(tx + r * tw * 0.8, baseY - 5, tx + r * tw * 1.2, baseY);
      ctx.lineTo(tx + r * tw * 0.4, baseY);
      ctx.closePath();
      ctx.fill();
    }

    // Golden canopy (top)
    const canopyR = tw * 2.5 + hash(i * 83 + seed + 300) * tw * 1.5;
    ctx.fillStyle = `rgba(60, 80, 30, ${alpha * 0.4})`;
    ctx.beginPath();
    ctx.arc(tx, canopyY + 20, canopyR, 0, Math.PI * 2);
    ctx.fill();

    // Golden leaf clusters
    ctx.fillStyle = `rgba(180, 160, 50, ${alpha * 0.15})`;
    for (let c = 0; c < 5; c++) {
      const cx = tx + (hash(i * 89 + c * 7 + seed + 400) - 0.5) * canopyR * 1.5;
      const cy = canopyY + hash(i * 97 + c * 11 + seed + 500) * 40;
      const cr = 8 + hash(i * 101 + c * 13 + seed + 600) * 15;
      ctx.beginPath();
      ctx.arc(cx, cy, cr, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.globalAlpha = 1;
  }
}

function _drawHangingLeaves(ctx, offsetX, cw, ch, time) {
  const spacing = 40;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 43 + 23500);
    if (h < 0.6) continue;
    const lx = i * spacing;
    const ly = ch * 0.05 + hash(i * 53 + 23600) * (ch * 0.25);
    const sway = Math.sin(time * 0.8 + i * 2) * 5;
    const length = 10 + h * 25;

    ctx.strokeStyle = `rgba(60, 80, 30, ${0.15 + h * 0.15})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(lx, ly);
    ctx.quadraticCurveTo(lx + sway, ly + length * 0.5, lx + sway * 1.3, ly + length);
    ctx.stroke();

    // Leaf at end
    ctx.fillStyle = `rgba(${170 + h * 40 | 0}, ${140 + h * 30 | 0}, ${30 + h * 20 | 0}, 0.3)`;
    ctx.beginPath();
    ctx.ellipse(lx + sway * 1.3, ly + length, 3, 1.5, sway * 0.1, 0, Math.PI * 2);
    ctx.fill();
  }
}

function _drawElvenFerns(ctx, offsetX, cw, groundY, time) {
  const spacing = 25;
  const startI = Math.floor(offsetX * SCALE / spacing) - 1;
  const endI = startI + Math.ceil(cw / spacing) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 47 + 24000);
    if (h < 0.4) continue;
    const fx = i * spacing + hash(i * 53 + 24100) * 10;
    const fh = 6 + h * 12;
    const sway = Math.sin(time * 0.5 + i * 1.5) * 2;

    // Fern frond
    ctx.strokeStyle = `rgba(50, 90, 30, ${0.3 + h * 0.2})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(fx, groundY);
    ctx.quadraticCurveTo(fx + sway, groundY - fh * 0.6, fx + sway * 1.5, groundY - fh);
    ctx.stroke();

    // Small leaf pairs
    for (let l = 0; l < 3; l++) {
      const ly = groundY - fh * (0.3 + l * 0.2);
      const lSway = sway * (0.5 + l * 0.2);
      ctx.fillStyle = `rgba(60, 100, 30, ${0.2 + h * 0.15})`;
      ctx.fillRect(Math.floor(fx + lSway - 2), Math.floor(ly), 2, 1);
      ctx.fillRect(Math.floor(fx + lSway + 1), Math.floor(ly), 2, 1);
    }
  }
}

// =====================================================================================================================
// Level registry
// =====================================================================================================================

export const LEVELS = [shire, mistyMountains, moria, mordor, lothlorien];

export function getLevel(index) {
  return LEVELS[Math.max(0, Math.min(index, LEVELS.length - 1))];
}
