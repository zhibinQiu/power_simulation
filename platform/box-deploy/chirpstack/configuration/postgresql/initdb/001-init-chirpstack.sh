#!/bin/bash
# ChirpStack 数据库初始化（PostgreSQL 官方镜像会在数据目录为空时自动执行本目录脚本）
# ChirpStack schema migrations 需要 pg_trgm（GIN 索引）与 hstore 扩展
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    create extension if not exists pg_trgm;
    create extension if not exists hstore;
EOSQL
