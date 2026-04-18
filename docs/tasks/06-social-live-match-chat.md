# Task: Social Feature - Live Match Chat

## Goal
Enable real-time chat per match room.

## Core Features
- One room per match id.
- Authenticated usernames.
- Live message stream and auto-scroll.
- Basic moderation and anti-spam controls.

## Safety and Moderation
- Rate limits per user.
- Profanity filter and blocked terms.
- Report and mute controls.
- Temporary auto-mute for abuse patterns.

## Technical Notes
- Use WebSocket channels keyed by match id.
- Persist recent messages for replay on join.
- Add message retention policy.

## Acceptance Criteria
- Users can join and chat in match-specific rooms.
- Messages appear in near real time.
- Spam protection triggers correctly.
- Chat remains stable during peak traffic.

## Milestones
1. Define chat protocol and schema.
2. Build WebSocket room manager.
3. Build frontend chat widget.
4. Add moderation and abuse controls.
