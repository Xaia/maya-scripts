"""Deferred UI-only bootstrap; does not replace the user's startup script."""
import maya.cmds as cmds
import maya.utils

if not cmds.about(batch=True):
    def _xaia_startup():
        try:
            import xaia_tools
            xaia_tools.show_menu()
        except Exception as exc:
            cmds.warning("Xaia Tools startup: {}".format(exc))
    maya.utils.executeDeferred(_xaia_startup)
