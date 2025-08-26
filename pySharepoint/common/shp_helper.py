import asyncio
from typing import List, Dict, Any, Optional
from common.interfaces import IGroup, IList, ISiteCollection, IUser, RoleDefinition
from common.template_info import list_template
from common.sharepoint_client import sharepoint_client
from dacite import from_dict, Config
from dataclasses import asdict
from diskcache import Cache


class shp_helper:
    def __init__(self, sp_client: sharepoint_client, store, cache: Cache): # type: ignore
        self.sp = sp_client
        self.cache = cache
        self.config = {
            "titlesite": "DefaultSite",
            "urlsite": "https://sortsactivedev.sharepoint.com"
        }
        self.store = store


    # -----------------------------
    # Funciones de carga de sites
    # -----------------------------
    
    def _replace_site_in_tree(self,
        sites: list[ISiteCollection],
        new_site: ISiteCollection
    ) -> list[ISiteCollection]:
        """
        Busca recursivamente un ISiteCollection por URL y lo sustituye
        con los datos de new_site.
        """
        replaced_sites: list[ISiteCollection] = []
        for site in sites:
            if site.Url == new_site.Url:
                # Sustituimos el nodo entero
                replaced_sites.append(new_site)
            else:
                # Recorremos los subsites recursivamente
                if site.SubSites:
                    site.SubSites = self._replace_site_in_tree(site.SubSites, new_site)
                replaced_sites.append(site)
        return replaced_sites
    
    async def cargar_datos_sites(self) -> List[ISiteCollection]:
            site: ISiteCollection = self.store.site_selected or ISiteCollection(Title="", Url="")
            subsite: ISiteCollection = self.store.subsite_selected or ISiteCollection(Title="", Url="")
            datos_sites: List[ISiteCollection] = []
                
            if site is None or site.Url == "":
                self.store.set_loading(False)
                return []
            
            self.store.set_loading(True)
            
            if site.Url and not subsite.Url:
                datos_sites_temp = await self.store.helper.obtener_datos_site(site, es_subsite=False)
                datos_sites = await self.store.helper.obtener_datos_subsites(datos_sites_temp)
                datos_sites = await self.store.helper.rellenar_objetos_sites(datos_sites)
                self.store.set_roles_definiciones(await self.store.helper.map2dropdown_option_tooltips(site) or [])
            elif subsite.Url:
                datos_sites = await self.store.helper.rellenar_objetos_sites([subsite]) 
                self.store.set_roles_definiciones(await self.store.helper.map2dropdown_option_tooltips(subsite) or [])
            
            self.store.set_loading(False)
            
            return datos_sites        

    # -------------------- Cache --------------------
    def _cache_get(self, key):
        return self.cache.get(key, default=None)

    def _cache_put(self, key, value, expire_seconds=3600):
        self.cache.set(key, value, expire=expire_seconds)

    # -------------------- SharePoint helpers --------------------
    
    def update_group(self, group: IGroup):
        if not group or not group.Id:
            raise ValueError("Group or Group ID is None")

        api_url = f"{self.sp.site_url}/_api/web/sitegroups({group.Id})"
        headers = {
            "Accept": "application/json;odata=verbose",
            "Content-Type": "application/json;odata=verbose",
            "IF-MATCH": "*",
            "X-HTTP-Method": "MERGE"
        }
        body = {
            "Title": group.Title
        }

        response = self.sp.post(api_url)
         
        if response is None:
            raise Exception(f"Failed to update group {group.Id}: No response")
               
        return response.get("value", False) if response else False
       
    async def has_unique_role_assignments(self, site: ISiteCollection, lista: Optional[dict] = None) -> bool:
        if lista:
            url = f"{site.Url}/_api/web/getList('{lista['RootFolder']['ServerRelativeUrl']}')/HasUniqueRoleAssignments"
        else:
            url = f"{site.Url}/_api/web/HasUniqueRoleAssignments"

        response = self.sp.get(url)
        return response.get("value", False) if response else False

    async def obtener_datos_site(self, site:ISiteCollection, es_subsite: bool) -> List[ISiteCollection]:
        cache_key = f"mynet_Datos_{site.Url}"
        cached = self._cache_get(cache_key)
        
        if cached and isinstance(cached, list):
            return [s for s in cached if isinstance(s, ISiteCollection)]

        api_url = (
            f"{site.Url}/_api/search/query?"
            + ("querytext='contentclass:STS_Web'" if es_subsite else "querytext='(contentclass:STS_Site OR contentclass:STS_Web OR contentclass:STS_TeamSite)'")
            + "&selectproperties='Path,Url,Title'"
            + f"&refinementfilters='Path:equals(\"{site.Url}\")'"
            + "&refiners='Path'&startrow=0&rowlimit=1000"
        )

        try:
            data = self.sp.get(api_url)
            rows = data.get("PrimaryQueryResult", {}).get("RelevantResults", {}).get("Table", {}).get("Rows", [])

            site_collections: List[ISiteCollection] = []
            for row in rows:
                cells = {cell["Key"]: cell["Value"] for cell in row["Cells"]}
                if site.Title == cells.get("Title", ""):
                    site_collections.append(ISiteCollection(
                        Title=cells.get("Title", ""),
                        Url=cells.get("Path", ""),
                        Admins=[],
                        Users=[],
                        Views=[],
                        HasRoleUniqueAssigment=True
                    ))

            self._cache_put(cache_key, site_collections)
            return site_collections
        except Exception as e:
            print("Error al obtener datos de SharePoint:", e)
            return []

    async def obtener_datos_subsites(self, sites: List[ISiteCollection]) -> List[ISiteCollection]:
        if not sites:
            sites.append(ISiteCollection(
                Title=self.config["titlesite"],
                Url=self.config["urlsite"],
                Admins=[], Users=[], Groups=[], Lists=[], SubSites=[], Views=[],
                HasRoleUniqueAssigment=False
            ))

        updated_sites: List[ISiteCollection] = []
        for site in sites:
            key_cache = f"mynet_Datos_SubSites_{site.Url}"
            cached = self._cache_get(key_cache)
            if cached and isinstance(cached, list):
                return [s for s in cached if isinstance(s, ISiteCollection)]

            api_url = (
                f"{site.Url}/_api/search/query"
                f"?querytext='contentclass:STS_Web'"
                f"&selectproperties='Path,Url,Title'"
                f"&refiners='Path'"
                f"&refinementfilters='Path:equals(\"{site.Url}*\")'"
                f"&startrow=0&rowlimit=1000"
            )

            try:
                response = self.sp.get(api_url)
                rows = response["PrimaryQueryResult"]["RelevantResults"]["Table"]["Rows"]

                sub_sites: List[ISiteCollection] = []
                for row in rows:
                    cells = {cell["Key"]: cell["Value"] for cell in row["Cells"]}
                    title = cells.get("Title", "")
                    url = cells.get("Path", "")
                    if title:
                        sub_sites.append(ISiteCollection(
                            Title=title,
                            Url=url,
                            Admins=[],
                            Users=[],
                            Groups=[],
                            Lists=[],
                            SubSites=[],
                            Views=[],
                            HasRoleUniqueAssigment=False
                        ))

                uniquerole = await self.has_unique_role_assignments(site, None)
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

                self._cache_put(key_cache, updated_site)
                updated_sites.append(updated_site)
            except Exception as e:
                print(f"Error en {site.Url}: {e}")

        return [s for s in updated_sites if s.SubSites] or sites

    async def fetch_administrators(self, site_url: str):
        admin_url = f"{site_url}/_api/web/siteusers?filter=IsSiteAdmin eq true"
        response = self.sp.get(admin_url)
        if response:
            users = response.get("value", [])  
            admins = [
                user for user in users
                if user.get("IsSiteAdmin") and user.get("UserPrincipalName")
            ]
            admins_sorted = sorted(admins, key=lambda u: u.get("Title", ""))
            return admins_sorted
        else:
            raise Exception(f"Failed to fetch administrators data for {site_url}: {response}")

    async def map2dropdown_option_tooltips(self, site:ISiteCollection) -> List[Dict[str, Any]]:
        
        roles = await self.obtener_definiciones_roles(site)
            
        # Filtrar roles
        filtered_roles = [
            role for role in roles
            if not any(substr in role.get("Name", "").lower()
                    for substr in ["limited", "limitededit", "limitado"])
        ]

        # Mapear a opciones de dropdown con tooltip
        options: List[Dict[str, Any]] = [
            {
                "key": role.get("Id"),
                "text": role.get("Name"),
                "data": {"tooltip": role.get("Description", "")}
            }
            for role in filtered_roles
        ]

        return options
    
    async def obtener_definiciones_roles(self, sitegrupo: ISiteCollection) -> List[Dict[str, Any]]:
        api_url = f"{sitegrupo.Url}/_api/web/roledefinitions"
        cache_key = f"mynet_Roles_Def_{sitegrupo.Url}"

        # cache.get es síncrono → sin await
        cached = self.cache.get(cache_key)
        rows: List[Dict[str, Any]] = cached if isinstance(cached, list) else []

        if not rows:
            try:
                # sp.get es asíncrono → con await
                response: Dict[str, Any] =  self.sp.get(api_url)

                if isinstance(response, dict) and "value" in response:
                    rows = response["value"]

                    # cache.set también suele ser síncrono
                    self.cache.set(cache_key, rows, expire=3600)
                else:
                    print(f"Error: respuesta inválida en {api_url}")

            except Exception as e:
                print(f"Error obteniendo definiciones de roles: {e}")

        return rows
    
    async def fetch_lists(self, site_url: str, site_collection: ISiteCollection) -> List[IList]:
        list_url = (
            f"{site_url}/_api/Web/Lists/"
            "?$filter=Hidden eq false and (BaseTemplate eq 100 or BaseTemplate eq 101 or BaseTemplate eq 106 or BaseTemplate eq 119)"
            "&$select=*,RootFolder/ServerRelativeUrl&$expand=RootFolder"
        )
        list_data = self.sp.get(list_url)
        listas_temp = list_data.get("value", [])

        async def process_lista(lista_dict):
            try:
                list_roles_url = f"{site_url}/_api/web/getList('{lista_dict['RootFolder']['ServerRelativeUrl']}')/roleassignments?$expand=Member/Users,RoleDefinitionBindings"
                roles_data = self.sp.get(list_roles_url)
                result = self.obtener_datos_array(roles_data.get("value", []))

                # Filtrar usuarios según roles
                users_lista = [
                    user for user in sorted(result["Users"], key=lambda u: u.Title)
                    if any(
                        role.Name.lower() not in ["limited", "limitededit", "limitado"]
                        for role in user.Roles
                    )
                ]
                groups = sorted(result["Groups"], key=lambda g: g.Title)

                # Completar la lista con los datos procesados
                lista_dict.update({
                    "Users": users_lista,
                    "Groups": groups,
                    "Roles": [],
                    "Template": list_template.get_template_info_by_id(lista_dict.get("BaseTemplate")),
                    "HasRoleUniqueAssigment": await self.has_unique_role_assignments(site_collection, lista_dict),
                })

                return from_dict(IList, lista_dict, config=Config(strict=False))
            except Exception as e:
                print(f"Error procesando lista {lista_dict.get('Title')}: {e}")
                return None

        tasks = [process_lista(l) for l in listas_temp]
        listas2 = await asyncio.gather(*tasks)
        
        return [l for l in listas2 if l]

    def obtener_datos_array(self, original_array: List[dict]) -> dict:
        result = {"Groups": [], "Users": []}
        for item in original_array:
            member = item.get("Member", {})
            if member.get("PrincipalType") == 8 and not any(s.lower() in member.get("Title", "").lower() for s in ["limited", "limitado", "sharinglinks"]):
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

    async def rellenar_objetos_sites(self, sites: List[ISiteCollection]) -> List[ISiteCollection]:
        async def procesar_site(site: ISiteCollection) -> Optional[ISiteCollection]:
            
            cached = self._cache_get(f"mynet_Objetos_Sites_{site.Url}")
            
            if cached is not None:
                if isinstance(cached, ISiteCollection):
                    return cached
                else:
                    return None
            try:
                    
                admin_data = await self.fetch_admin_data(site.Url)

                users = [u for item in admin_data for u in (item.get("Member", {}).get("Users") or []) if str(u.get("PrincipalType")) == "1"]
                users = sorted(users, key=lambda u: u.get("Title", ""))

                groups = [u for item in admin_data for u in (item.get("Member", {}).get("Users") or []) if str(u.get("PrincipalType")) == "4"]
                groups = sorted(groups, key=lambda u: u.get("Title", ""))

                administrators = await self.fetch_administrators(site.Url or "")
                lists = await self.fetch_lists(site.Url or "", site)
                unique_roles = await self.has_unique_role_assignments(site)

                updated_site = ISiteCollection(
                    Title=site.Title,
                    Url=site.Url,
                    Admins=administrators,
                    Groups=groups,
                    Users=users,
                    Lists=lists,
                    Views=site.Views,
                    SubSites=site.SubSites,
                    HasRoleUniqueAssigment=unique_roles
                )
                self._cache_put(f"mynet_Objetos_Sites_{site.Url}", updated_site)
                return updated_site
            except Exception as e:
                print(f"Error procesando site {site.Url}: {e}")
                return None

        tasks = [procesar_site(s) for s in sites]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        updated_sites = [r for r in results if isinstance(r, ISiteCollection)]
        return sorted(updated_sites, key=lambda s: s.Title or "") if updated_sites else sites

    async def fetch_admin_data(self, site_url: str | None):

        admin_url = f"{site_url}/_api/web/roleassignments?$expand=Member/users,RoleDefinitionBindings"
        response = self.sp.get(admin_url)    
        
        if response:
            return response.get("value", [])
        else:      
            raise Exception(f"Failed to fetch admin data for {site_url}: {response}")
        
       