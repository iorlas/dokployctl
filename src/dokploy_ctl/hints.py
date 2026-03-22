"""Deterministic hints — map error patterns to actionable suggestions."""


def hint_unhealthy(compose_id: str, service: str) -> str:
    return f"Hint: {service} is unhealthy.\n  dokploy-ctl logs {compose_id} --service {service} --since 5m"


def hint_deploy_failed(compose_id: str, service: str, reason: str) -> str:
    return (
        f"Hint: {service} failed ({reason}). Check the Dockerfile entrypoint or config.\n"
        f"  dokploy-ctl logs {compose_id} --service {service} --tail 200\n"
        f"  dokploy-ctl status {compose_id}"
    )


def hint_restart(compose_id: str) -> str:
    return f"Hint: To restart: dokploy-ctl start {compose_id}"


def hint_stopped(compose_id: str) -> str:
    return f"Hint: To start: dokploy-ctl start {compose_id}"


def hint_no_containers(compose_id: str) -> str:
    return f"Hint: No containers found. The app may be stopped.\n  dokploy-ctl start {compose_id}"
