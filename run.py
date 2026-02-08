#!/usr/bin/env python3
"""Simple run script for DevOps Monitoring Agent"""

import subprocess
import sys
import threading
import time
import platform
from pathlib import Path

def get_python_cmd():
    """Get the appropriate Python command based on OS and virtual environment"""
    system = platform.system().lower()
    
    if system == "windows":
        venv_python = Path("venv/Scripts/python.exe")
        if venv_python.exists():
            return str(venv_python)
    else:
        venv_python = Path("venv/bin/python")
        if venv_python.exists():
            return str(venv_python)
    
    return "python"

def run_main_agent():
    """Run the main monitoring agent"""
    python_cmd = get_python_cmd()
    try:
        subprocess.run([python_cmd, "main.py"], check=True)
    except KeyboardInterrupt:
        print("Main agent stopped by user")
    except Exception as e:
        print(f"Error running main agent: {e}")

def run_streamlit_ui():
    """Run the Streamlit UI"""
    python_cmd = get_python_cmd()
    try:
        # Wait a bit for the main agent to start
        time.sleep(3)
        subprocess.run([
            python_cmd, "-m", "streamlit", "run", 
            "app/ui/main.py", 
            "--server.address", "0.0.0.0",
            "--server.port", "8501"
        ], check=True)
    except KeyboardInterrupt:
        print("Streamlit UI stopped by user")
    except Exception as e:
        print(f"Error running Streamlit UI: {e}")

def main():
    """Main entry point"""
    print("🔧 Starting DevOps Monitoring Agent")
    print("=" * 50)
    
    # Check if main.py exists
    if not Path("main.py").exists():
        print("❌ main.py not found. Please run from the project root directory.")
        sys.exit(1)
    
    # Check if .env file exists
    if not Path(".env").exists():
        print("⚠️  .env file not found. Creating from template...")
        if Path(".env.template").exists():
            import shutil
            shutil.copy(".env.template", ".env")
            print("✅ Created .env file from template. Please configure it and run again.")
        else:
            print("❌ .env.template not found. Please run setup.py first.")
        sys.exit(1)
    
    try:
        print("🚀 Starting main monitoring agent...")
        
        # Start main agent in a separate thread
        main_thread = threading.Thread(target=run_main_agent, daemon=False)
        main_thread.start()
        
        print("🌐 Starting Streamlit UI...")
        print("   UI will be available at: http://localhost:8501")
        print("   Webhook API available at: http://localhost:8088")
        
        # Start Streamlit UI in main thread
        run_streamlit_ui()
        
    except KeyboardInterrupt:
        print("\\n🛑 Stopping DevOps Monitoring Agent...")
        print("Goodbye!")

if __name__ == "__main__":
    main()