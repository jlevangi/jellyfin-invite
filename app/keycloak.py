import json
import urllib.error
import urllib.parse
import urllib.request


class KeycloakError(RuntimeError):
    pass


class Keycloak:
    def __init__(self, base, realm, client_id, client_secret, group_id):
        self.base = base.rstrip("/")
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.group_id = group_id

    def _http(self, method, url, token=None, body=None, form=None):
        data = None
        headers = {}
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                raw = res.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise KeycloakError(f"Keycloak {e.code}: {detail[:300]}") from e

    def token(self):
        url = f"{self.base}/realms/{self.realm}/protocol/openid-connect/token"
        return self._http("POST", url, form={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        })["access_token"]

    def exchange_code(self, code, redirect_uri):
        url = f"{self.base}/realms/{self.realm}/protocol/openid-connect/token"
        return self._http("POST", url, form={
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        })

    def userinfo(self, access_token):
        url = f"{self.base}/realms/{self.realm}/protocol/openid-connect/userinfo"
        return self._http("GET", url, token=access_token)

    def find_or_create_user(self, token, email):
        q = urllib.parse.urlencode({"email": email, "exact": "true"})
        users = self._http("GET", f"{self.base}/admin/realms/{self.realm}/users?{q}", token=token)
        if users:
            return users[0]["id"], False
        self._http("POST", f"{self.base}/admin/realms/{self.realm}/users", token=token, body={
            "username": email, "email": email, "enabled": True, "emailVerified": False,
            "requiredActions": ["VERIFY_EMAIL", "UPDATE_PASSWORD"]})
        users = self._http("GET", f"{self.base}/admin/realms/{self.realm}/users?{q}", token=token)
        if not users:
            raise KeycloakError("Created user was not found")
        return users[0]["id"], True

    def grant_group(self, token, user_id):
        self._http("PUT", f"{self.base}/admin/realms/{self.realm}/users/{user_id}/groups/{self.group_id}", token=token)

    def grant_group_and_email(self, token, user_id):
        self.grant_group(token, user_id)
        self._http("PUT", f"{self.base}/admin/realms/{self.realm}/users/{user_id}/execute-actions-email",
                   token=token, body=["VERIFY_EMAIL", "UPDATE_PASSWORD"])

    def activate(self, email):
        token = self.token()
        user_id, created = self.find_or_create_user(token, email)
        self.grant_group_and_email(token, user_id)
        return created

    def grant_existing_user(self, user_id):
        self.grant_group(self.token(), user_id)
