"""Output formatting helpers for consistent CLI output."""

import re


def parse_service_name(container_name: str, app_name: str) -> str:
    """Extract service name from Docker container name.

    Container names look like: {app_name}-{service}-{instance}
    We strip the app_name prefix and trailing instance number.
    """
    name = container_name
    if name.startswith(f"{app_name}-"):
        name = name[len(app_name) + 1 :]
    # Strip trailing -N instance number
    name = re.sub(r"-\d+$", "", name)
    return name


def parse_health(status: str) -> str:
    """Extract health status from Docker status string."""
    if "(healthy)" in status:
        return "healthy"
    if "(unhealthy)" in status:
        return "unhealthy"
    if "(health: starting)" in status.lower():
        return "starting"
    return "\u2014"


def parse_uptime(status: str) -> str:
    """Extract uptime from Docker status string."""
    if status.startswith("Exited"):
        return "\u2014"
    # Match patterns like "Up 2 hours", "Up 30 seconds", "Up 5 minutes"
    m = re.match(r"Up\s+(.+?)(?:\s+\(|$)", status)
    if m:
        raw = m.group(1).strip()
        # Shorten: "2 hours" → "2h", "30 seconds" → "30s", "5 minutes" → "5m"
        raw = re.sub(r"\s*hours?", "h", raw)
        raw = re.sub(r"\s*minutes?", "m", raw)
        raw = re.sub(r"\s*seconds?", "s", raw)
        return raw
    return "\u2014"


def format_container_row(container: dict, app_name: str) -> str:
    """Format a single container as a table row."""
    service = parse_service_name(container.get("name", "?"), app_name)
    state = container.get("state", "?")
    health = parse_health(container.get("status", ""))
    image = container.get("image", "?")
    uptime = parse_uptime(container.get("status", ""))
    cid = container.get("containerId", "?")[:8]
    return f"  {service:<20} {state:<10} {health:<12} {image:<45} {uptime:<8} {cid}"


def format_container_table(containers: list[dict], app_name: str) -> str:
    """Format containers as a table with headers."""
    header = f"  {'SERVICE':<20} {'STATE':<10} {'HEALTH':<12} {'IMAGE':<45} {'UPTIME':<8} CONTAINER ID"
    rows = [format_container_row(c, app_name) for c in containers]
    return "\n".join([header, *rows])
