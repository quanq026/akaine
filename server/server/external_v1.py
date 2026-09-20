from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic

from flask import Blueprint, g, jsonify, request, send_from_directory


PLAYER_COLUMNS = (
    "user_id", "name", "join_date", "user_code", "rating_ptt", "character_id",
    "is_char_uncapped", "is_char_uncapped_override", "is_hide_rating", "song_id",
    "difficulty", "score", "shiny_perfect_count", "perfect_count", "near_count",
    "miss_count", "health", "modifier", "time_played", "clear_type", "rating",
    "is_profile_public", "showcase_characters",
)
BEST_SCORE_COLUMNS = (
    "user_id", "song_id", "difficulty", "score", "shiny_perfect_count",
    "perfect_count", "near_count", "miss_count", "health", "modifier",
    "time_played", "best_clear_type", "clear_type", "rating", "score_v2",
)
RECENT_SCORE_COLUMNS = (
    "user_id", "r_index", "time_played", "song_id", "difficulty", "score",
    "shiny_perfect_count", "perfect_count", "near_count", "miss_count", "health",
    "modifier", "clear_type", "rating",
)
PLAY_COLUMNS = (
    "user_id", "song_id", "difficulty", "time_played", "score",
    "shiny_perfect_count", "perfect_count", "near_count", "miss_count", "health",
    "modifier", "clear_type", "rating",
)
USER_CODE_PATTERN = re.compile(r"^[0-9]{9}$")
SONG_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
CHART_COLUMNS = (
    "song_id", "name", "rating_pst", "rating_prs", "rating_ftr", "rating_byn",
    "rating_etr",
)
ASSET_PART_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
ASSET_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PUBLIC_UNTIL_DEFAULT = "2026-09-18T08:32:49Z"
ANONYMOUS_REQUEST_LIMIT = 300
ANONYMOUS_WINDOW_SECONDS = 60


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _public_until(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("public_until_requires_timezone")
    return parsed.astimezone(timezone.utc)


def create_blueprint(
    game_db_path: str | Path | None = None,
    log_db_path: str | Path | None = None,
    mapping_db_path: str | Path | None = None,
    asset_root: str | Path | None = None,
    public_until: str | datetime | None = None,
    anonymous_limit: int = ANONYMOUS_REQUEST_LIMIT,
    anonymous_window_seconds: int = ANONYMOUS_WINDOW_SECONDS,
) -> Blueprint:
    root = Path(os.environ.get("LYGUS_SERVER_ROOT", Path(__file__).resolve().parents[1]))
    game_db = Path(game_db_path or root / "database/arcaea_database.db")
    log_db = Path(log_db_path or root / "database/arcaea_log.db")
    mapping_db = Path(mapping_db_path or root / "database/discord_bot.db")
    assets = Path(asset_root or root / "assets")
    anonymous_deadline = _public_until(
        public_until or os.environ.get("EXTERNAL_API_PUBLIC_UNTIL", PUBLIC_UNTIL_DEFAULT)
    )
    if anonymous_limit < 1 or anonymous_window_seconds < 1:
        raise ValueError("invalid_anonymous_rate_limit")
    anonymous_requests: deque[float] = deque()
    anonymous_lock = Lock()
    bp = Blueprint("external_v1", __name__, url_prefix="/external/v1")

    def anonymous_active() -> bool:
        return datetime.now(timezone.utc) < anonymous_deadline

    def allow_anonymous_request() -> bool:
        now = monotonic()
        cutoff = now - anonymous_window_seconds
        with anonymous_lock:
            while anonymous_requests and anonymous_requests[0] <= cutoff:
                anonymous_requests.popleft()
            if len(anonymous_requests) >= anonymous_limit:
                return False
            anonymous_requests.append(now)
            return True

    def page_args() -> tuple[int, int]:
        try:
            limit = int(request.args.get("limit", 100))
            offset = int(request.args.get("offset", 0))
        except ValueError:
            raise ValueError("invalid_pagination")
        if not 1 <= limit <= 200 or not 0 <= offset <= 1_000_000:
            raise ValueError("invalid_pagination")
        return limit, offset

    def rows(connection: sqlite3.Connection, query: str, parameters: tuple) -> list[dict]:
        return [dict(row) for row in connection.execute(query, parameters).fetchall()]

    @bp.before_request
    def authenticate():
        header = request.headers.get("Authorization", "")
        if anonymous_active() and not header:
            g.external_api_auth_mode = "public-temporary"
            if not allow_anonymous_request():
                response = jsonify({"error": "rate_limited"})
                response.headers["Retry-After"] = str(anonymous_window_seconds)
                return response, 429
            return None
        if not header.startswith("Bearer ") or len(header) > 263:
            return jsonify({"error": "unauthorized"}), 401
        token = header[7:]
        if not token or any(character.isspace() for character in token):
            return jsonify({"error": "unauthorized"}), 401
        key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        try:
            connection = _readonly(mapping_db)
            try:
                found = connection.execute(
                    "SELECT 1 FROM external_api_key WHERE key_hash = ? LIMIT 1",
                    (key_hash,),
                ).fetchone()
            finally:
                connection.close()
        except sqlite3.Error:
            return jsonify({"error": "api_unavailable"}), 503
        if found is None:
            return jsonify({"error": "unauthorized"}), 401
        g.external_api_auth_mode = "bearer"
        return None

    @bp.after_request
    def secure_response(response):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-External-API-Auth-Mode"] = getattr(
            g, "external_api_auth_mode", "unauthorized"
        )
        response.headers["X-External-API-Public-Until"] = (
            anonymous_deadline.isoformat().replace("+00:00", "Z")
        )
        return response

    @bp.get("")
    def meta():
        return jsonify({
            "version": 1,
            "access": {
                "anonymous_active": anonymous_active(),
                "anonymous_until": anonymous_deadline.isoformat().replace("+00:00", "Z"),
                "anonymous_limit_per_window": anonymous_limit,
                "anonymous_window_seconds": anonymous_window_seconds,
                "bearer_supported": True,
            },
            "pagination": {"default_limit": 100, "max_limit": 200},
            "resources": {
                "players": {"path": "/players", "columns": PLAYER_COLUMNS},
                "best-scores": {
                    "path": "/best-scores", "columns": BEST_SCORE_COLUMNS,
                    "filters": ["user_code"],
                },
                "recent-scores": {
                    "path": "/recent-scores", "columns": RECENT_SCORE_COLUMNS,
                    "filters": ["user_code"],
                },
                "plays": {
                    "path": "/plays", "columns": PLAY_COLUMNS, "filters": ["user_id"],
                },
                "charts": {
                    "path": "/charts", "columns": CHART_COLUMNS, "filters": ["song_id"],
                },
                "assets": {
                    "paths": ["/assets/jackets", "/assets/characters"],
                },
            },
        })

    @bp.get("/players")
    def players():
        try:
            limit, offset = page_args()
        except ValueError:
            return jsonify({"error": "invalid_pagination"}), 400
        connection = _readonly(game_db)
        try:
            data = rows(
                connection,
                f"SELECT {','.join(PLAYER_COLUMNS)} FROM user ORDER BY user_id LIMIT ? OFFSET ?",
                (limit, offset),
            )
        finally:
            connection.close()
        return jsonify({"data": data, "count": len(data), "limit": limit, "offset": offset})

    @bp.get("/best-scores")
    def best_scores():
        try:
            limit, offset = page_args()
        except ValueError:
            return jsonify({"error": "invalid_pagination"}), 400
        user_code = request.args.get("user_code")
        if user_code is not None and not USER_CODE_PATTERN.fullmatch(user_code):
            return jsonify({"error": "invalid_user_code"}), 400
        selected = ",".join(f"b.{column}" for column in BEST_SCORE_COLUMNS)
        if user_code is None:
            query = f"SELECT {selected} FROM best_score b ORDER BY b.user_id,b.rating DESC LIMIT ? OFFSET ?"
            parameters = (limit, offset)
        else:
            query = (
                f"SELECT {selected} FROM best_score b JOIN user u ON u.user_id=b.user_id "
                "WHERE u.user_code=? ORDER BY b.rating DESC LIMIT ? OFFSET ?"
            )
            parameters = (user_code, limit, offset)
        connection = _readonly(game_db)
        try:
            data = rows(connection, query, parameters)
        finally:
            connection.close()
        return jsonify({"data": data, "count": len(data), "limit": limit, "offset": offset})

    @bp.get("/recent-scores")
    def recent_scores():
        try:
            limit, offset = page_args()
        except ValueError:
            return jsonify({"error": "invalid_pagination"}), 400
        user_code = request.args.get("user_code")
        if user_code is not None and not USER_CODE_PATTERN.fullmatch(user_code):
            return jsonify({"error": "invalid_user_code"}), 400
        selected = ",".join(f"r.{column}" for column in RECENT_SCORE_COLUMNS)
        if user_code is None:
            query = f"SELECT {selected} FROM recent30 r ORDER BY r.user_id,r.time_played DESC LIMIT ? OFFSET ?"
            parameters = (limit, offset)
        else:
            query = (
                f"SELECT {selected} FROM recent30 r JOIN user u ON u.user_id=r.user_id "
                "WHERE u.user_code=? ORDER BY r.time_played DESC LIMIT ? OFFSET ?"
            )
            parameters = (user_code, limit, offset)
        connection = _readonly(game_db)
        try:
            data = rows(connection, query, parameters)
        finally:
            connection.close()
        return jsonify({"data": data, "count": len(data), "limit": limit, "offset": offset})

    @bp.get("/plays")
    def plays():
        try:
            limit, offset = page_args()
            user_id = request.args.get("user_id")
            parsed_user_id = None if user_id is None else int(user_id)
            if parsed_user_id is not None and parsed_user_id < 0:
                raise ValueError
        except ValueError:
            return jsonify({"error": "invalid_query"}), 400
        selected = ",".join(PLAY_COLUMNS)
        if parsed_user_id is None:
            query = f"SELECT {selected} FROM user_score ORDER BY time_played DESC LIMIT ? OFFSET ?"
            parameters = (limit, offset)
        else:
            query = (
                f"SELECT {selected} FROM user_score WHERE user_id=? "
                "ORDER BY time_played DESC LIMIT ? OFFSET ?"
            )
            parameters = (parsed_user_id, limit, offset)
        connection = _readonly(log_db)
        try:
            data = rows(connection, query, parameters)
        finally:
            connection.close()
        return jsonify({"data": data, "count": len(data), "limit": limit, "offset": offset})

    @bp.get("/charts")
    def charts():
        try:
            limit, offset = page_args()
        except ValueError:
            return jsonify({"error": "invalid_pagination"}), 400
        song_id = request.args.get("song_id")
        if song_id is not None and not SONG_ID_PATTERN.fullmatch(song_id):
            return jsonify({"error": "invalid_song_id"}), 400
        selected = ",".join(CHART_COLUMNS)
        if song_id is None:
            query = f"SELECT {selected} FROM chart ORDER BY song_id LIMIT ? OFFSET ?"
            parameters = (limit, offset)
        else:
            query = f"SELECT {selected} FROM chart WHERE song_id=? LIMIT ? OFFSET ?"
            parameters = (song_id, limit, offset)
        connection = _readonly(game_db)
        try:
            data = rows(connection, query, parameters)
        finally:
            connection.close()
        return jsonify({"data": data, "count": len(data), "limit": limit, "offset": offset})

    def asset_response(folder: str, asset_path: str):
        parts = asset_path.split("/")
        if (
            not parts
            or len(asset_path) > 180
            or any(part in {"", ".", ".."} or not ASSET_PART_PATTERN.fullmatch(part) for part in parts)
            or Path(parts[-1]).suffix.lower() not in ASSET_EXTENSIONS
        ):
            return jsonify({"error": "invalid_asset_path"}), 400
        return send_from_directory(assets / folder, asset_path, conditional=True)

    def asset_listing(folder: str):
        try:
            limit, offset = page_args()
        except ValueError:
            return jsonify({"error": "invalid_pagination"}), 400
        base = assets / folder
        files = sorted(
            path.relative_to(base).as_posix()
            for path in base.rglob("*")
            if path.is_file() and path.suffix.lower() in ASSET_EXTENSIONS
        )
        data = files[offset:offset + limit]
        return jsonify({"data": data, "count": len(data), "limit": limit, "offset": offset})

    @bp.get("/assets/jackets")
    def jacket_assets():
        return asset_listing("jackets")

    @bp.get("/assets/characters")
    def character_assets():
        return asset_listing("char")

    @bp.get("/assets/jackets/<path:asset_path>")
    def jacket_asset(asset_path: str):
        return asset_response("jackets", asset_path)

    @bp.get("/assets/characters/<path:asset_path>")
    def character_asset(asset_path: str):
        return asset_response("char", asset_path)

    return bp
