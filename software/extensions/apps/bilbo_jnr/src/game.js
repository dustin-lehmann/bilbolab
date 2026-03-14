/**
 * BILBO Jump & Run — Game logic
 *
 * - Physics at 100 Hz (Ts = 0.01s) matching the real robot
 * - Rendering at display refresh rate
 * - Procedural platform generation
 * - Jump mechanics with frozen theta during airtime
 * - Particle effects and screen shake
 */

import { BilboDynamics2D, VISUAL, MODEL } from './dynamics.js';
import {
  drawBilbo, drawHUD, drawTokens, drawParticles, drawSpeedLines,
  setTime, SCALE, setLevelTime, LEVELS, getLevel,
} from './levels.js';
import { Enemy, drawEnemies } from './enemies.js';

// =====================================================================================================================
// Arrow projectiles
// =====================================================================================================================

const ARROW_SPEED = 4.0;       // [m/s]
const ARROW_GRAVITY = 6.0;     // [m/s²]
const ARROW_LENGTH = 0.18;     // [m] visual length
const ARROW_MAX_LIFE = 3.0;    // [s]
const ARROW_HIT_RADIUS = 0.1;  // [m]

// Fire attack
const FIRE_BASE_SPEED = 1.5;   // minimum fire speed [m/s]
const FIRE_SPEED_MULT = 2.5;   // additional speed per m/s of robot velocity
const FIRE_LIFE = 0.6;         // base lifetime [s]
const FIRE_HIT_RADIUS = 0.08;  // [m]
const FIRE_COOLDOWN = 0.4;     // minimum time between fire bursts [s]
const FIRE_PARTICLE_COUNT = 18; // particles per burst

// Stab attack
const STAB_RANGE = 0.35;      // max distance to stab an enemy [m]
const STAB_COOLDOWN = 0.5;    // [s]

// Ring stealth
const RING_STEALTH_MAX_SPEED = 0.3; // max speed before enemies can hear you [m/s]

class Arrow {
  constructor(x, y, vx, vy) {
    this.x = x;
    this.y = y;
    this.vx = vx;
    this.vy = vy;
    this.life = ARROW_MAX_LIFE;
    this.dead = false;
  }

  update(dt) {
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.vy -= ARROW_GRAVITY * dt;
    this.life -= dt;
    if (this.life <= 0 || this.y < -0.5) this.dead = true;
  }

  checkEnemyHit(enemy) {
    if (!enemy.alive) return false;
    const dx = Math.abs(this.x - enemy.x);
    const enemyY = enemy.verticalPos !== undefined ? enemy.verticalPos : enemy.y;
    const dy = this.y - enemyY;
    return dx < ARROW_HIT_RADIUS && dy >= 0 && dy < enemy.height + ARROW_HIT_RADIUS;
  }
}

let _fireBurstId = 0;

class FireParticle {
  constructor(x, y, vx, vy, life, burstId) {
    this.x = x;
    this.y = y;
    this.vx = vx;
    this.vy = vy;
    this.life = life;
    this.maxLife = life;
    this.size = 3 + Math.random() * 5;
    this.dead = false;
    this.burstId = burstId; // all particles from one F press share this
  }

  update(dt) {
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    // Fire rises slightly
    this.vy += 1.5 * dt;
    // Slow down over time
    this.vx *= (1 - 0.8 * dt);
    this.life -= dt;
    if (this.life <= 0 || this.y < -0.1) this.dead = true;
  }

  get alpha() { return Math.max(0, this.life / this.maxLife); }
}

// =====================================================================================================================
// Constants
// =====================================================================================================================

const PHYSICS_DT = 0.01;           // 100 Hz physics (matches real robot)
const TORQUE_MIN = 0.15;           // Instant floor torque on key press [Nm]
const TORQUE_MAX = 0.6;            // Max torque at low speed [Nm]
const TORQUE_MAX_FAST = 2.0;       // Max torque at high speed [Nm]
const TORQUE_VEL_SCALE = 2.0;     // Velocity at which torque reaches max_fast [m/s]
const TORQUE_RAMP_TIME = 0.5;     // Seconds to ramp from min to max
const JUMP_VELOCITY = 2.5;         // Vertical jump velocity [m/s]
const DOUBLE_JUMP_VELOCITY = 2.8;  // Air-jump vertical boost [m/s]
const GRAVITY = 9.81;              // Gravity for jump parabola [m/s²]
const MAX_THETA = MODEL.max_pitch; // ~105°
const WHEEL_RADIUS = VISUAL.wheel_radius;

const BOOST_JUMP_VELOCITY = 4.5;   // jump velocity on boost pads [m/s]

// Collectible tokens
const TOKEN_COLLECT_DIST = 0.08;

// =====================================================================================================================
// Input state
// =====================================================================================================================

const keys = {
  left: false,
  right: false,
  space: false,
  spacePressed: false,
  restart: false,
  rightHeldTime: 0,
  leftHeldTime: 0,
  levelSwitch: 0,  // 1-5 for debug level switching, 0 = none
  firePressed: false,
  stabPressed: false,
  arrowDown: false,
  arrowDownPressed: false,
};

function setupInput() {
  window.addEventListener('keydown', (e) => {
    if (e.code === 'ArrowLeft') keys.left = true;
    if (e.code === 'ArrowRight') keys.right = true;
    if (e.code === 'Space') {
      if (!keys.space) keys.spacePressed = true;
      keys.space = true;
    }
    if (e.code === 'KeyR') keys.restart = true;
    if (e.code === 'KeyI') keys.ringToggle = true;
    if (e.code === 'KeyF') keys.firePressed = true;
    if (e.code === 'KeyS') keys.stabPressed = true;
    if (e.code === 'ArrowDown') {
      if (!keys.arrowDown) keys.arrowDownPressed = true;
      keys.arrowDown = true;
    }

    // Debug: number keys 1-5 switch levels
    if (e.code >= 'Digit1' && e.code <= 'Digit5') {
      keys.levelSwitch = parseInt(e.code.charAt(5));
    }

    if (['ArrowLeft', 'ArrowRight', 'ArrowDown', 'Space'].includes(e.code)) e.preventDefault();
  });
  window.addEventListener('keyup', (e) => {
    if (e.code === 'ArrowLeft') keys.left = false;
    if (e.code === 'ArrowRight') keys.right = false;
    if (e.code === 'Space') keys.space = false;
    if (e.code === 'ArrowDown') keys.arrowDown = false;
  });
}

// =====================================================================================================================
// Particle system
// =====================================================================================================================

class Particle {
  constructor(x, y, vx, vy, life, color, size, gravity = 0) {
    this.x = x; this.y = y;
    this.vx = vx; this.vy = vy;
    this.life = life; this.maxLife = life;
    this.color = color; this.size = size;
    this.gravity = gravity;
  }

  update(dt) {
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.vy += this.gravity * dt;
    this.life -= dt;
  }

  get alpha() { return Math.max(0, this.life / this.maxLife); }
  get dead() { return this.life <= 0; }
}

function findGround(worldX, verticalY, platforms) {
  let bestHeight = 0;
  let bestPlatform = null;
  for (const p of platforms) {
    if (worldX >= p.x && worldX <= p.x + p.w) {
      if (p.y > bestHeight && p.y <= verticalY + 0.01) {
        bestHeight = p.y;
        bestPlatform = p;
      }
    }
  }
  return { height: bestHeight, platform: bestPlatform };
}

// =====================================================================================================================
// Game class
// =====================================================================================================================

export class Game {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');

    this.dynamics = new BilboDynamics2D(PHYSICS_DT);

    // Level system
    this.currentLevelIndex = 0;
    this.level = getLevel(0);
    this.parallaxLayers = this.level.createParallaxLayers();

    this.platforms = [];
    this.tokens = [];

    this.score = 0;

    // Jump state
    this.airborne = false;
    this.verticalPos = WHEEL_RADIUS;
    this.verticalVel = 0;
    this.frozenTheta = 0;
    this.frozenThetaDot = 0;
    this.currentGroundHeight = 0;
    this.airJumpsRemaining = 2;
    this.doubleJumpSpin = 0;
    this.doubleJumpSpinning = false;
    this.standingOnPlatform = null;

    // Wheel animation
    this.wheelAngle = 0;

    // Camera
    this.cameraX = -0.5;

    // Physics accumulator
    this.physicsAccum = 0;
    this.lastTime = null;

    // Effects
    this.particles = [];
    this.screenShake = 0;
    this.jumpGlow = 0;       // glow intensity when jumping [0..1]
    this.landSquash = 0;     // squash-stretch on landing [0..1]
    this.gameTime = 0;

    // Enemies
    this.enemies = [];

    // Arrows
    this.arrows = [];
    this.arrowCount = 24;       // inventory
    this.arrowPickups = [];     // collectible arrow stacks in world

    // Fire
    this.fireParticles = [];
    this.fireCooldown = 0;

    // Stab
    this.stabCooldown = 0;
    this.stabFlash = 0; // visual flash timer
    this.stabDir = 1;   // direction of last stab

    // Last driving direction (persists when stopped)
    this.lastDriveDir = 1;

    // Player lives
    this.lives = 3;
    this.invincibleTime = 0;  // invincibility after taking damage [s]
    this.dead = false;        // true during death sequence
    this.deathTimer = 0;      // time since death [s]

    // One Ring invisibility
    this.ringActive = false;
    this.ringFade = 0;        // 0 = normal, 1 = fully in ring world
    this.ringParticles = [];

    this._initWorld();
    setupInput();
  }

  _initWorld() {
    this.score = 0;
    this.lives = 3;
    this.invincibleTime = 0;
    this.arrows = [];
    this.arrowCount = 24;
    this.fireParticles = [];
    this.fireCooldown = 0;
    this.stabCooldown = 0;
    this.stabFlash = 0;
    this.stabDir = 1;
    this.lastDriveDir = 1;
    // Deep copy platforms and tokens from current level
    this.platforms = this.level.platforms.map(p => ({ ...p }));
    this.tokens = this.level.tokens.map(t => ({ ...t, collected: false, collectTime: 0 }));
    this.arrowPickups = (this.level.arrowPickups || []).map(a => ({ ...a, collected: false, collectTime: 0 }));
    // Create enemies from level definition
    this.enemies = (this.level.enemies || []).map(e =>
      new Enemy(e.x, e.y, e.patrolLeft, e.patrolRight, e.speed, e.type || 'orc1')
    );
  }

  switchLevel(index) {
    this.currentLevelIndex = index;
    this.level = getLevel(index);
    this.parallaxLayers = this.level.createParallaxLayers();
    this.dynamics.reset(0, 0, 0, 0);
    this.airborne = false;
    this.verticalPos = WHEEL_RADIUS;
    this.verticalVel = 0;
    this.frozenTheta = 0;
    this.frozenThetaDot = 0;
    this.currentGroundHeight = 0;
    this.airJumpsRemaining = 2;
    this.doubleJumpSpin = 0;
    this.doubleJumpSpinning = false;
    this.standingOnPlatform = null;
    this.wheelAngle = 0;
    this.cameraX = -0.5;
    this.particles = [];
    this.screenShake = 0;
    this.jumpGlow = 0;
    this.landSquash = 0;
    this._initWorld();
  }

  restart() {
    this.dynamics.reset(0, 0, 0, 0);
    this.airborne = false;
    this.verticalPos = WHEEL_RADIUS;
    this.verticalVel = 0;
    this.frozenTheta = 0;
    this.frozenThetaDot = 0;
    this.currentGroundHeight = 0;
    this.airJumpsRemaining = 2;
    this.doubleJumpSpin = 0;
    this.doubleJumpSpinning = false;
    this.standingOnPlatform = null;
    this.wheelAngle = 0;
    this.cameraX = -0.5;
    this.physicsAccum = 0;
    this.lastTime = null;
    this.particles = [];
    this.screenShake = 0;
    this.jumpGlow = 0;
    this.landSquash = 0;
    this._initWorld();
  }

  resize() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }

  // --- Particle spawners ---

  spawnJumpParticles(worldX, worldY) {
    for (let i = 0; i < 12; i++) {
      const angle = Math.PI + (Math.random() - 0.5) * Math.PI * 0.8;
      const speed = 0.3 + Math.random() * 0.8;
      this.particles.push(new Particle(
        worldX, worldY,
        Math.cos(angle) * speed, Math.sin(angle) * speed,
        0.3 + Math.random() * 0.3,
        `hsl(${270 + Math.random() * 40}, 100%, ${60 + Math.random() * 30}%)`,
        2 + Math.random() * 3,
        2.0,
      ));
    }
  }

  spawnDoubleJumpParticles(worldX, worldY) {
    for (let i = 0; i < 20; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 0.5 + Math.random() * 1.2;
      this.particles.push(new Particle(
        worldX, worldY,
        Math.cos(angle) * speed, Math.sin(angle) * speed,
        0.4 + Math.random() * 0.4,
        `hsl(${180 + Math.random() * 60}, 100%, ${65 + Math.random() * 30}%)`,
        2 + Math.random() * 4,
        1.0,
      ));
    }
  }

  spawnLandParticles(worldX, worldY) {
    for (let i = 0; i < 8; i++) {
      const vx = (Math.random() - 0.5) * 1.5;
      this.particles.push(new Particle(
        worldX + (Math.random() - 0.5) * 0.04, worldY,
        vx, -0.2 - Math.random() * 0.3,
        0.2 + Math.random() * 0.25,
        `hsl(${240 + Math.random() * 30}, 60%, ${40 + Math.random() * 20}%)`,
        2 + Math.random() * 2,
        3.0,
      ));
    }
  }

  spawnBoostParticles(worldX, worldY) {
    for (let i = 0; i < 25; i++) {
      const angle = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 0.6;
      const speed = 0.8 + Math.random() * 1.5;
      this.particles.push(new Particle(
        worldX + (Math.random() - 0.5) * 0.06, worldY,
        Math.cos(angle) * speed, Math.sin(angle) * speed,
        0.4 + Math.random() * 0.5,
        `hsl(${140 + Math.random() * 40}, 100%, ${55 + Math.random() * 35}%)`,
        3 + Math.random() * 4,
        1.5,
      ));
    }
  }

  spawnTokenParticles(worldX, worldY) {
    for (let i = 0; i < 15; i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 0.4 + Math.random() * 0.8;
      this.particles.push(new Particle(
        worldX, worldY,
        Math.cos(angle) * speed, Math.sin(angle) * speed,
        0.3 + Math.random() * 0.3,
        `hsl(${40 + Math.random() * 20}, 100%, ${60 + Math.random() * 30}%)`,
        2 + Math.random() * 3,
        0.5,
      ));
    }
  }

  _drawArrows(ctx, groundY) {
    for (const arrow of this.arrows) {
      const sx = arrow.x * SCALE - this.cameraX * SCALE;
      const sy = groundY - arrow.y * SCALE;

      // Arrow angle from velocity
      const angle = Math.atan2(-arrow.vy, arrow.vx);
      const len = ARROW_LENGTH * SCALE;

      ctx.save();
      ctx.translate(sx, sy);
      ctx.rotate(angle);

      // Shaft
      ctx.strokeStyle = '#8B6914';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(-len / 2, 0);
      ctx.lineTo(len / 2, 0);
      ctx.stroke();

      // Arrowhead
      ctx.fillStyle = '#c0c0c0';
      ctx.beginPath();
      ctx.moveTo(len / 2 + 8, 0);
      ctx.lineTo(len / 2 - 4, -5);
      ctx.lineTo(len / 2 - 4, 5);
      ctx.closePath();
      ctx.fill();

      // Fletching
      ctx.strokeStyle = '#ddd';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(-len / 2, 0);
      ctx.lineTo(-len / 2 - 7, -5);
      ctx.moveTo(-len / 2, 0);
      ctx.lineTo(-len / 2 - 7, 5);
      ctx.stroke();

      ctx.restore();
    }
  }

  _drawArrowPickups(ctx, groundY) {
    for (const a of this.arrowPickups) {
      if (a.collected) continue;
      const sx = a.x * SCALE - this.cameraX * SCALE;
      const sy = groundY - a.y * SCALE;
      if (sx < -50 || sx > ctx.canvas.width + 50) continue;
      const float = Math.sin(this.gameTime * 2.0 + a.x * 3) * 3;

      ctx.save();
      ctx.translate(sx, sy + float);

      // Draw 3 bundled arrows
      const count = a.count || 3;
      for (let i = 0; i < count; i++) {
        const offsetX = (i - (count - 1) / 2) * 5;
        const tilt = (i - (count - 1) / 2) * 0.08;
        ctx.save();
        ctx.translate(offsetX, 0);
        ctx.rotate(-Math.PI / 2 + tilt); // point upward

        // Shaft
        ctx.strokeStyle = '#8B6914';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(0, -10);
        ctx.lineTo(0, 10);
        ctx.stroke();

        // Arrowhead
        ctx.fillStyle = '#c0c0c0';
        ctx.beginPath();
        ctx.moveTo(0, -13);
        ctx.lineTo(-3, -8);
        ctx.lineTo(3, -8);
        ctx.closePath();
        ctx.fill();

        // Fletching
        ctx.strokeStyle = '#ddd';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, 10);
        ctx.lineTo(-3, 13);
        ctx.moveTo(0, 10);
        ctx.lineTo(3, 13);
        ctx.stroke();

        ctx.restore();
      }

      // Glow
      ctx.shadowColor = '#d4a020';
      ctx.shadowBlur = 8;
      ctx.fillStyle = `rgba(200, 170, 80, ${0.15 + 0.1 * Math.sin(this.gameTime * 3 + a.x)})`;
      ctx.beginPath();
      ctx.arc(0, 0, 14, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      ctx.restore();
    }
  }

  _drawFire(ctx, groundY) {
    ctx.save();
    for (const fp of this.fireParticles) {
      const sx = fp.x * SCALE - this.cameraX * SCALE;
      const sy = groundY - fp.y * SCALE;
      const a = fp.alpha;
      const size = fp.size * (0.5 + a * 0.5);

      // Core glow
      ctx.shadowColor = `rgba(255, 160, 30, ${a * 0.8})`;
      ctx.shadowBlur = size * 2;

      // Color shifts from bright yellow/white core to orange to red as it fades
      const r = 255;
      const g = Math.floor(200 * a + 40 * (1 - a));
      const b = Math.floor(60 * a * a);
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${a * 0.9})`;
      ctx.beginPath();
      ctx.arc(sx, sy, size, 0, Math.PI * 2);
      ctx.fill();

      // Bright inner core
      if (a > 0.4) {
        ctx.fillStyle = `rgba(255, 255, 200, ${(a - 0.4) * 1.2})`;
        ctx.beginPath();
        ctx.arc(sx, sy, size * 0.4, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.shadowBlur = 0;
    ctx.restore();
  }

  // ===================================================================================================================
  // Physics step (100 Hz)
  // ===================================================================================================================

  physicsStep() {
    // During death sequence: only update enemies, particles, timer — skip player control
    if (this.dead) {
      this.deathTimer += PHYSICS_DT;
      this.gameTime += PHYSICS_DT;
      this.screenShake *= 0.92;
      // Keep enemies active so they can keep attacking the corpse
      for (const enemy of this.enemies) {
        enemy.update(PHYSICS_DT, this.dynamics.s, false, this.verticalPos, this.platforms);
      }
      this.enemies = this.enemies.filter(e => !e.removed);
      for (const p of this.particles) p.update(PHYSICS_DT);
      this.particles = this.particles.filter(p => !p.dead);
      if (this.deathTimer >= 5.0) {
        this.dead = false;
        this.deathTimer = 0;
        this.restart();
      }
      return;
    }

    // Update held timers
    if (keys.right) keys.rightHeldTime += PHYSICS_DT; else keys.rightHeldTime = 0;
    if (keys.left) keys.leftHeldTime += PHYSICS_DT; else keys.leftHeldTime = 0;

    // Compute torque input — progressive ramp + velocity-dependent max
    // At higher speed, allow more torque (TORQUE_MAX scales up to TORQUE_MAX_FAST)
    const absV = Math.abs(this.dynamics.v);
    const velFactor = Math.min(absV / TORQUE_VEL_SCALE, 1);
    const torqueMax = TORQUE_MAX + (TORQUE_MAX_FAST - TORQUE_MAX) * velFactor;

    let uExt = 0;
    if (keys.right) {
      const t = Math.min(keys.rightHeldTime / TORQUE_RAMP_TIME, 1);
      uExt -= TORQUE_MIN + (torqueMax - TORQUE_MIN) * t * t;
      this.lastDriveDir = 1;
    }
    if (keys.left) {
      const t = Math.min(keys.leftHeldTime / TORQUE_RAMP_TIME, 1);
      uExt += TORQUE_MIN + (torqueMax - TORQUE_MIN) * t * t;
      this.lastDriveDir = -1;
    }

    if (this.airborne) {
      // === AIRBORNE DYNAMICS ===
      this.dynamics.stepAirborne(uExt, this.frozenTheta, this.frozenThetaDot);

      // Air jump (double/triple)
      if (keys.spacePressed && this.airJumpsRemaining > 0) {
        keys.spacePressed = false;
        this.airJumpsRemaining--;
        this.verticalVel = DOUBLE_JUMP_VELOCITY;
        this.doubleJumpSpinning = true;
        this.doubleJumpSpin = 0;
        this.jumpGlow = 1.0;
        this.screenShake = 0.15;
        this.spawnDoubleJumpParticles(this.dynamics.s, this.verticalPos);
      } else if (keys.spacePressed && this.airJumpsRemaining === 0 && this.arrowCount >= 3) {
        // No air jumps left — shoot arrows downward on every space press
        keys.spacePressed = false;
        this.arrowCount -= 3;
        const px = this.dynamics.s;
        const py = this.verticalPos;
        const angles = [-10, 0, 10];
        for (const deg of angles) {
          const rad = (deg * Math.PI) / 180;
          const vx = Math.sin(rad) * ARROW_SPEED;
          const vy = -Math.cos(rad) * ARROW_SPEED;
          this.arrows.push(new Arrow(px, py, vx, vy));
        }
      }

      // Body spin animation (~0.4s)
      if (this.doubleJumpSpinning) {
        this.doubleJumpSpin += (Math.PI * 2) / (0.4 / PHYSICS_DT);
        if (this.doubleJumpSpin >= Math.PI * 2) {
          this.doubleJumpSpin = 0;
          this.doubleJumpSpinning = false;
        }
      }

      // Vertical parabola
      this.verticalVel -= GRAVITY * PHYSICS_DT;
      this.verticalPos += this.verticalVel * PHYSICS_DT;

      // Check landing
      const { height: groundH, platform: landPlatform } = findGround(
        this.dynamics.s, this.verticalPos, this.platforms);
      const landingY = groundH + WHEEL_RADIUS;

      const doLand = (h, platform) => {
        this.verticalPos = h + WHEEL_RADIUS;
        this.verticalVel = 0;
        this.airborne = false;
        this.currentGroundHeight = h;
        this.airJumpsRemaining = 2;
        this.doubleJumpSpinning = false;
        this.doubleJumpSpin = 0;
        // Reset theta to near-zero on landing to prevent controller instability
        // (frozenTheta can be large after spinning/tumbling in air)
        this.dynamics.state[2] = 0;
        this.dynamics.state[3] = 0;
        // Dampen velocity on landing to prevent air speed carrying over
        this.dynamics.state[1] *= 0.22;
        this.landSquash = 1.0;
        this.screenShake = 0.08;
        this.spawnLandParticles(this.dynamics.s, h);
        this.standingOnPlatform = platform;
      };

      if (this.verticalPos <= landingY && this.verticalVel <= 0) {
        doLand(groundH, landPlatform);
      }

      if (this.verticalPos < WHEEL_RADIUS) {
        doLand(0, null);
      }
    } else {
      // === GROUNDED DYNAMICS ===
      this.dynamics.step(uExt);

      // Clamp theta at max_pitch — robot has fallen over, kill velocity
      if (Math.abs(this.dynamics.theta) > MAX_THETA) {
        const sign = Math.sign(this.dynamics.theta);
        this.dynamics.state[2] = sign * MAX_THETA;
        this.dynamics.state[3] = -this.dynamics.state[3] * 0.3; // damped bounce
        this.dynamics.state[1] *= 0.9; // bleed off velocity — wheels not gripping
      }

      // Check ground under robot
      const { height: groundH } = findGround(this.dynamics.s, this.verticalPos, this.platforms);

      if (groundH < this.currentGroundHeight - 0.01) {
        this.airborne = true;
        this.verticalVel = 0;
        this.frozenTheta = this.dynamics.theta;
        this.frozenThetaDot = 0;
        this.currentGroundHeight = groundH;
      } else {
        this.currentGroundHeight = groundH;
        this.verticalPos = groundH + WHEEL_RADIUS;
      }

      // Track current platform
      const { platform: curPlat } = findGround(this.dynamics.s, this.verticalPos, this.platforms);
      this.standingOnPlatform = curPlat;

      // Jump initiation
      if (keys.spacePressed && !this.airborne) {
        keys.spacePressed = false;
        this.airborne = true;
        const onBoost = this.standingOnPlatform && this.standingOnPlatform.boost;
        this.verticalVel = onBoost ? BOOST_JUMP_VELOCITY : JUMP_VELOCITY;
        this.frozenTheta = this.dynamics.theta;
        this.frozenThetaDot = 0;
        this.jumpGlow = 1.0;
        if (onBoost) {
          this.screenShake = 0.2;
          this.spawnBoostParticles(this.dynamics.s, this.currentGroundHeight);
        }
        this.spawnJumpParticles(this.dynamics.s, this.currentGroundHeight);
      }
    }

    // Consume edge triggers
    keys.spacePressed = false;

    // Shoot arrows downward on ArrowDown
    if (keys.arrowDownPressed && this.arrowCount >= 3) {
      keys.arrowDownPressed = false;
      this.arrowCount -= 3;
      const px = this.dynamics.s;
      const py = this.verticalPos;
      const angles = [-10, 0, 10]; // degrees from straight down
      for (const deg of angles) {
        const rad = (deg * Math.PI) / 180;
        const vx = Math.sin(rad) * ARROW_SPEED;
        const vy = -Math.cos(rad) * ARROW_SPEED;
        this.arrows.push(new Arrow(px, py, vx, vy));
      }
    }
    keys.arrowDownPressed = false;

    // Fire attack
    if (this.fireCooldown > 0) this.fireCooldown -= PHYSICS_DT;
    if (keys.firePressed && this.fireCooldown <= 0) {
      keys.firePressed = false;
      this.fireCooldown = FIRE_COOLDOWN;
      const speed = Math.abs(this.dynamics.v);
      const fireSpeed = FIRE_BASE_SPEED + speed * FIRE_SPEED_MULT;
      const dir = this.dynamics.v >= 0 ? 1 : -1;
      const px = this.dynamics.s + dir * 0.05;
      const py = this.verticalPos + WHEEL_RADIUS * 0.3;
      const burstId = ++_fireBurstId;
      for (let i = 0; i < FIRE_PARTICLE_COUNT; i++) {
        const spreadAngle = (Math.random() - 0.5) * 0.5; // radians
        const speedVar = 0.6 + Math.random() * 0.8;
        const vx = dir * fireSpeed * speedVar * Math.cos(spreadAngle);
        const vy = fireSpeed * speedVar * Math.sin(spreadAngle) * 0.3;
        const life = FIRE_LIFE * (0.5 + Math.random() * 0.8) * (0.5 + speed * 0.3);
        this.fireParticles.push(new FireParticle(
          px + (Math.random() - 0.5) * 0.03,
          py + (Math.random() - 0.5) * 0.03,
          vx, vy, life, burstId
        ));
      }
      this.screenShake = 0.06;
    }
    keys.firePressed = false;

    // Update fire particles and check enemy hits (max 1 damage per burst per enemy)
    for (const fp of this.fireParticles) {
      fp.update(PHYSICS_DT);
      if (fp.dead) continue;
      for (const enemy of this.enemies) {
        if (!enemy.alive) continue;
        // Skip if this burst already damaged this enemy
        if (!enemy._fireBurstHits) enemy._fireBurstHits = new Set();
        if (enemy._fireBurstHits.has(fp.burstId)) continue;
        const dx = Math.abs(fp.x - enemy.x);
        const fpEnemyY = enemy.verticalPos !== undefined ? enemy.verticalPos : enemy.y;
        const dy = fp.y - fpEnemyY;
        if (dx < FIRE_HIT_RADIUS + (enemy.width || 0.12) && dy >= 0 && dy < (enemy.height || 0.18) + FIRE_HIT_RADIUS) {
          enemy.damage(1);
          enemy._fireBurstHits.add(fp.burstId);
          break;
        }
      }
    }

    this.fireParticles = this.fireParticles.filter(fp => !fp.dead);

    // Stab attack
    if (this.stabCooldown > 0) this.stabCooldown -= PHYSICS_DT;
    if (this.stabFlash > 0) this.stabFlash -= PHYSICS_DT;
    if (keys.stabPressed && this.stabCooldown <= 0) {
      keys.stabPressed = false;
      this.stabCooldown = STAB_COOLDOWN;
      this.stabDir = this.lastDriveDir;
      this.stabFlash = 0.25;
      // Damage: 2 when invisible (stealth bonus), 1 when visible
      const stealthActive = this.ringFade > 0.5;
      const dmg = stealthActive ? 2 : 1;
      // Find closest enemy in stab range (in the stab direction)
      let closest = null;
      let closestDist = Infinity;
      for (const enemy of this.enemies) {
        if (!enemy.alive) continue;
        const dx = enemy.x - this.dynamics.s;
        const absDx = Math.abs(dx);
        const enemyY = enemy.verticalPos !== undefined ? enemy.verticalPos : enemy.y;
        const dy = Math.abs(this.verticalPos - enemyY);
        // Must be in the direction we're stabbing and within range
        if (absDx < STAB_RANGE && dy < 0.3 && absDx < closestDist &&
            Math.sign(dx) === this.stabDir) {
          closest = enemy;
          closestDist = absDx;
        }
      }
      if (closest) {
        closest.damage(dmg);
        this.screenShake = 0.2;
        // Knock enemy back 0.3m away from BILBO
        closest.x += this.stabDir * 0.3;
        // Small BILBO hop
        this.verticalVel = 0.5;
        this.airborne = true;
        this.invincibleTime = Math.max(this.invincibleTime, 0.4);
        // Spawn stab spark particles at the enemy
        for (let i = 0; i < 12; i++) {
          const angle = Math.random() * Math.PI * 2;
          const speed = 0.5 + Math.random() * 1.0;
          this.particles.push(new Particle(
            closest.x, closest.y + 0.1,
            Math.cos(angle) * speed, Math.sin(angle) * speed,
            0.2 + Math.random() * 0.2,
            stealthActive
              ? `hsl(${200 + Math.random() * 40}, 80%, ${70 + Math.random() * 25}%)`
              : `hsl(${40 + Math.random() * 20}, 90%, ${60 + Math.random() * 30}%)`,
            2 + Math.random() * 3,
            1.0,
          ));
        }
      }
      // Break stealth — deactivate the One Ring
      if (this.ringActive) {
        this.ringActive = false;
      }
    }
    keys.stabPressed = false;

    // One Ring toggle
    if (keys.ringToggle) {
      keys.ringToggle = false;
      this.ringActive = !this.ringActive;
    }
    // Smooth fade in/out
    const ringTarget = this.ringActive ? 1 : 0;
    this.ringFade += (ringTarget - this.ringFade) * (this.ringActive ? 0.06 : 0.1);
    if (Math.abs(this.ringFade - ringTarget) < 0.005) this.ringFade = ringTarget;

    // Spawn ring-world particles — tiny Brownian motion dust everywhere
    if (this.ringFade > 0.1) {
      const camW = this.canvas.width / SCALE;
      const camH = this.canvas.height / SCALE;
      const maxParticles = 1200;
      const spawnCount = Math.floor(20 + this.ringFade * 30);
      for (let i = 0; i < spawnCount && this.ringParticles.length < maxParticles; i++) {
        const px = this.cameraX - camW * 0.1 + Math.random() * camW * 1.2;
        const py = Math.random() * camH * 1.1;
        this.ringParticles.push({
          x: px, y: py,
          vx: (Math.random() - 0.5) * 0.05,
          vy: (Math.random() - 0.5) * 0.05,
          life: 3.0 + Math.random() * 4.0,
          size: 1.0 + Math.random() * 2.5,
        });
      }
    }
    // Update ring particles with Brownian motion
    for (const rp of this.ringParticles) {
      // Random walk — small impulses each step
      rp.vx += (Math.random() - 0.5) * 0.12;
      rp.vy += (Math.random() - 0.5) * 0.12;
      // Dampen to prevent runaway
      rp.vx *= 0.95;
      rp.vy *= 0.95;
      rp.x += rp.vx * PHYSICS_DT;
      rp.y += rp.vy * PHYSICS_DT;
      rp.life -= PHYSICS_DT * 0.3;
    }
    this.ringParticles = this.ringParticles.filter(rp => rp.life > 0);

    // Wheel rotation
    this.wheelAngle += (this.dynamics.v * PHYSICS_DT) / WHEEL_RADIUS;

    // Collect tokens
    for (const t of this.tokens) {
      if (t.collected) continue;
      const dx = this.dynamics.s - t.x;
      const dy = this.verticalPos - t.y;
      if (Math.sqrt(dx * dx + dy * dy) < TOKEN_COLLECT_DIST) {
        t.collected = true;
        t.collectTime = this.gameTime;
        this.score += 10;
        this.spawnTokenParticles(t.x, t.y);
      }
    }

    // Collect arrow pickups
    for (const a of this.arrowPickups) {
      if (a.collected) continue;
      const dx = this.dynamics.s - a.x;
      const dy = this.verticalPos - a.y;
      if (Math.sqrt(dx * dx + dy * dy) < TOKEN_COLLECT_DIST + 0.02) {
        a.collected = true;
        a.collectTime = this.gameTime;
        this.arrowCount += (a.count || 3);
        // Spawn pickup particles
        for (let i = 0; i < 8; i++) {
          const angle = Math.random() * Math.PI * 2;
          const speed = 0.3 + Math.random() * 0.5;
          this.particles.push(new Particle(
            a.x, a.y,
            Math.cos(angle) * speed, Math.sin(angle) * speed,
            0.25 + Math.random() * 0.2,
            `hsl(${30 + Math.random() * 15}, 70%, ${50 + Math.random() * 25}%)`,
            2 + Math.random() * 2, 0.5,
          ));
        }
      }
    }

    // Update enemies
    const playerInvisible = this.ringFade > 0.5 && Math.abs(this.dynamics.v) < RING_STEALTH_MAX_SPEED;
    for (const enemy of this.enemies) {
      enemy.update(PHYSICS_DT, this.dynamics.s, playerInvisible, this.verticalPos, this.platforms);

      const result = enemy.checkCollision(
        this.dynamics.s, this.verticalPos, this.verticalVel, WHEEL_RADIUS
      );
      if (result === 'stomp' || result === 'hit') {
        if (this.invincibleTime <= 0 && !playerInvisible) {
          this.lives--;
          this.invincibleTime = 1.5;
          this.screenShake = 0.3;
          // Knock BILBO back ~0.5m horizontally
          const knockDir = Math.sign(this.dynamics.s - enemy.x) || 1;
          this.dynamics.state[1] = knockDir * 1.5;
          this.dynamics.state[0] += knockDir * 0.15;  // immediate position nudge
          this.verticalVel = 0.8;  // small hop so it doesn't look glued to ground
          this.airborne = true;
        }
      }
    }
    // Remove enemies after hurt animation completes
    this.enemies = this.enemies.filter(e => !e.removed);

    // Update arrows
    for (const arrow of this.arrows) {
      arrow.update(PHYSICS_DT);
      if (arrow.dead) continue;
      for (const enemy of this.enemies) {
        if (arrow.checkEnemyHit(enemy)) {
          enemy.damage(1);
          arrow.dead = true;
          this.screenShake = 0.1;
          this.spawnTokenParticles(arrow.x, arrow.y);
          break;
        }
      }
      // Remove arrow if it hits the ground
      if (arrow.y <= 0) arrow.dead = true;
    }
    this.arrows = this.arrows.filter(a => !a.dead);

    // Invincibility timer
    if (this.invincibleTime > 0) this.invincibleTime -= PHYSICS_DT;

    // Death check — enter death sequence
    if (this.lives <= 0 && !this.dead) {
      this.dead = true;
      this.deathTimer = 0;
      this.invincibleTime = 0;
      // Kill all velocity, set pitch to 90° (fallen over)
      this.dynamics.state[1] = 0;
      this.dynamics.state[2] = Math.PI / 2;   // 90° pitch — tipped over
      this.dynamics.state[3] = 0;
      this.verticalVel = 0;
      this.airborne = false;
      this.verticalPos = this.currentGroundHeight + WHEEL_RADIUS;
      return; // next physicsStep will enter the death fast-path at the top
    }

    // Decay effects
    this.jumpGlow *= 0.96;
    this.landSquash *= 0.9;
    this.screenShake *= 0.92;

    // Update particles
    for (const p of this.particles) p.update(PHYSICS_DT);
    this.particles = this.particles.filter(p => !p.dead);

    this.gameTime += PHYSICS_DT;
  }

  // ===================================================================================================================
  // Render
  // ===================================================================================================================

  render() {
    const ctx = this.ctx;
    const cw = this.canvas.width;
    const ch = this.canvas.height;

    const groundY = ch * 0.88;

    setTime(this.gameTime);
    setLevelTime(this.gameTime);

    // Camera follows robot smoothly
    const targetCameraX = this.dynamics.s - (cw / SCALE) * 0.35;
    this.cameraX += (targetCameraX - this.cameraX) * 0.08;

    // Screen shake offset
    const shakeX = (Math.random() - 0.5) * this.screenShake * 30;
    const shakeY = (Math.random() - 0.5) * this.screenShake * 30;

    ctx.save();
    ctx.translate(shakeX, shakeY);

    // Clear
    ctx.clearRect(-10, -10, cw + 20, ch + 20);

    // Parallax background
    for (const layer of this.parallaxLayers) {
      layer.draw(ctx, this.cameraX, cw, ch);
    }

    // One Ring — background wraith particles (behind everything)
    if (this.ringFade > 0.01) {
      for (const rp of this.ringParticles) {
        const rpx = rp.x * SCALE - this.cameraX * SCALE;
        const rpy = groundY - rp.y * SCALE;
        const alpha = Math.min(rp.life / 3, 1) * this.ringFade * 0.6;
        const sz = rp.size;
        ctx.fillStyle = `rgba(170, 165, 160, ${alpha})`;
        ctx.beginPath();
        ctx.arc(rpx, rpy, sz, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // Ground (level-specific)
    this.level.drawGround(ctx, this.cameraX, cw, ch, groundY);

    // Platforms (level-specific)
    for (const p of this.platforms) {
      if (p.y > 0.01) {
        this.level.drawPlatform(ctx, p, this.cameraX, groundY);
      }
    }

    // Tokens
    drawTokens(ctx, this.tokens, this.cameraX, groundY, this.gameTime);

    // Arrow pickups
    this._drawArrowPickups(ctx, groundY);

    // Enemies
    drawEnemies(ctx, this.enemies, this.cameraX, groundY);

    // Arrows
    this._drawArrows(ctx, groundY);

    // Fire
    this._drawFire(ctx, groundY);

    // Stab slash visual — Sting blade arc
    if (this.stabFlash > 0) {
      const sx = this.dynamics.s * SCALE - this.cameraX * SCALE;
      const sy = groundY - this.verticalPos * SCALE;
      const alpha = Math.min(this.stabFlash / 0.12, 1);
      const dir = this.stabDir;
      ctx.save();
      ctx.translate(sx, sy);

      // Outer blade arc — bright blue-white sweep
      ctx.globalAlpha = alpha;
      ctx.shadowColor = '#80c0ff';
      ctx.shadowBlur = 18 * alpha;
      ctx.strokeStyle = '#d0eaff';
      ctx.lineWidth = 4;
      ctx.beginPath();
      if (dir === 1) {
        ctx.arc(18, -18, 38, -Math.PI * 0.7, Math.PI * 0.2);
      } else {
        ctx.arc(-18, -18, 38, Math.PI * 0.8, Math.PI * 1.7);
      }
      ctx.stroke();

      // Inner glow arc
      ctx.strokeStyle = '#a0d8ff';
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      if (dir === 1) {
        ctx.arc(18, -18, 28, -Math.PI * 0.5, Math.PI * 0.1);
      } else {
        ctx.arc(-18, -18, 28, Math.PI * 0.9, Math.PI * 1.5);
      }
      ctx.stroke();

      // Blade line — the stab thrust
      ctx.strokeStyle = `rgba(180, 220, 255, ${alpha})`;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(0, -16);
      ctx.lineTo(dir * 45, -20);
      ctx.stroke();

      ctx.shadowBlur = 0;
      ctx.globalAlpha = 1;
      ctx.restore();
    }

    // Particles (behind robot)
    drawParticles(ctx, this.particles, this.cameraX, groundY, SCALE);

    // Speed lines when moving fast
    const absV = Math.abs(this.dynamics.v);
    if (absV > 0.3) {
      drawSpeedLines(ctx, this.dynamics.s, this.verticalPos, this.cameraX, groundY, absV, this.gameTime);
    }

    // One Ring — wraith world effects
    if (this.ringFade > 0.01) {
      const rf = this.ringFade;

      // Desaturate
      ctx.save();
      ctx.globalCompositeOperation = 'saturation';
      ctx.fillStyle = `rgba(128, 128, 128, ${rf * 0.9})`;
      ctx.fillRect(-10, -10, cw + 20, ch + 20);
      ctx.restore();

      // Dark overlay
      ctx.save();
      ctx.globalAlpha = rf * 0.35;
      ctx.fillStyle = '#000';
      ctx.fillRect(-10, -10, cw + 20, ch + 20);
      ctx.globalAlpha = 1;
      ctx.restore();

      // Heavy mist layers
      for (let i = 0; i < 6; i++) {
        const mx = (cw * 0.5) + Math.sin(this.gameTime * 0.2 + i * 1.8) * cw * 0.4;
        const my = ch * (0.2 + i * 0.12) + Math.sin(this.gameTime * 0.3 + i * 2.5) * 30;
        const mr = 120 + i * 40;
        const ma = rf * (0.08 + 0.04 * Math.sin(this.gameTime * 0.4 + i * 3));
        const grad = ctx.createRadialGradient(mx, my, 0, mx, my, mr);
        grad.addColorStop(0, `rgba(140, 135, 130, ${ma})`);
        grad.addColorStop(0.6, `rgba(120, 115, 110, ${ma * 0.5})`);
        grad.addColorStop(1, 'rgba(120, 115, 110, 0)');
        ctx.fillStyle = grad;
        ctx.fillRect(mx - mr, my - mr, mr * 2, mr * 2);
      }

      // Ground-level dense fog
      const fogH = 80;
      const fogAlpha = rf * (0.2 + 0.08 * Math.sin(this.gameTime * 0.5));
      const fogGrad = ctx.createLinearGradient(0, groundY - fogH, 0, groundY + 10);
      fogGrad.addColorStop(0, 'rgba(100, 95, 90, 0)');
      fogGrad.addColorStop(0.4, `rgba(100, 95, 90, ${fogAlpha * 0.5})`);
      fogGrad.addColorStop(1, `rgba(80, 75, 70, ${fogAlpha})`);
      ctx.fillStyle = fogGrad;
      ctx.fillRect(-10, groundY - fogH, cw + 20, fogH + 10);

    }

    // BILBO robot — draw to offscreen canvas when ring active for true transparency
    if (this.ringFade > 0.01) {
      // Use offscreen canvas to avoid globalAlpha resets inside drawBilbo
      if (!this._ringCanvas) {
        this._ringCanvas = document.createElement('canvas');
        this._ringCtx = this._ringCanvas.getContext('2d');
      }
      this._ringCanvas.width = cw;
      this._ringCanvas.height = ch;
      const rc = this._ringCtx;
      rc.clearRect(0, 0, cw, ch);
      rc.save();
      rc.translate(shakeX, shakeY);
      drawBilbo(rc, this.dynamics.s, this.verticalPos, this.dynamics.theta,
        this.cameraX, groundY, this.wheelAngle, this.doubleJumpSpin,
        this.jumpGlow, this.landSquash, this.airborne, this.gameTime);
      rc.restore();
      ctx.save();
      ctx.globalAlpha = 1 - this.ringFade * 0.7;
      ctx.drawImage(this._ringCanvas, -shakeX, -shakeY);
      ctx.restore();
    } else {
      // Blink when invincible
      const showBilbo = this.invincibleTime <= 0 || Math.floor(this.invincibleTime * 10) % 2 === 0;
      if (showBilbo) {
        drawBilbo(ctx, this.dynamics.s, this.verticalPos, this.dynamics.theta,
          this.cameraX, groundY, this.wheelAngle, this.doubleJumpSpin,
          this.jumpGlow, this.landSquash, this.airborne, this.gameTime);
      }
    }

    // Atmospheric effects (level-specific, after robot)
    this.level.drawAtmosphere(ctx, cw, ch, groundY, this.gameTime, this.cameraX);

    ctx.restore(); // undo shake

    // One Ring — blur overlay on top of everything
    if (this.ringFade > 0.01) {
      const blurAmount = Math.round(this.ringFade * 4); // up to 4px blur
      if (blurAmount > 0) {
        ctx.save();
        ctx.filter = `blur(${blurAmount}px)`;
        ctx.globalAlpha = this.ringFade * 0.45;
        ctx.drawImage(this.canvas, 0, 0);
        ctx.filter = 'none';
        ctx.globalAlpha = 1;
        ctx.restore();
      }
    }

    // HUD (outside shake)
    drawHUD(ctx, this.dynamics.state, cw, this.score, this.airborne, this.airJumpsRemaining, this.lives, this.arrowCount);

    // Death overlay
    if (this.dead) {
      // Red tint that fades in over the first second, then pulses gently
      const fadeIn = Math.min(this.deathTimer / 1.0, 1.0);
      const pulse = 0.02 * Math.sin(this.deathTimer * 3);
      const redAlpha = (0.25 + pulse) * fadeIn;
      ctx.save();
      ctx.fillStyle = `rgba(120, 0, 0, ${redAlpha})`;
      ctx.fillRect(0, 0, cw, ch);

      // Vignette darkening around the edges
      const vigAlpha = 0.4 * fadeIn;
      const vigGrad = ctx.createRadialGradient(cw / 2, ch / 2, cw * 0.25, cw / 2, ch / 2, cw * 0.7);
      vigGrad.addColorStop(0, 'rgba(0, 0, 0, 0)');
      vigGrad.addColorStop(1, `rgba(0, 0, 0, ${vigAlpha})`);
      ctx.fillStyle = vigGrad;
      ctx.fillRect(0, 0, cw, ch);

      // "YOU DIED" text that fades in after 0.5s
      if (this.deathTimer > 0.5) {
        const textFade = Math.min((this.deathTimer - 0.5) / 1.0, 1.0);
        ctx.globalAlpha = textFade;
        ctx.font = 'bold 64px "Courier New", monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.8)';
        ctx.lineWidth = 5;
        ctx.strokeText('YOU DIED', cw / 2, ch * 0.4);
        ctx.fillStyle = '#cc2020';
        ctx.fillText('YOU DIED', cw / 2, ch * 0.4);

        // Countdown
        const remaining = Math.ceil(5.0 - this.deathTimer);
        if (remaining > 0 && this.deathTimer > 1.5) {
          const countFade = Math.min((this.deathTimer - 1.5) / 0.5, 1.0);
          ctx.globalAlpha = countFade * 0.7;
          ctx.font = '24px "Courier New", monospace';
          ctx.fillStyle = '#aa8080';
          ctx.fillText(`Respawning in ${remaining}...`, cw / 2, ch * 0.4 + 50);
        }
      }
      ctx.restore();
    }

    // Level name indicator (debug)
    ctx.save();
    ctx.font = '13px "Courier New", monospace';
    ctx.fillStyle = 'rgba(180, 170, 140, 0.6)';
    ctx.textAlign = 'center';
    ctx.fillText(`${this.level.name}  [1-5 to switch]`, cw / 2, ch - 12);
    ctx.restore();
  }

  // ===================================================================================================================
  // Main loop
  // ===================================================================================================================

  tick(timestamp) {
    if (keys.restart) {
      keys.restart = false;
      this.restart();
    }

    // Debug: level switching with number keys
    if (keys.levelSwitch > 0) {
      const idx = keys.levelSwitch - 1;
      keys.levelSwitch = 0;
      if (idx !== this.currentLevelIndex) {
        this.switchLevel(idx);
      }
    }



    if (this.lastTime === null) this.lastTime = timestamp;

    let dt = (timestamp - this.lastTime) / 1000;
    this.lastTime = timestamp;
    if (dt > 0.1) dt = 0.1;

    this.physicsAccum += dt;
    while (this.physicsAccum >= PHYSICS_DT) {
      this.physicsStep();
      this.physicsAccum -= PHYSICS_DT;
    }

    this.render();
    requestAnimationFrame((t) => this.tick(t));
  }

  start() {
    this.resize();
    window.addEventListener('resize', () => this.resize());
    requestAnimationFrame((t) => this.tick(t));
  }
}
