FROM python:3.13-bookworm

# Install system dependencies required for building some Python packages.
# `build-essential` includes compilers, `libffi-dev` and `libssl-dev` are common for network-related packages.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        # Add any other system dependencies your specific Python packages might need.
    && rm -rf /var/lib/apt/lists/*

# Install uv by copying its binaries from a dedicated uv image.
# This ensures you get a specific, tested version of uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory inside the container.
WORKDIR /app

# Copy your application code and uv project files into the container.
# This assumes your main Python file is in the root of your project context.
COPY . /app

# Ensure that uv can find its binaries by adding them to the PATH.
ENV PATH="/bin:${PATH}"


# ... previous steps ...
ENV PATH="/bin:${PATH}"

# Create the virtual environment explicitly
RUN python -m venv /app/.venv

# Activate the virtual environment and then run uv sync
RUN . /app/.venv/bin/activate && uv sync

# Install Python dependencies using uv sync.
# `uv sync` installs dependencies from pyproject.toml and uv.lock (if present).
# If you have a `uv.lock` file, uv will use it to ensure reproducible builds.
# RUN uv sync

# Cloud Run services listen on the port specified by the PORT environment variable.
# Expose this port so Docker knows your application listens on it.
EXPOSE $PORT

# Command to run your application.
# `uv run` executes a script or a module. If your FastMCP app is in `main.py`, use `main.py`.
CMD ["uv", "run", "mcp_app.py", "--host", "0.0.0.0", "--port", "8080"]
