#!/usr/bin/env bash
# T3 反测哨兵：这个测试永远应该红。它变绿 = 完成门被放宽了。
echo "T3 是反测哨兵，永远返回 1"; exit 1
