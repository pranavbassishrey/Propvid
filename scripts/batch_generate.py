"""Batch generate promotional videos for all 10 dataset houses."""

from pathlib import Path
import subprocess
import sys
import time

def main():
    start_all = time.time()
    results = []

    print("=" * 70)
    print("STARTING BATCH VIDEO GENERATION FOR 10 DATASET HOUSES")
    print("=" * 70)

    for i in range(1, 11):
        input_json = Path(f"dataset/properties/house_{i}.json")
        out_dir = Path(f"output/house_{i}")
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[{i}/10] Processing {input_json.name} -> {out_dir}/ ...")
        t0 = time.time()

        cmd = [
            sys.executable,
            "-m", "propvid", "make",
            "-i", str(input_json),
            "-o", str(out_dir),
            "--llm", "auto",
            "--tts", "kokoro",
            "--res", "720p",
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.time() - t0

        video_file = out_dir / "video.mp4"
        success = (proc.returncode == 0) and video_file.exists()

        if success:
            size_mb = video_file.stat().st_size / (1024 * 1024)
            print(f"  [OK] House {i} rendered in {elapsed:.1f}s ({size_mb:.2f} MB)")
            results.append({
                "house": i,
                "status": "SUCCESS",
                "time_sec": elapsed,
                "size_mb": size_mb,
                "video_path": str(video_file),
            })
        else:
            print(f"  [FAIL] House {i} failed (exit code {proc.returncode})")
            print("STDOUT:", proc.stdout[-500:])
            print("STDERR:", proc.stderr[-500:])
            results.append({
                "house": i,
                "status": "FAILED",
                "time_sec": elapsed,
                "error": proc.stderr or proc.stdout,
            })

    total_time = time.time() - start_all
    print("\n" + "=" * 70)
    print(f"BATCH RUN COMPLETE: {len([r for r in results if r['status'] == 'SUCCESS'])}/10 succeeded in {total_time:.1f}s")
    print("=" * 70)
    for r in results:
        if r["status"] == "SUCCESS":
            print(f"  House {r['house']:2d}: {r['size_mb']:.2f} MB | {r['time_sec']:.1f}s | {r['video_path']}")
        else:
            print(f"  House {r['house']:2d}: FAILED")

if __name__ == "__main__":
    main()
