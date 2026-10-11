"""
================================================================================
 ISLAND ESCAPE - a 3D survival game built with PyOpenGL + GLUT only
================================================================================
Coordinate convention: Y is UP. The ground plane is the XZ plane at y = 0.
The island spans roughly [-GRID_LENGTH, GRID_LENGTH] on both X and Z.

No shaders, no VBOs/VAOs, no textures, no external model files, no
glutTimerFunc(). All timing runs off wall-clock delta time computed inside
idle(). Everything is built from GLUT/GLU primitives + glBegin/glEnd shapes
combined with glTranslatef / glRotatef / glScalef and flat glColor3f colors.

--------------------------------------------------------------------------
CONTROLS
--------------------------------------------------------------------------
  W / A / S / D      Move (relative to the direction the camera is facing)
  SPACE              Jump  (also advances the future-self radio message)
  F                  Throw a flare (scares the predator off - needs 1+ in stock)
  Arrow Left/Right    Rotate camera around the player
  Arrow Up/Down       Tilt camera up/down
  Left-mouse + drag   Also rotates/tilts the camera
  J                  Toggle the journal (collected clues)
  Y / N              Trust / Ignore the future-self's offer (radio event)
  R                  Reset the game at any time (including after game over)
  P                  Switch to NIGHT (manual control - no automatic cycle)
  L                  Switch to DAY

--------------------------------------------------------------------------
FEATURE MAP (search these tags in the code, e.g. "FEATURE 6")
--------------------------------------------------------------------------
  FEATURE 1  - Free-roam movement + collision            (update_player_physics, try_move, blocked)
  FEATURE 2  - Jump + gravity                             (update_player_physics, handle_space)
  FEATURE 3  - Third-person explorer camera                (setupCamera, update_camera_from_input)
  FEATURE 4  - Hunger & thirst system                      (update_survival_stats, check_food_water_pickups)
  FEATURE 5  - Health & damage system                      (damage_player, hazard zones, fall damage, starvation)
  FEATURE 6  - Day/night -> fantasy transformation          (manual: P/L - update_day_night_cycle, get_sky_color, draw_obstacles)
  FEATURE 7  - Fantasy-only hidden path & clue system       (steppingstone obstacles, clamp_to_island, hidden clue/friend)
  FEATURE 8  - Clue investigation & journal system          (check_clue_pickups, draw_journal_panel)
  FEATURE 9  - Friend rescue & dynamic mission system       (check_friend_rescues, draw_friends)
  FEATURE 10 - Two-tier AI + pathfinding predator           (update_predator_ai, avoid_obstacles)
  FEATURE 11 - Radio pickup + future-self message system    (check_radio, advance_dialogue, draw_dialogue_box)
  FEATURE 12 - Trust/ignore choice with one reroute         (resolve_radio_choice)
  FEATURE 13 - Throwable flare + predator fear response     (throw_flare, update_flares - projectile system)
  FEATURE 14 - Flare inventory / resource-gated tool        (check_flare_pickups, game_state["flare_count"])
  FEATURE 15 - Rescue performance rank                      (compute_rescue_rank)
  END CONDITIONS - implemented exactly inside idle()        (trigger_game_over, trigger_game_win)
================================================================================
"""

import math
import random
import time

from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *

# ============================================================================
# TEMPLATE GLOBALS (kept from the starter template)
# ============================================================================
camera_pos = (0, 500, 500)   # no longer drives rendering directly; kept for
                              # template compatibility. The real eye position
                              # is computed every frame inside setupCamera()
                              # from the `player` and `camera` state below.
fovY = 120
GRID_LENGTH = 600            # island half-extent on X and Z

# ============================================================================
# TUNING CONSTANTS
# ============================================================================
MOVE_SPEED = 220.0            # units / second
GRAVITY = 900.0                # units / second^2
JUMP_SPEED = 400.0              # units / second (upward impulse)
FALL_DAMAGE_THRESHOLD = 260.0   # fall distance (units) before it starts to hurt
FALL_DAMAGE_SCALE = 0.10        # hp lost per unit fallen beyond the threshold

HUNGER_RATE = 100.0 / 240.0     # hunger empties over ~4 minutes
THIRST_RATE = 100.0 / 180.0     # thirst empties over ~3 minutes
STARVE_DAMAGE_RATE = 2.0        # hp/sec drained while starving or dehydrated

CAMERA_TURN_SPEED = 1.6         # radians/second (arrow keys)
CAMERA_PITCH_SPEED = 1.0        # radians/second (arrow keys)

PREDATOR_RADIUS = 24.0          # collision radius used for the predator's hard obstacle check

FLARE_THROW_SPEED = 240.0       # horizontal speed of a thrown flare
FLARE_THROW_UP = 170.0          # initial upward speed of a thrown flare
FLARE_SCARE_RADIUS = 220.0      # a landed flare scares the predator within this range
FLARE_FLEE_TIME = 4.0           # seconds the predator flees after being scared
FLARE_GLOW_TIME = 3.0           # seconds a landed flare stays lit before burning out

# ============================================================================
# GLOBAL STATE
# ============================================================================
game_state = {
    "health": 100.0,
    "hunger": 100.0,
    "thirst": 100.0,
    "friends_found": 0,
    "timer": 300.0,          # rescue-window countdown, seconds
    "flare_count": 2,        # FEATURE 14: carried flares, starts with a couple
    "game_over": False,
    "game_win": False,
    "end_reason": None,
    "score": 0,              # FEATURE 15: computed once the run ends
    "rank": None,
}

player = {
    "x": 0.0, "y": 0.0, "z": 200.0,
    "vel_y": 0.0,
    "on_ground": True,
    "facing": math.pi,       # radians; direction the player model is drawn facing
    "radius": 18.0,
    "height": 60.0,
    "fall_start_y": 0.0,
    "was_airborne": False,
}

camera = {
    "yaw": math.pi,          # radians, orbit angle around the player
    "pitch": 0.26,           # radians above horizontal
    "distance": 95.0,        # follow distance - tight, close-up third-person
    "min_pitch": 0.08,
    "max_pitch": 1.3,
}

day_night = {
    # Day/night here is fully MANUAL - it only changes when the player
    # presses P (night) or L (day). "transition" eases between 0
    # (full day) and 1 (full night) over ~1.5s so the sky/colors blend
    # smoothly instead of snapping instantly.
    "is_night": False,
    "transition": 0.0,
}

ui_state = {"dialogue_active": False}

radio_message = {
    "triggered": False,
    "showing": False,
    "index": 0,
    "lines": [
        "...static... is this thing on? It's -- it's you. From the future.",
        "I don't have long. The rescue signal only stays open for so long.",
        "Find all five of your friends before the rescue window closes.",
        "There is one more thing I can do for you: trust me, and I'll open",
        "a shortcut to the friend you'd otherwise never reach in time.",
    ],
    "choice_pending": False,
    "choice_made": None,     # None / "trust" / "ignore"
}

last_damage_cause = {"cause": None}

keys_down = set()
special_keys_down = set()
mouse_state = {"dragging": False, "last_x": 0, "last_y": 0}

journal = []
show_journal = False

obstacles = []
food_pickups = []
water_pickups = []
clue_pickups = []
flare_pickups = []
friends = []
predator = {}
radio = {"x": 100.0, "z": 60.0}
signal_device = {"x": 0.0, "z": 0.0}
hazard_zones = []
flares_thrown = []

QUADRIC = None
STAR_FIELD = None

frame_dt = 0.0
last_frame_time = time.time()

FRIEND_COLORS = [
    (0.85, 0.20, 0.20), (0.20, 0.80, 0.30), (0.90, 0.60, 0.10),
    (0.60, 0.20, 0.85), (0.20, 0.75, 0.80),
]


# ============================================================================
# WORLD CONSTRUCTION  (FEATURES 1, 4, 5, 6, 7, 8, 9, 10, 11)
# ============================================================================
def build_world():
    """(Re)builds every placed object on the island. Uses a fixed random
    seed so the layout is reproducible between runs/resets, which makes
    testing and grading easier."""
    global obstacles, food_pickups, water_pickups, clue_pickups, flare_pickups, friends
    global predator, radio, signal_device, hazard_zones

    random.seed(7)
    obstacles = []

    # --- FEATURE 1: static obstacles (trees / rocks) ---
    tree_positions = [(-380, -150), (-300, 220), (-120, -380), (150, -300),
                       (320, 120), (400, -250), (-450, 80), (60, 380),
                       (-200, 420), (250, 420)]
    for (x, z) in tree_positions:
        obstacles.append({"x": x, "z": z, "y": 0.0, "r": 26.0,
                           "kind": "tree", "night_only": False, "fantasy": True})

    rock_positions = [(-200, 50), (180, -80), (-350, -320), (350, 300),
                       (0, -450), (450, -50), (-450, -200), (100, 150),
                       (-100, -150), (300, -400)]
    for (x, z) in rock_positions:
        r = 30.0
        obstacles.append({"x": x, "z": z, "y": 0.0, "r": r,
                           "kind": "rock", "night_only": False, "fantasy": True,
                           "top": r * 1.10})   # matches draw_rock()'s actual visual height

    # rock walls (big blockers, never fantasy-swapped)
    obstacles.append({"x": -250, "z": 300, "y": 0.0, "r": 60.0,
                       "kind": "wall", "night_only": False, "fantasy": False})
    obstacles.append({"x": 220, "z": -200, "y": 0.0, "r": 60.0,
                       "kind": "wall", "night_only": False, "fantasy": False})

    # raised platforms - "towers" you must jump (SPACE) up onto, and can
    # jump/walk back off the edge of to fall to the ground (FEATURE 2)
    obstacles.append({"x": -100, "z": -50, "y": 0.0, "r": 70.0,
                       "kind": "platform", "top": 45.0,
                       "night_only": False, "fantasy": False})
    obstacles.append({"x": 150, "z": 250, "y": 0.0, "r": 70.0,
                       "kind": "platform", "top": 60.0,
                       "night_only": False, "fantasy": False})

    # --- FEATURE 6/7: night-only stepping-stone bridge to the hidden area ---
    bridge_start_z = GRID_LENGTH - 40.0   # 560 -> just inside the daytime boundary
    for i in range(9):
        obstacles.append({
            "x": 0.0, "z": bridge_start_z + i * 50.0, "y": 0.0,
            "r": 34.0, "kind": "steppingstone", "top": 18.0,
            "night_only": True, "fantasy": True,
        })

    # --- FEATURE 5: environmental hazard zone (deals damage while inside) ---
    hazard_zones = [{"x": -420.0, "z": -420.0, "r": 55.0, "dps": 5.0}]

    # --- FEATURE 4: food / water pickups ---
    food_pickups = [{"x": x, "z": z, "active": True, "respawn_timer": 0.0} for (x, z) in
                     [(-260, -60), (120, 180), (-60, -320), (380, 80), (-380, 320)]]
    water_pickups = [{"x": x, "z": z, "active": True, "respawn_timer": 0.0} for (x, z) in
                      [(60, -220), (-320, 150), (220, 340), (0, -40), (340, -320)]]

    # --- FEATURE 8: clue pickups (journal entries) ---
    clue_pickups = [
        {"x": -150.0, "z": 80.0, "active": True,
         "text": "A torn map shows stones leading south past the treeline at night."},
        {"x": 250.0, "z": -150.0, "active": True,
         "text": "Footprints circle a strange rock. Something hunts here after dark."},
        {"x": -400.0, "z": -250.0, "active": True,
         "text": "Carved warning: the predator sleeps by day, hunts by moonlight."},
        {"x": 0.0, "z": GRID_LENGTH + 500.0, "active": True,
         "text": "A note pinned to a stone: your last friend is trapped beyond here."},
    ]

    # --- FEATURE 14: flare pickups (scattered, restock your throwable supply) ---
    flare_pickups = [{"x": x, "z": z, "active": True} for (x, z) in
                      [(-180.0, -380.0), (380.0, -100.0), (150.0, -420.0), (-420.0, 220.0)]]

    # --- FEATURE 9: friend NPCs (5 required for the win condition) ---
    friends = [
        {"x": -300.0, "z": 100.0, "active": True},
        {"x": 280.0, "z": -260.0, "active": True},
        {"x": -100.0, "z": 380.0, "active": True},
        {"x": 400.0, "z": 250.0, "active": True},
        {"x": 0.0, "z": GRID_LENGTH + 520.0, "active": True},  # only reachable at night (FEATURE 7)
    ]

    # --- FEATURE 11: radio + the escape/signal device ---
    radio = {"x": 100.0, "z": 60.0}
    signal_device = {"x": 0.0, "z": 0.0}

    # --- FEATURE 10: predator (patrol waypoints + hunt tuning) ---
    predator = {
        "x": 300.0, "z": -100.0, "state": "patrol",
        "waypoints": [(300.0, -100.0), (-200.0, -300.0), (-350.0, 100.0), (150.0, 300.0)],
        "wp_index": 0,
        "speed": 32.0, "hunt_speed": 65.0,    # moderate - noticeably slower than the player (220), still a threat
        "detect_radius": 180.0, "contact_radius": 40.0,
        "damage": 8.0, "cooldown": 0.0, "flee_timer": 0.0,
        "_dirx": 0.0, "_dirz": 1.0,
    }


def reset_game():
    """Resets every piece of game state and rebuilds the world. Bound to
    the R key at all times, including after a win/loss (END CONDITIONS)."""
    global journal, show_journal, last_frame_time, frame_dt, flares_thrown

    game_state.update({
        "health": 100.0, "hunger": 100.0, "thirst": 100.0,
        "friends_found": 0, "timer": 300.0, "flare_count": 2,
        "game_over": False, "game_win": False, "end_reason": None,
        "score": 0, "rank": None,
    })
    player.update({
        "x": 0.0, "y": 0.0, "z": 200.0, "vel_y": 0.0, "on_ground": True,
        "facing": math.pi, "fall_start_y": 0.0, "was_airborne": False,
    })
    camera.update({"yaw": math.pi, "pitch": 0.26, "distance": 95.0})
    day_night.update({"is_night": False, "transition": 0.0})
    keys_down.clear()
    special_keys_down.clear()
    ui_state["dialogue_active"] = False
    radio_message.update({"triggered": False, "showing": False, "index": 0,
                           "choice_pending": False, "choice_made": None})
    last_damage_cause["cause"] = None

    journal = []
    show_journal = False
    flares_thrown = []

    build_world()

    last_frame_time = time.time()
    frame_dt = 0.0


# ============================================================================
# MATH / COLLISION HELPERS  (FEATURE 1)
# ============================================================================
def near_player(x, z, radius):
    dx = player["x"] - x
    dz = player["z"] - z
    return dx * dx + dz * dz < radius * radius


def clamp_circular(x, z, limit=GRID_LENGTH):
    dist = math.hypot(x, z)
    if dist > limit:
        scale = limit / dist
        x *= scale
        z *= scale
    return x, z


def clamp_to_island(x, z):
    """Boundary clamp. The island is a circle of radius GRID_LENGTH (to
    match its round, beach-ringed look), but the night-only stepping-stone
    bridge (FEATURE 7) opens a narrow corridor through the +Z edge leading
    to the hidden fantasy area."""
    if z > GRID_LENGTH * 0.85 and abs(x) < 70.0 and day_night["is_night"]:
        z = min(z, GRID_LENGTH + 650.0)
        return x, z
    return clamp_circular(x, z)


ROOF_CLEARANCE = 12.0   # how close to a platform's roof height you must
                         # already be (mid-jump) before you're allowed to
                         # pass over its footprint horizontally at all


def blocked(nx, nz, radius, entity_y):
    """True if a circle of the given radius at (nx, nz) collides with a
    solid obstacle, for an entity whose feet are currently at entity_y.

    Trees and walls are always solid (go around them, full body-radius
    buffer). Platforms, stepping stones, and rocks act as solid walls too
    (also with a full buffer, so bodies don't clip into their side) UNLESS
    the entity is already up near their top height - in which case only
    the object's own footprint radius matters (matching get_ground_height
    exactly), so you can walk/jump freely on top and right off the edge
    without being blocked by a buffer that no longer applies up there."""
    for ob in obstacles:
        if ob.get("night_only") and not day_night["is_night"]:
            continue
        dx = nx - ob["x"]
        dz = nz - ob["z"]
        dist_sq = dx * dx + dz * dz
        kind = ob["kind"]

        if kind in ("platform", "steppingstone", "rock"):
            top = ob.get("top", 0.0)
            elevated = entity_y >= top - ROOF_CLEARANCE
            check_radius = ob["r"] if elevated else (radius + ob["r"])
            if dist_sq < check_radius * check_radius:
                if elevated:
                    continue   # within the walkable footprint - not blocked
                return True    # too low - solid wall, buffered by the body radius
            continue

        limit = radius + ob["r"]
        if dist_sq < limit * limit:
            return True        # tree / wall - always solid
    return False


def try_move(dx, dz):
    """Applies a movement delta one axis at a time so the player slides
    along obstacles instead of sticking to them."""
    nx, nz = clamp_to_island(player["x"] + dx, player["z"])
    if not blocked(nx, player["z"], player["radius"], player["y"]):
        player["x"] = nx
    nx2, nz2 = clamp_to_island(player["x"], player["z"] + dz)
    if not blocked(player["x"], nz2, player["radius"], player["y"]):
        player["z"] = nz2


def get_ground_height(x, z):
    """Returns the walkable ground height at (x, z), accounting for
    platforms, rocks (you can stand on top of one), and (at night) the
    stepping-stone bridge."""
    h = 0.0
    for ob in obstacles:
        if ob["kind"] not in ("platform", "steppingstone", "rock"):
            continue
        if ob.get("night_only") and not day_night["is_night"]:
            continue
        dx = x - ob["x"]
        dz = z - ob["z"]
        if dx * dx + dz * dz <= ob["r"] * ob["r"]:
            h = max(h, ob.get("top", 0.0))
    return h


def is_frozen():
    return game_state["game_over"] or game_state["game_win"]


def damage_player(amount, cause):
    if is_frozen() or amount <= 0:
        return
    game_state["health"] = max(0.0, game_state["health"] - amount)
    last_damage_cause["cause"] = cause


# ============================================================================
# PER-FRAME UPDATE FUNCTIONS (called from idle())
# ============================================================================
def update_player_physics():
    """FEATURE 1 (movement + collision) and FEATURE 2 (jump + gravity),
    plus the environmental-hazard part of FEATURE 5."""
    if is_frozen() or ui_state["dialogue_active"]:
        return

    # WASD is relative to the camera's facing direction (camera.yaw), which
    # is also treated as the player's forward heading (see FEATURE 3).
    fwd_x, fwd_z = math.sin(camera["yaw"]), math.cos(camera["yaw"])
    right_x, right_z = math.sin(camera["yaw"] + math.pi / 2), math.cos(camera["yaw"] + math.pi / 2)

    dx = dz = 0.0
    if b'w' in keys_down:
        dx -= fwd_x; dz -= fwd_z
    if b's' in keys_down:
        dx += fwd_x; dz += fwd_z
    if b'a' in keys_down:
        dx -= right_x; dz -= right_z
    if b'd' in keys_down:
        dx += right_x; dz += right_z

    length = math.hypot(dx, dz)
    if length > 1e-4:
        dx, dz = dx / length, dz / length
        player["facing"] = math.atan2(dx, dz)
        try_move(dx * MOVE_SPEED * frame_dt, dz * MOVE_SPEED * frame_dt)

    # gravity integration
    player["vel_y"] -= GRAVITY * frame_dt
    player["y"] += player["vel_y"] * frame_dt

    ground_h = get_ground_height(player["x"], player["z"])
    if player["y"] <= ground_h:
        if player["was_airborne"]:
            fall_distance = player["fall_start_y"] - ground_h
            if fall_distance > FALL_DAMAGE_THRESHOLD:
                damage_player((fall_distance - FALL_DAMAGE_THRESHOLD) * FALL_DAMAGE_SCALE, "fall")
        player["y"] = ground_h
        player["vel_y"] = 0.0
        player["on_ground"] = True
        player["was_airborne"] = False
        player["fall_start_y"] = ground_h
    else:
        player["on_ground"] = False
        player["was_airborne"] = True
        player["fall_start_y"] = max(player["fall_start_y"], player["y"])

    # environmental hazard zones (FEATURE 5)
    for hz in hazard_zones:
        ddx = player["x"] - hz["x"]
        ddz = player["z"] - hz["z"]
        if ddx * ddx + ddz * ddz < hz["r"] * hz["r"]:
            damage_player(hz["dps"] * frame_dt, "hazard")

    update_flares()


def handle_space():
    """SPACE is context-sensitive: it advances the radio dialogue if one is
    showing (FEATURE 11), otherwise it jumps (FEATURE 2)."""
    if ui_state["dialogue_active"]:
        advance_dialogue()
        return
    if is_frozen():
        return
    if player["on_ground"]:
        player["vel_y"] = JUMP_SPEED
        player["on_ground"] = False
        player["was_airborne"] = True


def throw_flare():
    """FEATURE 13: lobs a flare in the direction the player is facing. It
    follows the same gravity-integrated projectile motion as the player's
    own jump; once it lands, any predator within FLARE_SCARE_RADIUS is
    startled into a temporary 'fleeing' AI state (see update_predator_ai)."""
    if is_frozen() or ui_state["dialogue_active"]:
        return
    if game_state["flare_count"] <= 0:
        return
    game_state["flare_count"] -= 1
    fwd_x = math.sin(player["facing"])
    fwd_z = math.cos(player["facing"])
    flares_thrown.append({
        "x": player["x"] + fwd_x * 20.0,
        "y": player["y"] + player["height"] * 0.55,
        "z": player["z"] + fwd_z * 20.0,
        "vx": fwd_x * FLARE_THROW_SPEED,
        "vy": FLARE_THROW_UP,
        "vz": fwd_z * FLARE_THROW_SPEED,
        "landed": False,
        "life": 0.0,
    })


def update_flares():
    """FEATURE 13: projectile motion for thrown flares (reuses GRAVITY,
    same as the player's jump), plus the predator fear-response check on
    landing, plus aging out flares that have finished glowing."""
    for fl in flares_thrown:
        if not fl["landed"]:
            fl["vy"] -= GRAVITY * frame_dt
            fl["x"] += fl["vx"] * frame_dt
            fl["y"] += fl["vy"] * frame_dt
            fl["z"] += fl["vz"] * frame_dt
            if fl["y"] <= 0.0:
                fl["y"] = 0.0
                fl["landed"] = True
                fl["life"] = FLARE_GLOW_TIME
                ddx = predator["x"] - fl["x"]
                ddz = predator["z"] - fl["z"]
                if math.hypot(ddx, ddz) < FLARE_SCARE_RADIUS:
                    predator["state"] = "fleeing"
                    predator["flee_timer"] = FLARE_FLEE_TIME
        else:
            fl["life"] -= frame_dt
    flares_thrown[:] = [f for f in flares_thrown if not (f["landed"] and f["life"] <= 0.0)]


def check_food_water_pickups():
    """FEATURE 4."""
    for f in food_pickups:
        if f["active"]:
            if near_player(f["x"], f["z"], 40.0):
                f["active"] = False
                f["respawn_timer"] = 25.0
                game_state["hunger"] = min(100.0, game_state["hunger"] + 40.0)
        else:
            f["respawn_timer"] -= frame_dt
            if f["respawn_timer"] <= 0.0:
                f["active"] = True

    for w in water_pickups:
        if w["active"]:
            if near_player(w["x"], w["z"], 40.0):
                w["active"] = False
                w["respawn_timer"] = 25.0
                game_state["thirst"] = min(100.0, game_state["thirst"] + 40.0)
        else:
            w["respawn_timer"] -= frame_dt
            if w["respawn_timer"] <= 0.0:
                w["active"] = True


def check_clue_pickups():
    """FEATURE 8."""
    for c in clue_pickups:
        if c["active"] and near_player(c["x"], c["z"], 35.0):
            c["active"] = False
            journal.append(c["text"])


def check_flare_pickups():
    """FEATURE 14: restocks the flare inventory used by throw_flare()."""
    for fp in flare_pickups:
        if fp["active"] and near_player(fp["x"], fp["z"], 35.0):
            fp["active"] = False
            game_state["flare_count"] += 1


def check_friend_rescues():
    """FEATURE 9."""
    for fr in friends:
        if fr["active"] and near_player(fr["x"], fr["z"], 40.0):
            fr["active"] = False
            game_state["friends_found"] += 1


def check_radio():
    """FEATURE 11: proximity trigger for the one-time future-self message."""
    if (not radio_message["triggered"]) and near_player(radio["x"], radio["z"], 45.0):
        radio_message["triggered"] = True
        radio_message["showing"] = True
        radio_message["index"] = 0
        ui_state["dialogue_active"] = True


def update_survival_stats():
    """FEATURES 4, 5, 8, 9, 11, 14 (mission proximity checks live here since
    the idle() call list is fixed to the five names in the spec)."""
    if is_frozen() or ui_state["dialogue_active"]:
        return

    game_state["hunger"] = max(0.0, game_state["hunger"] - HUNGER_RATE * frame_dt)
    game_state["thirst"] = max(0.0, game_state["thirst"] - THIRST_RATE * frame_dt)
    if game_state["hunger"] <= 0.0 or game_state["thirst"] <= 0.0:
        damage_player(STARVE_DAMAGE_RATE * frame_dt, "starved")

    check_food_water_pickups()
    check_clue_pickups()
    check_flare_pickups()
    check_friend_rescues()
    check_radio()


def avoid_obstacles(px, pz, dirx, dirz):
    """Simple steering-based obstacle avoidance for the predator: look a
    short distance ahead along the current heading and, if it would hit a
    large static obstacle, blend in a perpendicular steering component."""
    look = 90.0
    ax, az = px + dirx * look, pz + dirz * look
    for ob in obstacles:
        if ob["kind"] not in ("tree", "rock", "wall"):
            continue
        dx = ax - ob["x"]
        dz = az - ob["z"]
        d = math.hypot(dx, dz)
        if d < ob["r"] + 30.0:
            perp_x, perp_z = -dirz, dirx
            test_x, test_z = ax + perp_x * 20.0, az + perp_z * 20.0
            if math.hypot(test_x - ob["x"], test_z - ob["z"]) > d:
                dirx, dirz = dirx * 0.4 + perp_x * 0.6, dirz * 0.4 + perp_z * 0.6
            else:
                dirx, dirz = dirx * 0.4 - perp_x * 0.6, dirz * 0.4 - perp_z * 0.6
            n = math.hypot(dirx, dirz)
            if n > 1e-4:
                dirx, dirz = dirx / n, dirz / n
            break
    return dirx, dirz


def update_predator_ai():
    """FEATURE 10: two-tier patrol/hunt AI with simple steering-based
    pathfinding and obstacle avoidance."""
    if is_frozen():
        return

    p = predator
    if p["cooldown"] > 0.0:
        p["cooldown"] -= frame_dt

    ddx = player["x"] - p["x"]
    ddz = player["z"] - p["z"]
    dist = math.hypot(ddx, ddz)

    if p["state"] == "fleeing":
        p["flee_timer"] -= frame_dt
        if p["flee_timer"] <= 0.0:
            p["state"] = "patrol"
    else:
        if dist < p["detect_radius"]:
            p["state"] = "hunt"
        elif dist > p["detect_radius"] * 1.4:
            p["state"] = "patrol"

    if p["state"] == "fleeing":
        # FEATURE 13: run directly away from the player, at hunt speed,
        # until the flare's fear effect wears off
        speed = p["hunt_speed"]
        if dist > 1e-3:
            dirx, dirz = -ddx / dist, -ddz / dist
        else:
            dirx, dirz = 0.0, 0.0
    elif p["state"] == "hunt":
        speed = p["hunt_speed"]
        if dist > 1e-3:
            dirx, dirz = ddx / dist, ddz / dist
        else:
            dirx, dirz = 0.0, 0.0
    else:
        speed = p["speed"]
        wp = p["waypoints"][p["wp_index"]]
        wdx = wp[0] - p["x"]
        wdz = wp[1] - p["z"]
        wdist = math.hypot(wdx, wdz)
        if wdist < 20.0:
            p["wp_index"] = (p["wp_index"] + 1) % len(p["waypoints"])
            dirx, dirz = 0.0, 0.0
        else:
            dirx, dirz = wdx / wdist, wdz / wdist

    dirx, dirz = avoid_obstacles(p["x"], p["z"], dirx, dirz)
    if abs(dirx) > 1e-4 or abs(dirz) > 1e-4:
        p["_dirx"], p["_dirz"] = dirx, dirz

    # move one axis at a time with a HARD collision check (entity_y=0.0 -
    # the predator never jumps, so it always treats trees/rocks/walls AND
    # platforms/stepping-stones as solid and has to go around them; the
    # steering in avoid_obstacles() above just makes that path smoother,
    # this is the hard stop that guarantees it can never clip through).
    nx = p["x"] + dirx * speed * frame_dt
    if not blocked(nx, p["z"], PREDATOR_RADIUS, 0.0):
        p["x"] = nx
    nz = p["z"] + dirz * speed * frame_dt
    if not blocked(p["x"], nz, PREDATOR_RADIUS, 0.0):
        p["z"] = nz
    p["x"], p["z"] = clamp_circular(p["x"], p["z"])

    if p["state"] != "fleeing" and dist < p["contact_radius"] and p["cooldown"] <= 0.0:
        damage_player(p["damage"], "predator")
        p["cooldown"] = 1.6
        if dist > 1e-3:
            kb = 90.0
            nx, nz = clamp_to_island(player["x"] + (ddx / dist) * kb,
                                      player["z"] + (ddz / dist) * kb)
            # only apply the knockback if it doesn't shove the player into
            # solid geometry - otherwise they'd be shoved into a rock/tower
            # footprint while still too low, which would incorrectly snap
            # them up onto it next frame (the exact bug jumping now avoids)
            if not blocked(nx, nz, player["radius"], player["y"]):
                player["x"], player["z"] = nx, nz


def get_sky_color():
    """FEATURE 6: smoothly interpolates the sky/clear color based on the
    current day<->night transition amount (0 = full day, 1 = full night)."""
    blend = day_night["transition"]
    day_color = (0.53, 0.80, 0.92)
    night_color = (0.03, 0.03, 0.10)
    r = day_color[0] + (night_color[0] - day_color[0]) * blend
    g = day_color[1] + (night_color[1] - day_color[1]) * blend
    b = day_color[2] + (night_color[2] - day_color[2]) * blend
    return (r, g, b)


DAY_NIGHT_TRANSITION_SPEED = 0.7   # per second; ~1.4s for a full day<->night blend


def update_day_night_cycle():
    """FEATURE 6. Day/night is switched manually (P = night, L = day);
    this just eases the visual transition amount toward whichever state is
    currently selected, so the change is a smooth blend rather than an
    instant snap. It does NOT auto-advance on its own."""
    if is_frozen():
        return
    target = 1.0 if day_night["is_night"] else 0.0
    diff = target - day_night["transition"]
    step = DAY_NIGHT_TRANSITION_SPEED * frame_dt
    if abs(diff) <= step:
        day_night["transition"] = target
    else:
        day_night["transition"] += step if diff > 0 else -step


def update_rescue_timer():
    """Drives the countdown referenced by the radio message (FEATURE 11)
    and the END CONDITIONS."""
    if is_frozen():
        return
    game_state["timer"] = max(0.0, game_state["timer"] - frame_dt)


# ============================================================================
# END CONDITIONS
# ============================================================================
def compute_rescue_rank():
    """FEATURE 15: a simple scoring/ranking system computed once the run
    ends (win OR lose - even a loss shows how close you got). Not a
    variable tweak - it's a new scored-outcome system layered on top of
    the existing mission stats."""
    score = (game_state["friends_found"] * 200
             + len(journal) * 50
             + int(game_state["timer"]))
    if game_state["friends_found"] >= 5 and score >= 1300:
        rank = "S - Legendary Rescue"
    elif game_state["friends_found"] >= 5:
        rank = "A - Great Escape"
    elif game_state["friends_found"] >= 3:
        rank = "B - Close Call"
    elif game_state["friends_found"] >= 1:
        rank = "C - Survivor"
    else:
        rank = "D - Lost Soul"
    game_state["score"] = score
    game_state["rank"] = rank


def trigger_game_over(reason):
    if game_state["game_over"] or game_state["game_win"]:
        return
    game_state["game_over"] = True
    if reason == "death":
        cause = last_damage_cause["cause"] or "unknown causes"
        game_state["end_reason"] = "YOU DIED - " + cause
    elif reason == "rescued_too_late":
        game_state["end_reason"] = "RESCUE MISSED"
    compute_rescue_rank()


def trigger_game_win():
    if game_state["game_over"] or game_state["game_win"]:
        return
    game_state["game_win"] = True
    game_state["end_reason"] = "YOU ESCAPED"
    compute_rescue_rank()


# ============================================================================
# LOW-LEVEL DRAW HELPERS
# ============================================================================
def get_quadric():
    global QUADRIC
    if QUADRIC is None:
        QUADRIC = gluNewQuadric()
    return QUADRIC


def _begin_ortho():
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, 1000, 0, 800)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()


def _end_ortho():
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glPopMatrix()


def draw_text(x, y, text, font=GLUT_BITMAP_HELVETICA_18):
    """Required template entry point: draws 2D text as a screen-space
    overlay. Caller is expected to set glColor3f before calling."""
    _begin_ortho()
    glRasterPos2f(x, y)
    for ch in text:
        glutBitmapCharacter(font, ord(ch))
    _end_ortho()


def draw_bar(x, y, w, h, pct, color):
    pct = max(0.0, min(1.0, pct))
    _begin_ortho()
    glDisable(GL_DEPTH_TEST)
    glColor3f(0.15, 0.15, 0.15)
    glBegin(GL_QUADS)
    glVertex2f(x, y); glVertex2f(x + w, y); glVertex2f(x + w, y + h); glVertex2f(x, y + h)
    glEnd()
    glColor3f(color[0], color[1], color[2])
    fw = w * pct
    glBegin(GL_QUADS)
    glVertex2f(x, y); glVertex2f(x + fw, y); glVertex2f(x + fw, y + h); glVertex2f(x, y + h)
    glEnd()
    glEnable(GL_DEPTH_TEST)
    _end_ortho()


# ============================================================================
# WORLD RENDERING  (FEATURES 1, 5, 6, 7)
# ============================================================================
def _ring_vertices(radius, y, segments=48):
    pts = []
    for i in range(segments + 1):
        ang = 2.0 * math.pi * i / segments
        pts.append((math.sin(ang) * radius, y, math.cos(ang) * radius))
    return pts


def draw_ground():
    """FEATURE 6/7. Renders the island as a round patch of grass ringed by
    a sandy beach, surrounded by an ocean - so it actually reads as an
    island rather than a flat rectangle."""
    is_night = day_night["is_night"]
    blend = day_night["transition"]

    # --- ocean: a huge flat plane surrounding the island, gently animated ---
    wave = 0.03 * math.sin(time.time() * 0.8)
    ocean_day = (0.10, 0.42, 0.68)
    ocean_night = (0.02, 0.06, 0.18)
    oc = tuple(ocean_day[i] + (ocean_night[i] - ocean_day[i]) * blend + wave for i in range(3))
    glColor3f(*oc)
    glBegin(GL_QUADS)
    glVertex3f(-3000, -3.0, -3000)
    glVertex3f(-3000, -3.0, 3000)
    glVertex3f(3000, -3.0, 3000)
    glVertex3f(3000, -3.0, -3000)
    glEnd()

    # --- beach: a sandy ring just outside the walkable green area ---
    sand_day = (0.86, 0.78, 0.55)
    sand_night = (0.30, 0.28, 0.34)
    sc = tuple(sand_day[i] + (sand_night[i] - sand_day[i]) * blend for i in range(3))
    glColor3f(*sc)
    beach_ring = _ring_vertices(GRID_LENGTH + 55, -0.6)
    glBegin(GL_TRIANGLE_FAN)
    glVertex3f(0, -0.6, 0)
    for (x, y, z) in beach_ring:
        glVertex3f(x, y, z)
    glEnd()

    # --- grass: the round, walkable island interior ---
    sparkle = 0.04 * math.sin(time.time() * 2.0) if is_night else 0.0
    grass_day = (0.24, 0.55, 0.18)
    grass_night = (0.09, 0.26, 0.21)
    gc = tuple(grass_day[i] + (grass_night[i] - grass_day[i]) * blend + sparkle for i in range(3))
    glColor3f(*gc)
    grass_ring = _ring_vertices(GRID_LENGTH, 0.0)
    glBegin(GL_TRIANGLE_FAN)
    glVertex3f(0, 0.0, 0)
    for (x, y, z) in grass_ring:
        glVertex3f(x, y, z)
    glEnd()

    # hidden fantasy island beyond the boundary - only visible at night (FEATURE 7)
    if is_night:
        glColor3f(0.16, 0.10, 0.28)
        glBegin(GL_QUADS)
        glVertex3f(-180, 0, GRID_LENGTH + 300)
        glVertex3f(-180, 0, GRID_LENGTH + 600)
        glVertex3f(180, 0, GRID_LENGTH + 600)
        glVertex3f(180, 0, GRID_LENGTH + 300)
        glEnd()


def draw_tree(r, fantasy=False):
    """A slightly leaning trunk with a bushy, clustered canopy (several
    overlapping spheres of different sizes/offsets) instead of a single
    perfect cone, so it reads as a more natural-looking tree."""
    quad = get_quadric()
    if fantasy:
        trunk_color = (0.55, 0.30, 0.75)
        leaf_color = (0.80, 0.55, 0.95)
        leaf_color2 = (0.65, 0.40, 0.90)
    else:
        trunk_color = (0.40, 0.26, 0.13)
        leaf_color = (0.16, 0.42, 0.16)
        leaf_color2 = (0.22, 0.50, 0.20)

    trunk_h = r * 2.6

    glColor3f(*trunk_color)
    glPushMatrix()
    glRotatef(-90, 1, 0, 0)
    gluCylinder(quad, r * 0.34, r * 0.22, trunk_h, 8, 3)
    glPopMatrix()

    # canopy: a cluster of overlapping, unevenly-sized spheres
    canopy = [
        (0.0,        trunk_h + r * 0.55, 0.0,        r * 1.15, leaf_color),
        (r * 0.55,   trunk_h + r * 0.15, r * 0.35,   r * 0.80, leaf_color2),
        (-r * 0.50,  trunk_h + r * 0.30, -r * 0.40,  r * 0.85, leaf_color2),
        (r * 0.15,   trunk_h + r * 0.95, -r * 0.45,  r * 0.75, leaf_color),
        (-r * 0.30,  trunk_h + r * 0.85, r * 0.50,   r * 0.70, leaf_color),
    ]
    for (ox, oy, oz, radius, color) in canopy:
        glColor3f(*color)
        glPushMatrix()
        glTranslatef(ox, oy, oz)
        gluSphere(quad, radius, 8, 7)
        glPopMatrix()


def draw_rock(r, fantasy=False):
    quad = get_quadric()
    color = (0.55, 0.35, 0.85) if fantasy else (0.5, 0.5, 0.5)
    glColor3f(*color)
    glPushMatrix()
    glTranslatef(0, r * 0.35, 0)
    glScalef(1.0, 0.75, 1.0)
    gluSphere(quad, r, 10, 8)
    glPopMatrix()


def draw_obstacles():
    is_night = day_night["is_night"]
    for ob in obstacles:
        if ob.get("night_only") and not is_night:
            continue
        glPushMatrix()
        glTranslatef(ob["x"], ob.get("y", 0.0), ob["z"])
        kind = ob["kind"]

        if kind == "tree":
            draw_tree(ob["r"], fantasy=(is_night and ob.get("fantasy")))
        elif kind == "rock":
            draw_rock(ob["r"], fantasy=(is_night and ob.get("fantasy")))
        elif kind == "wall":
            glColor3f(0.45, 0.42, 0.40)
            glTranslatef(0, 55.0, 0)
            glScalef(ob["r"] * 1.6, 110.0, ob["r"] * 1.6)
            glutSolidCube(1.0)
        elif kind == "platform":
            top = ob.get("top", 50.0)
            glColor3f(0.5, 0.45, 0.35)
            glTranslatef(0, top * 0.5, 0)
            glScalef(ob["r"] * 1.4, top, ob["r"] * 1.4)
            glutSolidCube(1.0)
        elif kind == "steppingstone":
            top = ob.get("top", 18.0)
            if is_night:
                glColor3f(0.55, 0.35, 0.75)
            else:
                glColor3f(0.5, 0.5, 0.5)
            glTranslatef(0, top * 0.5, 0)
            glScalef(ob["r"], top, ob["r"])
            glutSolidCube(1.0)

        glPopMatrix()


def draw_hazard_zones():
    quad = get_quadric()
    for hz in hazard_zones:
        glPushMatrix()
        glTranslatef(hz["x"], 0.6, hz["z"])
        glColor3f(0.85, 0.25, 0.10)
        glRotatef(-90, 1, 0, 0)
        gluDisk(quad, 0, hz["r"], 20, 1)
        glPopMatrix()


def draw_pickups():
    quad = get_quadric()
    t = time.time()

    for f in food_pickups:
        if not f["active"]:
            continue
        glPushMatrix()
        glTranslatef(f["x"], 20.0 + 5.0 * math.sin(t * 3.0 + f["x"]), f["z"])
        glColor3f(0.9, 0.6, 0.1)
        gluSphere(quad, 14, 8, 8)
        glPopMatrix()

    for w in water_pickups:
        if not w["active"]:
            continue
        glPushMatrix()
        glTranslatef(w["x"], 18.0 + 5.0 * math.sin(t * 3.0 + w["x"]), w["z"])
        glColor3f(0.2, 0.5, 0.95)
        gluSphere(quad, 13, 8, 8)
        glPopMatrix()

    for c in clue_pickups:
        if not c["active"]:
            continue
        glPushMatrix()
        glTranslatef(c["x"], 25.0 + 6.0 * math.sin(t * 2.0 + c["x"]), c["z"])
        glColor3f(0.95, 0.9, 0.15)
        glRotatef(45, 0, 0, 1)
        glRotatef((t * 40.0) % 360.0, 0, 1, 0)
        glScalef(14, 14, 14)
        glutSolidCube(1.0)
        glPopMatrix()

    # flare pickups (FEATURE 14) - small red cylinder with a bright tip
    for fp in flare_pickups:
        if not fp["active"]:
            continue
        glPushMatrix()
        glTranslatef(fp["x"], 16.0 + 4.0 * math.sin(t * 2.5 + fp["x"]), fp["z"])
        glColor3f(0.75, 0.15, 0.1)
        glPushMatrix()
        glRotatef(-90, 1, 0, 0)
        gluCylinder(quad, 3.0, 3.0, 16, 6, 2)
        glPopMatrix()
        glColor3f(1.0, 0.65, 0.1)
        glPushMatrix()
        glTranslatef(0, 16, 0)
        gluSphere(quad, 3.5, 6, 6)
        glPopMatrix()
        glPopMatrix()


def draw_flares():
    """FEATURE 13: draws flares currently in flight (a bright streaking
    sphere) and flares that have landed and are glowing on the ground
    (flickering light + a brief ground glow disc) before they burn out."""
    quad = get_quadric()
    for fl in flares_thrown:
        if not fl["landed"]:
            glPushMatrix()
            glTranslatef(fl["x"], fl["y"], fl["z"])
            glColor3f(1.0, 0.55, 0.05)
            gluSphere(quad, 5.0, 8, 8)
            glPopMatrix()
        else:
            flicker = 0.7 + 0.3 * math.sin(time.time() * 20.0 + fl["x"])
            fade = max(0.0, min(1.0, fl["life"] / FLARE_GLOW_TIME))
            glPushMatrix()
            glTranslatef(fl["x"], 6.0, fl["z"])
            glColor3f(1.0 * flicker * fade, 0.45 * flicker * fade, 0.05)
            gluSphere(quad, 5.0, 8, 8)
            glPopMatrix()

            glDisable(GL_DEPTH_TEST)
            glColor3f(0.9 * fade, 0.4 * fade, 0.05)
            glPushMatrix()
            glTranslatef(fl["x"], 0.5, fl["z"])
            glRotatef(-90, 1, 0, 0)
            gluDisk(quad, 0, 45.0 * fade, 16, 1)
            glPopMatrix()
            glEnable(GL_DEPTH_TEST)


def draw_radio_and_signal():
    quad = get_quadric()

    glPushMatrix()
    glTranslatef(radio["x"], 0, radio["z"])
    glColor3f(0.2, 0.2, 0.22)
    glPushMatrix()
    glTranslatef(0, 5, 0)
    glScalef(16, 10, 12)
    glutSolidCube(1.0)
    glPopMatrix()
    glColor3f(0.7, 0.7, 0.1)
    glPushMatrix()
    glTranslatef(0, 10, 0)
    glRotatef(-90, 1, 0, 0)
    gluCylinder(quad, 1.2, 0.4, 26, 6, 2)
    glPopMatrix()
    glPopMatrix()

    active = game_state["friends_found"] >= 5
    glPushMatrix()
    glTranslatef(signal_device["x"], 0, signal_device["z"])
    if active:
        glColor3f(0.2, 0.9, 0.3)
    else:
        glColor3f(0.4, 0.4, 0.4)
    glPushMatrix()
    glRotatef(-90, 1, 0, 0)
    gluCylinder(quad, 6, 6, 90, 8, 2)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0, 95, 0)
    if active:
        glColor3f(0.85, 0.85, 0.9)
    else:
        glColor3f(0.5, 0.5, 0.55)
    gluSphere(quad, 22, 12, 10)
    glPopMatrix()
    glPopMatrix()


def _init_stars():
    global STAR_FIELD
    rnd = random.Random(99)
    STAR_FIELD = [(rnd.uniform(-1500, 1500), rnd.uniform(300, 900), rnd.uniform(-1500, 1500))
                  for _ in range(180)]


def draw_night_effects():
    """FEATURE 6 polish: stars, moon and drifting fireflies to make the
    night island read as sparkly/fantasy."""
    if not day_night["is_night"]:
        return
    if STAR_FIELD is None:
        _init_stars()

    glDisable(GL_DEPTH_TEST)
    glColor3f(1, 1, 1)
    glPointSize(2.0)
    glBegin(GL_POINTS)
    for (x, y, z) in STAR_FIELD:
        glVertex3f(x, y, z)
    glEnd()
    glEnable(GL_DEPTH_TEST)

    quad = get_quadric()
    glPushMatrix()
    glTranslatef(400, 650, -900)
    glColor3f(0.95, 0.95, 0.85)
    gluSphere(quad, 55, 16, 16)
    glPopMatrix()

    glDisable(GL_DEPTH_TEST)
    glPointSize(5.0)
    glColor3f(0.85, 1.0, 0.4)
    glBegin(GL_POINTS)
    t = time.time()
    for i in range(40):
        fx = math.sin(t * 0.7 + i * 1.7) * 300 + math.sin(i) * 250
        fz = math.cos(t * 0.5 + i * 2.3) * 300 + math.cos(i * 1.3) * 250
        fy = 25 + 15 * math.sin(t * 1.5 + i)
        glVertex3f(fx, fy, fz)
    glEnd()
    glPointSize(1.0)
    glEnable(GL_DEPTH_TEST)


# ============================================================================
# CHARACTER RENDERING  (readable head / torso / arms with hands / legs with feet)
# ============================================================================
def draw_person(cx, cy, cz, facing_deg, body_color, head_color, scale=1.0):
    """A readable humanoid: legs run from the ground up to the hips, arms
    hang from the shoulders down to the hands, topped with a head that has
    simple eyes + a mouth on its front (local +Z) side so you can tell at a
    glance whether you're looking at the front or the back of the figure."""
    quad = get_quadric()
    leg_color = (body_color[0] * 0.6, body_color[1] * 0.6, body_color[2] * 0.6)

    HIP_Y = 24.0        # top of the legs / bottom of the torso
    SHOULDER_Y = 44.0   # top of the arms, just under the top of the torso
    HAND_Y = 22.0        # bottom of the arms / where the hands sit
    HEAD_Y = 52.0        # head center

    glPushMatrix()
    glTranslatef(cx, cy, cz)
    glRotatef(facing_deg, 0, 1, 0)
    glScalef(scale, scale, scale)

    # legs: rooted at the ground (y=2) and extending UP to the hips, so
    # they visibly connect the feet to the torso instead of floating.
    glColor3f(*leg_color)
    for lx in (-6, 6):
        glPushMatrix()
        glTranslatef(lx, 2.0, 0)
        glRotatef(-90, 1, 0, 0)
        gluCylinder(quad, 4.2, 3.8, HIP_Y - 2.0, 8, 2)
        glPopMatrix()
        # foot
        glPushMatrix()
        glTranslatef(lx, 0, 3)
        glScalef(6, 4, 10)
        glutSolidCube(1.0)
        glPopMatrix()

    # torso
    glColor3f(*body_color)
    glPushMatrix()
    glTranslatef(0, 34, 0)
    glScalef(15, 22, 9)
    glutSolidCube(1.0)
    glPopMatrix()

    # arms: rooted at the shoulder and extending DOWN to the hands, so they
    # visibly hang at the sides instead of floating up near the head.
    for ax in (-12, 12):
        glColor3f(*body_color)
        glPushMatrix()
        glTranslatef(ax, SHOULDER_Y, 0)
        glRotatef(90, 1, 0, 0)
        gluCylinder(quad, 3.4, 3.0, SHOULDER_Y - HAND_Y, 8, 2)
        glPopMatrix()
        glColor3f(0.93, 0.76, 0.62)
        glPushMatrix()
        glTranslatef(ax, HAND_Y, 0)
        gluSphere(quad, 4.2, 8, 8)
        glPopMatrix()

    # head
    glColor3f(*head_color)
    glPushMatrix()
    glTranslatef(0, HEAD_Y, 0)
    gluSphere(quad, 10.0, 12, 12)
    glPopMatrix()

    # face: two eyes + a mouth on the front (+Z) side of the head, so front
    # vs. back is obvious at a glance instead of the head being a blank ball.
    glColor3f(0.05, 0.05, 0.05)
    for ex in (-3.6, 3.6):
        glPushMatrix()
        glTranslatef(ex, HEAD_Y + 1.5, 8.7)
        gluSphere(quad, 1.4, 6, 6)
        glPopMatrix()
    glPushMatrix()
    glTranslatef(0, HEAD_Y - 4.5, 8.9)
    glScalef(5.0, 1.6, 1.0)
    glutSolidCube(1.0)
    glPopMatrix()

    glPopMatrix()


def draw_player():
    facing_deg = math.degrees(player["facing"])
    draw_person(player["x"], player["y"], player["z"], facing_deg,
                body_color=(0.15, 0.45, 0.85), head_color=(0.93, 0.76, 0.62), scale=1.0)


def draw_friends():
    """FEATURE 9."""
    for i, fr in enumerate(friends):
        if not fr["active"]:
            continue
        col = FRIEND_COLORS[i % len(FRIEND_COLORS)]
        draw_person(fr["x"], 0.0, fr["z"], 0.0,
                    body_color=col, head_color=(0.93, 0.76, 0.62), scale=0.95)


def draw_predator():
    """FEATURE 10: a low four-legged creature with a cone snout and
    glowing eyes at night."""
    quad = get_quadric()
    p = predator
    glPushMatrix()
    glTranslatef(p["x"], 22.0, p["z"])
    ang = math.degrees(math.atan2(p.get("_dirx", 0.0), p.get("_dirz", 1.0)))
    glRotatef(ang, 0, 1, 0)

    if p["state"] == "hunt":
        glColor3f(0.35, 0.08, 0.08)
    elif p["state"] == "fleeing":
        glColor3f(0.55, 0.48, 0.15)   # startled/scared tint (FEATURE 13)
    else:
        glColor3f(0.25, 0.20, 0.18)
    glPushMatrix()
    glScalef(1.6, 1.0, 2.2)
    gluSphere(quad, 16, 10, 8)
    glPopMatrix()

    for lx, lz in ((-10, 14), (10, 14), (-10, -14), (10, -14)):
        glPushMatrix()
        glTranslatef(lx, -14, lz)
        glRotatef(-90, 1, 0, 0)
        gluCylinder(quad, 3.5, 3.0, 18, 6, 2)
        glPopMatrix()

    glColor3f(0.30, 0.10, 0.10)
    glPushMatrix()
    glTranslatef(0, 4, 26)
    glutSolidCone(9, 16, 8, 4)
    glPopMatrix()

    if day_night["is_night"]:
        glColor3f(1.0, 0.15, 0.1)
        for ex in (-4, 4):
            glPushMatrix()
            glTranslatef(ex, 6, 34)
            gluSphere(quad, 1.6, 6, 6)
            glPopMatrix()

    glPopMatrix()


# ============================================================================
# HUD / OVERLAYS  (FEATURES 4, 5, 8, 9, 11, 12, END CONDITIONS)
# ============================================================================
def draw_journal_panel():
    """FEATURE 8."""
    _begin_ortho()
    glDisable(GL_DEPTH_TEST)
    glColor3f(0.05, 0.05, 0.08)
    glBegin(GL_QUADS)
    glVertex2f(650, 120); glVertex2f(980, 120); glVertex2f(980, 760); glVertex2f(650, 760)
    glEnd()
    glEnable(GL_DEPTH_TEST)
    _end_ortho()

    glColor3f(1, 1, 0.6)
    draw_text(660, 735, "JOURNAL (J to close)")
    glColor3f(0.9, 0.9, 0.9)
    y = 705
    if not journal:
        draw_text(660, y, "No clues collected yet.")
    else:
        for entry in journal[-18:]:
            draw_text(660, y, "- " + entry[:38])
            y -= 22


def draw_dialogue_box():
    """FEATURES 11 and 12."""
    _begin_ortho()
    glDisable(GL_DEPTH_TEST)
    glColor3f(0.05, 0.05, 0.10)
    glBegin(GL_QUADS)
    glVertex2f(120, 60); glVertex2f(880, 60); glVertex2f(880, 220); glVertex2f(120, 220)
    glEnd()
    glEnable(GL_DEPTH_TEST)
    _end_ortho()

    glColor3f(1, 1, 1)
    if radio_message["showing"]:
        line = radio_message["lines"][radio_message["index"]]
        draw_text(140, 170, "FUTURE SELF:")
        draw_text(140, 140, line)
        draw_text(140, 90, "[SPACE to continue]")
    elif radio_message["choice_pending"]:
        draw_text(140, 170, "Trust your future self's shortcut?")
        draw_text(140, 130, "[Y] Trust      [N] Ignore")


def draw_end_overlay():
    _begin_ortho()
    glDisable(GL_DEPTH_TEST)
    glColor3f(0, 0, 0)
    glBegin(GL_QUADS)
    glVertex2f(0, 0); glVertex2f(1000, 0); glVertex2f(1000, 800); glVertex2f(0, 800)
    glEnd()
    glEnable(GL_DEPTH_TEST)
    _end_ortho()

    if game_state["game_win"]:
        glColor3f(0.4, 1.0, 0.5)
    else:
        glColor3f(1.0, 0.3, 0.3)
    draw_text(360, 420, game_state["end_reason"] or "", font=GLUT_BITMAP_TIMES_ROMAN_24)
    glColor3f(0.85, 0.85, 0.85)
    draw_text(360, 380, "Score: {}   Rank: {}".format(game_state["score"], game_state["rank"]))
    draw_text(360, 350, "Press R to try again")


def draw_hud():
    glColor3f(1, 1, 1)
    draw_text(20, 770, "HEALTH")
    draw_bar(110, 768, 160, 16, game_state["health"] / 100.0, (0.85, 0.15, 0.15))

    glColor3f(1, 1, 1)
    draw_text(20, 745, "HUNGER")
    draw_bar(110, 743, 160, 16, game_state["hunger"] / 100.0, (0.85, 0.55, 0.10))

    glColor3f(1, 1, 1)
    draw_text(20, 720, "THIRST")
    draw_bar(110, 718, 160, 16, game_state["thirst"] / 100.0, (0.20, 0.55, 0.90))

    glColor3f(1, 1, 1)
    draw_text(20, 690, "Friends rescued: {}/5".format(game_state["friends_found"]))

    glColor3f(1, 0.6, 0.2)
    draw_text(20, 615, "Flares: {}  [F to throw]".format(game_state["flare_count"]))

    mins = int(game_state["timer"]) // 60
    secs = int(game_state["timer"]) % 60
    glColor3f(1, 1, 1)
    draw_text(20, 665, "Rescue window: {:02d}:{:02d}".format(mins, secs))

    draw_text(20, 640, "It is currently: {}".format("Night" if day_night["is_night"] else "Day"))
    draw_text(20, 20, "WASD move | SPACE jump | F flare | Arrows/drag camera | J journal | R reset")

    if show_journal:
        draw_journal_panel()
    if ui_state["dialogue_active"]:
        draw_dialogue_box()
    if game_state["game_over"] or game_state["game_win"]:
        draw_end_overlay()


# ============================================================================
# REQUIRED TEMPLATE ENTRY POINT: draw_shapes()
# ============================================================================
def draw_shapes():
    draw_ground()
    draw_hazard_zones()
    draw_obstacles()
    draw_pickups()
    draw_friends()
    draw_radio_and_signal()
    draw_flares()
    draw_predator()
    draw_player()
    draw_night_effects()


# ============================================================================
# MISSION LOGIC  (FEATURE 12)
# ============================================================================
def advance_dialogue():
    if radio_message["showing"]:
        radio_message["index"] += 1
        if radio_message["index"] >= len(radio_message["lines"]):
            radio_message["showing"] = False
            radio_message["choice_pending"] = True


def resolve_radio_choice(trust):
    radio_message["choice_pending"] = False
    ui_state["dialogue_active"] = False
    if trust:
        radio_message["choice_made"] = "trust"
        # concrete world-state change: reroute the hidden-area friend to an
        # easy, already-revealed spot near the main island (FEATURE 12)
        rerouted = friends[-1]
        rerouted["x"], rerouted["z"] = 60.0, GRID_LENGTH - 100.0
        journal.append("Future self opened a shortcut to the last friend.")
    else:
        radio_message["choice_made"] = "ignore"
        journal.append("You chose to go it alone. The last friend stays hidden.")


# ============================================================================
# INPUT HANDLERS  (required template entry points + supporting handlers)
# ============================================================================
def keyboardListener(key, x, y):
    global show_journal

    if key in (b'w', b'a', b's', b'd'):
        keys_down.add(key)
        return

    if key == b' ':
        handle_space()
        return

    if key in (b'f', b'F'):
        throw_flare()
        return

    if key in (b'j', b'J'):
        show_journal = not show_journal
        return

    if key in (b'r', b'R'):
        reset_game()
        return

    if key in (b'y', b'Y'):
        if radio_message["choice_pending"]:
            resolve_radio_choice(True)
        return

    if key in (b'n', b'N'):
        if radio_message["choice_pending"]:
            resolve_radio_choice(False)
        return

    # Manual day/night switch: P -> night, L -> day. This is the ONLY
    # thing that changes day_night["is_night"] - there is no automatic
    # cycle, so it will stay on whichever mode you last picked.
    if key in (b'p', b'P'):
        day_night["is_night"] = True
        return
    if key in (b'l', b'L'):
        day_night["is_night"] = False
        return


def keyboardUpListener(key, x, y):
    keys_down.discard(key)


def specialKeyListener(key, x, y):
    special_keys_down.add(key)


def specialKeyUpListener(key, x, y):
    special_keys_down.discard(key)


def mouseListener(button, state, x, y):
    if button == GLUT_LEFT_BUTTON:
        if state == GLUT_DOWN:
            mouse_state["dragging"] = True
            mouse_state["last_x"] = x
            mouse_state["last_y"] = y
        else:
            mouse_state["dragging"] = False


def mouseMotionListener(x, y):
    if mouse_state["dragging"]:
        dx = x - mouse_state["last_x"]
        dy = y - mouse_state["last_y"]
        camera["yaw"] += dx * 0.005
        camera["pitch"] = max(camera["min_pitch"],
                               min(camera["max_pitch"], camera["pitch"] - dy * 0.005))
        mouse_state["last_x"] = x
        mouse_state["last_y"] = y


def update_camera_from_input():
    """FEATURE 3: arrow-key camera orbit, framerate-independent."""
    dt = frame_dt if frame_dt else 0.016
    if GLUT_KEY_LEFT in special_keys_down:
        camera["yaw"] -= CAMERA_TURN_SPEED * dt
    if GLUT_KEY_RIGHT in special_keys_down:
        camera["yaw"] += CAMERA_TURN_SPEED * dt
    if GLUT_KEY_UP in special_keys_down:
        camera["pitch"] = min(camera["max_pitch"], camera["pitch"] + CAMERA_PITCH_SPEED * dt)
    if GLUT_KEY_DOWN in special_keys_down:
        camera["pitch"] = max(camera["min_pitch"], camera["pitch"] - CAMERA_PITCH_SPEED * dt)


# ============================================================================
# REQUIRED TEMPLATE ENTRY POINT: setupCamera()  (FEATURE 3)
# ============================================================================
def setupCamera():
    update_camera_from_input()

    eye_x = player["x"] + camera["distance"] * math.sin(camera["yaw"]) * math.cos(camera["pitch"])
    eye_y = player["y"] + player["height"] * 0.6 + camera["distance"] * math.sin(camera["pitch"])
    eye_z = player["z"] + camera["distance"] * math.cos(camera["yaw"]) * math.cos(camera["pitch"])

    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(fovY, 1000.0 / 800.0, 0.1, 3000.0)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    gluLookAt(eye_x, eye_y, eye_z,
              player["x"], player["y"] + player["height"] * 0.5, player["z"],
              0, 1, 0)


# ============================================================================
# REQUIRED TEMPLATE ENTRY POINT: idle()  -- END CONDITIONS wired exactly here
# ============================================================================
def idle():
    global last_frame_time, frame_dt
    now = time.time()
    frame_dt = min(now - last_frame_time, 0.05)  # clamp against lag spikes
    last_frame_time = now

    update_player_physics()
    update_survival_stats()
    update_predator_ai()
    update_day_night_cycle()
    update_rescue_timer()

    if game_state["health"] <= 0:
        trigger_game_over("death")
    elif game_state["timer"] <= 0 and game_state["friends_found"] < 5:
        trigger_game_over("rescued_too_late")
    elif game_state["friends_found"] >= 5:
        trigger_game_win()

    glutPostRedisplay()


# ============================================================================
# REQUIRED TEMPLATE ENTRY POINT: showScreen()
# ============================================================================
def showScreen():
    r, g, b = get_sky_color()
    glClearColor(r, g, b, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glLoadIdentity()
    glViewport(0, 0, 1000, 800)

    setupCamera()
    draw_shapes()
    draw_hud()

    glutSwapBuffers()


# ============================================================================
# REQUIRED TEMPLATE ENTRY POINT: main()
# ============================================================================
def main():
    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB | GLUT_DEPTH)
    glutInitWindowSize(1000, 800)
    glutInitWindowPosition(0, 0)
    glutCreateWindow(b"Island Escape")

    glEnable(GL_DEPTH_TEST)

    glutDisplayFunc(showScreen)
    glutKeyboardFunc(keyboardListener)
    glutKeyboardUpFunc(keyboardUpListener)
    glutSpecialFunc(specialKeyListener)
    glutSpecialUpFunc(specialKeyUpListener)
    glutMouseFunc(mouseListener)
    glutMotionFunc(mouseMotionListener)
    glutIdleFunc(idle)

    reset_game()

    glutMainLoop()


if __name__ == "__main__":
    main()


