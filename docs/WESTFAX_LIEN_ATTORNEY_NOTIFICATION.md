# Westfax Lien - Attorney Notification Requirement

## Overview

When a lien is received via Westfax, the system needs to look up the attorney on file and reply to the attorney's email for lien notifications. Additionally, if "notify case manager" is enabled, the case manager's email should be included in the reply.

## Requirements

1. **Attorney Lookup on Westfax Lien Receipt**
   - When a lien is received from Westfax, look up the attorney on file for the associated case/study.
   - Reply to the attorney's email address with lien notifications.

2. **Case Manager Notification (Conditional)**
   - If "notify case manager" is set to `true`, add the case manager's email to the reply as well.
   - This requires both the case manager's name and email to be available.

## Open Items / Dependencies

- **Notify Case Manager Flag**: The "notify case manager" information is not currently available from any existing API endpoint.
- **Action Taken**: Pranav Modi has reached out to the RadFlow team to request that the "notify case manager" flag, along with case manager name and email, be added to the study participants endpoint.
- **Blocked Until**: RadFlow team confirms availability of the notify case manager data in the study participants API response.

## Source

Conversation between Danny Rackow and Pranav Modi (captured Feb 2026).
