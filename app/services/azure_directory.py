import base64
import logging
from typing import Any, Dict, List, Optional, Tuple

import msal
import requests

from app.config import settings

logger = logging.getLogger("services.azure_directory")


class AzureGraphError(RuntimeError):
    """Error devuelto por Microsoft Graph."""

    def __init__(
        self,
        status_code: int,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        error_code: Optional[str] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.error_code = error_code
        self.request_id = request_id
        self.correlation_id = correlation_id


class AzureDirectoryClient:
    GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    DEFAULT_ALLOWED_DOMAINS = {
        "atisa.es",
        "grupoatisa.es",
        "atisaes.onmicrosoft.com",
    }

    def __init__(self):
        self._client_id = settings.get_azure_client_id()
        self._client_secret = settings.get_azure_client_secret()
        self._tenant_id = settings.get_azure_tenant_id()
        if not (self._client_id and self._client_secret and self._tenant_id):
            raise ValueError("Azure AD no configurado para consultas a Microsoft Graph")
        authority = f"https://login.microsoftonline.com/{self._tenant_id}"
        self._app = msal.ConfidentialClientApplication(
            client_id=self._client_id,
            client_credential=self._client_secret,
            authority=authority,
        )
        dominios = settings.get_azure_allowed_domains()
        if dominios:
            self._allowed_domains = {d.lower() for d in dominios}
        else:
            self._allowed_domains = set(self.DEFAULT_ALLOWED_DOMAINS)

    def _get_token(self) -> str:
        result = self._app.acquire_token_silent(self.GRAPH_SCOPE, account=None)
        if not result:
            result = self._app.acquire_token_for_client(scopes=self.GRAPH_SCOPE)
        if "access_token" not in result:
            error = result.get("error_description") or "No se pudo obtener token de Graph"
            raise RuntimeError(error)
        return result["access_token"]

    def search_users(
        self,
        query: str,
        page: int = 1,
        page_size: int = 25,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        query = (query or "").strip()
        page = max(1, page)
        page_size = max(1, min(page_size, 50))
        desired_count = (page * page_size) + 1

        token = self._get_token()
        params = {
            "$top": min(desired_count, 100),
            "$select": "displayName,userPrincipalName,mail,id,jobTitle,department,userType",
        }
        safe_filter = "userType eq 'Member'"
        if query:
            safe_query = query.replace("'", "''")
            safe_filter = (
                f"(startswith(displayName,'{safe_query}') "
                f"or startswith(userPrincipalName,'{safe_query}') "
                f"or startswith(mail,'{safe_query}')) and userType eq 'Member'"
            )
        params["$filter"] = safe_filter

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        internos: List[Dict[str, Any]] = []
        next_link: Optional[str] = None
        page_count = 0
        max_pages = 6
        url = f"{self.GRAPH_BASE}/users"
        use_params: Optional[Dict[str, Any]] = params

        while True:
            response = requests.get(url, headers=headers, params=use_params, timeout=10)
            use_params = None
            if response.status_code != 200:
                payload: Optional[Dict[str, Any]] = None
                try:
                    payload = response.json()
                except Exception:
                    payload = None
                human_message = None
                graph_code: Optional[str] = None
                request_id: Optional[str] = None
                correlation_id: Optional[str] = None
                if isinstance(payload, dict):
                    error_block = payload.get("error")
                    if isinstance(error_block, dict):
                        human_message = error_block.get("message")
                        graph_code = error_block.get("code")
                        inner_error = error_block.get("innerError")
                        if isinstance(inner_error, dict):
                            request_id = inner_error.get("request-id") or inner_error.get("requestId")
                            correlation_id = inner_error.get("client-request-id") or inner_error.get("correlation-id")
                log_message = human_message or response.text
                logger.warning("Graph /users devolvio %s: %s", response.status_code, log_message)
                raise AzureGraphError(
                    response.status_code,
                    human_message or f"Microsoft Graph error {response.status_code}",
                    payload,
                    error_code=graph_code,
                    request_id=request_id,
                    correlation_id=correlation_id,
                )

            data = response.json()
            values = data.get("value") or []
            for item in values:
                if self._es_usuario_interno(item):
                    internos.append(item)
                if len(internos) >= desired_count:
                    break

            next_link = data.get("@odata.nextLink")
            if len(internos) >= desired_count or not next_link:
                break
            page_count += 1
            if page_count >= max_pages:
                break
            url = next_link

        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        slice_items = internos[start_index:end_index]

        resultados: List[Dict[str, Any]] = []
        for item in slice_items:
            photo = self._obtener_foto(token, item.get("id"))
            resultados.append(
                {
                    "id": item.get("id"),
                    "displayName": item.get("displayName"),
                    "userPrincipalName": item.get("userPrincipalName"),
                    "mail": item.get("mail"),
                    "jobTitle": item.get("jobTitle"),
                    "department": item.get("department"),
                    "photo": photo,
                }
            )

        has_more = bool(next_link) or len(internos) > end_index
        return resultados, has_more

    def _es_usuario_interno(self, user: Dict[str, Any]) -> bool:
        user_type = (user.get("userType") or "").strip().lower()
        if user_type != "member":
            return False
        principal = (user.get("userPrincipalName") or "").lower()
        mail = (user.get("mail") or "").lower()
        if "#ext#" in principal:
            return False
        if self._allowed_domains:
            for domain in self._allowed_domains:
                suffix = f"@{domain}"
                if principal.endswith(suffix) or (mail and mail.endswith(suffix)):
                    return True
            return False
        return True

    def _obtener_foto(self, token: str, user_id: Optional[str]) -> Optional[str]:
        if not user_id:
            return None
        url = f"{self.GRAPH_BASE}/users/{user_id}/photos/48x48/$value"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "image/*",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200 and resp.content:
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                encoded = base64.b64encode(resp.content).decode("ascii")
                return f"data:{content_type};base64,{encoded}"
        except Exception as exc:
            pass
        return None
