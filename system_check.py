#!/usr/bin/env python3
"""
System Health Monitor for Synaqmaker Local Judge
Checks system readiness for ICPC/IOI contests
"""

import os
import sys
import platform
import subprocess
import sqlite3
import psutil
from datetime import datetime

def print_header(text):
    """Print formatted section header"""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")

def check_python():
    """Check Python version"""
    version = sys.version_info
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print("  ⚠️ WARNING: Python 3.9+ recommended")
        return False
    return True

def check_docker():
    """Check Docker availability and status"""
    try:
        result = subprocess.run(['docker', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✓ Docker installed: {version}")
            
            # Check if Docker is running
            result = subprocess.run(['docker', 'ps'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print("✓ Docker is running")
                return True
            else:
                print("❌ Docker is not running - please start Docker Desktop")
                return False
        else:
            print("❌ Docker not found")
            return False
    except FileNotFoundError:
        print("❌ Docker not installed")
        return False
    except subprocess.TimeoutExpired:
        print("❌ Docker command timeout - is Docker running?")
        return False
    except Exception as e:
        print(f"❌ Docker check failed: {e}")
        return False

def check_docker_images():
    """Check if required Docker images are built"""
    required_images = [
        'testirovschik-python',
        'testirovschik-cpp',
        'testirovschik-csharp'
    ]
    
    try:
        result = subprocess.run(['docker', 'images', '--format', '{{.Repository}}'],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            images = result.stdout.strip().split('\n')
            missing = []
            for img in required_images:
                if img in images:
                    print(f"✓ Docker image: {img}")
                else:
                    print(f"❌ Missing Docker image: {img}")
                    missing.append(img)
            
            if missing:
                print("\n  To build missing images, run:")
                for img in missing:
                    dockerfile = f"Dockerfile.{img.split('-')[1]}"
                    print(f"    docker build -f {dockerfile} -t {img} .")
                return False
            return True
        else:
            print("❌ Could not list Docker images")
            return False
    except Exception as e:
        print(f"❌ Docker images check failed: {e}")
        return False

def check_system_resources():
    """Check CPU, RAM, and disk space"""
    # CPU
    cpu_count = psutil.cpu_count(logical=True)
    cpu_percent = psutil.cpu_percent(interval=1)
    print(f"✓ CPU: {cpu_count} cores, {cpu_percent}% usage")
    
    if cpu_count < 4:
        print("  ⚠️ WARNING: 4+ cores recommended for contests")
    elif cpu_count < 8:
        print("  ℹ️  NOTE: 8+ cores recommended for 100 participants")
    
    # RAM
    ram = psutil.virtual_memory()
    ram_gb = ram.total / (1024**3)
    ram_available_gb = ram.available / (1024**3)
    print(f"✓ RAM: {ram_gb:.1f} GB total, {ram_available_gb:.1f} GB available ({ram.percent}% used)")
    
    if ram_gb < 8:
        print("  ⚠️ WARNING: 8+ GB RAM recommended")
    elif ram_gb < 16:
        print("  ℹ️  NOTE: 16+ GB RAM recommended for 100 participants")
    
    if ram.percent > 80:
        print("  ⚠️ WARNING: High RAM usage - close unnecessary applications")
    
    # Disk
    disk = psutil.disk_usage('.')
    disk_free_gb = disk.free / (1024**3)
    print(f"✓ Disk: {disk_free_gb:.1f} GB free ({disk.percent}% used)")
    
    if disk_free_gb < 10:
        print("  ⚠️ WARNING: Low disk space - 10+ GB free recommended")

def check_database():
    """Check database status"""
    db_path = 'testirovschik.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        print("  Database will be created on first run")
        return False
    
    db_size_mb = os.path.getsize(db_path) / (1024**2)
    print(f"✓ Database exists: {db_size_mb:.2f} MB")
    
    # Check WAL mode
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        conn.close()
        
        if mode.upper() == 'WAL':
            print(f"✓ Database mode: {mode} (optimized for concurrency)")
        else:
            print(f"⚠️ Database mode: {mode} (WAL recommended)")
            
        return True
    except Exception as e:
        print(f"❌ Database check failed: {e}")
        return False

def check_network():
    """Check network configuration"""
    import socket
    
    hostname = socket.gethostname()
    try:
        # Get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        print(f"✓ Hostname: {hostname}")
        print(f"✓ Local IP: {local_ip}")
        print(f"  Participants should access: http://{local_ip}:5000")
        return True
    except Exception as e:
        print(f"⚠️ Could not determine local IP: {e}")
        print("  Check network connection")
        return False

def check_ports():
    """Check if required ports are available"""
    import socket
    
    port = 5000
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', port))
    sock.close()
    
    if result == 0:
        print(f"ℹ️  Port {port} is in use (server may be running)")
        return True
    else:
        print(f"✓ Port {port} is available")
        return True

def check_dependencies():
    """Check Python dependencies"""
    required = [
        'flask',
        'flask_socketio',
        'gevent',
        'pandas',
        'openpyxl',
        'psutil'
    ]
    
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
            print(f"✓ {pkg}")
        except ImportError:
            print(f"❌ Missing: {pkg}")
            missing.append(pkg)
    
    if missing:
        print("\n  To install missing packages:")
        print(f"    pip install {' '.join(missing)}")
        return False
    return True

def check_backups():
    """Check backup configuration"""
    backup_dir = 'backups'
    
    if not os.path.exists(backup_dir):
        print(f"⚠️ Backup directory not found: {backup_dir}")
        print("  Will be created automatically on first run")
        return False
    
    backups = [f for f in os.listdir(backup_dir) if f.endswith('.db')]
    if backups:
        latest = max(backups, key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))
        latest_path = os.path.join(backup_dir, latest)
        latest_time = datetime.fromtimestamp(os.path.getmtime(latest_path))
        print(f"✓ Backups directory exists: {len(backups)} backup(s)")
        print(f"  Latest: {latest} ({latest_time.strftime('%Y-%m-%d %H:%M:%S')})")
    else:
        print(f"ℹ️  Backup directory exists but empty")
        print("  Backups are created automatically during server operation")
    
    return True

def check_logs():
    """Check logs directory"""
    log_dir = 'logs'
    
    if not os.path.exists(log_dir):
        print(f"ℹ️  Logs directory not found: {log_dir}")
        print("  Will be created automatically on first run")
        return True
    
    log_file = os.path.join(log_dir, 'judge.log')
    if os.path.exists(log_file):
        log_size_mb = os.path.getsize(log_file) / (1024**2)
        print(f"✓ Log file exists: {log_size_mb:.2f} MB")
        
        if log_size_mb > 100:
            print("  ⚠️ WARNING: Large log file - consider archiving")
    else:
        print(f"ℹ️  Log file will be created on first run")
    
    return True

def check_config():
    """Check config.ini"""
    config_file = 'config.ini'
    
    if not os.path.exists(config_file):
        print(f"⚠️ Config file not found: {config_file}")
        print("  Will be created with defaults on first run")
        return False
    
    print(f"✓ Config file exists")
    
    # Read config
    import configparser
    config = configparser.ConfigParser()
    try:
        config.read(config_file, encoding='utf-8')
        
        # Check MAX_CHECKS
        if config.has_section('server') and config.has_option('server', 'MAX_CHECKS'):
            max_checks = config.getint('server', 'MAX_CHECKS')
            print(f"  MAX_CHECKS: {max_checks}")
            
            cpu_count = psutil.cpu_count(logical=True)
            recommended_min = cpu_count * 2
            recommended_max = cpu_count * 3
            
            if max_checks < recommended_min:
                print(f"  ℹ️  NOTE: Consider increasing to {recommended_min}-{recommended_max} for {cpu_count} cores")
            elif max_checks > recommended_max:
                print(f"  ⚠️ WARNING: High value may cause resource exhaustion")
            else:
                print(f"  ✓ Good value for {cpu_count} cores")
        
        # Check admin password
        if config.has_section('security') and config.has_option('security', 'ADMIN_PASSWORD'):
            pwd = config.get('security', 'ADMIN_PASSWORD')
            if pwd in ['admin', 'commandblock2025', 'password', '12345']:
                print("  ⚠️ WARNING: Using default/weak admin password!")
                print("    Run: python SUPERSECRET_PASSWORD_GENERATOR.py")
            else:
                print("  ✓ Custom admin password set")
        
        return True
    except Exception as e:
        print(f"❌ Error reading config: {e}")
        return False

def performance_recommendations():
    """Provide performance recommendations"""
    print_header("Performance Recommendations")
    
    cpu_count = psutil.cpu_count(logical=True)
    ram_gb = psutil.virtual_memory().total / (1024**3)
    
    print("Based on your system:")
    print(f"  CPU: {cpu_count} cores")
    print(f"  RAM: {ram_gb:.1f} GB")
    print()
    
    if cpu_count >= 8 and ram_gb >= 16:
        print("✓ System is ready for 100+ participant contests!")
        print(f"  Recommended MAX_CHECKS: {cpu_count * 2}-{cpu_count * 3}")
    elif cpu_count >= 4 and ram_gb >= 8:
        print("✓ System is suitable for 30-50 participant contests")
        print(f"  Recommended MAX_CHECKS: {cpu_count * 2}")
        print("  Consider upgrading for larger contests")
    else:
        print("⚠️ System may struggle with large contests")
        print("  Suitable for: Development and testing")
        print("  Recommended MAX_CHECKS: 10-12")
        print("  Consider hardware upgrade for production contests")
    
    print()
    print("Contest preparation checklist:")
    print("  [ ] Run stress test: python stress_test_v2.py")
    print("  [ ] Clean Docker: docker system prune -f")
    print("  [ ] Close unnecessary applications")
    print("  [ ] Disable Windows updates (if applicable)")
    print("  [ ] Test participant network access")
    print("  [ ] Backup database before contest")

def main():
    """Main health check routine"""
    print_header(f"Synaqmaker Local Judge - System Health Check")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Platform: {platform.system()} {platform.release()}")
    
    all_checks_passed = True
    
    # Core checks
    print_header("Core Software")
    all_checks_passed &= check_python()
    all_checks_passed &= check_docker()
    all_checks_passed &= check_docker_images()
    
    print_header("Python Dependencies")
    all_checks_passed &= check_dependencies()
    
    print_header("System Resources")
    check_system_resources()
    
    print_header("Configuration")
    all_checks_passed &= check_config()
    
    print_header("Database")
    check_database()
    
    print_header("Network")
    check_network()
    check_ports()
    
    print_header("Maintenance")
    check_backups()
    check_logs()
    
    # Recommendations
    performance_recommendations()
    
    # Summary
    print_header("Summary")
    if all_checks_passed:
        print("✅ System is ready for contests!")
        print("\nTo start server: python run.py")
    else:
        print("⚠️ Some issues detected - please review warnings above")
        print("\nResolve issues before running contests")
    
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCheck interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
