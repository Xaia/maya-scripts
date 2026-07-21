# Arnold Stand-In and Texture Path Resolver v1.1
# Maya Python 3
#
# Tab 1: Relinks aiStandIn.dso paths by matching .ass filenames.
# Tab 2: Rewrites texture paths inside referenced .ass / .ass.gz files.
#
# Texture changes are matched by filename. Before any ASS file is modified,
# a timestamped backup is created next to the original file.

import gzip
import os
import re
import shutil
import tempfile
from datetime import datetime

import maya.cmds as cmds


VERSION = "1.1"
WINDOW_NAME = "aiStandInPathResolverWindow"

ASS_EXTENSIONS = (".ass", ".ass.gz")
TEXTURE_EXTENSIONS = (
    ".tx",
    ".tex",
    ".exr",
    ".tif",
    ".tiff",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tga",
    ".hdr",
    ".pic",
    ".iff",
    ".psd",
    ".rat",
)

# Matches a normal ASS parameter line containing one quoted string value.
# Example:     filename "D:/textures/rock_basecolor.<UDIM>.tx"
ASS_STRING_PARAMETER_RE = re.compile(
    r'^(?P<prefix>\s*(?P<parameter>[A-Za-z_][A-Za-z0-9_:.\-]*)\s+)'
    r'"(?P<value>[^"\r\n]+)"(?P<suffix>[^\r\n]*)$',
    re.MULTILINE,
)

# These ASS string parameters are not texture file references.
SKIPPED_ASS_PARAMETERS = {
    "name",
    "shader",
    "node",
    "operator",
    "color_space",
    "color_manager",
    "dso",
}


class ArnoldPathResolver(object):

    def __init__(self):
        # Stand-in tab widgets
        self.ass_folder_field = None
        self.ass_recursive_checkbox = None
        self.ass_selected_only_checkbox = None
        self.ass_missing_only_checkbox = None
        self.ass_log_field = None

        # Texture tab widgets
        self.texture_folder_field = None
        self.texture_recursive_checkbox = None
        self.texture_selected_only_checkbox = None
        self.texture_missing_only_checkbox = None
        self.texture_log_field = None

    # ------------------------------------------------------------------ UI --

    def show(self):
        if cmds.window(WINDOW_NAME, exists=True):
            cmds.deleteUI(WINDOW_NAME, window=True)

        window = cmds.window(
            WINDOW_NAME,
            title="Arnold Path Resolver v1.1",
            widthHeight=(720, 570),
            sizeable=True,
        )

        # Maya may resolve short UI names relative to whichever layout is
        # currently active. Version 1.1 uses named controls and absolute paths
        # throughout, so a rowLayout cannot accidentally become the parent of
        # a later tab control.
        root_name = "arpRootLayout"
        root = "{}|{}".format(WINDOW_NAME, root_name)
        cmds.columnLayout(
            root_name,
            adjustableColumn=True,
            rowSpacing=6,
            columnAttach=("both", 10),
            parent=window,
        )

        cmds.text(
            "arpHeaderText",
            label="Arnold Path Resolver v1.1  |  Relink stand-ins and repair ASS texture paths",
            align="left",
            height=28,
            parent=root,
        )

        tabs_name = "arpTabs"
        tabs = "{}|{}".format(root, tabs_name)
        cmds.tabLayout(
            tabs_name,
            innerMarginWidth=8,
            innerMarginHeight=8,
            parent=root,
        )

        standin_tab = self._build_standin_tab(tabs)
        texture_tab = self._build_texture_tab(tabs)

        cmds.tabLayout(
            tabs,
            edit=True,
            tabLabel=[
                (standin_tab, "Stand-Ins"),
                (texture_tab, "Textures"),
            ],
        )

        cmds.showWindow(window)

    def _build_standin_tab(self, parent):
        layout_name = "arpStandinTab"
        layout = "{}|{}".format(parent, layout_name)
        cmds.columnLayout(
            layout_name,
            adjustableColumn=True,
            rowSpacing=8,
            parent=parent,
        )

        cmds.text(
            "arpStandinInfo",
            label="Find the same .ass filenames in a new folder and update aiStandIn.dso paths.",
            align="left",
            height=24,
            parent=layout,
        )

        cmds.separator("arpStandinSeparatorTop", style="in", height=8, parent=layout)
        cmds.text(
            "arpAssFolderLabel",
            label="New ASS Folder",
            align="left",
            font="boldLabelFont",
            parent=layout,
        )

        folder_row_name = "arpAssFolderRow"
        folder_row = "{}|{}".format(layout, folder_row_name)
        cmds.rowLayout(
            folder_row_name,
            numberOfColumns=2,
            adjustableColumn=1,
            columnWidth2=(580, 100),
            columnAttach=[(1, "both", 0), (2, "left", 6)],
            parent=layout,
        )

        field_name = "arpAssFolderField"
        self.ass_folder_field = "{}|{}".format(folder_row, field_name)
        cmds.textField(
            field_name,
            placeholderText="Choose the folder containing the relocated .ass files...",
            parent=folder_row,
        )
        cmds.button(
            "arpAssBrowseButton",
            label="Browse",
            width=100,
            command=self.browse_ass_folder,
            parent=folder_row,
        )

        checkbox_name = "arpAssRecursiveCheck"
        self.ass_recursive_checkbox = "{}|{}".format(layout, checkbox_name)
        cmds.checkBox(
            checkbox_name,
            label="Search subfolders",
            value=True,
            parent=layout,
        )

        checkbox_name = "arpAssSelectedOnlyCheck"
        self.ass_selected_only_checkbox = "{}|{}".format(layout, checkbox_name)
        cmds.checkBox(
            checkbox_name,
            label="Selected stand-ins only",
            value=False,
            parent=layout,
        )

        checkbox_name = "arpAssMissingOnlyCheck"
        self.ass_missing_only_checkbox = "{}|{}".format(layout, checkbox_name)
        cmds.checkBox(
            checkbox_name,
            label="Only replace stand-in paths that do not currently exist",
            value=False,
            parent=layout,
        )

        cmds.separator("arpStandinSeparatorButtons", style="in", height=10, parent=layout)

        button_row_name = "arpAssButtonRow"
        button_row = "{}|{}".format(layout, button_row_name)
        cmds.rowLayout(
            button_row_name,
            numberOfColumns=2,
            adjustableColumn=1,
            columnWidth2=(335, 335),
            columnAttach=[(1, "both", 0), (2, "both", 6)],
            parent=layout,
        )
        cmds.button(
            "arpAssPreviewButton",
            label="Preview Stand-In Changes",
            height=36,
            command=lambda *_: self.resolve_standin_paths(apply_changes=False),
            parent=button_row,
        )
        cmds.button(
            "arpAssResolveButton",
            label="Resolve Stand-In Paths",
            height=36,
            command=lambda *_: self.resolve_standin_paths(apply_changes=True),
            parent=button_row,
        )

        cmds.text(
            "arpAssResultsLabel",
            label="Results",
            align="left",
            font="boldLabelFont",
            parent=layout,
        )

        log_name = "arpAssLog"
        self.ass_log_field = "{}|{}".format(layout, log_name)
        cmds.scrollField(
            log_name,
            editable=False,
            wordWrap=False,
            height=345,
            text="",
            parent=layout,
        )

        return layout

    def _build_texture_tab(self, parent):
        layout_name = "arpTextureTab"
        layout = "{}|{}".format(parent, layout_name)
        cmds.columnLayout(
            layout_name,
            adjustableColumn=True,
            rowSpacing=8,
            parent=parent,
        )

        cmds.text(
            "arpTextureInfo",
            label=(
                "Find matching texture filenames and rewrite their paths inside the "
                ".ass files referenced by scene stand-ins."
            ),
            align="left",
            height=24,
            parent=layout,
        )

        cmds.separator("arpTextureSeparatorTop", style="in", height=8, parent=layout)
        cmds.text(
            "arpTextureFolderLabel",
            label="New Texture Folder",
            align="left",
            font="boldLabelFont",
            parent=layout,
        )

        folder_row_name = "arpTextureFolderRow"
        folder_row = "{}|{}".format(layout, folder_row_name)
        cmds.rowLayout(
            folder_row_name,
            numberOfColumns=2,
            adjustableColumn=1,
            columnWidth2=(580, 100),
            columnAttach=[(1, "both", 0), (2, "left", 6)],
            parent=layout,
        )

        field_name = "arpTextureFolderField"
        self.texture_folder_field = "{}|{}".format(folder_row, field_name)
        cmds.textField(
            field_name,
            placeholderText="Choose the folder containing the relocated textures...",
            parent=folder_row,
        )
        cmds.button(
            "arpTextureBrowseButton",
            label="Browse",
            width=100,
            command=self.browse_texture_folder,
            parent=folder_row,
        )

        checkbox_name = "arpTextureRecursiveCheck"
        self.texture_recursive_checkbox = "{}|{}".format(layout, checkbox_name)
        cmds.checkBox(
            checkbox_name,
            label="Search texture subfolders",
            value=True,
            parent=layout,
        )

        checkbox_name = "arpTextureSelectedOnlyCheck"
        self.texture_selected_only_checkbox = "{}|{}".format(layout, checkbox_name)
        cmds.checkBox(
            checkbox_name,
            label="Use selected stand-ins only",
            value=False,
            parent=layout,
        )

        checkbox_name = "arpTextureMissingOnlyCheck"
        self.texture_missing_only_checkbox = "{}|{}".format(layout, checkbox_name)
        cmds.checkBox(
            checkbox_name,
            label="Only replace texture paths that do not currently exist",
            value=False,
            parent=layout,
        )

        cmds.text(
            "arpTextureBackupInfo",
            label=(
                "A timestamped backup is always created next to every modified "
                ".ass or .ass.gz file."
            ),
            align="left",
            parent=layout,
        )

        cmds.separator("arpTextureSeparatorButtons", style="in", height=10, parent=layout)

        button_row_name = "arpTextureButtonRow"
        button_row = "{}|{}".format(layout, button_row_name)
        cmds.rowLayout(
            button_row_name,
            numberOfColumns=2,
            adjustableColumn=1,
            columnWidth2=(335, 335),
            columnAttach=[(1, "both", 0), (2, "both", 6)],
            parent=layout,
        )
        cmds.button(
            "arpTexturePreviewButton",
            label="Preview Texture Changes",
            height=36,
            command=lambda *_: self.resolve_texture_paths(apply_changes=False),
            parent=button_row,
        )
        cmds.button(
            "arpTextureReplaceButton",
            label="Replace Texture Paths",
            height=36,
            command=lambda *_: self.resolve_texture_paths(apply_changes=True),
            parent=button_row,
        )

        cmds.text(
            "arpTextureResultsLabel",
            label="Results",
            align="left",
            font="boldLabelFont",
            parent=layout,
        )

        log_name = "arpTextureLog"
        self.texture_log_field = "{}|{}".format(layout, log_name)
        cmds.scrollField(
            log_name,
            editable=False,
            wordWrap=False,
            height=315,
            text="",
            parent=layout,
        )

        return layout

    def browse_ass_folder(self, *_):
        result = cmds.fileDialog2(
            dialogStyle=2,
            fileMode=3,
            caption="Choose ASS Search Folder",
        )
        if result:
            cmds.textField(
                self.ass_folder_field,
                edit=True,
                text=self.normalize_path(result[0]),
            )

    def browse_texture_folder(self, *_):
        result = cmds.fileDialog2(
            dialogStyle=2,
            fileMode=3,
            caption="Choose Texture Search Folder",
        )
        if result:
            cmds.textField(
                self.texture_folder_field,
                edit=True,
                text=self.normalize_path(result[0]),
            )

    # ---------------------------------------------------------- Scene nodes --

    def get_standins(self, selected_only=False):
        if not selected_only:
            return sorted(set(cmds.ls(type="aiStandIn", long=True) or []))

        selection = cmds.ls(selection=True, long=True) or []
        standins = set()

        for node in selection:
            try:
                if cmds.nodeType(node) == "aiStandIn":
                    standins.add(node)
            except RuntimeError:
                continue

            shapes = cmds.listRelatives(
                node,
                shapes=True,
                fullPath=True,
            ) or []
            descendants = cmds.listRelatives(
                node,
                allDescendents=True,
                shapes=True,
                fullPath=True,
            ) or []

            for shape in shapes + descendants:
                try:
                    if cmds.nodeType(shape) == "aiStandIn":
                        standins.add(shape)
                except RuntimeError:
                    pass

        return sorted(standins)

    def collect_referenced_ass_files(self, standins):
        ass_files = set()
        unresolved = []

        for standin in standins:
            attribute = standin + ".dso"
            if not cmds.objExists(attribute):
                unresolved.append((standin, "Missing dso attribute"))
                continue

            dso_path = str(cmds.getAttr(attribute) or "").strip()
            if not dso_path:
                unresolved.append((standin, "Empty dso path"))
                continue

            expanded_files = self.expand_file_reference(dso_path, ASS_EXTENSIONS)
            if not expanded_files:
                unresolved.append((standin, dso_path))
                continue

            ass_files.update(expanded_files)

        return sorted(ass_files), unresolved

    # ------------------------------------------------------ Stand-in relink --

    def resolve_standin_paths(self, apply_changes=False):
        self.clear_log(self.ass_log_field)

        root_folder = cmds.textField(
            self.ass_folder_field,
            query=True,
            text=True,
        ).strip()

        root_folder = self.validate_folder(root_folder, self.ass_log_field)
        if not root_folder:
            return

        recursive = cmds.checkBox(
            self.ass_recursive_checkbox,
            query=True,
            value=True,
        )
        selected_only = cmds.checkBox(
            self.ass_selected_only_checkbox,
            query=True,
            value=True,
        )
        missing_only = cmds.checkBox(
            self.ass_missing_only_checkbox,
            query=True,
            value=True,
        )

        standins = self.get_standins(selected_only)
        if not standins:
            message = (
                "No selected Arnold stand-ins found."
                if selected_only
                else "No Arnold stand-ins found in the scene."
            )
            cmds.warning(message)
            self.log(self.ass_log_field, message)
            return

        ass_files = self.scan_files(root_folder, ASS_EXTENSIONS, recursive)
        if not ass_files:
            cmds.warning("No .ass or .ass.gz files were found.")
            self.log(self.ass_log_field, "No .ass or .ass.gz files were found.")
            return

        filename_index = self.build_filename_index(ass_files)

        self.log(self.ass_log_field, "Scanning: {}".format(root_folder))
        self.log(self.ass_log_field, "Found {} ASS file(s).".format(len(ass_files)))
        self.log(self.ass_log_field, "Checking {} stand-in node(s).".format(len(standins)))
        self.log(self.ass_log_field, "=" * 88)

        updated = 0
        matched = 0
        unchanged = 0
        not_found = 0
        ambiguous = 0
        invalid = 0

        if apply_changes:
            cmds.undoInfo(openChunk=True, chunkName="Resolve Arnold Stand-In Paths")

        try:
            for standin in standins:
                attribute = standin + ".dso"
                if not cmds.objExists(attribute):
                    self._log_item(self.ass_log_field, "INVALID", standin, "Missing dso attribute")
                    invalid += 1
                    continue

                old_path = str(cmds.getAttr(attribute) or "").strip()
                if not old_path:
                    self._log_item(self.ass_log_field, "EMPTY", standin, "No ASS path to match")
                    invalid += 1
                    continue

                if missing_only and self.file_reference_exists(old_path, ASS_EXTENSIONS):
                    self._log_item(self.ass_log_field, "SKIPPED", standin, old_path)
                    unchanged += 1
                    continue

                matches, tokenized = self.find_relocated_path(
                    old_path,
                    ass_files,
                    filename_index,
                )

                if not matches:
                    self._log_item(self.ass_log_field, "NOT FOUND", standin, old_path)
                    not_found += 1
                    continue

                if len(matches) > 1:
                    self.log(self.ass_log_field, "")
                    self.log(self.ass_log_field, "[AMBIGUOUS] {}".format(standin))
                    self.log(self.ass_log_field, "  {}".format(old_path))
                    for match in matches:
                        self.log(self.ass_log_field, "    {}".format(match))
                    ambiguous += 1
                    continue

                new_path = matches[0]
                if self.paths_equal(old_path, new_path):
                    self._log_item(self.ass_log_field, "UNCHANGED", standin, old_path)
                    unchanged += 1
                    continue

                matched += 1
                self.log(self.ass_log_field, "")
                self.log(self.ass_log_field, "[MATCH] {}".format(standin))
                self.log(self.ass_log_field, "  Old: {}".format(old_path))
                self.log(self.ass_log_field, "  New: {}".format(new_path))
                if tokenized:
                    self.log(self.ass_log_field, "  Sequence token preserved")

                if apply_changes:
                    try:
                        cmds.setAttr(attribute, new_path, type="string")
                        updated += 1
                        self.log(self.ass_log_field, "  Status: Updated")
                    except RuntimeError as error:
                        invalid += 1
                        self.log(self.ass_log_field, "  Status: Failed")
                        self.log(self.ass_log_field, "  Error: {}".format(error))
        finally:
            if apply_changes:
                cmds.undoInfo(closeChunk=True)

        self.log(self.ass_log_field, "")
        self.log(self.ass_log_field, "=" * 88)
        self.log(
            self.ass_log_field,
            "Updated: {}".format(updated) if apply_changes else "Would update: {}".format(matched),
        )
        self.log(self.ass_log_field, "Unchanged: {}".format(unchanged))
        self.log(self.ass_log_field, "Not found: {}".format(not_found))
        self.log(self.ass_log_field, "Ambiguous: {}".format(ambiguous))
        self.log(self.ass_log_field, "Invalid: {}".format(invalid))

        message = (
            "Updated {} Arnold stand-in path(s).".format(updated)
            if apply_changes
            else "{} stand-in path(s) can be updated.".format(matched)
        )
        cmds.inViewMessage(amg=message, position="topCenter", fade=True)

    # ------------------------------------------------------- Texture relink --

    def resolve_texture_paths(self, apply_changes=False):
        self.clear_log(self.texture_log_field)

        texture_root = cmds.textField(
            self.texture_folder_field,
            query=True,
            text=True,
        ).strip()

        texture_root = self.validate_folder(texture_root, self.texture_log_field)
        if not texture_root:
            return

        recursive = cmds.checkBox(
            self.texture_recursive_checkbox,
            query=True,
            value=True,
        )
        selected_only = cmds.checkBox(
            self.texture_selected_only_checkbox,
            query=True,
            value=True,
        )
        missing_only = cmds.checkBox(
            self.texture_missing_only_checkbox,
            query=True,
            value=True,
        )

        standins = self.get_standins(selected_only)
        if not standins:
            message = (
                "No selected Arnold stand-ins found."
                if selected_only
                else "No Arnold stand-ins found in the scene."
            )
            cmds.warning(message)
            self.log(self.texture_log_field, message)
            return

        texture_files = self.scan_files(
            texture_root,
            TEXTURE_EXTENSIONS,
            recursive,
        )
        if not texture_files:
            cmds.warning("No supported texture files were found.")
            self.log(self.texture_log_field, "No supported texture files were found.")
            return

        texture_index = self.build_filename_index(texture_files)
        ass_files, unresolved_standins = self.collect_referenced_ass_files(standins)

        self.log(self.texture_log_field, "Texture search folder: {}".format(texture_root))
        self.log(self.texture_log_field, "Found {} texture file(s).".format(len(texture_files)))
        self.log(self.texture_log_field, "Found {} referenced ASS file(s).".format(len(ass_files)))

        if unresolved_standins:
            self.log(self.texture_log_field, "")
            self.log(self.texture_log_field, "Unresolved stand-in references:")
            for node, value in unresolved_standins:
                self.log(self.texture_log_field, "  {} -> {}".format(node, value))

        if not ass_files:
            cmds.warning("No readable .ass files were found from the scene stand-ins.")
            self.log(
                self.texture_log_field,
                "No readable .ass or .ass.gz files were found from the scene stand-ins.",
            )
            return

        self.log(self.texture_log_field, "=" * 88)

        changed_files = 0
        replacement_count = 0
        not_found_count = 0
        ambiguous_count = 0
        skipped_existing_count = 0
        failed_files = 0
        backup_paths = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for ass_path in ass_files:
            self.log(self.texture_log_field, "")
            self.log(self.texture_log_field, "ASS: {}".format(ass_path))

            try:
                original_text = self.read_ass_text(ass_path)
            except Exception as error:
                failed_files += 1
                self.log(self.texture_log_field, "  [FAILED TO READ] {}".format(error))
                continue

            result = self.repath_ass_textures(
                original_text,
                texture_files,
                texture_index,
                missing_only,
            )

            replacements = result["replacements"]
            not_found = result["not_found"]
            ambiguous = result["ambiguous"]
            skipped_existing = result["skipped_existing"]

            for old_path, new_path in replacements:
                self.log(self.texture_log_field, "  [MATCH]")
                self.log(self.texture_log_field, "    Old: {}".format(old_path))
                self.log(self.texture_log_field, "    New: {}".format(new_path))

            for old_path in not_found:
                self.log(self.texture_log_field, "  [NOT FOUND] {}".format(old_path))

            for old_path, matches in ambiguous:
                self.log(self.texture_log_field, "  [AMBIGUOUS] {}".format(old_path))
                for match in matches:
                    self.log(self.texture_log_field, "    {}".format(match))

            if skipped_existing:
                self.log(
                    self.texture_log_field,
                    "  Existing paths skipped: {}".format(len(skipped_existing)),
                )

            replacement_count += len(replacements)
            not_found_count += len(not_found)
            ambiguous_count += len(ambiguous)
            skipped_existing_count += len(skipped_existing)

            if not replacements:
                self.log(self.texture_log_field, "  No changes required")
                continue

            changed_files += 1

            if not apply_changes:
                self.log(
                    self.texture_log_field,
                    "  Would replace {} texture path(s)".format(len(replacements)),
                )
                continue

            try:
                backup_path = self.create_backup(ass_path, timestamp)
                backup_paths.append(backup_path)
                self.write_ass_text_atomic(ass_path, result["text"])
                self.log(self.texture_log_field, "  Backup: {}".format(backup_path))
                self.log(
                    self.texture_log_field,
                    "  Updated {} texture path(s)".format(len(replacements)),
                )
            except Exception as error:
                failed_files += 1
                changed_files -= 1
                replacement_count -= len(replacements)
                self.log(self.texture_log_field, "  [FAILED TO WRITE] {}".format(error))

        self.log(self.texture_log_field, "")
        self.log(self.texture_log_field, "=" * 88)
        self.log(
            self.texture_log_field,
            "Modified ASS files: {}".format(changed_files)
            if apply_changes
            else "ASS files that would change: {}".format(changed_files),
        )
        self.log(
            self.texture_log_field,
            "Texture paths replaced: {}".format(replacement_count)
            if apply_changes
            else "Texture paths that would change: {}".format(replacement_count),
        )
        self.log(self.texture_log_field, "Texture paths not found: {}".format(not_found_count))
        self.log(self.texture_log_field, "Ambiguous texture paths: {}".format(ambiguous_count))
        self.log(
            self.texture_log_field,
            "Existing texture paths skipped: {}".format(skipped_existing_count),
        )
        self.log(self.texture_log_field, "Failed ASS files: {}".format(failed_files))
        if apply_changes:
            self.log(self.texture_log_field, "Backups created: {}".format(len(backup_paths)))

        message = (
            "Updated {} texture path(s) in {} ASS file(s).".format(
                replacement_count,
                changed_files,
            )
            if apply_changes
            else "{} texture path(s) can be updated in {} ASS file(s).".format(
                replacement_count,
                changed_files,
            )
        )
        cmds.inViewMessage(amg=message, position="topCenter", fade=True)

    def repath_ass_textures(
        self,
        text,
        texture_files,
        texture_index,
        missing_only,
    ):
        replacements = []
        not_found = []
        ambiguous = []
        skipped_existing = []

        # Prevent identical unresolved references from flooding the log.
        seen_not_found = set()
        seen_ambiguous = set()
        seen_skipped = set()

        def replace_parameter(match):
            parameter = match.group("parameter").lower()
            old_path = match.group("value")

            if parameter in SKIPPED_ASS_PARAMETERS:
                return match.group(0)

            if not self.looks_like_texture_path(old_path):
                return match.group(0)

            if missing_only and self.file_reference_exists(
                old_path,
                TEXTURE_EXTENSIONS,
            ):
                key = old_path.lower()
                if key not in seen_skipped:
                    seen_skipped.add(key)
                    skipped_existing.append(old_path)
                return match.group(0)

            matches, _tokenized = self.find_relocated_path(
                old_path,
                texture_files,
                texture_index,
            )

            if not matches:
                key = old_path.lower()
                if key not in seen_not_found:
                    seen_not_found.add(key)
                    not_found.append(old_path)
                return match.group(0)

            if len(matches) > 1:
                key = old_path.lower()
                if key not in seen_ambiguous:
                    seen_ambiguous.add(key)
                    ambiguous.append((old_path, matches))
                return match.group(0)

            new_path = matches[0]
            if self.paths_equal(old_path, new_path):
                return match.group(0)

            replacements.append((old_path, new_path))
            return '{}"{}"{}'.format(
                match.group("prefix"),
                new_path,
                match.group("suffix"),
            )

        new_text = ASS_STRING_PARAMETER_RE.sub(replace_parameter, text)

        return {
            "text": new_text,
            "replacements": replacements,
            "not_found": not_found,
            "ambiguous": ambiguous,
            "skipped_existing": skipped_existing,
        }

    # --------------------------------------------------------- File matching --

    def scan_files(self, root_folder, extensions, recursive=True):
        files = []

        if recursive:
            for current_root, _directories, filenames in os.walk(root_folder):
                for filename in filenames:
                    if self.has_extension(filename, extensions):
                        files.append(
                            self.normalize_path(os.path.join(current_root, filename))
                        )
        else:
            try:
                for filename in os.listdir(root_folder):
                    full_path = os.path.join(root_folder, filename)
                    if os.path.isfile(full_path) and self.has_extension(filename, extensions):
                        files.append(self.normalize_path(full_path))
            except OSError:
                pass

        return sorted(set(files))

    @staticmethod
    def build_filename_index(files):
        index = {}
        for path in files:
            key = os.path.basename(path).lower()
            index.setdefault(key, []).append(path)
        return index

    def find_relocated_path(self, old_path, candidate_files, filename_index):
        old_filename = os.path.basename(old_path.replace("\\", "/"))
        exact_matches = filename_index.get(old_filename.lower(), [])
        if exact_matches:
            return sorted(set(exact_matches)), False

        sequence_regex = self.sequence_filename_to_regex(old_filename)
        if sequence_regex is None:
            return [], False

        matching_directories = set()
        for candidate_path in candidate_files:
            if sequence_regex.match(os.path.basename(candidate_path)):
                matching_directories.add(
                    self.normalize_path(os.path.dirname(candidate_path))
                )

        token_paths = [
            self.normalize_path(os.path.join(folder, old_filename))
            for folder in sorted(matching_directories)
        ]
        return token_paths, True

    def expand_file_reference(self, path, extensions):
        expanded = os.path.expandvars(os.path.expanduser(path))
        expanded = os.path.normpath(expanded)

        if os.path.isfile(expanded):
            return [self.normalize_path(expanded)]

        filename = os.path.basename(expanded)
        folder = os.path.dirname(expanded)
        sequence_regex = self.sequence_filename_to_regex(filename)

        if sequence_regex is None or not os.path.isdir(folder):
            return []

        matches = []
        try:
            for candidate in os.listdir(folder):
                candidate_path = os.path.join(folder, candidate)
                if (
                    os.path.isfile(candidate_path)
                    and self.has_extension(candidate, extensions)
                    and sequence_regex.match(candidate)
                ):
                    matches.append(self.normalize_path(candidate_path))
        except OSError:
            return []

        return sorted(set(matches))

    def file_reference_exists(self, path, extensions):
        return bool(self.expand_file_reference(path, extensions))

    @staticmethod
    def sequence_filename_to_regex(filename):
        """Convert common Arnold, Maya and Houdini filename tokens to regex."""
        token_re = re.compile(
            r"(<UDIM>|%\(UDIM\)d|<frame>|%0\d+d|%d|\$F\d*|#+)",
            re.IGNORECASE,
        )

        parts = []
        last_end = 0
        token_found = False

        for match in token_re.finditer(filename):
            token_found = True
            parts.append(re.escape(filename[last_end:match.start()]))
            token = match.group(0)
            token_lower = token.lower()

            if token_lower in ("<udim>", "%(udim)d"):
                parts.append(r"\d{4}")
            elif token.startswith("#"):
                parts.append(r"\d{%d}" % len(token))
            elif token_lower.startswith("%0") and token_lower.endswith("d"):
                padding = int(token[2:-1])
                parts.append(r"\d{%d}" % padding)
            elif token.startswith("$F") and len(token) > 2:
                padding = int(token[2:])
                parts.append(r"\d{%d}" % padding)
            else:
                parts.append(r"\d+")

            last_end = match.end()

        if not token_found:
            return None

        parts.append(re.escape(filename[last_end:]))

        try:
            return re.compile("^" + "".join(parts) + "$", re.IGNORECASE)
        except re.error:
            return None

    # ------------------------------------------------------------- ASS I/O --

    @staticmethod
    def read_ass_text(path):
        if path.lower().endswith(".gz"):
            with gzip.open(
                path,
                "rt",
                encoding="utf-8",
                errors="surrogateescape",
                newline="",
            ) as stream:
                return stream.read()

        with open(
            path,
            "r",
            encoding="utf-8",
            errors="surrogateescape",
            newline="",
        ) as stream:
            return stream.read()

    @staticmethod
    def write_ass_text_atomic(path, text):
        folder = os.path.dirname(path) or "."
        descriptor, temp_path = tempfile.mkstemp(
            prefix=".__ass_repath_",
            suffix=".tmp.gz" if path.lower().endswith(".gz") else ".tmp",
            dir=folder,
        )
        os.close(descriptor)

        try:
            if path.lower().endswith(".gz"):
                with gzip.open(
                    temp_path,
                    "wt",
                    encoding="utf-8",
                    errors="surrogateescape",
                    newline="",
                ) as stream:
                    stream.write(text)
            else:
                with open(
                    temp_path,
                    "w",
                    encoding="utf-8",
                    errors="surrogateescape",
                    newline="",
                ) as stream:
                    stream.write(text)

            os.replace(temp_path, path)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

    @staticmethod
    def create_backup(path, timestamp):
        lower_path = path.lower()
        if lower_path.endswith(".ass.gz"):
            stem = path[:-7]
            extension = ".ass.gz"
        elif lower_path.endswith(".ass"):
            stem = path[:-4]
            extension = ".ass"
        else:
            stem, extension = os.path.splitext(path)

        base_backup_path = "{}.backup_{}{}".format(
            stem,
            timestamp,
            extension,
        )
        backup_path = base_backup_path
        counter = 1

        while os.path.exists(backup_path):
            backup_path = "{}.backup_{}_{}{}".format(
                stem,
                timestamp,
                counter,
                extension,
            )
            counter += 1

        shutil.copy2(path, backup_path)
        return ArnoldPathResolver.normalize_path(backup_path)

    # ------------------------------------------------------------ Utilities --

    def validate_folder(self, folder, log_field):
        if not folder:
            cmds.warning("Choose a folder first.")
            self.log(log_field, "No folder selected.")
            return None

        folder = os.path.expandvars(os.path.expanduser(folder))
        folder = os.path.normpath(folder)

        if not os.path.isdir(folder):
            cmds.warning("The selected folder does not exist.")
            self.log(log_field, "Folder does not exist:")
            self.log(log_field, folder)
            return None

        return self.normalize_path(folder)

    @staticmethod
    def has_extension(filename, extensions):
        lower_name = filename.lower()
        return any(lower_name.endswith(extension) for extension in extensions)

    @staticmethod
    def looks_like_texture_path(path):
        lower_path = path.lower()
        return any(lower_path.endswith(extension) for extension in TEXTURE_EXTENSIONS)

    @staticmethod
    def normalize_path(path):
        return os.path.normpath(path).replace("\\", "/")

    @staticmethod
    def paths_equal(path_a, path_b):
        normalized_a = os.path.normcase(
            os.path.normpath(os.path.expandvars(os.path.expanduser(path_a)))
        )
        normalized_b = os.path.normcase(
            os.path.normpath(os.path.expandvars(os.path.expanduser(path_b)))
        )
        return normalized_a == normalized_b

    @staticmethod
    def clear_log(field):
        cmds.scrollField(field, edit=True, text="")

    @staticmethod
    def log(field, message):
        cmds.scrollField(field, edit=True, insertText=str(message) + "\n")

    def _log_item(self, field, status, node, value):
        self.log(field, "")
        self.log(field, "[{}] {}".format(status, node))
        self.log(field, "  {}".format(value))


_ARNOLD_PATH_RESOLVER = None


def show_arnold_path_resolver():
    global _ARNOLD_PATH_RESOLVER
    _ARNOLD_PATH_RESOLVER = ArnoldPathResolver()
    _ARNOLD_PATH_RESOLVER.show()


show_arnold_path_resolver()
