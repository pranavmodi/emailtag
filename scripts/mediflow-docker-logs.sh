#!/bin/bash

# Script to SSH to mediflow and tail Docker logs in separate iTerm tabs
# Usage: ./mediflow-docker-logs.sh

# Docker service names (matching docker-compose.yml)
# Maps screen name -> docker compose service name
declare -A SERVICES
SERVICES=(
    ["emailtag"]="web"
    ["celery"]="worker"
    ["emailUI"]="frontend"
    ["mcp"]="mcp"
)

# Screen names to open (in order)
SCREENS=("emailtag" "celery" "emailUI" "mcp")

# Create a persistent expect script in the same directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPECT_SCRIPT="$SCRIPT_DIR/.mediflow-docker-expect.sh"

# Write expect script with password embedded
cat > "$EXPECT_SCRIPT" << 'EXPECTEOF'
#!/usr/bin/expect -f
set timeout 30
set service_name [lindex $argv 0]
set password {Trewqaszx88990!@#}
spawn ssh mediflow
expect {
    timeout { puts "Timeout waiting for password prompt"; exit 1 }
    "password:" { send "$password\r" }
}
expect {
    timeout { puts "Timeout waiting for shell"; exit 1 }
    "$ " { send "docker compose -f /home/fret/work/emailtag/docker-compose.yml logs --tail 100 -f $service_name\r" }
}
interact
EXPECTEOF
chmod +x "$EXPECT_SCRIPT"

# Open first tab in current window, then add tabs
FIRST=true
for screen in "${SCREENS[@]}"; do
    service="${SERVICES[$screen]}"
    if $FIRST; then
        osascript -e "
            tell application \"iTerm\"
                activate
                tell current window
                    tell current session
                        write text \"expect '$EXPECT_SCRIPT' '$service'\"
                    end tell
                end tell
            end tell
        "
        FIRST=false
    else
        osascript -e "
            tell application \"iTerm\"
                tell current window
                    create tab with default profile
                    tell current session
                        write text \"expect '$EXPECT_SCRIPT' '$service'\"
                    end tell
                end tell
            end tell
        "
    fi
    sleep 0.5
done

echo "Opened ${#SCREENS[@]} Docker log tabs in iTerm"
