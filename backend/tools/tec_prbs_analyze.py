#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TEC PRBS 实验数据分析与出图（方案.md 第 19 章图表复现脚本）。

用法：
    python3 backend/tools/tec_prbs_analyze.py
输入：仓库根目录 tec_prbs_run.csv（prbs_tec_ident.py 采集）
输出：方案.assets/fig1_prbs_response.png / fig2_static_nonlinearity.png / fig3_model_validation.png
依赖：numpy、matplotlib
"""
import csv, math, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["PingFang SC", "Hiragino Sans GB", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "方案.assets")
os.makedirs(OUT, exist_ok=True)

cols = ["t","current_set","current","power","voltage",
        "shuitong_temp","servers_temp","env_temp","zhileng_temp","temp_age","temp_new"]
data = {c: [] for c in cols}
with open(os.path.join(ROOT, "tec_prbs_run.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        for c in cols:
            v = row[c].strip()
            data[c].append(float(v) if v else np.nan)
for c in cols:
    data[c] = np.array(data[c], dtype=float)

t_min = data["t"] / 60.0
TS = 5.0
N = len(data["t"])
print("样本数 N =", N, " 时长 %.1f min" % (data["t"][-1] / 60))

def fill_nan(x):
    idx = np.arange(len(x))
    ok = ~np.isnan(x)
    return np.interp(idx, idx[ok], x[ok])

u   = fill_nan(data["current"])        # 实测电流
uset= data["current_set"]
pw  = fill_nan(data["power"])
cup = fill_nan(data["servers_temp"])   # 水杯水温（CV）
air = fill_nan(data["zhileng_temp"])   # 冷端风口温度
env = fill_nan(data["env_temp"])
wat = fill_nan(data["shuitong_temp"])  # 冷却水温度

miss = {c: int(np.isnan(data[c]).sum()) for c in cols}
print("缺测行数：", miss)
print("丢包率(温度最严重通道 env) = %.1f%%" % (100*miss["env_temp"]/N))

# ---------------- 图 1：激励与响应全览 ----------------
fig, ax = plt.subplots(2, 1, figsize=(11, 6.2), sharex=True,
                       gridspec_kw={"height_ratios": [1, 1.4]})
ax[0].plot(t_min, uset, lw=1.2, color="#1f77b4", label="设定电流（PRBS 激励）")
ax[0].plot(t_min, u, lw=0.8, color="#ff7f0e", alpha=0.8, label="实测电流")
ax[0].set_ylabel("电流 (A)")
ax[0].legend(loc="lower right", fontsize=9)
ax[0].set_title("TEC 小样 5 电平 PRBS 开环激励实验（真实采集，%d 点 x 5s）" % N)
ax[0].grid(alpha=0.3)

ax[1].plot(t_min, cup, lw=1.4, color="#d62728", label="水杯水温（被控 CV）")
ax[1].plot(t_min, air, lw=1.0, color="#2ca02c", label="冷端风口温度")
ax[1].plot(t_min, wat, lw=1.0, color="#9467bd", label="热端冷却水温")
ax[1].plot(t_min, env, lw=1.0, color="#7f7f7f", label="环境室温")
ax[1].axvspan(0, 16.7, color="orange", alpha=0.12)
ax[1].text(3, 41, "初始非稳态段\n（水杯 41.9 度自然降温，\n辨识时剔除）", fontsize=8.5, color="#b36b00")
ax[1].set_xlabel("时间 (min)")
ax[1].set_ylabel("温度 (C)")
ax[1].legend(loc="upper right", fontsize=9, ncol=2)
ax[1].grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig1_prbs_response.png"), dpi=150)
plt.close(fig)

# ---------------- 静态关系（剔除初始 200 点） ----------------
K0 = 200  # 初始非稳态段剔除点
levels = [0, 1.25, 2.5, 3.75, 5.0]
stat = []
for lv in levels:
    m = (np.abs(uset - lv) < 1e-6)
    m[:K0] = False
    stat.append((lv, np.nanmean(pw[m]), np.nanmean(air[m]), np.nanmean(cup[m])))
stat = np.array(stat)
A = np.vstack([stat[:,0]**2, stat[:,0]]).T
coef, *_ = np.linalg.lstsq(A, stat[:,1], rcond=None)
p_fit = lambda I: coef[0]*I**2 + coef[1]*I
print("\n功率拟合 P = %.3f*I^2 + %.3f*I  (W)" % (coef[0], coef[1]))
for lv, p_, a_, c_ in stat:
    print("  I=%.2fA  P=%.2fW  风口=%.2fC  水杯=%.2fC" % (lv, p_, a_, c_))

fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
ax[0].scatter(u[K0:], pw[K0:], s=4, alpha=0.25, color="#1f77b4", label="实测点")
Is = np.linspace(0, 5, 100)
ax[0].plot(Is, p_fit(Is), "r-", lw=2,
           label="二次拟合 P=%.2fI2+%.2fI" % (coef[0], coef[1]))
ax[0].set_xlabel("TEC 电流 (A)")
ax[0].set_ylabel("TEC 功率 (W)")
ax[0].set_title("静态非线性1：功率随电流超线性增长")
ax[0].legend(fontsize=9)
ax[0].grid(alpha=0.3)

cool = env - air
ax[1].scatter(u[K0:], cool[K0:], s=4, alpha=0.25, color="#2ca02c",
              label="实测点（室温-风口）")
ax[1].plot(stat[:,0], np.nanmean(env[K0:]) - stat[:,2], "ro-", lw=2, ms=7,
           label="各电平均（驻留 25s 未达全稳态，仅示意趋势）")
ax[1].set_xlabel("TEC 电流 (A)")
ax[1].set_ylabel("冷端降温幅度 (C)")
ax[1].set_title("静态非线性2：制冷效果并非电流的线性放大")
ax[1].legend(fontsize=9)
ax[1].grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig2_static_nonlinearity.png"), dpi=150)
plt.close(fig)

# ---------------- FOPDT(ARX) 辨识：外层枚举滞后 + 内层最小二乘 ----------------
def fit_fopdt(y, u_mv, dvs, d_range, split=0.8):
    best = None
    ntr = int(len(y) * split)
    for d in d_range:
        cols_ = [y[:-1]]
        cols_.append(u_mv[: len(y)-1] if d == 0 else
                     np.concatenate([np.full(d, u_mv[0]), u_mv[: len(y)-1-d]]))
        for dv in dvs:
            cols_.append(dv[:-1])
        Phi = np.column_stack(cols_ + [np.ones(len(y)-1)])
        theta, *_ = np.linalg.lstsq(Phi[:ntr], y[1:ntr+1], rcond=None)
        pred_all = Phi @ theta
        res = y[1:] - pred_all
        nrmse = math.sqrt(np.mean(res[ntr:]**2)) / (np.max(y[ntr:]) - np.min(y[ntr:]))
        r2 = 1 - np.sum(res[ntr:]**2) / np.sum((y[ntr:] - np.mean(y[ntr:]))**2)
        sse_tr = np.sum(res[:ntr]**2)
        if best is None or sse_tr < best[0]:
            best = (sse_tr, d, theta, pred_all, nrmse, r2, ntr, res)
    return best

def report(name, best):
    sse, d, th, pred, nrmse, r2, ntr, res = best
    a, b = th[0], th[1]
    tau = -TS / math.log(a)
    K = b / (1 - a)
    print("\n[%s] 滞后 d=%d (%.0fs)  a=%.5f b=%.6f  tau=%.1fs  K=%.3f C/A"
          % (name, d, d*TS, a, b, tau, K))
    print("  测试段一步预测 NRMSE=%.2f%%  R2=%.4f" % (nrmse*100, r2))

report("慢通道 含初始段（对照）", fit_fopdt(cup, u, [air, env, wat], range(0, 13)))
b_slow = fit_fopdt(cup[K0:], u[K0:], [air[K0:], env[K0:], wat[K0:]], range(0, 13))
report("慢通道 剔除初始段", b_slow)
report("快通道 电流->风口", fit_fopdt(air[K0:], u[K0:], [], range(0, 9)))

sse, d2, th2, pred2, nrmse2, r2_2, ntr2, res2 = b_slow
a2, b2 = th2[0], th2[1]
print("  DV 系数：风口 %.4f  室温 %.4f  冷却水 %.4f  常数 %.3f"
      % (th2[2], th2[3], th2[4], th2[5]))

# 自由仿真（演示「一步拟合≠部署指标」）
ysim = np.zeros(N - K0)
ysim[0] = cup[K0]
ud = np.concatenate([np.full(d2, u[K0]), u[K0: N - d2]])
for k in range(N - K0 - 1):
    ysim[k+1] = a2*ysim[k] + b2*ud[k] + th2[2]*air[K0+k] + th2[3]*env[K0+k] \
               + th2[4]*wat[K0+k] + th2[5]
res_sim = cup[K0:] - ysim
nrmse_sim = math.sqrt(np.mean(res_sim[ntr2:]**2)) / (np.max(cup[K0+ntr2:]) - np.min(cup[K0+ntr2:]))
print("  自由仿真测试段 NRMSE=%.1f%%（对比一步预测：正式模型须用仿真误差准则 NLS 精修）"
      % (nrmse_sim*100))

# ---------------- 图 3：模型验证 ----------------
y_seg = cup[K0:]
t_seg = t_min[K0:]
res_test = res2[ntr2:]
nlags = 20
r0 = res_test - res_test.mean()
acf = [1.0] + [float(np.sum(r0[l:]*r0[:-l]) / np.sum(r0**2)) for l in range(1, nlags+1)]
ci = 1.96 / math.sqrt(len(res_test))

fig = plt.figure(figsize=(11, 7.5))
gs = fig.add_gridspec(3, 1, height_ratios=[1.5, 1, 1])
ax1 = fig.add_subplot(gs[0])
ax1.plot(t_seg, y_seg, lw=1.3, color="#d62728", label="实测水杯水温")
ax1.plot(t_seg[1:], pred2, lw=1.0, color="#1f77b4", alpha=0.9,
         label="模型一步预测（已剔除初始非稳态段）")
ax1.axvline(t_seg[ntr2], color="k", ls="--", lw=1)
ax1.text(t_seg[ntr2]+1, y_seg.max()-0.3, "<- 训练 | 测试 ->", fontsize=9)
ax1.set_ylabel("水温 (C)")
ax1.set_title("模型验证：实测 vs 一步预测（测试段 NRMSE=%.2f%%，R2=%.3f）"
              % (nrmse2*100, r2_2))
ax1.legend(fontsize=9)
ax1.grid(alpha=0.3)

ax2 = fig.add_subplot(gs[1], sharex=ax1)
ax2.plot(t_seg[1:], res2, lw=0.8, color="#555")
ax2.axhline(0, color="k", lw=0.8)
ax2.set_ylabel("残差 (C)")
ax2.set_xlabel("时间 (min)")
ax2.set_title("预测残差")
ax2.grid(alpha=0.3)

ax3 = fig.add_subplot(gs[2])
ax3.bar(range(nlags+1), acf, color="#1f77b4")
ax3.axhline(ci, color="r", ls="--", lw=1, label="95%% 置信界 +/-%.3f" % ci)
ax3.axhline(-ci, color="r", ls="--", lw=1)
ax3.set_xlabel("滞后阶数")
ax3.set_ylabel("ACF")
ax3.set_title("残差自相关检验（除 0 阶外均应落在置信界内）")
ax3.legend(fontsize=9)
ax3.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig3_model_validation.png"), dpi=150)
plt.close(fig)

print("\nACF(1..5) =", [round(x, 3) for x in acf[1:6]], " CI95=+/-%.3f" % ci)
print("图片已输出到：", OUT)
