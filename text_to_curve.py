# ==============================================================
#  Text‑to‑Curve UI for Autodesk Maya
#  Author:  Dawid Cencora – July 2025
#  Maya 2018+  |  Python 2.7/3.x compatible
# ==============================================================

import maya.cmds as cmds

# ----------------------------------------
# Globals (kept minimal and namespaced)
# ----------------------------------------
_CURVE_UI_WIN   = 'textCurveWin'
_CURVE_UI_FONT  = {'family': None}       # will hold the chosen font family
_LINE_SPACING   = 1.3                    # vertical offset (in Maya units) between lines

# ----------------------------------------
# Core function – creates curves from one line of text
# ----------------------------------------
def create_curve_line(txt, font_family):
    """
    Creates one line of NURBS curves from `txt` using `font_family`.
    Returns the top‑level transform Maya gives us.
    """
    if not txt:
        cmds.warning('No text supplied; skipping.')
        return None

    # textCurves – ch=0 prevents extraneous construction history
    grp = cmds.textCurves(ch=0, f=font_family if font_family else "Arial|w400|r", t=txt)[0]

    # Freeze + center pivot for tidy transforms
    cmds.makeIdentity(grp, apply=True, t=True, r=True, s=True, n=False)
    cmds.xform(grp, centerPivots=True)

    return grp

# ----------------------------------------
# Convenience: wrap font selection around the OS font dialog
# ----------------------------------------
def pick_font(*_):
    """Opens the system font dialog and stores result."""
    try:
        font_info = cmds.fontDialog()
        # fontDialog returns family, style, size; you only need the family name
        family = font_info.split(',')[0]
        _CURVE_UI_FONT['family'] = family
        cmds.text('fontLabel', e=True, l='Font: {}'.format(family))
    except RuntimeError:
        cmds.warning('Font selection cancelled.')

# ----------------------------------------
# Main callback that reads UI, creates curves, and lays out multi‑line text
# ----------------------------------------
def create_curves_from_ui(*_):
    txt = cmds.scrollField('textScroll', q=True, tx=True).rstrip('\n')
    if not txt:
        cmds.warning('Please enter some text first.')
        return

    font = _CURVE_UI_FONT['family'] or 'Arial|w400|r'
    all_groups = []
    y_offset   = 0.0

    # Build each line separately so we can stack them with spacing
    for line in reversed(txt.splitlines() or ['']):      # bottom‑up for natural reading order
        grp = create_curve_line(line, font)
        if grp:
            cmds.move(0, y_offset, 0, grp, r=True)
            # measure height for next offset
            bbox   = cmds.exactWorldBoundingBox(grp)
            height = bbox[4] - bbox[1]   # Y‑size
            y_offset += height * _LINE_SPACING
            all_groups.append(grp)

    # Group all lines together
    if all_groups:
        master = cmds.group(all_groups, n='{}Text_CURVES_GRP'.format(font.split('|')[0]))
        cmds.xform(master, centerPivots=True)
        cmds.select(master)
        print('Created curve group:', master)

# ----------------------------------------
# Build the UI
# ----------------------------------------
def show_text_curve_ui():
    if cmds.window(_CURVE_UI_WIN, exists=True):
        cmds.deleteUI(_CURVE_UI_WIN)

    cmds.window(_CURVE_UI_WIN, title='Text → Curves', sizeable=False)
    cmds.columnLayout(adj=True, rs=8)

    cmds.text(label='Enter text (multi‑line supported):')
    cmds.scrollField('textScroll', wordWrap=False, h=80, tx='Hello Maya')

    cmds.separator(h=8, style='in')

    # Font selector row
    cmds.rowLayout(nc=2, adj=2, cw2=(60, 160))
    cmds.text('fontLabel', l='Font: Default', align='left')
    cmds.button(l='Pick Font…', c=pick_font, h=25)
    cmds.setParent('..')

    cmds.separator(h=8, style='none')

    # Action button
    cmds.button(l='Create Curves', bgc=(0.4, 0.8, 0.4), h=35,
                c=create_curves_from_ui, ann='Generate NURBS curves from the text above.')

    cmds.showWindow(_CURVE_UI_WIN)

# ----------------------------------------
# Run it
# ----------------------------------------
show_text_curve_ui()
