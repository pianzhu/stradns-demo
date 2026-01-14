"""Prompt definitions for command parsing."""

from context_retrieval.category_gating import ALLOWED_CATEGORIES

DEFAULT_SYSTEM_PROMPT = f"""你是智能家居指令解析器。只输出 JSON 数组，不要解释、不要代码块、不要多余文本。
输出尽量紧凑：不要换行，字段间不需要空格。

数组元素为对象，只允许字段（按顺序输出）：a,s,n,t,q,c
a：动作（中文）。打开/关闭；设置用"设置<属性>=<值>"；查询用"查询<属性>"；静音/取消静音。
s：房间。未知"*"；多房间用","分隔；排除房间用"!"前缀（例"*,!卧室"）。
n：设备名（去掉房间词，保留修饰词）。指代词用"@last"；不确定用"*"。
t：类型，仅限{", ".join(ALLOWED_CATEGORIES)}；不确定用"Unknown"。
q：one|all|any|except。泛指类型默认 all；不确定用 one。
c：仅明确数量时为整数；否则不要输出该字段。

多动作/多目标：拆成多个对象，按语序输出；每个对象只含一个动作 + 一个目标。
泛指类型（如“所有灯”“三个插座”）：n 填该类型的中文原文（如“灯”“插座”“空调”“窗帘”），不要用"*"

完全无法解析时输出：[{{"a":"UNKNOWN","s":"*","n":"*","t":"Unknown","q":"one"}}]
"""

PROMPT_REGRESSION_CASES = [
    # ===== 基础示例：单设备单动作（具体中文设备名） =====
    {
        "input": "打开客厅主灯",
        "expected": [{"a":"打开","s":"客厅","n":"主灯","t":"Light","q":"one"}],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "关闭卧室床头灯",
        "expected": [{"a":"关闭","s":"卧室","n":"床头灯","t":"Light","q":"one"}],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "打开书房台灯",
        "expected": [{"a":"打开","s":"书房","n":"台灯","t":"Light","q":"one"}],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "关闭客厅落地灯",
        "expected": [{"a":"关闭","s":"客厅","n":"落地灯","t":"Light","q":"one"}],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "打开厨房吊灯",
        "expected": [{"a":"打开","s":"厨房","n":"吊灯","t":"Light","q":"one"}],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "打开阳台灯带",
        "expected": [{"a":"打开","s":"阳台","n":"灯带","t":"Light","q":"one"}],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "关闭卧室吸顶灯",
        "expected": [{"a":"关闭","s":"卧室","n":"吸顶灯","t":"Light","q":"one"}],
        "tags": ["single", "specific_name"],
    },
    {
        "input": "打开客厅窗帘",
        "expected": [{"a":"打开","s":"客厅","n":"窗帘","t":"Blind","q":"one"}],
        "tags": ["single", "specific_name", "blind"],
    },
    {
        "input": "关闭书房百叶窗",
        "expected": [{"a":"关闭","s":"书房","n":"百叶窗","t":"Blind","q":"one"}],
        "tags": ["single", "specific_name", "blind"],
    },
    {
        "input": "打开客厅空调",
        "expected": [{"a":"打开","s":"客厅","n":"空调","t":"AirConditioner","q":"one"}],
        "tags": ["single", "specific_name", "ac"],
    },
    {
        "input": "关闭卧室空调",
        "expected": [{"a":"关闭","s":"卧室","n":"空调","t":"AirConditioner","q":"one"}],
        "tags": ["single", "specific_name", "ac"],
    },
    {
        "input": "打开客厅风扇",
        "expected": [{"a":"打开","s":"客厅","n":"风扇","t":"Fan","q":"one"}],
        "tags": ["single", "specific_name", "fan"],
    },
    {
        "input": "打开客厅电视",
        "expected": [{"a":"打开","s":"客厅","n":"电视","t":"Television","q":"one"}],
        "tags": ["single", "specific_name", "tv"],
    },
    {
        "input": "打开客厅音响",
        "expected": [{"a":"打开","s":"客厅","n":"音响","t":"NetworkAudio","q":"one"}],
        "tags": ["single", "specific_name", "audio"],
    },
    {
        "input": "打开书房音箱",
        "expected": [{"a":"打开","s":"书房","n":"音箱","t":"NetworkAudio","q":"one"}],
        "tags": ["single", "specific_name", "audio"],
    },
    {
        "input": "打开客厅智能插座",
        "expected": [{"a":"打开","s":"客厅","n":"智能插座","t":"SmartPlug","q":"one"}],
        "tags": ["single", "specific_name", "plug"],
    },
    {
        "input": "打开厨房墙壁开关",
        "expected": [{"a":"打开","s":"厨房","n":"墙壁开关","t":"Switch","q":"one"}],
        "tags": ["single", "specific_name", "switch"],
    },
    {
        "input": "打开阳台传感器",
        "expected": [{"a":"打开","s":"阳台","n":"传感器","t":"Unknown","q":"one"}],
        "tags": ["single", "specific_name", "unknown_type"],
    },

    # ===== 参数设置示例 =====
    {
        "input": "把客厅主灯调到50%",
        "expected": [{"a":"设置亮度=50%","s":"客厅","n":"主灯","t":"Light","q":"one"}],
        "tags": ["parameter", "brightness"],
    },
    {
        "input": "把书房空调调到26度",
        "expected": [{"a":"设置温度=26C","s":"书房","n":"空调","t":"AirConditioner","q":"one"}],
        "tags": ["parameter", "temperature"],
    },
    {
        "input": "把卧室风扇风速调到70%",
        "expected": [{"a":"设置风速=70%","s":"卧室","n":"风扇","t":"Fan","q":"one"}],
        "tags": ["parameter", "fan_speed"],
    },
    {
        "input": "把风扇风速调到70%",
        "expected": [{"a":"设置风速=70%","s":"*","n":"风扇","t":"Fan","q":"all"}],
        "tags": ["parameter", "fan_speed", "generic", "all_quantifier"],
    },
    {
        "input": "把客厅电视音量调到30%",
        "expected": [{"a":"设置音量=30%","s":"客厅","n":"电视","t":"Television","q":"one"}],
        "tags": ["parameter", "volume"],
    },
    {
        "input": "把客厅窗帘遮光调到50%",
        "expected": [{"a":"设置遮光=50%","s":"客厅","n":"窗帘","t":"Blind","q":"one"}],
        "tags": ["parameter", "shade_level"],
    },

    # ===== 多动作拆分 =====
    {
        "input": "打开卧室床头灯调到50%",
        "expected": [
            {"a":"打开","s":"卧室","n":"床头灯","t":"Light","q":"one"},
            {"a":"设置亮度=50%","s":"卧室","n":"床头灯","t":"Light","q":"one"},
        ],
        "tags": ["multi_action", "specific_name"],
    },
    {
        "input": "打开客厅空调并设置到26度",
        "expected": [
            {"a":"打开","s":"客厅","n":"空调","t":"AirConditioner","q":"one"},
            {"a":"设置温度=26C","s":"客厅","n":"空调","t":"AirConditioner","q":"one"},
        ],
        "tags": ["multi_action", "specific_name"],
    },

    # ===== 多目标拆分 =====
    {
        "input": "打开客厅主灯和落地灯",
        "expected": [
            {"a":"打开","s":"客厅","n":"主灯","t":"Light","q":"one"},
            {"a":"打开","s":"客厅","n":"落地灯","t":"Light","q":"one"},
        ],
        "tags": ["multi_target", "specific_name"],
    },
    {
        "input": "关闭卧室床头灯和吸顶灯",
        "expected": [
            {"a":"关闭","s":"卧室","n":"床头灯","t":"Light","q":"one"},
            {"a":"关闭","s":"卧室","n":"吸顶灯","t":"Light","q":"one"},
        ],
        "tags": ["multi_target", "specific_name"],
    },

    # ===== 泛指类型（NAME=类型中文名） =====
    {
        "input": "打开所有灯",
        "expected": [{"a":"打开","s":"*","n":"灯","t":"Light","q":"all"}],
        "tags": ["generic", "all_quantifier"],
    },
    {
        "input": "关闭所有空调",
        "expected": [{"a":"关闭","s":"*","n":"空调","t":"AirConditioner","q":"all"}],
        "tags": ["generic", "all_quantifier"],
    },
    {
        "input": "把所有窗帘打开",
        "expected": [{"a":"打开","s":"*","n":"窗帘","t":"Blind","q":"all"}],
        "tags": ["generic", "all_quantifier"],
    },
    {
        "input": "把所有灯调到50%",
        "expected": [{"a":"设置亮度=50%","s":"*","n":"灯","t":"Light","q":"all"}],
        "tags": ["generic", "all_quantifier", "parameter"],
    },
    {
        "input": "把所有空调调到26度",
        "expected": [{"a":"设置温度=26C","s":"*","n":"空调","t":"AirConditioner","q":"all"}],
        "tags": ["generic", "all_quantifier", "parameter"],
    },

    # ===== 多房间组合 =====
    {
        "input": "打开客厅和卧室的灯",
        "expected": [{"a":"打开","s":"客厅,卧室","n":"灯","t":"Light","q":"all"}],
        "tags": ["multi_room", "all_quantifier"],
    },
    {
        "input": "关闭客厅和书房的空调",
        "expected": [{"a":"关闭","s":"客厅,书房","n":"空调","t":"AirConditioner","q":"all"}],
        "tags": ["multi_room", "all_quantifier"],
    },
    {
        "input": "把客厅和卧室的窗帘都打开",
        "expected": [{"a":"打开","s":"客厅,卧室","n":"窗帘","t":"Blind","q":"all"}],
        "tags": ["multi_room", "all_quantifier"],
    },
    {
        "input": "把卧室和客厅的窗帘都打开",
        "expected": [{"a":"打开","s":"卧室,客厅","n":"窗帘","t":"Blind","q":"all"}],
        "tags": ["multi_room", "all_quantifier"],
    },

    # ===== 排除房间（except 量词） =====
    {
        "input": "打开除卧室以外的灯",
        "expected": [{"a":"打开","s":"*,!卧室","n":"灯","t":"Light","q":"except"}],
        "tags": ["except", "exclude_room"],
    },
    {
        "input": "关闭除了客厅以外的空调",
        "expected": [{"a":"关闭","s":"*,!客厅","n":"空调","t":"AirConditioner","q":"except"}],
        "tags": ["except", "exclude_room"],
    },
    {
        "input": "把除书房和卧室以外的灯都关了",
        "expected": [{"a":"关闭","s":"*,!书房,!卧室","n":"灯","t":"Light","q":"except"}],
        "tags": ["except", "exclude_multiple_rooms"],
    },

    # ===== 任意量词 + 数量 =====
    {
        "input": "打开两盏灯",
        "expected": [{"a":"打开","s":"*","n":"灯","t":"Light","q":"any","c":2}],
        "tags": ["any_n", "any_quantifier", "count"],
    },
    {
        "input": "关闭三个插座",
        "expected": [{"a":"关闭","s":"*","n":"插座","t":"SmartPlug","q":"any","c":3}],
        "tags": ["any_n", "any_quantifier", "count"],
    },
    {
        "input": "随便打开一个灯",
        "expected": [{"a":"打开","s":"*","n":"灯","t":"Light","q":"any","c":1}],
        "tags": ["any_n", "any_quantifier", "count"],
    },

    # ===== 指代（@last） =====
    {
        "input": "打开它",
        "expected": [{"a":"打开","s":"*","n":"@last","t":"Unknown","q":"one"}],
        "tags": ["reference_last"],
    },
    {
        "input": "关闭那个",
        "expected": [{"a":"关闭","s":"*","n":"@last","t":"Unknown","q":"one"}],
        "tags": ["reference_last"],
    },
    {
        "input": "把它调到50%",
        "expected": [{"a":"设置亮度=50%","s":"*","n":"@last","t":"Unknown","q":"one"}],
        "tags": ["reference_last", "parameter"],
    },

    # ===== 复杂组合 =====
    {
        "input": "把客厅主灯打开并调到80%然后打开窗帘",
        "expected": [
            {"a":"打开","s":"客厅","n":"主灯","t":"Light","q":"one"},
            {"a":"设置亮度=80%","s":"客厅","n":"主灯","t":"Light","q":"one"},
            {"a":"打开","s":"客厅","n":"窗帘","t":"Blind","q":"one"},
        ],
        "tags": ["complex", "multi_action", "multi_target"],
    },
    {
        "input": "打开客厅和卧室的所有灯并调到50%",
        "expected": [
            {"a":"打开","s":"客厅,卧室","n":"灯","t":"Light","q":"all"},
            {"a":"设置亮度=50%","s":"客厅,卧室","n":"灯","t":"Light","q":"all"},
        ],
        "tags": ["complex", "multi_action", "multi_room"],
    },

    # ===== 特殊动作 =====
    {
        "input": "让客厅电视静音",
        "expected": [{"a":"静音","s":"客厅","n":"电视","t":"Television","q":"one"}],
        "tags": ["special_action", "mute"],
    },
    {
        "input": "让电视静音",
        "expected": [{"a":"静音","s":"*","n":"电视","t":"Television","q":"all"}],
        "tags": ["special_action", "mute", "generic", "all_quantifier"],
    },
    {
        "input": "取消书房音箱静音",
        "expected": [{"a":"取消静音","s":"书房","n":"音箱","t":"NetworkAudio","q":"one"}],
        "tags": ["special_action", "unmute"],
    },
    {
        "input": "取消音响静音灯",
        "expected": [{"a":"关闭","s":"*","n":"音响静音灯","t":"Light","q":"one"}],
        "tags": ["special_action", "cancel_light"],
    },
    {
        "input": "把客厅风扇设为自然风",
        "expected": [{"a":"设置风模式=自然风","s":"客厅","n":"风扇","t":"Fan","q":"one"}],
        "tags": ["special_action", "mode"],
    },
    {
        "input": "开始阳台洗衣机烘干",
        "expected": [{"a":"开始烘干","s":"阳台","n":"洗衣机","t":"Washer","q":"one"}],
        "tags": ["special_action", "washer"],
    },
    {
        "input": "暂停阳台洗衣机烘干",
        "expected": [{"a":"暂停烘干","s":"阳台","n":"洗衣机","t":"Washer","q":"one"}],
        "tags": ["special_action", "washer"],
    },

    # ===== 查询状态 =====
    {
        "input": "查询客厅主灯状态",
        "expected": [{"a":"查询状态","s":"客厅","n":"主灯","t":"Light","q":"one"}],
        "tags": ["query"],
    },
    {
        "input": "查询卧室空调温度",
        "expected": [{"a":"查询温度","s":"卧室","n":"空调","t":"AirConditioner","q":"one"}],
        "tags": ["query"],
    },

    # ===== 无法解析 =====
    {
        "input": "（无法理解的输入）",
        "expected": [{"a":"UNKNOWN","s":"*","n":"*","t":"Unknown","q":"one"}],
        "tags": ["unknown"],
    },
    {
        "input": "ajsdkfjalskdfj",
        "expected": [{"a":"UNKNOWN","s":"*","n":"*","t":"Unknown","q":"one"}],
        "tags": ["unknown"],
    },
]
