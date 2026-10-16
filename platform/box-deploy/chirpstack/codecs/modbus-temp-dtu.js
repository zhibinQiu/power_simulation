/*
 * ChirpStack v4 自定义 JS codec —— 透传 DTU + Modbus RTU 温度传感器（Class C 问-答取数）
 * =============================================================================
 * 场景：
 *   mapper 每拍下行完整 Modbus RTU 读帧(hex) -> DTU 透传到 RS485 -> 从站应答 ->
 *   DTU 把传感器响应帧整包 LoRaWAN 上行 -> ChirpStack 得到的是原始字节，mapper 无法
 *   直接取数，必须由本 codec 把字节解成 JSON object，mapper 按 payloadKey 取值。
 *
 * 上行字节两种形态（都兼容）：
 *   A. DTU 全透传，上行 = 传感器 Modbus RTU 响应帧（7 字节）：
 *      [07][03][02][温度Hi][温度Lo][CRC低][CRC高]
 *   B. DTU 剥壳（只透传数据域），上行 = 裸 2 字节温度：[温度Hi][温度Lo]
 *
 * 输出：
 *   { "temperature": <寄存器原始值，有符号 16 位整型> }
 *   单位换算放到 mapper 点位 scale（一般温度模块为 0.1°C/LSB，config 里 scale=0.1）。
 *
 * 用法：ChirpStack UI -> 设备 -> Configuration -> Payload codec ->
 *       Custom JavaScript -> 粘贴本文件 -> 保存。
 */
function Decode(fPort, bytes, variables) {
  if (!bytes || bytes.length === 0) {
    return {};
  }

  // 拷贝一份，避免修改入参
  var payload = bytes.slice(0, bytes.length);

  // 形态 A：标准 Modbus RTU 读保持寄存器响应（从站 07 / 功能码 03 / 数据长度 2）
  // 前 3 字节为帧头，第 4~5 字节为温度字，CRC 在尾部（本解码器不校验 CRC，容忍 DTU 加壳差异）
  if (payload.length >= 5 && payload[0] === 0x07 && payload[1] === 0x03 && payload[2] === 0x02) {
    payload = payload.slice(3, 5);
  } else if (payload.length >= 2) {
    // 形态 B / 未知加壳：兜底取前 2 字节当作温度字
    payload = payload.slice(0, 2);
  } else {
    return {};
  }

  // Modbus 16 位寄存器默认大端（高字节在前）；若实测读数乱序，交换 payload[0]/payload[1]
  var raw = (payload[0] << 8) | payload[1];
  if (raw > 0x7FFF) {
    raw -= 0x10000; // 有符号：零下温度
  }

  return { temperature: raw };
}

// 下行编码占位：mapper 下行直接发布原始 hex（不走 ChirpStack Encode），保留空实现。
function Encode(fPort, obj, variables) {
  return [];
}
