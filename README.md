# Skyrim Emblem 3D

A high-poly (3.7M triangles), worn-iron 3D dragon emblem generated procedurally from a single 2D
image. Renders in real time in the browser with three.js.

**Live demo:** https://skyrim-emblem-3d.vercel.app

![preview](preview.png)

## What's inside

- `build_mesh.py`: extracts a height field from `source.png` and builds a front/back/side-wall mesh
  plus albedo, roughness, cavity, object-space normal and curvature maps.
- `index.html`: three.js viewer. HDRI environments (Poly Haven, CC0), curvature-driven edge polish and
  oxidation, GTAO, bloom, 4096 shadow map, iridescence-based heat tint (temper).
- UI controls for grime, wear, temper, light, environment and wireframe.

## 3D files

GLB files are on the [Releases](../../releases) page:
- `emblem.glb`: raw mesh (106 MB)
- `emblem.web.glb`: meshopt-compressed (16 MB, `EXT_meshopt_compression`)

The maps live in the repo root as PNGs (R = albedo, G = roughness, B = cavity). The GLBs carry no
embedded textures, so other viewers show plain geometry; the worn look comes from the viewer's shader.

## Running locally

```bash
python3 -m http.server 8000   # then open http://localhost:8000
```

To regenerate: `python3 build_mesh.py 4 8` (requires numpy, pillow, scipy).

## Disclaimer

Non-commercial fan art. The Elder Scrolls V: Skyrim and its dragon emblem are trademarks of
Bethesda Softworks / ZeniMax Media; this project is not affiliated with them.
HDRIs from Poly Haven (CC0).
