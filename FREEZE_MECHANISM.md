# ICPC-Style Freeze/Unfreeze Mechanism

## Overview
This implementation follows the ICPC "Blind Freeze" philosophy where the scoreboard is frozen during the last part of the contest to create suspense. The public scoreboard shows limited information while participants always see their own results and admins see everything in real-time.

## How It Works

### 1. Freeze Triggering
When the contest reaches the freeze threshold (e.g., last 60 minutes):
- A snapshot of the current scoreboard is created and stored in `oly['frozen_scoreboard']`
- The flag `oly['freeze_triggered']` is set to `True`
- The freeze time is recorded in `oly['freeze_time']`

**Code:** `_get_olympiad_state()` function, lines 119-129

### 2. The Masking Logic (`_apply_freeze_mask`)
This is the core of the freeze mechanism:

**What spectators see on the public scoreboard:**
- **OLD scores** - The scores/penalties from the frozen snapshot
- **NEW attempt counts** - The current number of attempts (so they know someone is trying)
- **Pending indicators** - Orange "?" for tasks where attempts increased during freeze

**What spectators don't see on the public scoreboard:**
- Whether new submissions passed or failed
- New scores earned during freeze
- Ranking changes due to freeze-period activity

**What participants always see (their own results):**
- Full feedback for ALL their submissions (pass/fail, verdict, test results)
- Their submission history with actual verdicts
- This is NOT affected by freeze - participants need to know if their solution works

**Implementation:**
```python
def _apply_freeze_mask(frozen_scoreboard, live_scoreboard):
    # For each participant:
    # - Show frozen total_score and total_penalty
    # - For each task:
    #   - Show frozen score, passed status, penalty
    #   - Show LIVE attempt count (visible activity)
    #   - Set is_frozen_pending=True if live_attempts > frozen_attempts
```

### 3. Admin/Spectator Separation

**Two SocketIO Rooms:**
1. **`olympiad_id`** - Public room for spectators and participants (scoreboard masked, personal results unmasked)
2. **`olympiad_id_admin`** - Private room for organizers (all data unmasked)

**How it works:**
- When organizers join, they join BOTH rooms
- When submissions are processed, the system emits:
  - Personal result (unmasked) → Participant who submitted
  - Masked scoreboard → Public room (for spectators)
  - Live scoreboard → Admin room (for organizers)
- Admins see green/red cells in real-time
- Spectators see orange "?" cells for pending submissions
- Participants always see their own actual submission results

**Code:**
- `handle_join_room()` - Lines 437-457
- `process_single_submission()` - Lines 711-726

### 4. Frontend Display

**Spectator Board (`spectator_board.html`):**
- Checks `is_frozen_pending` flag for each task
- If `true`, displays orange cell with "?" and attempt count
- CSS animation: `pulseOrange` creates pulsing effect
- Spectators see the frozen scoreboard state

**Participant View (`olympiad_run.html`):**
- Participants ALWAYS see their actual submission results (pass/fail, verdict, tests)
- Personal feedback is never masked during freeze
- The scoreboard view shows frozen state (like spectators)
- Individual task history shows real verdicts

**Admin View (`olympiad_host.html`):**
- Joins admin SocketIO room
- Receives unmasked data with all current results
- Sees normal green (passed) / red (failed) cells
- Sees live scoreboard updates

### 5. The Reveal Ceremony (`presentation.html`)

After the contest ends, the presentation page:
1. Loads `frozen_scoreboard` and `final_scoreboard` from database
2. Compares them to find all pending submissions
3. Reveals results one by one, starting from the bottom of standings
4. Shows animations when participants move up in ranking
5. Announces diplomas and first-to-solve achievements

## Data Flow During Freeze

```
┌─────────────────────────────────────────────────────────────┐
│ Participant submits code during freeze                       │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ Judge processes submission                                    │
│ - Updates olympiad state with result                          │
│ - Marks olympiad as dirty (needs scoreboard recalc)          │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ process_single_submission() calls emit twice:                 │
│                                                               │
│ 1. _get_olympiad_state(id, is_admin=False)                   │
│    → _apply_freeze_mask()                                     │
│    → emit to olympiad_id (spectators see ?)                  │
│                                                               │
│ 2. _get_olympiad_state(id, is_admin=True)                    │
│    → returns live scoreboard (no mask)                        │
│    → emit to olympiad_id_admin (admins see result)           │
└───────────────────────────────────────────────────────────────┘
```

## Example Scenario

**Before Freeze (17:00):**
- Alice: 2 problems solved, 150 penalty
- Bob: 1 problem solved, 50 penalty

**Freeze Triggered (17:00):**
- System takes snapshot of current standings

**During Freeze (17:05):**
- Bob submits solution for problem B → gets Accepted (Bob sees "Accepted" immediately)
- Alice tries problem C → gets Wrong Answer (Alice sees "WA on test 3" immediately)

**What Spectators See (Scoreboard):**
```
Place | Name  | Solved | Penalty | A | B   | C
1     | Alice |   2    |  150    | + | +   | ?3   ← Orange, pulsing
2     | Bob   |   1    |   50    | + | ?3  | -    ← Orange, pulsing
```

**What Bob Sees (His View):**
- Submission result: "✅ Accepted! Solution accepted."
- History: Shows "Accepted" verdict for problem B
- Knows his solution passed!

**What Alice Sees (Her View):**
- Submission result: "❌ WA on test 3"
- History: Shows "Wrong Answer" verdict with test results
- Knows she needs to fix her solution

**What Admins See (Scoreboard):**
```
Place | Name  | Solved | Penalty | A | B  | C
1     | Bob   |   3    |  250    | + | +  | +   ← Green (new solve)
2     | Alice |   2    |  150    | + | +  | -3  ← Red (3 WA)
```

**After Reveal:**
- Animation shows Bob's B turning green
- Bob's row slides up to 1st place
- Diploma announcement for Bob
- Alice's C turning red revealed
- Final standings displayed

## Configuration

Freeze is configured per contest in `olympiad_create.html`:
```python
config = {
    'freeze_minutes': 60,  # Last 60 minutes frozen
    # ... other config ...
}
```

Set `freeze_minutes: 0` to disable freeze.

## Database Storage

When a contest with freeze ends:
- `frozen_scoreboard` - Snapshot at freeze time
- `final_scoreboard` - Final results
- `freeze_time` - Unix timestamp when freeze started
- `is_revealed` - Boolean flag if reveal ceremony was shown

Stored in `olympiad_frozen_data` table via `db.save_frozen_scoreboard()`

## Testing the Freeze

1. Create a contest with 30+ minute duration
2. Set `freeze_minutes` to 5
3. Start contest
4. Have participants solve problems normally
5. When 5 minutes remain, freeze activates
6. Submit more solutions
7. Open spectator board → see orange "?" cells
8. Open admin host page → see actual results
9. End contest
10. Navigate to reveal page → see animation

## Key Implementation Files

- `app.py` - Lines 90-306: Core freeze logic
- `app.py` - Lines 437-524: SocketIO room management
- `app.py` - Lines 526-726: Submission processing with dual emit
- `templates/spectator_board.html` - Spectator UI with masked data
- `templates/olympiad_run.html` - Participant UI with masked data
- `templates/olympiad_host.html` - Admin UI with live data
- `templates/presentation.html` - ICPC-style reveal ceremony and presentation
- `db_manager.py` - Frozen data persistence

## Security Considerations

✅ **Enforced separation** - Spectators cannot access admin room  
✅ **Session validation** - Admin status checked via session  
✅ **No data leakage** - Masked data never contains actual results  
✅ **Database integrity** - Frozen snapshot immutable after creation  

## Performance Notes

- Freeze mask computation is O(n*m) where n=participants, m=tasks
- Computed on-demand, cached until next submission
- No performance impact on non-frozen contests
- Dual emit adds minimal overhead (~1ms per submission)
