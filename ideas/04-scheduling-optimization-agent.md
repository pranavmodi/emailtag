# Scheduling Optimization Agent

## The Problem

MRI machines cost $1-3M each. CT scanners cost $500K-2M. Every empty slot is direct lost revenue ($500-2,000 per slot depending on modality). Imaging centers typically experience:

- 10-20% no-show rates
- Suboptimal machine utilization (especially off-peak hours)
- Cancellations that leave unfillable gaps
- Multi-study patients scheduled inefficiently (separate visits when they could be combined)
- No dynamic response to real-time capacity changes

## The Solution: An AI Scheduling Agent

### No-Show Prediction

Predict no-shows based on historical patterns:
- Patient type (PI vs. insurance vs. self-pay)
- Day of week and time of day
- Attorney firm (some firms' patients no-show more)
- Time since referral (longer gaps = higher no-show risk)
- Number of previous reschedules
- Weather, distance to facility

Use predictions to implement intelligent overbooking: "This 2pm MRI slot has a 35% no-show probability. Schedule a backup patient with a short-notice flexibility flag."

### Active Waitlist Management

When a cancellation comes in:
1. Immediately identify waitlist patients who match the slot (right modality, nearby, flexible schedule)
2. Contact them automatically via text/email: "An earlier appointment is available for your MRI on Tuesday at 10am. Would you like to switch?"
3. Fill the gap in minutes, not hours

### Multi-Study Optimization

"Patient needs both MRI lumbar and MRI cervical. Schedule back-to-back on the same machine to save the patient a trip and consolidate prep time."

- Reduces patient burden (fewer visits)
- Improves machine utilization (less setup/changeover)
- Faster case completion (attorney gets all imaging done sooner)

### Capacity Balancing

- "CT machine 2 has been at 95% utilization on Tuesdays but 60% on Thursdays. Redistribute."
- Identify which modalities are bottlenecked and which have excess capacity
- Suggest schedule template adjustments

### Proactive Attorney Coordination

"Your client's scan is scheduled for Thursday. We have an earlier opening on Tuesday. Would your client prefer the earlier date?"

- Sent proactively to the referring attorney's office
- Reduces time-to-scan (competitive advantage for the imaging center)
- Fills otherwise empty slots

## Value Proposition

"Every empty MRI slot is $500-2,000 in lost revenue. You have a no-show rate of X%. An AI agent that predicts and backfills no-shows could recover $Y per month in otherwise lost capacity."

## Revenue Impact Calculation

Assumptions for a center with 3 MRI machines:
- 15 scans/day/machine = 45 scans/day
- Average revenue per scan: $1,000
- Current no-show rate: 15% (6.75 empty slots/day)
- AI reduces effective no-show rate to 8% (3.6 empty slots/day)
- Recovered slots: 3.15/day * $1,000 = **$3,150/day = ~$70K/month**

Even at half these numbers, the ROI is immediate and obvious.

## Revenue Model

- Percentage of recovered revenue from filled slots that would have been empty
- Monthly subscription based on number of machines/modalities managed
- Performance guarantee: "If we don't reduce your no-show rate by at least X%, you don't pay"

## Build Effort: Medium

Requires deeper RadFlow scheduling integration (read and write access to the schedule). Patient communication automation (SMS/email). Prediction model training on historical scheduling data.

## Priority: MEDIUM-HIGH

Direct, measurable, immediate revenue impact. Less complex than insurance-related agents. Strong proof-of-value for expanding to other imaging centers. However, requires scheduling system write access which may face more resistance than read-only data access.
