#!/usr/bin/env python3

import argparse
import getpass
import json
import os
import pathlib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "https://sandbox-api.summation.com"
CONFIG_FILE_NAME = ".summation-config"
ACTIVE_PROFILE_KEY = "SUM_API_ACTIVE_PROFILE"
PROFILE_ENV_KEYS = ("SUM_API_PROFILE", "SUMMATION_PROFILE")
CONFIG_PATH_ENV_KEYS = ("SUM_API_CONFIG_FILE", "SUMMATION_CONFIG")
PROFILE_SECTION_PREFIX = "profile."
PROFILE_OVERRIDE: str | None = None


def skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def home_config_path() -> pathlib.Path:
    return pathlib.Path.home() / ".summation" / "skill-config"


def legacy_config_paths() -> list[pathlib.Path]:
    return [skill_root() / CONFIG_FILE_NAME, pathlib.Path.home() / CONFIG_FILE_NAME]


def migrate_legacy_config(found: pathlib.Path) -> pathlib.Path:
    canonical = home_config_path()
    if canonical.exists():
        return found
    if found.resolve() not in {path.resolve() for path in legacy_config_paths()}:
        return found
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(found.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(canonical, 0o600)
    print(
        f"Migrated config from {found} to {canonical}; legacy file left in place.",
        file=sys.stderr,
    )
    return canonical


def candidate_config_paths() -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for env_key in CONFIG_PATH_ENV_KEYS:
        explicit = os.getenv(env_key)
        if explicit:
            paths.append(pathlib.Path(explicit).expanduser())
    paths.extend([
        pathlib.Path.cwd() / CONFIG_FILE_NAME,
        home_config_path(),
        skill_root() / CONFIG_FILE_NAME,
        pathlib.Path.home() / CONFIG_FILE_NAME,
    ])
    seen = set()
    unique_paths = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(path)
    return unique_paths


def active_config_path() -> pathlib.Path | None:
    for path in candidate_config_paths():
        if path.exists():
            return migrate_legacy_config(path)
    return None


def parse_config_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export "):].strip()
    if "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def parse_config_section(line: str) -> str | None:
    stripped = line.strip()
    if len(stripped) < 3 or not stripped.startswith("[") or not stripped.endswith("]"):
        return None
    name = stripped[1:-1].strip()
    if name.startswith(PROFILE_SECTION_PREFIX):
        name = name[len(PROFILE_SECTION_PREFIX):]
    return name or None


def empty_config() -> dict[str, Any]:
    return {"values": {}, "profiles": {}}


def read_config_from_path(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return empty_config()
    values: dict[str, str] = {}
    profiles: dict[str, dict[str, str]] = {}
    current_profile: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        section = parse_config_section(line)
        if section:
            current_profile = section
            profiles.setdefault(current_profile, {})
            continue
        parsed = parse_config_line(line)
        if parsed:
            key, value = parsed
            if current_profile:
                profiles.setdefault(current_profile, {})[key] = value
            else:
                values[key] = value
    return {"values": values, "profiles": profiles}


def read_config() -> dict[str, Any]:
    path = active_config_path()
    if not path:
        return empty_config()
    return read_config_from_path(path)


CONFIG = read_config()


def config_values() -> dict[str, str]:
    values = CONFIG.get("values", {})
    return values if isinstance(values, dict) else {}


def config_profiles() -> dict[str, dict[str, str]]:
    profiles = CONFIG.get("profiles", {})
    return profiles if isinstance(profiles, dict) else {}


def profile_name_from(values: dict[str, str], profiles: dict[str, dict[str, str]]) -> str | None:
    if PROFILE_OVERRIDE:
        return PROFILE_OVERRIDE
    for key in PROFILE_ENV_KEYS:
        value = os.getenv(key)
        if value:
            return value
    configured = values.get(ACTIVE_PROFILE_KEY)
    if configured:
        return configured
    if "default" in profiles:
        return "default"
    if len(profiles) == 1:
        return next(iter(profiles))
    return None


def selected_profile_name() -> str | None:
    return profile_name_from(config_values(), config_profiles())


def selected_profile_values() -> dict[str, str]:
    profile = selected_profile_name()
    if not profile:
        return {}
    return config_profiles().get(profile, {})


def setting(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is not None and value != "":
        return value
    value = selected_profile_values().get(name)
    if value is not None and value != "":
        return value
    value = config_values().get(name)
    if value is not None and value != "":
        return value
    return default


def base_url() -> str:
    return setting("SUM_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def json_dumps(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def parse_json_arg(raw: str | None, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON argument: {exc}") from exc


def ssl_context() -> ssl.SSLContext | None:
    cert_file = setting("SSL_CERT_FILE") or os.getenv("REQUESTS_CA_BUNDLE")
    if cert_file:
        return ssl.create_default_context(cafile=cert_file)
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def format_url_error(exc: urllib.error.URLError) -> str:
    reason = exc.reason
    if isinstance(reason, ssl.SSLCertVerificationError):
        return (
            "Request failed: TLS certificate verification failed. "
            "Set SSL_CERT_FILE to a CA bundle path, or install certifi in this Python environment."
        )
    return f"Request failed: {exc}"


def request_json(
    method: str,
    path_or_url: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any = None,
    query: dict[str, Any] | None = None,
    form: bool = False,
) -> Any:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        url = path_or_url
    else:
        path = path_or_url if path_or_url.startswith("/") else f"/{path_or_url}"
        url = f"{base_url()}{path}"

    if query:
        clean_query = {
            key: str(value)
            for key, value in query.items()
            if value is not None
        }
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urllib.parse.urlencode(clean_query)}"

    data = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=60, context=ssl_context()) as response:
            raw = response.read()
            if not raw:
                return None
            content_type = response.headers.get("Content-Type", "")
            if "json" not in content_type:
                return raw.decode("utf-8", errors="replace")
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        raise SystemExit(json_dumps({
            "error": {
                "status": exc.code,
                "reason": exc.reason,
                "body": detail,
            }
        })) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(format_url_error(exc)) from exc


def fetch_openapi() -> dict[str, Any]:
    return request_json("GET", "/openapi.json")


def exchange_m2m_token() -> str:
    client_id = setting("SUM_API_CLIENT_ID")
    client_secret = setting("SUM_API_CLIENT_SECRET")
    scope = setting("SUM_API_M2M_SCOPE")
    if not client_id or not client_secret:
        raise SystemExit(
            "Set SUM_API_ACCESS_TOKEN, or configure SUM_API_CLIENT_ID and SUM_API_CLIENT_SECRET"
        )

    body: dict[str, Any] = {
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if scope:
        body["scope"] = scope

    response = request_json("POST", "/v1/auth/m2m/token", body=body, form=True)
    token = response.get("access_token") if isinstance(response, dict) else None
    if not token:
        raise SystemExit("M2M token response did not include access_token")
    return token


def auth_headers(required: bool = True) -> dict[str, str]:
    token = setting("SUM_API_ACCESS_TOKEN")
    if not token:
        token = exchange_m2m_token() if required else None
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def resolve_refs(node: Any, spec: dict[str, Any], _seen: frozenset[str] | None = None) -> Any:
    seen = _seen or frozenset()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            if ref in seen:
                return {"$ref": ref, "__cycle__": True}
            target: Any = spec
            for part in ref.lstrip("#/").split("/"):
                if not isinstance(target, dict) or part not in target:
                    return node
                target = target[part]
            return resolve_refs(target, spec, seen | {ref})
        return {key: resolve_refs(value, spec, seen) for key, value in node.items()}
    if isinstance(node, list):
        return [resolve_refs(item, spec, seen) for item in node]
    return node


def request_stream(
    method: str,
    path_or_url: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any = None,
    query: dict[str, Any] | None = None,
) -> None:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        url = path_or_url
    else:
        path = path_or_url if path_or_url.startswith("/") else f"/{path_or_url}"
        url = f"{base_url()}{path}"

    if query:
        clean_query = {key: str(value) for key, value in query.items() if value is not None}
        if clean_query:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urllib.parse.urlencode(clean_query)}"

    request_headers = {"Accept": "text/event-stream"}
    if headers:
        for key, value in headers.items():
            if key.lower() != "accept":
                request_headers[key] = value

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=600, context=ssl_context()) as response:
            for raw_line in response:
                sys.stdout.write(raw_line.decode("utf-8", errors="replace"))
                sys.stdout.flush()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        raise SystemExit(json_dumps({
            "error": {
                "status": exc.code,
                "reason": exc.reason,
                "body": detail,
            }
        })) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(format_url_error(exc)) from exc


def iter_operations(spec: dict[str, Any]):
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict):
                continue
            yield method.upper(), path, operation


def command_openapi(_: argparse.Namespace) -> None:
    print(json_dumps(fetch_openapi()))


def command_operations(args: argparse.Namespace) -> None:
    spec = fetch_openapi()
    needle = (args.search or "").lower()
    rows = []
    for method, path, operation in iter_operations(spec):
        haystack = " ".join([
            method,
            path,
            str(operation.get("operationId", "")),
            str(operation.get("summary", "")),
            " ".join(operation.get("tags", [])),
        ]).lower()
        if needle and needle not in haystack:
            continue
        rows.append({
            "method": method,
            "path": path,
            "operation_id": operation.get("operationId"),
            "tags": operation.get("tags", []),
            "summary": operation.get("summary"),
        })
    print(json_dumps(rows))


def find_operation(spec: dict[str, Any], operation_id: str) -> tuple[str, str, dict[str, Any]]:
    for method, path, operation in iter_operations(spec):
        if operation.get("operationId") == operation_id:
            return method, path, operation
    raise SystemExit(f"Operation not found: {operation_id}")


def fill_path(path: str, params: dict[str, Any]) -> str:
    filled = path
    for key, value in params.items():
        filled = filled.replace("{" + key + "}", urllib.parse.quote(str(value), safe=""))
    if "{" in filled or "}" in filled:
        raise SystemExit(f"Missing path parameter for {filled}")
    return filled


def operation_query_params(operation: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    query = {}
    for parameter in operation.get("parameters", []):
        if not isinstance(parameter, dict):
            continue
        if parameter.get("in") != "query":
            continue
        name = parameter.get("name")
        if name in params:
            query[name] = params[name]
    return query


def command_operation(args: argparse.Namespace) -> None:
    spec = fetch_openapi()
    method, path, operation = find_operation(spec, args.operation_id)
    params = parse_json_arg(args.params, {})
    body = parse_json_arg(args.body, None)
    filled_path = fill_path(path, params)
    query = operation_query_params(operation, params)
    if args.stream:
        request_stream(method, filled_path, headers=auth_headers(), body=body, query=query)
        return
    response = request_json(
        method,
        filled_path,
        headers=auth_headers(),
        body=body,
        query=query,
    )
    print(json_dumps(response))


def command_call(args: argparse.Namespace) -> None:
    query = parse_json_arg(args.query, {})
    body = parse_json_arg(args.body, None)
    if args.stream:
        request_stream(
            args.method,
            args.path,
            headers=auth_headers(),
            body=body,
            query=query,
        )
        return
    response = request_json(
        args.method,
        args.path,
        headers=auth_headers(),
        body=body,
        query=query,
    )
    print(json_dumps(response))


def command_describe(args: argparse.Namespace) -> None:
    spec = fetch_openapi()
    method, path, operation = find_operation(spec, args.operation_id)
    request_body = operation.get("requestBody")
    out = {
        "method": method,
        "path": path,
        "operationId": operation.get("operationId"),
        "summary": operation.get("summary"),
        "description": operation.get("description"),
        "tags": operation.get("tags", []),
        "parameters": resolve_refs(operation.get("parameters", []), spec),
        "requestBody": resolve_refs(request_body, spec) if request_body else None,
        "responses": resolve_refs(operation.get("responses", {}), spec),
    }
    print(json_dumps(out))


def command_schema(args: argparse.Namespace) -> None:
    spec = fetch_openapi()
    schemas = spec.get("components", {}).get("schemas", {})
    name = args.name
    if name not in schemas:
        matches = [n for n in schemas if name.lower() in n.lower()]
        if not matches:
            raise SystemExit(f"Schema not found: {name}")
        if len(matches) > 1:
            raise SystemExit(
                f"Ambiguous schema name '{name}'. Candidates: {', '.join(sorted(matches)[:10])}"
            )
        name = matches[0]
    print(json_dumps({"name": name, "schema": resolve_refs(schemas[name], spec)}))


def command_token(_: argparse.Namespace) -> None:
    print(json_dumps({"access_token": exchange_m2m_token()}))


def config_file_mode(path: pathlib.Path) -> str | None:
    if not path.exists():
        return None
    return oct(path.stat().st_mode & 0o777)


def prompt_if_needed(label: str, current: str | None, *, secret: bool = False) -> str | None:
    if current:
        return current
    if not sys.stdin.isatty():
        return current
    prompt = f"{label}: "
    return getpass.getpass(prompt) if secret else input(prompt)


def redacted_values(values: dict[str, str]) -> dict[str, str]:
    redacted = {}
    for key, value in values.items():
        if "SECRET" in key or "TOKEN" in key:
            redacted[key] = "[redacted]" if value else ""
        else:
            redacted[key] = value
    return redacted


def render_config(values: dict[str, str], profiles: dict[str, dict[str, str]]) -> str:
    lines = ["# Summation local API config. Do not commit this file."]
    for key in sorted(values):
        lines.append(f"{key}={values[key]}")
    for profile in sorted(profiles):
        if lines[-1] != "":
            lines.append("")
        lines.append(f"[profile.{profile}]")
        for key in sorted(profiles[profile]):
            lines.append(f"{key}={profiles[profile][key]}")
    return "\n".join(lines) + "\n"


def write_config_file(
    path: pathlib.Path,
    values: dict[str, str],
    profiles: dict[str, dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_config(values, profiles), encoding="utf-8")
    os.chmod(path, 0o600)


def command_configure(args: argparse.Namespace) -> None:
    path = pathlib.Path(args.path).expanduser() if args.path else home_config_path()
    file_config = read_config_from_path(path)
    root_values = dict(file_config.get("values", {}))
    profiles = {
        name: dict(profile)
        for name, profile in file_config.get("profiles", {}).items()
    }
    profile_name = args.profile or profile_name_from(root_values, profiles) or selected_profile_name()
    target_values = dict(profiles.get(profile_name, {})) if profile_name else dict(root_values)
    client_id = prompt_if_needed(
        "SUM_API_CLIENT_ID",
        args.client_id or target_values.get("SUM_API_CLIENT_ID") or setting("SUM_API_CLIENT_ID"),
    )
    client_secret = prompt_if_needed(
        "SUM_API_CLIENT_SECRET",
        args.client_secret
        or target_values.get("SUM_API_CLIENT_SECRET")
        or setting("SUM_API_CLIENT_SECRET"),
        secret=True,
    )
    values = {
        "SUM_API_BASE_URL": (
            args.base_url
            or target_values.get("SUM_API_BASE_URL")
            or setting("SUM_API_BASE_URL", DEFAULT_BASE_URL)
        ),
        "SUM_API_CLIENT_ID": client_id or "",
        "SUM_API_CLIENT_SECRET": client_secret or "",
    }
    if args.scope or target_values.get("SUM_API_M2M_SCOPE") or setting("SUM_API_M2M_SCOPE"):
        values["SUM_API_M2M_SCOPE"] = (
            args.scope
            or target_values.get("SUM_API_M2M_SCOPE")
            or setting("SUM_API_M2M_SCOPE", "")
        )

    missing = [key for key, value in values.items() if key != "SUM_API_M2M_SCOPE" and not value]
    if missing:
        raise SystemExit(f"Missing required config values: {', '.join(missing)}")

    stored_profile = profile_name or args.profile
    if stored_profile:
        profiles[stored_profile] = values
        if args.activate or not root_values.get(ACTIVE_PROFILE_KEY):
            root_values[ACTIVE_PROFILE_KEY] = stored_profile
        stored = sorted(values.keys())
    else:
        root_values.update(values)
        stored = sorted(values.keys())

    write_config_file(path, root_values, profiles)
    print(json_dumps({
        "config_file": str(path),
        "mode": config_file_mode(path),
        "active_profile": root_values.get(ACTIVE_PROFILE_KEY),
        "profile": stored_profile,
        "stored": stored,
    }))


def command_doctor(_: argparse.Namespace) -> None:
    spec = fetch_openapi()
    config_path = active_config_path()
    result = {
        "base_url": base_url(),
        "profile": selected_profile_name(),
        "config_file": str(config_path) if config_path else None,
        "config_file_mode": config_file_mode(config_path) if config_path else None,
        "openapi_title": spec.get("info", {}).get("title"),
        "openapi_version": spec.get("info", {}).get("version"),
        "path_count": len(spec.get("paths", {})),
        "has_access_token": bool(setting("SUM_API_ACCESS_TOKEN")),
        "has_m2m_credentials": bool(setting("SUM_API_CLIENT_ID") and setting("SUM_API_CLIENT_SECRET")),
    }
    print(json_dumps(result))


def command_profiles(_: argparse.Namespace) -> None:
    profiles = config_profiles()
    print(json_dumps({
        "active_profile": selected_profile_name(),
        "config_file": str(active_config_path()) if active_config_path() else None,
        "profiles": [
            {
                "name": name,
                "active": name == selected_profile_name(),
                "settings": redacted_values(values),
            }
            for name, values in sorted(profiles.items())
        ],
        "legacy_settings": redacted_values(config_values()),
    }))


def command_use_profile(args: argparse.Namespace) -> None:
    path = pathlib.Path(args.path).expanduser() if args.path else active_config_path()
    if not path:
        path = home_config_path()
    file_config = read_config_from_path(path)
    profiles = {
        name: dict(profile)
        for name, profile in file_config.get("profiles", {}).items()
    }
    if args.profile not in profiles:
        raise SystemExit(f"Profile not found: {args.profile}")
    values = dict(file_config.get("values", {}))
    values[ACTIVE_PROFILE_KEY] = args.profile
    write_config_file(path, values, profiles)
    print(json_dumps({
        "config_file": str(path),
        "mode": config_file_mode(path),
        "active_profile": args.profile,
    }))


def add_profile_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", help="Named profile from .summation-config")


def main() -> int:
    parser = argparse.ArgumentParser(description="Summation sum-api helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    openapi_parser = subparsers.add_parser("openapi", help="Fetch the live OpenAPI document")
    add_profile_argument(openapi_parser)
    openapi_parser.set_defaults(func=command_openapi)

    operations_parser = subparsers.add_parser("operations", help="List OpenAPI operations")
    add_profile_argument(operations_parser)
    operations_parser.add_argument("search", nargs="?", help="Filter by method, path, tag, operationId, or summary")
    operations_parser.set_defaults(func=command_operations)

    operation_parser = subparsers.add_parser("operation", help="Call an operation by operationId")
    add_profile_argument(operation_parser)
    operation_parser.add_argument("operation_id")
    operation_parser.add_argument("--params", help="JSON object for path and query parameters")
    operation_parser.add_argument("--body", help="JSON request body")
    operation_parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream response body line-by-line (for SSE or NDJSON endpoints; pair with Monitor in Claude Code)",
    )
    operation_parser.set_defaults(func=command_operation)

    call_parser = subparsers.add_parser("call", help="Call a method and path directly")
    add_profile_argument(call_parser)
    call_parser.add_argument("method")
    call_parser.add_argument("path")
    call_parser.add_argument("--query", help="JSON object of query parameters")
    call_parser.add_argument("--body", help="JSON request body")
    call_parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream response body line-by-line (for SSE or NDJSON endpoints; pair with Monitor in Claude Code)",
    )
    call_parser.set_defaults(func=command_call)

    describe_parser = subparsers.add_parser(
        "describe",
        help="Print an operation's resolved schema without calling it",
    )
    add_profile_argument(describe_parser)
    describe_parser.add_argument("operation_id")
    describe_parser.set_defaults(func=command_describe)

    schema_parser = subparsers.add_parser(
        "schema",
        help="Print a component schema with $ref's resolved (substring match if name is not exact)",
    )
    add_profile_argument(schema_parser)
    schema_parser.add_argument("name")
    schema_parser.set_defaults(func=command_schema)

    token_parser = subparsers.add_parser("token", help="Exchange M2M credentials for an access token")
    add_profile_argument(token_parser)
    token_parser.set_defaults(func=command_token)

    configure_parser = subparsers.add_parser("configure", help="Write a local Summation config file")
    configure_parser.add_argument("--profile", help="Profile name to create or update")
    configure_parser.add_argument(
        "--activate",
        action="store_true",
        help="Make the written profile active",
    )
    configure_parser.add_argument("--base-url", dest="base_url", help="sum-api base URL")
    configure_parser.add_argument("--client-id", dest="client_id", help="M2M client ID")
    configure_parser.add_argument("--client-secret", dest="client_secret", help="M2M client secret")
    configure_parser.add_argument("--scope", help="M2M token scope")
    configure_parser.add_argument("--path", help="Config file path")
    configure_parser.set_defaults(func=command_configure)

    doctor_parser = subparsers.add_parser("doctor", help="Check OpenAPI reachability and local auth inputs")
    add_profile_argument(doctor_parser)
    doctor_parser.set_defaults(func=command_doctor)

    profiles_parser = subparsers.add_parser("profiles", help="List configured profiles")
    profiles_parser.set_defaults(func=command_profiles)

    use_profile_parser = subparsers.add_parser("use-profile", help="Set the active profile")
    use_profile_parser.add_argument("profile")
    use_profile_parser.add_argument("--path", help="Config file path")
    use_profile_parser.set_defaults(func=command_use_profile)

    args = parser.parse_args()
    global PROFILE_OVERRIDE
    PROFILE_OVERRIDE = getattr(args, "profile", None)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
