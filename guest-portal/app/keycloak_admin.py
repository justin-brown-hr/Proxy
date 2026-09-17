"""Keycloak Admin API helper — create guests disabled; approve by enabling."""
from __future__ import annotations

from typing import Any

import httpx

from .config import settings

ATTR_STATUS = "guest_status"
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


class KeycloakAdmin:
    def __init__(self) -> None:
        self.base = settings.keycloak_url.rstrip("/")
        self.realm = settings.keycloak_realm
        self._token: str | None = None

    async def _token_password(self) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base}/realms/master/protocol/openid-connect/token",
                data={
                    "client_id": "admin-cli",
                    "username": settings.keycloak_admin_user,
                    "password": settings.keycloak_admin_password,
                    "grant_type": "password",
                },
            )
            r.raise_for_status()
            return r.json()["access_token"]

    async def _token_client(self) -> str | None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base}/realms/{self.realm}/protocol/openid-connect/token",
                data={
                    "client_id": settings.guest_client_id,
                    "client_secret": settings.guest_client_secret,
                    "grant_type": "client_credentials",
                },
            )
            if r.status_code >= 400:
                return None
            return r.json().get("access_token")

    async def access_token(self) -> str:
        token = await self._token_client()
        if token:
            return token
        return await self._token_password()

    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def create_guest(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        password: str,
        institution: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        token = await self.access_token()
        username = email.strip().lower()
        local_uid = username.split("@")[0]
        async with httpx.AsyncClient(timeout=30.0) as client:
            existing = await client.get(
                f"{self.base}/admin/realms/{self.realm}/users",
                params={"email": username, "exact": "true"},
                headers=self._headers(token),
            )
            existing.raise_for_status()
            found = existing.json()

            # If LDAP already created the person, federation may surface them here —
            # adopt that user instead of failing as duplicate.
            if found:
                user = found[0]
                user_id = user["id"]
                attrs = dict(user.get("attributes") or {})
                st = (attrs.get(ATTR_STATUS) or [""])[0]
                # Adopt freshly LDAP-provisioned / still-pending guests
                if st in ("", STATUS_PENDING, "unknown") or (
                    not user.get("enabled") and st != STATUS_APPROVED
                ):
                    attrs[ATTR_STATUS] = [STATUS_PENDING]
                    attrs["guest_institution"] = [institution.strip()]
                    attrs["guest_reason"] = [reason.strip()]
                    user["attributes"] = attrs
                    user["enabled"] = False
                    user["firstName"] = first_name.strip()
                    user["lastName"] = last_name.strip()
                    put = await client.put(
                        f"{self.base}/admin/realms/{self.realm}/users/{user_id}",
                        headers=self._headers(token),
                        json=user,
                    )
                    put.raise_for_status()
                    try:
                        await client.put(
                            f"{self.base}/admin/realms/{self.realm}/users/{user_id}/reset-password",
                            headers=self._headers(token),
                            json={"type": "password", "value": password, "temporary": False},
                        )
                    except Exception:
                        pass
                    await self._assign_guest_role(client, token, user_id)
                    return {
                        "id": user_id,
                        "email": username,
                        "status": STATUS_PENDING,
                    }
                raise ValueError("Ya existe una cuenta con ese correo.")

            create_payload = {
                "username": local_uid,
                "email": username,
                "firstName": first_name.strip(),
                "lastName": last_name.strip(),
                "enabled": False,
                "emailVerified": False,
                "credentials": [{"type": "password", "value": password, "temporary": False}],
            }
            r = await client.post(
                f"{self.base}/admin/realms/{self.realm}/users",
                headers=self._headers(token),
                json=create_payload,
            )
            if r.status_code == 409:
                raise ValueError("Ya existe una cuenta con ese correo.")
            if r.status_code >= 400:
                detail = r.text[:500]
                raise RuntimeError(f"Keycloak create failed ({r.status_code}): {detail}")
            r.raise_for_status()

            users = await client.get(
                f"{self.base}/admin/realms/{self.realm}/users",
                params={"email": username, "exact": "true"},
                headers=self._headers(token),
            )
            users.raise_for_status()
            user = users.json()[0]
            user_id = user["id"]

            user["attributes"] = {
                ATTR_STATUS: [STATUS_PENDING],
                "guest_institution": [institution.strip()],
                "guest_reason": [reason.strip()],
            }
            user["enabled"] = False
            put = await client.put(
                f"{self.base}/admin/realms/{self.realm}/users/{user_id}",
                headers=self._headers(token),
                json=user,
            )
            put.raise_for_status()

            await self._assign_guest_role(client, token, user_id)
            return {
                "id": user_id,
                "email": username,
                "status": STATUS_PENDING,
            }

    async def _assign_guest_role(self, client: httpx.AsyncClient, token: str, user_id: str) -> None:
        roles = await client.get(
            f"{self.base}/admin/realms/{self.realm}/roles",
            headers=self._headers(token),
        )
        roles.raise_for_status()
        guest = next((x for x in roles.json() if x["name"] == "guest"), None)
        if not guest:
            return
        await client.post(
            f"{self.base}/admin/realms/{self.realm}/users/{user_id}/role-mappings/realm",
            headers=self._headers(token),
            json=[guest],
        )

    async def list_by_status(self, status: str) -> list[dict[str, Any]]:
        token = await self.access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Prefer attribute search; always fall back to a broader scan + filter
            # (KC user-profile can leave attrs unset until PUT succeeds).
            candidates: list[dict[str, Any]] = []
            r = await client.get(
                f"{self.base}/admin/realms/{self.realm}/users",
                params={"q": f"{ATTR_STATUS}:{status}", "max": 200},
                headers=self._headers(token),
            )
            if r.status_code < 400 and r.json():
                candidates = r.json()
            else:
                params: dict[str, Any] = {"max": 500}
                if status == STATUS_PENDING:
                    params["enabled"] = "false"
                r2 = await client.get(
                    f"{self.base}/admin/realms/{self.realm}/users",
                    params=params,
                    headers=self._headers(token),
                )
                r2.raise_for_status()
                candidates = r2.json()

            out = []
            for u in candidates:
                attrs = u.get("attributes") or {}
                st = (attrs.get(ATTR_STATUS) or [""])[0]
                if st == status:
                    out.append(self._serialize(u))
            return out

    def _serialize(self, u: dict[str, Any]) -> dict[str, Any]:
        attrs = u.get("attributes") or {}
        return {
            "id": u["id"],
            "username": u.get("username"),
            "email": u.get("email"),
            "firstName": u.get("firstName") or "",
            "lastName": u.get("lastName") or "",
            "enabled": bool(u.get("enabled")),
            "status": (attrs.get(ATTR_STATUS) or ["unknown"])[0],
            "institution": (attrs.get("guest_institution") or [""])[0],
            "reason": (attrs.get("guest_reason") or [""])[0],
            "createdTimestamp": u.get("createdTimestamp"),
        }

    async def approve(self, user_id: str) -> dict[str, Any]:
        return await self._set_status(user_id, STATUS_APPROVED, enabled=True)

    async def reject(self, user_id: str) -> dict[str, Any]:
        return await self._set_status(user_id, STATUS_REJECTED, enabled=False)

    async def _set_status(self, user_id: str, status: str, *, enabled: bool) -> dict[str, Any]:
        token = await self.access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{self.base}/admin/realms/{self.realm}/users/{user_id}",
                headers=self._headers(token),
            )
            r.raise_for_status()
            user = r.json()
            attrs = dict(user.get("attributes") or {})
            attrs[ATTR_STATUS] = [status]
            user["attributes"] = attrs
            user["enabled"] = enabled
            if status == STATUS_APPROVED:
                user["emailVerified"] = True
            put = await client.put(
                f"{self.base}/admin/realms/{self.realm}/users/{user_id}",
                headers=self._headers(token),
                json=user,
            )
            put.raise_for_status()
            return self._serialize(user)

    async def user_has_admin_role(self, email: str) -> bool:
        if not email or email == "-":
            return False
        token = await self.access_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            users: list[dict[str, Any]] = []
            for params in (
                {"email": email, "exact": "true"},
                {"username": email, "exact": "true"},
            ):
                r = await client.get(
                    f"{self.base}/admin/realms/{self.realm}/users",
                    params=params,
                    headers=self._headers(token),
                )
                r.raise_for_status()
                users = r.json()
                if users:
                    break
            if not users:
                return False
            uid = users[0]["id"]
            roles = await client.get(
                f"{self.base}/admin/realms/{self.realm}/users/{uid}/role-mappings/realm",
                headers=self._headers(token),
            )
            roles.raise_for_status()
            names = {x["name"] for x in roles.json()}
            return "admin" in names


kc = KeycloakAdmin()
