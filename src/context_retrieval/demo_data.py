"""演示数据。"""

from context_retrieval.models import Device, CommandSpec, ValueRange, ValueOption


DEMO_DEVICES = [
    Device(
        id="lamp-1",
        name="老伙计",
        room="客厅",
        type="smartthings:switch",
        commands=[
            CommandSpec(id="main-switch-on", description="打开设备"),
            CommandSpec(id="main-switch-off", description="关闭设备"),
            CommandSpec(
                id="main-switchLevel-setLevel",
                description="调亮度",
                type="integer",
                value_range=ValueRange(minimum=0, maximum=100, unit="%"),
            ),
        ],
    ),
    Device(
        id="lamp-2",
        name="卧室灯",
        room="卧室",
        type="smartthings:switch",
        commands=[
            CommandSpec(id="main-switch-on", description="打开设备"),
            CommandSpec(id="main-switch-off", description="关闭设备"),
        ],
    ),
    Device(
        id="lamp-3",
        name="厨房灯",
        room="厨房",
        type="smartthings:switch",
        commands=[
            CommandSpec(id="main-switch-on", description="打开设备"),
            CommandSpec(id="main-switch-off", description="关闭设备"),
        ],
    ),
    Device(
        id="ac-1",
        name="大白",
        room="客厅",
        type="smartthings:air-conditioner",
        commands=[
            CommandSpec(id="main-switch-on", description="打开空调"),
            CommandSpec(id="main-switch-off", description="关闭空调"),
            CommandSpec(
                id="main-thermostat-setTemperature",
                description="设置温度",
                type="integer",
                value_range=ValueRange(minimum=16, maximum=30, unit="℃"),
            ),
            CommandSpec(
                id="main-mode-setMode",
                description="设置模式",
                type="string",
                value_list=[
                    ValueOption(value="cool", description="制冷"),
                    ValueOption(value="heat", description="制热"),
                    ValueOption(value="auto", description="自动"),
                ],
            ),
        ],
    ),
    Device(
        id="curtain-1",
        name="客厅窗帘",
        room="客厅",
        type="smartthings:curtain",
        commands=[
            CommandSpec(id="main-curtain-open", description="打开窗帘"),
            CommandSpec(id="main-curtain-close", description="关闭窗帘"),
        ],
    ),
    Device(
        id="sensor-1",
        name="客厅温度传感器",
        room="客厅",
        type="smartthings:temperature-sensor",
        commands=[
            CommandSpec(id="main-temperature-read", description="读取温度"),
        ],
    ),
]


# FakeLLM 预设响应
DEMO_LLM_PRESETS = {
    "打开老伙计": {
        "action": {"kind": "open"},
        "name_hint": "老伙计",
    },
    "关闭客厅灯": {
        "action": {"kind": "close"},
        "name_hint": "客厅灯",
    },
    "打开客厅的灯": {
        "action": {"kind": "open"},
        "scope_include": ["客厅"],
        "type_hint": "light",
    },
    "关闭所有灯": {
        "action": {"kind": "close"},
        "quantifier": "all",
        "type_hint": "light",
    },
    "打开除卧室以外的灯": {
        "action": {"kind": "open"},
        "quantifier": "except",
        "scope_exclude": ["卧室"],
        "type_hint": "light",
    },
    "打开大白": {
        "action": {"kind": "open"},
        "name_hint": "大白",
    },
    "把空调温度设置为26度": {
        "action": {"kind": "set", "target_value": "26"},
        "name_hint": "空调",
    },
    "客厅温度是多少": {
        "action": {"kind": "query"},
        "scope_include": ["客厅"],
        "type_hint": "sensor",
    },
}
