# Blender Icicle Generator

## Overview

A modern Blender add-on for generating realistic icicles directly onto your mesh. Supports Blender **4.0 and above**. Forked and modernized from [MayeoinBread/Blender-IcicleGenerator](https://github.com/MayeoinBread/Blender-IcicleGenerator).

---

## Features

- **Blender 4.0+ Compatible**
- Add icicles to selected edges (or faces) in Edit Mode
- Realistic icicle shapes:
  - Gravity curve (icicles bend downward as they grow)
  - Wind effect (icicles bend in a consistent direction)
  - Waviness (natural kinks and bends)
- Randomized placement and size for natural clustering
- Adjustable number of icicles per edge
- Live 3D preview of icicle paths
- All geometry is added directly to your mesh (not as separate objects)
- Full undo/redo support
- Customizable parameters: radius, depth, curvature, wind, waviness, and more

---

## Installation

1. Download this repository as a ZIP file.
2. In Blender, go to **Edit > Preferences > Add-ons**.
3. Click **Install...** and select the ZIP file.
4. Enable the "Icicle Generator" add-on.

---

## Usage

1. Select a mesh object and enter **Edit Mode**.
2. Select the edges where you want to add icicles.
3. Open the **N-panel** (press `N`), go to the **Icicle Generator** tab.
4. Adjust parameters as desired (radius, depth, gravity, wind, etc.).
5. Click **Generate** to add icicles to your mesh.
6. Use the **Preview** button to see a live preview of icicle paths before generating.
