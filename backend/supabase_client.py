from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class SupabaseClient:
    def __init__(self, base_url: str, service_key: str, timeout: int = 25) -> None:
        self.base_url = base_url.rstrip("/") + "/rest/v1"
        self.service_key = service_key
        self.timeout = timeout
        self._ssl_context = self._build_ssl_context()

    @staticmethod
    def _build_ssl_context() -> ssl.SSLContext:
        try:
            import certifi

            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return ssl.create_default_context()

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)

        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("apikey", self.service_key)
        request.add_header("Authorization", f"Bearer {self.service_key}")
        request.add_header("Content-Type", "application/json")
        if headers:
            for key, value in headers.items():
                request.add_header(key, value)

        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=self._ssl_context
            ) as response:
                body = response.read().decode("utf-8")
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type and body:
                    return response.status, json.loads(body), dict(response.headers)
                return response.status, body, dict(response.headers)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            content_type = exc.headers.get("Content-Type", "")
            if "application/json" in content_type and body:
                return exc.code, json.loads(body), dict(exc.headers)
            return exc.code, body, dict(exc.headers)

    def select(
        self,
        table: str,
        columns: str,
        filters: dict[str, str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order: str | None = None,
        count: bool = False,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": columns}
        if filters:
            params.update(filters)
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)
        if order:
            params["order"] = order

        headers = {}
        if count:
            headers["Prefer"] = "count=exact"

        status, data, _ = self._request("GET", f"/{table}", params=params, headers=headers)
        if status >= 400:
            raise RuntimeError(f"Supabase select failed: {status} {data}")
        return data

    def select_all(
        self,
        table: str,
        columns: str,
        filters: dict[str, str] | None = None,
        order: str | None = None,
        page_size: int = 1000,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self.select(
                table,
                columns,
                filters=filters,
                limit=page_size,
                offset=offset,
                order=order,
            )
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows

    def insert(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        status, data, _ = self._request(
            "POST",
            f"/{table}",
            payload=rows,
            headers={"Prefer": "return=representation"},
        )
        if status >= 400:
            raise RuntimeError(f"Supabase insert failed: {status} {data}")
        return data

    def upsert(
        self, table: str, rows: list[dict[str, Any]], on_conflict: str
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        status, data, _ = self._request(
            "POST",
            f"/{table}",
            params={"on_conflict": on_conflict},
            payload=rows,
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        )
        if status >= 400:
            raise RuntimeError(f"Supabase upsert failed: {status} {data}")
        return data

    def update(self, table: str, values: dict[str, Any], filters: dict[str, str]) -> None:
        status, data, _ = self._request(
            "PATCH",
            f"/{table}",
            params=filters,
            payload=values,
            headers={"Prefer": "return=minimal"},
        )
        if status >= 400:
            raise RuntimeError(f"Supabase update failed: {status} {data}")
