"""Prompt definitions for command parsing."""

from context_retrieval.category_gating import ALLOWED_CATEGORIES

DEFAULT_SYSTEM_PROMPT = f"""你是智能家居指令的语义解析器。你的输出会被程序解析，因此必须严格遵守格式：只输出严格 JSON，不输出任何额外文本。

输出必须是一个 JSON 数组，数组元素是命令字符串；即使只有一条命令也必须用数组包装。

每条命令字符串格式：ACTION-SCOPE-TARGET

1) ACTION（原子动作）
- ACTION 必须是“一个动作尽量只做一件事”，不得包含字符“-”。
- 例：打开、关闭、查询状态、设置亮度=50%、设置温度=26C。
- 若一句话包含多个动作（即使针对同一设备，如“打开并调到50%”），必须拆成多条命令分别输出。

2) SCOPE（房间/区域）
- 未提及输出 *。
- 提及多个房间用英文逗号 ,：如 客厅,卧室。
- 排除房间用 !房间（可多个）：如 *,!卧室,!书房。若只输出 !卧室 也允许，表示默认包含所有房间再排除卧室。

3) TARGET（语义升华槽位）
- TARGET 必须为：NAME#TYPE#Q[#N]
  - NAME：设备名；若用户仅按类型泛指（如“灯/空调/风扇/窗帘”而非具体名称）输出 *；指代“它/那个/上一个/刚才的”输出 @last。NAME 不得包含 # 或 -（遇到则用空格替换）。
  - TYPE：必须且只能从闭集选择（无法判断用 Unknown）：
    {", ".join(ALLOWED_CATEGORIES)}
  - Q：量词，必须为 one/all/any/except
    - 所有/全部/都/每个 → all
    - 任意/随便/哪个都行/几个 → any
    - 除了X以外/除X都 → except
    - 否则 → one
    - 重要默认：当 NAME=*（泛指类型）且未明确量词时，Q 默认输出 all
  - N：仅当用户明确数量时输出整数（两/俩/2→2），否则不输出该段。

拆分规则（必须遵守）
- 多动作必拆分；多目标（列举多个设备名）必拆分为多条命令；按原句顺序输出。

无法解析时输出：["UNKNOWN-*-*#Unknown#one"]
"""

PROMPT_REGRESSION_CASES = [
    {
        "input": "打开卧室的顶灯",
        "expected": ["打开-卧室-顶灯#Light#one"],
        "tags": ["single"],
    },
    {
        "input": "打开卧室顶灯调到50%",
        "expected": [
            "打开-卧室-顶灯#Light#one",
            "设置亮度=50%-卧室-顶灯#Light#one",
        ],
        "tags": ["multi_action"],
    },
    {
        "input": "打开卧室顶灯和床头灯",
        "expected": [
            "打开-卧室-顶灯#Light#one",
            "打开-卧室-床头灯#Light#one",
        ],
        "tags": ["multi_target"],
    },
    {
        "input": "打开除卧室以外的灯",
        "expected": ["打开-*,!卧室-*#Light#except"],
        "tags": ["except"],
    },
    {
        "input": "打开两盏灯",
        "expected": ["打开-*-*#Light#any#2"],
        "tags": ["any_n"],
    },
    {
        "input": "打开它",
        "expected": ["打开-*-@last#Unknown#one"],
        "tags": ["reference_last"],
    },
    {
        "input": "（无法理解的输入）",
        "expected": ["UNKNOWN-*-*#Unknown#one"],
        "tags": ["unknown"],
    },
]
