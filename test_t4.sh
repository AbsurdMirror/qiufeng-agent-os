#!/bin/bash
# Check if T4 files/features exist.
echo "Checking T4 implementations..."
find src -type f | xargs grep -E "(GW-P0-05|GW-P0-06|OE-P0-04|OE-P0-05|OE-P0-06|SH-P0-02|MP-P0-01|MP-P0-02|SM-P0-02|SM-P0-03|SM-P0-04)"
