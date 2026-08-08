"""
Quick tester for the CV service — prints a readable summary (not the 478-point dump).
Usage (venv active, service running on :8000):
    python test_analyze.py you.png her.png
Full JSON is saved to last_result.json.
"""
import sys, json, base64, requests


def b64(path):
    ext = "png" if path.lower().endswith(".png") else "jpeg"
    return f"data:image/{ext};base64," + base64.b64encode(open(path, "rb").read()).decode()


def face_line(f):
    if not f or not f.get("detected"):
        return "  ✗ not detected"
    mesh = (f.get("mesh") or {}).get("count")
    return f"  ✓ detected (score {f.get('score'):.2f}) · head_pose {f.get('head_pose')} · mesh {mesh} pts"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python test_analyze.py <you> [her]")
        sys.exit(1)
    payload = {"user_image": b64(sys.argv[1])}
    if len(sys.argv) > 2:
        payload["reference_image"] = b64(sys.argv[2])
    if len(sys.argv) > 3:
        payload["vibe_image"] = b64(sys.argv[3])   # optional: the unforgettable / vibe image
    d = requests.post("http://localhost:8000/analyze", json=payload, timeout=180).json()

    print("\nUSER:"); print(face_line(d.get("user")))
    if "reference" in d:
        print("REFERENCE:"); print(face_line(d.get("reference")))
        af = d.get("arcface") or {}
        print(f"\narcface (quality signal): {af.get('cosine')} — {af.get('note')}")
        st = d.get("structure") or {}
        print(f"\nLAYER 1 — structure similarity: {st.get('similarity')}  (shared: {st.get('shared')})")
        print("   your structure:", ", ".join(st.get("user_tags", [])))
        print("   measurement similarity:")
        for k, v in (st.get("measurement_similarity") or {}).items():
            print(f"      {k:14s} {v}")
        print(f"\nLAYER 2 — overall_similarity : {d.get('overall_similarity')}")
        print("\nfeature_scores:")
        for k, v in (d.get("feature_scores") or {}).items():
            print(f"   {k:18s} {v}" + ("   <-- MATCH (>0.80)" if v >= 0.80 else ""))
        ms = d.get("matches", [])
        print(f"\nmatches ({len(ms)}):")
        for m in ms:
            pts = sum(len(r) for r in m.get("user_landmarks", []))
            print(f"   {m['id']:12s} conf {m['confidence']}   ({pts} trace pts)")
            if m.get("labels"):
                print(f"        labels: {' · '.join(m['labels'])}")
            if m.get("line"):
                print(f"        line:   {m['line']}")
        aes = d.get("aesthetic")
        if aes:
            print(f"\nAESTHETIC ENGINE — visual_similarity: {aes.get('visual_similarity')}")
            print("   you:  " + ", ".join(f"{p['concept']} {p['score']}" for p in aes.get("user_profile", [])))
            print("   her:  " + ", ".join(f"{p['concept']} {p['score']}" for p in aes.get("reference_profile", [])))
            if aes.get("vibe_profile"):
                print("   vibe: " + ", ".join(f"{p['concept']} {p['score']}" for p in aes["vibe_profile"]))
            print("   SHARED energy (you∩her): " + ", ".join(s["concept"] for s in aes.get("shared", [])))
            print("   YOUR VISUAL LANGUAGE: " + ", ".join(p["concept"] for p in aes.get("visual_language", [])))
    json.dump(d, open("last_result.json", "w"), indent=2)
    print("\n(full JSON saved to last_result.json)")
