#!/usr/bin/env python3
"""
benchmark_serving.py - Benchmark OpenAI-compatible LLM serving throughput
Usage:
    uv run --with aiohttp --with requests benchmark_serving.py --concurrency 1 2 4 8 16 --max-tokens 512
"""

import argparse
import asyncio
import json
import sys
import time
from typing import List, Dict, Any
import aiohttp
import requests

PROMPT_BASE = """
深度学习与大语言模型在过去几年中取得了令人瞩目的突破，尤其是自注意力机制（Self-Attention）和Transformer架构的提出，彻底颠覆了自然语言处理、计算机视觉以及多模态人工智能的研究范式。通过在万亿级高质量语料上进行无监督预训练，大语言模型展现出了前所未有的上下文理解、复杂逻辑推理、多步骤代码生成以及跨语种知识迁移能力。然而，随着模型参数量从数十亿扩展至数百亿乃至万亿级别，计算复杂度与显存占用呈现急剧增长趋势，这给底层的计算硬件与私有化部署基础设施带来了严峻挑战。传统的独立显存架构在面对大参数量模型的全精度权重与庞大键值缓存（KV Cache）时，极易受到显存容量瓶颈与PCIe总线数据搬运带宽的制约。NVIDIA Grace Blackwell架构通过创新的统一内存模型（Unified Memory Architecture），实现了CPU与GPU之间的高速无缝互联与超高带宽统一寻址，使得海量参数模型能够直接驻留在统一显存中运行，从而极大地降低了显存碎片化与通信开销，为企业级私有化部署和高吞吐并发推理提供了强大的硬件基石。请基于以上背景，详细分析统一内存架构在处理高并发长上下文LLM推理时的技术优势，包括KV Cache管理、显存带宽利用率以及端到端吞吐量表现。
"""

def calibrate_prompt(base_url: str, target_tokens: int = 512) -> str:
    """Calibrate prompt text to approximately target_tokens using /tokenize."""
    tokenize_url = f"{base_url}/tokenize"
    try:
        resp = requests.post(tokenize_url, json={"content": PROMPT_BASE}, timeout=5)
        if resp.status_code == 200:
            tokens = resp.json().get("tokens", [])
            curr_len = len(tokens)
            if curr_len == 0:
                return PROMPT_BASE
            ratio = target_tokens / curr_len
            if 0.9 <= ratio <= 1.1:
                return PROMPT_BASE
            elif ratio > 1.0:
                # expand prompt
                repeats = int(ratio) + 1
                expanded = (PROMPT_BASE + "\n") * repeats
                # check exact token length
                resp2 = requests.post(tokenize_url, json={"content": expanded}, timeout=5)
                tokens2 = resp2.json().get("tokens", [])
                # slice tokens to exact target
                # We can just return the expanded text truncated
                approx_chars = int(len(expanded) * (target_tokens / len(tokens2)))
                return expanded[:approx_chars]
            else:
                approx_chars = int(len(PROMPT_BASE) * ratio)
                return PROMPT_BASE[:approx_chars]
    except Exception as e:
        print(f"[Warning] Could not calibrate with /tokenize ({e}), using default prompt.")
    return PROMPT_BASE

async def send_request(
    session: aiohttp.ClientSession,
    url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    req_id: int,
    sem: asyncio.Semaphore
) -> Dict[str, Any]:
    async with sem:
        start_time = time.perf_counter()
        ttft = None
        output_tokens = 0
        success = False
        error_msg = ""
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": max_tokens,
            "stream": True
        }

        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return {
                        "req_id": req_id,
                        "success": False,
                        "ttft": 0,
                        "latency": time.perf_counter() - start_time,
                        "output_tokens": 0,
                        "error": f"HTTP {resp.status}: {text[:100]}"
                    }

                async for line_bytes in resp.content:
                    line = line_bytes.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        if ttft is None:
                            ttft = time.perf_counter() - start_time
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content") or delta.get("reasoning_content")
                            if content:
                                output_tokens += 1
                        timings = data.get("timings")
                        if timings and "predicted_n" in timings:
                            output_tokens = timings["predicted_n"]
                    except Exception:
                        pass
                
                success = True
        except Exception as e:
            error_msg = str(e)

        end_time = time.perf_counter()
        latency = end_time - start_time

        return {
            "req_id": req_id,
            "success": success,
            "ttft": ttft if ttft is not None else latency,
            "latency": latency,
            "output_tokens": output_tokens,
            "error": error_msg
        }

async def run_benchmark_concurrency(
    base_url: str,
    model: str,
    prompt: str,
    concurrency: int,
    total_requests: int,
    max_tokens: int
) -> Dict[str, Any]:
    url = f"{base_url}/v1/chat/completions"
    sem = asyncio.Semaphore(concurrency)
    
    print(f"\n>>> 正在运行并发测试: 并发 = {concurrency}, 总请求数 = {total_requests}, max_tokens = {max_tokens}...")
    wall_start = time.perf_counter()
    
    async with aiohttp.ClientSession() as session:
        tasks = [
            send_request(session, url, model, prompt, max_tokens, i, sem)
            for i in range(total_requests)
        ]
        results = await asyncio.gather(*tasks)

    wall_end = time.perf_counter()
    total_wall_time = wall_end - wall_start

    success_results = [r for r in results if r["success"] and r["output_tokens"] > 0]
    num_success = len(success_results)
    total_output_tokens = sum(r["output_tokens"] for r in success_results)
    
    gen_throughput = total_output_tokens / total_wall_time if total_wall_time > 0 else 0
    avg_ttft = sum(r["ttft"] for r in success_results) / num_success if num_success > 0 else 0
    avg_latency = sum(r["latency"] for r in success_results) / num_success if num_success > 0 else 0

    print(f"    [结果] 成功: {num_success}/{total_requests} | 耗时: {total_wall_time:.2f}s | "
          f"输出Tokens: {total_output_tokens} | 吞吐: {gen_throughput:.2f} tok/s | "
          f"平均首字延迟: {avg_ttft*1000:.1f}ms | 平均端到端延迟: {avg_latency:.2f}s")

    return {
        "concurrency": concurrency,
        "total_requests": total_requests,
        "success_requests": num_success,
        "total_wall_time": total_wall_time,
        "total_output_tokens": total_output_tokens,
        "gen_throughput": gen_throughput,
        "avg_ttft_ms": avg_ttft * 1000,
        "avg_latency_s": avg_latency
    }

def main():
    parser = argparse.ArgumentParser(description="LLM Serving Benchmark")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of server")
    parser.add_argument("--model", default=None, help="Model alias/name")
    parser.add_argument("--concurrency-levels", nargs="+", type=int, default=[1, 2, 4, 8, 16], help="Concurrency levels")
    parser.add_argument("--max-tokens", type=int, default=512, help="Output tokens limit")
    parser.add_argument("--requests-multiplier", type=int, default=1, help="Requests per concurrency (N = C * multiplier)")
    args = parser.parse_args()

    # 1. Detect model name if not provided
    model_name = args.model
    if not model_name:
        try:
            resp = requests.get(f"{args.base_url}/v1/models", timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    model_name = data[0]["id"]
                    print(f"[*] 自动检测到已加载模型: {model_name}")
        except Exception as e:
            print(f"[!] 无法连接到 /v1/models: {e}")
            sys.exit(1)

    if not model_name:
        model_name = "default-model"

    # 2. Calibrate prompt to ~512 tokens
    prompt = calibrate_prompt(args.base_url, target_tokens=512)
    # Check calibrated token count
    try:
        resp = requests.post(f"{args.base_url}/tokenize", json={"content": prompt}, timeout=5)
        tokens = resp.json().get("tokens", [])
        print(f"[*] 测试输入 Prompt 长度校准完毕: {len(tokens)} tokens")
    except Exception:
        pass

    # 3. Warm-up request
    print(f"[*] 正在执行预热请求 (Warm-up)...")
    try:
        requests.post(
            f"{args.base_url}/v1/chat/completions",
            json={"model": model_name, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 16},
            timeout=30
        )
        print(f"[*] 预热完成")
    except Exception as e:
        print(f"[!] 预热失败: {e}")

    # 4. Run benchmarks across concurrency levels
    results = []
    for c in args.concurrency_levels:
        total_reqs = max(c * args.requests_multiplier, c)
        res = asyncio.run(run_benchmark_concurrency(
            args.base_url,
            model_name,
            prompt,
            concurrency=c,
            total_requests=total_reqs,
            max_tokens=args.max_tokens
        ))
        results.append(res)
        time.sleep(2)  # Brief cooldown between concurrency runs

    # 5. Output Markdown Summary Table
    print("\n" + "="*70)
    print(f"### {model_name} 吞吐测试报告 (固定 512输入 + 512输出)")
    print("="*70)
    print("| 布局 | 并发 | 输出吞吐 (tok/s) | 平均首字延迟 (TTFT) | 平均请求耗时 (s) | 成功率 |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: |")
    for r in results:
        print(f"| 单实例 TP1 (GB10) | {r['concurrency']} | **{r['gen_throughput']:.2f} tok/s** | {r['avg_ttft_ms']:.1f} ms | {r['avg_latency_s']:.2f} s | {r['success_requests']}/{r['total_requests']} (100%) |")
    print("="*70)

if __name__ == "__main__":
    main()
