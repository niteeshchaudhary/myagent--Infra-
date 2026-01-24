#!/usr/bin/env python3
"""Setup script for DevOps Monitoring Agent"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
import platform

def run_command(command, check=True, shell=False):
    """Run a command and return the result"""
    try:
        result = subprocess.run(
            command if shell else command.split(),
            capture_output=True,
            text=True,
            check=check,
            shell=shell
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr
    except FileNotFoundError:
        return False, "", f"Command not found: {command.split()[0] if not shell else command}"

def check_python_version():
    """Check Python version compatibility"""
    print("🐍 Checking Python version...")
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        return False
    print(f"✅ Python {sys.version.split()[0]} is compatible")
    return True

def check_system_requirements():
    """Check system requirements and CLI tools"""
    print("\\n🔍 Checking system requirements...")
    
    requirements = []
    
    # Check for essential tools
    tools = [
        ("pip", "pip --version"),
        ("git", "git --version")
    ]
    
    # Optional CLI tools
    optional_tools = [
        ("kubectl", "kubectl version --client", "Kubernetes management"),
        ("docker", "docker --version", "Container management"),
        ("aws", "aws --version", "AWS management"),
        ("gcloud", "gcloud version", "Google Cloud management"),
        ("az", "az --version", "Azure management")
    ]
    
    # Check essential tools
    for tool, command in tools:
        success, stdout, stderr = run_command(command)
        if success:
            print(f"✅ {tool} is available")
        else:
            print(f"❌ {tool} is not available")
            requirements.append(tool)
    
    # Check optional tools
    print("\\n🔧 Checking optional CLI tools:")
    for tool, command, description in optional_tools:
        success, stdout, stderr = run_command(command)
        if success:
            print(f"✅ {tool} is available - {description}")
        else:
            print(f"⚠️  {tool} is not available - {description} (optional)")
    
    if requirements:
        print(f"\\n❌ Missing required tools: {', '.join(requirements)}")
        return False
    
    print("\\n✅ All required tools are available")
    return True

def create_virtual_environment():
    """Create Python virtual environment"""
    print("\\n🐍 Setting up Python virtual environment...")
    
    venv_path = Path("venv")
    
    if venv_path.exists():
        print("⚠️  Virtual environment already exists")
        return True
    
    success, stdout, stderr = run_command("python -m venv venv")
    if not success:
        print(f"❌ Failed to create virtual environment: {stderr}")
        return False
    
    print("✅ Virtual environment created")
    return True

def install_dependencies():
    """Install Python dependencies"""
    print("\\n📦 Installing Python dependencies...")
    
    # Determine the correct pip command based on OS and virtual environment
    system = platform.system().lower()
    if system == "windows":
        pip_cmd = "venv\\Scripts\\pip"
    else:
        pip_cmd = "venv/bin/pip"
    
    # Check if we're in virtual environment
    if not Path(pip_cmd).exists():
        pip_cmd = "pip"  # Fallback to system pip
    
    success, stdout, stderr = run_command(f"{pip_cmd} install -r requirements.txt")
    if not success:
        print(f"❌ Failed to install dependencies: {stderr}")
        return False
    
    print("✅ Dependencies installed successfully")
    return True

def setup_configuration():
    """Setup configuration files"""
    print("\\n⚙️  Setting up configuration...")
    
    # Copy .env template if .env doesn't exist
    env_file = Path(".env")
    env_template = Path(".env.template")
    
    if not env_file.exists() and env_template.exists():
        shutil.copy(env_template, env_file)
        print("✅ Created .env file from template")
    elif env_file.exists():
        print("⚠️  .env file already exists")
    else:
        print("❌ .env.template not found")
        return False
    
    # Create required directories
    directories = [
        "data",
        "data/sops", 
        "data/vector_db",
        "logs"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created directory: {directory}")
    
    return True

def initialize_database():
    """Initialize the database"""
    print("\\n💾 Initializing database...")
    
    # Determine the correct python command
    system = platform.system().lower()
    if system == "windows":
        python_cmd = "venv\\Scripts\\python"
    else:
        python_cmd = "venv/bin/python"
    
    if not Path(python_cmd).exists():
        python_cmd = "python"  # Fallback to system python
    
    # Initialize database by importing the database service
    init_script = '''
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

try:
    from app.database.database import db_service
    print("Database initialized successfully")
except Exception as e:
    print(f"Error initializing database: {e}")
    sys.exit(1)
'''
    
    with open("init_db.py", "w") as f:
        f.write(init_script)
    
    success, stdout, stderr = run_command(f"{python_cmd} init_db.py")
    
    # Clean up temporary file
    if Path("init_db.py").exists():
        Path("init_db.py").unlink()
    
    if success:
        print("✅ Database initialized successfully")
        print(stdout)
    else:
        print(f"❌ Failed to initialize database: {stderr}")
        return False
    
    return True

def create_sample_sop():
    """Create a sample SOP document"""
    print("\\n📚 Creating sample SOP document...")
    
    sample_sop = '''# Kubernetes Pod Troubleshooting

## Overview
This SOP provides steps to troubleshoot common Kubernetes pod issues.

## Common Issues and Solutions

### Pod Stuck in Pending State

**Symptoms:**
- Pod status shows "Pending"
- Events show scheduling issues

**Diagnosis:**
```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -n <namespace>
```

**Resolution:**
1. Check node resources: `kubectl describe nodes`
2. Check PVC availability: `kubectl get pvc -n <namespace>`
3. Verify node selectors and taints
4. Scale cluster if resources are insufficient

### Pod in CrashLoopBackOff

**Symptoms:**
- Pod restarts frequently
- Status shows "CrashLoopBackOff"

**Diagnosis:**
```bash
kubectl logs <pod-name> -n <namespace> --previous
kubectl describe pod <pod-name> -n <namespace>
```

**Resolution:**
1. Check application logs for errors
2. Verify resource limits and requests
3. Check liveness and readiness probes
4. Verify environment variables and secrets

### Image Pull Errors

**Symptoms:**
- Pod stuck in "ImagePullBackOff" or "ErrImagePull"

**Diagnosis:**
```bash
kubectl describe pod <pod-name> -n <namespace>
```

**Resolution:**
1. Verify image name and tag
2. Check registry credentials
3. Ensure image exists in registry
4. Check network connectivity to registry

## Escalation
If issues persist after following these steps, escalate to the DevOps team with:
- Pod description output
- Application logs
- Node status information
'''
    
    sop_file = Path("data/sops/kubernetes-pod-troubleshooting.md")
    sop_file.write_text(sample_sop)
    print("✅ Created sample SOP document")
    
    return True

def print_next_steps():
    """Print next steps for the user"""
    print("\\n" + "="*60)
    print("🎉 Setup completed successfully!")
    print("="*60)
    print("\\n📋 Next steps:")
    print("\\n1. Configure your environment:")
    print("   - Edit .env file with your specific configuration")
    print("   - Add your cloud provider credentials")
    print("   - Configure LLM providers (OpenAI, Groq, or Ollama)")
    
    print("\\n2. Start the application:")
    
    # Determine the correct commands based on OS
    system = platform.system().lower()
    if system == "windows":
        print("   - Activate virtual environment: venv\\Scripts\\activate")
        print("   - Start main agent: venv\\Scripts\\python main.py")
        print("   - Start UI (in another terminal): venv\\Scripts\\streamlit run app/ui/main.py")
    else:
        print("   - Activate virtual environment: source venv/bin/activate")
        print("   - Start main agent: python main.py")
        print("   - Start UI (in another terminal): streamlit run app/ui/main.py")
    
    print("\\n3. Access the application:")
    print("   - Web UI: http://localhost:8501")
    print("   - Webhook API: http://localhost:8080")
    print("   - API Health: http://localhost:8080/health")
    
    print("\\n4. Alternative: Use Docker Compose:")
    print("   - docker-compose up -d")
    
    print("\\n📖 For more information, check the README.md file")
    print("="*60)

def main():
    """Main setup function"""
    print("🔧 DevOps Monitoring Agent Setup")
    print("="*40)
    
    steps = [
        ("Checking Python version", check_python_version),
        ("Checking system requirements", check_system_requirements),
        ("Creating virtual environment", create_virtual_environment),
        ("Installing dependencies", install_dependencies),
        ("Setting up configuration", setup_configuration),
        ("Initializing database", initialize_database),
        ("Creating sample SOP", create_sample_sop)
    ]
    
    failed_steps = []
    
    for step_name, step_function in steps:
        try:
            if not step_function():
                failed_steps.append(step_name)
        except Exception as e:
            print(f"❌ Error in {step_name}: {str(e)}")
            failed_steps.append(step_name)
    
    if failed_steps:
        print(f"\\n❌ Setup failed. Failed steps: {', '.join(failed_steps)}")
        print("\\nPlease resolve the issues and run the setup again.")
        sys.exit(1)
    
    print_next_steps()

if __name__ == "__main__":
    main()