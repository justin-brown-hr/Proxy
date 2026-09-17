"""Create / update guest users directly in OpenLDAP."""
from __future__ import annotations

import secrets
from typing import Any

from ldap3 import ALL, Connection, Server, MODIFY_REPLACE, HASHED_SALTED_SHA
from ldap3.utils.hashed import hashed

from .config import settings


class LdapGuests:
    def __init__(self) -> None:
        self.url = settings.ldap_url
        self.bind_dn = settings.ldap_bind_dn
        self.bind_password = settings.ldap_bind_password
        self.users_ou = settings.ldap_users_ou
        self.base_dn = settings.ldap_base_dn

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.bind_dn and self.bind_password and self.users_ou)

    def _conn(self) -> Connection:
        server = Server(self.url, get_info=ALL, connect_timeout=10)
        return Connection(
            server,
            user=self.bind_dn,
            password=self.bind_password,
            auto_bind=True,
            raise_exceptions=True,
        )

    def create_guest(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        password: str,
        institution: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"skipped": True, "reason": "ldap not configured"}
        uid = email.strip().lower().split("@")[0]
        with self._conn() as conn:
            if conn.search(self.users_ou, f"(uid={uid})", attributes=["uid"]):
                uid = f"{uid}.{secrets.token_hex(3)}"
            dn = f"uid={uid},{self.users_ou}"
            uid_number = 20000 + int(secrets.randbelow(40000))
            attrs = {
                "objectClass": ["inetOrgPerson", "posixAccount", "top"],
                "uid": uid,
                "cn": f"{first_name.strip()} {last_name.strip()}".strip(),
                "sn": last_name.strip() or uid,
                "givenName": first_name.strip() or uid,
                "mail": email.strip().lower(),
                "uidNumber": str(uid_number),
                "gidNumber": "5000",
                "homeDirectory": f"/home/{uid}",
                "loginShell": "/bin/bash",
                "userPassword": hashed(HASHED_SALTED_SHA, password),
                "employeeType": "pending",
                "description": f"guest institution={institution}; reason={reason}"[:500],
            }
            conn.add(dn, attributes=attrs)
            if conn.result.get("result") != 0:
                raise RuntimeError(f"LDAP add failed: {conn.result}")
            return {"dn": dn, "uid": uid, "status": "pending"}

    def set_status(self, email: str, status: str) -> bool:
        if not self.enabled:
            return False
        mail = email.strip().lower()
        with self._conn() as conn:
            if not conn.search(self.users_ou, f"(mail={mail})", attributes=["employeeType"]):
                return False
            dn = conn.entries[0].entry_dn
            value = {"approved": "guest", "rejected": "rejected"}.get(status, "pending")
            conn.modify(dn, {"employeeType": [(MODIFY_REPLACE, [value])]})
            return True


ldap_guests = LdapGuests()
