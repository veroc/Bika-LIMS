"""
    Sampling Round
"""

from Products.Archetypes.public import *

from AccessControl import ClassSecurityInfo
from bika.lims import bikaMessageFactory as _
from bika.lims.browser.fields import DurationField
from bika.lims.browser.widgets import DurationWidget
from bika.lims.browser.widgets import RecordsWidget as BikaRecordsWidget
from bika.lims.browser.widgets import ReferenceWidget as BikaReferenceWidget
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
    ReferenceField(
        'Template',
        allowed_types=('SRTemplate',),
        referenceClass=HoldingReference,
        relationship='SamplingRoundSRTemplate',
        mode='rw',
        read_permission=permissions.View,
        write_permission=permissions.ModifyPortalContent,
        widget=BikaReferenceWidget(
            label=_('Template'),
            size=20,
            visible={
                'edit': 'visible',
                'view': 'visible',
                'add': 'visible',
                'secondary': 'invisible'
            },
            catalog_name='bika_setup_catalog',
            showOn=True,
        ),
    ),
    DurationField(
        'SamplingFrequency',
        vocabulary_display_path_bound=sys.maxint,
        widget=DurationWidget(
            label=_('Sampling Frequency'),
            description=_('Indicate the amount of time between recurring '
                'field trips'),
        ),
    ),
    StringField(
        'Sampler',
        vocabulary='getSamplers',
        vocabulary_display_path_bound=sys.maxint,
        widget=SelectionWidget(
            label=_('Default Sampler'),
            description=_('Select the default Sampler to be assigned'),
        ),
    ),
    ReferenceField(
        'Department',
        allowed_types=('Department',),
        referenceClass=HoldingReference,
        relationship='SRTemplateDepartment',
        vocabulary_display_path_bound=sys.maxint,
        widget=BikaReferenceWidget(
            label=_('Department'),
            description=_('Select the lab Department responsible'),
            catalog_name='bika_setup_catalog',
            showOn=True,
        )
    ),
    TextField(
        'Instructions',
        searchable=True,
        default_content_type='text/plain',
        allowed_content_types=('text/plain'),
        default_output_type="text/plain",
        widget=TextAreaWidget(
            label=_('Sampling Instructions'),
            append_only=True,
        ),
    ),
    # ComputedField(
    #     'TotalSamplePoints',
    #     expression='context.getTotalSamplePoints()',
    #     widget=ComputedWidget(
    #         visible='visible',
    #         label=_('Total Sample Points'),
    #     ),
    # ),
    # ComputedField(
    #     'TotalContainers',
    #     expression='context.getTotalContainers()',
    #     widget=ComputedWidget(
    #         visible='visible',
    #         label=_('Total Containers'),
    #     ),
    # ),
))


schema['description'].widget.visible = True
schema['title'].widget.visible = True
schema['title'].validators = ('uniquefieldvalidator',)
# Update the validation layer after change the validator in runtime
schema['title']._validationLayer()


class SamplingRound(BaseContent):
    security = ClassSecurityInfo()
    schema = schema
    displayContentsTab = False

    _at_rename_after_creation = True
    def _renameAfterCreation(self, check_auto_id=False):
        renameAfterCreation(self)

    def getSamplers(self):
        users = getUsers(self, ['Sampler', 'LabManager', 'Manager'])
        return users

    # def getTotalSamplePoints(self):
    #     return len(self.getARTemplates())

    # def getTotalContainers(self):
    #     return reduce(
    #         lambda r,o: r + len(o.getPartitions()),
    #         self.getARTemplates(),
    #         0
    #     )


registerType(SamplingRound, PROJECTNAME)
