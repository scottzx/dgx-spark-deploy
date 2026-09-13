import time
import requests
import json

URL = "http://127.0.0.1:8000/v1/chat/completions"
MODEL = "Qwen3.8-Flash-Next-UD-IQ4_XS"

tests = [
    {
        "title": "场景1：代码重构与结构化字段复用 (高上下文复用)",
        "prompt": """请重构以下订单模型，转换为带有 Pydantic v2 校验的规范数据类，包含所有字段、类型注解和 json 序列化逻辑：
class OrderItem:
    order_id: str
    item_id: str
    item_name: str
    item_price: float
    item_quantity: int
    item_discount: float
    shipping_address: str
    billing_address: str
    customer_phone: str
    customer_email: str
    payment_method: str
    created_at: str
    updated_at: str
""",
        "max_tokens": 350
    },
    {
        "title": "场景2：长文提取与要点归纳 (中等上下文复用)",
        "prompt": """阅读以下关于 NVIDIA Blackwell 架构的技术简述，严格基于原文提炼出核心规格要点（包括晶体管数量、NVLink 带宽、内存类型与容量、推理性能倍数）：
【原文】NVIDIA Blackwell 架构 GPU 包含 2080 亿个晶体管，采用专门定制的双芯片双倍光刻极限台积电 4NP 工艺制程。第五代 NVLink 为每个 GPU 提供高达 1.8TB/s 的双向互联带宽，确保在复杂超大规模 MoE 模型中实现无缝高速通信。计算节点最高配备 192GB HBM3e 高带宽内存，内存带宽达到 8.0TB/s。相较于上一代 Hopper 架构，Blackwell 在万亿参数大模型 FP4 精度推理场景下，吞吐性能提升高达 30 倍，能耗效率提升 25 倍。
""",
        "max_tokens": 250
    },
    {
        "title": "场景3：发散性自由问答 (零上下文复用)",
        "prompt": "请用充满诗意和哲理的文风，写一段关于“秋风与落叶”的散文随笔，字数 200 字左右。",
        "max_tokens": 250
    }
]

print("=" * 65)
print("  N-Gram 投机解码在不同真实场景下的生成速度与命中表现实测")
print("=" * 65)

for item in tests:
    t_title = item["title"]
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": item["prompt"]}],
        "temperature": 0.1,
        "max_tokens": item["max_tokens"],
        "stream": False
    }
    
    t0 = time.time()
    resp = requests.post(URL, json=payload)
    t1 = time.time()
    
    if resp.status_code == 200:
        data = resp.json()
        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        prompt_tokens = usage.get("prompt_tokens", 0)
        elapsed = t1 - t0
        speed = completion_tokens / elapsed if elapsed > 0 else 0
        print(f"\n【{t_title}】")
        print(f"  - 输入: {prompt_tokens} tokens | 输出: {completion_tokens} tokens")
        print(f"  - 客户端端到端耗时: {elapsed:.2f}s | 端到端生成速度: {speed:.2f} tok/s")
    else:
        print(f"\n【{t_title}】 失败: {resp.status_code} - {resp.text}")

print("\n" + "=" * 65)
