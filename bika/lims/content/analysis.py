"DuplicateAnalysis uses this as it's base.  This accounts for much confusion."

from AccessControl import getSecurityManager
from AccessControl import ClassSecurityInfo
from DateTime import DateTime
from bika.lims.utils.analysis import format_numeric_result
from plone.indexer import indexer
from Products.ATContentTypes.content import schemata
from Products.ATExtensions.ateapi import DateTimeField, DateTimeWidget, RecordsField
from Products.Archetypes import atapi
from Products.Archetypes.config import REFERENCE_CATALOG
from Products.Archetypes.public import *
from Products.Archetypes.references import HoldingReference
from Products.CMFCore.WorkflowCore import WorkflowException
from Products.CMFCore.permissions import View, ModifyPortalContent
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import safe_unicode, _createObjectByType
from Products.CMFEditions.ArchivistTool import ArchivistRetrieveError
from bika.lims import bikaMessageFactory as _
from bika.lims.utils import t
from bika.lims import logger
from bika.lims.browser.fields import DurationField
from bika.lims.browser.fields import HistoryAwareReferenceField
from bika.lims.browser.fields import InterimFieldsField
from bika.lims.permissions import *
from bika.lims.browser.widgets import DurationWidget
from bika.lims.browser.widgets import RecordsWidget as BikaRecordsWidget
from bika.lims.config import PROJECTNAME
from bika.lims.content.bikaschema import BikaSchema
from bika.lims.interfaces import IAnalysis
from bika.lims.interfaces import IReferenceSample
from bika.lims.utils import changeWorkflowState, formatDecimalMark
from bika.lims.workflow import skip
from bika.lims.workflow import doActionFor
from decimal import Decimal
from zope.interface import implements
import datetime
import math

@indexer(IAnalysis)
def Priority(instance):
    priority = instance.getPriority()
    if priority:
        return priority.getSortKey()

schema = BikaSchema.copy() + Schema((
    HistoryAwareReferenceField('Service',
        required=1,
        allowed_types=('AnalysisService',),
        relationship='AnalysisAnalysisService',
        referenceClass=HoldingReference,
        widget=ReferenceWidget(
            label=_("Analysis Service"),
        )
    ),
    HistoryAwareReferenceField('Calculation',
        allowed_types=('Calculation',),
        relationship='AnalysisCalculation',
        referenceClass=HoldingReference,
    ),
    ReferenceField('Attachment',
        multiValued=1,
        allowed_types=('Attachment',),
        referenceClass = HoldingReference,
        relationship = 'AnalysisAttachment',
    ),
    InterimFieldsField('InterimFields',
        widget = BikaRecordsWidget(
            label=_("Calculation Interim Fields"),
        )
    ),
    StringField('Result',
    ),
    DateTimeField('ResultCaptureDate',
        widget = ComputedWidget(
            visible=False,
        ),
    ),
    StringField('ResultDM',
    ),
    BooleanField('Retested',
        default = False,
    ),
    DurationField('MaxTimeAllowed',
        widget = DurationWidget(
            label=_("Maximum turn-around time"),
            description=_("Maximum time allowed for completion of the analysis. "
                            "A late analysis alert is raised when this period elapses"),
        ),
    ),
    DateTimeField('DateAnalysisPublished',
        widget = DateTimeWidget(
            label=_("Date Published"),
        ),
    ),
    DateTimeField('DueDate',
        widget = DateTimeWidget(
            label=_("Due Date"),
        ),
    ),
    IntegerField('Duration',
        widget = IntegerWidget(
            label=_("Duration"),
        )
    ),
    IntegerField('Earliness',
        widget = IntegerWidget(
            label=_("Earliness"),
        )
    ),
    BooleanField('ReportDryMatter',
        default = False,
    ),
    StringField('Analyst',
    ),
    TextField('Remarks',
    ),
    ReferenceField('Instrument',
        required = 0,
        allowed_types = ('Instrument',),
        relationship = 'AnalysisInstrument',
        referenceClass = HoldingReference,
    ),
    ReferenceField('Method',
        required = 0,
        allowed_types = ('Method',),
        relationship = 'AnalysisMethod',
        referenceClass = HoldingReference,
    ),
    ReferenceField('SamplePartition',
        required = 0,
        allowed_types = ('SamplePartition',),
        relationship = 'AnalysisSamplePartition',
        referenceClass = HoldingReference,
    ),
    ComputedField('ClientUID',
        expression = 'context.aq_parent.aq_parent.UID()',
    ),
    ComputedField('ClientTitle',
        expression = 'context.aq_parent.aq_parent.Title()',
    ),
    ComputedField('RequestID',
        expression = 'context.aq_parent.getRequestID()',
    ),
    ComputedField('ClientOrderNumber',
        expression = 'context.aq_parent.getClientOrderNumber()',
    ),
    ComputedField('Keyword',
        expression = 'context.getService().getKeyword()',
    ),
    ComputedField('ServiceTitle',
        expression = 'context.getService().Title()',
    ),
    ComputedField('ServiceUID',
        expression = 'context.getService().UID()',
    ),
    ComputedField('SampleTypeUID',
        expression = 'context.aq_parent.getSample().getSampleType().UID()',
    ),
    ComputedField('SamplePointUID',
        expression = 'context.aq_parent.getSample().getSamplePoint().UID() if context.aq_parent.getSample().getSamplePoint() else None',
    ),
    ComputedField('CategoryUID',
        expression = 'context.getService().getCategoryUID()',
    ),
    ComputedField('CategoryTitle',
        expression = 'context.getService().getCategoryTitle()',
    ),
    ComputedField('PointOfCapture',
        expression = 'context.getService().getPointOfCapture()',
    ),
    ComputedField('DateReceived',
        expression = 'context.aq_parent.getDateReceived()',
    ),
    ComputedField('DateSampled',
        expression = 'context.aq_parent.getSample().getDateSampled()',
    ),
    ComputedField('InstrumentValid',
        expression = 'context.isInstrumentValid()'
    ),
),
)


class Analysis(BaseContent):
    implements(IAnalysis)
    security = ClassSecurityInfo()
    displayContentsTab = False
    schema = schema

    def _getCatalogTool(self):
        from bika.lims.catalog import getCatalog
        return getCatalog(self)

    def Title(self):
        """ Return the service title as title.
        Some silliness here, for premature indexing, when the service
        is not yet configured.
        """
        try:
            s = self.getService()
            if s:
                s = s.Title()
            if not s:
                s = ''
        except ArchivistRetrieveError:
            s = ''
        return safe_unicode(s).encode('utf-8')

    def updateDueDate(self):
        # set the max hours allowed

        service = self.getService()
        maxtime = service.getMaxTimeAllowed()
        if not maxtime:
            maxtime = {'days': 0, 'hours': 0, 'minutes': 0}
        self.setMaxTimeAllowed(maxtime)
        # set the due date
        # default to old calc in case no calendars
        max_days = float(maxtime.get('days', 0)) + \
                 (
                     (float(maxtime.get('hours', 0)) * 3600 +
                      float(maxtime.get('minutes', 0)) * 60)
                     / 86400
                 )
        part = self.getSamplePartition()
        if part:
            starttime = part.getDateReceived()
            if starttime:
                duetime = starttime + max_days
            else:
                duetime = ''
            self.setDueDate(duetime)

    def getReviewState(self):
        """ Return the current analysis' state"""
        workflow = getToolByName(self, "portal_workflow")
        return workflow.getInfoFor(self, "review_state")

    def getUncertainty(self, result=None):
        """ Calls self.Service.getUncertainty with either the provided
            result value or self.Result
        """
        return self.getService().getUncertainty(result and result or self.getResult())

    def getDependents(self):
        """ Return a list of analyses who depend on us
            to calculate their result
        """
        rc = getToolByName(self, REFERENCE_CATALOG)
        dependents = []
        service = self.getService()
        ar = self.aq_parent
        for sibling in ar.getAnalyses(full_objects=True):
            if sibling == self:
                continue
            service = rc.lookupObject(sibling.getServiceUID())
            calculation = service.getCalculation()
            if not calculation:
                continue
            depservices = calculation.getDependentServices()
            dep_keywords = [x.getKeyword() for x in depservices]
            if self.getService().getKeyword() in dep_keywords:
                dependents.append(sibling)
        return dependents

    def getDependencies(self):
        """ Return a list of analyses who we depend on
            to calculate our result.
        """
        siblings = self.aq_parent.getAnalyses(full_objects=True)
        calculation = self.getService().getCalculation()
        if not calculation:
            return []
        dep_services = [d.UID() for d in calculation.getDependentServices()]
        dep_analyses = [a for a in siblings if a.getServiceUID() in dep_services]
        return dep_analyses

    def setResult(self, value, **kw):
        # Always update ResultCapture date when this field is modified
        self.setResultCaptureDate(DateTime())
        self.getField('Result').set(self, value, **kw)

    def getSample(self):
        return self.aq_parent.getSample()

    def getAnalysisSpecs(self, specification=None):
        """ Retrieves the analysis specs to be applied to this analysis.
            Allowed values for specification= 'client', 'lab', None
            If specification is None, client specification gets priority from
            lab specification.
            If no specification available for this analysis, returns None
        """
        sample = self.getSample()

        # No specifications available for ReferenceSamples
        if IReferenceSample.providedBy(sample):
            return None

        sampletype = sample.getSampleType()
        sampletype_uid = sampletype and sampletype.UID() or ''
        bsc = getToolByName(self, 'bika_setup_catalog')

        # retrieves the desired specs if None specs defined
        if not specification:
            proxies = bsc(portal_type='AnalysisSpec',
                          getClientUID=self.getClientUID(),
                          getSampleTypeUID=sampletype_uid)

            if len(proxies) == 0:
                # No client specs available, retrieve lab specs
                labspecsuid = self.bika_setup.bika_analysisspecs.UID()
                proxies = bsc(portal_type='AnalysisSpec',
                              getSampleTypeUID=sampletype_uid,
                              getClientUID=labspecsuid)
        else:
            specuid = specification == "client" and self.getClientUID() or \
                    self.bika_setup.bika_analysisspecs.UID()
            proxies = bsc(portal_type='AnalysisSpec',
                              getSampleTypeUID=sampletype_uid,
                              getClientUID=specuid)

        return (proxies and len(proxies) > 0) and proxies[0].getObject() or None

    def calculateResult(self, override=False, cascade=False):
        """ Calculates the result for the current analysis if it depends of
            other analysis/interim fields. Otherwise, do nothing
        """

        if self.getResult() and override == False:
            return False

        calculation = self.getService().getCalculation()
        if not calculation:
            return False

        mapping = {}

        # Add interims to mapping
        for interimdata in self.getInterimFields():
            for i in interimdata:
                try:
                    ivalue = float(i['value'])
                    mapping[i['keyword']] = ivalue
                except:
                    # Interim not float, abort
                    return False

        # Add calculation's hidden interim fields to mapping
        for field in calculation.getInterimFields():
            if field['keyword'] not in mapping.keys():
                if field.get('hidden', False):
                    try:
                        ivalue = float(field['value'])
                        mapping[field['keyword']] = ivalue
                    except:
                        return False

        # Add Analysis Service interim defaults to mapping
        service = self.getService()
        for field in service.getInterimFields():
            if field['keyword'] not in mapping.keys():
                if field.get('hidden', False):
                    try:
                        ivalue = float(field['value'])
                        mapping[field['keyword']] = ivalue
                    except:
                        return False

        # Add dependencies results to mapping
        dependencies = self.getDependencies()
        for dependency in dependencies:
            result = dependency.getResult()
            if not result:
                # Dependency without results found
                if cascade:
                    # Try to calculate the dependency result
                    dependency.calculateResult(override, cascade)
                    result = dependency.getResult()
                    if result:
                        try:
                            result = float(str(result))
                            mapping[dependency.getKeyword()] = result
                        except:
                            return False
                else:
                    return False
            else:
                # Result must be float
                try:
                    result = float(str(result))
                    mapping[dependency.getKeyword()] = result
                except:
                    return False

        # Calculate
        formula = calculation.getMinifiedFormula()
        formula = formula.replace('[', '%(').replace(']', ')f')
        try:
            formula = eval("'%s'%%mapping" % formula,
                               {"__builtins__": None,
                                'math': math,
                                'context': self},
                               {'mapping': mapping})
            result = eval(formula)
        except TypeError:
            self.setResult("NA")
            return True
        except ZeroDivisionError:
            self.setResult('0/0')
            return True
        except KeyError as e:
            self.setResult("NA")
            return True

        self.setResult(result)
        return True

    def get_default_specification(self):
        bsc = getToolByName(self, "bika_setup_catalog")
        spec = None
        sampletype = self.getSample().getSampleType()
        keyword = self.getKeyword()
        client_folder_uid = self.aq_parent.aq_parent.UID()
        client_specs = bsc(
            portal_type="AnalysisSpec",
            getSampleTypeUID=sampletype.UID(),
            getClientUID=client_folder_uid
        )
        for client_spec in client_specs:
            rr = client_spec.getObject().getResultsRange()
            kw_list = [r for r in rr if r['keyword'] == keyword]
            if kw_list:
                    spec = kw_list[0]
            break
        if not spec:
            lab_folder_uid = self.bika_setup.bika_analysisspecs.UID()
            lab_specs = bsc(
                portal_type="AnalysisSpec",
                getSampleTypeUID=sampletype.UID(),
                getClientUID=lab_folder_uid
            )
            for lab_spec in lab_specs:
                rr = lab_spec.getObject().getResultsRange()
                kw_list = [r for r in rr if r['keyword'] == keyword]
                if kw_list:
                    spec = kw_list[0]
                    break
        if not spec:
            return {"min": "", "max": "", "error": ""}
        return spec

    def getPriority(self):
        """ get priority from AR
        """
        # this analysis may be a Duplicate or Reference Analysis - CAREFUL
        # these types still subclass Analysis.
        if self.portal_type != 'Analysis':
            return None
        # this analysis could be in a worksheet or instrument, careful
        return self.aq_parent.getPriority() \
            if hasattr(self.aq_parent, 'getPriority') else None

    def getPrice(self):
        price = self.getService().getPrice()
        priority = self.getPriority()
        if priority and priority.getPricePremium() > 0:
            price = Decimal(price) + (
                      Decimal(price) * Decimal(priority.getPricePremium())
                      / 100)
        return price

    def getVATAmount(self):
        vat = self.getService().getVAT()
        price = self.getPrice()
        return float(price) * float(vat) / 100

    def getTotalPrice(self):
        return float(self.getPrice()) + float(self.getVATAmount())

    def isInstrumentValid(self):
        """ Checks if the instrument selected for this analysis service
            is valid. Returns false if an out-of-date or uncalibrated
            instrument is assigned. Returns true if the Analysis has
            no instrument assigned or is valid.
        """
        return self.getInstrument().isValid() \
                if self.getInstrument() else True

    def getDefaultInstrument(self):
        """ Returns the default instrument for this analysis according
            to its parent analysis service
        """
        return self.getService().getInstrument() \
            if self.getService().getInstrumentEntryOfResults() \
            else None

    def isInstrumentAllowed(self, instrument):
        """ Checks if the specified instrument can be set for this
            analysis, according to the Method and Analysis Service.
            If the Analysis Service hasn't set 'Allows instrument entry'
            of results, returns always False. Otherwise, checks if the
            method assigned is supported by the instrument specified.
            Returns false, If the analysis hasn't any method assigned.
            NP: The methods allowed for selection are defined at
            Analysis Service level.
            instrument param can be either an uid or an object
        """
        if isinstance(instrument, str):
            uid = instrument
        else:
            uid = instrument.UID()

        return uid in self.getAllowedInstruments()

    def isMethodAllowed(self, method):
        """ Checks if the analysis can follow the method specified.
            Looks for manually selected methods when AllowManualEntry
            is set and instruments methods when AllowInstrumentResultsEntry
            is set.
            method param can be either an uid or an object
        """
        if isinstance(method, str):
            uid = method
        else:
            uid = method.UID()

        return uid in self.getAllowedMethods()

    def getAllowedMethods(self, onlyuids=True):
        """ Returns the allowed methods for this analysis. If manual
            entry of results is set, only returns the methods set
            manually. Otherwise (if Instrument Entry Of Results is set)
            returns the methods assigned to the instruments allowed for
            this Analysis
        """
        service = self.getService()
        uids = []

        if service.getInstrumentEntryOfResults() == True:
            uids = [ins.getRawMethod() for ins in service.getInstruments()]

        else:
            # Get only the methods set manually
            uids = service.getRawMethods()

        if onlyuids == False:
            uc = getToolByName(self, 'uid_catalog')
            meths = [item.getObject() for item in uc(UID=uids)]
            return meths

        return uids

    def getAllowedInstruments(self, onlyuids=True):
        """ Returns the allowed instruments for this analysis. Gets the
            instruments assigned to the allowed methods
        """
        uids = []
        service = self.getService()

        if service.getInstrumentEntryOfResults() == True:
            uids = service.getRawInstruments()

        elif service.getManualEntryOfResults == True:
            meths = self.getAllowedMethods(False)
            for meth in meths:
                uids += meth.getInstrumentUIDs()
            set(uids)

        if onlyuids == False:
            uc = getToolByName(self, 'uid_catalog')
            instrs = [item.getObject() for item in uc(UID=uids)]
            return instrs

        return uids

    def getDefaultMethod(self):
        """ Returns the default method for this Analysis
            according to its current instrument. If the Analysis hasn't
            set yet an Instrument, looks to the Service
        """
        instr = self.getInstrument() \
            if self.getInstrument else self.getDefaultInstrument()
        return instr.getMethod() if instr else None

    def getFormattedResult(self, specs=None, decimalmark='.'):
        """Formatted result:
        1. Print ResultText of matching ResultOptions
        2. If the result is not floatable, return it without being formatted
        3. If the analysis specs has hidemin or hidemax enabled and the
           result is out of range, render result as '<min' or '>max'
        4. Otherwise, render numerical value
        specs param is optional. A dictionary as follows:
            {'min': <min_val>,
             'max': <max_val>,
             'error': <error>,
             'hidemin': <hidemin_val>,
             'hidemax': <hidemax_val>}
        """
        result = self.getResult()
        service = self.getService()
        choices = service.getResultOptions()

        # 1. Print ResultText of matching ResulOptions
        match = [x['ResultText'] for x in choices
                 if str(x['ResultValue']) == str(result)]
        if match:
            return match[0]

        # 2. If the result is not floatable, return it without being formatted
        try:
            result = float(result)
        except:
            return result

        # 3. If the analysis specs has enabled hidemin or hidemax and the
        #    result is out of range, render result as '<min' or '>max'
        belowmin = False
        abovemax = False
        if not specs:
            specs = self.getAnalysisSpecs()
            specs = specs.getResultsRangeDict() if specs is not None else {}
            specs = specs.get(self.getKeyword(), {})
        hidemin = specs.get('hidemin', '')
        hidemax = specs.get('hidemax', '')
        try:
            belowmin = hidemin and result < float(hidemin) or False
        except:
            belowmin = False
            pass
        try:
            abovemax = hidemax and result > float(hidemax) or False
        except:
            abovemax = False
            pass

        # 3.1. If result is below min and hidemin enabled, return '<min'
        if belowmin:
            return formatDecimalMark('< %s' % hidemin, decimalmark)

        # 3.2. If result is above max and hidemax enabled, return '>max'
        if abovemax:
            return formatDecimalMark('> %s' % hidemax, decimalmark)

        # Render numerical value
        return formatDecimalMark(format_numeric_result(self, result), decimalmark)

    def getAnalyst(self):
        """ Returns the identifier of the assigned analyst. If there is
            no analyst assigned, and this analysis is attached to a
            worksheet, retrieves the analyst assigned to the parent
            worksheet
        """
        field = self.getField('Analyst')
        analyst = field and field.get(self) or ''
        if not analyst:
            # Is assigned to a worksheet?
            wss = self.getBackReferences('WorksheetAnalysis')
            if len(wss) > 0:
                analyst = wss[0].getAnalyst()
                field.set(self, analyst)
        return analyst if analyst else ''

    def getAnalystName(self):
        """ Returns the name of the currently assigned analyst
        """
        mtool = getToolByName(self, 'portal_membership')
        analyst = self.getAnalyst().strip()
        analyst_member = mtool.getMemberById(analyst)
        if analyst_member != None:
            return analyst_member.getProperty('fullname')
        else:
            return ''

    def guard_sample_transition(self):
        workflow = getToolByName(self, "portal_workflow")
        if workflow.getInfoFor(self, "cancellation_state", "active") == "cancelled":
            return False
        return True

    def guard_retract_transition(self):
        workflow = getToolByName(self, "portal_workflow")
        if workflow.getInfoFor(self, "cancellation_state", "active") == "cancelled":
            return False
        return True

    def guard_receive_transition(self):
        workflow = getToolByName(self, "portal_workflow")
        if workflow.getInfoFor(self, "cancellation_state", "active") == "cancelled":
            return False
        return True

    def guard_publish_transition(self):
        workflow = getToolByName(self, "portal_workflow")
        if workflow.getInfoFor(self, "cancellation_state", "active") == "cancelled":
            return False
        return True

    def guard_import_transition(self):
        workflow = getToolByName(self, "portal_workflow")
        if workflow.getInfoFor(self, "cancellation_state", "active") == "cancelled":
            return False
        return True

    def guard_attach_transition(self):
        if self.portal_type in ("Analysis",
                                "ReferenceAnalysis",
                                "DuplicateAnalysis"):
            if not self.getAttachment():
                service = self.getService()
                if service.getAttachmentOption() == "r":
                    return False
        return True

    def guard_verify_transition(self):
        workflow = getToolByName(self, "portal_workflow")
        mtool = getToolByName(self, "portal_membership")
        checkPermission = mtool.checkPermission
        if workflow.getInfoFor(self, 'cancellation_state', 'active') == "cancelled":
            return False
        # Only Analysis needs to have dependencies checked
        if self.portal_type == "Analysis":
            for d in self.getDependencies():
                review_state = workflow.getInfoFor(d, "review_state")
                if review_state in ("to_be_sampled", "to_be_preserved", "sample_due",
                                    "sample_received", "attachment_due", "to_be_verified"):
                    return False
        # submitter and verifier compared
        # May we verify results that we ourself submitted?
        if checkPermission(VerifyOwnResults, self):
            return True
        # Check for self-submitted Analysis.
        user_id = getSecurityManager().getUser().getId()
        self_submitted = False
        review_history = workflow.getInfoFor(self, "review_history")
        review_history = self.reverseList(review_history)
        for event in review_history:
            if event.get("action") == "submit":
                if event.get("actor") == user_id:
                    self_submitted = True
                break
        if self_submitted:
            return False
        return True

    def guard_assign_transition(self):
        workflow = getToolByName(self, "portal_workflow")
        if workflow.getInfoFor(self, 'cancellation_state', 'active') == "cancelled":
            return False
        return True

    def guard_unassign_transition(self):
        """ Check permission against parent worksheet
        """
        workflow = getToolByName(self, "portal_workflow")
        mtool = getToolByName(self, "portal_membership")
        ws = self.getBackReferences("WorksheetAnalysis")
        if not ws:
            return False
        ws = ws[0]
        if workflow.getInfoFor(ws, "cancellation_state", "") == "cancelled":
            return False
        if mtool.checkPermission(Unassign, ws):
            return True
        return False

    def workflow_script_receive(self):
        workflow = getToolByName(self, "portal_workflow")
        if workflow.getInfoFor(self, 'cancellation_state', 'active') == "cancelled":
            return False
        # DuplicateAnalysis doesn't have analysis_workflow.
        if self.portal_type == "DuplicateAnalysis":
            return
        if skip(self, "receive"):
            return
        self.updateDueDate()
        self.reindexObject()

    def workflow_script_submit(self):
        # DuplicateAnalysis doesn't have analysis_workflow.
        if self.portal_type == "DuplicateAnalysis":
            return
        if skip(self, "submit"):
            return
        workflow = getToolByName(self, "portal_workflow")
        if workflow.getInfoFor(self, 'cancellation_state', 'active') == "cancelled":
            return False
        ar = self.aq_parent
        self.reindexObject(idxs=["review_state", ])
        # Dependencies are submitted already, ignore them.
        #-------------------------------------------------
        # Submit our dependents
        # Need to check for result and status of dependencies first
        dependents = self.getDependents()
        for dependent in dependents:
            if not skip(dependent, "submit", peek=True):
                can_submit = True
                if not dependent.getResult():
                    can_submit = False
                else:
                    interim_fields = False
                    service = dependent.getService()
                    calculation = service.getCalculation()
                    if calculation:
                        interim_fields = calculation.getInterimFields()
                    if interim_fields:
                        can_submit = False
                if can_submit:
                    dependencies = dependent.getDependencies()
                    for dependency in dependencies:
                        if workflow.getInfoFor(dependency, "review_state") in \
                           ("to_be_sampled", "to_be_preserved",
                            "sample_due", "sample_received",):
                            can_submit = False
                if can_submit:
                    workflow.doActionFor(dependent, "submit")

        # If all analyses in this AR have been submitted
        # escalate the action to the parent AR
        if not skip(ar, "submit", peek=True):
            all_submitted = True
            for a in ar.getAnalyses():
                if a.review_state in \
                   ("to_be_sampled", "to_be_preserved",
                    "sample_due", "sample_received",):
                    all_submitted = False
                    break
            if all_submitted:
                workflow.doActionFor(ar, "submit")

        # If assigned to a worksheet and all analyses on the worksheet have been submitted,
        # then submit the worksheet.
        ws = self.getBackReferences("WorksheetAnalysis")
        if ws:
            ws = ws[0]
            # if the worksheet analyst is not assigned, the worksheet can't  be transitioned.
            if ws.getAnalyst() and not skip(ws, "submit", peek=True):
                all_submitted = True
                for a in ws.getAnalyses():
                    if workflow.getInfoFor(a, "review_state") in \
                       ("to_be_sampled", "to_be_preserved",
                        "sample_due", "sample_received", "assigned",):
                        # Note: referenceanalyses and duplicateanalyses can still have review_state = "assigned".
                        all_submitted = False
                        break
                if all_submitted:
                    workflow.doActionFor(ws, "submit")

        # If no problem with attachments, do 'attach' action for this instance.
        can_attach = True
        if not self.getAttachment():
            service = self.getService()
            if service.getAttachmentOption() == "r":
                can_attach = False
        if can_attach:
            dependencies = self.getDependencies()
            for dependency in dependencies:
                if workflow.getInfoFor(dependency, "review_state") in \
                   ("to_be_sampled", "to_be_preserved", "sample_due",
                    "sample_received", "attachment_due",):
                    can_attach = False
        if can_attach:
            try:
                workflow.doActionFor(self, "attach")
            except WorkflowException:
                pass

    def workflow_script_retract(self):
        # DuplicateAnalysis doesn't have analysis_workflow.
        if self.portal_type == "DuplicateAnalysis":
            return
        if skip(self, "retract"):
            return
        ar = self.aq_parent
        workflow = getToolByName(self, "portal_workflow")
        if workflow.getInfoFor(self, 'cancellation_state', 'active') == "cancelled":
            return False
        # We'll assign the new analysis to this same worksheet, if any.
        ws = self.getBackReferences("WorksheetAnalysis")
        if ws:
            ws = ws[0]
        # Rename the analysis to make way for it's successor.
        # Support multiple retractions by renaming to *-0, *-1, etc
        parent = self.aq_parent
        analyses = [x for x in parent.objectValues("Analysis")
                    if x.getId().startswith(self.id)]
        kw = self.getKeyword()
        # LIMS-1290 - Analyst must be able to retract, which creates a new Analysis.
        parent._verifyObjectPaste = str   # I cancel the permission check with this.
        parent.manage_renameObject(kw, "{0}-{1}".format(kw, len(analyses)))
        delattr(parent, '_verifyObjectPaste')
        # Create new analysis and copy values from retracted
        analysis = _createObjectByType("Analysis", parent, kw)
        analysis.edit(
            Service=self.getService(),
            Calculation=self.getCalculation(),
            InterimFields=self.getInterimFields(),
            Result=self.getResult(),
            ResultDM=self.getResultDM(),
            Retested=True,  # True
            MaxTimeAllowed=self.getMaxTimeAllowed(),
            DueDate=self.getDueDate(),
            Duration=self.getDuration(),
            ReportDryMatter=self.getReportDryMatter(),
            Analyst=self.getAnalyst(),
            Instrument=self.getInstrument(),
            SamplePartition=self.getSamplePartition())
        analysis.unmarkCreationFlag()

        # We must bring the specification across manually.
        analysis.specification = self.specification

        # zope.event.notify(ObjectInitializedEvent(analysis))
        changeWorkflowState(analysis,
                            "bika_analysis_workflow", "sample_received")
        if ws:
            ws.addAnalysis(analysis)
        analysis.reindexObject()
        # retract our dependencies
        if not "retract all dependencies" in self.REQUEST["workflow_skiplist"]:
            for dependency in self.getDependencies():
                if not skip(dependency, "retract", peek=True):
                    if workflow.getInfoFor(dependency, "review_state") in ("attachment_due", "to_be_verified",):
                        # (NB: don"t retract if it"s verified)
                        workflow.doActionFor(dependency, "retract")
        # Retract our dependents
        for dep in self.getDependents():
            if not skip(dep, "retract", peek=True):
                if workflow.getInfoFor(dep, "review_state") not in ("sample_received", "retracted"):
                    self.REQUEST["workflow_skiplist"].append("retract all dependencies")
                    # just return to "received" state, no cascade
                    workflow.doActionFor(dep, 'retract')
                    self.REQUEST["workflow_skiplist"].remove("retract all dependencies")
        # Escalate action to the parent AR
        if not skip(ar, "retract", peek=True):
            if workflow.getInfoFor(ar, "review_state") == "sample_received":
                skip(ar, "retract")
            else:
                if not "retract all analyses" in self.REQUEST["workflow_skiplist"]:
                    self.REQUEST["workflow_skiplist"].append("retract all analyses")
                workflow.doActionFor(ar, "retract")
        # Escalate action to the Worksheet (if it's on one).
        ws = self.getBackReferences("WorksheetAnalysis")
        if ws:
            ws = ws[0]
            if not skip(ws, "retract", peek=True):
                if workflow.getInfoFor(ws, "review_state") == "open":
                    skip(ws, "retract")
                else:
                    if not "retract all analyses" in self.REQUEST['workflow_skiplist']:
                        self.REQUEST["workflow_skiplist"].append("retract all analyses")
                    try:
                        workflow.doActionFor(ws, "retract")
                    except WorkflowException:
                        pass
            # Add to worksheet Analyses
            analyses = list(ws.getAnalyses())
            analyses += [analysis, ]
            ws.setAnalyses(analyses)
            # Add to worksheet layout
            layout = ws.getLayout()
            pos = [x["position"] for x in layout
                   if x["analysis_uid"] == self.UID()][0]
            slot = {"position": pos,
                    "analysis_uid": analysis.UID(),
                    "container_uid": analysis.aq_parent.UID(),
                    "type": "a"}
            layout.append(slot)
            ws.setLayout(layout)

    def workflow_script_verify(self):
        # DuplicateAnalysis doesn't have analysis_workflow.
        if self.portal_type == "DuplicateAnalysis":
            return
        if skip(self, "verify"):
            return
        workflow = getToolByName(self, "portal_workflow")
        if workflow.getInfoFor(self, 'cancellation_state', 'active') == "cancelled":
            return False
        self.reindexObject(idxs=["review_state", ])
        # If all analyses in this AR are verified
        # escalate the action to the parent AR
        ar = self.aq_parent
        if not skip(ar, "verify", peek=True):
            all_verified = True
            for a in ar.getAnalyses():
                if a.review_state in \
                   ("to_be_sampled", "to_be_preserved", "sample_due",
                    "sample_received", "attachment_due", "to_be_verified"):
                    all_verified = False
                    break
            if all_verified:
                if not "verify all analyses" in self.REQUEST['workflow_skiplist']:
                    self.REQUEST["workflow_skiplist"].append("verify all analyses")
                workflow.doActionFor(ar, "verify")
        # If this is on a worksheet and all it's other analyses are verified,
        # then verify the worksheet.
        ws = self.getBackReferences("WorksheetAnalysis")
        if ws:
            ws = ws[0]
            ws_state = workflow.getInfoFor(ws, "review_state")
            if ws_state == "to_be_verified" and not skip(ws, "verify", peek=True):
                all_verified = True
                for a in ws.getAnalyses():
                    if workflow.getInfoFor(a, "review_state") in \
                       ("to_be_sampled", "to_be_preserved", "sample_due",
                        "sample_received", "attachment_due", "to_be_verified",
                        "assigned"):
                        # Note: referenceanalyses and duplicateanalyses can
                        # still have review_state = "assigned".
                        all_verified = False
                        break
                if all_verified:
                    if not "verify all analyses" in self.REQUEST['workflow_skiplist']:
                        self.REQUEST["workflow_skiplist"].append("verify all analyses")
                    workflow.doActionFor(ws, "verify")

    def workflow_script_publish(self):
        workflow = getToolByName(self, "portal_workflow")
        if workflow.getInfoFor(self, 'cancellation_state', 'active') == "cancelled":
            return False
        # DuplicateAnalysis doesn't have analysis_workflow.
        if self.portal_type == "DuplicateAnalysis":
            return
        if skip(self, "publish"):
            return
        endtime = DateTime()
        self.setDateAnalysisPublished(endtime)
        starttime = self.aq_parent.getDateReceived()
        starttime = starttime or self.created()
        service = self.getService()
        maxtime = service.getMaxTimeAllowed()
        # set the instance duration value to default values
        # in case of no calendars or max hours
        if maxtime:
            duration = (endtime - starttime) * 24 * 60
            maxtime_delta = int(maxtime.get("hours", 0)) * 86400
            maxtime_delta += int(maxtime.get("hours", 0)) * 3600
            maxtime_delta += int(maxtime.get("minutes", 0)) * 60
            earliness = duration - maxtime_delta
        else:
            earliness = 0
            duration = 0
        self.setDuration(duration)
        self.setEarliness(earliness)
        self.reindexObject()

    def workflow_script_cancel(self):
        if skip(self, "cancel"):
            return
        # DuplicateAnalysis doesn't have analysis_workflow.
        if self.portal_type == "DuplicateAnalysis":
            return
        workflow = getToolByName(self, "portal_workflow")
        self.reindexObject(idxs=["worksheetanalysis_review_state", ])
        # If it is assigned to a worksheet, unassign it.
        if workflow.getInfoFor(self, 'worksheetanalysis_review_state') == 'assigned':
            ws = self.getBackReferences("WorksheetAnalysis")[0]
            skip(self, "cancel", unskip=True)
            ws.removeAnalysis(self)

    def workflow_script_attach(self):
        # DuplicateAnalysis doesn't have analysis_workflow.
        if self.portal_type == "DuplicateAnalysis":
            return
        if skip(self, "attach"):
            return
        workflow = getToolByName(self, "portal_workflow")
        self.reindexObject(idxs=["review_state", ])
        # If all analyses in this AR have been attached
        # escalate the action to the parent AR
        ar = self.aq_parent
        ar_state = workflow.getInfoFor(ar, "review_state")
        if ar_state == "attachment_due" and not skip(ar, "attach", peek=True):
            can_attach = True
            for a in ar.getAnalyses():
                if a.review_state in \
                   ("to_be_sampled", "to_be_preserved",
                    "sample_due", "sample_received", "attachment_due",):
                    can_attach = False
                    break
            if can_attach:
                workflow.doActionFor(ar, "attach")
        # If assigned to a worksheet and all analyses on the worksheet have been attached,
        # then attach the worksheet.
        ws = self.getBackReferences('WorksheetAnalysis')
        if ws:
            ws = ws[0]
            ws_state = workflow.getInfoFor(ws, "review_state")
            if ws_state == "attachment_due" and not skip(ws, "attach", peek=True):
                can_attach = True
                for a in ws.getAnalyses():
                    if workflow.getInfoFor(a, "review_state") in \
                       ("to_be_sampled", "to_be_preserved", "sample_due",
                        "sample_received", "attachment_due", "assigned",):
                        # Note: referenceanalyses and duplicateanalyses can still have review_state = "assigned".
                        can_attach = False
                        break
                if can_attach:
                    workflow.doActionFor(ws, "attach")

    def workflow_script_assign(self):
        # DuplicateAnalysis doesn't have analysis_workflow.
        if self.portal_type == "DuplicateAnalysis":
            return
        if skip(self, "assign"):
            return
        workflow = getToolByName(self, "portal_workflow")
        self.reindexObject(idxs=["worksheetanalysis_review_state", ])
        rc = getToolByName(self, REFERENCE_CATALOG)
        wsUID = self.REQUEST["context_uid"]
        ws = rc.lookupObject(wsUID)
        # retract the worksheet to 'open'
        ws_state = workflow.getInfoFor(ws, "review_state")
        if ws_state != "open":
            if "workflow_skiplist" not in self.REQUEST:
                self.REQUEST["workflow_skiplist"] = ["retract all analyses", ]
            else:
                self.REQUEST["workflow_skiplist"].append("retract all analyses")
            allowed_transitions = [t["id"] for t in workflow.getTransitionsFor(ws)]
            if "retract" in allowed_transitions:
                workflow.doActionFor(ws, "retract")
        # If all analyses in this AR have been assigned,
        # escalate the action to the parent AR
        if not skip(self, "assign", peek=True):
            if not self.getAnalyses(worksheetanalysis_review_state="unassigned"):
                try:
                    allowed_transitions = [t["id"] for t in workflow.getTransitionsFor(self)]
                    if "assign" in allowed_transitions:
                        workflow.doActionFor(self, "assign")
                except:
                    pass

    def workflow_script_unassign(self):
        # DuplicateAnalysis doesn't have analysis_workflow.
        if self.portal_type == "DuplicateAnalysis":
            return
        if skip(self, "unassign"):
            return
        workflow = getToolByName(self, "portal_workflow")
        self.reindexObject(idxs=["worksheetanalysis_review_state", ])
        rc = getToolByName(self, REFERENCE_CATALOG)
        wsUID = self.REQUEST["context_uid"]
        ws = rc.lookupObject(wsUID)
        # Escalate the action to the parent AR if it is assigned
        # Note: AR adds itself to the skiplist so we have to take it off again
        #       to allow multiple promotions/demotions (maybe by more than one instance).
        if workflow.getInfoFor(self, "worksheetanalysis_review_state") == "assigned":
            workflow.doActionFor(self, "unassign")
            skip(self, "unassign", unskip=True)
        # If it has been duplicated on the worksheet, delete the duplicates.
        dups = self.getBackReferences("DuplicateAnalysisAnalysis")
        for dup in dups:
            ws.removeAnalysis(dup)
        # May need to promote the Worksheet's review_state
        #  if all other analyses are at a higher state than this one was.
        # (or maybe retract it if there are no analyses left)
        # Note: duplicates, controls and blanks have 'assigned' as a review_state.
        can_submit = True
        can_attach = True
        can_verify = True
        ws_empty = True
        for a in ws.getAnalyses():
            ws_empty = False
            a_state = workflow.getInfoFor(a, "review_state")
            if a_state in \
               ("to_be_sampled", "to_be_preserved", "assigned",
                "sample_due", "sample_received",):
                can_submit = False
            else:
                if not ws.getAnalyst():
                    can_submit = False
            if a_state in \
               ("to_be_sampled", "to_be_preserved", "assigned",
                "sample_due", "sample_received", "attachment_due",):
                can_attach = False
            if a_state in \
               ("to_be_sampled", "to_be_preserved", "assigned", "sample_due",
                "sample_received", "attachment_due", "to_be_verified",):
                can_verify = False
        if not ws_empty:
        # Note: WS adds itself to the skiplist so we have to take it off again
        #       to allow multiple promotions (maybe by more than one instance).
            if can_submit and workflow.getInfoFor(ws, "review_state") == "open":
                workflow.doActionFor(ws, "submit")
                skip(ws, 'unassign', unskip=True)
            if can_attach and workflow.getInfoFor(ws, "review_state") == "attachment_due":
                workflow.doActionFor(ws, "attach")
                skip(ws, 'unassign', unskip=True)
            if can_verify and workflow.getInfoFor(ws, "review_state") == "to_be_verified":
                self.REQUEST['workflow_skiplist'].append("verify all analyses")
                workflow.doActionFor(ws, "verify")
                skip(ws, 'unassign', unskip=True)
        else:
            if workflow.getInfoFor(ws, "review_state") != "open":
                workflow.doActionFor(ws, "retract")
                skip(ws, "retract", unskip=True)


atapi.registerType(Analysis, PROJECTNAME)

