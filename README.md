# 🏝️ Island Escape

A 3D survival game built with **Python, PyOpenGL and GLUT**, and nothing else. You're stranded on a mysterious island with five missing friends, a hungry predator, and a radio that claims to be your future self. Find everyone before the rescue window closes.

## ✨ Highlights

- **Pure fixed-function OpenGL.** No shaders, VBOs/VAOs, textures or external model files. Every object is built from GLUT/GLU primitives and `glBegin`/`glEnd` shapes with flat colors.
- **No timers.** All timing runs off wall-clock delta time inside `idle()`.
- **Day/night fantasy transformation.** Press a key and the island morphs: purple trees, glowing rocks, stars, a moon, fireflies, and a hidden stepping-stone bridge that leads to a secret area.
- **Two-tier predator AI** with patrol, hunt and flee states, plus steering-based obstacle avoidance.
- **Survival mechanics:** hunger, thirst, health, fall damage and environmental hazards.
- **Story-driven mission:** collect clues, rescue friends, and decide whether to trust a message from your future self.
- **Deterministic world.** A fixed random seed means the layout is identical on every run and reset.

## 🎯 Objective

Rescue **all 5 friends** before the **5-minute rescue timer** runs out, while keeping yourself fed, hydrated and alive.

| Outcome | Condition |
|---|---|
| **Win** | 5/5 friends rescued |
| **Lose (death)** | Health reaches 0 (predator, starvation, dehydration, falling, hazard) |
| **Lose (time)** | Timer hits 0:00 with fewer than 5 friends rescued |

At the end of every run you get a score and rank:

| Rank | Requirement |
|---|---|
| **S – Legendary Rescue** | 5 friends and a score of 1300+ |
| **A – Great Escape** | 5 friends |
| **B – Close Call** | 3–4 friends |
| **C – Survivor** | 1–2 friends |
| **D – Lost Soul** | 0 friends |

`Score = (friends × 200) + (clues × 50) + seconds remaining`

## 🎮 Controls

| Key | Action |
|---|---|
| `W` `A` `S` `D` | Move (relative to camera direction) |
| `Space` | Jump (also advances radio dialogue) |
| `F` | Throw a flare |
| `←` `→` | Rotate camera around the player |
| `↑` `↓` | Tilt camera up/down |
| Left mouse + drag | Rotate/tilt camera |
| `J` | Toggle journal |
| `Y` / `N` | Trust / ignore your future self's offer |
| `P` | Switch to **night** |
| `L` | Switch to **day** |
| `R` | Reset the game (works any time, including after game over) |

> Day/night is fully manual. It never changes unless you press `P` or `L`.

## 🚀 Getting Started

### Requirements

- Python 3.8+
- [PyOpenGL](https://pypi.org/project/PyOpenGL/)
- A GLUT implementation (FreeGLUT)

### Install

```bash
pip install PyOpenGL PyOpenGL_accelerate
```

**GLUT setup by platform:**

- **Windows:** PyOpenGL needs a FreeGLUT DLL. If you see a `NullFunctionPointerError` on startup, download `freeglut.dll` (64-bit) and place it next to the script or in `C:\Windows\System32`. Alternatively, install a PyOpenGL wheel that bundles it, such as `pip install PyOpenGL-accelerate` from [Christoph Gohlke's builds](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyopengl).
- **Linux (Debian/Ubuntu):** `sudo apt install freeglut3-dev`
- **macOS:** GLUT ships with the OS, so no extra steps are normally needed.

### Run

```bash
python Escape_the_island.py
```

A 1000×800 window titled *Island Escape* will open.

## 🧭 How to Play

1. **Stay alive.** Hunger and thirst drain over time (about 4 and 3 minutes respectively). Grab orange food orbs and blue water orbs, which respawn after 25 seconds. At zero, you start taking damage.
2. **Find the radio** near the center-right of the island. Your "future self" explains the mission and offers a shortcut: trust it (`Y`) or go it alone (`N`).
3. **Collect clues** (spinning yellow cubes). They're saved in your journal (`J`) and hint at the island's secrets.
4. **Rescue friends** by walking up to them. Four are on the main island.
5. **Find the fifth friend** at night. Press `P` and a stepping-stone bridge appears at the south edge of the island, leading to a hidden area. Or, if you trust the radio, the last friend is moved to an easy spot near the shore instead.
6. **Avoid the predator.** It patrols by day and hunts when you get close. Throw a flare (`F`) to scare it away for a few seconds.
7. **Watch your step.** Falling from great heights hurts, and the red zone in the southwest corner burns.

## 🗺️ World Objects

| Object | Description |
|---|---|
| 🍊 Orange orb | Restores hunger |
| 💧 Blue orb | Restores thirst |
| 🟨 Yellow spinning cube | Clue (added to journal) |
| 🔴 Red cylinder with glowing tip | Flare pickup (+1 flare; you start with 2) |
| 🗼 Raised platforms | Jump onto them; walk or jump off to fall back down |
| 🪨 Rocks | Solid from the side, but you can jump up and stand on them |
| 🌲 Trees / walls | Always solid |
| 🔥 Red disk | Hazard zone, damages you while you stand in it |
| 📻 Radio | Triggers the future-self message |
| 📡 Signal tower | Turns green once all 5 friends are found |

## 🧩 Code Overview

The whole game lives in a single file, `Escape_the_island.py`. Each major system is tagged in the source with a `FEATURE n` comment you can search for:

| Feature | System | Key functions |
|---|---|---|
| 1 | Free-roam movement and collision | `update_player_physics`, `try_move`, `blocked` |
| 2 | Jump and gravity | `update_player_physics`, `handle_space` |
| 3 | Third-person orbit camera | `setupCamera`, `update_camera_from_input` |
| 4 | Hunger and thirst | `update_survival_stats`, `check_food_water_pickups` |
| 5 | Health and damage | `damage_player`, hazard zones, fall damage |
| 6 | Day/night fantasy transformation | `update_day_night_cycle`, `get_sky_color`, `draw_obstacles` |
| 7 | Hidden night-only path | stepping-stone obstacles, `clamp_to_island` |
| 8 | Clues and journal | `check_clue_pickups`, `draw_journal_panel` |
| 9 | Friend rescue mission | `check_friend_rescues`, `draw_friends` |
| 10 | Predator AI and pathfinding | `update_predator_ai`, `avoid_obstacles` |
| 11 | Radio and future-self dialogue | `check_radio`, `advance_dialogue`, `draw_dialogue_box` |
| 12 | Trust/ignore choice and world reroute | `resolve_radio_choice` |
| 13 | Throwable flares and predator fear | `throw_flare`, `update_flares` |
| 14 | Flare inventory | `check_flare_pickups` |
| 15 | Rescue rank and score | `compute_rescue_rank` |

**Coordinate convention:** Y is up and the ground is the XZ plane at `y = 0`. The island is a circle of radius `GRID_LENGTH` (600 units).

### Tuning

Gameplay constants are collected near the top of the file, so it's easy to adjust difficulty:

```python
MOVE_SPEED = 220.0          # player speed (units/sec)
GRAVITY = 900.0
JUMP_SPEED = 400.0
HUNGER_RATE = 100.0 / 240.0 # hunger empties in ~4 minutes
THIRST_RATE = 100.0 / 180.0 # thirst empties in ~3 minutes
FLARE_SCARE_RADIUS = 220.0
FLARE_FLEE_TIME = 4.0       # seconds the predator flees
```

The predator's speed, detection radius and damage are defined in `build_world()`, and the rescue timer starts at `300.0` seconds in `game_state`.

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| `NullFunctionPointerError` or GLUT not found | Install FreeGLUT for your OS (see [Install](#install)) |
| Black or blank window | Update your graphics drivers; the game needs basic OpenGL 2.x support |
| Controls feel stuck after alt-tabbing | Tap the stuck key once, or press `R` to reset input state |
| Very low FPS | Close other GPU-heavy apps; the game uses immediate-mode rendering |

## 🙌 Acknowledgements

Built with [PyOpenGL](https://pyopengl.sourceforge.net/) and FreeGLUT.
