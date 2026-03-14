/**
 * BILBO Jump & Run — Enemy System
 *
 * Individual-frame sprite enemies (orcs and trolls) that patrol platforms and ground.
 * Uses PNG frame sequences from public/sprites/.
 */

import { SCALE } from './renderer_lotr.js';

// =====================================================================================================================
// Sprite frame loading
// =====================================================================================================================

const DRAW_HEIGHT = 210;  // 140 * 1.5

// AI ranges [m]
const ATTACK_RANGE = 0.18;
const CHASE_SPEED_MULT = 1.8;   // chase speed relative to patrol speed
const AGGRO_SPEED_MULT = 4.5;   // aggro patrol/chase speed relative to base speed

// Vertical physics for enemies
const ENEMY_GRAVITY = 9.81;
const ENEMY_JUMP_VEL = 2.8;       // jump velocity [m/s]
const ENEMY_JUMP_COOLDOWN = 0.4;   // min time between jumps [s]
const ENEMY_MAX_JUMP_H = (ENEMY_JUMP_VEL * ENEMY_JUMP_VEL) / (2 * ENEMY_GRAVITY);  // ~0.40m
const ENEMY_MAX_HORIZ_REACH = 0.9; // max horizontal gap coverable during a jump [m]
const ENEMY_PATH_RECOMPUTE = 0.4;  // recompute path interval [s]

const ENEMY_TYPES = {
  orc1: {
    folder: 'sprites/1_ORK',
    prefix: 'ORK_01',
    anims: {
      walk:   { name: 'WALK',  frames: 10, speed: 8 },
      run:    { name: 'RUN',   frames: 10, speed: 10 },
      attack: { name: 'ATTAK', frames: 10, speed: 12 },
      hurt:   { name: 'HURT',  frames: 10, speed: 12 },
      die:    { name: 'DIE',   frames: 10, speed: 8 },
    },
    hp: 3,
    sightRange: 1.8,      // directional vision range [m]
    hearRange: 0.5,        // omnidirectional hearing range [m]
    aggroSightRange: 3.5,  // sight range once aggro'd [m]
    width: 0.12,
    height: 0.18,
  },
  orc2: {
    folder: 'sprites/2_ORK',
    prefix: 'ORK_02',
    anims: {
      walk:   { name: 'WALK',  frames: 10, speed: 8 },
      run:    { name: 'RUN',   frames: 10, speed: 10 },
      attack: { name: 'ATTAK', frames: 10, speed: 12 },
      hurt:   { name: 'HURT',  frames: 10, speed: 12 },
      die:    { name: 'DIE',   frames: 10, speed: 8 },
    },
    hp: 3,
    sightRange: 1.5,
    hearRange: 0.4,
    aggroSightRange: 3.0,
    width: 0.12,
    height: 0.18,
  },
  orc3: {
    folder: 'sprites/3_ORK',
    prefix: 'ORK_03',
    anims: {
      walk:   { name: 'WALK',  frames: 10, speed: 8 },
      run:    { name: 'RUN',   frames: 10, speed: 10 },
      attack: { name: 'ATTAK', frames: 10, speed: 12 },
      hurt:   { name: 'HURT',  frames: 10, speed: 12 },
      die:    { name: 'DIE',   frames: 10, speed: 8 },
    },
    hp: 3,
    sightRange: 2.0,
    hearRange: 0.6,
    aggroSightRange: 4.0,
    width: 0.12,
    height: 0.18,
  },
  troll1: {
    folder: 'sprites/1_TROLL',
    prefix: 'Troll_01_1',
    anims: {
      walk:   { name: 'WALK',   frames: 10, speed: 6 },
      run:    { name: 'RUN',    frames: 10, speed: 8 },
      attack: { name: 'ATTACK', frames: 10, speed: 12 },
      hurt:   { name: 'HURT',   frames: 10, speed: 10 },
      die:    { name: 'DIE',    frames: 10, speed: 8 },
    },
    hp: 5,
    sightRange: 1.2,
    hearRange: 0.7,
    aggroSightRange: 2.5,
    width: 0.18,
    height: 0.26,
  },
  troll2: {
    folder: 'sprites/2_TROLL',
    prefix: 'Troll_02_1',
    anims: {
      walk:   { name: 'WALK',   frames: 10, speed: 6 },
      run:    { name: 'RUN',    frames: 10, speed: 8 },
      attack: { name: 'ATTACK', frames: 10, speed: 12 },
      hurt:   { name: 'HURT',   frames: 10, speed: 10 },
      die:    { name: 'DIE',    frames: 10, speed: 8 },
    },
    hp: 5,
    sightRange: 1.0,
    hearRange: 0.8,
    aggroSightRange: 2.0,
    width: 0.18,
    height: 0.26,
  },
  troll3: {
    folder: 'sprites/3_TROLL',
    prefix: 'Troll_03_1',
    anims: {
      walk:   { name: 'WALK',   frames: 10, speed: 6 },
      run:    { name: 'RUN',    frames: 10, speed: 8 },
      attack: { name: 'ATTACK', frames: 10, speed: 12 },
      hurt:   { name: 'HURT',   frames: 10, speed: 10 },
      die:    { name: 'DIE',    frames: 10, speed: 8 },
    },
    hp: 5,
    sightRange: 1.4,
    hearRange: 0.9,
    aggroSightRange: 3.0,
    width: 0.18,
    height: 0.26,
  },
  dragon: {
    folder: 'sprites/Dragon_3',
    prefix: '',    // no prefix — files are AnimName_000.png
    anims: {
      walk:     { name: 'Walk',      frames: 12, speed: 8 },
      run:      { name: 'Flight',    frames: 12, speed: 10 },
      attack:   { name: 'Attack_1',  frames: 4,  speed: 6 },   // close range bite/claw
      attack2:  { name: 'Attack_2',  frames: 10, speed: 10 },   // fire breath (ranged)
      hurt:     { name: 'Hurt',      frames: 4,  speed: 8 },
      die:      { name: 'Dead',      frames: 3,  speed: 4 },
      idle:     { name: 'Idle',      frames: 7,  speed: 6 },
      rise:     { name: 'Rise',      frames: 7,  speed: 8 },
      special:  { name: 'Special',   frames: 13, speed: 8 },
      landing:  { name: 'Landing',   frames: 5,  speed: 8 },
    },
    hp: 15,
    sightRange: 1.5,
    hearRange: 0.6,
    aggroSightRange: 5.0,
    width: 1.0,
    height: 0.5,
    drawHeight: 504,  // bigger than normal enemies
    isDragon: true,
    closeAttackRange: 0.35,  // [m] range for Attack_1 (melee)
    fireAttackRange: 0.5,    // [m] range for Attack_2 (fire breath)
  },
};

// Loaded frame images: { [typeName]: { [animName]: Image[] } }
const LOADED = {};
// Content bottom as fraction of image height per frame: { [typeName]: { [animName]: number[] } }
const CONTENT_BOTTOM = {};
// Reference ground line (from first walk frame) per type
const GROUND_LINE = {};

// Offscreen canvas for measuring content bounds
const _measureCanvas = document.createElement('canvas');
const _measureCtx = _measureCanvas.getContext('2d', { willReadFrequently: true });

// Offscreen canvas for red tint effect
const _tintCanvas = document.createElement('canvas');
const _tintCtx = _tintCanvas.getContext('2d');

function measureContentBottom(img) {
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  _measureCanvas.width = w;
  _measureCanvas.height = h;
  _measureCtx.clearRect(0, 0, w, h);
  _measureCtx.drawImage(img, 0, 0);
  const data = _measureCtx.getImageData(0, 0, w, h).data;
  // Scan from bottom up to find last non-transparent row
  for (let row = h - 1; row >= 0; row--) {
    for (let col = 0; col < w; col++) {
      if (data[(row * w + col) * 4 + 3] > 10) {
        return (row + 1) / h;
      }
    }
  }
  return 1.0;
}

function loadAllSprites() {
  for (const [typeName, cfg] of Object.entries(ENEMY_TYPES)) {
    LOADED[typeName] = {};
    CONTENT_BOTTOM[typeName] = {};
    for (const [animKey, anim] of Object.entries(cfg.anims)) {
      const frames = [];
      const bottoms = [];
      CONTENT_BOTTOM[typeName][animKey] = bottoms;
      for (let i = 0; i < anim.frames; i++) {
        const idx = String(i).padStart(3, '0');
        const img = new Image();
        img.src = cfg.prefix
          ? `./${cfg.folder}/${cfg.prefix}_${anim.name}_${idx}.png`
          : `./${cfg.folder}/${anim.name}_${idx}.png`;
        const frameIdx = i;
        img.onload = () => {
          bottoms[frameIdx] = measureContentBottom(img);
          // Set ground line from first walk frame
          if (animKey === 'walk' && frameIdx === 0 && !GROUND_LINE[typeName]) {
            GROUND_LINE[typeName] = bottoms[0];
          }
        };
        frames.push(img);
      }
      LOADED[typeName][animKey] = frames;
    }
  }
}

loadAllSprites();

// =====================================================================================================================
// Enemy class
// =====================================================================================================================

export class Enemy {
  /**
   * @param {number} x - World x position [m]
   * @param {number} y - Platform height [m] (0 = ground)
   * @param {number} patrolLeft - Left patrol bound [m]
   * @param {number} patrolRight - Right patrol bound [m]
   * @param {number} speed - Walk speed [m/s]
   * @param {string} type - Enemy type key (orc1, orc2, orc3, troll1, troll2, troll3)
   */
  constructor(x, y, patrolLeft, patrolRight, speed = 0.3, type = 'orc1') {
    this.x = x;
    this.y = y;
    this.patrolLeft = patrolLeft;
    this.patrolRight = patrolRight;
    this.speed = speed;
    this.type = type;
    const cfg = ENEMY_TYPES[type] || ENEMY_TYPES.orc1;
    this.direction = cfg.isDragon ? -1 : 1; // dragon starts facing left
    this.animTime = Math.random() * 10;

    this.hp = cfg.hp || 1;
    this.maxHp = this.hp;
    this.width = cfg.width;
    this.height = cfg.height;

    this.alive = true;
    this.state = cfg.isDragon ? 'idle' : 'patrol';    // dragon starts idle
    this.aggro = false;       // true once enemy has spotted BILBO
    this.aggroTime = 0;       // time since aggro triggered (for "!" display)
    this.attackTime = 0;      // time into current attack animation
    this.hurtFlash = false;   // true while playing hurt reaction (non-lethal hit)
    this.hurtFlashTime = 0;   // time into hurt flash animation
    this.dying = false;       // true while playing death sequence
    this.deathPhase = 'hurt'; // 'hurt' then 'die'
    this.deathTime = 0;       // time into current death phase
    this.removed = false;     // true when ready to be removed

    // Vertical physics (platform climbing)
    this.verticalPos = y;          // current vertical position [m]
    this.verticalVel = 0;          // vertical velocity [m/s]
    this.airborne = false;         // true when in the air
    this.jumpCooldown = 0;         // time until next jump allowed [s]
    this.groundHeight = y;         // height of current ground/platform

    // Pathfinding state
    this.path = [];                // array of platform indices (-1 = ground)
    this.pathTimer = 99;           // force immediate computation
    this._jumpTargetX = null;      // locked horizontal target during a path jump
    this._jumpSpeed = null;        // computed speed to guarantee reaching target

    // Dragon-specific state
    this.dragonPhase = 'ground';  // 'ground', 'rising', 'flying', 'special', 'landing'
    this.dragonTimer = 0;         // time in current dragon phase
    this.baseY = y;               // ground level to return to
    this.fireBreath = false;      // true while breathing fire (game.js reads this)
    this.fireBreathX = 0;         // target X for fire
    this.dragonLandY = y;         // target platform Y for landing
  }

  update(dt, playerX, playerInvisible = false, playerY = 0, platforms = []) {
    if (this.removed) return;

    if (this.dying) {
      this.deathTime += dt;
      const cfg = ENEMY_TYPES[this.type] || ENEMY_TYPES.orc1;
      const phaseAnim = cfg.anims[this.deathPhase];
      const phaseDuration = phaseAnim.frames / phaseAnim.speed;
      if (this.deathPhase === 'hurt' && this.deathTime >= phaseDuration) {
        this.deathPhase = 'die';
        this.deathTime = 0;
      } else if (this.deathPhase === 'die' && this.deathTime >= phaseDuration + 3.0) {
        this.removed = true;
      }
      // Still apply gravity to dying enemies
      this._applyVerticalPhysics(dt, platforms);
      return;
    }

    if (!this.alive) return;

    // Hurt flash (non-lethal hit reaction)
    if (this.hurtFlash) {
      this.hurtFlashTime += dt;
      const cfg = ENEMY_TYPES[this.type] || ENEMY_TYPES.orc1;
      const hurtDuration = cfg.anims.hurt.frames / cfg.anims.hurt.speed;
      if (this.hurtFlashTime >= hurtDuration) {
        this.hurtFlash = false;
        this.hurtFlashTime = 0;
      }
      this._applyVerticalPhysics(dt, platforms);
      return; // locked in hurt animation
    }

    this.animTime += dt;
    if (this.aggro) this.aggroTime += dt;
    if (this.jumpCooldown > 0) this.jumpCooldown -= dt;

    const dist = Math.abs(playerX - this.x);
    const dirToPlayer = Math.sign(playerX - this.x);
    const cfg = ENEMY_TYPES[this.type] || ENEMY_TYPES.orc1;
    const sightRange = this.aggro ? cfg.aggroSightRange : cfg.sightRange;

    // 3D distance for sight check (account for vertical distance)
    const dy = playerY - this.verticalPos;
    const dist3D = Math.sqrt(dist * dist + dy * dy);

    // ---- Dragon AI ----
    if (cfg.isDragon) {
      this.fireBreath = false;
      this.dragonTimer += dt;

      const DRAGON_FLY_SPEED = this.speed * 8;   // fast flight
      const DRAGON_WALK_SPEED = this.speed * AGGRO_SPEED_MULT;
      const FLY_THRESHOLD = 1.2;  // [m] fly if further, walk if closer

      // Detect BILBO
      const canSee = this.aggro || this.direction === dirToPlayer || dirToPlayer === 0 || dist <= cfg.hearRange;
      if (!playerInvisible && dist3D <= sightRange && canSee) {
        if (!this.aggro) {
          this.aggro = true;
          this.aggroTime = 0;
          // Start rise on first aggro
          if (this.dragonPhase === 'ground' || this.dragonPhase === 'idle') {
            this.dragonPhase = 'rising';
            this.dragonTimer = 0;
            this.state = 'rising';
            this.direction = dirToPlayer || this.direction;
          }
        }
      }

      // Locked in attack animation
      if (this.dragonPhase === 'attack1' || this.dragonPhase === 'attack2') {
        const atkAnim = this.dragonPhase === 'attack1' ? cfg.anims.attack : cfg.anims.attack2;
        const atkDur = atkAnim.frames / atkAnim.speed;
        if (this.dragonTimer >= atkDur) {
          this.dragonPhase = 'ground';
          this.dragonTimer = 0;
          this.direction = dirToPlayer || this.direction;
        }
        return;
      }

      // Rise animation → then always fly (never skip to ground)
      if (this.dragonPhase === 'rising') {
        const riseDur = cfg.anims.rise.frames / cfg.anims.rise.speed;
        if (this.dragonTimer >= riseDur) {
          if (dist > 0.3) this.direction = dirToPlayer || this.direction;
          this.dragonPhase = 'flying';
          this.dragonTimer = 0;
        }
        return;
      }

      // Flying toward BILBO
      if (this.dragonPhase === 'flying') {
        this.state = 'flying';
        // Direction hysteresis: only flip when clearly past the player
        if (dist > 0.3) {
          this.direction = dirToPlayer || this.direction;
        }
        this.x += this.direction * DRAGON_FLY_SPEED * dt;
        // Follow player vertically
        const targetY = Math.max(this.baseY, playerY);
        const dyFly = targetY - this.verticalPos;
        const DRAGON_VERT_SPEED = DRAGON_FLY_SPEED * 0.6;
        if (Math.abs(dyFly) > 0.05) {
          this.verticalPos += Math.sign(dyFly) * DRAGON_VERT_SPEED * dt;
          this.y = this.verticalPos;
        }
        // Only land when player is on the ground floor and dragon is close
        if (dist <= FLY_THRESHOLD && playerY < 0.15) {
          this.dragonLandY = 0;
          this.dragonPhase = 'landing';
          this.dragonTimer = 0;
        }
        return;
      }

      // Landing animation → dive down to ground
      if (this.dragonPhase === 'landing') {
        this.state = 'landing';
        const dyLand = this.dragonLandY - this.verticalPos;
        const landDur = cfg.anims.landing.frames / cfg.anims.landing.speed;
        const timeLeft = Math.max(0.1, landDur - this.dragonTimer);
        const LAND_SPEED = Math.abs(dyLand) / timeLeft;
        if (Math.abs(dyLand) > 0.02) {
          this.verticalPos += Math.sign(dyLand) * LAND_SPEED * dt;
          this.y = this.verticalPos;
        }
        if (this.dragonTimer >= landDur) {
          this.verticalPos = this.dragonLandY;
          this.y = this.dragonLandY;
          this.groundHeight = this.dragonLandY;
          this.dragonPhase = 'ground';
          this.dragonTimer = 0;
        }
        return;
      }

      // Ground behavior — snap to ground
      this.verticalPos = 0;
      this.y = 0;

      if (this.aggro && !playerInvisible) {
        if (dist > 0.3) this.direction = dirToPlayer || this.direction;

        // Player went up on a platform → rise and fly after them
        if (playerY >= 0.15) {
          this.dragonPhase = 'rising';
          this.dragonTimer = 0;
          this.state = 'rising';
          return;
        }
        // Close range → Attack_1 (melee)
        if (dist <= cfg.closeAttackRange) {
          this.dragonPhase = 'attack1';
          this.dragonTimer = 0;
          this.state = 'attack';
          return;
        }
        // Mid range → Attack_2 (fire breath)
        if (dist <= cfg.fireAttackRange) {
          this.dragonPhase = 'attack2';
          this.dragonTimer = 0;
          this.state = 'attack2';
          return;
        }
        // Far away → rise and fly
        if (dist > FLY_THRESHOLD) {
          this.dragonPhase = 'rising';
          this.dragonTimer = 0;
          this.state = 'rising';
          return;
        }
        // Walk toward BILBO
        this.state = 'chase';
        this.dragonPhase = 'ground';
        this.x += this.direction * DRAGON_WALK_SPEED * dt;
      } else {
        // Not aggro: idle (standing still, facing left)
        this.state = 'idle';
        this.dragonPhase = 'idle';
      }
      return;
    }

    // ---- Standard enemy AI ----

    // Apply vertical physics (gravity, landing)
    this._applyVerticalPhysics(dt, platforms);

    // If currently attacking, finish the full animation before changing state
    if (this.state === 'attack') {
      this.attackTime += dt;
      const atkDuration = cfg.anims.attack.frames / cfg.anims.attack.speed;
      if (this.attackTime < atkDuration) {
        return; // locked in attack animation
      }
      // Attack finished — face player direction and decide next state
      this.attackTime = 0;
      this.direction = dirToPlayer || this.direction;
    }

    // When player is invisible (One Ring), enemies lose track entirely
    if (playerInvisible) {
      // Drop aggro over time
      if (this.aggro) {
        this.state = 'aggro_patrol';
        this._moveHorizontal(dt, this.speed * AGGRO_SPEED_MULT * 0.5, platforms);
        if (this.x >= this.patrolRight) { this.x = this.patrolRight; this.direction = -1; }
        else if (this.x <= this.patrolLeft) { this.x = this.patrolLeft; this.direction = 1; }
        // Lose aggro after 3s of invisibility
        if (this.aggroTime > 3.0) {
          this.aggro = false;
          this.aggroTime = 0;
        }
      } else {
        this.state = 'patrol';
        this._moveHorizontal(dt, this.speed, platforms);
        if (this.x >= this.patrolRight) { this.x = this.patrolRight; this.direction = -1; }
        else if (this.x <= this.patrolLeft) { this.x = this.patrolLeft; this.direction = 1; }
      }
      return;
    }

    // Spot BILBO: use 3D distance and also consider vertical line of sight
    const canSee = this.aggro || this.direction === dirToPlayer || dirToPlayer === 0 || dist <= cfg.hearRange;
    const sameLevel = Math.abs(dy) < this.height + 0.12;

    if (dist <= ATTACK_RANGE && sameLevel && canSee) {
      // Attack if at roughly the same height and close
      if (!this.aggro) { this.aggro = true; this.aggroTime = 0; }
      if (this.state !== 'attack') {
        this.state = 'attack';
        this.attackTime = 0;
      }
      this.direction = dirToPlayer || this.direction;
    } else if (dist3D <= sightRange && canSee) {
      // Chase — with pathfinding across platforms
      if (!this.aggro) { this.aggro = true; this.aggroTime = 0; }
      this.state = 'chase';

      const chaseSpeed = this.speed * AGGRO_SPEED_MULT;

      if (this.airborne) {
        // While airborne, just follow existing path — never recompute mid-jump
        this._followPath(dt, platforms, chaseSpeed, playerX);
      } else {
        const myPlatIdx = this._getPlatformIndex(platforms);
        const playerPlatIdx = this._getPlatformIndex(platforms, playerX, playerY);

        if (myPlatIdx === playerPlatIdx) {
          // Same platform — direct chase, clear path
          this.path = [];
          this._steerToward(playerX);
          this._moveHorizontal(dt, chaseSpeed, platforms, true);
        } else {
          // Different platform — use BFS pathfinding
          this.pathTimer += dt;
          if (this.pathTimer >= ENEMY_PATH_RECOMPUTE) {
            this.pathTimer = 0;
            this.path = this._computePath(platforms, myPlatIdx, playerPlatIdx);
          }
          this._followPath(dt, platforms, chaseSpeed, playerX);
        }
      }
    } else if (this.aggro) {
      // Aggro patrol — continue following path if we have one, else patrol
      this.state = 'aggro_patrol';
      if (this.path.length > 0) {
        this._followPath(dt, platforms, this.speed * AGGRO_SPEED_MULT);
      } else {
        this._moveHorizontal(dt, this.speed * AGGRO_SPEED_MULT, platforms, true);
        if (this.x >= this.patrolRight) { this.x = this.patrolRight; this.direction = -1; }
        else if (this.x <= this.patrolLeft) { this.x = this.patrolLeft; this.direction = 1; }
      }
    } else {
      this.state = 'patrol';
      this.path = [];
      this._moveHorizontal(dt, this.speed, platforms, false);
      if (this.x >= this.patrolRight) { this.x = this.patrolRight; this.direction = -1; }
      else if (this.x <= this.patrolLeft) { this.x = this.patrolLeft; this.direction = 1; }
    }
  }

  // =========================================================================
  // Vertical physics
  // =========================================================================

  _applyVerticalPhysics(dt, platforms) {
    if (this.airborne) {
      this.verticalVel -= ENEMY_GRAVITY * dt;
      this.verticalPos += this.verticalVel * dt;

      // Check landing on platforms
      const ground = this._findGround(platforms);
      if (this.verticalPos <= ground && this.verticalVel <= 0) {
        this.verticalPos = ground;
        this.verticalVel = 0;
        this.airborne = false;
        this.groundHeight = ground;
        this.y = ground;
        this._onLand();
      }
      // Fell below world floor
      if (this.verticalPos < 0 && this.verticalVel <= 0) {
        this.verticalPos = 0;
        this.verticalVel = 0;
        this.airborne = false;
        this.groundHeight = 0;
        this.y = 0;
        this._onLand();
      }
    } else {
      // Check if we walked off a platform edge
      const ground = this._findGround(platforms);
      if (ground < this.verticalPos - 0.02) {
        this.airborne = true;
        this.verticalVel = 0;
      } else {
        this.verticalPos = ground;
        this.groundHeight = ground;
        this.y = ground;
      }
    }
  }

  _findGround(platforms) {
    let bestHeight = 0;
    for (const p of platforms) {
      if (this.x >= p.x && this.x <= p.x + p.w) {
        if (p.y > bestHeight && p.y <= this.verticalPos + 0.02) {
          bestHeight = p.y;
        }
      }
    }
    return bestHeight;
  }

  _jump() {
    if (this.airborne || this.jumpCooldown > 0) return;
    this.airborne = true;
    this.verticalVel = ENEMY_JUMP_VEL;
    this.jumpCooldown = ENEMY_JUMP_COOLDOWN;
  }

  _onLand() {
    // Clear jump trajectory lock
    this._jumpTargetX = null;
    this._jumpSpeed = null;
    // Force immediate path recompute on next grounded frame
    this.pathTimer = 99;
  }

  // Direction setter with hysteresis to prevent flickering.
  // Only flips direction when dx exceeds a threshold; below that, keeps current direction.
  _steerToward(targetX, threshold = 0.06) {
    const dx = targetX - this.x;
    if (Math.abs(dx) < threshold) return;  // too close — keep current direction
    const newDir = Math.sign(dx);
    if (newDir !== 0) this.direction = newDir;
  }

  // =========================================================================
  // Horizontal movement with edge awareness
  // =========================================================================

  _moveHorizontal(dt, speed, platforms, allowFall = false) {
    const nextX = this.x + this.direction * speed * dt;

    // When not allowed to fall and on elevated platform, don't walk off edges
    if (!allowFall && !this.airborne && this.verticalPos > 0.05) {
      let hasGround = false;
      for (const p of platforms) {
        if (nextX >= p.x && nextX <= p.x + p.w && Math.abs(p.y - this.verticalPos) < 0.05) {
          hasGround = true;
          break;
        }
      }
      if (!hasGround) {
        this.direction = -this.direction;
        return;
      }
    }

    this.x = nextX;
  }

  // =========================================================================
  // BFS Pathfinding across platforms
  // =========================================================================

  _getPlatformIndex(platforms, x = this.x, y = this.verticalPos) {
    let bestIdx = -1;
    let bestY = -1;
    for (let i = 0; i < platforms.length; i++) {
      const p = platforms[i];
      if (x >= p.x && x <= p.x + p.w && Math.abs(y - p.y) < 0.08 && p.y > bestY) {
        bestIdx = i;
        bestY = p.y;
      }
    }
    // On ground floor
    if (bestIdx === -1 && y < 0.08) return -1;
    // Airborne or falling — find closest platform below
    if (bestIdx === -1) {
      for (let i = 0; i < platforms.length; i++) {
        const p = platforms[i];
        if (x >= p.x && x <= p.x + p.w && p.y <= y && p.y > bestY) {
          bestIdx = i;
          bestY = p.y;
        }
      }
    }
    return bestIdx;
  }

  // Horizontal gap between two platform x-ranges (0 if overlapping)
  static _platGap(a, b) {
    return Math.max(0, Math.max(a.x, b.x) - Math.min(a.x + a.w, b.x + b.w));
  }

  _computePath(platforms, fromIdx, toIdx) {
    if (fromIdx === toIdx) return [];
    const n = platforms.length;

    // Build adjacency list. Nodes: -1 (ground), 0..n-1 (platforms)
    const adj = new Map();
    adj.set(-1, []);
    for (let i = 0; i < n; i++) adj.set(i, []);

    // Ground ↔ platform connections
    for (let i = 0; i < n; i++) {
      const p = platforms[i];
      // Jump from ground to platform (must be within jump height)
      if (p.y <= ENEMY_MAX_JUMP_H * 0.92) {
        adj.get(-1).push(i);
      }
      // Fall from platform to ground (always possible)
      adj.get(i).push(-1);
    }

    // Platform ↔ platform connections
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        const a = platforms[i];
        const b = platforms[j];
        const hDiff = b.y - a.y;
        const gap = Enemy._platGap(a, b);

        if (hDiff > 0 && hDiff <= ENEMY_MAX_JUMP_H * 0.92 && gap <= ENEMY_MAX_HORIZ_REACH) {
          // Jump up from i to j
          adj.get(i).push(j);
        } else if (hDiff <= 0 && gap <= ENEMY_MAX_HORIZ_REACH * 1.3) {
          // Fall down or walk across from i to j (more horizontal reach when falling)
          adj.get(i).push(j);
        }
      }
    }

    // BFS
    const visited = new Set();
    const parent = new Map();
    const queue = [fromIdx];
    visited.add(fromIdx);

    while (queue.length > 0) {
      const node = queue.shift();
      if (node === toIdx) break;
      for (const next of (adj.get(node) || [])) {
        if (!visited.has(next)) {
          visited.add(next);
          parent.set(next, node);
          queue.push(next);
        }
      }
    }

    if (!visited.has(toIdx)) return []; // no path

    // Reconstruct
    const path = [];
    let cur = toIdx;
    while (cur !== fromIdx) {
      path.unshift(cur);
      cur = parent.get(cur);
    }
    return path;
  }

  // =========================================================================
  // Path following
  // =========================================================================

  _followPath(dt, platforms, speed, playerX = null) {
    if (this.path.length === 0) {
      // No path — chase directly toward player if we know where they are
      if (playerX !== null) {
        this._steerToward(playerX);
        this._moveHorizontal(dt, speed, platforms, true);
      }
      return;
    }

    // --- Airborne: follow locked trajectory ---
    if (this.airborne) {
      if (this._jumpTargetX !== null) {
        // Locked trajectory — steer toward computed target at computed speed
        this._steerToward(this._jumpTargetX, 0.02);
        this.x += this.direction * (this._jumpSpeed || speed) * dt;
      } else {
        // Airborne without a locked target (e.g. walked off edge) — steer toward next path platform
        const nextIdx = this.path[0];
        if (nextIdx === -1) {
          if (playerX !== null) this._steerToward(playerX);
        } else {
          const np = platforms[nextIdx];
          this._steerToward(np.x + np.w / 2);
        }
        this.x += this.direction * speed * dt;
      }
      return;
    }

    // --- Grounded: navigate to next platform in path ---
    const myPlatIdx = this._getPlatformIndex(platforms);
    if (myPlatIdx === this.path[0]) {
      this.path.shift();
      if (this.path.length === 0) return;
    }

    const nextIdx = this.path[0];
    const nextPlat = nextIdx === -1 ? null : platforms[nextIdx];
    const nextY = nextPlat ? nextPlat.y : 0;

    if (nextY > this.verticalPos + 0.05) {
      // --- JUMP UP to next platform ---
      const myPlat = myPlatIdx >= 0 ? platforms[myPlatIdx] : null;
      const targetCenterX = nextPlat.x + nextPlat.w / 2;
      const jumpX = this._getJumpX(myPlat, nextPlat);
      const dxToJump = jumpX - this.x;

      if (Math.abs(dxToJump) < 0.10) {
        // At launch position — compute trajectory and jump
        const dh = nextY - this.verticalPos;
        const disc = ENEMY_JUMP_VEL * ENEMY_JUMP_VEL - 2 * ENEMY_GRAVITY * dh;
        if (disc > 0) {
          const tLand = (ENEMY_JUMP_VEL + Math.sqrt(disc)) / ENEMY_GRAVITY;
          const hDist = Math.abs(targetCenterX - this.x);
          this._jumpSpeed = Math.max(speed, (hDist / tLand) * 1.2);
        } else {
          this._jumpSpeed = speed;
        }
        this._jumpTargetX = targetCenterX;
        this._steerToward(targetCenterX, 0.02);
        this._jump();
      } else {
        // Walk to launch position
        this._steerToward(jumpX, 0.04);
        this.x += this.direction * speed * dt;
      }
    } else {
      // --- FALL DOWN or walk across to next platform ---
      let targetX;
      if (nextPlat) {
        targetX = nextPlat.x + nextPlat.w / 2;
      } else if (playerX !== null) {
        targetX = playerX;
      } else {
        targetX = this.x + this.direction * 0.5;
      }
      this._steerToward(targetX);
      // Lock target for air steering when falling off edge
      this._jumpTargetX = targetX;
      this._jumpSpeed = speed;
      this.x += this.direction * speed * dt;
    }
  }

  _getJumpX(curPlat, targetPlat) {
    const targetCenter = targetPlat.x + targetPlat.w / 2;
    if (curPlat) {
      // Jump from the edge of current platform closest to target (no margin — use the full edge)
      return Math.max(curPlat.x, Math.min(curPlat.x + curPlat.w, targetCenter));
    }
    // On ground — go directly under target
    return targetCenter;
  }

  checkCollision(playerX, playerY, playerVelY, wheelRadius) {
    if (!this.alive) return null;

    const cfg = ENEMY_TYPES[this.type] || ENEMY_TYPES.orc1;
    const dx = Math.abs(playerX - this.x);
    const enemyY = this.verticalPos !== undefined ? this.verticalPos : this.y;
    const dy = playerY - enemyY;

    // Dragon flying: bump collision to knock BILBO off platforms
    if (cfg.isDragon && this.state === 'flying') {
      const bumpRange = cfg.width * 0.4;
      if (dx < bumpRange + wheelRadius && Math.abs(dy) < this.height + wheelRadius * 0.5) {
        return 'hit';
      }
      return null;
    }

    // Only damage during attack animations
    if (this.state !== 'attack' && this.state !== 'attack2') return null;

    // Dragon: attack1 uses closeAttackRange, attack2 uses fireAttackRange (sprite shows fire)
    let range = ATTACK_RANGE;
    if (cfg.isDragon && this.state === 'attack') range = cfg.closeAttackRange;
    else if (cfg.isDragon && this.state === 'attack2') range = cfg.fireAttackRange;
    if (dx > range + wheelRadius) return null;

    if (dy >= 0 && dy < this.height + wheelRadius * 0.5) {
      return 'hit';
    }

    return null;
  }

  damage(amount = 1) {
    if (!this.alive) return;
    this.hp -= amount;
    // Immediately aggro on any hit
    if (!this.aggro) {
      this.aggro = true;
      this.aggroTime = 0;
    }
    if (this.hp <= 0) {
      this.kill();
    } else {
      // Non-lethal hit — play hurt flash
      this.hurtFlash = true;
      this.hurtFlashTime = 0;
    }
  }

  kill() {
    this.alive = false;
    this.dying = true;
    this.deathPhase = 'hurt';
    this.deathTime = 0;
  }
}

// =====================================================================================================================
// Rendering
// =====================================================================================================================

export function drawEnemies(ctx, enemies, cameraX, groundY) {
  for (const enemy of enemies) {
    if (enemy.removed) continue;

    const cfg = ENEMY_TYPES[enemy.type] || ENEMY_TYPES.orc1;
    const frames = LOADED[enemy.type] || LOADED.orc1;

    const screenX = enemy.x * SCALE - cameraX * SCALE;
    const screenY = groundY - (enemy.verticalPos !== undefined ? enemy.verticalPos : enemy.y) * SCALE;

    const cullMargin = (cfg.drawHeight || DRAW_HEIGHT) * 1.5;
    if (screenX < -cullMargin || screenX > ctx.canvas.width + cullMargin) continue;

    let animKey, animTime;
    if (enemy.dying) {
      animKey = enemy.deathPhase;
      animTime = enemy.deathTime;
    } else if (enemy.hurtFlash) {
      animKey = 'hurt';
      animTime = enemy.hurtFlashTime;
    } else if (enemy.state === 'attack') {
      animKey = 'attack';
      animTime = cfg.isDragon ? enemy.dragonTimer : enemy.attackTime;
    } else if (enemy.state === 'attack2') {
      animKey = 'attack2';
      animTime = enemy.dragonTimer;
    } else if (enemy.state === 'flying') {
      animKey = 'run';  // Flight animation
      animTime = enemy.animTime;
    } else if (enemy.state === 'landing') {
      animKey = 'landing';
      animTime = enemy.dragonTimer;
    } else if (enemy.state === 'chase' || enemy.state === 'aggro_patrol') {
      animKey = cfg.isDragon ? 'walk' : 'run';
      animTime = enemy.animTime;
    } else if (enemy.state === 'rising') {
      animKey = 'rise';
      animTime = enemy.dragonTimer;
    } else if (enemy.state === 'idle') {
      animKey = 'idle';
      animTime = enemy.animTime;
    } else {
      animKey = cfg.anims.idle ? 'idle' : 'walk';
      animTime = enemy.animTime;
    }

    const anim = cfg.anims[animKey];
    const animFrames = frames[animKey];
    if (!animFrames || animFrames.length === 0) continue;

    let frameIndex;
    if (enemy.dying || enemy.state === 'attack' || enemy.state === 'attack2' || enemy.state === 'rising' || enemy.state === 'landing') {
      // Clamp to last frame (don't loop)
      frameIndex = Math.min(Math.floor(animTime * anim.speed), anim.frames - 1);
    } else {
      frameIndex = Math.floor(animTime * anim.speed) % anim.frames;
    }

    const img = animFrames[frameIndex];
    if (!img || !img.complete || img.naturalWidth === 0) continue;

    // Compute draw size preserving aspect ratio at type-specific or default height
    const aspect = img.naturalWidth / img.naturalHeight;
    const drawH = cfg.drawHeight || DRAW_HEIGHT;
    const drawW = drawH * aspect;

    ctx.save();
    ctx.translate(screenX, screenY);

    // Fade out during the last 1s of the die phase linger
    if (enemy.dying && enemy.deathPhase === 'die') {
      const dieDuration = cfg.anims.die.frames / cfg.anims.die.speed;
      const totalDie = dieDuration + 3.0;
      const remaining = totalDie - enemy.deathTime;
      if (remaining < 1.0) {
        ctx.globalAlpha = Math.max(0, remaining);
      }
    }

    // Flip for direction (sprites face right by default)
    if (enemy.direction === -1) {
      ctx.scale(-1, 1);
    }

    // Align content bottom of each frame to the ground line
    // groundLine is the content bottom fraction of the walk frame (e.g. 0.95 means feet at 95% of image)
    // We need to shift the sprite down so that fraction lands exactly at screenY (y=0 after translate)
    const groundLine = GROUND_LINE[enemy.type] || 1.0;
    const bottoms = CONTENT_BOTTOM[enemy.type] && CONTENT_BOTTOM[enemy.type][animKey];
    const contentBottom = (bottoms && bottoms[frameIndex]) || groundLine;
    // drawH * contentBottom pixels from top is where this frame's feet are
    // We want that point at y=0 (ground), so top of image goes at -(contentBottom * drawH)
    // Then adjust for walk ground line alignment across animations
    const baseY = -(groundLine * drawH);
    const shiftY = (groundLine - contentBottom) * drawH;
    // Pulsing red tint when aggro'd
    if (enemy.aggro && !enemy.dying) {
      const pulse = 0.1 + 0.1 * Math.sin(enemy.aggroTime * 6);
      _tintCanvas.width = img.naturalWidth;
      _tintCanvas.height = img.naturalHeight;
      _tintCtx.clearRect(0, 0, _tintCanvas.width, _tintCanvas.height);
      _tintCtx.drawImage(img, 0, 0);
      _tintCtx.globalCompositeOperation = 'source-atop';
      _tintCtx.fillStyle = `rgba(255, 0, 0, ${pulse})`;
      _tintCtx.fillRect(0, 0, _tintCanvas.width, _tintCanvas.height);
      _tintCtx.globalCompositeOperation = 'source-over';
      ctx.drawImage(_tintCanvas, -drawW / 2, baseY + shiftY, drawW, drawH);
    } else {
      ctx.drawImage(img, -drawW / 2, baseY + shiftY, drawW, drawH);
    }

    ctx.restore();

    // Aggro "!" indicator above head
    if (enemy.aggro && !enemy.dying && enemy.aggroTime < 1.5) {
      ctx.save();
      ctx.translate(screenX, screenY);
      const bounce = Math.sin(enemy.aggroTime * 12) * 3;
      const alpha = enemy.aggroTime < 1.0 ? 1.0 : Math.max(0, 1 - (enemy.aggroTime - 1.0) / 0.5);
      ctx.globalAlpha = alpha;
      ctx.font = 'bold 28px "Courier New", monospace';
      ctx.fillStyle = '#ff3030';
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 3;
      ctx.textAlign = 'center';
      const yPos = -(cfg.drawHeight || DRAW_HEIGHT) * 0.52 + bounce;
      ctx.strokeText('!', 0, yPos);
      ctx.fillText('!', 0, yPos);
      ctx.restore();
    }

    // HP hearts above aggro'd enemies
    if (enemy.aggro && !enemy.dying && enemy.alive) {
      ctx.save();
      ctx.translate(screenX, screenY);
      const heartY = -(cfg.drawHeight || DRAW_HEIGHT) * 0.58;
      const heartSize = 10;
      const heartSpacing = 14;
      const totalW = enemy.maxHp * heartSpacing;
      const startX = -totalW / 2 + heartSpacing / 2;
      ctx.font = `${heartSize}px sans-serif`;
      ctx.textAlign = 'center';
      for (let i = 0; i < enemy.maxHp; i++) {
        const hx = startX + i * heartSpacing;
        if (i < enemy.hp) {
          ctx.fillStyle = '#ff3030';
        } else {
          ctx.fillStyle = 'rgba(60, 60, 60, 0.6)';
        }
        ctx.fillText('♥', hx, heartY);
      }
      ctx.restore();
    }
  }
}
