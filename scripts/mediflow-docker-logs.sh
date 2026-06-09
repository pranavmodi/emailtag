#!/bin/bash

# Script to SSH to mediflow and tail Docker logs in separate iTerm tabs
# Usage: ./mediflow-docker-logs.sh

# Docker service names (matching docker-compose.yml)
# Parallel arrays: SCREENS[i] is the tab label, DOCKER_SERVICES[i] is the docker compose service
SCREENS=("emailtag" "celery" "ocr" "emailUI" "mcp")
DOCKER_SERVICES=("web" "worker" "ocr-worker" "frontend" "mcp")

# Create a persistent expect script in the same directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPECT_SCRIPT="$SCRIPT_DIR/.mediflow-docker-expect.sh"
SCREEN_EXPECT_SCRIPT="$SCRIPT_DIR/.mediflow-screen-expect.sh"

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

# Write expect script for attaching to an existing screen session
cat > "$SCREEN_EXPECT_SCRIPT" << 'EXPECTEOF'
#!/usr/bin/expect -f
set timeout 30
set screen_name [lindex $argv 0]
set password {Trewqaszx88990!@#}
spawn ssh mediflow
expect {
    timeout { puts "Timeout waiting for password prompt"; exit 1 }
    "password:" { send "$password\r" }
}
expect {
    timeout { puts "Timeout waiting for shell"; exit 1 }
    "$ " { send "screen -dr $screen_name\r" }
}
interact
EXPECTEOF
chmod +x "$SCREEN_EXPECT_SCRIPT"

# Open first tab in current window, then add tabs
FIRST=true
for i in "${!SCREENS[@]}"; do
    screen="${SCREENS[$i]}"
    service="${DOCKER_SERVICES[$i]}"
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

# Open an additional tab attached to the existing 'claude' screen session
osascript -e "
    tell application \"iTerm\"
        tell current window
            create tab with default profile
            tell current session
                write text \"expect '$SCREEN_EXPECT_SCRIPT' 'claude'\"
            end tell
        end tell
    end tell
"

echo "Opened ${#SCREENS[@]} Docker log tabs plus 'claude' screen tab in iTerm"
