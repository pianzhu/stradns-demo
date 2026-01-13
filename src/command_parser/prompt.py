"""Prompt definitions for command parsing."""

from context_retrieval.category_gating import ALLOWED_CATEGORIES

DEFAULT_SYSTEM_PROMPT = f"""你是智能家居指令的语义解析器。你的输出会被程序解析：只输出严格 JSON（不要解释、不要代码块），不输出任何额外文本。

输出必须是 JSON 数组（元素为字符串）。每项命令字符串格式："ACTION-SCOPE-NAME#TYPE#Q[#N]"（正好 2 个 "-"）。

ACTION：中文，不含 "-"；多动作/多目标拆分规则：1. 当原句包含多个独立动作指令时，按原句表述顺序拆分；2. 当同一动作对应多个独立设备目标时，按原句表述顺序拆分；3. 动作表述需符合建议：打开/关闭；设置用 设置<属性>=<值>；查询用 查询<属性>；静音用 静音/取消静音。
SCOPE：房间/区域；无则 "*"；多房间用英文逗号 ","（不要用"和/、"）；排除用 "!房间"（仅排除则默认包含 "*"）；同一动作+同一目标+多房间合并为 1 条。
NAME：中文设备名（去掉房间词，保留修饰词）；指代规则：1. 它/那个/这个 → @last；2. 刚才的 → 指代本次会话中上一条指令里的目标设备，若会话中无历史指令则无法解析；3. 连续指代（如‘它的那个’）统一解析为@last。
TYPE：只能取 {", ".join(ALLOWED_CATEGORIES)}，否则 Unknown。
Q：all(所有/全部/都/每个/泛指类型默认) | any(任意/随便) | except(除了X/除X都) | one(仅指单个特定目标，当原句明确指定某一个具体设备时使用)
N：仅当明确数量时给整数。

关键优化提示：解析时优先匹配常见设备（如灯、空调、电视、插座等）的TYPE，避免误判为Unknown；当原句含"所有/全部/都"时，Q字段必须为all；多房间合并为英文逗号分隔的SCOPE，不要拆分成多条指令。

无法解析场景判定标准：1. 无法识别动作类型或动作表述不符合规范；2. 无法确定有效设备目标且无明确指代可关联；3. 指令表述模糊无法明确语义；满足任一条件时输出：["UNKNOWN-*-*#Unknown#one"]"""

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
    {
        "input": "打开阳台传感器",
        "expected": ["打开-阳台-传感器#Unknown#one"],
        "tags": ["single", "specific_name", "unknown_type"],
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
        "input": "把风扇风速调到70%",
        "expected": ["设置风速=70%-*-风扇#Fan#all"],
        "tags": ["parameter", "fan_speed", "generic", "all_quantifier"],
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

    # ===== 泛指类型（NAME=类型中文名） =====
    {
        "input": "打开所有灯",
        "expected": ["打开-*-灯#Light#all"],
        "tags": ["generic", "all_quantifier"],
    },
    {
        "input": "关闭所有空调",
        "expected": ["关闭-*-空调#AirConditioner#all"],
        "tags": ["generic", "all_quantifier"],
    },
    {
        "input": "把所有窗帘打开",
        "expected": ["打开-*-窗帘#Blind#all"],
        "tags": ["generic", "all_quantifier"],
    },
    {
        "input": "把所有灯调到50%",
        "expected": ["设置亮度=50%-*-灯#Light#all"],
        "tags": ["generic", "all_quantifier", "parameter"],
    },
    {
        "input": "把所有空调调到26度",
        "expected": ["设置温度=26C-*-空调#AirConditioner#all"],
        "tags": ["generic", "all_quantifier", "parameter"],
    },

    # ===== 多房间组合 =====
    {
        "input": "打开客厅和卧室的灯",
        "expected": ["打开-客厅,卧室-灯#Light#all"],
        "tags": ["multi_room", "all_quantifier"],
    },
    {
        "input": "关闭客厅和书房的空调",
        "expected": ["关闭-客厅,书房-空调#AirConditioner#all"],
        "tags": ["multi_room", "all_quantifier"],
    },
    {
        "input": "把客厅和卧室的窗帘都打开",
        "expected": ["打开-客厅,卧室-窗帘#Blind#all"],
        "tags": ["multi_room", "all_quantifier"],
    },
    {
        "input": "把卧室和客厅的窗帘都打开",
        "expected": ["打开-卧室,客厅-窗帘#Blind#all"],
        "tags": ["multi_room", "all_quantifier"],
    },

    # ===== 排除房间（except 量词） =====
    {
        "input": "打开除卧室以外的灯",
        "expected": ["打开-*,!卧室-灯#Light#except"],
        "tags": ["except", "exclude_room"],
    },
    {
        "input": "关闭除了客厅以外的空调",
        "expected": ["关闭-*,!客厅-空调#AirConditioner#except"],
        "tags": ["except", "exclude_room"],
    },
    {
        "input": "把除书房和卧室以外的灯都关了",
        "expected": ["关闭-*,!书房,!卧室-灯#Light#except"],
        "tags": ["except", "exclude_multiple_rooms"],
    },

    # ===== 任意量词 + 数量 =====
    {
        "input": "打开两盏灯",
        "expected": ["打开-*-灯#Light#any#2"],
        "tags": ["any_n", "any_quantifier", "count"],
    },
    {
        "input": "关闭三个插座",
        "expected": ["关闭-*-插座#SmartPlug#any#3"],
        "tags": ["any_n", "any_quantifier", "count"],
    },
    {
        "input": "随便打开一个灯",
        "expected": ["打开-*-灯#Light#any#1"],
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
            "打开-客厅,卧室-灯#Light#all",
            "设置亮度=50%-客厅,卧室-灯#Light#all",
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
        "input": "让电视静音",
        "expected": ["静音-*-电视#Television#all"],
        "tags": ["special_action", "mute", "generic", "all_quantifier"],
    },
    {
        "input": "取消书房音箱静音",
        "expected": ["取消静音-书房-音箱#NetworkAudio#one"],
        "tags": ["special_action", "unmute"],
    },
    {
        "input": "取消音响静音灯",
        "expected": ["关闭-*-音响静音灯#Light#one"],
        "tags": ["special_action", "cancel_light"],
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
