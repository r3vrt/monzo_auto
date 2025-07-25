#!/usr/bin/env python3
"""
Real-time log monitoring script for debugging hangs and API issues.
"""

import time
import subprocess
import sys
from datetime import datetime

def monitor_logs():
    """Monitor logs in real-time with filtering for important events."""
    print("🔍 Starting real-time log monitoring...")
    print("📊 Press Ctrl+C to stop monitoring")
    print("=" * 80)
    
    try:
        # Use tail -f to follow the log file
        process = subprocess.Popen(
            ['tail', '-f', 'monzo_app.log'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        while True:
            line = process.stdout.readline()
            if not line:
                break
                
            # Highlight important events
            if 'timeout' in line.lower() or 'hang' in line.lower():
                print(f"🚨 TIMEOUT/HANG: {line.strip()}")
            elif 'error' in line.lower():
                print(f"❌ ERROR: {line.strip()}")
            elif 'api' in line.lower():
                print(f"🌐 API: {line.strip()}")
            elif 'sync' in line.lower():
                print(f"🔄 SYNC: {line.strip()}")
            elif 'automation' in line.lower():
                print(f"🤖 AUTOMATION: {line.strip()}")
            elif 'debug' in line.lower():
                print(f"🐛 DEBUG: {line.strip()}")
            else:
                print(f"📝 {line.strip()}")
                
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user")
        if process:
            process.terminate()
    except Exception as e:
        print(f"❌ Error monitoring logs: {e}")

def show_recent_errors():
    """Show recent errors from the log file."""
    print("🔍 Recent errors from log file:")
    print("=" * 80)
    
    try:
        result = subprocess.run(
            ['grep', '-i', 'error', 'monzo_app.log'],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            lines = result.stdout.strip().split('\n')
            # Show last 20 error lines
            for line in lines[-20:]:
                print(f"❌ {line}")
        else:
            print("✅ No errors found in recent logs")
            
    except Exception as e:
        print(f"❌ Error reading log file: {e}")

def show_timeout_stats():
    """Show timeout statistics."""
    print("⏱️  Timeout statistics:")
    print("=" * 80)
    
    try:
        result = subprocess.run(
            ['grep', '-c', 'timeout', 'monzo_app.log'],
            capture_output=True,
            text=True
        )
        
        timeout_count = int(result.stdout.strip()) if result.stdout.strip() else 0
        print(f"Total timeouts: {timeout_count}")
        
        # Show recent timeouts
        result = subprocess.run(
            ['grep', 'timeout', 'monzo_app.log'],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            lines = result.stdout.strip().split('\n')
            print("\nRecent timeouts:")
            for line in lines[-10:]:
                print(f"⏱️  {line}")
                
    except Exception as e:
        print(f"❌ Error reading timeout stats: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "errors":
            show_recent_errors()
        elif command == "timeouts":
            show_timeout_stats()
        else:
            print("Usage: python monitor_logs.py [errors|timeouts]")
            print("  errors   - Show recent errors")
            print("  timeouts - Show timeout statistics")
            print("  (no args) - Start real-time monitoring")
    else:
        monitor_logs() 