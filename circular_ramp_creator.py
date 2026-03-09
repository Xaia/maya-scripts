"""
Circular Ramp Creator for Maya
Creates a circular ramp texture node with alternating black/white rings.
Supports color randomization and thickness (band width) randomization.

FIX NOTES:
  - Maya ramp colorEntryList does NOT have a per-entry .interp attribute.
    Interpolation is a single node-level attribute only. Attempting to set
    per-entry interp was silently erroring and aborting the creation loop,
    which left only one colour entry in the ramp.
"""

import random
import maya.cmds as cmds


# ─────────────────────────────────────────────────────────────────────────────
# Core builder
# ─────────────────────────────────────────────────────────────────────────────

def create_circular_ramp(
    num_circles=10,
    interp_value=0,
    color_randomize=0.0,
    thickness_randomize=0.0,
    assign_to_selection=False,
    seed=42,
):
    """
    Creates a circular ramp with alternating dark/light bands.

    Args:
        num_circles        : Number of black+white circle pairs
        interp_value       : Maya ramp interpolation (0=None, 1=Linear, 2=Smooth, 3=Spline)
        color_randomize    : 0-1  how much brightness (and optionally hue) is randomised
        thickness_randomize: 0-1  how much each band's width deviates from uniform
        assign_to_selection: Assign via Lambert to selected meshes
        seed               : Int seed for reproducible randomness
    """
    rng = random.Random(seed)

    # ── Build band widths (with optional thickness variance) ──────────────────
    num_bands     = num_circles * 2          # dark + light per circle
    uniform_w     = 1.0 / num_bands

    raw_widths = []
    for _ in range(num_bands):
        delta = (rng.random() - 0.5) * 2.0 * thickness_randomize * uniform_w
        raw_widths.append(max(uniform_w + delta, 1e-4))

    # Normalise so positions span exactly [0, 1]
    total  = sum(raw_widths)
    widths = [w / total for w in raw_widths]

    # Convert widths → start positions for each band
    positions = []
    cursor = 0.0
    for w in widths:
        positions.append(cursor)
        cursor += w

    # ── Color helper ──────────────────────────────────────────────────────────
    def make_color(is_dark):
        base = 0.0 if is_dark else 1.0

        if color_randomize <= 0.0:
            return (base, base, base)

        # Pull the value toward mid-grey proportionally
        jitter = rng.random() * color_randomize
        v = (base + jitter) if is_dark else (base - jitter)
        v = max(0.0, min(1.0, v))

        # Above 0.5 also add a random hue tint
        if color_randomize > 0.5:
            t = (color_randomize - 0.5) * 2.0
            r = max(0.0, min(1.0, v + (rng.random() - 0.5) * t * 0.7))
            g = max(0.0, min(1.0, v + (rng.random() - 0.5) * t * 0.7))
            b = max(0.0, min(1.0, v + (rng.random() - 0.5) * t * 0.7))
            return (r, g, b)

        return (v, v, v)

    # ── Create ramp node ──────────────────────────────────────────────────────
    ramp_node = cmds.shadingNode("ramp", asTexture=True, name="circularRamp_#")

    # type 4 = Circular (concentric rings); interpolation is NODE-LEVEL only
    cmds.setAttr("{}.type".format(ramp_node), 4)
    cmds.setAttr("{}.interpolation".format(ramp_node), interp_value)

    # Remove every default entry Maya created
    defaults = cmds.getAttr("{}.colorEntryList".format(ramp_node), multiIndices=True)
    if defaults:
        for idx in defaults:
            cmds.removeMultiInstance(
                "{}.colorEntryList[{}]".format(ramp_node, idx), b=True
            )

    # Write one entry per band — no .interp per entry, that attribute does not exist
    for i, pos in enumerate(positions):
        col = make_color(i % 2 == 0)          # even = dark, odd = light
        cmds.setAttr("{}.colorEntryList[{}].position".format(ramp_node, i), pos)
        cmds.setAttr(
            "{}.colorEntryList[{}].color".format(ramp_node, i),
            col[0], col[1], col[2],
            type="double3",
        )

    # Closing entry at 1.0 so the outermost ring has a clean edge
    close_col = make_color(num_bands % 2 == 0)
    cmds.setAttr(
        "{}.colorEntryList[{}].position".format(ramp_node, num_bands), 1.0
    )
    cmds.setAttr(
        "{}.colorEntryList[{}].color".format(ramp_node, num_bands),
        close_col[0], close_col[1], close_col[2],
        type="double3",
    )

    # ── place2dTexture ────────────────────────────────────────────────────────
    p2d = cmds.shadingNode("place2dTexture", asUtility=True)
    cmds.connectAttr("{}.outUV".format(p2d),           "{}.uv".format(ramp_node),           force=True)
    cmds.connectAttr("{}.outUvFilterSize".format(p2d), "{}.uvFilterSize".format(ramp_node), force=True)

    # ── Optional Lambert assignment ───────────────────────────────────────────
    if assign_to_selection:
        sel = cmds.ls(selection=True, transforms=True)
        if sel:
            shader = cmds.shadingNode("lambert", asShader=True, name="circularRampShader_#")
            sg     = cmds.sets(renderable=True, noSurfaceShader=True,
                               empty=True, name="circularRampSG_#")
            cmds.connectAttr("{}.outColor".format(shader), "{}.surfaceShader".format(sg), force=True)
            cmds.connectAttr("{}.outColor".format(ramp_node), "{}.color".format(shader), force=True)
            cmds.sets(sel, edit=True, forceElement=sg)
            print("[Circular Ramp] Assigned '{}' to: {}".format(ramp_node, sel))
        else:
            cmds.warning("[Circular Ramp] No mesh selected – shader NOT assigned.")

    cmds.select(ramp_node)
    print("[Circular Ramp] '{}' created — {} circles, {} entries".format(
        ramp_node, num_circles, num_bands + 1))
    return ramp_node


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────
WINDOW_ID   = "circularRampCreatorWin"
_INTERP_MAP = {1: 0, 2: 1, 3: 2, 4: 3}   # optionMenu (1-based) → Maya interp value


def _slider(label, name, annotation=""):
    return cmds.floatSliderGrp(
        name,
        label=label,
        field=True,
        minValue=0.0, maxValue=1.0, value=0.0,
        columnWidth3=(158, 52, 82),
        columnAlign3=("right", "left", "left"),
        precision=2,
        annotation=annotation,
    )


def build_ui():
    if cmds.window(WINDOW_ID, exists=True):
        cmds.deleteUI(WINDOW_ID)

    cmds.window(
        WINDOW_ID,
        title="Circular Ramp Creator",
        widthHeight=(370, 355),
        sizeable=False,
    )
    col = cmds.columnLayout(adjustableColumn=True, rowSpacing=5, columnOffset=("both", 12))
    cmds.separator(height=10, style="none")

    # Header
    cmds.text(label="Circular Ramp Creator", font="boldLabelFont", align="center")
    cmds.text(label="Alternating black & white concentric rings", align="center")
    cmds.separator(height=8)

    # ── Circles count ─────────────────────────────────────────────────────────
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(160, 120),
                   columnAlign2=("right", "left"), adjustableColumn=2)
    cmds.text(label="Number of circles :  ", align="right")
    circles_field = cmds.intField("circlesField", value=10, minValue=1, maxValue=500,
                                  width=60, annotation="Black+white ring pairs")
    cmds.setParent("..")

    # ── Interpolation ─────────────────────────────────────────────────────────
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(160, 160),
                   columnAlign2=("right", "left"), adjustableColumn=2)
    cmds.text(label="Interpolation :  ", align="right")
    interp_menu = cmds.optionMenu("interpMenu",
                                  annotation="How colours blend between stops")
    cmds.menuItem(label="None  (sharp edges)")
    cmds.menuItem(label="Linear  (soft blend)")
    cmds.menuItem(label="Smooth")
    cmds.menuItem(label="Spline")
    cmds.setParent("..")

    # ── Color Randomize ───────────────────────────────────────────────────────
    cmds.separator(height=4, style="in")
    cmds.text(label="  COLOR RANDOMIZE", font="smallBoldLabelFont", align="left")
    cmds.text(
        label="  Shifts each ring away from pure black/white.\n"
              "  Above 0.5 also adds random hue tints.",
        align="left", font="smallPlainLabelFont",
    )
    color_rand_ctrl = _slider("Amount :  ", "colorRandSlider",
                              "0 = pure B&W  |  1 = fully randomised brightness + colour")

    # Seed row
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(160, 62, 76),
                   columnAlign3=("right", "left", "left"), adjustableColumn=3)
    cmds.text(label="Seed :  ", align="right")
    seed_field = cmds.intField("seedField", value=42, minValue=0, maxValue=99999,
                               width=62, annotation="Same seed = same result")
    cmds.button(label="New seed", width=72,
                command=lambda *_: cmds.intField(
                    seed_field, edit=True, value=random.randint(0, 99999)),
                annotation="Pick a fresh random seed")
    cmds.setParent("..")

    # ── Thickness Randomize ───────────────────────────────────────────────────
    cmds.separator(height=4, style="in")
    cmds.text(label="  THICKNESS RANDOMIZE", font="smallBoldLabelFont", align="left")
    cmds.text(
        label="  Varies each ring's width. Uses the same seed.",
        align="left", font="smallPlainLabelFont",
    )
    thick_rand_ctrl = _slider("Amount :  ", "thickRandSlider",
                              "0 = all rings equal  |  1 = maximum width variation")

    # ── Assign to selection ───────────────────────────────────────────────────
    cmds.separator(height=4, style="in")
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(160, 190),
                   columnAlign2=("right", "left"), adjustableColumn=2)
    cmds.text(label="Assign to selection :  ", align="right")
    assign_check = cmds.checkBox("assignCheck", label="(creates Lambert shader)",
                                 value=False,
                                 annotation="Assign ramp to selected meshes")
    cmds.setParent("..")

    cmds.separator(height=6, style="none")

    # ── Create ────────────────────────────────────────────────────────────────
    cmds.button(
        label="Create Ramp", height=40,
        backgroundColor=(0.22, 0.52, 0.22),
        command=lambda *_: on_create(
            circles_field, interp_menu,
            color_rand_ctrl, thick_rand_ctrl,
            seed_field, assign_check,
        ),
    )
    cmds.separator(height=10, style="none")
    cmds.showWindow(WINDOW_ID)


def on_create(circles_field, interp_menu, color_rand_ctrl,
              thick_rand_ctrl, seed_field, assign_check):
    num_circles = cmds.intField(circles_field,        query=True, value=True)
    interp_idx  = cmds.optionMenu(interp_menu,        query=True, select=True)
    color_rand  = cmds.floatSliderGrp(color_rand_ctrl, query=True, value=True)
    thick_rand  = cmds.floatSliderGrp(thick_rand_ctrl, query=True, value=True)
    seed        = cmds.intField(seed_field,            query=True, value=True)
    assign      = cmds.checkBox(assign_check,          query=True, value=True)

    ramp = create_circular_ramp(
        num_circles=num_circles,
        interp_value=_INTERP_MAP.get(interp_idx, 0),
        color_randomize=color_rand,
        thickness_randomize=thick_rand,
        assign_to_selection=assign,
        seed=seed,
    )

    cmds.inViewMessage(
        assistMessage=(
            "<hl>Circular Ramp</hl> '{}' — {} circles | "
            "color {:.2f} | thickness {:.2f} | seed {}".format(
                ramp, num_circles, color_rand, thick_rand, seed
            )
        ),
        position="midCenter", fade=True,
    )


# ── Entry point ───────────────────────────────────────────────────────────────
build_ui()
