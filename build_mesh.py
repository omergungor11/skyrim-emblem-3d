"""Builds a high-poly, double-sided emblem mesh + detail maps from an image.

Usage: python3 build_mesh.py [mesh_scale] [detail_scale]   (default 4, 8)
  mesh_scale   : mesh grid = source pixels x mesh_scale
  detail_scale : maps = source pixels x detail_scale (must be a multiple of mesh_scale)
Outputs:
  emblem.glb  : 3 primitive -> front / back / wall (same material names)
  texture.png, normal.png            : front face (R=albedo, G=roughness, B=cavity; object-space normal)
  back_texture.png, back_normal.png  : back face (+ side wall uses the same texture)
"""
import sys, json, struct
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

MS = int(sys.argv[1]) if len(sys.argv) > 1 else 4
DS = int(sys.argv[2]) if len(sys.argv) > 2 else 8
assert DS % MS == 0
STEP = DS // MS
rng = np.random.default_rng(7)

src = Image.open("source.png").convert("L")
W0, H0 = src.size
Wd, Hd = W0 * DS, H0 * DS
L = np.clip(np.asarray(src.resize((Wd, Hd), Image.LANCZOS), dtype=np.float32) / 255.0, 0, 1)
g = lambda a, s: ndi.gaussian_filter(a, s * DS)            # sigma in source pixels
px = 1.0 / Hd                                              # model height = 1 unit

# ---------------- mask
mask = g(L, 0.6) > 0.07
mask = ndi.binary_opening(mask, iterations=STEP)
lab, n = ndi.label(mask)
sizes = ndi.sum(mask, lab, range(1, n + 1))
keep = np.zeros(n + 1, bool); keep[1:] = sizes > 400 * DS * DS
mask = keep[lab]
mask = (ndi.binary_fill_holes(mask) & (g(L, 1.0) > 0.03)) | mask

# edge notches
dist0 = ndi.distance_transform_edt(mask).astype(np.float32) / DS
chipnoise = g(rng.standard_normal((Hd, Wd)).astype(np.float32), 1.1)
chipnoise /= chipnoise.std()
mask &= ~((dist0 < 1.6) & (chipnoise > 2.3 + dist0 * 0.6))
mask = ndi.binary_opening(mask, iterations=max(1, STEP // 2))
dist = ndi.distance_transform_edt(mask).astype(np.float32) / DS
del dist0


def micro_layer(expo, seed, density):
    """Procedural wear: direction-clustered scratches (+burr), impact pits, hammered texture."""
    r = np.random.default_rng(seed)
    img = Image.new("F", (Wd, Hd), 0.0)
    dr = ImageDraw.Draw(img)
    dirs = r.uniform(0, np.pi, 4)
    for _ in range(int((int(9000 * (DS / 8) ** 2 * 0.5) + 4000) * density)):
        x, y = r.uniform(0, Wd), r.uniform(0, Hd)
        if not mask[int(y), int(x)]:
            continue
        ang = r.choice(dirs) + r.normal(0, 0.18) if r.random() < 0.7 else r.uniform(0, np.pi)
        ln = min(r.pareto(1.6) * 4 * DS + 1.5 * DS, 60 * DS)
        k = r.normal(0, 0.15)
        pts = [(x + np.cos(ang + k * t) * ln * t, y + np.sin(ang + k * t) * ln * t)
               for t in np.linspace(-0.5, 0.5, 6)]
        dr.line(pts, fill=float(r.uniform(0.3, 1.0)), width=int(r.choice([1, 1, 1, 2, 2, 3])))
    scr = ndi.gaussian_filter(np.asarray(img, dtype=np.float32), 0.7)
    burr = np.clip(ndi.gaussian_filter(scr, 2.0) - scr, 0, None)
    pits = np.zeros((Hd, Wd), np.float32)
    npit = int(Wd * Hd * 1.5e-4)
    pits[r.integers(0, Hd, npit), r.integers(0, Wd, npit)] = r.pareto(2.0, npit).astype(np.float32) + 0.3
    pits = ndi.gaussian_filter(pits, 1.2 * STEP) * 6 + ndi.gaussian_filter(pits, 3.0 * STEP) * 18
    ham = (g(r.standard_normal((Hd, Wd)).astype(np.float32), 3.0) * 9
           + g(r.standard_normal((Hd, Wd)).astype(np.float32), 0.9) * 1.2)
    micro = (-scr * 0.0011 + burr * 0.0012 - pits * 0.0016) * expo + ham * 0.00022 * mask
    return micro.astype(np.float32), scr, burr


def objspace_normal(h, zsign):
    """h: outward surface height. zsign=+1 front (faces +z), -1 back."""
    gy, gx = np.gradient(h, px)                           # gy: row (downward) direction
    nrm = np.stack([-gx, gy, np.full_like(gx, zsign)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    out = ((nrm * 0.5 + 0.5) * 255).astype(np.uint8)
    out[~mask] = [128, 128, 255 if zsign > 0 else 0]
    return out


def save_curv(path, h, zsign):
    """Convexity (ridge/corner = 1) for edge wear. Difference-of-Gaussians."""
    lap = (g(h, 0.5) - g(h, 2.5)) * zsign
    lap = np.where(mask, lap, 0)
    k = np.percentile(lap[mask & (lap > 0)], 96)
    Image.fromarray((np.clip(lap / k, 0, 1) ** 0.8 * 255).astype(np.uint8)).save(path, optimize=True)


def save_tex(path, albedo, rough, cav):
    Image.fromarray((np.stack([albedo, rough, 1 - cav], -1) * 255).astype(np.uint8)).save(path, optimize=True)


# ================= FRONT FACE
bevel = g(np.sqrt(np.clip(dist / 9.0, 0, 1)), 1.0)
Ls = g(L, 0.35)
low = g(L, 6)
b15 = g(L, 1.5)
mid, fine = b15 - low, Ls - b15
del b15
expo = mask * (0.35 + 0.65 * bevel)
micro, scr, burr = micro_layer(expo, 101, 1.0)
height = np.where(mask, bevel * 0.022 + mid * 0.020 + fine * 0.007 + low * 0.010 + micro, 0)
height -= np.clip(1 - dist / 1.2, 0, 1) * np.clip(chipnoise * 0.5 + 0.5, 0, 1) * 0.004 * mask
height = height.astype(np.float32)

cav = np.clip((g(height, 1.5) - height) * 260, 0, 1)
save_tex("texture.png",
         np.clip(Ls * (1 - 0.55 * cav) + scr * 0.22 * expo + burr * 0.1, 0, 1),
         np.clip(0.28 + 0.4 * (1 - Ls) + 0.25 * cav + 0.15 * scr - 0.1 * bevel, 0.08, 0.95), cav)
# suppress source-image JPEG noise in the normal map (it stays in the geometry)
Image.fromarray(objspace_normal(height - fine * 0.007 * mask + g(fine, 0.25) * 0.004 * mask, 1)).save("normal.png", optimize=True)
save_curv("curv.png", height, 1)
del micro, scr, burr, cav, mid, low, Ls, L

# ================= BACK FACE (cast back: rounded edge, undulation, its own wear)
bevel_b = g(np.sqrt(np.clip(dist / 6.0, 0, 1)), 0.7)
patina = g(rng.standard_normal((Hd, Wd)).astype(np.float32), 10); patina /= patina.std() + 1e-9
patina2 = g(rng.standard_normal((Hd, Wd)).astype(np.float32), 3); patina2 /= patina2.std() + 1e-9
expo_b = mask * (0.3 + 0.7 * bevel_b)
micro_b, scr_b, burr_b = micro_layer(expo_b, 202, 0.7)
hb = np.where(mask, bevel_b * 0.010 + patina * 0.0010 + patina2 * 0.00025 + micro_b, 0).astype(np.float32)
cav_b = np.clip((g(hb, 1.5) - hb) * 260, 0, 1)
save_tex("back_texture.png",
         np.clip(0.48 + patina2 * 0.05 + patina * 0.04 - 0.4 * cav_b + scr_b * 0.25 * expo_b + burr_b * 0.1, 0, 1),
         np.clip(0.45 + 0.25 * cav_b + 0.12 * scr_b - 0.1 * bevel_b + patina2 * 0.05, 0.1, 0.95), cav_b)
Image.fromarray(objspace_normal(hb, -1)).save("back_normal.png", optimize=True)
save_curv("back_curv.png", hb, 1)
del micro_b, scr_b, burr_b, cav_b, patina, patina2, chipnoise

# ================= SIDE TEXTURE (tileable, triplanar for steep walls)
T = 1024
tr = np.random.default_rng(303)
timg = Image.new("F", (T, T), 0.0)
tdr = ImageDraw.Draw(timg)
for _ in range(1400):
    x, y = tr.uniform(0, T), tr.uniform(0, T)
    ang = tr.normal(0, 0.35) if tr.random() < 0.6 else tr.uniform(0, np.pi)
    ln = min(tr.pareto(1.6) * 25 + 10, 400)
    for ox in (-T, 0, T):
        for oy in (-T, 0, T):
            tdr.line([(x + ox - np.cos(ang) * ln / 2, y + oy - np.sin(ang) * ln / 2),
                      (x + ox + np.cos(ang) * ln / 2, y + oy + np.sin(ang) * ln / 2)],
                     fill=float(tr.uniform(0.3, 1)), width=int(tr.choice([1, 1, 2])))
tscr = ndi.gaussian_filter(np.asarray(timg, np.float32), 0.7, mode="wrap")
tn = lambda s_: (lambda a_: a_ / a_.std())(ndi.gaussian_filter(tr.standard_normal((T, T)).astype(np.float32), s_, mode="wrap"))
tp = np.zeros((T, T), np.float32)
tp[tr.integers(0, T, 900), tr.integers(0, T, 900)] = tr.pareto(2.0, 900) + 0.3
tcav = np.clip(ndi.gaussian_filter(tp, 2.0, mode="wrap") * 10 + np.clip(tn(6) - 1.2, 0, None) * 0.5, 0, 1)
n1, n2 = tn(40), tn(4)
save_tex("side_texture.png",
         np.clip(0.5 + n1 * 0.06 + n2 * 0.04 - 0.25 * tcav + tscr * 0.25, 0, 1),
         np.clip(0.42 + 0.25 * tcav + 0.12 * tscr + n2 * 0.05, 0.1, 0.95), tcav)
del timg, tscr, tp, tcav

# ================= MESH
o = STEP // 2
mmask = mask[o::STEP, o::STEP]
mh, mhb = height[o::STEP, o::STEP], hb[o::STEP, o::STEP]
H, W = mmask.shape
idx = -np.ones((H, W), np.int64)
ys, xs = np.nonzero(mmask)
idx[ys, xs] = np.arange(len(xs))
nv = len(xs)
mpx = 1.0 / H
xy = np.stack([(xs - W / 2) * mpx, (H / 2 - ys) * mpx], 1).astype(np.float32)
zf = mh[ys, xs].astype(np.float32)
BACK0 = -0.006
zb = (BACK0 - mhb[ys, xs]).astype(np.float32)
uv = np.stack([(xs + 0.5) / W, (ys + 0.5) / H], 1).astype(np.float32)

a = idx[:-1, :-1]; b = idx[:-1, 1:]; c = idx[1:, :-1]; d = idx[1:, 1:]
full = (a >= 0) & (b >= 0) & (c >= 0) & (d >= 0)
tris = [np.stack([a[full], c[full], b[full]], 1), np.stack([b[full], c[full], d[full]], 1)]
for (p, q, r_), cond in [((a, c, d), (a >= 0) & (c >= 0) & (d >= 0) & (b < 0)),
                         ((a, d, b), (a >= 0) & (b >= 0) & (d >= 0) & (c < 0)),
                         ((a, c, b), (a >= 0) & (b >= 0) & (c >= 0) & (d < 0)),
                         ((b, c, d), (b >= 0) & (c >= 0) & (d >= 0) & (a < 0))]:
    tris.append(np.stack([p[cond], q[cond], r_[cond]], 1))
front = np.concatenate(tris).astype(np.int64)

e = np.concatenate([front[:, [0, 1]], front[:, [1, 2]], front[:, [2, 0]]])
key = np.minimum(e[:, 0], e[:, 1]) * nv + np.maximum(e[:, 0], e[:, 1])
uk, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
bedges = e[cnt[inv] == 1]
bl = np.unique(bedges)
nbv = len(bl)
remap = -np.ones(nv, np.int64); remap[bl] = np.arange(nbv)
nb = {}
for u, v in bedges:
    nb.setdefault(u, []).append(v); nb.setdefault(v, []).append(u)
nbr = np.array([nb[v][:2] if len(nb[v]) >= 2 else [nb[v][0]] * 2 for v in bl])
for _ in range(6):                                         # smooth the outline in 2D
    t_ = xy.copy()
    xy[bl] = 0.5 * t_[bl] + 0.25 * (t_[nbr[:, 0]] + t_[nbr[:, 1]])
zf[bl] = np.minimum(zf[bl], 0.002)
zb[bl] = np.maximum(zb[bl], BACK0 - 0.0005)

# outward-facing 2D edge normals
en = np.zeros((nv, 2), np.float32)
dxy = xy[bedges[:, 1]] - xy[bedges[:, 0]]
edge_n = np.stack([dxy[:, 1], -dxy[:, 0]], 1)
np.add.at(en, bedges[:, 0], edge_n); np.add.at(en, bedges[:, 1], edge_n)
bn = en[bl]
for _ in range(4):
    bn = 0.5 * bn + 0.25 * (bn[remap[nbr[:, 0]]] + bn[remap[nbr[:, 1]]])
bn /= np.linalg.norm(bn, axis=1, keepdims=True) + 1e-12
probe = xy[bl] + bn * 3 * mpx                              # orientation check: outside must not be in the mask
pxp = np.clip((probe[:, 0] / mpx + W / 2).astype(int), 0, W - 1)
pyp = np.clip((H / 2 - probe[:, 1] / mpx).astype(int), 0, H - 1)
if mmask[pyp, pxp].mean() > 0.5:
    bn = -bn

# ---- side wall: R rings, outward-bulging rounded profile + 3D noise dents
R = 10
vol = ndi.gaussian_filter(rng.standard_normal((96, 96, 96)).astype(np.float32), 2.0, mode="wrap")
vol /= vol.std()
vol2 = ndi.gaussian_filter(rng.standard_normal((96, 96, 96)).astype(np.float32), 1.0, mode="wrap")
vol2 /= vol2.std()
def noise3(v, p, cell):
    return ndi.map_coordinates(v, (p / cell).T, order=1, mode="grid-wrap")

bxy, bzf, bzb, buv = xy[bl], zf[bl], zb[bl], uv[bl]
wpos, wuv = [], []
for j in range(R + 1):
    t = j / R
    depth = bzf - bzb
    z = bzf - depth * t
    s = np.sin(np.pi * t)
    p = np.concatenate([bxy + bn * (0.32 * depth * s)[:, None], z[:, None]], 1)
    dent = (0.00035 * noise3(vol, p, 0.0005) - 0.0012 * np.clip(noise3(vol2, p, 0.0004) - 1.4, 0, None))
    p[:, :2] += bn * (dent * s ** 0.5)[:, None]
    off = depth * 1.3 * t                                  # UV shifts inward along depth -> no stretching
    wuv.append(np.stack([buv[:, 0] - bn[:, 0] * off / (W * mpx),
                         buv[:, 1] + bn[:, 1] * off / (H * mpx)], 1))
    wpos.append(p)
WP = np.concatenate(wpos).astype(np.float32)
WUV = np.concatenate(wuv).astype(np.float32)
eu, ev = remap[bedges[:, 0]], remap[bedges[:, 1]]
wf = []
for j in range(R):
    o0, o1 = j * nbv, (j + 1) * nbv
    wf += [np.stack([ev + o0, eu + o0, eu + o1], 1), np.stack([ev + o0, eu + o1, ev + o1], 1)]
WF = np.concatenate(wf).astype(np.int64)

FP = np.concatenate([xy, zf[:, None]], 1).astype(np.float32)
BP = np.concatenate([xy, zb[:, None]], 1).astype(np.float32)
BF = front[:, ::-1].copy()


def normals(P, F):
    N = np.zeros_like(P)
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    return (N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)).astype(np.float32), fn

FN, ffn = normals(FP, front)
BN, bfn = normals(BP, BF)
WN, wfn = normals(WP, WF)
assert ffn[:, 2].sum() > 0 and bfn[:, 2].sum() < 0, "front/back winding is reversed"
# do wall faces point outward? (face normal · edge normal)
edge_of_face = np.tile(np.arange(len(bedges)), 2 * R)
wout = (wfn[:, :2] * bn[remap[bedges[edge_of_face, 0]]]).sum()
if wout < 0:
    WF = WF[:, ::-1].copy(); WN, _ = normals(WP, WF)

# ================= GLB (3 primitive)
prims = [("front", FP, FN, uv, front), ("back", BP, BN, uv, BF), ("wall", WP, WN, WUV, WF)]
buf, views, accs, gprims, mats = b"", [], [], [], []
def add(arr, target, comp, typ, mm=False):
    global buf
    bts = arr.tobytes()
    views.append({"buffer": 0, "byteOffset": len(buf), "byteLength": len(bts), "target": target})
    buf += bts + b"\x00" * ((4 - len(bts) % 4) % 4)
    acc = {"bufferView": len(views) - 1, "componentType": comp,
           "count": len(arr) if arr.ndim > 1 else arr.size, "type": typ}
    if mm:
        acc["min"], acc["max"] = arr.min(0).tolist(), arr.max(0).tolist()
    accs.append(acc); return len(accs) - 1
rough_base = {"front": 0.3, "back": 0.45, "wall": 0.45}
for i, (name, P, N, UV, F) in enumerate(prims):
    ip = add(P, 34962, 5126, "VEC3", True); inn = add(N, 34962, 5126, "VEC3"); iu = add(UV, 34962, 5126, "VEC2")
    ii = add(F.astype(np.uint32).ravel(), 34963, 5125, "SCALAR")
    gprims.append({"attributes": {"POSITION": ip, "NORMAL": inn, "TEXCOORD_0": iu}, "indices": ii, "material": i})
    mats.append({"name": name, "pbrMetallicRoughness": {"baseColorFactor": [0.6, 0.6, 0.62, 1],
                 "metallicFactor": 1.0, "roughnessFactor": rough_base[name]}})
gltf = {"asset": {"version": "2.0", "generator": "build_mesh.py"}, "scene": 0,
        "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "emblem"}],
        "meshes": [{"primitives": gprims}], "materials": mats,
        "buffers": [{"byteLength": len(buf)}], "bufferViews": views, "accessors": accs}
js = json.dumps(gltf).encode(); js += b" " * ((4 - len(js) % 4) % 4)
with open("emblem.glb", "wb") as f:
    f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(buf)))
    f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
    f.write(struct.pack("<II", len(buf), 0x004E4942)); f.write(buf)
nt = len(front) * 2 + len(WF)
print(f"mesh {W}x{H}  maps {Wd}x{Hd}  vertices {len(FP) + len(BP) + len(WP):,}  triangles {nt:,}  "
      f"(wall {len(WF):,})  glb {len(buf)/1e6:.1f} MB  wall-out {wout > 0}")
