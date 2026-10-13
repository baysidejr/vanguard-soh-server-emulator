"""Find water in a chunk (fishing spots, swimming): the WaterVolume actors of the chunk's
level package (Assets/Maps/<chunk>.vgr) and the terrain below their top (docs/FISHING.md).

    python water.py chunk_n19_12 [x y]   -> the volumes, and the nearest submerged ground to (x, y)
"""
import math
import os
import struct
import sys

from upackage import Package, _compact
import terrain

MAPS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Assets", "Maps")
sizes=[1,2,4,12,16]
def props(p,raw,pos):
    out={}
    while pos<len(raw):
        n,pos=_compact(raw,pos)
        if n<0 or n>=len(p.names): return out,pos
        name=p.names[n]
        if name=="None": return out,pos
        info=raw[pos];pos+=1
        t,si,arr=info&0xF,(info>>4)&7,info&0x80
        sname=None
        if t==10:
            s,pos=_compact(raw,pos); sname=p.names[s]
        if si<5: size=sizes[si]
        elif si==5: size=raw[pos];pos+=1
        elif si==6: size=struct.unpack_from("<H",raw,pos)[0];pos+=2
        else: size=struct.unpack_from("<I",raw,pos)[0];pos+=4
        ai=0
        if arr and t!=3:
            b0=raw[pos]; ai=b0; pos+=1 if b0<0x80 else (2 if b0<0xC0 else 4)
        v=raw[pos:pos+size]
        if t==3: v=bool(arr)
        elif sname in("Vector","Rotator") : v=struct.unpack("<3f" if sname=="Vector" else "<3i",v)
        elif t==4: v=struct.unpack("<f",v)[0]
        elif t==2: v=struct.unpack("<i",v)[0]
        elif t==5: v=_compact(v,0)[0]
        elif t==1: v=v[0]
        elif t==6: v=p.names[_compact(v,0)[0]]
        else: v=v.hex()[:40]
        out[name if not ai else f"{name}[{ai}]"]=v
        pos+=size
    return out,pos
def objname(p,i):
    if i>0: return p.exports[i-1]["name"]
    if i<0: return p.imports[-i-1][3]
    return None
def actor_props(p,e):
    raw=p.raw[e["offset"]:e["offset"]+e["size"]]
    for j in range(0,64):
        try:
            o,end=props(p,raw,j)
            if len(o) >= 2:
                return o
        except Exception: pass
    return {}
def model_bounds(p,idx):
    e=p.exports[idx-1]; raw=p.raw[e["offset"]:e["offset"]+e["size"]]
    o,pos=props(p,raw,0)
    mn=struct.unpack_from("<3f",raw,pos); mx=struct.unpack_from("<3f",raw,pos+12); valid=raw[pos+24]
    return mn,mx,valid


def water_boxes(chunk, maps=MAPS):
    """[(name, (x0, y0, z0), (x1, y1, z1))] world boxes of the chunk's WaterVolumes (no rotation)."""
    p = Package(os.path.join(maps, chunk + ".vgr"))
    out = []
    for e in p.exports:
        if p.class_name(e["class"]) != "WaterVolume":
            continue
        o = actor_props(p, e)
        br = o.get("Brush")
        if not br:
            continue
        mn, mx, _ = model_bounds(p, br)
        loc, pp = o.get("Location", (0, 0, 0)), o.get("PrePivot", (0, 0, 0))
        ds, dsc = o.get("DrawScale3D", (1, 1, 1)), o.get("DrawScale", 1.0)
        a, b = [[loc[i] + (m[i] - pp[i]) * ds[i] * dsc for i in range(3)] for m in (mn, mx)]
        out.append((e["name"], tuple(min(a[i], b[i]) for i in range(3)), tuple(max(a[i], b[i]) for i in range(3))))
    return out


def nearest_water(chunk, x, y, depth=150, step=400, maps=MAPS):
    """(distance, wx, wy, ground z) of the nearest terrain point at least `depth` below a
    water volume's top, or None."""
    t = terrain.Terrain(os.path.join(maps, chunk + ".vgr"))
    boxes = water_boxes(chunk, maps)
    best = None
    for gy in range(-102400, 102400, step):
        for gx in range(-102400, 102400, step):
            z = t.height(gx, gy)
            if z is None:
                continue
            for _n, lo, hi in boxes:
                if lo[0] <= gx <= hi[0] and lo[1] <= gy <= hi[1] and lo[2] <= z <= hi[2] - depth:
                    d = math.hypot(gx - x, gy - y)
                    if best is None or d < best[0]:
                        best = (d, gx, gy, z)
    return best


if __name__ == "__main__":
    chunk = sys.argv[1]
    for name, lo, hi in water_boxes(chunk):
        print(name, [round(v) for v in lo], [round(v) for v in hi])
    if len(sys.argv) >= 4:
        print("nearest water:", nearest_water(chunk, float(sys.argv[2]), float(sys.argv[3])))
