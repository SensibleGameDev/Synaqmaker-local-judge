# Contest Day Checklist

Complete checklist for running ICPC/IOI style programming contests with Synaqmaker Local Judge.

## 📅 Two Weeks Before Contest

### Hardware & Infrastructure
- [ ] Confirm server hardware meets requirements (8+ cores, 16+ GB RAM recommended)
- [ ] Test network infrastructure (gigabit LAN for 100 participants)
- [ ] Prepare backup server/laptop (optional but recommended)
- [ ] Check all participant workstations are functional
- [ ] Ensure UPS (Uninterruptible Power Supply) is available

### Software Setup
- [ ] Install/update Synaqmaker Local Judge on server
- [ ] Build all Docker images (Python, C++, C#)
- [ ] Run system health check: `python system_check.py`
- [ ] Configure MAX_CHECKS based on CPU cores (see README.md)
- [ ] Change default admin password using SUPERSECRET_PASSWORD_GENERATOR.py
- [ ] Test server with a practice contest

### Training
- [ ] Train backup staff on system operation
- [ ] Prepare troubleshooting guide for team
- [ ] Test disaster recovery procedures

---

## 📅 One Week Before Contest

### Problem Preparation
- [ ] Finalize all contest problems (1-10 problems)
- [ ] Write comprehensive test cases (minimum 10 per problem)
  - Include edge cases (empty input, maximum values)
  - Include corner cases
  - Include sample test cases
  - Include strong test cases to prevent weak solutions
- [ ] Upload problems to system via admin panel
- [ ] Test each problem manually with correct and incorrect solutions
- [ ] Verify time limits are reasonable (2x correct solution time)
- [ ] Test memory limits are appropriate
- [ ] Prepare problem statements (PDF format recommended)

### Contest Configuration
- [ ] Decide contest duration (typical: 4-5 hours for ICPC)
- [ ] Choose scoring mode:
  - ICPC: Binary (solved/unsolved) with time penalties
  - IOI: Partial points based on test cases passed
  - All-or-Nothing: 100 points or 0
- [ ] Set scoreboard freeze time (last 1 hour for ICPC)
- [ ] Decide on allowed programming languages
- [ ] Choose contest mode:
  - Free mode: Anyone can join
  - Closed mode: Pre-registered participants with passwords
- [ ] If closed mode: Prepare participant list and passwords

### Testing
- [ ] Full system stress test: `python stress_test_v2.py`
- [ ] Verify 100+ concurrent submissions work correctly
- [ ] Test from different machines on the network
- [ ] Verify scoreboard updates in real-time
- [ ] Test WebSocket connections from participant machines

---

## 📅 One Day Before Contest

### Final System Checks
- [ ] Run full stress test again: `python stress_test_v2.py`
  - Target: 500 submissions, 0 errors
  - Average processing time < 10 seconds
- [ ] Verify all problems work end-to-end
- [ ] Test submission from participant workstations
- [ ] Check server disk space (minimum 10 GB free)
- [ ] Review system logs for any errors
- [ ] Backup clean database: `cp testirovschik.db testirovschik_backup_clean.db`

### Documentation
- [ ] Print problem statements for all participants (2 copies per team)
- [ ] Print quick reference guides (if applicable)
- [ ] Prepare system access instructions handout
- [ ] Create announcement templates for common issues

### Network Configuration
- [ ] Verify server has static IP address
- [ ] Test connectivity from all participant workstations
- [ ] Check firewall allows port 5000 (or configured port)
- [ ] Measure network latency (ping from participants to server)
- [ ] Verify internet is disabled (for network isolation, optional)

### Physical Setup
- [ ] Set up server in secure, accessible location
- [ ] Ensure good cooling/ventilation for server
- [ ] Connect server to UPS
- [ ] Set up admin monitoring station (can see server screen/logs)
- [ ] Prepare USB flash drive with installation files (emergency backup)

### Participant Workstations
- [ ] Clear browser cache on all machines
- [ ] Test browser access to server
- [ ] Verify text editors/IDEs are installed and working
- [ ] Remove/disable games and entertainment software
- [ ] Ensure all machines have network connectivity
- [ ] Install compilers if participants want to test locally (optional)

### Communication Setup
- [ ] Set up PA system or projector for announcements
- [ ] Prepare emergency contact information
- [ ] Establish communication channel with network admin
- [ ] Brief all staff on contest procedures

---

## 📅 Contest Day - Morning (3 hours before start)

### Server Preparation
- [ ] **Restart server computer** (fresh boot)
- [ ] Start Docker Desktop
  - Windows: Verify Docker Desktop is running (system tray icon)
  - Linux: `sudo systemctl start docker`
- [ ] Clean Docker cache: `docker system prune -f`
- [ ] Verify Docker images are available: `docker images`
- [ ] Run system health check: `python system_check.py`
- [ ] Start server: `2_START.bat` (Windows) or `python run.py` (Linux)
- [ ] Note server IP address for participants
- [ ] Verify server is accessible: http://localhost:5000

### Contest Setup
- [ ] Login to admin panel (http://SERVER_IP:5000/login)
- [ ] Create new contest (click "Создать олимпиаду")
- [ ] Select problems (verify correct problems are selected)
- [ ] Set duration (e.g., 300 minutes for 5 hours)
- [ ] Set scoring mode (ICPC/IOI/All-or-Nothing)
- [ ] Set freeze time if using (60 minutes for ICPC)
- [ ] Choose contest mode (Free/Closed)
- [ ] If closed mode: Upload participant list
- [ ] Set start time or leave for manual start
- [ ] **Write down 8-character Contest ID**

### Final Verification
- [ ] Test submission from participant machine:
  - Join contest using contest ID
  - Submit a simple solution
  - Verify it gets judged correctly
  - Check scoreboard updates
- [ ] Verify all problems are accessible
- [ ] Check live scoreboard displays correctly
- [ ] Test spectator view (if using): http://SERVER_IP:5000/spectate/CONTEST_ID

### Monitoring Setup
- [ ] Open 3 terminal windows:
  - Terminal 1: `tail -f logs/judge.log` (application logs)
  - Terminal 2: `docker stats` (container resource usage)
  - Terminal 3: System resource monitor
    - Windows: Task Manager (Performance tab)
    - Linux: `htop` or `top`
- [ ] Keep backup laptop nearby (if available)
- [ ] Have admin panel open in browser

### Participant Preparation
- [ ] Distribute problem statements
- [ ] Write access information on whiteboard:
  - Server URL: http://SERVER_IP:5000/olympiad/join
  - Contest ID: [8-character code]
  - If closed mode: Ensure participants have login credentials
- [ ] Give brief demo of system (5 minutes):
  - How to join contest
  - How to submit solutions
  - How to view results
  - How to read scoreboard

### Emergency Preparation
- [ ] Backup current database: `cp testirovschik.db testirovschik_precontest.db`
- [ ] Have latest backup accessible
- [ ] Prepare emergency announcements
- [ ] Brief staff on contingency procedures

---

## 🏁 Contest Start

### Starting the Contest
- [ ] Verify all participants have joined and are in lobby
- [ ] Make pre-contest announcements (rules, clarifications)
- [ ] In admin panel, click "Start" button
- [ ] Announce: "Contest has started!"
- [ ] Start external timer (backup timing method)

### Initial Monitoring (First 30 minutes)
- [ ] Watch for surge of submissions
- [ ] Monitor queue size (should stay manageable)
- [ ] Check server CPU/RAM usage (should be <80%)
- [ ] Watch for error messages in logs
- [ ] Verify scoreboard is updating correctly
- [ ] Be ready to handle clarification requests

---

## 🔄 During Contest

### Continuous Monitoring

**Every 15 minutes:**
- [ ] Check application logs for errors
- [ ] Monitor Docker container status: `docker ps`
- [ ] Check server resources (CPU, RAM, disk)
- [ ] Verify scoreboard is updating
- [ ] Check queue size (participants should not wait >1 minute)

**Watch For:**
- Error messages in logs (grep ERROR logs/judge.log)
- High CPU usage (>90% sustained)
- High RAM usage (>90%)
- Network connectivity issues
- Participant complaints about slow judging
- Database lock warnings

### Common Issues & Quick Fixes

**Queue growing too large:**
- Check MAX_CHECKS value
- Monitor Docker container execution time
- Consider temporary reduction if overloaded

**Participant can't access:**
- Verify network connection
- Check firewall
- Verify server IP hasn't changed
- Have participant refresh browser (Ctrl+F5)

**Scoreboard not updating:**
- Check WebSocket connection (browser console)
- Have participants refresh page
- Verify server is responding

**Submission taking too long:**
- Normal for complex C++ compilation
- Check if participant's code has infinite loop (will timeout)
- Monitor Docker stats for stuck containers

### Clarifications
- [ ] Monitor for clarification requests
- [ ] Respond promptly and fairly
- [ ] Document all clarifications
- [ ] Broadcast important clarifications to all participants

### Backup Database
- [ ] Automatic backups run every 10 minutes to `backups/`
- [ ] Verify backups are being created
- [ ] Manual backup if needed: `cp testirovschik.db testirovschik_mid_contest.db`

---

## 🏆 Contest End

### Stopping Submissions
When time expires:
- [ ] Server automatically stops accepting submissions
- [ ] Verify countdown timer reached zero
- [ ] Announce "Contest has ended - no more submissions"
- [ ] Allow final submissions to finish judging

### Scoreboard Freeze (ICPC Style)
If you used freeze:
- [ ] Navigate to Reveal page
- [ ] Display frozen scoreboard to audience
- [ ] Animate reveals from bottom to top
- [ ] Create dramatic finish!

### Final Results
- [ ] Verify all submissions have been judged
- [ ] Download results as Excel: Admin panel → Download Results
- [ ] Save copy of final scoreboard (screenshot or export)
- [ ] Backup final database: `cp testirovschik.db testirovschik_final.db`

### Data Preservation
- [ ] Copy entire `backups/` folder to external drive
- [ ] Copy `logs/` folder for analysis
- [ ] Export participant submissions (if needed)
- [ ] Save final database permanently

---

## 🎓 Post-Contest

### Immediate Actions
- [ ] Thank participants and staff
- [ ] Announce preliminary results (if ready)
- [ ] Address any protests or clarifications
- [ ] Keep server running until all protests resolved

### Data Analysis
- [ ] Review submission statistics
- [ ] Analyze problem difficulty (solve rates)
- [ ] Check for suspicious activity
- [ ] Generate reports for organizers

### System Cleanup
- [ ] Archive contest data
- [ ] Clean Docker containers: `docker system prune -af`
- [ ] Archive old logs
- [ ] Document any issues encountered

### Feedback Collection
- [ ] Gather participant feedback
- [ ] Get staff feedback on system
- [ ] Document improvements for next contest
- [ ] Update procedures based on lessons learned

---

## 🚨 Emergency Procedures

### Server Crash
1. **Restart server immediately:** `python run.py`
2. System auto-recovers from database
3. Announce to participants: "Please refresh your browser"
4. Verify scoreboard restored correctly
5. Maximum data loss: 10 minutes (backup interval)

### Network Failure
1. Check network cables
2. Restart switch/router if needed
3. Verify server IP unchanged
4. Test connectivity: `ping SERVER_IP`
5. Participants can continue when restored (code saved in browser)

### Docker Failure
1. Restart Docker: Windows (Docker Desktop), Linux (`systemctl restart docker`)
2. Restart server: `python run.py`
3. Verify Docker images: `docker images`
4. Test submission to verify recovery

### Database Corruption
1. Stop server (Ctrl+C)
2. Restore from latest backup: `cp backups/testirovschik_LATEST.db testirovschik.db`
3. Restart server: `python run.py`
4. Data loss: Maximum 10 minutes

### Need to Switch to Backup Server
1. Copy `testirovschik.db` to backup laptop
2. Start server on backup laptop
3. Announce new IP to participants
4. Update whiteboard with new URL
5. Switch time: ~5 minutes

### Critical Issue - Contest Extension
If major technical issue causes >15 minute downtime:
- [ ] Announce to participants
- [ ] Document downtime duration
- [ ] Extend contest by equivalent time
- [ ] Update in admin panel if needed
- [ ] Make fair decision for all

---

## 📊 Success Criteria

**System is working correctly if:**
- ✅ All submissions are judged within 60 seconds
- ✅ No errors in application logs
- ✅ Scoreboard updates in real-time (<5 second delay)
- ✅ Server CPU usage <80%
- ✅ Server RAM usage <80%
- ✅ No participant complaints about system
- ✅ All Docker containers complete successfully
- ✅ Database responds quickly (<100ms queries)

**If any criteria fails, investigate immediately!**

---

## 📝 Notes Section

Use this space for contest-specific notes:

**Contest Details:**
- Date: ________________
- Participants: ________
- Problems: ___________
- Duration: ___________

**Staff:**
- Server operator: ______________
- Technical support: ____________
- Network admin: _______________

**Issues Encountered:**
- ________________________________
- ________________________________
- ________________________________

**Performance Stats:**
- Peak submissions/min: _________
- Max queue size: ______________
- Longest judging time: _________
- Server uptime: _______________

---

**Good luck with your contest! 🎯🏆**
