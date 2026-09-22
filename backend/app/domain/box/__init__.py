"""能碳一体机领域：设备 YAML 渲染。

对外导出：
- DeviceYamlFactory：按协议创建渲染器的工厂（注册表模式，协议可插拔）。
"""
from .device_yaml import (
    BluetoothDeviceYamlRenderer,
    DeviceYamlFactory,
    DeviceYamlRenderer,
    ModbusDeviceYamlRenderer,
    OpcuaDeviceYamlRenderer,
)
from .hwid import (
    HWID_LABEL,
    backfill_hwids,
    ensure_hwid,
    hwid_of,
    new_hwid,
    slug,
)

__all__ = [
    "DeviceYamlRenderer",
    "ModbusDeviceYamlRenderer",
    "OpcuaDeviceYamlRenderer",
    "BluetoothDeviceYamlRenderer",
    "DeviceYamlFactory",
    "HWID_LABEL",
    "hwid_of",
    "new_hwid",
    "ensure_hwid",
    "backfill_hwids",
    "slug",
]
