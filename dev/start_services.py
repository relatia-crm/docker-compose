#!/usr/bin/env python3
import subprocess
import time
import sys
import os
from pathlib import Path

def run_command(command, cwd=None, shell=False):
    """Run a shell command and return True if successful"""
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            shell=shell
        )
        print(f"✅ Success: {' '.join(command) if isinstance(command, list) else command}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running {' '.join(command) if isinstance(command, list) else command}:")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False

def check_http_health(port, path="/actuator/health/readiness"):
    """Check if a service is healthy via HTTP"""
    import http.client
    try:
        conn = http.client.HTTPConnection("localhost", port, timeout=5)
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status == 200 and b"UP" in response.read()
    except Exception as e:
        print(f"Health check failed: {str(e)}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def wait_for_service(name, port, max_retries=30, delay=2):
    """Wait for a service to become available"""
    print(f"⏳ Waiting for {name} to be ready...")
    for i in range(max_retries):
        if check_http_health(port):
            print(f"✅ {name} is ready!")
            return True
        time.sleep(delay)
        print(f"⏳ Still waiting for {name}... ({i+1}/{max_retries})")
    print(f"❌ Timed out waiting for {name}")
    return False

def start_spring_boot_service(service_name, port, service_path):
    """Start a Spring Boot service using Maven and wait for it to be ready"""
    print(f"🚀 Starting {service_name}...")

    # Build the service first
    build_cmd = ["./mvnw", "clean", "package", "-DskipTests"]
    if not run_command(build_cmd, cwd=service_path):
        print(f"❌ Failed to build {service_name}")
        return False

    # Start the service in a new terminal window
    if sys.platform == "win32":
        cmd = f'start cmd /k "cd /D {service_path} && ./mvnw spring-boot:run"'
    else:  # Linux (Fedora)
        cmd = f'ptyxis --new-window  -- bash -c "cd {service_path} && ./mvnw spring-boot:run; exec bash"'
    if not run_command(cmd, shell=True):
        print(f"❌ Failed to start {service_name}")
        return False

    # Give it some time to start
    time.sleep(5)

    # Wait for the service to be ready
    return wait_for_service(service_name, port)

def main():
    print("🚀 Starting CRM Microservices Locally...\n")

    # Get the root directory of the project (where the microservices are located)
    root_dir = Path("/run/media/gokult/common/repos/crm")

    # Define services in the order they should be started
    services = [
        {
            "name": "config-server",
            "port": 8071,
            "path": os.path.join(root_dir, "config-server"),
            "depends_on": []
        },
        {
            "name": "eureka-server",
            "port": 8070,
            "path": os.path.join(root_dir, "eureka-server"),
            "depends_on": ["config-server"]
        },
        {
            "name": "customer-service",
            "port": 8080,
            "path": os.path.join(root_dir, "customer-service"),
            "depends_on": ["eureka-server"]
        },
        {
            "name": "notification-service",
            "port": 9000,
            "path": os.path.join(root_dir, "notification-service"),
            "depends_on": ["eureka-server"]
        },
        {
            "name": "gateway-server",
            "port": 8072,
            "path": os.path.join(root_dir, "gateway-server"),
            "depends_on": ["customer-service", "notification-service"]
        }
    ]

    # First, ensure infrastructure services are running via Docker
    print("🔄 Starting infrastructure services via Docker...")
    docker_compose_path = os.path.join(os.path.dirname(__file__), "docker-compose.yaml")
    if not run_command(["docker-compose", "-f", docker_compose_path, "up", "-d", "redis", "rabbit", "customerdb"]):
        print("❌ Failed to start infrastructure services")
        return False

    # Wait for infrastructure services to be ready
    print("\n⏳ Waiting for infrastructure services to be ready...")
    time.sleep(10)  # Give some time for infrastructure to initialize

    # Start Spring Boot services in order
    started_services = set()

    while len(started_services) < len(services):
        for service in services:
            service_name = service["name"]

            # Skip if already started
            if service_name in started_services:
                continue

            # Check if all dependencies are started
            if not all(dep in started_services for dep in service["depends_on"]):
                continue

            # Start the service
            if not start_spring_boot_service(
                service_name=service_name,
                port=service["port"],
                service_path=service["path"]
            ):
                print(f"❌ Failed to start {service_name}")
                return False

            started_services.add(service_name)
            break
        else:
            print("❌ Circular dependency detected or unable to start services")
            return False

    print("\n🎉 All services started successfully!")
    print("\nServices running on:")
    for service in services:
        print(f"- {service['name']}: http://localhost:{service['port']}")

    print("\nTo stop all services, press Ctrl+C in each terminal window.")
    return True

if __name__ == "__main__":
    try:
        if not main():
            print("\n❌ Failed to start all services. Check the logs above for details.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Script interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ An error occurred: {str(e)}")
        sys.exit(1)
