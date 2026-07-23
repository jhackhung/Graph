import argparse
import json
import math
import os
import random
import sys
import numpy as np
import networkx as nx

from Save_And_Read_Graphs import save_graph_sequence_to_txt
from Save_And_Read_Graphs import load_graph_sequence_from_txt
from Debug import are_graphs_equal

EARTH_RADIUS_KM = 6371.0
MIN_ELEVATION_ANGLE = 30.0
REMOTE_AREA_MIN_DIST_KM = 500.0

def get_cost_traffic_by_distance(p1, p2, u_type, v_type, base_cost_per_km=0.001):
    dist_km = float(math.dist(p1, p2))
    dist_factor = (dist_km / 10.0)

    multiplier = 1.0
    if u_type == "satellite" and v_type == "satellite":
        multiplier = 1.0 
    elif "cloud" in (u_type, v_type) and "satellite" not in (u_type, v_type):
        multiplier = 0.5 
    elif "satellite" in (u_type, v_type):
        multiplier = 1.2 
    
    cost = dist_factor * base_cost_per_km * multiplier 
    return max(cost, 1e-9)

def add_edge_with_cost(G, u, v, latency, bandwidth, penalty_mult=1.0):
    p1 = G.nodes[u]["pos"]
    p2 = G.nodes[v]["pos"]
    u_type = G.nodes[u]["type"]
    v_type = G.nodes[v]["type"]
    
    cost_traffic = get_cost_traffic_by_distance(p1, p2, u_type, v_type)
    
    cost_traffic *= penalty_mult
    
    G.add_edge(
        u, v,
        latency=latency,
        bandwidth=bandwidth,
        used_bandwidth=0,
        cost_traffic=cost_traffic,
        virtual=False
    )

def euclid_latency(p1, p2):
    return float(math.dist(p1, p2))

def realistic_latency(p1, p2, u_type, v_type, bin_size_ms=5.0):
    distance_km = float(math.dist(p1, p2))
    d = distance_km * 1000.0
    
    if u_type == "cloud" and v_type == "cloud":
        speed = 2e8 
    else:
        speed = 3e8 
        
    prop_delay = d / speed * 1000.0
    
    if u_type == "satellite" and v_type == "satellite":
        proc_delay = 1.0
    elif "cloud" in (u_type, v_type):
        proc_delay = 0.5
    else:
        proc_delay = 0.2
        
    total_latency = prop_delay + proc_delay

    if bin_size_ms > 0:
        total_latency = round(total_latency / bin_size_ms) * bin_size_ms
        total_latency = max(total_latency, bin_size_ms)

    return total_latency

def get_elevation_angle(p_ground, p_sat):
    norm_p_ground = np.linalg.norm(p_ground)
    if norm_p_ground == 0: return -90.0
    vec_zenith = np.array(p_ground) / norm_p_ground
    vec_gnd_to_sat = np.array(p_sat) - np.array(p_ground)
    norm_vec_gnd_to_sat = np.linalg.norm(vec_gnd_to_sat)
    if norm_vec_gnd_to_sat == 0: return 90.0
    dot_product = np.dot(vec_zenith, vec_gnd_to_sat)
    cos_zenith_angle = max(-1.0, min(1.0, dot_product / norm_vec_gnd_to_sat))
    zenith_angle_rad = np.arccos(cos_zenith_angle)
    elevation_rad = (np.pi / 2.0) - zenith_angle_rad
    return np.degrees(elevation_rad)

def is_earth_blocking(p1, p2, earth_radius=EARTH_RADIUS_KM):
    p1 = np.array(p1)
    p2 = np.array(p2)
    v = p2 - p1
    norm_v_sq = np.dot(v, v)
    if norm_v_sq == 0: return False
    u = -p1
    t = np.dot(u, v) / norm_v_sq
    if 0 <= t <= 1:
        closest_point = p1 + t * v
        if np.linalg.norm(closest_point) < earth_radius:
            return True
    return False

def force_connect_ground(G, ground, sats):
    if not sats: return
    sats_sorted = sorted(
        sats,
        key=lambda s: euclid_latency(G.nodes[ground]["pos"], G.nodes[s]["pos"])
    )[:2]
    
    for s in sats_sorted:
        add_edge_with_cost(G, ground, s, latency=1, bandwidth=1000, penalty_mult=10.0)
        add_edge_with_cost(G, s, ground, latency=1, bandwidth=1000, penalty_mult=10.0)

def ensure_strongly_connected(G):
    UG = G.to_undirected()
    comps = list(nx.connected_components(UG))
    if len(comps) <= 1: return
    
    comps = [list(c) for c in comps]
    comps.sort(key=lambda x: min(x))
    
    for i in range(len(comps) - 1):
        A = comps[i]
        B = comps[i + 1]
        best_dist = float("inf")
        best_pair = None
        
        for u in A:
            for v in B:
                d = euclid_latency(G.nodes[u]["pos"], G.nodes[v]["pos"])
                if d < best_dist:
                    best_dist = d
                    best_pair = (u, v)
        
        if best_pair:
            u, v = best_pair
            add_edge_with_cost(G, u, v, latency=1, bandwidth=1000, penalty_mult=10.0)
            add_edge_with_cost(G, v, u, latency=1, bandwidth=1000, penalty_mult=10.0)

def generate_walker_meta(num_sats_total=60, num_planes=6, altitude_km=550.0, inclination_deg=53.0, f_phasing_param=0, base_angular_velocity=0.2):
    radius_km = EARTH_RADIUS_KM + altitude_km
    inclination_rad = math.radians(inclination_deg)
    satellites_meta = []
    
    FIXED_SLOT_SPACING_DEG = 360.0 / 20.0 
    
    for i in range(num_sats_total):
        p_idx = i % num_planes
        k_idx = i // num_planes
        
        raan_rad = math.radians(p_idx * (360.0 / num_planes))
        phase_in_plane = math.radians(k_idx * FIXED_SLOT_SPACING_DEG)
        
        total_slots_theoretical = num_planes * (360.0 / FIXED_SLOT_SPACING_DEG) 
        phase_offset = math.radians(f_phasing_param * (p_idx * 360.0 / total_slots_theoretical))
        
        phi0 = phase_in_plane + phase_offset
        
        meta = dict(
            type="satellite",
            mobile=True,
            orbit=dict(
                r=radius_km, 
                inc=inclination_rad, 
                raan=raan_rad, 
                w=base_angular_velocity,
                orbit_id=p_idx, 
                id_in_plane=k_idx
            ),
            phi0=phi0,
        )
        satellites_meta.append(meta)
        
    return satellites_meta

def get_pos(meta, t):
    if not meta["mobile"]: return meta["pos0"]
    if "orbit" in meta and meta["orbit"] is not None:
        orb = meta["orbit"]
        r, inc, raan, w = orb["r"], orb["inc"], orb["raan"], orb["w"]
        
        phi_t = meta["phi0"] + w * t
        
        x_orb = r * np.cos(phi_t)
        y_orb = r * np.sin(phi_t)
        
        x_rot_i = x_orb
        y_rot_i = y_orb * np.cos(inc)
        z_rot_i = y_orb * np.sin(inc)
        
        x = x_rot_i * np.cos(raan) - y_rot_i * np.sin(raan)
        y = x_rot_i * np.sin(raan) + y_rot_i * np.cos(raan)
        z = z_rot_i
        return x, y, z
    raise ValueError(f"Invalid mobile node without orbit info: {meta}")

def _sample_edge_bw(avg, rng, lower_ratio=0.4, upper_ratio=1.8, min_bw=10):
    return 1000

def _assign_regions_to_dests(G, dests, pos, thr):
    H = nx.Graph()
    H.add_nodes_from(dests)
    for i in range(len(dests)):
        for j in range(i + 1, len(dests)):
            di, dj = dests[i], dests[j]
            if euclid_latency(pos[di], pos[dj]) <= thr:
                H.add_edge(di, dj)
    regions = {}
    comps = list(nx.connected_components(H))
    comps.sort(key=lambda c: min(c))
    for ridx, comp in enumerate(comps):
        rid = f"R{ridx}"
        members = sorted(list(comp))
        coords = np.array([pos[n] for n in members], dtype=float)
        centroid = tuple(coords.mean(axis=0))
        regions[rid] = {"members": members, "centroid": centroid}
        for n in members:
            G.nodes[n]["region"] = rid
    G.graph["regions"] = regions

def generate_graph_sequence_realistic(
    n_sats=60, n_clouds=10, n_srcs=5, n_dests=25, total_time=10, seed=42,
    num_planes=6, altitude_km=550.0, inclination_deg=53.0, f_phasing_param=0,
    base_angular_velocity=0.05, thr_cloud_to_cloud=2000.0, region_dist_thr=1000.0
):
    rng = random.Random(seed)
    rng_node = random.Random(seed + 99991)
    np.random.seed(seed)
    # debug
    pos_seed = seed - 42
    rng_src_pos = random.Random(pos_seed + 1001)
    rng_dest_pos = random.Random(pos_seed + 2002)
    rng_cloud_pos = random.Random(pos_seed + 3003)

    def _gen_random_sphere_pos(generator):
        lat_rad = math.radians(generator.uniform(-70, 70))
        lon_rad = math.radians(generator.uniform(-180, 180))
        x = EARTH_RADIUS_KM * np.cos(lat_rad) * np.cos(lon_rad)
        y = EARTH_RADIUS_KM * np.cos(lat_rad) * np.sin(lon_rad)
        z = EARTH_RADIUS_KM * np.sin(lat_rad)
        return (x, y, z)
    
    def _xyz_to_latlon(p):
        x, y, z = p
        lat = math.asin(z / EARTH_RADIUS_KM)
        lon = math.atan2(y, x)
        return lat, lon

    def _latlon_to_xyz(lat, lon):
        x = EARTH_RADIUS_KM * math.cos(lat) * math.cos(lon)
        y = EARTH_RADIUS_KM * math.cos(lat) * math.sin(lon)
        z = EARTH_RADIUS_KM * math.sin(lat)
        return (x, y, z)

    def _gen_remote_centroid(generator, avoid_list, min_dist_km):
        while True:
            lat_rad = math.radians(generator.uniform(0, 50)) 
            lon_rad = math.radians(generator.uniform(0, 120))
            x = EARTH_RADIUS_KM * np.cos(lat_rad) * np.cos(lon_rad)
            y = EARTH_RADIUS_KM * np.cos(lat_rad) * np.sin(lon_rad)
            z = EARTH_RADIUS_KM * np.sin(lat_rad)
            c = (x, y, z)
            
            if all(math.dist(c, p) >= min_dist_km for p in avoid_list):
                return c

    def _gen_remote_dest_clusters(generator, avoid_list, n_dests, min_dist_km, K=3, spread_km=200.0):
        spread_deg = (spread_km / EARTH_RADIUS_KM) * (180.0 / math.pi)
        centroids = [_gen_remote_centroid(generator, avoid_list, min_dist_km) for _ in range(K)]

        counts = [n_dests // K] * K
        for i in range(n_dests % K):
            counts[i] += 1

        dests = []
        for c, cnt in zip(centroids, counts):
            lat0, lon0 = _xyz_to_latlon(c)
            for _ in range(cnt):
                dlat = math.radians(generator.uniform(-spread_deg, spread_deg))
                dlon = math.radians(generator.uniform(-spread_deg, spread_deg))
                lat = max(math.radians(-70), min(math.radians(70), lat0 + dlat))
                lon = lon0 + dlon
                dests.append(_latlon_to_xyz(lat, lon))
        return dests

    fixed_cloud_coords = []
    for _ in range(n_clouds):
        fixed_cloud_coords.append(_gen_random_sphere_pos(rng_cloud_pos))

    fixed_src_coords = []
    for _ in range(n_srcs):
        fixed_src_coords.append(_gen_random_sphere_pos(rng_src_pos))

    avoid_list = fixed_cloud_coords + fixed_src_coords

    K = max(2, min(5, n_dests // 5)) 
    fixed_dest_coords = _gen_remote_dest_clusters(
        generator=rng_dest_pos,
        avoid_list=avoid_list,
        n_dests=n_dests,
        min_dist_km=REMOTE_AREA_MIN_DIST_KM,
        K=K,
        spread_km=1000.0, 
    )

    src_iter = iter(fixed_src_coords)
    dest_iter = iter(fixed_dest_coords)
    cloud_iter = iter(fixed_cloud_coords)
        
    nodes_meta = []

    if n_sats > 0:
        sat_metas_list = generate_walker_meta(
            num_sats_total=n_sats,
            num_planes=num_planes,
            altitude_km=altitude_km,
            inclination_deg=inclination_deg,
            f_phasing_param=f_phasing_param,
            base_angular_velocity=base_angular_velocity
        )
    else:
        sat_metas_list = []
    sat_meta_iter = iter(sat_metas_list)

    node_types = (["cloud"] * n_clouds + ["src"] * n_srcs + ["dest"] * n_dests + ["satellite"] * n_sats)

    for idx, n_type in enumerate(node_types):
        name = f"v{idx}"

        if n_type == "satellite":
            meta = next(sat_meta_iter)
            meta["name"] = name
            meta["bandwidth"] = 0

            meta["storage_model"] = "concave"
            meta["d"] = round(rng_node.uniform(0.5, 1.5), 5)
            meta["z"] = 0.8
            meta["gamma"] = 1.5                                      
            meta["cache"] = (rng_node.random() < 0.6)                
            meta["capacity"] = round(rng_node.uniform(500, 1500), 2)
            meta["req_size"] = 0.0
            meta["data_size"] = 0.0

        elif n_type in ("src", "dest", "cloud"):
            if n_type == "src":
                pos0 = next(src_iter)
                bw = rng_node.randint(3, 5)
            elif n_type == "dest":
                pos0 = next(dest_iter)
                bw = 0
            else:
                pos0 = next(cloud_iter)
                bw = 0

            meta = dict(name=name, type=n_type, mobile=False, orbit=None, pos0=pos0, bandwidth=bw)

            if n_type == "dest":
                meta["req_size"] = round(rng_node.uniform(200, 800), 2)
                meta["storage_model"] = None
                meta["d"] = 0.0
                meta["z"] = 0.0
                meta["gamma"] = 0.0
                meta["cache"] = False
                meta["capacity"] = 0.0
                meta["data_size"] = 0.0

            elif n_type == "cloud":
                meta["storage_model"] = "linear"
                meta["d"] = round(rng_node.uniform(1.0, 3.0), 5)
                meta["z"] = 1.0
                meta["gamma"] = 1.0
                meta["cache"] = True
                meta["capacity"] = round(rng_node.uniform(5000, 20000), 2)
                meta["req_size"] = 0.0
                meta["data_size"] = 0.0

            elif n_type == "src":
                meta["data_size"] = 1.0
                meta["req_size"] = 0.0
                meta["storage_model"] = None
                meta["d"] = 0.0
                meta["z"] = 0.0
                meta["gamma"] = 0.0
                meta["cache"] = False
                meta["capacity"] = 0.0

        nodes_meta.append(meta)

    graph_seq = []
    for t in range(total_time):
        G = nx.DiGraph(time=t)
        
        for meta in nodes_meta:
            p = get_pos(meta, t)
            node_type = meta["type"]

            G.add_node(
                meta["name"],
                type=node_type,
                time=t,
                pos=p,
                bandwidth=meta.get("bandwidth", 0),
                storage_model=meta.get("storage_model", None),
                d=meta.get("d", 0.0),
                z=meta.get("z", 0.0),
                gamma=meta.get("gamma", 0.0),
                req_size=meta.get("req_size", 0.0),
                capacity=meta.get("capacity", 0.0),
                storage_used=0.0,  
                orbit_id=(meta["orbit"]["orbit_id"] if meta.get("orbit") else None),
                orbit_id_in_plane=(meta["orbit"]["id_in_plane"] if meta.get("orbit") else None),
                cache=meta.get("cache", False),
            )
            if node_type == "src":
                G.nodes[meta["name"]]["data_size"] = meta.get("data_size", 1.0)

        srcs = [n for n, d in G.nodes(data=True) if d["type"] == "src"]
        dests = [n for n, d in G.nodes(data=True) if d["type"] == "dest"]
        sats = [n for n, d in G.nodes(data=True) if d["type"] == "satellite"]
        clouds = [n for n, d in G.nodes(data=True) if d["type"] == "cloud"]
        pos = {n: G.nodes[n]["pos"] for n in G.nodes}
        
        src_bws = [G.nodes[s]["bandwidth"] for s in srcs]
        avg_src_bw = (sum(src_bws) / len(src_bws)) if src_bws else 10
        _assign_regions_to_dests(G, dests, pos, region_dist_thr)

        ground_stations = srcs + dests + clouds

        for gnd_node in ground_stations:
            for sat_node in sats:
                if get_elevation_angle(pos[gnd_node], pos[sat_node]) > MIN_ELEVATION_ANGLE:
                    bw = _sample_edge_bw(avg_src_bw * 20, rng, 0.8, 1.2)
                    lat_gs = realistic_latency(pos[gnd_node], pos[sat_node], G.nodes[gnd_node]["type"], G.nodes[sat_node]["type"])
                    add_edge_with_cost(G, gnd_node, sat_node, lat_gs, bw)
                    
                    lat_sg = realistic_latency(pos[sat_node], pos[gnd_node], G.nodes[sat_node]["type"], G.nodes[gnd_node]["type"])
                    add_edge_with_cost(G, sat_node, gnd_node, lat_sg, bw)

        sats_by_plane = {}
        for s in sats:
            orb_id = G.nodes[s]["orbit_id"]
            sats_by_plane.setdefault(orb_id, []).append(s)
        sorted_plane_ids = sorted(sats_by_plane.keys())
        num_planes_actual = len(sorted_plane_ids)

        for p_idx_key, p_id in enumerate(sorted_plane_ids):
            plane_sats = sorted(sats_by_plane[p_id], key=lambda n: G.nodes[n]["orbit_id_in_plane"])
            num_sats_in_plane = len(plane_sats)
            for k_idx, sat_a in enumerate(plane_sats):
                if len(plane_sats) > 1:
                    sat_b_intra = plane_sats[(k_idx + 1) % num_sats_in_plane]
                    if not G.has_edge(sat_a, sat_b_intra) and not is_earth_blocking(pos[sat_a], pos[sat_b_intra]):
                        bw = _sample_edge_bw(avg_src_bw * 50, rng, 0.8, 1.2)
                        lat_ab = realistic_latency(pos[sat_a], pos[sat_b_intra], "satellite", "satellite")
                        lat_ba = realistic_latency(pos[sat_b_intra], pos[sat_a], "satellite", "satellite")
                        add_edge_with_cost(G, sat_a, sat_b_intra, lat_ab, bw)
                        add_edge_with_cost(G, sat_b_intra, sat_a, lat_ba, bw)
                
                if num_planes_actual > 1:
                    adj_plane_id = sorted_plane_ids[(p_idx_key + 1) % num_planes_actual]
                    adj_plane_sats = sorted(sats_by_plane[adj_plane_id], key=lambda n: G.nodes[n]["orbit_id_in_plane"])
                    if k_idx < len(adj_plane_sats):
                        sat_b_inter = adj_plane_sats[k_idx]
                        if not G.has_edge(sat_a, sat_b_inter) and not is_earth_blocking(pos[sat_a], pos[sat_b_inter]):
                            bw = _sample_edge_bw(avg_src_bw * 50, rng, 0.8, 1.2)
                            lat_ab = realistic_latency(pos[sat_a], pos[sat_b_inter], "satellite", "satellite")
                            lat_ba = realistic_latency(pos[sat_b_inter], pos[sat_a], "satellite", "satellite")
                            add_edge_with_cost(G, sat_a, sat_b_inter, lat_ab, bw)
                            add_edge_with_cost(G, sat_b_inter, sat_a, lat_ba, bw)

        for i in range(len(clouds)):
            for j in range(i + 1, len(clouds)):
                a, b = clouds[i], clouds[j]
                dist_km = euclid_latency(pos[a], pos[b])
                if dist_km <= thr_cloud_to_cloud:
                    bw = _sample_edge_bw(avg_src_bw * 10, rng, 0.8, 1.2)
                    lat_ab = realistic_latency(pos[a], pos[b], "cloud", "cloud")
                    lat_ba = realistic_latency(pos[b], pos[a], "cloud", "cloud")
                    add_edge_with_cost(G, a, b, lat_ab, bw)
                    add_edge_with_cost(G, b, a, lat_ba, bw)

        for s in srcs:
            for c in clouds:
                dist_km = euclid_latency(pos[s], pos[c])
                if dist_km <= thr_cloud_to_cloud:
                    bw = _sample_edge_bw(avg_src_bw * 5, rng, 0.8, 1.2)
                    lat_sc = realistic_latency(pos[s], pos[c], "src", "cloud")
                    lat_cs = realistic_latency(pos[c], pos[s], "cloud", "src")
                    add_edge_with_cost(G, s, c, lat_sc, bw)
                    add_edge_with_cost(G, c, s, lat_cs, bw)
                    
        backbone_nodes = sats + clouds
        if backbone_nodes: 
            for s in srcs:
                if G.out_degree(s) == 0:
                    force_connect_ground(G, s, sats) 
                    if G.out_degree(s) == 0:
                        closest = min(backbone_nodes, key=lambda n: euclid_latency(pos[s], pos[n]))
                        add_edge_with_cost(G, s, closest, latency=1, bandwidth=1000, penalty_mult=10.0)
                        add_edge_with_cost(G, closest, s, latency=1, bandwidth=1000, penalty_mult=10.0)

            for d in dests:
                if G.out_degree(d) == 0 or G.in_degree(d) == 0:
                     force_connect_ground(G, d, sats)
                     if G.out_degree(d) == 0:
                        closest = min(backbone_nodes, key=lambda n: euclid_latency(pos[d], pos[n]))
                        add_edge_with_cost(G, d, closest, latency=1, bandwidth=1000, penalty_mult=10.0)
                        add_edge_with_cost(G, closest, d, latency=1, bandwidth=1000, penalty_mult=10.0)

        ensure_strongly_connected(G)
        graph_seq.append(G)
        
    return graph_seq
        
def main():
    if len(sys.argv) < 2:
        print("使用方法: python main.py <config.json> [excel_name.xlsx]")
        sys.exit(1)

    config_path = sys.argv[1]

    with open(config_path, "r") as f:
        cfg = json.load(f)

    dir_path = "output_graphs"
    os.makedirs(dir_path, exist_ok=True)
    txt_count = len([f for f in os.listdir(dir_path) if f.endswith(".txt")])
    
    graphs = generate_graph_sequence_realistic(
        seed=cfg["seed_offset"],
        n_sats=cfg["n_sats"],
        n_clouds=cfg["n_clouds"],
        n_srcs=cfg["n_srcs"],
        n_dests=cfg["n_dests"],
        total_time=cfg["total_time"],
        num_planes=cfg["num_planes"],
        altitude_km=cfg["altitude_km"],
        inclination_deg=cfg["inclination_deg"],
        f_phasing_param=cfg["f_phasing_param"],
        base_angular_velocity=cfg["base_angular_velocity"],
        thr_cloud_to_cloud=cfg["thr_cloud_to_cloud"],
        region_dist_thr=cfg["region_dist_thr"]
    )
    
    print(f"成功生成 {len(graphs)} 個時間步的圖形。")
    if graphs:
        G0 = graphs[0]
        print(f"\n--- 圖形 t=0 資訊 ---")
        print(f"節點總數: {G0.number_of_nodes()}")
        print(f"邊總數: {G0.number_of_edges()}")
        
        n_sats = len([n for n, d in G0.nodes(data=True) if d['type'] == 'satellite'])
        print(f"  - 衛星 (Satellites): {n_sats}")
        
        is_strong = nx.is_strongly_connected(G0)
        is_weak = nx.is_connected(G0.to_undirected())
        print(f"Strongly Connected: {is_strong}")
        print(f"Weakly Connected: {is_weak}")
        
        if not is_strong:
            print("警告：圖形並非強連通，STARFRONT 可能會報錯。")

    save_graph_sequence_to_txt(graph_seq=graphs)

if __name__ == "__main__":
    main()