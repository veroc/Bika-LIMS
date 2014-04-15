"""
    Sample Round Template
"""

from Products.Archetypes.public import *

from AccessControl import ClassSecurityInfo
from bika.lims import bikaMessageFactory as _
from bika.lims.browser.widgets import RecordsWidget as BikaRecordsWidget
# from bika.lims.browser.widgets import ReferenceWidget
from bika.lims.browser.widgets import SRTemplateARTemplatesWidget
from bika.lims.config import PROJECTNAME
from bika.lims.content.bikaschema import BikaSchema
from bika.lims.idserver import renameAfterCreation
from bika.lims.utils import getUsers
from Products.Archetypes.references import HoldingReference
from Products.ATExtensions.field.records import RecordsField
from Products.CMFCore import permissions
from Products.CMFCore.utils import getToolByName
import sys


schema = BikaSchema.copy() + Schema((
    TextField(
        'Instructions',
        searchable = True,
        default_content_type='text/plain',
        allowed_content_types=('text/plain'),
        default_output_type="text/plain",
        widget = TextAreaWidget(
            label = _('Instructions'),
            append_only = True,
        ),
    ),
    StringField(
        'Sampler',
        vocabulary='getSamplers',
        vocabulary_display_path_bound=sys.maxint,
        widget=ReferenceWidget(
            label=_("Default Sampler"),
            description=_("Select the default Sampler to be assigned"),
        ),
    ),
    ReferenceField(
        'ARTemplates',
        schemata='AR Templates',
        required=1,
        multiValued=1,
        allowed_types=('ARTemplate',),
        relationship='SRTemplateARTemplate',
        widget=SRTemplateARTemplatesWidget(
            label=_("AR Templates"),
            description=_("Select AR Templates to include"),
        )
    ),
))


schema['description'].widget.visible = True
schema['title'].widget.visible = True
schema['title'].validators = ('uniquefieldvalidator',)
# Update the validation layer after change the validator in runtime
schema['title']._validationLayer()


class SRTemplate(BaseContent):
    security = ClassSecurityInfo()
    schema = schema
    displayContentsTab = False

    _at_rename_after_creation = True
    def _renameAfterCreation(self, check_auto_id=False):
        renameAfterCreation(self)

    def getSamplers(self):
        samplers = getUsers(self, ['Sampler', 'LabManager', 'Manager'])
        return samplers


registerType(SRTemplate, PROJECTNAME)
