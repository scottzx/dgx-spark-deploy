#!/usr/bin/env python3
"""
DGX Spark - 3 轮 × 4 并发全新会话压测与 FIFO 状态全景检测
"""

import asyncio
import time
import json
import httpx

BASE_URL = "http://127.0.0.1:8000"

ROUNDS_DATA = [
    # 第一轮: 4 个全新独立业务会话
    [
        ("会话01_研发架构", "你好，我是架构师，这是第一轮会话1：请用15字以内总结微服务核心价值。"),
        ("会话02_财务预算", "你好，我是财务总监，这是第一轮会话2：请用15字以内说明预算控制核心原则。"),
        ("会话03_公文行政", "你好，我是行政主管，这是第一轮会话3：请用15字以内拟定中秋节放假通告标题。"),
        ("会话04_算法工程", "你好，我是算法专家，这是第一轮会话4：请用15字以内说明大模型推理显存优化要点。"),
    ],
    # 第二轮: 4 个全新独立业务会话 (将顶替第一轮的前台槽位)
    [
        ("会话05_市场竞对", "你好，我是市场经理，这是第二轮会话5：请用15字以内总结竞品调研的核心步骤。"),
        ("会话06_法务合规", "你好，我是法务顾问，这是第二轮会话6：请用15字以内说明劳动合同签订法律风险。"),
        ("会话07_运维容灾", "你好，我是SRE工程师，这是第二轮会话7：请用15字以内说明服务熔断与降级策略。"),
        ("会话08_产品原型", "你好，我是产品总监，这是第二轮会话8：请用15字以内说明用户故事的核心三要素。"),
    ],
    # 第三轮: 4 个全新独立业务会话 (将顶替第二轮的前台槽位)
    [
        ("会话09_人才梯队", "你好，我是HRD，这是第三轮会话9：请用15字以内说明技术人才职级考核标准。"),
        ("会话10_网络安全", "你好，我是安全专家，这是第三轮会话10：请用15字以内说明SQL注入最有效防范手段。"),
        ("会话11_交互体验", "你好，我是UI设计师，这是第三轮会话11：请用15字以内说明移动端触控区设计原则。"),
        ("会话12_数据中台", "你好，我是数仓工程师，这是第三轮会话12：请用15字以内说明ODS到DWD分层设计目的。"),
    ]
]


async def send_request(client: httpx.AsyncClient, session_name: str, prompt: str):
    t0 = time.time()
    # 提取纯英文字符串作为 header，同时在 JSON body 里携带
    sess_id = f"sess_{hash(session_name) & 0xffffffff:08x}"
    resp = await client.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"x-conversation-id": sess_id},
        json={
            "model": "Qwen3.8-Flash-Next-UD-IQ4_XS",
            "conversation_id": sess_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 40,
            "stream": False
        },
        timeout=120.0
    )
    cost = time.time() - t0
    data = resp.json()
    reply = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    return session_name, cost, resp.status_code, reply


async def run_batch():
    async with httpx.AsyncClient(timeout=180.0) as client:
        for round_idx, round_tasks in enumerate(ROUNDS_DATA, 1):
            print(f"\n==========================================================")
            print(f"🔥 开始执行第 {round_idx} 轮压测 (4 个并发新会话)...")
            print(f"==========================================================")
            t_start = time.time()
            tasks = [send_request(client, s_name, prompt) for s_name, prompt in round_tasks]
            results = await asyncio.gather(*tasks)
            total_round_cost = time.time() - t_start

            for s_name, cost, status, reply in results:
                print(f"  ✅ [{s_name}] 状态: {status} | 耗时: {cost:.2f}s | 回复: {reply[:30]}...")
            print(f"⏱️ 第 {round_idx} 轮 4 并发总耗时: {total_round_cost:.2f}s (平均单并发耗时: {total_round_cost/4:.2f}s)")
            await asyncio.sleep(2)

        # 终极检验: 切回第一轮被顶掉的「会话01_研发架构」进行追问
        print(f"\n==========================================================")
        print(f"🎯 终极回访测试: 追问在第 1 轮已被挤出显存的 [会话01_研发架构]...")
        print(f"==========================================================")
        t0 = time.time()
        sess_id_01 = f"sess_{hash('会话01_研发架构') & 0xffffffff:08x}"
        resp = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={"x-conversation-id": sess_id_01},
            json={
                "model": "Qwen3.8-Flash-Next-UD-IQ4_XS",
                "conversation_id": sess_id_01,
                "messages": [
                    {"role": "user", "content": "你好，我是架构师，这是第一轮会话1：请用15字以内总结微服务核心价值。"},
                    {"role": "assistant", "content": "高内聚低耦合，独立部署与扩展。"},
                    {"role": "user", "content": "请接着追问：那么服务网格（Service Mesh）的核心定位是什么？"}
                ],
                "max_tokens": 40,
                "stream": False
            },
            timeout=60.0
        )
        cost = time.time() - t0
        data = resp.json()
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        timings = data.get("timings", {})
        print(f"  🎉 [会话01 追问结果] 状态: {resp.status_code} | 整体耗时: {cost:.2f}s")
        print(f"  ⚡ 首字推理耗时: {timings.get('prompt_ms', 0):.1f} ms | 缓存命中 Tokens: {timings.get('cache_n', 0)}")
        print(f"  💬 回复内容: {reply}")


if __name__ == "__main__":
    asyncio.run(run_batch())
