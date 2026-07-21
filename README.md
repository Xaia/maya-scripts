# maya-scripts

A collection of small but useful Python scripts for Autodesk Maya.

## About

This repository contains various utility scripts designed to streamline common workflows and automate tasks in Maya. Whether you're optimizing your modeling pipeline, automating repetitive tasks, or setting up Arnold rendering, these scripts help save time and improve efficiency.

## Scripts

### **arnold_path_resolver_v1_1.py**
Resolves Arnold texture paths and handles path remapping. Useful for managing texture references across different project directories or when moving assets between locations. Provides utilities to update and consolidate texture file paths in Arnold shader networks.

### **circular_ramp_creator.py**
Creates circular ramp texture nodes with alternating black and white concentric rings. Features include:
- Configurable number of circles (black+white pairs)
- Color randomization with optional hue tints
- Thickness randomization for varied band widths
- Interpolation mode selection (None, Linear, Smooth, Spline)
- Optional direct assignment to selected meshes via Lambert shader
- Interactive UI with seed control for reproducible randomness

### **mat_to_group.py**
Automatically organizes selected meshes into groups based on their assigned materials. Creates a material hierarchy under each object's top-level group, making it easy to manage and organize complex scenes by material assignment. Useful for managing large asset trees.

### **materials_to_object_set.py**
Collects all materials assigned to selected meshes (or groups) into a Maya Object Set. Includes an interactive UI to:
- Scan selected geometry or groups
- Collect unique materials (excluding Maya defaults)
- Create a named Object Set containing all found materials
- Display collection results with material details

### **quad_patch.py**
Smart hole-patching utility for polygonal meshes. Intelligently detects the geometry of a hole boundary and creates a clean quad-based patch surface. Features:
- Adaptive edge loop analysis with angle detection
- Automatic corner vertex identification
- Handles both open and closed edge loops
- Creates smooth birail surfaces for seamless patching
- UI with toggle buttons for quick access

### **remove_name_spaces.py**
Removes all non-default namespaces from the Maya scene by merging their contents into the root namespace. Useful when cleaning up imported assets or consolidating references. Preserves Maya's default "UI" and "shared" namespaces.

### **render_curves.py**
Arnold curves utility with an interactive PySide2 UI for configuring NURBS curves for rendering:
- Toggle "Render Curve" on all curve shapes
- Assign custom curve shaders (creates aiStandardSurface shaders)
- Configure sample rate and curve width with presets
- Three shader assignment modes: all same shader, per-similar-name, or per-group
- Automatic bright color generation for visual distinction
- Supports both all curves and selected curves workflows

### **sh_to_aiStandardSurface.py**
Converts non-Arnold shaders (Lambert, Phong, Blinn, etc.) to aiStandardSurface with attribute mapping and connection preservation. Features include:
- Convert selected shaders or all assigned shaders in the scene
- Intelligent attribute mapping (color → baseColor, transparency → opacity, etc.)
- Automatic texture color space assignment based on file paths (_d* = sRGB, others = Raw)
- Safe handling of shared textures (creates localized copies when needed)
- Comprehensive logging and undo support
- Interactive UI for batch conversions

### **text_to_curve.py**
Converts text into NURBS curves for use in scenes. Features include:
- Multi-line text support with automatic vertical stacking
- Custom font selection via system font dialog
- Configurable line spacing
- Automatic pivot centering and transform freezing
- Groups output curves for organization
- Simple PySide2 UI with intuitive text editor

## Features

- Lightweight Python scripts for quick integration
- Most scripts include interactive UIs for ease of use
- Arnold rendering support (curves, shader conversion, path resolution)
- Material and asset organization utilities
- Texture and shader management tools
- Designed for Maya 2017+ (PySide2 compatible)
- Compatible with Python 2.7 and Python 3.x

## Installation

1. Clone this repository to your local machine:
   ```bash
   git clone https://github.com/Xaia/maya-scripts.git
   ```

2. Copy the scripts to your Maya scripts folder:
   - **Windows**: `%USERPROFILE%\Documents\maya\<version>\scripts`
   - **macOS**: `~/Library/Preferences/Autodesk/maya/<version>/scripts`
   - **Linux**: `~/maya/<version>/scripts`

3. Restart Maya or reload the scripts module.

## Usage

Each script can be run from Maya's Script Editor or imported as a Python module. Most scripts launch an interactive UI when executed. Simply copy the desired script to the Maya Script Editor and run it, or add it to your shelf for quick access.

## Requirements

- Autodesk Maya 2017+ (for PySide2 support in UI scripts)
- Python 2.7 or Python 3.x depending on your Maya version
- Arnold plugin for Maya (required for Arnold-specific scripts)

## Contributing

Contributions are welcome! Feel free to submit pull requests or open issues for bug reports and feature requests.

## License

Feel free to use these scripts as you like.

## Support

For questions or issues, please open an issue on the GitHub repository.

---

**Happy scripting!** 🎨
