import asyncio
from datetime import datetime, timedelta
import os
import json
import time
from typing import List, Dict, Any, Optional, cast
from common.interfaces import IGroup, IList, ISiteCollection, IUser, RoleDefinition
from common.template_info import list_template
from sharepoint_client import SharePointOnlineClient
from dacite import from_dict, Config
from dataclasses import asdict

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
        
    async def obtener_datos_site(self, site: Dict[str, str], es_subsite: bool) -> List[ISiteCollection]:
        cache_key = f"mynet_Datos_{site['key']}"
        site_collections: List[ISiteCollection] = []

        datos_temp = self.cache.get(cache_key)
        if datos_temp and self._is_cache_valid(datos_temp):
            return sorted(datos_temp["data"], key=lambda s: s.get("Title") or "") # type: ignore

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
                    site_collections.append(ISiteCollection(
                        Title=cells.get("Title", ""),
                        Url=cells.get("Path", ""),
                        Admins=[],
                        Users=[],
                        Views=[],
                        HasRoleUniqueAssigment=True
                    ))
                else:
                    site_collections.append(ISiteCollection(
                        Title="",
                        Url="",
                        Admins=[],
                        Users=[],
                        Views=[],
                        HasRoleUniqueAssigment=False
                    ))

            site_collections = [s for s in site_collections if s.Title]  # descartar vacíos

            self.cache[cache_key] = {
                "data":  [asdict(s) for s in site_collections],
                "expires_on": time.time() + 3600
            }
            self._save_cache()

        except Exception as e:
            print("Error al obtener datos de SharePoint:", e)

        return sorted(site_collections, key=lambda s: s.Title or "")

    async def obtener_datos_subsites(self, sites: List[ISiteCollection]) -> List[ISiteCollection]:

        # Si sites está vacío → añadir uno por defecto
        if not sites:
            sites.append(
                ISiteCollection(
                    Title=self.config["titlesite"],
                    Url=self.config["urlsite"],
                    Admins=[],
                    Users=[],
                    Groups=[],
                    Lists=[],
                    SubSites=[],
                    Views=[],
                    HasRoleUniqueAssigment=False
                )
            )

        updated_sites: List[ISiteCollection] = []

        for site in sites:
            key_cache = f"mynet_Datos_SubSites_{site.Url}"
            cached: Optional[ISiteCollection] = self._cache_get(key_cache)

            if cached:
                updated_sites.append(cached)
                continue

            api_url = (
                f"{site.Url}/_api/search/query"
                f"?querytext='contentclass:STS_Web'"
                f"&selectproperties='Path,Url,Title'"
                f"&refiners='Path'"
                f"&refinementfilters='Path:equals(\"{site.Url}*\")'"
                f"&startrow=0&rowlimit=1000"
            )

            try:
                response = self.sp.get(api_url)  # tu cliente SP ya autenticado
                data = response
                rows = data["PrimaryQueryResult"]["RelevantResults"]["Table"]["Rows"]

                sub_sites: List[ISiteCollection] = []
                for row in rows:
                    cells = {cell["Key"]: cell["Value"] for cell in row["Cells"]}
                    title = cells.get("Title", "")
                    url = cells.get("Path", "")

                    if title:
                        sub_sites.append(
                            ISiteCollection(
                                Title=title,
                                Url=url,
                                Admins=[],
                                Users=[],
                                Groups=[],
                                Lists=[],
                                SubSites=[],
                                Views=[],
                                HasRoleUniqueAssigment=False
                            )
                        )

                # Llamada a método async que devuelve bool
                uniquerole = await self.has_unique_role_assignments(site, None)  # type: ignore

                # Actualizar site con los subsites y unique role
                updated_site = ISiteCollection(
                    Title=site.Title,
                    Url=site.Url,
                    Admins=site.Admins,
                    Users=site.Users,
                    Groups=site.Groups,
                    Lists=site.Lists,
                    Views=site.Views,
                    SubSites=sub_sites,
                    HasRoleUniqueAssigment=uniquerole,
                )

                # Guardar en cache 1 hora
                self._cache_put(key_cache, updated_site, minutes=60)

                updated_sites.append(updated_site)

            except Exception as e:
                print(f"Error en {site.Url}: {e}")

        # Filtrar subsites (simulación de filterSubsitesByDepth)
        updated_sites_final = [s for s in updated_sites if s.SubSites]

        if updated_sites_final:
            updated_sites_final.sort(key=lambda s: s.Title or "")
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
    
    async def fetch_administrators(self, site_url: str):
        
        admin_url = f"{site_url}/_api/web/siteusers?filter=IsSiteAdmin eq true"
        response = self.sp.get(admin_url)    
        
        if response:
            return response.get("value", [])
        else:      
            raise Exception(f"Failed to fetch administrators data for {site_url}: {response}")

    async def fetch_lists(self, site_url: str, site_collection: dict) -> List[IList]:
        # URL para traer listas visibles con ciertos templates
        list_url = (
            f"{site_url}/_api/Web/Lists/"
            "?$filter=Hidden eq false and (BaseTemplate eq 100 or BaseTemplate eq 101 or BaseTemplate eq 106 or BaseTemplate eq 119)"
            "&$select=*,RootFolder/ServerRelativeUrl&$expand=RootFolder"
        )

        # Llamada a SharePoint
        list_data = self.sp.get(list_url)
        listas_temp = list_data.get("value", [])

        # Función interna para procesar cada lista
        async def process_lista(lista_dict):
            try:
                # URL para roles
                list_roles_url = f"{site_url}/_api/web/getList('{lista_dict['RootFolder']['ServerRelativeUrl']}')/roleassignments?$expand=Member/Users,RoleDefinitionBindings"
                roles_data = self.sp.get(list_roles_url)
                roles_items = roles_data.get("value", [])

                # Convertir roles a objetos Python usando tu método obtener_datos_array
                result = self.obtener_datos_array(roles_items)

                # Filtrar usuarios según roles
                users_lista = [
                    user for user in sorted(result["Users"], key=lambda u: u.Title) # type: ignore
                    if any(
                        role.Name.lower() not in ["limited", "limitededit", "limitado"]
                        for role in user.Roles # type: ignore
                    )
                ]
                groups = sorted(result["Groups"], key=lambda g: g.Title) # type: ignore

                # Agregar campos calculados
                lista_dict.update({
                    "Users": users_lista,
                    "Groups": groups,
                    "Roles": [],
                    "Template": list_template.get_template_info_by_id(lista_dict.get("BaseTemplate")),
                    "HasRoleUniqueAssigment": await self.has_unique_role_assignments(site_collection, lista_dict),
                })

                # Convertir diccionario a IList tipado
                lista_obj = from_dict(
                    data_class=IList,
                    data=lista_dict,
                    config=Config(strict=False)
                )
                return lista_obj
            except Exception as e:
                print(f"Error procesando lista {lista_dict.get('Title')}: {e}")
                return None

        # Ejecutar todas las listas en paralelo
        tasks = [process_lista(l) for l in listas_temp]
        listas2 = await asyncio.gather(*tasks)

        # Filtrar None y devolver solo listas válidas
        return [l for l in listas2 if l]


    # ---- Métodos auxiliares a implementar ----    
    def obtener_datos_array(self, original_array: List[dict]) -> dict:
        # Método que ya definimos antes
        result = {"Groups": [], "Users": []}
        for item in original_array:
            member = item.get("Member", {})
            if member.get("PrincipalType") == 8 and not any(
                s.lower() in member.get("Title", "").lower() for s in ["limited", "limitado", "sharinglinks"]
            ):
                group = IGroup(
                    Id=member.get("Id"),
                    Title=member.get("Title"),
                    Users=[IUser(Id=u.get("Id"), Title=u.get("Title"), Email=u.get("Email")) for u in member.get("Users", [])],
                    Roles=[RoleDefinition(Id=r.get("Id"), Name=r.get("Name"), Description=r.get("Description"), odata_id=r.get("@odata.id")) for r in item.get("RoleDefinitionBindings", [])]
                )
                result["Groups"].append(group)
            elif member.get("PrincipalType") == 1:
                user = IUser(
                    Id=member.get("Id"),
                    Title=member.get("Title"),
                    Email=member.get("UserPrincipalName", ""),
                    Roles=[RoleDefinition(Id=r.get("Id"), Name=r.get("Name"), Description=r.get("Description"), odata_id=r.get("@odata.id")) for r in item.get("RoleDefinitionBindings", [])]
                )
                result["Users"].append(user)
        return result
    
    def mapear_propiedades_lista(self, lista: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError()

    def get_template_info_by_id(self, base_template: int) -> Dict[str, Any]:
        raise list_template.get_template_info_by_id(base_template)  # type: ignore
    
    # ---------------------------------------------    
    
    async def fetch_admin_data(self, site_url: str | None):

        admin_url = f"{site_url}/_api/web/roleassignments?$expand=Member/users,RoleDefinitionBindings"
        response = self.sp.get(admin_url)    
        
        if response:
            return response.get("value", [])
        else:      
            raise Exception(f"Failed to fetch admin data for {site_url}: {response}")
    
    async def rellenar_objetos_sites(self, sites: List[ISiteCollection]) -> List[ISiteCollection]:

        async def procesar_site(site: ISiteCollection) -> Optional[ISiteCollection]:
            # Comprobar cache primero
            site_data: Optional[ISiteCollection] = self.cache.get(f"mynet_Objetos_Sites_{site.Url}")
            if site_data:
                return site_data

            try:
                admin_data = await self.fetch_admin_data(site.Url)

                # --- Usuarios (PrincipalType = 1) ---
                users = []
                for item in admin_data:
                    member = item.get("Member", {})
                    users_data = member.get("Users", [])
                    if isinstance(users_data, dict):
                        users_data = [users_data]
                    for u in users_data:
                        if str(u.get("PrincipalType")) == "1":
                            users.append(u)
                site_users = sorted(users, key=lambda u: u.get("Title", "")) if users else []

                # --- Grupos (PrincipalType = 4) ---
                groups = []
                for item in admin_data:
                    member = item.get("Member", {})
                    users_data = member.get("Users", [])
                    if isinstance(users_data, dict):
                        users_data = [users_data]
                    for u in users_data:
                        if str(u.get("PrincipalType")) == "4":
                            groups.append(u)
                site_groups = sorted(groups, key=lambda g: g.get("Title", "")) if groups else []

                # --- Otros datos ---
                administrators = await self.fetch_administrators(site.Url) # pyright: ignore[reportArgumentType]
                lists = await self.fetch_lists(site.Url, site) # type: ignore
                unique_roles = await self.has_unique_role_assignments(site)  # type: ignore

                # Crear un nuevo objeto ISiteCollection actualizado
                updated_site = ISiteCollection(
                    Title=site.Title,
                    Url=site.Url,
                    Admins=administrators,
                    Groups=site_groups,
                    Users=site_users,
                    Lists=lists,
                    Views=site.Views,
                    SubSites=site.SubSites,
                    HasRoleUniqueAssigment=unique_roles
                )

                # Guardar en cache
                self.cache[f"mynet_Objetos_Sites_{site.Url}"] = updated_site
                return updated_site

            except Exception as e:
                print(f"Error procesando site {site.Url}: {e}")
                return None

        # Crear tareas async para todos los sites
        tasks = [procesar_site(s) for s in sites]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filtrar errores y None
        updated_sites: List[ISiteCollection] = [
            r for r in results if isinstance(r, ISiteCollection) and r is not None
        ]
        errors = [r for r in results if isinstance(r, Exception)]

        if updated_sites:
            updated_sites.sort(key=lambda s: s.Title or "")
            return updated_sites

        return sites
            
