"""调试 DashScope API 响应结构。"""
import os
import sys
import json

sys.path.insert(0, "src")

try:
    import dashscope
    from dashscope import Generation
except ImportError as e:
    print(f"导入失败: {e}")
    sys.exit(1)

# 设置 API Key
api_key = os.getenv("DASHSCOPE_API_KEY")
if not api_key:
    print("DASHSCOPE_API_KEY 未设置")
    sys.exit(1)

dashscope.api_key = api_key

# 测试调用
messages = [
    {"role": "system", "content": "你是智能家居助手的语义解析器，请仅返回一个 JSON 对象。"},
    {"role": "user", "content": "打开客厅的灯"},
]

print("正在调用 DashScope API...")
try:
    response = Generation.call(
        model="qwen-flash",
        messages=messages,
    )

    print("\n=== 响应对象类型 ===")
    print(f"type(response): {type(response)}")

    print("\n=== 响应对象属性 ===")
    print(f"dir(response): {dir(response)}")

    print("\n=== 响应对象关键属性值 ===")
    for attr in ["status_code", "output_text", "output", "code", "message"]:
        value = getattr(response, attr, "NOT_FOUND")
        print(f"{attr}: {value!r}")

    print("\n=== 响应 output 详细结构 ===")
    output = getattr(response, "output", None)
    if output:
        print(f"type(output): {type(output)}")
        if hasattr(output, "choices"):
            print(f"output.choices: {output.choices}")
            if output.choices and len(output.choices) > 0:
                first = output.choices[0]
                print(f"type(choices[0]): {type(first)}")
                print(f"choices[0].message: {getattr(first, 'message', 'NOT_FOUND')}")
        if isinstance(output, dict):
            print(f"output dict keys: {list(output.keys())}")
            print(f"output: {json.dumps(output, ensure_ascii=False, indent=2)}")

except Exception as e:
    print(f"\n调用失败: {e}")
    import traceback
    traceback.print_exc()
