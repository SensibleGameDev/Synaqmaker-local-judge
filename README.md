# Synaqmaker Local Judge

**Professional contest judging system for ICPC, IOI, and local programming competitions**

A robust, Docker-based automated judging system designed to handle competitive programming contests for up to 100 participants with 10 problems simultaneously in a local network environment.

## 🎯 Features

- **Contest-Ready**: Optimized for ICPC and IOI style competitions
- **High Performance**: Handles 100+ concurrent participants
- **Multi-Language Support**: Python, C++, C#
- **Real-time Scoreboard**: Live updates with WebSocket support
- **ICPC Freeze Mode**: Scoreboard freezing for dramatic reveals
- **Secure Execution**: Docker-isolated code execution
- **Flexible Scoring**: ICPC, IOI (partial points), and all-or-nothing modes
- **Easy Setup**: Automated installation scripts for Windows

## 📋 System Requirements

### Minimum Requirements (Small Contests, <30 participants)
- **CPU**: 4 cores / 8 threads
- **RAM**: 8 GB
- **Storage**: 20 GB free space
- **OS**: Windows 10/11, Linux (Ubuntu 20.04+)
- **Network**: 100 Mbps LAN

### Recommended for ICPC/IOI (100 participants)
- **CPU**: 8 cores / 16 threads or better (Intel i7/i9, AMD Ryzen 7/9)
- **RAM**: 16 GB or more
- **Storage**: 50 GB SSD
- **OS**: Windows 10/11 Pro, Ubuntu Server 22.04
- **Network**: Gigabit LAN (1 Gbps)

### Software Requirements
- Python 3.9 or higher
- Docker Desktop (Windows) / Docker Engine (Linux)
- Modern web browser (Chrome, Firefox, Edge)

## 🚀 Quick Start

### Windows Installation

1. **Install Prerequisites**
   - Download and install [Python 3.9+](https://www.python.org/downloads/) (check "Add to PATH")
   - Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   - Start Docker Desktop

2. **Run Installation**
   ```cmd
   1_INSTALL.bat
   ```
   This will:
   - Install Python dependencies
   - Build Docker images for Python, C++, and C#
   - Set up the database

3. **Start Server**
   ```cmd
   2_START.bat
   ```

4. **Access System**
   - Admin Panel: `http://localhost:5000` or `http://YOUR_IP:5000`
   - Default password is shown in console (change it immediately!)

### Linux Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Build Docker images
docker build -f Dockerfile.python -t testirovschik-python .
docker build -f Dockerfile.cpp -t testirovschik-cpp .
docker build -f Dockerfile.csharp -t testirovschik-csharp .

# Start server
python run.py
```

## 📚 Usage Guide

### Setting Up a Contest

1. **Login as Admin**
   - Navigate to `http://YOUR_IP:5000/login`
   - Use password from `config.ini` or console output

2. **Create Problems**
   - Go to "Задачи" (Tasks)
   - Add problems with test cases
   - Configure time limits and checkers

3. **Create Contest**
   - Click "Создать олимпиаду" (Create Contest)
   - Select 1-10 problems
   - Configure:
     - Duration (minutes)
     - Scoring mode (ICPC/IOI/All-or-Nothing)
     - Language restrictions
     - Freeze time (for ICPC-style reveals)
     - Start time (immediate or scheduled)
   - Choose mode:
     - **Free**: Anyone can join with any nickname
     - **Closed**: Pre-registered participants only

4. **Share Contest Code**
   - Share the 8-character contest ID with participants
   - Participants join at: `http://YOUR_IP:5000/olympiad/join`

5. **Monitor Contest**
   - Real-time scoreboard updates
   - View participant submissions
   - Disqualify rule violators if needed
   - Download results as Excel

### For Participants

1. Navigate to `http://CONTEST_IP:5000/olympiad/join`
2. Enter contest ID and nickname
3. Wait in lobby until organizer starts contest
4. Submit solutions and track progress on live scoreboard

## ⚙️ Configuration

### Performance Tuning

Edit `config.ini`:

```ini
[server]
MAX_CHECKS = 25  # Concurrent Docker containers
```

**Recommendations by CPU:**
- 4 cores: MAX_CHECKS = 10-15
- 8 cores: MAX_CHECKS = 20-25
- 16+ cores: MAX_CHECKS = 30-40

### Security

**IMPORTANT**: Change default admin password!

Use the password generator:
```bash
python SUPERSECRET_PASSWORD_GENERATOR.py
```

Then update `config.ini` with the new hashed password.

### Network Setup

For local network contests:

1. **Find Server IP**
   - Windows: `ipconfig` (look for IPv4 Address)
   - Linux: `ip addr` or `hostname -I`

2. **Firewall Configuration**
   - Allow port 5000 (or your configured port)
   - Windows: Windows Defender Firewall → Allow an app
   - Linux: `sudo ufw allow 5000`

3. **Share Access URL**
   - Give participants: `http://SERVER_IP:5000`

## 🔍 System Monitoring

### Check System Health

```bash
# View active containers
docker ps

# Monitor logs
tail -f logs/judge.log

# Database backups (automatic every 10 minutes)
ls backups/
```

### Performance Metrics

The stress test tools help verify system readiness:

```bash
# Basic stress test (20 concurrent users)
python stress_test.py

# Full contest simulation (100 participants)
python stress_test_v2.py
```

**Success Criteria:**
- All submissions processed without errors
- Response time < 10 seconds per submission
- No database locks or timeouts

## 🏆 Contest Day Checklist

**Before Contest (1 day):**
- [ ] Update system: `git pull`
- [ ] Rebuild Docker images
- [ ] Run stress test: `python stress_test_v2.py`
- [ ] Check disk space: at least 10 GB free
- [ ] Verify network speed: 100+ Mbps
- [ ] Change default admin password
- [ ] Prepare contest problems with test cases
- [ ] Test all problems manually

**Contest Day (1 hour before):**
- [ ] Restart server machine
- [ ] Start Docker Desktop
- [ ] Clean old containers: `docker system prune -f`
- [ ] Start server: `2_START.bat` or `python run.py`
- [ ] Create contest with correct settings
- [ ] Test participant access from different machines
- [ ] Prepare backup laptop (recommended)

**During Contest:**
- [ ] Monitor logs: `tail -f logs/judge.log`
- [ ] Watch Docker CPU/RAM usage
- [ ] Keep database backups folder open
- [ ] Have contact with network admin

**After Contest:**
- [ ] Stop accepting submissions
- [ ] Download results (Excel)
- [ ] Backup database: copy `testirovschik.db`
- [ ] Optionally: use ICPC Reveal mode for dramatic finish

## 🐛 Troubleshooting

### Docker Issues

**"Docker not found" error:**
- Ensure Docker Desktop is running
- Windows: Check system tray for Docker icon
- Linux: `sudo systemctl start docker`

**"Port 5000 already in use":**
- Change PORT in `config.ini`
- Or stop conflicting application

**Slow container execution:**
- Reduce MAX_CHECKS in config.ini
- Check Docker resource limits in Docker Desktop settings
- Close unnecessary applications

### Database Issues

**"Database locked" errors:**
- Automatic with WAL mode, but if persistent:
- Stop server
- Run: `sqlite3 testirovschik.db "PRAGMA optimize;"`
- Restart server

**Lost data after crash:**
- Restore from `backups/` folder
- Copy latest backup to `testirovschik.db`

### Network Issues

**Participants can't connect:**
- Verify server IP: `ipconfig` / `ip addr`
- Check firewall allows port 5000
- Ensure same network/subnet
- Try accessing from server itself: `http://localhost:5000`

**Scoreboard not updating:**
- Check browser console for WebSocket errors
- Verify no proxy/VPN interfering
- Refresh page (Ctrl+F5)

## 📊 Scoring Modes

### ICPC Mode
- Binary scoring: 1 point per solved problem
- Penalty: time to solve + 20 minutes per wrong attempt
- Frozen scoreboard in final hour (configurable)

### IOI Mode (Points)
- Partial credit based on test cases passed
- Best submission counts
- No time penalties

### All-or-Nothing
- 100 points if all tests pass
- 0 points otherwise
- Simple mode for practice/exams

## 🔒 Security Features

- Isolated Docker execution (no network, limited resources)
- Non-root container users
- Memory and CPU limits per submission
- File size restrictions
- Process limit protection
- No direct filesystem access

## 📦 Project Structure

```
Synaqmaker-local-judge/
├── app.py                 # Main Flask application
├── db_manager.py          # Database operations
├── run.py                 # Server startup with monitoring
├── config.ini             # Configuration file
├── requirements.txt       # Python dependencies
├── judge_scripts/         # Language-specific judges
│   ├── py_runner.py
│   ├── cpp_runner.py
│   └── cs_runner.py
├── templates/             # Web interface HTML
├── static/                # CSS, JS, fonts
├── Dockerfile.*           # Docker images for languages
└── logs/                  # Application logs
```

## 🤝 Contributing

Contributions welcome! Please:
1. Test changes with stress tests
2. Document new features
3. Maintain backward compatibility
4. Follow existing code style

## 📄 License

See LICENSE file for details.

## 🆘 Support

For issues during contests:
1. Check logs: `logs/judge.log`
2. Try restarting server
3. Check GitHub issues
4. Have backup system ready

## 🎓 Best Practices

### For Contest Organizers
- Always test system 1 day before contest
- Have backup hardware ready
- Keep contestant machines on same network switch
- Prepare printed problem statements (in case of network issues)
- Brief participants on system usage before contest

### For System Performance
- Close unnecessary applications during contest
- Use SSD for database storage
- Ensure good cooling for server CPU
- Monitor Docker resource usage
- Keep MAX_CHECKS reasonable for your CPU

### For Fair Competition
- Test all problems before contest
- Verify time limits are reasonable
- Use strong test cases
- Have clear rules about allowed languages/libraries
- Monitor for suspicious activity

---

**Ready for ICPC/IOI competitions! Good luck! 🏆**
