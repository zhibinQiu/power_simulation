"""能碳一体机设备 YAML 渲染（工厂模式 + 注册表）。

业务可替换点：DeviceModel / Device 两份 KubeEdge v1beta1 YAML 如何按协议生成。
- ModbusDeviceYamlRenderer：    Modbus RTU/TCP（寄存器映射）；
- OpcuaDeviceYamlRenderer：     OPC-UA（节点浏览）；
- BluetoothDeviceYamlRenderer： BLE（特征 UUID）；
- LoraDeviceYamlRenderer：      LoRaWAN（网关桥接，DevEUI/AppKey + 上行 payloadKey）；
- CellularDeviceYamlRenderer：  5G/4G 模块自监控（AT 命令信号/ICCID/速率）。

新增协议：继承 DeviceYamlRenderer 并实现 render_config_data（及可选 render_visitor），
再向 DeviceYamlFactory 注册即可，设备管理业务无需改动。

结构约定（与云端 v1beta1 CRD 对齐，见 kubeedge-console-ops.md §5.2）：
协议映射位于 Device.spec.protocol（protocolName + configData，visitors 在 configData 内）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

# ---------------------------------------------------------------------------
# v1beta1 常量（属性类型 / 寄存器类型 / 访问模式）
# ---------------------------------------------------------------------------

# v1beta1 DeviceModel 属性 type 为标量枚举：INT/FLOAT/DOUBLE/STRING/BOOLEAN/BYTES/STREAM
MODEL_TYPE = {
    "int": "INT", "integer": "INT", "float": "FLOAT", "double": "DOUBLE",
    "string": "STRING", "boolean": "BOOLEAN", "bool": "BOOLEAN",
    "bytes": "BYTES", "stream": "STREAM",
}
# v1beta1 modbus visitor 的 register 取值（KubeEdge Device protocol configData.visitors）
REG_TYPE = {
    "holdingregister": "HoldingRegister", "inputregister": "InputRegister",
    "coil": "CoilRegister", "discreteinput": "DiscreteInputRegister",
}
ACCESS_MODE = {"r": "ReadOnly", "rw": "ReadWrite"}

# 统一协议注册名：KubeEdge edgecore 按 Device.spec.protocol.protocolName 匹配 mapper 注册的
# protocol 名，匹配才把设备路由给该 mapper。盒子 box_mapper.py 为多协议单进程
# （modbus-rtu / modbus-tcp / opcua），统一注册 nengtan-iot，故所有协议 YAML 的
# protocolName 都输出此名（协议细节在 configData / visitors 中区分），
# 与盒子 config.json 顶层 "protocol": "nengtan-iot" 保持一致。
KUBEEDGE_PROTOCOL_NAME = "nengtan-iot"


def _yaml_esc(v: Any) -> str:
    """安全转义用户输入为 YAML 标量（防特殊字符破坏模板结构）。"""
    s = str(v if v is not None else "")
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def _prop_yaml(p: Dict[str, Any]) -> str:
    """渲染一个属性点的 DeviceModel properties 片段（v1beta1 标量字段，见 §5.2）。

    v1beta1 的协议映射不在 DeviceModel 里，而在 Device.spec.protocol.configData.visitors。
    """
    ptype = MODEL_TYPE.get(str(p.get("type", "float")).lower(), "FLOAT")
    access = ACCESS_MODE.get(str(p.get("accessMode", "r")).lower(), "ReadOnly")
    lines = [
        f"  - name: \"{_yaml_esc(p.get('name', 'prop'))}\"",
        f"    description: \"{_yaml_esc(p.get('desc', ''))}\"",
        f"    type: {ptype}",
        f"    accessMode: {access}",
        f"    unit: \"{_yaml_esc(p.get('unit', ''))}\"",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 渲染器策略接口
# ---------------------------------------------------------------------------


class DeviceYamlRenderer(ABC):
    """按协议渲染 DeviceModel + Device 两份 YAML 的抽象基类。"""

    protocol: str = ""

    def render(self, p: Dict[str, Any]) -> Dict[str, str]:
        """生成 {model, device} 两份 YAML（公共骨架 + 协议专属 configData）。"""
        model_name = _yaml_esc(p.get("modelName", "box-metric-model"))
        device_name = _yaml_esc(p.get("deviceName", "box-device"))
        namespace = _yaml_esc(p.get("namespace", "default"))
        node_name = _yaml_esc(p.get("nodeName", "edge-node"))
        collect_cycle = int(p.get("collectCycle", 1000))
        desc = _yaml_esc(p.get("desc", ""))
        props: list[Dict[str, Any]] = p.get("properties", []) or []

        props_txt = "\n".join([_prop_yaml(x) for x in props])
        visitors_txt = "\n".join([self.render_visitor(x) for x in props])

        model_yaml = f"""apiVersion: devices.kubeedge.io/v1beta1
kind: DeviceModel
metadata:
  name: "{model_name}"
  namespace: "{namespace}"
spec:
  properties:
{props_txt}
"""

        props_lines = []
        for prop in props:
            props_lines.append(f"  - name: \"{_yaml_esc(prop.get('name', 'prop'))}\"")
            props_lines.append(f"    collectCycle: {collect_cycle}")
        props_txt2 = "\n".join(props_lines) if props_lines else "  - name: \"value\"\n    collectCycle: 1000"

        protocol_cfg = self.render_config_data(p, visitors_txt)
        device_yaml = f"""apiVersion: devices.kubeedge.io/v1beta1
kind: Device
metadata:
  name: "{device_name}"
  namespace: "{namespace}"
  labels:
    description: \"{desc}\"
spec:
  deviceModelRef:
    name: "{model_name}"
  nodeName: "{node_name}"
  properties:
{props_txt2}
""" + protocol_cfg
        return {"model": model_yaml, "device": device_yaml}

    def render_visitor(self, p: Dict[str, Any]) -> str:
        """渲染一个属性点的 visitors 片段；协议专属子字段由子类覆写。

        缩进约定：visitors 键 8 空格（configData 子键），序列项 8 空格，子字段 10 空格。
        """
        return f"        - propertyName: \"{_yaml_esc(p.get('name', 'prop'))}\""

    @abstractmethod
    def render_config_data(self, p: Dict[str, Any], visitors_txt: str) -> str:
        """渲染 Device.spec.protocol 协议配置块（含 visitors_txt）。"""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 三种协议渲染器
# ---------------------------------------------------------------------------


class ModbusDeviceYamlRenderer(DeviceYamlRenderer):
    """Modbus RTU/TCP：寄存器映射 + 通信参数（serial/tcp）。"""

    protocol = "modbus"

    def render_visitor(self, p: Dict[str, Any]) -> str:
        reg = REG_TYPE.get(str(p.get("registerType", "holdingRegister")).lower(), "HoldingRegister")
        lines = [
            f"        - propertyName: \"{_yaml_esc(p.get('name', 'prop'))}\"",
            f"          register: {reg}",
            f"          offset: {int(p.get('register', 0) or 0)}",
            f"          limit: {int(p.get('limit', 0) or 0)}",
            f"          scale: {p.get('scale', 1.0)}",
            f"          isSwap: {'true' if p.get('isSwap', False) else 'false'}",
            f"          isRegisterSwap: {'true' if p.get('isRegisterSwap', False) else 'false'}",
        ]
        return "\n".join(lines)

    def render_config_data(self, p: Dict[str, Any], visitors_txt: str) -> str:
        comm = p.get("comm", {})
        comm_type = str(comm.get("commType", "serial")).lower()
        if comm_type == "tcp":
            com_cfg = (
                "        com:\n"
                "          commType: tcp\n"
                f"          ip: \"{_yaml_esc(comm.get('tcpIP', '192.168.1.10'))}\"\n"
                f"          port: {int(comm.get('tcpPort', 502))}\n"
            )
        else:
            com_cfg = (
                "        com:\n"
                "          commType: serial\n"
                f"          serialPort: \"{_yaml_esc(comm.get('serialPort', '/dev/ttyS0'))}\"\n"
                f"          baudRate: {int(comm.get('baudRate', 9600))}\n"
                f"          dataBits: {int(comm.get('dataBits', 8))}\n"
                f"          parity: \"{_yaml_esc(comm.get('parity', 'none'))}\"\n"
                f"          stopBits: {int(comm.get('stopBits', 1))}\n"
            )
        slave_id = int(comm.get("slaveID", 1) or 1)
        return (
            "  protocol:\n"
            f"    protocolName: {KUBEEDGE_PROTOCOL_NAME}\n"
            "    configData:\n"
            f"{com_cfg}        slaveID: {slave_id}\n"
            "        visitors:\n"
            f"{visitors_txt}\n"
        )


class OpcuaDeviceYamlRenderer(DeviceYamlRenderer):
    """OPC-UA：服务器 URL + 凭据 + 节点浏览映射。"""

    protocol = "opcua"

    def render_visitor(self, p: Dict[str, Any]) -> str:
        lines = [
            f"        - propertyName: \"{_yaml_esc(p.get('name', 'prop'))}\"",
            "          opcua:",
            f"            nodeID: \"{_yaml_esc(p.get('nodeID', ''))}\"",
        ]
        return "\n".join(lines)

    def render_config_data(self, p: Dict[str, Any], visitors_txt: str) -> str:
        opcua = p.get("opcua", {})
        return (
            "  protocol:\n"
            f"    protocolName: {KUBEEDGE_PROTOCOL_NAME}\n"
            "    configData:\n"
            f"        url: \"{_yaml_esc(opcua.get('url', 'opc.tcp://127.0.0.1:4840'))}\"\n"
            f"        userName: \"{_yaml_esc(opcua.get('userName', ''))}\"\n"
            f"        password: \"{_yaml_esc(opcua.get('password', ''))}\"\n"
            f"        securityMode: \"{_yaml_esc(opcua.get('securityMode', 'None'))}\"\n"
            f"        securityPolicy: \"{_yaml_esc(opcua.get('securityPolicy', 'None'))}\"\n"
            "        visitors:\n"
            f"{visitors_txt}\n"
        )


class BluetoothDeviceYamlRenderer(DeviceYamlRenderer):
    """BLE：MAC 地址 + 特征 UUID 映射。"""

    protocol = "bluetooth"

    def render_visitor(self, p: Dict[str, Any]) -> str:
        lines = [
            f"        - propertyName: \"{_yaml_esc(p.get('name', 'prop'))}\"",
            "          bluetooth:",
            f"            characteristicUUID: \"{_yaml_esc(p.get('characteristicUUID', ''))}\"",
        ]
        return "\n".join(lines)

    def render_config_data(self, p: Dict[str, Any], visitors_txt: str) -> str:
        bt = p.get("bluetooth", {})
        return (
            "  protocol:\n"
            f"    protocolName: {KUBEEDGE_PROTOCOL_NAME}\n"
            "    configData:\n"
            f"        macAddress: \"{_yaml_esc(bt.get('macAddress', 'AA:BB:CC:DD:EE:FF'))}\"\n"
            "        visitors:\n"
            f"{visitors_txt}\n"
        )


class LoraDeviceYamlRenderer(DeviceYamlRenderer):
    """LoRaWAN：盒子侧 LoRa 网关（SX1302 + ChirpStack）桥接，上行 JSON payloadKey 映射。

    链路：LoRa 传感器 → LoRaWAN 无线 → 盒子 LoRa 网关 → 本地 mosquitto
          (application/+/device/+/event/up) → box_mapper LoraReader 解析 → DMI twins。
    """

    protocol = "lora"

    def render_visitor(self, p: Dict[str, Any]) -> str:
        lines = [
            f"        - propertyName: \"{_yaml_esc(p.get('name', 'prop'))}\"",
            "          lora:",
            f"            payloadKey: \"{_yaml_esc(p.get('payloadKey', ''))}\"",
        ]
        return "\n".join(lines)

    def render_config_data(self, p: Dict[str, Any], visitors_txt: str) -> str:
        lora = p.get("lora", {})
        broker = str(lora.get("broker", "127.0.0.1") or "127.0.0.1")
        port = lora.get("port")
        if port not in (None, "") and ":" not in broker:
            broker = "%s:%s" % (broker, port)
        return (
            "  protocol:\n"
            f"    protocolName: {KUBEEDGE_PROTOCOL_NAME}\n"
            "    configData:\n"
            f"        broker: \"{_yaml_esc(broker)}\"\n"
            f"        applicationID: \"{_yaml_esc(lora.get('applicationID', ''))}\"\n"
            f"        devEUI: \"{_yaml_esc(lora.get('devEUI', ''))}\"\n"
            f"        appKey: \"{_yaml_esc(lora.get('appKey', ''))}\"\n"
            f"        region: \"{_yaml_esc(lora.get('region', 'CN470'))}\"\n"
            f"        dataRate: \"{_yaml_esc(lora.get('dataRate', 'SF7BW125'))}\"\n"
            "        visitors:\n"
            f"{visitors_txt}\n"
        )


class CellularDeviceYamlRenderer(DeviceYamlRenderer):
    """5G/4G 模块自监控：AT 命令采集信号/ICCID/注册态/上下行速率。

    把 5G 模块当一台"设备"纳入统一管理：盒子 box_mapper CellularReader
    通过 AT 口（/dev/ttyUSB*）读取模块状态，速率统计读蜂窝接口计数差分。
    """

    protocol = "cellular"

    def render_visitor(self, p: Dict[str, Any]) -> str:
        lines = [
            f"        - propertyName: \"{_yaml_esc(p.get('name', 'prop'))}\"",
            "          cellular:",
            f"            kind: \"{_yaml_esc(p.get('kind', 'signal'))}\"",
        ]
        return "\n".join(lines)

    def render_config_data(self, p: Dict[str, Any], visitors_txt: str) -> str:
        cellular = p.get("cellular", {})
        return (
            "  protocol:\n"
            f"    protocolName: {KUBEEDGE_PROTOCOL_NAME}\n"
            "    configData:\n"
            f"        serialPort: \"{_yaml_esc(cellular.get('serialPort', '/dev/ttyUSB2'))}\"\n"
            f"        baudRate: {int(cellular.get('baudRate', 115200))}\n"
            f"        apn: \"{_yaml_esc(cellular.get('apn', ''))}\"\n"
            f"        iface: \"{_yaml_esc(cellular.get('iface', 'wwan0'))}\"\n"
            "        visitors:\n"
            f"{visitors_txt}\n"
        )


# ---------------------------------------------------------------------------
# 工厂（注册表模式）：新增协议在此注册一行即可
# ---------------------------------------------------------------------------


class DeviceYamlFactory:
    """按协议名获取渲染器；未知协议回退为 Modbus（向后兼容）。"""

    _registry: Dict[str, type] = {
        ModbusDeviceYamlRenderer.protocol: ModbusDeviceYamlRenderer,
        OpcuaDeviceYamlRenderer.protocol: OpcuaDeviceYamlRenderer,
        BluetoothDeviceYamlRenderer.protocol: BluetoothDeviceYamlRenderer,
        LoraDeviceYamlRenderer.protocol: LoraDeviceYamlRenderer,
        CellularDeviceYamlRenderer.protocol: CellularDeviceYamlRenderer,
    }

    @classmethod
    def register(cls, renderer_cls: type) -> None:
        """注册新的协议渲染器（协议名取自 renderer_cls.protocol）。"""
        cls._registry[renderer_cls.protocol] = renderer_cls

    @classmethod
    def get(cls, protocol: str) -> DeviceYamlRenderer:
        key = (protocol or "modbus").strip().lower()
        renderer_cls = cls._registry.get(key, ModbusDeviceYamlRenderer)
        return renderer_cls()
