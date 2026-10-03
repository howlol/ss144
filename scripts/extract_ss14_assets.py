#!/usr/bin/env python3
"""
Extracts real Space Station 14 assets from a Space Station 14 source checkout (/tmp/ss14):
1. Parses Resources/Maps/saltern.yml (grid chunks, tiles, walls, doors, cameras, beacons, spawn points, machines, items)
2. Parses Resources/Prototypes/Tiles/*.yml and Resources/Prototypes/Entities/**/*.yml for Sprite mappings
3. Parses Resources/Prototypes/Roles/Jobs/**/*.yml for real SS14 jobs, accesses, and starting gear
4. Copies referenced textures (.png and meta.json) from Resources/Textures/ into ss14_assets/textures/
5. Writes ss14_assets/maps/saltern.json and ss14_assets/sprite_manifest.json
"""

import base64
import json
import math
import os
import re
import shutil
import struct
import sys
from pathlib import Path
import yaml


def ss14_tag_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        d = loader.construct_mapping(node)
        d["_tag"] = tag_suffix
        return d
    return None


yaml.SafeLoader.add_multi_constructor("!", ss14_tag_constructor)


def load_yaml_safe(path: Path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def main():
    ss14_root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ss14")
    out_root = Path(sys.argv[2] if len(sys.argv) > 2 else "ss14_assets")

    res_root = ss14_root / "Resources"
    tex_root = res_root / "Textures"
    proto_root = res_root / "Prototypes"
    map_file = res_root / "Maps" / "saltern.yml"

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "maps").mkdir(parents=True, exist_ok=True)
    (out_root / "textures").mkdir(parents=True, exist_ok=True)
    (out_root / "prototypes").mkdir(parents=True, exist_ok=True)

    print(f"[1/5] Scanning SS14 Tile & Entity Prototypes in {proto_root}...")
    tile_protos = {}
    entity_protos = {}
    job_protos = {}
    starting_gears = {}

    for yml_path in proto_root.rglob("*.yml"):
        docs = load_yaml_safe(yml_path)
        if not isinstance(docs, list):
            continue
        for item in docs:
            if not isinstance(item, dict):
                continue
            ptype = item.get("type")
            pid = item.get("id")
            if not pid or not isinstance(pid, str):
                continue

            if ptype == "tile":
                tile_protos[pid] = {
                    "id": pid,
                    "name": item.get("name", pid),
                    "sprite": item.get("sprite", ""),
                    "isSubfloor": bool(item.get("isSubfloor", False)),
                }
            elif ptype == "job":
                job_protos[pid] = {
                    "id": pid,
                    "name": item.get("name", pid),
                    "description": item.get("description", ""),
                    "startingGear": item.get("startingGear", ""),
                    "icon": item.get("icon", ""),
                    "access": item.get("access", []),
                    "extendedAccess": item.get("extendedAccess", []),
                    "supervisors": item.get("supervisors", ""),
                }
            elif ptype == "startingGear":
                starting_gears[pid] = {
                    "id": pid,
                    "equipment": item.get("equipment", {}),
                    "inhand": item.get("inhand", []),
                    "storage": item.get("storage", {}),
                }
            elif ptype == "entity":
                parents = item.get("parent", [])
                if isinstance(parents, str):
                    parents = [parents]
                elif not isinstance(parents, list):
                    parents = []

                sprite_info = {}
                icon_info = {}
                door_info = None
                access_info = None
                camera_info = None
                beacon_info = None

                for comp in item.get("components", []):
                    if not isinstance(comp, dict):
                        continue
                    ctype = comp.get("type")
                    if ctype == "Sprite":
                        sprite_info = {
                            "sprite": comp.get("sprite"),
                            "state": comp.get("state"),
                            "drawdepth": comp.get("drawdepth"),
                            "layers": comp.get("layers", []),
                        }
                    elif ctype == "Icon":
                        icon_info = {
                            "sprite": comp.get("sprite"),
                            "state": comp.get("state"),
                        }
                    elif ctype == "Door":
                        door_info = {
                            "bumpOpen": comp.get("bumpOpen", True),
                            "clickOpen": comp.get("clickOpen", True),
                            "occludes": comp.get("occludes", True),
                        }
                    elif ctype == "AccessReader":
                        access_info = comp.get("access", [])
                    elif ctype == "SurveillanceCamera":
                        camera_info = {
                            "id": comp.get("id", ""),
                            "networks": comp.get("setupAvailableNetworks", []),
                        }
                    elif ctype == "NavMapBeacon":
                        beacon_info = {
                            "text": comp.get("text", ""),
                            "color": comp.get("color", "#ffffff"),
                        }

                entity_protos[pid] = {
                    "id": pid,
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "parents": parents,
                    "sprite": sprite_info,
                    "icon": icon_info,
                    "door": door_info,
                    "access": access_info,
                    "camera": camera_info,
                    "beacon": beacon_info,
                }

    print(
        f"Loaded {len(tile_protos)} tiles, {len(entity_protos)} entities, {len(job_protos)} jobs."
    )

    # Resolve inheritance for entity prototypes (name, description, sprite, door, access, beacon)
    def resolve_proto(pid, visited=None):
        if visited is None:
            visited = set()
        if pid in visited or pid not in entity_protos:
            return {}
        visited.add(pid)
        cur = entity_protos[pid]
        merged = {
            "id": pid,
            "name": cur.get("name"),
            "description": cur.get("description"),
            "sprite_path": None,
            "sprite_state": None,
            "drawdepth": None,
            "door": cur.get("door"),
            "access": cur.get("access"),
            "camera": cur.get("camera"),
            "beacon": cur.get("beacon"),
        }

        sp = cur.get("sprite") or {}
        ic = cur.get("icon") or {}
        sprite_path = sp.get("sprite") or ic.get("sprite")
        sprite_state = sp.get("state") or ic.get("state")
        if not sprite_state and isinstance(sp.get("layers"), list):
            for layer in sp["layers"]:
                if isinstance(layer, dict) and layer.get("state"):
                    sprite_state = layer.get("state")
                    if layer.get("sprite") and not sprite_path:
                        sprite_path = layer.get("sprite")
                    break

        merged["sprite_path"] = sprite_path
        merged["sprite_state"] = sprite_state
        merged["drawdepth"] = sp.get("drawdepth")

        for parent_id in cur.get("parents", []):
            p_res = resolve_proto(parent_id, visited.copy())
            if not merged["name"] and p_res.get("name"):
                merged["name"] = p_res["name"]
            if not merged["description"] and p_res.get("description"):
                merged["description"] = p_res["description"]
            if not merged["sprite_path"] and p_res.get("sprite_path"):
                merged["sprite_path"] = p_res["sprite_path"]
            if not merged["sprite_state"] and p_res.get("sprite_state"):
                merged["sprite_state"] = p_res["sprite_state"]
            if not merged["drawdepth"] and p_res.get("drawdepth"):
                merged["drawdepth"] = p_res["drawdepth"]
            if merged["door"] is None and p_res.get("door") is not None:
                merged["door"] = p_res["door"]
            if merged["access"] is None and p_res.get("access") is not None:
                merged["access"] = p_res["access"]
            if merged["camera"] is None and p_res.get("camera") is not None:
                merged["camera"] = p_res["camera"]
            if merged["beacon"] is None and p_res.get("beacon") is not None:
                merged["beacon"] = p_res["beacon"]

        return merged

    print(f"[2/5] Parsing Saltern Station Map ({map_file})...")
    map_data = load_yaml_safe(map_file)
    tilemap = {int(k): v for k, v in map_data.get("tilemap", {}).items()}

    # Decode Grid 31 tiles
    tiles_list = []
    min_x, max_x = 9999, -9999
    min_y, max_y = 9999, -9999

    entities_groups = map_data.get("entities", [])
    for group in entities_groups:
        for ent in group.get("entities", []):
            if ent.get("uid") == 31:
                for comp in ent.get("components", []):
                    if comp.get("type") == "MapGrid":
                        chunks = comp.get("chunks", {})
                        for chunk_key, chunk_val in chunks.items():
                            cx_str, cy_str = chunk_val["ind"].split(",")
                            cx, cy = int(cx_str), int(cy_str)
                            raw = base64.b64decode(chunk_val["tiles"])
                            for ly in range(16):
                                for lx in range(16):
                                    idx = (ly * 16 + lx) * 7
                                    tid, flags, variant, rot = struct.unpack_from("<IBBB", raw, idx)
                                    tname = tilemap.get(tid, "Space")
                                    if tname != "Space":
                                        wx = cx * 16 + lx
                                        wy = cy * 16 + ly
                                        min_x = min(min_x, wx)
                                        max_x = max(max_x, wx)
                                        min_y = min(min_y, wy)
                                        max_y = max(max_y, wy)
                                        tiles_list.append([wx, wy, tname, variant])

    print(f"Decoded {len(tiles_list)} non-space station tiles. Bounds: X=[{min_x}, {max_x}], Y=[{min_y}, {max_y}]")

    # Classify and extract map entities on Grid 31
    walls = []
    windows = []
    doors = []
    cameras = []
    beacons = []
    spawn_points = []
    objects = []

    skip_prefixes = (
        "Cable",
        "GasPipe",
        "DisposalPipe",
        "DisposalTagger",
        "DisposalRouter",
        "DisposalJunction",
        "VentScrubber",
        "GasVent",
        "LightTube",
        "LightSmall",
        "PoweredLight",
        "PoweredSmallLight",
        "EmergencyLight",
        "FloorTileItem",
        "SignDirectional",
        "Effect",
        "Marker",
        "SpawnDungeon",
        "RandomSpawner",
        "LootSpawner",
        "MaintFluff",
        "FilledToolbox",
        "Paper",
        "Trash",
        "Puddle",
        "Decal",
    )

    referenced_protos = set()

    for group in entities_groups:
        proto_id = group.get("proto", "")
        if not proto_id:
            continue
        resolved = resolve_proto(proto_id)

        for ent in group.get("entities", []):
            uid = ent.get("uid")
            comps = ent.get("components", [])
            xform = None
            surv_cam = None
            nav_beacon = None
            meta_name = None

            for c in comps:
                if not isinstance(c, dict):
                    continue
                ct = c.get("type")
                if ct == "Transform":
                    xform = c
                elif ct == "SurveillanceCamera":
                    surv_cam = c
                elif ct == "NavMapBeacon":
                    nav_beacon = c
                elif ct == "MetaData":
                    meta_name = c.get("name")

            if not xform or xform.get("parent") != 31:
                continue

            pos_str = str(xform.get("pos", "0,0"))
            px_s, py_s = pos_str.split(",")
            px, py = float(px_s), float(py_s)

            rot_str = str(xform.get("rot", "0"))
            rot = float(rot_str.replace("rad", "").strip()) if rot_str else 0.0

            # 1. Surveillance Cameras
            if proto_id.startswith("SurveillanceCamera") and not proto_id.startswith("SurveillanceCameraRouter") and not proto_id.startswith("SurveillanceCameraMonitor"):
                cam_id = (surv_cam or {}).get("id") or (resolved.get("camera") or {}).get("id") or f"Cam-{uid}"
                nets = (surv_cam or {}).get("setupAvailableNetworks") or (resolved.get("camera") or {}).get("networks") or ["General"]
                net_name = nets[0].replace("SurveillanceCamera", "") if nets else "General"
                cameras.append({
                    "uid": uid,
                    "id": cam_id,
                    "network": net_name,
                    "proto": proto_id,
                    "x": round(px, 2),
                    "y": round(py, 2),
                    "rot": round(rot, 3),
                })
                referenced_protos.add(proto_id)
                continue

            # 2. Station Beacons (Rooms)
            if proto_id.startswith("DefaultStationBeacon") or nav_beacon or resolved.get("beacon"):
                b_info = nav_beacon or resolved.get("beacon") or {}
                b_text = b_info.get("text") or proto_id.replace("DefaultStationBeacon", "")
                b_color = b_info.get("color", "#4fc3f7")
                if b_text:
                    beacons.append({
                        "uid": uid,
                        "name": b_text,
                        "proto": proto_id,
                        "x": round(px, 2),
                        "y": round(py, 2),
                        "color": b_color,
                    })
                continue

            # 3. Spawn Points
            if proto_id.startswith("SpawnPoint"):
                role = proto_id.replace("SpawnPoint", "")
                spawn_points.append({
                    "uid": uid,
                    "role": role,
                    "proto": proto_id,
                    "x": round(px, 2),
                    "y": round(py, 2),
                })
                continue

            # 4. Walls & Windows & Grilles
            if proto_id.startswith("Wall") or proto_id in ("ReinforcedWall", "WallSolid", "WallReinforced", "WallShuttle", "WallUranium", "WallPlasma", "WallGold", "WallSilver", "WallWood", "WallBrick"):
                walls.append({
                    "uid": uid,
                    "proto": proto_id,
                    "x": round(px, 2),
                    "y": round(py, 2),
                })
                referenced_protos.add(proto_id)
                continue

            if "Window" in proto_id or proto_id.startswith("Grille"):
                windows.append({
                    "uid": uid,
                    "proto": proto_id,
                    "x": round(px, 2),
                    "y": round(py, 2),
                    "rot": round(rot, 3),
                })
                referenced_protos.add(proto_id)
                continue

            # 5. Doors & Airlocks & Windoors
            if proto_id.startswith("Airlock") or proto_id.startswith("Windoor") or proto_id.startswith("Door") or proto_id.startswith("HighSec") or resolved.get("door") is not None:
                if "Note" in proto_id or "Electronics" in proto_id:
                    continue
                access_req = resolved.get("access") or []
                # Flatten access list
                flat_access = []
                if isinstance(access_req, list):
                    for a in access_req:
                        if isinstance(a, list):
                            flat_access.extend(a)
                        elif isinstance(a, str):
                            flat_access.append(a)
                doors.append({
                    "uid": uid,
                    "proto": proto_id,
                    "name": meta_name or resolved.get("name") or proto_id,
                    "x": round(px, 2),
                    "y": round(py, 2),
                    "rot": round(rot, 3),
                    "isGlass": "Glass" in proto_id or "Windoor" in proto_id,
                    "access": flat_access,
                    "open": False,
                    "bolted": False,
                })
                referenced_protos.add(proto_id)
                continue

            # 6. Skip invisible/subfloor pipes & cables
            if any(proto_id.startswith(p) for p in skip_prefixes):
                continue

            # 7. Important station structures, consoles, furniture, lockers, vending machines, medical/engineering/science equipment, items
            drawdepth = resolved.get("drawdepth") or ""
            if drawdepth in ("SubFloor", "BelowFloor", "FloorTiles"):
                continue

            if resolved.get("sprite_path"):
                category = "object"
                if any(k in proto_id for k in ("Computer", "Console", "Radar", "SolarControl", "Communications", "CardId")):
                    category = "console"
                elif any(k in proto_id for k in ("Vending", "SmartFridge", "BoozeDispenser", "SodaDispenser")):
                    category = "vending"
                elif any(k in proto_id for k in ("Table", "Counter", "Rack")):
                    category = "table"
                elif any(k in proto_id for k in ("Chair", "Stool", "Bench", "Sofa", "ComfyChair")):
                    category = "chair"
                elif any(k in proto_id for k in ("Bed", "MedicalBed", "RollerBed", "CryoPod", "CloningPod", "StasisBed")):
                    category = "bed"
                elif any(k in proto_id for k in ("Locker", "Closet", "Crate", "Wardrobe")):
                    category = "locker"
                elif any(k in proto_id for k in ("SMES", "Substation", "APC", "AME", "Generator", "Teg", "Collector", "PA")):
                    category = "power"
                elif any(k in proto_id for k in ("Lathe", "Autolathe", "Protolathe", "ChemMaster", "ChemDispenser", "Microwave", "ReagentGrinder", "Hydroponics", "Anomaly", "Research", "Scanner", "OperatingTable")):
                    category = "machine"
                elif drawdepth in ("SmallObjects", "Items") or any(k in proto_id for k in ("Weapon", "Tool", "Medkit", "Syringe", "Beaker", "Drink", "Food", "PDA", "Box", "Crowbar", "Wrench", "Screwdriver", "Welder", "Multitool", "Analyzer", "Extinguisher", "Flashlight", "Stunbaton", "Mop", "Bucket")):
                    category = "item"

                objects.append({
                    "uid": uid,
                    "proto": proto_id,
                    "name": meta_name or resolved.get("name") or proto_id,
                    "desc": resolved.get("description") or "",
                    "category": category,
                    "x": round(px, 2),
                    "y": round(py, 2),
                    "rot": round(rot, 3),
                })
                referenced_protos.add(proto_id)

    print(
        f"Extracted Saltern entities: {len(walls)} walls, {len(windows)} windows, {len(doors)} doors/airlocks, "
        f"{len(cameras)} surveillance cameras, {len(beacons)} room beacons, {len(spawn_points)} spawn points, {len(objects)} interactive objects/machines."
    )

    # [3/5] Copy referenced textures (.png and .rsi) and build sprite_manifest.json
    print("[3/5] Extracting real SS14 textures for tiles, walls, doors, machines, items, and humanoids...")
    sprite_manifest = {
        "tiles": {},
        "prototypes": {},
        "humanoid": {},
        "job_outfits": {},
    }

    copied_files = set()

    def copy_tex_file(rel_tex_path: str):
        if not rel_tex_path:
            return None
        clean = rel_tex_path.lstrip("/")
        if clean.startswith("Textures/"):
            clean = clean[len("Textures/"):]
        src = tex_root / clean
        if not src.exists():
            return None
        dst = out_root / "textures" / clean
        if clean not in copied_files:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied_files.add(clean)
        return f"/assets/textures/{clean}"

    def copy_rsi_state(rsi_path: str, preferred_state: str = None):
        if not rsi_path:
            return None
        clean = rsi_path.lstrip("/")
        if clean.startswith("Textures/"):
            clean = clean[len("Textures/"):]
        if clean.endswith(".png"):
            url = copy_tex_file(clean)
            if url:
                return {"url": url, "size": [32, 32], "directions": 1, "frames": 1}
            return None

        if not clean.endswith(".rsi"):
            # Could be folder/state.rsi/state
            if ".rsi/" in clean:
                parts = clean.split(".rsi/")
                clean = parts[0] + ".rsi"
                if not preferred_state:
                    preferred_state = parts[1]
            else:
                clean = clean + ".rsi"

        rsi_dir = tex_root / clean
        if not rsi_dir.exists() or not rsi_dir.is_dir():
            return None

        meta_path = rsi_dir / "meta.json"
        meta = {}
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = {}

        size = [meta.get("size", {}).get("x", 32), meta.get("size", {}).get("y", 32)]
        states = meta.get("states", [])

        # Choose state
        chosen_state = None
        candidates = [preferred_state, "icon", "closed", "full", "solid0", "on", "normal", "base", "unlit", "equipped-INNERCLOTHING", "inhand-left"]
        state_map = {s.get("name"): s for s in states if isinstance(s, dict) and s.get("name")}

        for c in candidates:
            if c and c in state_map and (rsi_dir / f"{c}.png").exists():
                chosen_state = state_map[c]
                break

        if not chosen_state and states:
            for s in states:
                sname = s.get("name")
                if sname and (rsi_dir / f"{sname}.png").exists():
                    chosen_state = s
                    break

        if not chosen_state:
            # Fallback to any png in rsi_dir
            pngs = list(rsi_dir.glob("*.png"))
            if not pngs:
                return None
            sname = pngs[0].stem
            chosen_state = {"name": sname, "directions": 1}

        sname = chosen_state["name"]
        rel_png = f"{clean}/{sname}.png"
        url = copy_tex_file(rel_png)
        if not url:
            return None

        # Also copy open/closed states for doors if available
        extra_states = {}
        for extra_name in ("open", "closed", "opening", "closing", "panel_open", "unlit", "off", "on", "active", "broken"):
            if (rsi_dir / f"{extra_name}.png").exists():
                extra_url = copy_tex_file(f"{clean}/{extra_name}.png")
                if extra_url:
                    extra_states[extra_name] = extra_url

        delays = chosen_state.get("delays", [[1.0]])
        frames = len(delays[0]) if delays and isinstance(delays[0], list) else 1

        return {
            "url": url,
            "state": sname,
            "size": size,
            "directions": chosen_state.get("directions", 1),
            "frames": max(1, frames),
            "extra": extra_states,
        }

    # Copy tile textures
    used_tile_names = set(t[2] for t in tiles_list)
    for tname in used_tile_names:
        tproto = tile_protos.get(tname)
        if tproto and tproto.get("sprite"):
            url = copy_tex_file(tproto["sprite"])
            if url:
                sprite_manifest["tiles"][tname] = {"url": url, "size": [32, 32]}

    # Copy prototype textures
    for pid in referenced_protos:
        res = resolve_proto(pid)
        sp_path = res.get("sprite_path")
        sp_state = res.get("sprite_state")
        if sp_path:
            info = copy_rsi_state(sp_path, sp_state)
            if info:
                sprite_manifest["prototypes"][pid] = info

    # Copy Humanoid species body parts & job uniforms/clothing/icons for character rendering
    human_parts = [
        ("body_m", "Mobs/Species/Human/parts.rsi", "full"),
        ("head_m", "Mobs/Species/Human/parts.rsi", "head_m"),
        ("head_f", "Mobs/Species/Human/parts.rsi", "head_f"),
        ("torso_m", "Mobs/Species/Human/parts.rsi", "torso_m"),
        ("torso_f", "Mobs/Species/Human/parts.rsi", "torso_f"),
        ("l_arm", "Mobs/Species/Human/parts.rsi", "l_arm"),
        ("r_arm", "Mobs/Species/Human/parts.rsi", "r_arm"),
        ("l_hand", "Mobs/Species/Human/parts.rsi", "l_hand"),
        ("r_hand", "Mobs/Species/Human/parts.rsi", "r_hand"),
        ("l_leg", "Mobs/Species/Human/parts.rsi", "l_leg"),
        ("r_leg", "Mobs/Species/Human/parts.rsi", "r_leg"),
        ("l_foot", "Mobs/Species/Human/parts.rsi", "l_foot"),
        ("r_foot", "Mobs/Species/Human/parts.rsi", "r_foot"),
    ]
    for key, rpath, rstate in human_parts:
        info = copy_rsi_state(rpath, rstate)
        if info:
            sprite_manifest["humanoid"][key] = info

    # Copy Job Jumpsuits & Hats equipped-INNERCLOTHING / equipped-HELMET / equipped-OUTERCLOTHING
    job_outfit_rsis = {
        "Captain": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Command/captain.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Hats/captain.rsi", "equipped-HELMET"),
            "outer": ("Clothing/OuterClothing/Armor/captain_carapace.rsi", "equipped-OUTERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "Captain"),
            "color": "#ffd700",
            "dept": "Command",
        },
        "HeadOfPersonnel": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Command/hop.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Hats/hopcap.rsi", "equipped-HELMET"),
            "icon": ("Interface/Misc/job_icons.rsi", "HeadOfPersonnel"),
            "color": "#38bdf8",
            "dept": "Command",
        },
        "HeadOfSecurity": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Security/hos.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Hats/hoshat.rsi", "equipped-HELMET"),
            "outer": ("Clothing/OuterClothing/Coats/hos_trenchcoat.rsi", "equipped-OUTERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "HeadOfSecurity"),
            "color": "#ef4444",
            "dept": "Security",
        },
        "SecurityOfficer": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Security/security.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Helmets/security.rsi", "equipped-HELMET"),
            "outer": ("Clothing/OuterClothing/Vests/armor.rsi", "equipped-OUTERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "SecurityOfficer"),
            "color": "#f87171",
            "dept": "Security",
        },
        "Warden": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Security/warden.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Hats/warden.rsi", "equipped-HELMET"),
            "icon": ("Interface/Misc/job_icons.rsi", "Warden"),
            "color": "#dc2626",
            "dept": "Security",
        },
        "Detective": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Security/detective.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Hats/brownfedora.rsi", "equipped-HELMET"),
            "outer": ("Clothing/OuterClothing/Coats/detective.rsi", "equipped-OUTERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "Detective"),
            "color": "#b45309",
            "dept": "Security",
        },
        "ChiefEngineer": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Engineering/ce.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Hardhats/white.rsi", "equipped-HELMET"),
            "icon": ("Interface/Misc/job_icons.rsi", "ChiefEngineer"),
            "color": "#f59e0b",
            "dept": "Engineering",
        },
        "StationEngineer": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Engineering/engineering.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Hardhats/yellow.rsi", "equipped-HELMET"),
            "icon": ("Interface/Misc/job_icons.rsi", "StationEngineer"),
            "color": "#fbbf24",
            "dept": "Engineering",
        },
        "AtmosphericTechnician": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Engineering/atmos.rsi", "equipped-INNERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "AtmosphericTechnician"),
            "color": "#38bdf8",
            "dept": "Engineering",
        },
        "ChiefMedicalOfficer": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Medical/cmo.rsi", "equipped-INNERCLOTHING"),
            "outer": ("Clothing/OuterClothing/Coats/cmo.rsi", "equipped-OUTERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "ChiefMedicalOfficer"),
            "color": "#06b6d4",
            "dept": "Medical",
        },
        "MedicalDoctor": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Medical/medical.rsi", "equipped-INNERCLOTHING"),
            "outer": ("Clothing/OuterClothing/Coats/labcoat.rsi", "equipped-OUTERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "MedicalDoctor"),
            "color": "#22d3ee",
            "dept": "Medical",
        },
        "Chemist": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Medical/chemistry.rsi", "equipped-INNERCLOTHING"),
            "outer": ("Clothing/OuterClothing/Coats/labcoat_chem.rsi", "equipped-OUTERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "Chemist"),
            "color": "#fb923c",
            "dept": "Medical",
        },
        "Paramedic": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Medical/paramedic.rsi", "equipped-INNERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "Paramedic"),
            "color": "#34d399",
            "dept": "Medical",
        },
        "ResearchDirector": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Science/rnd.rsi", "equipped-INNERCLOTHING"),
            "outer": ("Clothing/OuterClothing/Coats/labcoat_rd.rsi", "equipped-OUTERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "ResearchDirector"),
            "color": "#c084fc",
            "dept": "Science",
        },
        "Scientist": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Science/scientist.rsi", "equipped-INNERCLOTHING"),
            "outer": ("Clothing/OuterClothing/Coats/labcoat_sci.rsi", "equipped-OUTERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "Scientist"),
            "color": "#a855f7",
            "dept": "Science",
        },
        "Quartermaster": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Cargo/qm.rsi", "equipped-INNERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "QuarterMaster"),
            "color": "#d97706",
            "dept": "Cargo",
        },
        "CargoTechnician": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Cargo/cargotech.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Soft/cargosoft.rsi", "equipped-HELMET"),
            "icon": ("Interface/Misc/job_icons.rsi", "CargoTechnician"),
            "color": "#f59e0b",
            "dept": "Cargo",
        },
        "SalvageSpecialist": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Cargo/salvage.rsi", "equipped-INNERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "ShaftMiner"),
            "color": "#b45309",
            "dept": "Cargo",
        },
        "Bartender": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Service/bartender.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Hats/tophat.rsi", "equipped-HELMET"),
            "icon": ("Interface/Misc/job_icons.rsi", "Bartender"),
            "color": "#10b981",
            "dept": "Service",
        },
        "Chef": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Service/chef.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Hats/chef.rsi", "equipped-HELMET"),
            "icon": ("Interface/Misc/job_icons.rsi", "Chef"),
            "color": "#4ade80",
            "dept": "Service",
        },
        "Botanist": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Service/hydro.rsi", "equipped-INNERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "Botanist"),
            "color": "#22c55e",
            "dept": "Service",
        },
        "Janitor": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Service/janitor.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Soft/purplesoft.rsi", "equipped-HELMET"),
            "icon": ("Interface/Misc/job_icons.rsi", "Janitor"),
            "color": "#d946ef",
            "dept": "Service",
        },
        "Clown": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Service/clown.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Mask/clown.rsi", "equipped-MASK"),
            "icon": ("Interface/Misc/job_icons.rsi", "Clown"),
            "color": "#f43f5e",
            "dept": "Service",
        },
        "Mime": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Service/mime.rsi", "equipped-INNERCLOTHING"),
            "head": ("Clothing/Head/Hats/beret_french.rsi", "equipped-HELMET"),
            "icon": ("Interface/Misc/job_icons.rsi", "Mime"),
            "color": "#e2e8f0",
            "dept": "Service",
        },
        "Chaplain": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Service/chaplain.rsi", "equipped-INNERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "Chaplain"),
            "color": "#94a3b8",
            "dept": "Service",
        },
        "Passenger": {
            "jumpsuit": ("Clothing/Uniforms/Jumpsuits/Civilian/casual.rsi", "equipped-INNERCLOTHING"),
            "icon": ("Interface/Misc/job_icons.rsi", "Passenger"),
            "color": "#9ca3af",
            "dept": "Civilian",
        },
    }

    for job_name, outfit_cfg in job_outfit_rsis.items():
        entry = {"color": outfit_cfg["color"], "dept": outfit_cfg["dept"], "layers": {}}
        for slot in ("jumpsuit", "head", "outer", "icon"):
            if slot in outfit_cfg:
                rpath, rstate = outfit_cfg[slot]
                info = copy_rsi_state(rpath, rstate)
                if info:
                    entry["layers"][slot] = info
        sprite_manifest["job_outfits"][job_name] = entry

    # Also copy speech bubble & status effect textures
    for eff_key, eff_path, eff_state in [
        ("speech", "Effects/speech.rsi", "typing"),
        ("say", "Effects/speech.rsi", "say0"),
        ("exclamation", "Effects/speech.rsi", "say1"),
        ("question", "Effects/speech.rsi", "say2"),
    ]:
        info = copy_rsi_state(eff_path, eff_state)
        if info:
            sprite_manifest["humanoid"][eff_key] = info

    print(f"[4/5] Writing {out_root / 'maps/saltern.json'} and {out_root / 'sprite_manifest.json'}...")
    saltern_payload = {
        "stationName": "NSS Saltern (Space Station 14)",
        "mapId": "Saltern",
        "bounds": {
            "minX": min_x,
            "maxX": max_x,
            "minY": min_y,
            "maxY": max_y,
        },
        "tiles": tiles_list,
        "walls": walls,
        "windows": windows,
        "doors": doors,
        "cameras": cameras,
        "beacons": beacons,
        "spawnPoints": spawn_points,
        "objects": objects,
    }

    with open(out_root / "maps" / "saltern.json", "w", encoding="utf-8") as f:
        json.dump(saltern_payload, f, separators=(",", ":"))

    with open(out_root / "sprite_manifest.json", "w", encoding="utf-8") as f:
        json.dump(sprite_manifest, f, indent=2)

    with open(out_root / "prototypes" / "jobs.json", "w", encoding="utf-8") as f:
        json.dump({"jobs": job_protos, "startingGears": starting_gears}, f, indent=2)

    print(f"[5/5] Done! Copied {len(copied_files)} real SS14 texture files into {out_root / 'textures'}.")


if __name__ == "__main__":
    main()
