import os
import re
import logging
import subprocess
import docker
from docker.errors import ImageNotFound

IMAGE_NAME = "joshxt/safeexecute:latest"


def install_docker_image():
    client = docker.from_env()
    try:
        client.images.get(IMAGE_NAME)
        logging.info(f"Image '{IMAGE_NAME}' found locally")
    except ImageNotFound:
        logging.info(f"Installing docker image '{IMAGE_NAME}' from Docker Hub")
        low_level_client = docker.APIClient()
        for line in low_level_client.pull(IMAGE_NAME, stream=True, decode=True):
            status = line.get("status")
            progress = line.get("progress")
            if status and progress:
                logging.info(f"{status}: {progress}")
            elif status:
                logging.info(status)
        logging.info(f"Image '{IMAGE_NAME}' installed")
    return client


async def execute_python_code(code: str, working_directory: str) -> str:
    # Create working directory if it doesn't exist
    if not os.path.exists(working_directory):
        os.makedirs(working_directory)
    # Check if there are any package requirements in the code to install
    package_requirements = re.findall(r"pip install (.*)", code)
    if package_requirements:
        # Install the required packages
        for package in package_requirements:
            try:
                subprocess.check_output(["pip", "install", package])
            except:
                pass
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0]
    # Create a temporary Python file in the WORKSPACE directory
    temp_file = os.path.join(working_directory, "temp.py")
    with open(temp_file, "w") as f:
        f.write(code)
    try:
        client = install_docker_image()
        container = client.containers.run(
            IMAGE_NAME,
            f"python {temp_file}",
            volumes={
                os.path.abspath(working_directory): {
                    "bind": "/workspace",
                    "mode": "ro",
                }
            },
            working_dir="/workspace",
            stderr=True,
            stdout=True,
            detach=True,
        )
        container.wait()
        logs = container.logs().decode("utf-8")
        container.remove()
        os.remove(temp_file)
        return logs
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    install_docker_image()
