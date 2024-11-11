import os
import subprocess
import json


def get_github_username():
    try:
        username = (
            subprocess.check_output(["git", "config", "user.name"]).decode().strip()
        )
        if not username:
            username = os.getenv("GITHUB_USERNAME", "default-username")
        return username
    except Exception:
        return "default-username"


# Fetch the author directly from cookiecutter context
author = "{{cookiecutter.author}}"
if author == "unknown":
    # If the user didn't enter an author, use GitHub username as fallback
    author = get_github_username()

# Path to the generated metadata.json
metadata_json_path = "metadata.json"

# Update the author field in metadata.json
if os.path.exists(metadata_json_path):
    with open(metadata_json_path, "r") as file:
        data = json.load(file)

    # Update the 'author' field with the GitHub username
    data["author"] = author

    with open(metadata_json_path, "w") as file:
        json.dump(data, file, indent=4)
