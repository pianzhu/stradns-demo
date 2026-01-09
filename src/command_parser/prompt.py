"""Prompt definitions for command parsing."""

from context_retrieval.category_gating import ALLOWED_CATEGORIES

DEFAULT_SYSTEM_PROMPT = f"""你是智能家居指令的语义解析器。你的输出会被程序解析，因此必须严格遵守格式：只输出严格 JSON，不输出任何额外文本。

输出必须是一个 JSON 数组，数组元素是命令字符串；即使只有一条命令也必须用数组包装。

每条命令字符串格式：ACTION-SCOPE-TARGET

1) ACTION（原子动作）
- ACTION 必须是"一个动作尽量只做一件事"，不得包含字符"-"。
- 例：打开、关闭、查询状态、设置亮度=50%、设置温度=26C。
- 若一句话包含多个动作（即使针对同一设备，如"打开并调到50%"），必须拆成多条命令分别输出。

2) SCOPE（房间/区域）
- 未提及输出 *。
- 提及多个房间用英文逗号 ,：如 客厅,卧室。
- 排除房间用 !房间（可多个）：如 *,!卧室,!书房。若只输出 !卧室 也允许，表示默认包含所有房间再排除卧室。

3) TARGET（语义升华槽位）
- TARGET 必须为：NAME#TYPE#Q[#N]
  - NAME：**必须用中文**。设备具体名称（如"主灯"/"床头灯"/"吸顶灯"/"空调"/"窗帘"）；若用户仅按类型泛指（如"灯/空调/风扇/窗帘"而非具体名称）输出 *；指代"它/那个/上一个/刚才的"输出 @last。NAME 不得包含 # 或 -（遇到则用空格替换）。
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

示例 1（中文设备名 + 多动作拆分 + 参数）：
输入：打开卧室床头灯调到50%
输出：["打开-卧室-床头灯#Light#one","设置亮度=50%-卧室-床头灯#Light#one"]

示例 2（泛指 + 排除房间 + except 量词）：
输入：关闭除卧室以外的灯
输出：["关闭-*,!卧室-*#Light#except"]
"""

PROMPT_REGRESSION_CASES = [
    # ===== 基础示例：单设备单动作（具体中文设备名） =====
    {
        "input": "打开客厅主灯",
        "expected": ["打开-客厅-主灯#Light#one"],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "关闭卧室床头灯",
        "expected": ["关闭-卧室-床头灯#Light#one"],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "打开书房台灯",
        "expected": ["打开-书房-台灯#Light#one"],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "关闭客厅落地灯",
        "expected": ["关闭-客厅-落地灯#Light#one"],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "打开厨房吊灯",
        "expected": ["打开-厨房-吊灯#Light#one"],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "打开阳台灯带",
        "expected": ["打开-阳台-灯带#Light#one"],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "关闭卧室吸顶灯",
        "expected": ["关闭-卧室-吸顶灯#Light#one"],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "打开客厅窗帘",
        "expected": ["打开-客厅-窗帘#Blind#one"],
        "tags": ["single", "specific_name", "blind"],
    },
    {
        "input": "关闭书房百叶窗",
        "expected": ["关闭-书房-百叶窗#Blind#one"],
        "tags": ["single", "specific_name", "blind"],
    },
    {
        "input": "打开客厅空调",
        "expected": ["打开-客厅-空调#AirConditioner#one"],
        "tags": ["single", "specific_name", "ac"],
    },
    {
        "input": "关闭卧室空调",
        "expected": ["关闭-卧室-空调#AirConditioner#one"],
        "tags": ["single", "specific_name", "ac"],
    },
    {
        "input": "打开客厅风扇",
        "expected": ["打开-客厅-风扇#Fan#one"],
        "tags": ["single", "specific_name", "fan"],
    },
    {
        "input": "打开客厅电视",
        "expected": ["打开-客厅-电视#Television#one"],
        "tags": ["single", "specific_name", "tv"],
    },
    {
        "input": "打开客厅音响",
        "expected": ["打开-客厅-音响#NetworkAudio#one"],
        "tags": ["single", "specific_name", "audio"],
    },
    {
        "input": "打开书房音箱",
        "expected": ["打开-书房-音箱#NetworkAudio#one"],
        "tags": ["single", "specific_name", "audio"],
    },
    {
        "input": "打开客厅智能插座",
        "expected": ["打开-客厅-智能插座#SmartPlug#one"],
        "tags": ["single", "specific_name", "plug"],
    },
    {
        "input": "打开厨房墙壁开关",
        "expected": ["打开-厨房-墙壁开关#Switch#one"],
        "tags": ["single", "specific_name", "switch"],
    },

    # ===== 参数设置示例 =====
    {
        "input": "把客厅主灯调到50%",
        "expected": ["设置亮度=50%-客厅-主灯#Light#one"],
        "tags": ["parameter", "brightness"],
    },
    {
        "input": "把书房空调调到26度",
        "expected": ["设置温度=26C-书房-空调#AirConditioner#one"],
        "tags": ["parameter", "temperature"],
    },
    {
        "input": "把卧室风扇风速调到70%",
        "expected": ["设置风速=70%-卧室-风扇#Fan#one"],
        "tags": ["parameter", "fan_speed"],
    },
    {
        "input": "把客厅电视音量调到30%",
        "expected": ["设置音量=30%-客厅-电视#Television#one"],
        "tags": ["parameter", "volume"],
    },
    {
        "input": "把客厅窗帘遮光调到50%",
        "expected": ["设置遮光=50%-客厅-窗帘#Blind#one"],
        "tags": ["parameter", "shade_level"],
    },

    # ===== 多动作拆分 =====
    {
        "input": "打开卧室床头灯调到50%",
        "expected": [
            "打开-卧室-床头灯#Light#one",
            "设置亮度=50%-卧室-床头灯#Light#one",
        ],
        "tags": ["multi_action", "specific_name"],
    },
    {
        "input": "打开客厅空调并设置到26度",
        "expected": [
            "打开-客厅-空调#AirConditioner#one",
            "设置温度=26C-客厅-空调#AirConditioner#one",
        ],
        "tags": ["multi_action", "specific_name"],
    },

    # ===== 多目标拆分 =====
    {
        "input": "打开客厅主灯和落地灯",
        "expected": [
            "打开-客厅-主灯#Light#one",
            "打开-客厅-落地灯#Light#one",
        ],
        "tags": ["multi_target", "specific_name"],
    },
    {
        "input": "关闭卧室床头灯和吸顶灯",
        "expected": [
            "关闭-卧室-床头灯#Light#one",
            "关闭-卧室-吸顶灯#Light#one",
        ],
        "tags": ["multi_target", "specific_name"],
    },

    # ===== 泛指类型（NAME=*） =====
    {
        "input": "打开所有灯",
        "expected": ["打开-*-*#Light#all"],
        "tags": ["generic", "all_quantifier"],
    },
    {
        "input": "关闭所有空调",
        "expected": ["关闭-*-*#AirConditioner#all"],
        "tags": ["generic", "all_quantifier"],
    },
    {
        "input": "把所有窗帘打开",
        "expected": ["打开-*-*#Blind#all"],
        "tags": ["generic", "all_quantifier"],
    },
    {
        "input": "把所有灯调到50%",
        "expected": ["设置亮度=50%-*-*#Light#all"],
        "tags": ["generic", "all_quantifier", "parameter"],
    },
    {
        "input": "把所有空调调到26度",
        "expected": ["设置温度=26C-*-*#AirConditioner#all"],
        "tags": ["generic", "all_quantifier", "parameter"],
    },

    # ===== 多房间组合 =====
    {
        "input": "打开客厅和卧室的灯",
        "expected": ["打开-客厅,卧室-*#Light#all"],
        "tags": ["multi_room", "all_quantifier"],
    },
    {
        "input": "关闭客厅和书房的空调",
        "expected": ["关闭-客厅,书房-*#AirConditioner#all"],
        "tags": ["multi_room", "all_quantifier"],
    },
    {
        "input": "把客厅和卧室的窗帘都打开",
        "expected": ["打开-客厅,卧室-*#Blind#all"],
        "tags": ["multi_room", "all_quantifier"],
    },

    # ===== 排除房间（except 量词） =====
    {
        "input": "打开除卧室以外的灯",
        "expected": ["打开-*,!卧室-*#Light#except"],
        "tags": ["except", "exclude_room"],
    },
    {
        "input": "关闭除了客厅以外的空调",
        "expected": ["关闭-*,!客厅-*#AirConditioner#except"],
        "tags": ["except", "exclude_room"],
    },
    {
        "input": "把除书房和卧室以外的灯都关了",
        "expected": ["关闭-*,!书房,!卧室-*#Light#except"],
        "tags": ["except", "exclude_multiple_rooms"],
    },

    # ===== 任意量词 + 数量 =====
    {
        "input": "打开两盏灯",
        "expected": ["打开-*-*#Light#any#2"],
        "tags": ["any_n", "any_quantifier", "count"],
    },
    {
        "input": "关闭三个插座",
        "expected": ["关闭-*-*#SmartPlug#any#3"],
        "tags": ["any_n", "any_quantifier", "count"],
    },
    {
        "input": "随便打开一个灯",
        "expected": ["打开-*-*#Light#any#1"],
        "tags": ["any_n", "any_quantifier", "count"],
    },

    # ===== 指代（@last） =====
    {
        "input": "打开它",
        "expected": ["打开-*-@last#Unknown#one"],
        "tags": ["reference_last"],
    },
    {
        "input": "关闭那个",
        "expected": ["关闭-*-@last#Unknown#one"],
        "tags": ["reference_last"],
    },
    {
        "input": "把它调到50%",
        "expected": ["设置亮度=50%-*-@last#Unknown#one"],
        "tags": ["reference_last", "parameter"],
    },

    # ===== 复杂组合 =====
    {
        "input": "把客厅主灯打开并调到80%然后打开窗帘",
        "expected": [
            "打开-客厅-主灯#Light#one",
            "设置亮度=80%-客厅-主灯#Light#one",
            "打开-客厅-窗帘#Blind#one",
        ],
        "tags": ["complex", "multi_action", "multi_target"],
    },
    {
        "input": "打开客厅和卧室的所有灯并调到50%",
        "expected": [
            "打开-客厅,卧室-*#Light#all",
            "设置亮度=50%-客厅,卧室-*#Light#all",
        ],
        "tags": ["complex", "multi_action", "multi_room"],
    },

    # ===== 特殊动作 =====
    {
        "input": "让客厅电视静音",
        "expected": ["静音-客厅-电视#Television#one"],
        "tags": ["special_action", "mute"],
    },
    {
        "input": "取消书房音箱静音",
        "expected": ["取消静音-书房-音箱#NetworkAudio#one"],
        "tags": ["special_action", "unmute"],
    },
    {
        "input": "把客厅风扇设为自然风",
        "expected": ["设置风模式=自然风-客厅-风扇#Fan#one"],
        "tags": ["special_action", "mode"],
    },
    {
        "input": "开始阳台洗衣机烘干",
        "expected": ["开始烘干-阳台-洗衣机#Washer#one"],
        "tags": ["special_action", "washer"],
    },
    {
        "input": "暂停阳台洗衣机烘干",
        "expected": ["暂停烘干-阳台-洗衣机#Washer#one"],
        "tags": ["special_action", "washer"],
    },

    # ===== 查询状态 =====
    {
        "input": "查询客厅主灯状态",
        "expected": ["查询状态-客厅-主灯#Light#one"],
        "tags": ["query"],
    },
    {
        "input": "查询卧室空调温度",
        "expected": ["查询温度-卧室-空调#AirConditioner#one"],
        "tags": ["query"],
    },

    # ===== 无法解析 =====
    {
        "input": "（无法理解的输入）",
        "expected": ["UNKNOWN-*-*#Unknown#one"],
        "tags": ["unknown"],
    },
    {
        "input": "ajsdkfjalskdfj",
        "expected": ["UNKNOWN-*-*#Unknown#one"],
        "tags": ["unknown"],
    },
]
