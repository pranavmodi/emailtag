#!/bin/bash

# Script to SSH to mediflow, create screen sessions, and start all servers after reboot
# Usage: ./mediflow-startup.sh

# Create a persistent expect script in the same directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPECT_SCRIPT="$SCRIPT_DIR/.mediflow-startup-expect.sh"

# Write expect script with password embedded (avoids shell escaping issues)
cat > "$EXPECT_SCRIPT" << 'EXPECTEOF'
#!/usr/bin/expect -f
set timeout 30
set screen_name [lindex $argv 0]
set startup_cmd [lindex $argv 1]
set password {TreqazxcE33887#!T}
spawn ssh mediflow
expect {
    "password:" {
        send "$password\r"
    }
    timeout {
        puts "Connection timeout"
        exit 1
    }
}
expect {
    "$ " {
        send "screen -S $screen_name\r"
    }
    timeout {
        puts "Login timeout"
        exit 1
    }
}
expect "$ "
send "$startup_cmd\r"
interact
EXPECTEOF
chmod +x "$EXPECT_SCRIPT"

# Define screens and commands using arrays (compatible with bash 3.x)
SCREENS=(emailtag celery emailUI claude scripts mcp)
CMDS=(
    "cd /home/fret/work/emailtag && source emailtag/bin/activate && uvicorn app.main:app --reload --port 8444 --ssl-keyfile certs/privkey.pem --ssl-certfile certs/fullchain.pem"
    "cd /home/fret/work/emailtag && source emailtag/bin/activate && celery -A app.tasks.worker worker -l info -Q emails,tagging,processing,ocr"
    "cd /home/fret/work/emailtag/frontend/settings2 && npm run dev"
    "cd /home/fret/work/emailtag && source emailtag/bin/activate"
    "cd /home/fret/work/emailtag && source emailtag/bin/activate"
    "cd /home/fret/work/precisemcp && PORT=8001 uv run python3 server.py"
)

# Open tabs sequentially with delay between each connection
i=0
for screen in "${SCREENS[@]}"; do
    cmd="${CMDS[$i]}"

    echo "Starting screen: $screen..."

    if [ $i -eq 0 ]; then
        # First tab - use current window
        osascript -e "
            tell application \"iTerm\"
                activate
                tell current window
                    tell current session
                        write text \"expect '$EXPECT_SCRIPT' '$screen' '$cmd'\"
                    end tell
                end tell
            end tell
        "
    else
        # New tab in same window
        osascript -e "
            tell application \"iTerm\"
                tell current window
                    create tab with default profile
                    tell current session
                        write text \"expect '$EXPECT_SCRIPT' '$screen' '$cmd'\"
                    end tell
                end tell
            end tell
        "
    fi

    i=$((i + 1))

    # Wait for connection to establish before starting next one
    sleep 5
done

echo "Created ${#SCREENS[@]} screen sessions and started servers in iTerm tabs"
