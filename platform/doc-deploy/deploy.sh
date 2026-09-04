#!/usr/bin/env bash
# ============================================================================
# 能碳平台 · 文档站首次拉起（platform/doc-deploy/deploy.sh，开发机执行）
#
# 说明：文档站（docs-site 容器，随平台同机，端口见 platform/servers.conf DOCS_PORT）不独立于
#       平台存在：全新服务器整站部署用 platform/bs-deploy/deploy.sh（含文档站服务）；
#       平台已运行、文档站尚未拉起时用本脚本。
#
# 实现：复用 update.sh —— 容器不存在时自动执行首次构建，首次部署与后续更新
#       共用同一条「构建 + 拉起」链路（幂等）。
#
# 用法：
#   bash platform/doc-deploy/deploy.sh     # 文档站首次拉起/重建
# ============================================================================
exec bash "$(dirname "$0")/update.sh"
