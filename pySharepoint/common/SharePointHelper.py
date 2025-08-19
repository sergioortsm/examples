import asyncio
from datetime import datetime, timedelta
import os
import json
import time
from typing import List, Dict, Any, Optional
from sharepoint_client import SharePointOnlineClient

CACHE_FILE = "site_data_cache.json"

class Utils:
    @staticmethod
    def comparar_por_title(item):
        return item["Title"].lower()

class SharePointHelper:
    def __init__(self, sp_client: SharePointOnlineClient, cache):
        self.sp = sp_client
        self.cache = cache
        self.config = {
            "titlesite": "DefaultSite",
            "urlsite": "https://sortsactivedev.sharepoint.com/sites/prueba"
        }
        
        self._load_cache()

    # -------------------- Cache --------------------
    def _cache_get(self, key):
        item = self.cache.get(key)
        if item and item["expires"] > datetime.utcnow():
            return item["value"]
        return None

    def _cache_put(self, key, value, minutes=60):
        self.cache[key] = {
            "value": value,
            "expires": datetime.utcnow() + timedelta(minutes=minutes)
        }

    def _load_cache(self):
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                try:
                    self.cache = json.load(f)
                except json.JSONDecodeError:
                    self.cache = {}
        else:
            self.cache = {}

    def _save_cache(self):
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def _is_cache_valid(self, entry: Dict[str, Any]) -> bool:
   
        expires_on = entry.get("expires_on")
        if expires_on is None or not isinstance(expires_on, (int, float)):
            return False

        data = entry.get("data")
        
        if not data:  # [] o None → inválido
            return False

        return expires_on > time.time()

    async def has_unique_role_assignments(self, site: dict, lista: Optional[dict] = None) -> bool:
 
        if lista:
            url = f"{site['Url']}/_api/web/getList('{lista['RootFolder']['ServerRelativeUrl']}')/HasUniqueRoleAssignments"
        else:
            url = f"{site['Url']}/_api/web/HasUniqueRoleAssignments"

        response = self.sp.get(url)
        
        if response:
            return response["value"]
        else:
            return False
        
    async def obtener_datos_site(self, site: Dict[str, str], es_subsite: bool) -> List[Dict[str, Any]]:
        """
        site: {'key': site_url, 'text': display_name}
        es_subsite: True si es subsite, False si es root site
        """
        cache_key = f"mynet_Datos_{site["key"]}"
        site_collections: List[Dict[str, Any]] = []

        # revisar cache
        datos_temp = self.cache.get(cache_key)
        if datos_temp and self._is_cache_valid(datos_temp):
            return sorted(datos_temp["data"], key=Utils.comparar_por_title)

        # construir API URL
        if es_subsite:
            api_url = (
                f"{site['key']}/_api/search/query?"
                "querytext='contentclass:STS_Web'&"
                "selectproperties='Path,Url,Title'&"
                f"refinementfilters='Path:equals(\"{site['key']}\")'&"
                "refiners='Path'&startrow=0&rowlimit=1000"
            )
        else:
            api_url = (
                f"{site['key']}/_api/search/query?"
                "querytext='(contentclass:STS_Site OR contentclass:STS_Web OR contentclass:STS_TeamSite)'&"
                "selectproperties='Path,Url,Title'&"
                f"refinementfilters='Path:equals(\"{site['key']}\")'&"
                "refiners='Path'&startrow=0&rowlimit=1000"
            )

        try:
            data = self.sp.get(api_url)
            rows = data.get("PrimaryQueryResult", {}).get("RelevantResults", {}).get("Table", {}).get("Rows", [])

            for row in rows:
                cells = {cell["Key"]: cell["Value"] for cell in row["Cells"]}
                if site["text"] == cells.get("Title", ""):
                    site_collections.append({
                        "Title": cells.get("Title", ""),
                        "Url": cells.get("Path", ""),
                        "Admins": [],
                        "Users": [],
                        "Views": [],
                        "HasUniqueRoleAssignments": True
                    })
                else:
                    site_collections.append({
                        "Title": "",
                        "Url": "",
                        "Admins": [],
                        "Users": [],
                        "Views": [],
                        "HasUniqueRoleAssignments": False
                    })

            # filtrar solo los sites válidos
            site_collections = [s for s in site_collections if s["Title"] != ""]

            # guardar cache por 1 hora
            self.cache[cache_key] = {
                "data": site_collections,
                "expires_on": time.time() + 3600
            }
            self._save_cache()

        except Exception as e:
            print("Error al obtener datos de SharePoint:", e)

        return sorted(site_collections, key=Utils.comparar_por_title)

    async def obtener_datos_subsites(self, sites):
            sub_sites_all = []

            # Si sites está vacío → añadir uno por defecto
            if not sites:
                sites.append({
                    "Title": self.config["titlesite"],
                    "Url": self.config["urlsite"],
                    "Admins": [],
                    "Users": [],
                    "Views": []
                })

            updated_sites = []

            for site in sites:
                key_cache = f"mynet_Datos_SubSites_{site['Url']}"
                cached = self._cache_get(key_cache)

                if cached:
                    updated_sites.append(cached)
                    continue

                api_url = (
                    f"{site['Url']}/_api/search/query"
                    f"?querytext='contentclass:STS_Web'"
                    f"&selectproperties='Path,Url,Title'"
                    f"&refiners='Path'"
                    f"&refinementfilters='Path:equals(\"{site['Url']}*\")'"
                    f"&startrow=0&rowlimit=1000"
                )

                try:
                    response = self.sp.get(api_url)  # tu cliente SP ya autenticado
                    data = response
                    rows = data["PrimaryQueryResult"]["RelevantResults"]["Table"]["Rows"]

                    sub_sites = []
                    for row in rows:
                        cells = {cell["Key"]: cell["Value"] for cell in row["Cells"]}
                        title = cells.get("Title", "")
                        url = cells.get("Path", "")
                        if title:
                            sub_sites.append({
                                "Title": title,
                                "Url": url,
                                "Admins": [],
                                "Users": [],
                                "Views": []
                            })

                    uniquerole = await self.has_unique_role_assignments(site,None)

                    updated_site = {
                        **site,
                        "HasUniqueRoleAssignments": uniquerole,
                        "SubSites": sub_sites
                    }

                    # Guardar en cache 1 hora
                    self._cache_put(key_cache, updated_site, minutes=60)

                    updated_sites.append(updated_site)

                except Exception as e:
                    print(f"Error en {site['Url']}: {e}")

            # Filtrar subsites (simulación de filterSubsitesByDepth)
            updated_sites_final = [
                s for s in updated_sites if s.get("SubSites")
            ]

            if updated_sites_final:
                # Simulación de sort por Title
                updated_sites_final.sort(key=lambda s: s["Title"])
                return updated_sites_final
            else:
                return sites
    
    async def obtener_definiciones_roles(self, site_key):
        cache_key = f"Roles_{site_key}"
        apiUrl = f"{site_key}/_api/web/roledefinitions"
        roles = self.cache.get(cache_key)
        
        if roles: 
            return roles
        else:
            data = self.sp.get(apiUrl)
            
            if data and self._is_cache_valid(data):
                roles = data.get("d", {}).get("results", [])
                self.cache[cache_key] = {
                    "data": roles,
                    "expires_on": time.time() + 3600
                }
                
                self._save_cache()
      
        return roles
    
    async def fetch_administrators(self, site_url: str) -> List[Dict[str, Any]]:
        return [{"Title": "Admin1"}, {"Title": "Admin2"}]

    async def fetch_lists(self, site_url: str, site: dict) -> List[Dict[str, Any]]:
        return [{"Title": "List1"}, {"Title": "List2"}]    
    
    async def fetch_admin_data(self, site_url: str):

        admin_url = f"{site_url}/_api/web/roleassignments?$expand=Member/users,RoleDefinitionBindings"

        response = self.sp.get(admin_url) 
        
        if response:
            response["data"] = response.get("d", {}).get("results", [])
        else:      
            raise Exception(f"Failed to fetch admin data for {site_url}: {response}")

        admin_data = response
        # Equivalente a tu ObterDatosArray(adminData.value)
        return admin_data.get("d", {}).get("results", [])
    
    async def rellenar_objetos_sites(self, sites: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

        async def procesar_site(site: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            # Comprobar cache primero
            site_data = self.cache.get(f"mynet_Objetos_Sites_{site['Url']}")
            if site_data:
                return site_data  # suponer que flattenArray ya se aplica si hace falta

            try:
                admin_data = await self.fetch_admin_data(site["Url"])
                site_users = sorted(admin_data["Users"], key=lambda u: u["Title"])
                site_groups = sorted(admin_data["Groups"], key=lambda g: g["Title"])
                administrators = await self.fetch_administrators(site["Url"])
                lists = await self.fetch_lists(site["Url"], site)
                unique_roles = await self.has_unique_role_assignments(site)

                updated_site = {
                    **site,
                    "Admins": administrators,
                    "Groups": site_groups,
                    "Users": site_users,
                    "Lists": lists,
                    "HasUniqueRoleAssignments": unique_roles
                }

                # Guardar en cache
                self.cache[f"mynet_Objetos_Sites_{site['Url']}"] = updated_site
                return updated_site
            except Exception as e:
                print(f"Error procesando site {site['Url']}: {e}")
                return None

        # Crear tareas async para todos los sites
        tasks = [procesar_site(s) for s in sites]

        # asyncio.gather con return_exceptions=True equivale a Promise.allSettled
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filtrar errores y None
        updated_sites = [r for r in results if isinstance(r, dict)]

        # Ordenar si hay resultados, o devolver la lista original
        if updated_sites:
            updated_sites.sort(key=lambda s: s.get("Title", ""))
            return updated_sites
        return sites
            
