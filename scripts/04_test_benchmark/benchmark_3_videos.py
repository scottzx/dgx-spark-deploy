import json, os, shutil, subprocess, sys, time, uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = os.environ.get("BASE", "http://127.0.0.1:30010").rstrip("/")
H3_HOME = Path(__file__).resolve().parent
RUNS_DIR = H3_HOME / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

PROMPTS = [
    {
        "name": "Test-1: 舞蹈表演 (室内全景)",
        "prompt": "A dancer performs a flowing routine in a bright studio, full body shot, smooth camera movement, photorealistic.",
        "duration": 5.0,
        "aspect_ratio": "16:9",
        "steps": 4,
        "seed": 20260901,
    },
    {
        "name": "Test-2: 金毛小狗 (自然光景深)",
        "prompt": "A cute fluffy golden retriever puppy playing with fallen autumn leaves in a sunny park, cinematic lighting, shallow depth of field.",
        "duration": 5.0,
        "aspect_ratio": "16:9",
        "steps": 4,
        "seed": 20260902,
    },
    {
        "name": "Test-3: 赛博朋克城市 (夜景霓虹)",
        "prompt": "A futuristic cyberpunk city street at night with neon reflections on rain-slicked asphalt, flying cars passing by, high contrast, cinematic 4k.",
        "duration": 5.0,
        "aspect_ratio": "16:9",
        "steps": 4,
        "seed": 20260903,
    },
]

def check_health():
    print(f"正在检查 MiniMax-H3 服务健康状态: {BASE}/health ...")
    try:
        with urlopen(f"{BASE}/health", timeout=5) as resp:
            data = resp.read().decode()
            print(f"✅ 服务在线! 响应: {data}")
            return True
    except Exception as e:
        print(f"❌ 服务未就绪或未启动: {e}")
        print("请先执行 bash /home/admin/switch_to_minimax.sh 启动服务并等待加载完成。")
        return False

def api(path, data=None):
    body = None if data is None else json.dumps(data).encode()
    req = Request(BASE + path, data=body, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=600 if data is not None else 30) as resp:
        return json.load(resp)

def generate_one(test_item, index):
    print(f"\n==========================================================")
    print(f"[{index}/3] 开始测试: {test_item['name']}")
    print(f"提示词: {test_item['prompt']}")
    print(f"规格: {test_item['duration']}s, {test_item['aspect_ratio']}, 步数: {test_item['steps']}")
    print(f"==========================================================")

    payload = {
        "model": "MiniMaxAI/MiniMax-H3",
        "task": "t2va",
        "prompt": test_item["prompt"],
        "conditions": [],
        "target": {
            "short_edge": 768,
            "aspect_ratio": test_item["aspect_ratio"],
            "duration_seconds": test_item["duration"],
        },
        "num_inference_steps": test_item["steps"],
        "flow_shift": 12.0,
        "audio_flow_shift": 3.0,
        "seed": test_item["seed"],
    }

    run_dir = RUNS_DIR / f"test_{index}_{uuid.uuid4().hex[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "request.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    started = time.monotonic()
    job = api("/v1/videos", payload)
    job_id = job["id"]
    print(f"任务已提交! Job ID: {job_id}，正在轮询生成进度...")

    deadline = started + 1800
    while True:
        (run_dir / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2))
        status = job.get("status")
        if status == "completed":
            break
        if status in {"failed", "error", "cancelled", "deleted"}:
            raise RuntimeError(f"Job {job_id} 失败: {job}")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Job {job_id} 超时 (30分钟)")
        time.sleep(2)
        try:
            job = api(f"/v1/videos/{job_id}")
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504}:
                raise
        except URLError:
            pass

    total_time = time.monotonic() - started
    inference_time = job.get("inference_time_s", total_time)
    peak_memory = job.get("peak_memory_mb", "N/A")

    # 下载视频文件
    out_video = run_dir / "video.mp4"
    with urlopen(f"{BASE}/v1/videos/{job_id}/content", timeout=120) as resp:
        with open(out_video, "wb") as f:
            shutil.copyfileobj(resp, f)

    file_size_mb = out_video.stat().st_size / (1024 * 1024)
    result = {
        "name": test_item["name"],
        "job_id": job_id,
        "inference_time_s": inference_time,
        "total_time_s": total_time,
        "peak_memory_mb": peak_memory,
        "video_path": str(out_video),
        "video_size_mb": round(file_size_mb, 2),
    }
    (run_dir / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"✅ 完成! 生成耗时: {inference_time:.2f}s (总耗时: {total_time:.2f}s), 文件大小: {file_size_mb:.2f}MB")
    print(f"   视频保存路径: {out_video}")
    return result

def main():
    if not check_health():
        sys.exit(1)

    results = []
    for i, item in enumerate(PROMPTS, 1):
        res = generate_one(item, i)
        results.append(res)

    print("\n" + "="*70)
    print("MiniMax-H3 文生视频 (T2VA) 3次测试性能汇总表:")
    print("="*70)
    print(f"{'测试项':<25} | {'生成耗时(s)':<12} | {'总耗时(s)':<10} | {'文件大小(MB)':<12}")
    print("-"*70)
    for r in results:
        print(f"{r['name']:<25} | {r['inference_time_s']:<12.2f} | {r['total_time_s']:<10.2f} | {r['video_size_mb']:<12.2f}")
    print("="*70)

if __name__ == "__main__":
    main()
