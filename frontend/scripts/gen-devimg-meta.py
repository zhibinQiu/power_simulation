#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成设备图「图形真实边界」清单 deviceImgMeta.json。

背景：public/2D-image/devices/*.png 为透明背景素材，设备图形并不铺满整张画布
（例如 热风炉.png 为 2048×2048 方形，但圆筒本体只占中间 1027×1883 ≈ 46% 面积）。
前端若按「整张图」等比 contain 到节点图带，透明留白会被当成图形的一部分，
导致设备图形缩小并偏离节点边缘 —— 连线端点贴节点盒缘时与设备之间出现明显空隙。

本脚本逐张解析 PNG 的 alpha 通道，求出 alpha>阈值 的最小外接矩形（图形真实边界），
输出 { 图名: {W,H,bx,by,bw,bh} } 供前端按「图形边界」定位与缩放。

另外输出四条边的「边缘实体跨距」et/eb/el/er = [a,b]（图像素，绝对坐标）：
取图形边缘各 6%（最少 6px）厚的一带，记录该带内**有实体的最小/最大坐标**。

还输出上下轮廓剖面 tp/bp（各 32 段，值 = 该段内实体最上/最下缘的 y，按图形高度归一化）：
图形外接盒的角并不等于设备轮廓 —— 典型如转炉（梨形炉体 + 顶部氧枪，外接盒左上角完全空）
与烧结机（台车带只在最左端高、其余是低矮台面）。连线自上/下接入时若端点只按外接盒取 y，
就会停在轮廓之外的空气里。前端用剖面把端点落到「该 x 处的真实轮廓」上。

用法：新增/替换设备图后重跑本脚本，再 build（dev 下刷新即可）：
    python scripts/gen-devimg-meta.py
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DEV_DIR = os.path.join(HERE, '..', 'public', '2D-image', 'devices')
OUT = os.path.join(HERE, '..', 'src', 'data', 'deviceImgMeta.json')
ALPHA_MIN = 8   # alpha 阈值：低于此值视为透明（滤掉抗锯齿边缘噪声）
PROF_N = 32     # 上下轮廓剖面的分段数（段宽 ≈ 图形宽/32，节点宽 340 时约 10px/段）


def bbox_of(path):
    im = Image.open(path).convert('RGBA')
    a = np.array(im)[:, :, 3]
    W, H = im.size
    ys, xs = np.where(a > ALPHA_MIN)
    if len(xs) == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return {'W': W, 'H': H, 'bx': x0, 'by': y0, 'bw': x1 - x0 + 1, 'bh': y1 - y0 + 1}


def edge_spans_of(path, bb):
    """四条边的实体跨距（图像素绝对坐标）：[min, max] 或 None（该带全透明）。"""
    a = np.array(Image.open(path).convert('RGBA'))[:, :, 3] > ALPHA_MIN
    x0, y0 = bb['bx'], bb['by']
    sub = a[y0:y0 + bb['bh'], x0:x0 + bb['bw']]
    h, w = sub.shape
    band_y = max(6, int(round(h * 0.06)))   # 上下边的取样厚度
    band_x = max(6, int(round(w * 0.06)))   # 左右边的取样厚度

    def span_x(rows):
        idx = np.where(rows.any(axis=0))[0]
        return None if len(idx) == 0 else [int(idx.min()) + x0, int(idx.max()) + x0]

    def span_y(cols):
        idx = np.where(cols.any(axis=1))[0]
        return None if len(idx) == 0 else [int(idx.min()) + y0, int(idx.max()) + y0]

    out = {}
    for key, val in (('et', span_x(sub[:band_y, :])), ('eb', span_x(sub[h - band_y:, :])),
                     ('el', span_y(sub[:, :band_x])), ('er', span_y(sub[:, w - band_x:]))):
        if val:
            out[key] = val
    return out


def profiles_of(path, bb):
    """上下轮廓剖面：每段内实体最上缘（tp）/最下缘（bp）的 y，按图形高度归一化 0..1。

    值 0 = 该段顶部就是图形外接盒顶；全透明的段记 None（前端回退到外接盒边）。"""
    a = np.array(Image.open(path).convert('RGBA'))[:, :, 3] > ALPHA_MIN
    sub = a[bb['by']:bb['by'] + bb['bh'], bb['bx']:bb['bx'] + bb['bw']]
    h, w = sub.shape
    tp, bp = [], []
    for i in range(PROF_N):
        c0 = int(round(i * w / PROF_N))
        c1 = max(c0 + 1, int(round((i + 1) * w / PROF_N)))
        rows = np.where(sub[:, c0:c1].any(axis=1))[0]
        if len(rows) == 0:
            tp.append(None)
            bp.append(None)
        else:
            tp.append(round(float(rows.min()) / h, 3))
            bp.append(round(float(rows.max()) / h, 3))
    return tp, bp


def main():
    dev_dir = os.path.abspath(DEV_DIR)
    if not os.path.isdir(dev_dir):
        print('目录不存在:', dev_dir)
        return 1
    meta = {}
    for fn in sorted(os.listdir(dev_dir)):
        if not fn.lower().endswith('.png'):
            continue
        key = fn[:-4]
        path = os.path.join(dev_dir, fn)
        bb = bbox_of(path)
        if not bb:
            print('  ! 空图(全透明)，跳过:', fn)
            continue
        bb.update(edge_spans_of(path, bb))
        tp, bp = profiles_of(path, bb)
        bb['tp'] = tp
        bb['bp'] = bp
        meta[key] = bb
        cover = bb['bw'] * bb['bh'] / (bb['W'] * bb['H']) * 100
        print('  %-14s %4dx%-5d 内容 %4dx%-5d 占比 %5.1f%%  et=%s er=%s' % (
            key, bb['W'], bb['H'], bb['bw'], bb['bh'], cover,
            bb.get('et'), bb.get('er')))
    with open(os.path.abspath(OUT), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write('\n')
    print('\n共 %d 张 -> %s' % (len(meta), os.path.abspath(OUT)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
