# Deployment Guide for ICPC/IOI Contests

This guide provides detailed instructions for deploying Synaqmaker Local Judge for professional programming contests with 100 participants.

## Table of Contents
1. [Hardware Setup](#hardware-setup)
2. [Network Configuration](#network-configuration)
3. [Software Installation](#software-installation)
4. [Performance Optimization](#performance-optimization)
5. [Contest Preparation](#contest-preparation)
6. [Monitoring & Maintenance](#monitoring--maintenance)
7. [Disaster Recovery](#disaster-recovery)

## Hardware Setup

### Server Specifications

#### Minimum Setup (Development/Practice)
- **CPU**: Intel Core i5 (4 cores) or AMD Ryzen 5
- **RAM**: 8 GB DDR4
- **Storage**: 256 GB SSD
- **Network**: 100 Mbps Ethernet
- **Capacity**: Up to 30 participants

#### Recommended Setup (ICPC/IOI Contests)
- **CPU**: Intel Core i7-12700 (12 cores) or AMD Ryzen 7 5800X
- **RAM**: 32 GB DDR4 (16 GB minimum)
- **Storage**: 512 GB NVMe SSD
- **Network**: Gigabit Ethernet (1000 Mbps)
- **Capacity**: 100+ participants comfortably

#### Enterprise Setup (Multiple Contests)
- **CPU**: Intel Xeon or AMD EPYC (16+ cores)
- **RAM**: 64 GB ECC DDR4
- **Storage**: 1 TB NVMe SSD in RAID
- **Network**: 10 Gbps Ethernet with redundancy
- **Capacity**: 200+ participants, multiple simultaneous contests

### Storage Recommendations

**Database Storage:**
- Use SSD (not HDD) for database files
- SQLite with WAL mode benefits greatly from SSD
- Reserve 10 GB for database and logs
- Enable automatic backups (included)

**Docker Storage:**
- Docker images: ~2 GB
- Running containers: 256 MB each
- Reserve 20 GB for Docker data

## Network Configuration

### Network Topology

```
Internet
    |
[Router/Firewall]
    |
[Switch] ─── Server (192.168.1.100)
    |
    ├─── Participant PC 1 (192.168.1.101)
    ├─── Participant PC 2 (192.168.1.102)
    └─── Participant PC N (192.168.1.200)
```

### IP Address Planning

**Static IP for Server:**
- Assign static IP to avoid DNS issues
- Example: 192.168.1.100
- Configure in router DHCP settings

**DHCP for Participants:**
- Automatic IP assignment
- Reserve 192.168.1.101-200 for participants
- Keep server outside this range

### Firewall Configuration

**Windows Firewall:**
```cmd
# Allow incoming connections on port 5000
netsh advfirewall firewall add rule name="Synaqmaker Judge" dir=in action=allow protocol=TCP localport=5000
```

**Linux UFW:**
```bash
sudo ufw allow 5000/tcp
sudo ufw enable
```

**Router/Hardware Firewall:**
- No special configuration needed for LAN
- Block external access if connected to internet
- Allow only port 5000 internally

### Bandwidth Requirements

**Per Participant:**
- Active browsing: 0.5-1 Mbps
- Submission upload: negligible (code is small)
- Live scoreboard: 0.1-0.2 Mbps

**Total for 100 Participants:**
- Peak bandwidth: 50-100 Mbps
- Recommended: 200+ Mbps (headroom)
- Gigabit LAN eliminates concerns

### Network Quality Checks

**Before Contest:**
```bash
# Test server accessibility
# From participant machine:
ping 192.168.1.100
curl http://192.168.1.100:5000

# Test bandwidth
# Install iperf3 on server and client
# Server: iperf3 -s
# Client: iperf3 -c 192.168.1.100 -t 30
```

## Software Installation

### Windows Server Setup

**Step 1: Install Python**
1. Download Python 3.11+ from https://www.python.org/downloads/
2. Run installer
3. ✅ **Check "Add Python to PATH"**
4. Choose "Install Now"
5. Verify: `python --version`

**Step 2: Install Docker Desktop**
1. Download from https://www.docker.com/products/docker-desktop/
2. Install with default settings
3. Restart computer
4. Start Docker Desktop
5. Verify: `docker --version`

**Step 3: Configure Docker Resources**
1. Open Docker Desktop
2. Settings → Resources
3. Set CPU limit: 80% of total cores
4. Set Memory: 12-16 GB (leave 4-8 GB for OS)
5. Apply & Restart

**Step 4: Install Synaqmaker**
```cmd
cd C:\synaqmaker
1_INSTALL.bat
```

Wait for Docker images to build (10-20 minutes first time).

### Linux Server Setup (Ubuntu 22.04)

**Step 1: Update System**
```bash
sudo apt update && sudo apt upgrade -y
```

**Step 2: Install Python**
```bash
sudo apt install python3 python3-pip python3-venv -y
python3 --version  # Should be 3.9+
```

**Step 3: Install Docker**
```bash
# Official Docker installation
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group (no sudo needed)
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
```

**Step 4: Install Synaqmaker**
```bash
cd /opt/synaqmaker
sudo chown $USER:$USER .

# Install Python dependencies
pip3 install -r requirements.txt

# Build Docker images
docker build -f Dockerfile.python -t testirovschik-python .
docker build -f Dockerfile.cpp -t testirovschik-cpp .
docker build -f Dockerfile.csharp -t testirovschik-csharp .

# Start server
python3 run.py
```

## Performance Optimization

### Configuration Tuning

**config.ini settings for 100 participants:**

```ini
[server]
MAX_CHECKS = 25  # Adjust based on CPU cores

# Formula: MAX_CHECKS = (CPU_CORES × 2) to (CPU_CORES × 3)
# Examples:
#   4 cores: MAX_CHECKS = 10-12
#   8 cores: MAX_CHECKS = 20-25
#   16 cores: MAX_CHECKS = 30-40
```

**Too High = Resource Exhaustion**
- Symptoms: Slow responses, timeouts, system hang
- Solution: Reduce MAX_CHECKS by 5

**Too Low = Idle Resources**
- Symptoms: Low CPU usage, slow queue processing
- Solution: Increase MAX_CHECKS by 5

### Database Optimization

**Already Configured (no action needed):**
- WAL mode for concurrent reads
- 64 MB cache size
- Automatic backups every 10 minutes

**Optional: Database Maintenance**
```bash
# Stop server first
sqlite3 testirovschik.db "VACUUM;"
sqlite3 testirovschik.db "REINDEX;"
sqlite3 testirovschik.db "ANALYZE;"
```

Run this weekly or after large contests.

### Docker Optimization

**Prewarm Docker Images:**
```bash
# Before contest, ensure images are cached
docker pull python:3.11-slim
docker pull gcc:latest
```

**Clean Docker Cache:**
```bash
# Remove old containers/images (before contest)
docker system prune -af
```

**Monitor Docker Resources:**
```bash
# During contest
docker stats
```

### Operating System Tuning

**Windows:**
- Disable Windows Updates during contest
- Close unnecessary applications (browsers, games, etc.)
- Disable antivirus real-time scanning for project folder
- Set power plan to "High Performance"

**Linux:**
```bash
# Increase file descriptors (for high connections)
ulimit -n 65536

# Disable swap usage (if enough RAM)
sudo swapoff -a

# Set CPU governor to performance
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

## Contest Preparation

### Two Weeks Before

- [ ] Order/setup hardware if needed
- [ ] Test network infrastructure
- [ ] Install and configure software
- [ ] Run stress test with 100 simulated users
- [ ] Train backup staff on system operation

### One Week Before

- [ ] Prepare all contest problems
- [ ] Write test cases (minimum 10 per problem)
- [ ] Verify time limits are reasonable
- [ ] Create problem statements (PDF)
- [ ] Set up contestant accounts (for closed mode)
- [ ] Configure contest settings (duration, scoring, freeze time)

### One Day Before

- [ ] Full system stress test: `python stress_test_v2.py`
- [ ] Verify all problems work correctly
- [ ] Backup clean database
- [ ] Update server OS and software (optional)
- [ ] Prepare USB flash drive with installation files
- [ ] Print problem statements for all participants
- [ ] Test participant machines connectivity

### Contest Day Morning (3 hours before)

- [ ] Boot server fresh (restart)
- [ ] Start Docker Desktop
- [ ] Clean Docker: `docker system prune -f`
- [ ] Start server: `2_START.bat` or `python run.py`
- [ ] Verify server IP and note it down
- [ ] Create contest with correct settings
- [ ] Test submit from participant machine
- [ ] Open backup laptop nearby
- [ ] Clear browser cache on all participant machines

### During Contest

**Monitor continuously:**
```bash
# Terminal 1: Application logs
tail -f logs/judge.log

# Terminal 2: Docker stats
docker stats

# Terminal 3: System resources
# Windows: Task Manager
# Linux: htop
```

**Watch for:**
- Error messages in logs
- High CPU/RAM usage (>90%)
- Slow scoreboard updates
- Participant complaints

**Emergency Actions:**
- Restart server if frozen (all data persists in database)
- Switch to backup laptop if hardware fails
- Increase MAX_CHECKS if queue grows too long

## Monitoring & Maintenance

### Real-time Monitoring

**Web Dashboard:**
- Open admin panel: `http://SERVER_IP:5000/olympiad/host/<ID>`
- Shows live participant count, submissions, scoreboard

**Logs:**
```bash
# View last 100 lines
tail -n 100 logs/judge.log

# Follow live
tail -f logs/judge.log

# Search for errors
grep ERROR logs/judge.log
```

**Docker Monitoring:**
```bash
# Container list
docker ps

# Resource usage
docker stats --no-stream

# Container logs (if issues)
docker logs <container_id>
```

### Health Checks

**System Health Script (create check.sh):**
```bash
#!/bin/bash
echo "=== System Health Check ==="
echo "Date: $(date)"
echo ""

echo "1. Server Process:"
pgrep -f "python.*run.py" && echo "✅ Running" || echo "❌ NOT RUNNING"

echo ""
echo "2. Docker:"
docker ps --format "table {{.Names}}\t{{.Status}}" | head -n 5

echo ""
echo "3. Disk Space:"
df -h | grep -E "/$|/home"

echo ""
echo "4. Memory:"
free -h

echo ""
echo "5. Database:"
ls -lh testirovschik.db
```

Run every 30 minutes during contest.

### Maintenance Schedule

**Daily (if running multiple contests):**
- Check log file size
- Verify backups are created
- Test system accessibility

**Weekly:**
- Review error logs
- Clean old Docker images
- Database vacuum/optimize
- Update Docker images

**Monthly:**
- Update Python packages: `pip install -r requirements.txt --upgrade`
- Review and archive old contest data
- Test disaster recovery procedure

## Disaster Recovery

### Backup Strategy

**Automatic Backups:**
- Database backed up every 10 minutes to `backups/`
- Last 5 backups retained automatically
- No action required

**Manual Backup Before Contest:**
```bash
# Create snapshot
cp testirovschik.db testirovschik_contest_2024.db
cp -r backups backups_contest_2024
```

### Recovery Procedures

**Scenario 1: Server Crash During Contest**

1. **Restart server immediately:**
   ```bash
   python run.py
   ```

2. **System auto-recovers:**
   - Loads contest state from database
   - Participants reconnect automatically
   - Scoreboard restores from last save

3. **Verify recovery:**
   - Check scoreboard shows all participants
   - Test submission from participant machine
   - Announce to participants: "Please refresh page"

**Scenario 2: Database Corruption**

1. **Stop server:**
   ```bash
   # Ctrl+C or close window
   ```

2. **Restore from backup:**
   ```bash
   # Find latest backup
   ls -lt backups/
   
   # Copy to main database
   cp backups/testirovschik_YYYYMMDD_HHMMSS.db testirovschik.db
   ```

3. **Restart server:**
   ```bash
   python run.py
   ```

4. **Data loss:** Maximum 10 minutes (backup interval)

**Scenario 3: Network Failure**

1. **Verify server is accessible:**
   ```bash
   ping SERVER_IP
   ```

2. **If unreachable:**
   - Check network cable
   - Restart switch/router
   - Verify firewall settings
   - Use backup network if available

3. **Participants can continue:**
   - Code is saved locally in browser
   - Reconnect when network restored

**Scenario 4: Docker Failure**

1. **Restart Docker:**
   - Windows: Restart Docker Desktop
   - Linux: `sudo systemctl restart docker`

2. **Rebuild images if needed:**
   ```bash
   docker build -f Dockerfile.python -t testirovschik-python .
   ```

3. **Clear stuck containers:**
   ```bash
   docker ps -a | grep testirovschik
   docker rm -f $(docker ps -aq)
   ```

### Backup Hardware

**Recommended Backup:**
- Second laptop with same setup
- Keep updated with same software
- Copy database before contest
- Keep offline during main contest
- Switch if primary fails (5 minute switch time)

**Quick Switch Procedure:**
1. Copy `testirovschik.db` to backup laptop
2. Start server on backup
3. Announce new IP to participants
4. Participants reconnect and continue

### Communication Plan

**Before Contest:**
- Give participants emergency contact (phone/messenger)
- Prepare pre-written announcements for common issues
- Have PA system or projection for announcements

**During Issues:**
- Announce problem immediately
- Give estimated fix time
- Update every 5 minutes
- Consider extending contest if downtime > 15 minutes

## Performance Benchmarks

### Expected Performance

**100 Participants, 10 Problems:**
- Simultaneous submissions: 25 (limited by MAX_CHECKS)
- Queue wait time: 5-30 seconds (depends on code complexity)
- Scoreboard update: < 1 second
- Database queries: < 100ms
- WebSocket latency: < 50ms

### Stress Test Validation

**Before contest, run:**
```bash
python stress_test_v2.py
```

**Success criteria:**
- ✅ All 500 submissions processed
- ✅ 0 errors
- ✅ Average time < 10 seconds per submission
- ✅ Server responsive during test

**If failing:**
- Reduce MAX_CHECKS
- Upgrade hardware
- Close other applications
- Check network bandwidth

## Security Considerations

### Network Security
- Disable WiFi on server (use wired only)
- Isolate contest network from internet (optional)
- Monitor for unauthorized access
- Use strong admin password

### Code Execution Security
- Docker isolation prevents:
  - Network access from submissions
  - File system access
  - Fork bombs (process limit: 64)
  - Memory bombs (limit: 256 MB)
  - Infinite loops (time limit enforced)

### Contest Integrity
- Monitor for code similarity (manual)
- Log all submissions with timestamps
- Disqualify function available in admin panel
- All actions logged for review

## Troubleshooting Guide

### Common Issues

**Issue: "Database is locked"**
- **Cause:** Concurrent write contention
- **Solution:** Already handled with WAL mode
- **If persistent:** Reduce MAX_CHECKS, check disk speed

**Issue: Slow submission processing**
- **Cause:** Too many concurrent checks
- **Solution:** Reduce MAX_CHECKS in config.ini
- **Prevention:** Follow CPU core recommendations

**Issue: WebSocket disconnections**
- **Cause:** Network instability or proxy
- **Solution:** Use direct LAN connection, disable proxies
- **Check:** Browser console for errors

**Issue: Container timeout**
- **Cause:** Infinite loop in submission or too-strict time limit
- **Solution:** Time limits enforced, will terminate automatically
- **Note:** User gets "Time Limit Exceeded" verdict

**Issue: High memory usage**
- **Cause:** Many active containers
- **Solution:** Normal for contests, ensure 16+ GB RAM
- **Monitor:** `docker stats`, should not exceed 80%

### Support Contacts

During contest, have these contacts ready:
- Network administrator (for network issues)
- Hardware technician (for hardware failures)
- Docker/system administrator (for technical issues)
- Contest director (for rule decisions)

---

## Summary Checklist

**Server Ready When:**
- [x] Hardware meets specifications
- [x] Network configured and tested
- [x] Software installed and updated
- [x] Configuration optimized for participant count
- [x] All problems tested and working
- [x] Stress test passed successfully
- [x] Backups configured and verified
- [x] Monitoring tools ready
- [x] Recovery procedures tested
- [x] Team briefed on operations

**You are ready for a successful contest! 🎯**
