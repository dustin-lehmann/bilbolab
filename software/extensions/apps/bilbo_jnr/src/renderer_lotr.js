/**
 * LOTR Theme Renderer for BILBO Jump & Run
 *
 * Middle-earth aesthetic: misty mountains, ancient forests, rolling grasslands,
 * stone ruins, and moody atmospheric lighting.
 */

import { VISUAL } from './dynamics.js';

const SCALE = 400;

// =====================================================================================================================
// Parallax layer
// =====================================================================================================================

class ParallaxLayer {
  constructor(speedFactor, drawFn) {
    this.speedFactor = speedFactor;
    this.drawFn = drawFn;
  }

  draw(ctx, cameraX, canvasW, canvasH) {
    ctx.save();
    ctx.translate(-cameraX * this.speedFactor * SCALE, 0);
    this.drawFn(ctx, cameraX * this.speedFactor, canvasW, canvasH);
    ctx.restore();
  }
}

// =====================================================================================================================
// Hash for procedural generation
// =====================================================================================================================

function hash(x) {
  x = ((x >> 16) ^ x) * 0x45d9f3b;
  x = ((x >> 16) ^ x) * 0x45d9f3b;
  x = (x >> 16) ^ x;
  return (x & 0x7fffffff) / 0x7fffffff;
}

// =====================================================================================================================
// Stars — faint, Middle-earth night sky
// =====================================================================================================================

function drawStars(ctx, cw, ch, time) {
  for (let i = 0; i < 100; i++) {
    const x = hash(i * 7 + 1) * cw;
    const y = hash(i * 13 + 3) * ch * 0.4;
    const twinkle = 0.4 + 0.6 * Math.sin(time * (0.8 + hash(i * 29 + 9) * 2) + hash(i * 37 + 11) * 10);
    const brightness = (0.15 + hash(i * 23 + 7) * 0.45) * twinkle;
    // Warm-tinted stars
    const warmth = hash(i * 41 + 13);
    const r = 220 + warmth * 35;
    const g = 200 + warmth * 40;
    const b = 180 + (1 - warmth) * 75;
    ctx.fillStyle = `rgba(${r | 0}, ${g | 0}, ${b | 0}, ${brightness})`;
    const sz = 0.5 + hash(i * 19 + 5) * 1.2;
    ctx.fillRect(Math.floor(x), Math.floor(y), Math.ceil(sz), Math.ceil(sz));
  }

  // Eärendil — the brightest star
  const earendilX = cw * 0.72;
  const earendilY = ch * 0.08;
  const earendilPulse = 0.7 + 0.3 * Math.sin(time * 1.2);
  ctx.shadowColor = 'rgba(200, 220, 255, 0.8)';
  ctx.shadowBlur = 12 * earendilPulse;
  ctx.fillStyle = `rgba(220, 235, 255, ${0.6 + earendilPulse * 0.4})`;
  ctx.fillRect(Math.floor(earendilX), Math.floor(earendilY), 3, 3);
  ctx.shadowBlur = 0;
}

// =====================================================================================================================
// Moon
// =====================================================================================================================

function drawMoon(ctx, cw, ch, time) {
  const mx = cw * 0.18;
  const my = ch * 0.12;
  const r = 22;

  // Glow
  const glowGrad = ctx.createRadialGradient(mx, my, r * 0.5, mx, my, r * 4);
  glowGrad.addColorStop(0, 'rgba(200, 195, 170, 0.15)');
  glowGrad.addColorStop(0.4, 'rgba(180, 175, 150, 0.06)');
  glowGrad.addColorStop(1, 'rgba(180, 175, 150, 0)');
  ctx.fillStyle = glowGrad;
  ctx.beginPath();
  ctx.arc(mx, my, r * 4, 0, Math.PI * 2);
  ctx.fill();

  // Moon body
  ctx.fillStyle = '#d8d0b8';
  ctx.beginPath();
  ctx.arc(mx, my, r, 0, Math.PI * 2);
  ctx.fill();

  // Crescent shadow
  ctx.fillStyle = '#1a1820';
  ctx.beginPath();
  ctx.arc(mx + 8, my - 3, r * 0.88, 0, Math.PI * 2);
  ctx.fill();

  // Surface details
  ctx.fillStyle = 'rgba(160, 150, 130, 0.15)';
  ctx.beginPath();
  ctx.arc(mx - 5, my + 2, 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(mx - 8, my - 5, 2, 0, Math.PI * 2);
  ctx.fill();
}

// =====================================================================================================================
// Mountains — Misty Mountains
// =====================================================================================================================

function drawMountainRange(ctx, offsetX, cw, ch, config) {
  const { seed, baseY, minH, maxH, peakW, colors, snowLine, mist } = config;
  const groundY = ch;

  const step = peakW * 0.6;
  const startI = Math.floor(offsetX * SCALE / step) - 3;
  const endI = startI + Math.ceil(cw * 1.5 / step) + 6;

  // Mountain silhouettes
  ctx.beginPath();
  ctx.moveTo(-100, groundY);

  for (let i = startI; i <= endI; i++) {
    const h0 = hash(i * 73 + seed);
    const h1 = hash(i * 137 + seed + 500);
    const peakH = minH + h0 * (maxH - minH);
    const px = i * step + h1 * step * 0.4;
    const py = baseY - peakH;

    // Jagged peaks with sub-peaks
    if (i === startI) {
      ctx.lineTo(px - peakW * 0.5, baseY);
    }
    // Slope up
    const midH = peakH * (0.4 + hash(i * 211 + seed + 800) * 0.3);
    ctx.lineTo(px - peakW * 0.3, baseY - midH);
    ctx.lineTo(px, py);
    // Sub-peak
    const subPeakOff = hash(i * 179 + seed + 300) * 0.2;
    ctx.lineTo(px + peakW * (0.1 + subPeakOff), py + peakH * 0.15);
    ctx.lineTo(px + peakW * 0.3, baseY - midH * 0.7);
    ctx.lineTo(px + peakW * 0.5, baseY);
  }

  ctx.lineTo(cw + 200, groundY);
  ctx.closePath();

  // Fill with gradient
  const grad = ctx.createLinearGradient(0, baseY - maxH, 0, baseY);
  grad.addColorStop(0, colors[0]);
  grad.addColorStop(0.4, colors[1]);
  grad.addColorStop(1, colors[2]);
  ctx.fillStyle = grad;
  ctx.fill();

  // Snow caps
  if (snowLine) {
    for (let i = startI; i <= endI; i++) {
      const h0 = hash(i * 73 + seed);
      const h1 = hash(i * 137 + seed + 500);
      const peakH = minH + h0 * (maxH - minH);
      if (peakH < maxH * 0.6) continue;
      const px = i * step + h1 * step * 0.4;
      const py = baseY - peakH;
      const snowH = peakH * 0.18;

      ctx.fillStyle = `rgba(200, 205, 215, ${0.15 + h0 * 0.15})`;
      ctx.beginPath();
      ctx.moveTo(px - peakW * 0.12, py + snowH);
      ctx.lineTo(px, py);
      ctx.lineTo(px + peakW * 0.1, py + snowH * 0.8);
      ctx.closePath();
      ctx.fill();
    }
  }

  // Mist between mountains
  if (mist) {
    const mistGrad = ctx.createLinearGradient(0, baseY - mist.height, 0, baseY);
    mistGrad.addColorStop(0, 'rgba(0,0,0,0)');
    mistGrad.addColorStop(0.5, `rgba(${mist.color}, ${mist.alpha * 0.5})`);
    mistGrad.addColorStop(1, `rgba(${mist.color}, ${mist.alpha})`);
    ctx.fillStyle = mistGrad;
    ctx.fillRect(0, baseY - mist.height, cw + 200, mist.height);
  }
}

// =====================================================================================================================
// Forest treeline
// =====================================================================================================================

function drawForest(ctx, offsetX, cw, ch, config) {
  const { seed, baseY, minH, maxH, spacing, colors, fogAlpha } = config;

  const startI = Math.floor(offsetX * SCALE / spacing) - 2;
  const endI = startI + Math.ceil(cw * 1.5 / spacing) + 4;

  for (let i = startI; i <= endI; i++) {
    const h0 = hash(i * 67 + seed);
    const h1 = hash(i * 131 + seed + 400);
    const h2 = hash(i * 193 + seed + 700);
    const treeH = minH + h0 * (maxH - minH);
    const tx = i * spacing + h1 * spacing * 0.6;
    const ty = baseY;
    const colorIdx = Math.floor(h2 * colors.length) % colors.length;

    const isPine = h2 > 0.45;

    if (isPine) {
      // Pine tree — triangular layers
      const trunkW = 3;
      ctx.fillStyle = colors[colorIdx];

      // Multiple triangle layers
      const layers = 3;
      for (let l = 0; l < layers; l++) {
        const layerH = treeH * (0.35 - l * 0.05);
        const layerW = treeH * (0.35 - l * 0.08);
        const layerY = ty - treeH * 0.3 - l * treeH * 0.22;
        ctx.beginPath();
        ctx.moveTo(tx, layerY - layerH);
        ctx.lineTo(tx - layerW, layerY);
        ctx.lineTo(tx + layerW, layerY);
        ctx.closePath();
        ctx.fill();
      }

      // Trunk
      ctx.fillStyle = '#1a120a';
      ctx.fillRect(tx - trunkW / 2, ty - treeH * 0.3, trunkW, treeH * 0.3);
    } else {
      // Deciduous tree — round canopy
      const canopyR = treeH * 0.32;
      const trunkH = treeH * 0.4;
      const trunkW = 3 + h0 * 2;

      // Trunk
      ctx.fillStyle = '#1a120a';
      ctx.fillRect(tx - trunkW / 2, ty - trunkH, trunkW, trunkH);

      // Canopy — overlapping circles
      ctx.fillStyle = colors[colorIdx];
      const cY = ty - trunkH - canopyR * 0.4;
      ctx.beginPath();
      ctx.arc(tx, cY, canopyR, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(tx - canopyR * 0.5, cY + canopyR * 0.2, canopyR * 0.7, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(tx + canopyR * 0.5, cY + canopyR * 0.15, canopyR * 0.75, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Atmospheric fog over the forest
  if (fogAlpha > 0) {
    const fogGrad = ctx.createLinearGradient(0, baseY - maxH, 0, baseY);
    fogGrad.addColorStop(0, `rgba(25, 30, 35, 0)`);
    fogGrad.addColorStop(0.4, `rgba(30, 35, 40, ${fogAlpha * 0.3})`);
    fogGrad.addColorStop(1, `rgba(35, 40, 45, ${fogAlpha})`);
    ctx.fillStyle = fogGrad;
    ctx.fillRect(0, baseY - maxH, cw + 200, maxH);
  }
}

// =====================================================================================================================
// Foreground vegetation — grass, flowers, rocks, roots
// =====================================================================================================================

function drawForegroundVegetation(ctx, offsetX, cw, groundY) {
  const startI = Math.floor(offsetX * SCALE / 8) - 1;
  const endI = startI + Math.ceil(cw / 8) + 2;

  for (let i = startI; i <= endI; i++) {
    const h = hash(i * 47 + 5555);
    const x = i * 8 + hash(i * 83 + 111) * 4;

    // Biome-dependent detail based on position
    const biome = hash(Math.floor(i / 30) * 31 + 9999);

    if (h > 0.7) {
      // Tall grass blade
      const bladeH = 4 + hash(i * 59 + 222) * 8;
      const lean = (hash(i * 71 + 333) - 0.5) * 3;
      ctx.strokeStyle = biome < 0.4
        ? `rgba(45, 75, 30, ${0.4 + h * 0.3})`
        : `rgba(60, 85, 40, ${0.3 + h * 0.3})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, groundY);
      ctx.quadraticCurveTo(x + lean, groundY - bladeH * 0.6, x + lean * 1.5, groundY - bladeH);
      ctx.stroke();
    }

    if (h > 0.92) {
      // Wildflower
      const fy = groundY - 3 - hash(i * 97 + 444) * 6;
      const flowerHue = hash(i * 103 + 555) < 0.5 ? '#c8a848' : '#a86848';
      ctx.fillStyle = flowerHue;
      ctx.fillRect(Math.floor(x), Math.floor(fy), 2, 2);
    }

    // Occasional small rocks
    if (h > 0.85 && h < 0.92 && biome > 0.5) {
      const rw = 4 + hash(i * 107 + 666) * 6;
      const rh = 2 + hash(i * 109 + 777) * 3;
      ctx.fillStyle = `rgba(80, 75, 65, ${0.3 + hash(i * 113 + 888) * 0.3})`;
      ctx.fillRect(Math.floor(x), Math.floor(groundY - rh), Math.floor(rw), Math.floor(rh));
    }
  }
}

// =====================================================================================================================
// Fireflies
// =====================================================================================================================

function drawFireflies(ctx, cw, ch, groundY, time) {
  for (let i = 0; i < 20; i++) {
    const baseX = hash(i * 53 + 7070) * cw;
    const baseY = groundY - 30 - hash(i * 67 + 8080) * (ch * 0.4);
    const wobbleX = Math.sin(time * (0.5 + hash(i * 71 + 9090) * 1.5) + i * 3) * 15;
    const wobbleY = Math.cos(time * (0.4 + hash(i * 79 + 1010) * 1.2) + i * 5) * 10;
    const pulse = 0.3 + 0.7 * Math.max(0, Math.sin(time * (1 + hash(i * 83 + 2020) * 2) + i * 4));

    if (pulse > 0.4) {
      ctx.shadowColor = 'rgba(180, 200, 100, 0.6)';
      ctx.shadowBlur = 8 * pulse;
      ctx.fillStyle = `rgba(200, 220, 120, ${pulse * 0.7})`;
      ctx.fillRect(Math.floor(baseX + wobbleX), Math.floor(baseY + wobbleY), 2, 2);
    }
  }
  ctx.shadowBlur = 0;
}

// =====================================================================================================================
// Mist wisps — drifting low fog
// =====================================================================================================================

function drawMistWisps(ctx, cw, groundY, time) {
  for (let i = 0; i < 6; i++) {
    const baseX = (hash(i * 113 + 3030) * cw * 2 + time * (8 + i * 3)) % (cw + 300) - 150;
    const baseY = groundY - 5 - hash(i * 127 + 4040) * 40;
    const w = 80 + hash(i * 131 + 5050) * 120;
    const h = 8 + hash(i * 139 + 6060) * 15;
    const alpha = 0.03 + 0.04 * Math.sin(time * 0.3 + i * 2);

    const grad = ctx.createRadialGradient(baseX + w / 2, baseY, 0, baseX + w / 2, baseY, w / 2);
    grad.addColorStop(0, `rgba(160, 170, 180, ${alpha})`);
    grad.addColorStop(1, 'rgba(160, 170, 180, 0)');
    ctx.fillStyle = grad;
    ctx.fillRect(baseX, baseY - h, w, h * 2);
  }
}

// =====================================================================================================================
// Create parallax layers
// =====================================================================================================================

let _time = 0;
export function setTime(t) { _time = t; }

export function createParallaxLayers() {
  // Layer 0: Sky — twilight/dusk gradient with stars and moon
  const sky = new ParallaxLayer(0, (ctx, ox, cw, ch) => {
    const grad = ctx.createLinearGradient(0, 0, 0, ch);
    grad.addColorStop(0, '#0a0e14');
    grad.addColorStop(0.15, '#121a24');
    grad.addColorStop(0.35, '#1a2530');
    grad.addColorStop(0.55, '#253040');
    grad.addColorStop(0.72, '#2a3838');
    grad.addColorStop(0.85, '#2d3a30');
    grad.addColorStop(1.0, '#1a2818');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, cw, ch);

    drawStars(ctx, cw, ch, _time);
    drawMoon(ctx, cw, ch, _time);
  });

  // Layer 1: Far Misty Mountains — very faded, snowy peaks
  const farMountains = new ParallaxLayer(0.08, (ctx, ox, cw, ch) => {
    drawMountainRange(ctx, ox, cw, ch, {
      seed: 42,
      baseY: ch * 0.75,
      minH: 100,
      maxH: 320,
      peakW: 120,
      colors: ['#1a2028', '#182028', '#1c2530'],
      snowLine: true,
      mist: { height: 120, color: '30, 40, 50', alpha: 0.35 },
    });
  });

  // Layer 2: Mid mountains — darker, closer
  const midMountains = new ParallaxLayer(0.18, (ctx, ox, cw, ch) => {
    drawMountainRange(ctx, ox, cw, ch, {
      seed: 137,
      baseY: ch * 0.82,
      minH: 60,
      maxH: 200,
      peakW: 90,
      colors: ['#141e1a', '#162018', '#1a2520'],
      snowLine: false,
      mist: { height: 80, color: '25, 35, 30', alpha: 0.25 },
    });
  });

  // Layer 3: Far forest — dark Mirkwood-style treeline
  const farForest = new ParallaxLayer(0.32, (ctx, ox, cw, ch) => {
    drawForest(ctx, ox, cw, ch, {
      seed: 333,
      baseY: ch * 0.88,
      minH: 40,
      maxH: 100,
      spacing: 18,
      colors: ['#0e1a10', '#101c12', '#0c1810', '#121e14'],
      fogAlpha: 0.3,
    });
  });

  // Layer 4: Near forest / hills — with visible tree shapes
  const nearForest = new ParallaxLayer(0.52, (ctx, ox, cw, ch) => {
    // Rolling hill silhouette
    const hillBaseY = ch * 0.9;
    ctx.beginPath();
    ctx.moveTo(-50, ch);
    const hillStep = 60;
    const hillStart = Math.floor(ox * SCALE / hillStep) - 2;
    const hillEnd = hillStart + Math.ceil(cw * 1.5 / hillStep) + 4;
    for (let i = hillStart; i <= hillEnd; i++) {
      const hx = i * hillStep;
      const hh = 10 + hash(i * 43 + 7777) * 25;
      const hy = hillBaseY - hh;
      ctx.quadraticCurveTo(hx - hillStep * 0.25, hy, hx, hillBaseY - hh * 0.3);
    }
    ctx.lineTo(cw + 200, ch);
    ctx.closePath();

    const hillGrad = ctx.createLinearGradient(0, hillBaseY - 35, 0, hillBaseY);
    hillGrad.addColorStop(0, '#1a2a18');
    hillGrad.addColorStop(1, '#142214');
    ctx.fillStyle = hillGrad;
    ctx.fill();

    drawForest(ctx, ox, cw, ch, {
      seed: 777,
      baseY: ch * 0.9,
      minH: 25,
      maxH: 65,
      spacing: 14,
      colors: ['#152210', '#1a2814', '#132010', '#1c2c16'],
      fogAlpha: 0.12,
    });
  });

  return [sky, farMountains, midMountains, farForest, nearForest];
}

// =====================================================================================================================
// Ground — grassy earth with terrain variation
// =====================================================================================================================

export function drawGround(ctx, cameraX, canvasW, canvasH, groundY) {
  const gy = groundY;

  // Earth fill
  const earthGrad = ctx.createLinearGradient(0, gy, 0, canvasH);
  earthGrad.addColorStop(0, '#2a3a1e');
  earthGrad.addColorStop(0.15, '#1e2a14');
  earthGrad.addColorStop(0.4, '#18220e');
  earthGrad.addColorStop(1, '#0e1508');
  ctx.fillStyle = earthGrad;
  ctx.fillRect(0, gy, canvasW, canvasH - gy);

  // Grass top — irregular pixel-art grass line
  const grassStartI = Math.floor(cameraX * SCALE / 3);
  const grassEndI = grassStartI + Math.ceil(canvasW / 3) + 1;
  for (let i = grassStartI; i < grassEndI; i++) {
    const gx = i * 3 - cameraX * SCALE;
    const h = hash(i * 41 + 2222);
    const grassH = 1 + Math.floor(h * 4);
    const shade = 0.3 + h * 0.4;
    ctx.fillStyle = `rgba(${50 + shade * 40 | 0}, ${80 + shade * 50 | 0}, ${30 + shade * 20 | 0}, 1)`;
    ctx.fillRect(Math.floor(gx), Math.floor(gy - grassH), 3, grassH + 1);
  }

  // Dirt/path patches visible below grass
  const patchStartI = Math.floor(cameraX * SCALE / 50);
  const patchEndI = patchStartI + Math.ceil(canvasW / 50) + 2;
  for (let i = patchStartI; i < patchEndI; i++) {
    const h = hash(i * 89 + 3333);
    if (h > 0.7) {
      const px = i * 50 - cameraX * SCALE + hash(i * 97 + 4444) * 20;
      const pw = 10 + hash(i * 101 + 5555) * 30;
      ctx.fillStyle = `rgba(60, 50, 35, ${0.15 + h * 0.15})`;
      ctx.fillRect(Math.floor(px), gy + 2, Math.floor(pw), 4);
    }
  }

  // Foreground vegetation (grass blades, flowers, rocks)
  drawForegroundVegetation(ctx, cameraX, canvasW, gy);

  // Low mist wisps
  drawMistWisps(ctx, canvasW, gy, _time);

  // Fireflies near the ground
  drawFireflies(ctx, canvasW, canvasH, gy, _time);
}

// =====================================================================================================================
// Platforms — ancient stone ruins
// =====================================================================================================================

export function drawPlatform(ctx, platform, cameraX, groundY) {
  const px = platform.x * SCALE - cameraX * SCALE;
  const pw = platform.w * SCALE;
  const py = groundY - platform.y * SCALE;
  const ph = 20;
  const isBoost = platform.boost;

  // Support columns — weathered stone pillars
  const pillarW = 6;
  ctx.fillStyle = isBoost ? 'rgba(80, 100, 60, 0.3)' : 'rgba(70, 65, 55, 0.25)';
  ctx.fillRect(px + 3, py + ph, pillarW, groundY - py - ph);
  ctx.fillRect(px + pw - 3 - pillarW, py + ph, pillarW, groundY - py - ph);

  // Pillar detail — stone segments
  for (let sy = py + ph + 8; sy < groundY - 5; sy += 12) {
    ctx.fillStyle = 'rgba(90, 80, 70, 0.1)';
    ctx.fillRect(px + 3, sy, pillarW, 1);
    ctx.fillRect(px + pw - 3 - pillarW, sy, pillarW, 1);
  }

  // Platform body — stone block
  if (isBoost) {
    // Elven platform — silver-green with inner glow
    const grad = ctx.createLinearGradient(px, py, px, py + ph);
    grad.addColorStop(0, '#4a6a3a');
    grad.addColorStop(0.5, '#3a5a2a');
    grad.addColorStop(1, '#2a4a1a');
    ctx.fillStyle = grad;
    ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

    // Elven glow top
    ctx.shadowColor = '#8ab860';
    ctx.shadowBlur = 12;
    ctx.fillStyle = '#8ab860';
    ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 2);
    ctx.shadowBlur = 0;

    // Elven runes / leaf motif
    ctx.fillStyle = 'rgba(140, 190, 100, 0.25)';
    for (let x = px + 10; x < px + pw - 10; x += 16) {
      const rx = Math.floor(x);
      const ry = Math.floor(py + 7);
      // Simple leaf shape
      ctx.fillRect(rx, ry, 2, 6);
      ctx.fillRect(rx - 1, ry + 2, 4, 2);
    }
  } else {
    // Weathered stone
    const grad = ctx.createLinearGradient(px, py, px, py + ph);
    grad.addColorStop(0, '#5a5548');
    grad.addColorStop(0.3, '#4a4538');
    grad.addColorStop(1, '#3a352a');
    ctx.fillStyle = grad;
    ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), ph);

    // Stone block lines
    ctx.fillStyle = 'rgba(30, 28, 22, 0.3)';
    ctx.fillRect(Math.floor(px), Math.floor(py + ph * 0.45), Math.ceil(pw), 1);

    // Vertical mortar lines
    for (let x = px + 15; x < px + pw - 10; x += 20 + hash(Math.floor(x) * 71 + 888) * 15) {
      const topH = ph * 0.45;
      const botH = ph * 0.55;
      const sx = Math.floor(x);
      ctx.fillRect(sx, Math.floor(py), 1, topH);
      ctx.fillRect(sx + 8, Math.floor(py + topH), 1, botH);
    }

    // Top edge — lighter capstone
    ctx.fillStyle = '#6a6555';
    ctx.fillRect(Math.floor(px), Math.floor(py), Math.ceil(pw), 3);

    // Moss patches
    ctx.fillStyle = 'rgba(55, 80, 35, 0.35)';
    for (let x = px + 2; x < px + pw - 5; x += 8) {
      const h = hash(Math.floor(x) * 67 + Math.floor(py) * 31 + 1234);
      if (h > 0.55) {
        const mw = 3 + h * 5;
        ctx.fillRect(Math.floor(x), Math.floor(py), Math.floor(mw), 3);
        // Dripping moss
        if (h > 0.8) {
          ctx.fillRect(Math.floor(x + 1), Math.floor(py + 3), 1, 2 + Math.floor(h * 4));
        }
      }
    }

    // Cracks
    ctx.strokeStyle = 'rgba(25, 22, 18, 0.2)';
    ctx.lineWidth = 1;
    const crackSeed = hash(Math.floor(px) * 53 + 7777);
    if (crackSeed > 0.6) {
      const cx = px + pw * (0.3 + crackSeed * 0.4);
      ctx.beginPath();
      ctx.moveTo(cx, py);
      ctx.lineTo(cx + 3, py + ph * 0.3);
      ctx.lineTo(cx - 1, py + ph * 0.6);
      ctx.lineTo(cx + 2, py + ph);
      ctx.stroke();
    }
  }
}

// =====================================================================================================================
// BILBO robot — same as cyberpunk but with warm tones
// =====================================================================================================================

export function drawBilbo(ctx, worldX, worldY, theta, cameraX, groundY,
  wheelAngle = 0, spinAngle = 0, jumpGlow = 0, landSquash = 0,
  airborne = false, gameTime = 0) {

  const screenX = worldX * SCALE - cameraX * SCALE;
  const screenY = groundY - worldY * SCALE;

  ctx.save();
  ctx.translate(screenX, screenY);

  const squash = 1 + landSquash * 0.15;
  const stretch = 1 - landSquash * 0.1;
  ctx.scale(squash, stretch);

  const rOuter = VISUAL.wheel_radius * SCALE;
  const rInner = VISUAL.wheel_radius * VISUAL.wheel_inner_ratio * SCALE;
  const bw = VISUAL.body_width * SCALE;
  const bh = VISUAL.body_height * SCALE;
  const cr = VISUAL.body_corner_radius * SCALE;

  // Jump glow — warm golden
  if (jumpGlow > 0.05) {
    const glowR = rOuter * 2 + jumpGlow * 30;
    const glowGrad = ctx.createRadialGradient(0, 0, rOuter * 0.5, 0, 0, glowR);
    glowGrad.addColorStop(0, `rgba(200, 170, 80, ${jumpGlow * 0.35})`);
    glowGrad.addColorStop(0.5, `rgba(180, 140, 60, ${jumpGlow * 0.15})`);
    glowGrad.addColorStop(1, 'rgba(180, 140, 60, 0)');
    ctx.fillStyle = glowGrad;
    ctx.beginPath();
    ctx.arc(0, -bh * 0.3, glowR, 0, Math.PI * 2);
    ctx.fill();
  }

  // Afterimage trail
  if (airborne && Math.abs(theta) > 0.01) {
    ctx.globalAlpha = 0.12;
    ctx.save();
    ctx.rotate(theta + spinAngle - 0.05);
    ctx.fillStyle = '#8a7040';
    roundRect(ctx, -bw / 2, -bh, bw, bh, cr);
    ctx.fill();
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  // === Body ===
  ctx.save();
  ctx.rotate(theta + spinAngle);

  ctx.shadowColor = 'rgba(200, 170, 80, 0.3)';
  ctx.shadowBlur = 8;

  // Body — warm bronze/copper tone
  ctx.fillStyle = '#8a6a35';
  ctx.strokeStyle = '#2a2010';
  ctx.lineWidth = 2;
  roundRect(ctx, -bw / 2, -bh, bw, bh, cr);
  ctx.fill();
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Panel lines
  ctx.fillStyle = '#7a5a28';
  ctx.fillRect(-bw / 2 + 3, -bh + 3, bw - 6, 2);
  ctx.fillRect(-bw / 2 + 3, -bh * 0.55, bw - 6, 1);
  ctx.fillRect(-bw / 2 + 3, -bh * 0.38, bw - 6, 1);

  // Eye — warm amber
  const eyeY = -bh * 0.72;
  const eyePulse = 0.8 + 0.2 * Math.sin(gameTime * 4);
  const eyeR = bw * 0.16 * eyePulse;
  ctx.shadowColor = '#d4a840';
  ctx.shadowBlur = 12;
  ctx.fillStyle = '#d4a840';
  ctx.beginPath();
  ctx.arc(0, eyeY, eyeR, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Eye highlight
  ctx.fillStyle = '#fff8e0';
  ctx.beginPath();
  ctx.arc(-eyeR * 0.25, eyeY - eyeR * 0.25, eyeR * 0.3, 0, Math.PI * 2);
  ctx.fill();

  // Status LEDs — warm tones
  const ledY = -bh * 0.22;
  for (let li = -1; li <= 1; li++) {
    const ledOn = Math.sin(gameTime * 3 + li * 2) > 0;
    ctx.fillStyle = ledOn ? '#c8a848' : '#2a2818';
    ctx.fillRect(-3 + li * 7, ledY, 3, 3);
  }

  ctx.restore(); // body rotation

  // === Wheel ===
  ctx.fillStyle = '#1a1810';
  ctx.strokeStyle = '#3a3828';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(0, 0, rOuter, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  // Hub — warm metal
  ctx.fillStyle = '#b8a888';
  ctx.strokeStyle = '#706848';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(0, 0, rInner, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  // Spokes
  ctx.save();
  ctx.rotate(wheelAngle);
  ctx.strokeStyle = '#907848';
  ctx.lineWidth = 2;
  for (let i = 0; i < 4; i++) {
    const angle = (i / 4) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(Math.cos(angle) * rInner * 0.85, Math.sin(angle) * rInner * 0.85);
    ctx.stroke();
  }
  ctx.fillStyle = '#605030';
  ctx.beginPath();
  ctx.arc(0, 0, 2, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  ctx.restore(); // translate + scale
}

// =====================================================================================================================
// Tokens — The One Ring
// =====================================================================================================================

export function drawTokens(ctx, tokens, cameraX, groundY, gameTime) {
  for (const t of tokens) {
    if (t.collected) continue;
    const tx = t.x * SCALE - cameraX * SCALE;
    const ty = groundY - t.y * SCALE;
    const float = Math.sin(gameTime * 2.5 + t.x * 4) * 3;

    ctx.save();
    ctx.translate(tx, ty + float);

    // Golden glow
    ctx.shadowColor = '#d4a020';
    ctx.shadowBlur = 16;

    // Ring — outer circle
    const r = 8;
    ctx.strokeStyle = '#d4a020';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Ring highlight
    ctx.strokeStyle = '#f0d060';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(0, 0, r, -Math.PI * 0.7, -Math.PI * 0.2);
    ctx.stroke();

    // Inner glow
    const innerGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
    innerGrad.addColorStop(0, 'rgba(220, 180, 60, 0.15)');
    innerGrad.addColorStop(1, 'rgba(220, 180, 60, 0)');
    ctx.fillStyle = innerGrad;
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.fill();

    // Elvish script suggestion — tiny marks around ring
    const scriptPulse = 0.3 + 0.7 * Math.max(0, Math.sin(gameTime * 1.5 + t.x * 3));
    if (scriptPulse > 0.5) {
      ctx.fillStyle = `rgba(255, 200, 80, ${scriptPulse * 0.4})`;
      for (let a = 0; a < 8; a++) {
        const angle = (a / 8) * Math.PI * 2 + gameTime * 0.5;
        const sx = Math.cos(angle) * (r + 3);
        const sy = Math.sin(angle) * (r + 3);
        ctx.fillRect(Math.floor(sx), Math.floor(sy), 1, 1);
      }
    }

    ctx.restore();
  }
}

// =====================================================================================================================
// Particles — earthy / leafy
// =====================================================================================================================

export function drawParticles(ctx, particles, cameraX, groundY, scale) {
  for (const p of particles) {
    const sx = p.x * scale - cameraX * scale;
    const sy = groundY - p.y * scale;
    const alpha = p.alpha;
    const size = p.size * alpha;

    ctx.globalAlpha = alpha;
    ctx.shadowColor = p.color;
    ctx.shadowBlur = 4;
    ctx.fillStyle = p.color;
    ctx.fillRect(Math.floor(sx - size / 2), Math.floor(sy - size / 2),
      Math.ceil(size), Math.ceil(size));
  }
  ctx.globalAlpha = 1;
  ctx.shadowBlur = 0;
}

// =====================================================================================================================
// Speed lines — wind / leaves
// =====================================================================================================================

export function drawSpeedLines(ctx, worldX, worldY, cameraX, groundY, speed, gameTime) {
  const screenX = worldX * SCALE - cameraX * SCALE;
  const screenY = groundY - worldY * SCALE;
  const intensity = Math.min(speed / 1.5, 1);
  const count = Math.floor(intensity * 6);

  ctx.globalAlpha = intensity * 0.2;
  ctx.lineWidth = 1;

  for (let i = 0; i < count; i++) {
    const seed = Math.sin(gameTime * 8 + i * 7.3) * 0.5 + 0.5;
    const offsetY = (seed - 0.5) * 50;
    const len = 8 + seed * 20 * intensity;
    const x = screenX + 15 + seed * 5;

    // Alternating earth tones
    ctx.strokeStyle = seed > 0.5 ? '#6a8a4a' : '#8a7a5a';
    ctx.beginPath();
    ctx.moveTo(x, screenY + offsetY);
    ctx.lineTo(x + len, screenY + offsetY - 2);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

// =====================================================================================================================
// HUD — parchment style
// =====================================================================================================================

export function drawHUD(ctx, state, canvasW, score, airborne, airJumpsRemaining = 2, lives = 3, arrowCount = 0) {
  ctx.save();

  // Arrow inventory — individual arrows along top edge
  const arrowBarX = 240;
  const arrowBarY = 14;
  const arrowSpacing = 8;
  const maxShow = Math.min(arrowCount, 40); // cap visual at 40

  ctx.fillStyle = 'rgba(30, 25, 18, 0.7)';
  const barW = Math.max(80, maxShow * arrowSpacing + 30);
  ctx.fillRect(arrowBarX, 10, barW, 24);
  ctx.strokeStyle = '#5a4a30';
  ctx.lineWidth = 1;
  ctx.strokeRect(arrowBarX, 10, barW, 24);
  ctx.fillStyle = '#8a7a50';
  ctx.fillRect(arrowBarX, 10, barW, 2);

  // Draw individual arrow icons
  for (let i = 0; i < maxShow; i++) {
    const ax = arrowBarX + 10 + i * arrowSpacing;
    const ay = arrowBarY + 10;
    ctx.strokeStyle = '#8B6914';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(ax, ay + 5);
    ctx.lineTo(ax, ay - 5);
    ctx.stroke();
    // Tiny arrowhead
    ctx.fillStyle = '#c0c0c0';
    ctx.beginPath();
    ctx.moveTo(ax, ay - 7);
    ctx.lineTo(ax - 2, ay - 4);
    ctx.lineTo(ax + 2, ay - 4);
    ctx.closePath();
    ctx.fill();
  }
  // Count text
  ctx.font = 'bold 10px "Courier New", monospace';
  ctx.fillStyle = '#b8a878';
  ctx.textAlign = 'right';
  ctx.fillText(`${arrowCount}`, arrowBarX + barW - 6, arrowBarY + 12);
  ctx.textAlign = 'left';

  // Parchment panel
  ctx.fillStyle = 'rgba(30, 25, 18, 0.85)';
  ctx.fillRect(10, 10, 220, 146);
  ctx.strokeStyle = '#5a4a30';
  ctx.lineWidth = 1;
  ctx.strokeRect(10, 10, 220, 146);

  // Top accent — gold
  ctx.fillStyle = '#8a7a50';
  ctx.fillRect(10, 10, 220, 2);

  ctx.font = '12px "Courier New", monospace';
  ctx.fillStyle = '#b8a878';
  ctx.textAlign = 'left';

  const thetaDeg = (state[2] * 180 / Math.PI).toFixed(1);
  const vel = state[1].toFixed(2);
  const pos = state[0].toFixed(2);

  ctx.fillText(`POS   ${pos} m`, 20, 32);
  ctx.fillText(`VEL   ${vel} m/s`, 20, 48);
  ctx.fillText(`THETA ${thetaDeg}°`, 20, 64);

  ctx.fillStyle = '#d4a840';
  ctx.font = 'bold 14px "Courier New", monospace';
  ctx.fillText(`RINGS ${score}`, 20, 84);

  ctx.font = '11px "Courier New", monospace';
  if (airborne) {
    ctx.fillStyle = '#c89848';
    ctx.fillText('◆ AIRBORNE', 20, 102);
  } else {
    ctx.fillStyle = '#6a9a48';
    ctx.fillText('◆ GROUNDED', 20, 102);
  }

  ctx.fillStyle = airJumpsRemaining > 0 ? '#b8a060' : '#3a3828';
  ctx.fillText(`◆ AIR-JUMP ×${airJumpsRemaining}`, 20, 118);

  // Lives
  ctx.fillStyle = lives > 1 ? '#c86040' : '#ff3030';
  ctx.font = 'bold 12px "Courier New", monospace';
  ctx.fillText(`♥ LIVES ×${lives}`, 20, 136);

  // Controls hint (right side)
  ctx.fillStyle = 'rgba(30, 25, 18, 0.85)';
  ctx.fillRect(canvasW - 220, 10, 210, 148);
  ctx.strokeStyle = '#5a4a30';
  ctx.strokeRect(canvasW - 220, 10, 210, 148);
  ctx.fillStyle = '#8a7a50';
  ctx.fillRect(canvasW - 220, 10, 210, 2);

  ctx.fillStyle = '#6a6050';
  ctx.font = '11px "Courier New", monospace';
  ctx.textAlign = 'right';
  ctx.fillText('← → DRIVE', canvasW - 20, 30);
  ctx.fillText('SPACE JUMP', canvasW - 20, 46);
  ctx.fillText('SPACE×3 TRIPLE-JUMP', canvasW - 20, 62);
  ctx.fillText('↓ ARROWS (×3)', canvasW - 20, 78);
  ctx.fillText('F FIRE', canvasW - 20, 94);
  ctx.fillText('S STAB (STING)', canvasW - 20, 110);
  ctx.fillText('I ONE RING', canvasW - 20, 126);
  ctx.fillText('R RESTART', canvasW - 20, 142);

  ctx.restore();
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

export { SCALE, ParallaxLayer, hash, roundRect, drawMountainRange, drawForest, drawForegroundVegetation, drawFireflies, drawMistWisps, drawStars, drawMoon, _time };
