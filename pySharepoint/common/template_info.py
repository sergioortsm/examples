from dataclasses import dataclass
from typing import Optional, List, Dict

@dataclass(frozen=True)
class template_info:
    listTemplateType: str
    templateID: int
    baseType: int
    description: str

class list_template:
    CustomList = template_info(
        listTemplateType="Custom List",
        templateID=100,
        baseType=0,
        description="A basic list that can be adapted for multiple purposes."
    )

    DocumentLibrary = template_info(
        listTemplateType="Document Library",
        templateID=101,
        baseType=1,
        description="Contains a list of documents and other files."
    )

    Survey = template_info(
        listTemplateType="Survey",
        templateID=102,
        baseType=4,
        description="Fields (2) on a survey list represent questions that are asked of survey participants. Items in a list represent a set of responses to a survey."
    )

    Links = template_info(
        listTemplateType="Links",
        templateID=103,
        baseType=0,
        description="Contains a list of hyperlinks and their descriptions."
    )

    Announcements = template_info(
        listTemplateType="Announcements",
        templateID=104,
        baseType=0,
        description="Contains a set of simple announcements."
    )

    Contacts = template_info(
        listTemplateType="Contacts",
        templateID=105,
        baseType=0,
        description="Contains a list of contacts used for tracking people in a site (2)."
    )

    Calendar = template_info(
        listTemplateType="Calendar",
        templateID=106,
        baseType=0,
        description="Contains a list of single and recurring events. An events list has special views for displaying events on a calendar."
    )

    Tasks = template_info(
        listTemplateType="Tasks",
        templateID=107,
        baseType=0,
        description="Contains a list of items that represent finished and pending work items."
    )

    DiscussionBoard = template_info(
        listTemplateType="Discussion Board",
        templateID=108,
        baseType=0,
        description="Contains discussions entries and their replies."
    )

    PictureLibrary = template_info(
        listTemplateType="Picture Library",
        templateID=109,
        baseType=1,
        description="Contains a library adapted for storing and viewing digital pictures."
    )

    DataSources = template_info(
        listTemplateType="DataSources",
        templateID=110,
        baseType=1,
        description="Contains data connection description files."
    )

    FormLibrary = template_info(
        listTemplateType="Form Library",
        templateID=115,
        baseType=1,
        description="Contains XML documents. An XML form library can also contain templates for displaying and editing XML files through forms, as well as rules for specifying how XML data is converted to and from list items."
    )

    NoCodeWorkflows = template_info(
        listTemplateType="No Code Workflows",
        templateID=117,
        baseType=1,
        description="Contains additional workflow definitions that describe new processes that can be used in lists. These workflow definitions do not contain advanced code-based extensions."
    )

    CustomWorkflowProcess = template_info(
        listTemplateType="Custom Workflow Process",
        templateID=118,
        baseType=0,
        description="Contains a list used to support custom workflow process actions."
    )

    WikiPageLibrary = template_info(
        listTemplateType="Wiki Page Library",
        templateID=119,
        baseType=1,
        description="Contains a set of editable Web pages."
    )

    CustomGrid = template_info(
        listTemplateType="CustomGrid",
        templateID=120,
        baseType=0,
        description="Contains a set of list items with a grid-editing view."
    )

    NoCodePublicWorkflows = template_info(
        listTemplateType="No Code Public Workflows<14>",
        templateID=122,
        baseType=1,
        description="A gallery for storing workflow definitions that do not contain advanced code-based extensions."
    )

    WorkflowHistory = template_info(
        listTemplateType="Workflow History",
        templateID=140,
        baseType=0,
        description="Contains a set of history items for instances of workflows."
    )

    ProjectTasks = template_info(
        listTemplateType="Project Tasks",
        templateID=150,
        baseType=0,
        description="Contains a list of tasks with specialized views of task data in the form of Gantt chart."
    )

    PublicWorkflowsExternalList = template_info(
        listTemplateType="Public Workflows External List<15>",
        templateID=600,
        baseType=0,
        description="An external list for viewing the data of an external content type."
    )

    IssuesTracking = template_info(
        listTemplateType="Issues Tracking",
        templateID=1100,
        baseType=5,
        description="Contains a list of items to track issues."
    )

    @staticmethod
    def get_template_info_by_id(templateID: int) -> Optional[template_info]:
        # Recorremos todos los atributos de clase
        for attr_name, attr_value in vars(list_template).items():
            if isinstance(attr_value, template_info) and attr_value.templateID == templateID:
                return attr_value
        return None
