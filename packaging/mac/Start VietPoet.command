#!/bin/bash
# Double-click to start VietPoet (opens in Terminal).
cd "$(dirname "$0")" || exit 1
bash launcher/start.sh "$@"
rc=$?
if [ $rc -ne 0 ] && [ $rc -ne 130 ]; then
    echo
    read -r -p "Press Enter to close this window." _
fi
exit $rc
