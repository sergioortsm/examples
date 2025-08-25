import msal
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

# ----------------------
# CONFIGURACIÓN
# ----------------------
TENANT_ID = "a272015e-e187-4c3c-95a6-93cfdba816b8"
CLIENT_ID = "0ee25780-948d-4e07-bccf-5457e16d705f"
CERT_PFX_PATH = r"C:\repositorio\examples\pySharepoint\certificado\MiAppSharePointPython.pfx"
CERT_PFX_PASSWORD = b"MiPasswordSegura123"  # como bytes
CERT_THUMBPRINT = "A2C0322C559E3D70C69FB96A27C76479E7EF22C9"
SPO_SITE_ROOT = "https://sortsactivedev.sharepoint.com"
SPO_SITE = "https://sortsactivedev.sharepoint.com/SITES/PRUEBA"
# ----------------------
# CONVERTIR PFX A PEM
# ----------------------
with open(CERT_PFX_PATH, "rb") as f:
    pfx_data = f.read()

private_key, cert, additional_certs = load_key_and_certificates(
    pfx_data, CERT_PFX_PASSWORD, backend=default_backend()
)

# Clave privada en PEM
pem_private_key = private_key.private_bytes( # type: ignore
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

# Certificado en PEM (opcional, MSAL solo necesita clave privada + thumbprint)
pem_cert = cert.public_bytes(serialization.Encoding.PEM) # type: ignore

# ----------------------
# INICIALIZAR MSAL
# ----------------------
app = msal.ConfidentialClientApplication(
    client_id=CLIENT_ID,
    authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    client_credential={
        "private_key": pem_private_key.decode("utf-8"),
        "thumbprint": CERT_THUMBPRINT
    }
)

# ----------------------
# OBTENER TOKEN APP-ONLY
# ----------------------
scope = [f"https://{SPO_SITE_ROOT.split('//')[1]}/.default"]
token_response = app.acquire_token_for_client(scopes=scope)

if "access_token" not in token_response: # type: ignore
    print("Error al obtener token:", token_response)
    exit(1)

access_token = token_response["access_token"] # type: ignore

# ----------------------
# CONSULTA SEARCH
# ----------------------
search_query = "(contentclass:STS_Site OR contentclass:STS_Web OR contentclass:STS_TeamSite)"
refinement_filter = 'Path:equals("https://sortsactivedev.sharepoint.com/sites/prueba")'
select_properties = "Path,Url,Title"

url = f"{SPO_SITE_ROOT}/_api/search/query?querytext='{search_query}'&selectproperties='{select_properties}'&refinementfilters='{refinement_filter}'&startrow=0&rowlimit=1000"

headers = {
    "Authorization": f"Bearer {access_token}",
    "Accept": "application/json;odata=nometadata"
}

response = requests.get(url, headers=headers)

# ----------------------
# RESULTADOS
# ----------------------
print("Status code:", response.status_code)
try:
    data = response.json()
    for result in data.get("PrimaryQueryResult", {}).get("RelevantResults", {}).get("Table", {}).get("Rows", []):
        item = {c["Key"]: c["Value"] for c in result["Cells"]}
        print(item)
except Exception as e:
    print("Error parseando JSON:", e)
    print(response.text)


print("######################################################################################################")

# ----------------------
# CONSULTA SITE
# ----------------------
#r = requests.get(f"{SPO_SITE_ROOT}/_api/web?$select=Title", headers=headers)
r = requests.get(f"{SPO_SITE}/_api/web/roleassignments?$expand=Member/users,RoleDefinitionBindings", headers=headers)

print(r.status_code, r.json())


