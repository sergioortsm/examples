from typing import List
from dataclasses import dataclass, field

from common.interfaces import IUser, RoleDefinition

class Mapper:
    @staticmethod
    def to_user(data: dict) -> IUser:
        return IUser(
            Id=data.get("Id"),
            Title=data.get("Title"),
            Email=data.get("Email"),
            IsSiteAdmin=data.get("IsSiteAdmin"),
            # si vinieran roles dentro del json, también los mapearías aquí
            Roles=[]  
        )

    @staticmethod
    def to_users(data: List[dict]) -> List[IUser]:
        return [Mapper.to_user(u) for u in data]

    @staticmethod
    def to_role(data: dict) -> RoleDefinition:
        return RoleDefinition(
            Id=data.get("Id"),
            Name=data.get("Name"),
            Description=data.get("Description"),
            odata_id=data.get("@odata.id")
        )
