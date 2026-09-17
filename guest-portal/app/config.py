from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    keycloak_url: str = "http://keycloak:8080"
    keycloak_realm: str = "library"
    keycloak_admin_user: str = "admin"
    keycloak_admin_password: str = "admin"
    # Prefer service-account client when configured
    guest_client_id: str = "guest-portal"
    guest_client_secret: str = "guest-portal-secret-change-me"
    public_app_url: str = "https://proxy.bibliolatino.com"

    # Optional OpenLDAP (Milestone 4) — guests mirrored into directory
    ldap_url: str = ""
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_base_dn: str = ""
    ldap_users_ou: str = ""


settings = Settings()
