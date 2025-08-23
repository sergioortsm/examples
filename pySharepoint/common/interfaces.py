from dataclasses import dataclass, field
from typing import Any, List, Optional, Dict




@dataclass
class RoleDefinition:
    Id: Optional[int] = None
    Name: Optional[str] = None
    Description: Optional[str] = None
    odata_id: Optional[str] = None  # '@odata.id'

@dataclass
class IUser:
    Id: Optional[int] = None
    Title: Optional[str] = None
    Email: Optional[str] = None
    Roles: List[RoleDefinition] = field(default_factory=list)

@dataclass
class IGroup:
    Id: Optional[int] = None
    Title: Optional[str] = None
    Users: List[IUser] = field(default_factory=list)
    Roles: List[RoleDefinition] = field(default_factory=list)

@dataclass
class CurrentChangeToken:
    StringValue: Optional[str] = None

@dataclass
class ImagePath:
    DecodedUrl: Optional[str] = None

@dataclass
class RootFolder:
    ServerRelativeUrl: Optional[str] = None

@dataclass
class IList:
    Id: Optional[str] = None
    Users: List[IUser] = field(default_factory=list)
    Groups: List[IGroup] = field(default_factory=list)
    Roles: List[RoleDefinition] = field(default_factory=list)
    HasRoleUniqueAssigment: Optional[bool] = None
    Template: Optional[Any] = None  # TemplateInfo
    odata_editLink: Optional[str] = None  # '@odata.editLink'
    odata_etag: Optional[str] = None  # '@odata.etag'
    odata_id: Optional[str] = None  # '@odata.id'
    odata_type: Optional[str] = None  # '@odata.type'
    AllowContentTypes: Optional[bool] = None
    BaseTemplate: Optional[int] = None
    BaseType: Optional[int] = None
    ContentTypesEnabled: Optional[bool] = None
    CrawlNonDefaultViews: Optional[bool] = None
    Created: Optional[str] = None
    CurrentChangeToken: Optional[Any] = None # type: ignore
    DefaultContentApprovalWorkflowId: Optional[str] = None
    DefaultItemOpenUseListSetting: Optional[bool] = None
    DefaultSensitivityLabelForLibrary: Optional[str] = None
    Description: Optional[str] = None
    Direction: Optional[str] = None
    DisableCommenting: Optional[bool] = None
    DisableGridEditing: Optional[bool] = None
    DocumentTemplateUrl: Optional[str] = None
    DraftVersionVisibility: Optional[int] = None
    EnableAttachments: Optional[bool] = None
    EnableFolderCreation: Optional[bool] = None
    EnableMinorVersions: Optional[bool] = None
    EnableModeration: Optional[bool] = None
    EnableRequestSignOff: Optional[bool] = None
    EnableVersioning: Optional[bool] = None
    EntityTypeName: Optional[str] = None
    ExemptFromBlockDownloadOfNonViewableFiles: Optional[bool] = None
    FileSavePostProcessingEnabled: Optional[bool] = None
    ForceCheckout: Optional[bool] = None
    HasExternalDataSource: Optional[bool] = None
    Hidden: Optional[bool] = None
    ImagePath: Optional[Any] = None # type: ignore
    ImageUrl: Optional[str] = None
    IrmEnabled: Optional[bool] = None
    IrmExpire: Optional[bool] = None
    IrmReject: Optional[bool] = None
    IsApplicationList: Optional[bool] = None
    IsCatalog: Optional[bool] = None
    IsPrivate: Optional[bool] = None
    ItemCount: Optional[int] = None
    LastItemDeletedDate: Optional[str] = None
    LastItemModifiedDate: Optional[str] = None
    LastItemUserModifiedDate: Optional[str] = None
    ListExperienceOptions: Optional[int] = None
    ListItemEntityTypeFullName: Optional[str] = None
    MajorVersionLimit: Optional[int] = None
    MajorWithMinorVersionsLimit: Optional[int] = None
    MultipleDataList: Optional[bool] = None
    NoCrawl: Optional[bool] = None
    ParentWebPath: Optional[Any] = None # type: ignore
    RootFolder: Optional[Any] = None # type: ignore
    ParentWebUrl: Optional[str] = None
    ParserDisabled: Optional[bool] = None
    SensitivityLabelToEncryptOnDownloadForLibrary: Optional[str] = None
    ServerTemplateCanCreateFolders: Optional[bool] = None
    TemplateFeatureId: Optional[str] = None
    Title: Optional[str] = None

@dataclass
class ISiteCollection:    
    Title:  Optional[str] = None
    Url: Optional[str] = None
    Users: List[IUser] = field(default_factory=list)
    Groups:  List[IGroup] = field(default_factory=list)
    Admins: List[IUser] = field(default_factory=list)
    Views : List[Any] = field(default_factory=list)
    Lists: List[IList] = field(default_factory=list)
    SubSites: List["ISiteCollection"] = field(default_factory=list)
    HasRoleUniqueAssigment: Optional[bool] = False