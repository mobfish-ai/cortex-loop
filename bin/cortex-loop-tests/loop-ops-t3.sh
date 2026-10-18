#!/usr/bin/env bash
# T3 negative sentinel: this test must stay red forever. Turning green means the completion gate was loosened.
echo "T3 is a negative sentinel and always returns 1"; exit 1
