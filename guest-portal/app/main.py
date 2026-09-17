from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from .keycloak_admin import kc
from .ldap_guests import ldap_guests

STATIC = Path(__file__).resolve().parents[1] / "static"

app = FastAPI(title="Bibliolatino Guest Portal", docs_url=None, redoc_url=None)
app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")


class RegisterBody(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    institution: str = Field(default="", max_length=160)
    reason: str = Field(default="", max_length=500)


async def require_admin(email: str | None) -> str:
    if not email:
        raise HTTPException(status_code=401, detail="Se requiere autenticación.")
    if not await kc.user_has_admin_role(email):
        raise HTTPException(status_code=403, detail="Se requiere rol de administrador.")
    return email


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "guest-portal"}


@app.get("/")
async def register_page():
    return FileResponse(STATIC / "register.html")


@app.get("/admin")
async def admin_page():
    return FileResponse(STATIC / "admin.html")


@app.post("/api/register")
async def register(body: RegisterBody):
    ldap_info: dict = {}
    try:
        ldap_info = ldap_guests.create_guest(
            email=str(body.email),
            first_name=body.first_name,
            last_name=body.last_name,
            password=body.password,
            institution=body.institution,
            reason=body.reason,
        )
    except Exception as exc:  # noqa: BLE001
        ldap_info = {"error": str(exc)}

    try:
        result = await kc.create_guest(
            email=str(body.email),
            first_name=body.first_name,
            last_name=body.last_name,
            password=body.password,
            institution=body.institution,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        # If Keycloak fails but LDAP succeeded, still accept (admin can sync)
        if ldap_info.get("dn"):
            result = {
                "id": ldap_info.get("uid"),
                "email": str(body.email).strip().lower(),
                "status": "pending",
                "note": f"LDAP ok; Keycloak: {exc}",
            }
        else:
            raise HTTPException(status_code=502, detail=f"Error al crear la cuenta: {exc}") from exc

    return {
        "ok": True,
        "message": "Solicitud enviada. Un administrador debe aprobar tu acceso antes de iniciar sesión.",
        "user": result,
        "ldap": ldap_info,
    }


@app.get("/api/admin/pending")
async def pending(x_auth_request_email: str | None = Header(default=None)):
    await require_admin(x_auth_request_email)
    users = await kc.list_by_status("pending")
    return {"users": users}


@app.get("/api/admin/rejected")
async def rejected(x_auth_request_email: str | None = Header(default=None)):
    await require_admin(x_auth_request_email)
    users = await kc.list_by_status("rejected")
    return {"users": users}


@app.post("/api/admin/{user_id}/approve")
async def approve(user_id: str, x_auth_request_email: str | None = Header(default=None)):
    await require_admin(x_auth_request_email)
    try:
        user = await kc.approve(user_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if user.get("email"):
        try:
            ldap_guests.set_status(user["email"], "approved")
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "user": user}


@app.post("/api/admin/{user_id}/reject")
async def reject(user_id: str, x_auth_request_email: str | None = Header(default=None)):
    await require_admin(x_auth_request_email)
    try:
        user = await kc.reject(user_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if user.get("email"):
        try:
            ldap_guests.set_status(user["email"], "rejected")
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "user": user}


@app.exception_handler(HTTPException)
async def http_exc_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
